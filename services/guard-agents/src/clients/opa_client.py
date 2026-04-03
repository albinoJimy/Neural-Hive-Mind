"""
Wrapper de compatibilidade para neural_hive_opa.

Mantém compatibilidade com a API original do OPAClient do guard-agents
enquanto usa a biblioteca unificada neural_hive_opa por baixo.
"""
from typing import Any, Dict, Optional

from neural_hive_opa import OPAClient as NeuralHiveOPAClient
from neural_hive_opa import OPAConfig
from neural_hive_opa.exceptions import OPAConnectionError, OPAPolicyNotFoundError
import structlog

logger = structlog.get_logger()


class OPAClient:
    """
    Wrapper de compatibilidade para OPAClient.

    Mantém a mesma interface do OPAClient original do guard-agents
    mas usa a biblioteca neural_hive_opa internamente.
    """

    def __init__(
        self,
        base_url: str = "http://opa:8181",
        timeout: float = 5.0,
    ):
        """
        Inicializa wrapper OPA.

        Args:
            base_url: URL base do OPA (compatibilidade com assinatura original)
            timeout: Timeout em segundos (compatibilidade com assinatura original)
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: Optional[NeuralHiveOPAClient] = None

    async def connect(self):
        """
        Inicializa cliente HTTP assíncrono (compatibilidade).

        Este método é um alias para initialize() para manter compatibilidade.
        """
        await self.initialize()

    async def initialize(self):
        """Inicializa cliente OPA."""
        # Criar configuração OPA
        opa_config = OPAConfig(
            opa_url=self.base_url,
            opa_timeout_seconds=int(self.timeout),
        )

        # Criar cliente unificado
        self._client = NeuralHiveOPAClient(config=opa_config, metrics=None)

        # Inicializar cliente
        await self._client.initialize()

        # Verifica conectividade (health check)
        try:
            is_healthy = await self._client.health_check()
            if is_healthy:
                logger.info("opa_client.connected", base_url=self.base_url)
            else:
                logger.warning("opa_client.health_check_failed")
        except Exception as e:
            logger.error("opa_client.connect_failed", base_url=self.base_url, error=str(e))
            raise

    async def close(self):
        """Fecha cliente HTTP"""
        if self._client:
            await self._client.close()
            logger.info("opa_client.closed")

    def is_connected(self) -> bool:
        """Verifica se cliente está conectado"""
        return self._client is not None

    async def evaluate_policy(
        self, policy_path: str, input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Avalia política OPA com dados de entrada.

        Args:
            policy_path: Caminho da política (e.g., "security/unauthorized_access")
            input_data: Dados para avaliação

        Returns:
            Dict com decisão OPA (formato compatível com código original)
        """
        if not self._client:
            raise RuntimeError("Client not connected")

        try:
            logger.debug("opa_client.evaluating_policy", policy_path=policy_path)

            # Usar cliente unificado para avaliar
            # O cliente unificado retorna resultado direto da OPA, que pode ter formato
            # diferente do esperado pelo código original
            result = await self._client.evaluate(policy_path, input_data)

            # Normalizar resultado para formato esperado pelo código original
            # O código original espera: {"allowed": True/False, ...}
            normalized_result = self._normalize_result(result)

            logger.debug(
                "opa_client.policy_evaluated",
                policy_path=policy_path,
                allowed=normalized_result.get("allowed"),
            )

            return normalized_result

        except OPAPolicyNotFoundError as e:
            logger.error(
                "opa_client.policy_not_found",
                policy_path=policy_path,
                error=str(e),
            )
            # Em caso de política não encontrada, retorna negado por segurança
            return {"allowed": False, "reason": f"Policy not found: {policy_path}", "error": True}
        except OPAConnectionError as e:
            logger.error(
                "opa_client.connection_failed",
                policy_path=policy_path,
                error=str(e),
            )
            # Em caso de erro de conexão, retorna negado por segurança
            return {"allowed": False, "reason": f"OPA connection failed: {str(e)}", "error": True}
        except Exception as e:
            logger.error("opa_client.evaluation_error", policy_path=policy_path, error=str(e))
            # Em caso de erro genérico, retorna negado por segurança
            return {"allowed": False, "reason": f"OPA error: {str(e)}", "error": True}

    def _normalize_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normaliza resultado do OPA para formato esperado pelo código original.

        O neural_hive_opa retorna {"allow": True/False, ...}
        O código original espera {"allowed": True/False, ...}

        Args:
            result: Resultado do neural_hive_opa

        Returns:
            Resultado normalizado
        """
        # Verificar se já tem formato esperado
        if "allowed" in result:
            return result

        # Verificar se tem "allow" (formato neural_hive_opa)
        if "allow" in result:
            # Converter "allow" para "allowed" mantendo resto dos campos
            normalized = dict(result)
            normalized["allowed"] = result["allow"]
            return normalized

        # Se não tem nenhum dos dois, assumir permitido e retornar resultado como está
        return {"allowed": True, **result}


# Exportar classes para compatibilidade
__all__ = ["OPAClient"]
