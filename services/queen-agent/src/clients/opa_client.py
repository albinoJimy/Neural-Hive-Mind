"""Cliente HTTP para integração com Open Policy Agent (OPA)"""
from typing import Dict, Any, Optional
import httpx
import structlog

logger = structlog.get_logger()


class OPAClient:
    """
    Cliente HTTP para validação de políticas com OPA.
    Integra com servidor OPA para decisões de enforcement.
    """

    def __init__(
        self,
        base_url: str = "http://opa:8181",
        timeout: float = 5.0
    ):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def connect(self):
        """Inicializa cliente HTTP assíncrono"""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout
        )

        # Verifica conectividade
        try:
            response = await self._client.get("/health")
            if response.status_code == 200:
                logger.info("opa_client.connected", base_url=self.base_url)
            else:
                logger.warning(
                    "opa_client.health_check_failed",
                    status_code=response.status_code
                )
        except Exception as e:
            logger.error(
                "opa_client.connect_failed",
                base_url=self.base_url,
                error=str(e)
            )
            raise

    async def close(self):
        """Fecha cliente HTTP"""
        if self._client:
            await self._client.aclose()
            logger.info("opa_client.closed")

    async def evaluate_policy(
        self,
        policy_path: str,
        input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Avalia política OPA com dados de entrada.

        Args:
            policy_path: Caminho da política (e.g., "neuralhive/queen/ethical_guardrails")
            input_data: Dados para avaliação

        Returns:
            Dict com decisão OPA
        """
        if not self._client:
            raise RuntimeError("Client not connected")

        try:
            # OPA endpoint: /v1/data/{policy_path}
            url = f"/v1/data/{policy_path}"

            payload = {"input": input_data}

            logger.debug(
                "opa_client.evaluating_policy",
                policy_path=policy_path
            )

            response = await self._client.post(url, json=payload)
            response.raise_for_status()

            result = response.json()

            logger.debug(
                "opa_client.policy_evaluated",
                policy_path=policy_path,
                allowed=result.get("result", {}).get("allow")
            )

            return result.get("result", {})

        except httpx.HTTPStatusError as e:
            logger.error(
                "opa_client.evaluation_failed",
                policy_path=policy_path,
                status_code=e.response.status_code,
                error=str(e)
            )
            # Em caso de erro, retorna negado por segurança
            return {
                "allow": False,
                "reason": f"OPA evaluation failed: {str(e)}",
                "error": True
            }
        except Exception as e:
            logger.error(
                "opa_client.evaluation_error",
                policy_path=policy_path,
                error=str(e)
            )
            return {
                "allow": False,
                "reason": f"OPA error: {str(e)}",
                "error": True
            }

    def is_connected(self) -> bool:
        """Verifica se cliente está conectado"""
        return self._client is not None
