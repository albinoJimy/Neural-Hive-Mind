"""
Wrapper de compatibilidade para neural_hive_opa.

Mantém compatibilidade com a API original do OPAClient do architect-agent
enquanto usa a biblioteca unificada neural_hive_opa por baixo.
"""
from typing import Any, Dict

from neural_hive_opa import OPAClient as NeuralHiveOPAClient
from neural_hive_opa import OPAConfig, OPAConnectionError, OPAEvaluationError
from neural_hive_opa.exceptions import OPAPolicyNotFoundError
import structlog

from src.config.settings import get_settings

logger = structlog.get_logger(__name__)


class OPAClient:
    """
    Wrapper de compatibilidade para OPAClient.

    Mantém a mesma interface do OPAClient original do architect-agent
    mas usa a biblioteca neural_hive_opa internamente.
    """

    def __init__(self) -> None:
        """Inicializa wrapper OPA."""
        settings = get_settings()

        # Expor propriedades para compatibilidade com código original
        self.base_url = settings.opa.url
        self.timeout = settings.opa.timeout_seconds
        self.policy_path = settings.opa.policy_path

        # Criar configuração OPA para biblioteca unificada
        opa_config = OPAConfig(
            opa_url=settings.opa.url,
            opa_timeout_seconds=settings.opa.timeout_seconds,
            opa_cache_ttl_seconds=300,  # 5 minutos de cache
            opa_circuit_breaker_enabled=True,
            opa_circuit_breaker_failure_threshold=5,
            opa_circuit_breaker_reset_timeout_seconds=60,
            opa_max_concurrent_evaluations=20,
            opa_cache_max_size=1000,
            opa_enable_metrics=False,  # architect-agent não usa métricas OPA
        )

        # Criar cliente unificado
        self._client = NeuralHiveOPAClient(config=opa_config, metrics=None)

    async def initialize(self) -> None:
        """Inicializa cliente OPA."""
        await self._client.initialize()

    async def close(self) -> None:
        """Fecha cliente OPA."""
        await self._client.close()

    async def evaluate_policy(
        self, policy_path: str, input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Avalia política no OPA.

        Args:
            policy_path: Caminho da política
            input_data: Dados de entrada

        Returns:
            Resultado da avaliação
        """
        try:
            result = await self._client.evaluate(policy_path, input_data)
            return result
        except OPAPolicyNotFoundError as e:
            logger.warning("OPA policy not found", policy_path=policy_path, error=str(e))
            # Retornar resultado vazio para compatibilidade
            return {"violations": []}
        except (OPAConnectionError, OPAEvaluationError) as e:
            logger.error("OPA evaluation error", policy_path=policy_path, error=str(e))
            # Retornar resultado vazio para compatibilidade (fail open)
            return {"violations": []}

    async def check_architecture_rules(
        self, patterns: list[Dict[str, Any]], insights: Dict[str, Any]
    ) -> list[Dict[str, Any]]:
        """
        Verifica regras arquiteturais no OPA.

        Args:
            patterns: Lista de padrões de código
            insights: Insights do Scout Agents

        Returns:
            Lista de violações encontradas
        """
        input_data = {"patterns": patterns, "insights": insights}
        result = await self.evaluate_policy(self.policy_path, input_data)
        return result.get("violations", [])

    async def health_check(self) -> bool:
        """
        Verifica saúde da conexão OPA.

        Returns:
            True se OPA está saudável
        """
        return await self._client.health_check()

    def clear_cache(self) -> None:
        """Limpa cache de decisões."""
        self._client.clear_cache()

    def get_cache_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do cache."""
        return self._client.get_cache_stats()

    @property
    def session(self):
        """Sessão HTTP (compatibilidade)."""
        return self._client.session


# Exportar exceções para compatibilidade
__all__ = ["OPAClient"]
