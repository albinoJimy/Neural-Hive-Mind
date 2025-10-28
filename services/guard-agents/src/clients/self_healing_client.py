"""Cliente HTTP para integração com Self-Healing Engine"""
from typing import Dict, Any, Optional
import httpx
import structlog
from enum import Enum

logger = structlog.get_logger()


class RemediationStatus(str, Enum):
    """Status de execução de remediação"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class SelfHealingClient:
    """
    Cliente HTTP para comunicação com Self-Healing Engine.
    Permite solicitar execução de remediações e consultar status.
    """

    def __init__(
        self,
        base_url: str,
        timeout: float = 30.0,
        max_retries: int = 3
    ):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.max_retries = max_retries
        self._client: Optional[httpx.AsyncClient] = None

    async def connect(self):
        """Inicializa cliente HTTP assíncrono"""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=100)
        )

        # Verifica conectividade
        try:
            response = await self._client.get("/health")
            if response.status_code == 200:
                logger.info(
                    "self_healing_client.connected",
                    base_url=self.base_url
                )
            else:
                logger.warning(
                    "self_healing_client.health_check_failed",
                    status_code=response.status_code
                )
        except Exception as e:
            logger.error(
                "self_healing_client.connect_failed",
                base_url=self.base_url,
                error=str(e)
            )
            raise

    async def close(self):
        """Fecha cliente HTTP"""
        if self._client:
            await self._client.aclose()
            logger.info("self_healing_client.closed")

    async def trigger_remediation(
        self,
        remediation_id: str,
        incident_id: str,
        playbook_id: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Solicita execução de playbook de remediação.

        Args:
            remediation_id: ID único da remediação
            incident_id: ID do incidente relacionado
            playbook_id: ID do playbook a executar
            parameters: Parâmetros para execução do playbook

        Returns:
            Dict com resultado da solicitação
        """
        if not self._client:
            raise RuntimeError("Client not connected")

        payload = {
            "remediation_id": remediation_id,
            "incident_id": incident_id,
            "playbook_id": playbook_id,
            "parameters": parameters or {}
        }

        try:
            logger.info(
                "self_healing_client.triggering_remediation",
                remediation_id=remediation_id,
                playbook_id=playbook_id
            )

            response = await self._client.post(
                "/api/v1/remediation/execute",
                json=payload
            )

            response.raise_for_status()
            result = response.json()

            logger.info(
                "self_healing_client.remediation_triggered",
                remediation_id=remediation_id,
                status=result.get("status")
            )

            return result

        except httpx.HTTPStatusError as e:
            logger.error(
                "self_healing_client.trigger_failed",
                remediation_id=remediation_id,
                status_code=e.response.status_code,
                error=str(e)
            )
            raise
        except Exception as e:
            logger.error(
                "self_healing_client.trigger_error",
                remediation_id=remediation_id,
                error=str(e)
            )
            raise

    async def get_remediation_status(
        self,
        remediation_id: str
    ) -> Dict[str, Any]:
        """
        Consulta status de execução de remediação.

        Args:
            remediation_id: ID da remediação

        Returns:
            Dict com status e resultado
        """
        if not self._client:
            raise RuntimeError("Client not connected")

        try:
            response = await self._client.get(
                f"/api/v1/remediation/{remediation_id}/status"
            )

            response.raise_for_status()
            result = response.json()

            logger.debug(
                "self_healing_client.status_retrieved",
                remediation_id=remediation_id,
                status=result.get("status")
            )

            return result

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(
                    "self_healing_client.remediation_not_found",
                    remediation_id=remediation_id
                )
                return {
                    "remediation_id": remediation_id,
                    "status": "not_found",
                    "error": "Remediation not found"
                }
            logger.error(
                "self_healing_client.status_failed",
                remediation_id=remediation_id,
                status_code=e.response.status_code
            )
            raise
        except Exception as e:
            logger.error(
                "self_healing_client.status_error",
                remediation_id=remediation_id,
                error=str(e)
            )
            raise

    async def wait_for_completion(
        self,
        remediation_id: str,
        poll_interval: float = 2.0,
        max_wait: float = 300.0
    ) -> Dict[str, Any]:
        """
        Aguarda conclusão de remediação com polling.

        Args:
            remediation_id: ID da remediação
            poll_interval: Intervalo entre consultas (segundos)
            max_wait: Tempo máximo de espera (segundos)

        Returns:
            Dict com resultado final
        """
        import asyncio
        from datetime import datetime, timezone

        start_time = datetime.now(timezone.utc)

        logger.info(
            "self_healing_client.waiting_completion",
            remediation_id=remediation_id,
            max_wait=max_wait
        )

        while True:
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()

            if elapsed >= max_wait:
                logger.warning(
                    "self_healing_client.wait_timeout",
                    remediation_id=remediation_id,
                    elapsed=elapsed
                )
                return {
                    "remediation_id": remediation_id,
                    "status": "timeout",
                    "error": f"Timeout after {elapsed}s"
                }

            status = await self.get_remediation_status(remediation_id)
            current_status = status.get("status")

            if current_status in [
                RemediationStatus.COMPLETED,
                RemediationStatus.FAILED,
                RemediationStatus.ROLLED_BACK
            ]:
                logger.info(
                    "self_healing_client.completion_detected",
                    remediation_id=remediation_id,
                    status=current_status,
                    elapsed=elapsed
                )
                return status

            logger.debug(
                "self_healing_client.polling",
                remediation_id=remediation_id,
                status=current_status,
                elapsed=elapsed
            )

            await asyncio.sleep(poll_interval)

    async def cancel_remediation(
        self,
        remediation_id: str,
        reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Cancela execução de remediação em andamento.

        Args:
            remediation_id: ID da remediação
            reason: Motivo do cancelamento

        Returns:
            Dict com resultado do cancelamento
        """
        if not self._client:
            raise RuntimeError("Client not connected")

        payload = {
            "reason": reason or "Cancelled by guard agent"
        }

        try:
            logger.info(
                "self_healing_client.cancelling_remediation",
                remediation_id=remediation_id
            )

            response = await self._client.post(
                f"/api/v1/remediation/{remediation_id}/cancel",
                json=payload
            )

            response.raise_for_status()
            result = response.json()

            logger.info(
                "self_healing_client.remediation_cancelled",
                remediation_id=remediation_id
            )

            return result

        except Exception as e:
            logger.error(
                "self_healing_client.cancel_failed",
                remediation_id=remediation_id,
                error=str(e)
            )
            raise

    def is_connected(self) -> bool:
        """Verifica se cliente está conectado"""
        return self._client is not None
