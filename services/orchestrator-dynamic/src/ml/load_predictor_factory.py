"""
LoadPredictorFactory - Factory para criação de instâncias de LoadPredictor.

Fornece métodos para criar e inicializar LoadPredictor com injeção de dependências.
"""

import structlog
from typing import Any

from src.config.settings import OrchestratorSettings
from src.ml.load_predictor import LoadPredictor
from src.observability.metrics import OrchestratorMetrics

logger = structlog.get_logger(__name__)


class LoadPredictorFactory:
    """
    Factory para criação de instâncias de LoadPredictor.

    Responsável por:
    - Criar instâncias com configuração e dependências injetadas
    - Executar inicialização assíncrona (setup de cache, validações)
    - Fallback graceful quando dependências não disponíveis
    """

    @staticmethod
    def create(
        config: OrchestratorSettings,
        mongodb_client: Any,
        redis_client: Any,
        metrics: OrchestratorMetrics,
    ) -> LoadPredictor:
        """
        Cria uma instância de LoadPredictor.

        Args:
            config: Configurações do orchestrator
            mongodb_client: Cliente MongoDB para dados históricos
            redis_client: Cliente Redis para cache
            metrics: OrchestratorMetrics para observabilidade

        Returns:
            Instância de LoadPredictor configurada
        """
        return LoadPredictor(
            config=config,
            mongodb_client=mongodb_client,
            redis_client=redis_client,
            metrics=metrics,
        )

    @staticmethod
    async def create_and_initialize(
        config: OrchestratorSettings,
        mongodb_client: Any,
        redis_client: Any,
        metrics: OrchestratorMetrics,
    ) -> LoadPredictor:
        """
        Cria e inicializa uma instância de LoadPredictor.

        Executa setup assíncrono necessário (cache, validações).

        Args:
            config: Configurações do orchestrator
            mongodb_client: Cliente MongoDB para dados históricos
            redis_client: Cliente Redis para cache
            metrics: OrchestratorMetrics para observabilidade

        Returns:
            Instância de LoadPredictor configurada e inicializada
        """
        predictor = LoadPredictorFactory.create(
            config=config,
            mongodb_client=mongodb_client,
            redis_client=redis_client,
            metrics=metrics,
        )

        # Executar inicialização assíncrona
        await predictor.initialize()

        logger.info(
            "load_predictor_factory_created",
            mongodb_available=mongodb_client is not None,
            redis_available=redis_client is not None,
        )

        return predictor

    @staticmethod
    def create_or_none(
        config: OrchestratorSettings,
        mongodb_client: Any,
        redis_client: Any,
        metrics: OrchestratorMetrics,
    ) -> LoadPredictor | None:
        """
        Cria LoadPredictor ou retorna None se desabilitado.

        Verifica configuração ml_local_load_prediction_enabled antes de criar.

        Args:
            config: Configurações do orchestrator
            mongodb_client: Cliente MongoDB para dados históricos
            redis_client: Cliente Redis para cache
            metrics: OrchestratorMetrics para observabilidade

        Returns:
            Instância de LoadPredictor ou None se desabilitado
        """
        if not getattr(config, "ml_local_load_prediction_enabled", True):
            logger.info("load_predictor_disabled_via_config")
            return None

        return LoadPredictorFactory.create(
            config=config,
            mongodb_client=mongodb_client,
            redis_client=redis_client,
            metrics=metrics,
        )
