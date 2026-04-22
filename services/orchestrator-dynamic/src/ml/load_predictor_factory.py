"""
LoadPredictorFactory - Factory para criação do LoadPredictor centralizado.

Integra o LoadPredictor de neural_hive_ml com:
- Factory pattern para inicialização lazy
- Wrapper com cache Redis
- Fallback para LoadPredictor local quando centralizado indisponível
- Métricas Prometheus integradas
"""

import json
import time
from typing import Any, Optional

import structlog

from src.config.settings import OrchestratorSettings
from src.observability.metrics import OrchestratorMetrics

# Import centralizado de ML predictors
try:
    from neural_hive_ml.predictive_models import LoadPredictor as CentralLoadPredictor

    ML_AVAILABLE = True
except ImportError:
    CentralLoadPredictor = None
    ML_AVAILABLE = False

logger = structlog.get_logger(__name__)


class LoadPredictorWrapper:
    """
    Wrapper para LoadPredictor com cache Redis e fallback.

    Envolve o LoadPredictor centralizado para adicionar:
    - Cache Redis com TTL configurável
    - Tratamento de erros graceful
    - Métricas Prometheus
    - Fallback para predições stub quando desabilitado
    """

    def __init__(
        self,
        predictor: Optional[CentralLoadPredictor],
        config: OrchestratorSettings,
        redis_client,
        metrics: OrchestratorMetrics,
        enabled: bool = True,
    ):
        """
        Inicializa o wrapper.

        Args:
            predictor: Instância do LoadPredictor centralizado
            config: Configurações do orchestrator
            redis_client: Cliente Redis para cache
            metrics: Métricas Prometheus
            enabled: Se o wrapper está habilitado
        """
        self.predictor = predictor
        self.config = config
        self.redis_client = redis_client
        self.metrics = metrics
        self.enabled = enabled
        self.logger = logger.bind(component="load_predictor_wrapper")

        # Cache TTL
        self.cache_ttl = getattr(config, "load_predictor_cache_ttl_seconds", 300)

        # Horizontes configurados
        self.forecast_horizons = getattr(
            config, "load_predictor_forecast_horizons", [60, 360, 1440]
        )

    async def predict_load(
        self, horizon_minutes: int, include_confidence: bool = True
    ) -> dict[str, Any]:
        """
        Prediz carga do sistema para horizonte especificado.

        Usa cache Redis com TTL. Cache miss chama o predictor centralizado.

        Args:
            horizon_minutes: Horizonte de previsão em minutos
            include_confidence: Incluir intervalos de confiança

        Returns:
            Dict com forecast, timestamps, model_type, latency_seconds
        """
        if not self.enabled or not self.predictor:
            self.logger.debug("load_predictor_disabled", horizon_minutes=horizon_minutes)
            return {
                "forecast": [],
                "timestamps": [],
                "model_type": "disabled",
                "status": "disabled",
            }

        start_time = time.time()
        cache_key = f"load_forecast:{horizon_minutes}m"

        try:
            # Verificar cache
            if self.redis_client:
                from src.clients.redis_client import redis_get_safe

                cached = await redis_get_safe(cache_key)
                if cached:
                    self.logger.debug("load_forecast_cache_hit", horizon_minutes=horizon_minutes)
                    try:
                        result = json.loads(cached)
                        # Registrar métrica de cache hit
                        if self.metrics:
                            self.metrics.record_load_forecast_cache_hit(hit=True)
                        return result
                    except (json.JSONDecodeError, TypeError) as e:
                        self.logger.warning("cache_decode_error", error=str(e))

            # Cache miss - chamar predictor
            self.logger.debug("load_forecast_cache_miss", horizon_minutes=horizon_minutes)

            result = await self.predictor.predict_load(
                horizon_minutes=horizon_minutes, include_confidence=include_confidence
            )

            # Salvar no cache
            if self.redis_client and "error" not in result:
                from src.clients.redis_client import redis_setex_safe

                try:
                    await redis_setex_safe(cache_key, self.cache_ttl, json.dumps(result))
                except Exception as e:
                    self.logger.warning("cache_save_error", error=str(e))

            # Registrar métricas
            latency_seconds = time.time() - start_time
            if self.metrics:
                self.metrics.record_load_forecast_latency(
                    latency_seconds=latency_seconds, horizon_minutes=horizon_minutes
                )

                mape = result.get("mape", 0.0)
                if mape > 0:
                    self.metrics.record_load_forecast_mape(mape=mape)

            # Registrar cache miss
            if self.metrics:
                self.metrics.record_load_forecast_cache_hit(hit=False)

            return result

        except Exception as e:
            latency_seconds = time.time() - start_time
            self.logger.error(
                "load_forecast_error",
                horizon_minutes=horizon_minutes,
                error=str(e),
                latency_seconds=latency_seconds,
            )

            # Retornar resposta de erro gracefully
            if self.metrics:
                self.metrics.record_load_forecast_error(error_type=type(e).__name__)

            return {
                "forecast": [],
                "timestamps": [],
                "error": str(e),
                "model_type": "error",
                "latency_seconds": latency_seconds,
            }

    async def predict_bottlenecks(self, horizon_minutes: int = 360) -> list[dict[str, Any]]:
        """
        Identifica potenciais bottlenecks futuros.

        Args:
            horizon_minutes: Horizonte de análise

        Returns:
            Lista de bottlenecks previstos
        """
        if not self.enabled or not self.predictor:
            return []

        try:
            bottlenecks = await self.predictor.predict_bottlenecks(horizon_minutes=horizon_minutes)

            # Registrar métricas de bottlenecks
            if self.metrics and bottlenecks:
                high_severity = sum(1 for b in bottlenecks if b.get("severity") == "HIGH")
                medium_severity = sum(1 for b in bottlenecks if b.get("severity") == "MEDIUM")

                self.metrics.record_bottlenecks_detected(
                    high_severity=high_severity, medium_severity=medium_severity
                )

            return bottlenecks

        except Exception as e:
            self.logger.error(
                "bottleneck_prediction_error", horizon_minutes=horizon_minutes, error=str(e)
            )
            return []

    async def invalidate_cache(self, horizon_minutes: int) -> None:
        """
        Invalida cache para horizonte específico.

        Args:
            horizon_minutes: Horizonte para invalidar
        """
        if not self.redis_client:
            return

        cache_key = f"load_forecast:{horizon_minutes}m"

        try:
            from src.clients.redis_client import redis_delete_safe

            await redis_delete_safe(cache_key)
            self.logger.debug("cache_invalidated", horizon_minutes=horizon_minutes)
        except Exception as e:
            self.logger.warning("cache_invalidation_error", error=str(e))

    async def invalidate_all_cache(self) -> None:
        """
        Invalida todo o cache de forecasts.
        """
        if not self.redis_client:
            return

        try:
            from src.clients.redis_client import redis_delete_safe

            for horizon in self.forecast_horizons:
                cache_key = f"load_forecast:{horizon}m"
                await redis_delete_safe(cache_key)

            self.logger.debug("all_cache_invalidated")
        except Exception as e:
            self.logger.warning("cache_invalidation_error", error=str(e))


class LoadPredictorFactory:
    """
    Factory para criação e inicialização do LoadPredictor.

    Implementa:
    - Lazy initialization do LoadPredictor centralizado
    - Fallback automático quando neural_hive_ml indisponível
    - Inicialização assíncrona com retry
    - Configuração baseada em settings do orchestrator
    """

    def __init__(
        self,
        config: OrchestratorSettings,
        redis_client,
        mongodb_client,
        metrics: OrchestratorMetrics,
    ):
        """
        Inicializa a factory.

        Args:
            config: Configurações do orchestrator
            redis_client: Cliente Redis para cache
            mongodb_client: Cliente MongoDB para dados históricos
            metrics: Métricas Prometheus
        """
        self.config = config
        self.redis_client = redis_client
        self.mongodb_client = mongodb_client
        self.metrics = metrics
        self.logger = logger.bind(component="load_predictor_factory")

        # Verifica se LoadPredictor está habilitado
        self.enabled = getattr(config, "load_predictor_enabled", False)

        # Verifica se neural_hive_ml está disponível
        self.ml_available = ML_AVAILABLE and self.enabled

        # Predictor instance (lazy loaded)
        self._predictor: Optional[CentralLoadPredictor] = None
        self._wrapper: Optional[LoadPredictorWrapper] = None

    async def create_load_predictor(self) -> LoadPredictorWrapper:
        """
        Cria e retorna wrapper do LoadPredictor.

        Se neural_hive_ml não está disponível ou está desabilitado,
        retorna wrapper desabilitado.

        Returns:
            LoadPredictorWrapper (pode estar desabilitado)
        """
        if self._wrapper is not None:
            return self._wrapper

        # Se desabilitado ou ML não disponível, retornar wrapper desabilitado
        if not self.enabled or not self.ml_available:
            self.logger.info(
                "load_predictor_disabled", enabled=self.enabled, ml_available=self.ml_available
            )

            self._wrapper = LoadPredictorWrapper(
                predictor=None,
                config=self.config,
                redis_client=self.redis_client,
                metrics=self.metrics,
                enabled=False,
            )

            return self._wrapper

        # Criar predictor centralizado
        try:
            predictor_config = self._build_predictor_config()

            self._predictor = CentralLoadPredictor(
                config=predictor_config,
                model_registry=None,  # Opcional: MLflow client
                metrics=self._wrap_metrics(),
                redis_client=self.redis_client,
                data_source=self.mongodb_client,
            )

            self._wrapper = LoadPredictorWrapper(
                predictor=self._predictor,
                config=self.config,
                redis_client=self.redis_client,
                metrics=self.metrics,
                enabled=True,
            )

            self.logger.info(
                "load_predictor_created",
                enabled=True,
                forecast_horizons=self.config.load_predictor_forecast_horizons,
            )

            return self._wrapper

        except Exception as e:
            self.logger.error(
                "load_predictor_creation_failed", error=str(e), error_type=type(e).__name__
            )

            # Fallback: retornar wrapper desabilitado
            self._wrapper = LoadPredictorWrapper(
                predictor=None,
                config=self.config,
                redis_client=self.redis_client,
                metrics=self.metrics,
                enabled=False,
            )

            return self._wrapper

    async def initialize(self) -> None:
        """
        Inicializa o LoadPredictor centralizado.

        Deve ser chamado após create_load_predictor() para carregar modelos.
        """
        if not self.ml_available or not self._predictor:
            self.logger.debug("load_predictor_skip_init", ml_available=self.ml_available)
            return

        try:
            await self._predictor.initialize()
            self.logger.info("load_predictor_initialized")
        except Exception as e:
            self.logger.error(
                "load_predictor_init_failed", error=str(e), error_type=type(e).__name__
            )
            raise

    def _build_predictor_config(self) -> dict[str, Any]:
        """
        Constrói configuração para o LoadPredictor centralizado.

        Returns:
            Dict com configurações do LoadPredictor
        """
        return {
            "forecast_horizons": getattr(
                self.config, "load_predictor_forecast_horizons", [60, 360, 1440]
            ),
            "seasonality_mode": "additive",
            "cache_ttl_seconds": getattr(self.config, "load_predictor_cache_ttl_seconds", 300),
            "use_synthetic_data": getattr(self.config, "environment", "development")
            in ["development", "test", "local"],
        }

    def _wrap_metrics(self) -> Any:
        """
        Cria wrapper de métricas compatível com LoadPredictor.

        O LoadPredictor centralizado espera um objeto com métodos específicos
        para registrar métricas. Este wrapper adapta OrchestratorMetrics.

        Returns:
            Objeto com interface compatível
        """

        class MetricsAdapter:
            """Adapter para métricas do LoadPredictor."""

            def __init__(self, metrics: OrchestratorMetrics):
                self.metrics = metrics

            async def record_forecast_cache_hit(self, hit: bool) -> None:
                """Registra cache hit/miss."""
                if self.metrics:
                    self.metrics.record_load_forecast_cache_hit(hit=hit)

            async def record_load_forecast(
                self, horizon_minutes: int, status: str, latency: float, mape: float = 0.0
            ) -> None:
                """Registra forecast."""
                if self.metrics:
                    if status == "success":
                        self.metrics.record_load_forecast_latency(
                            latency_seconds=latency, horizon_minutes=horizon_minutes
                        )
                        if mape > 0:
                            self.metrics.record_load_forecast_mape(mape=mape)
                    else:
                        self.metrics.record_load_forecast_error(error_type=status)

            async def record_bottleneck_prediction(
                self, bottleneck_type: str, severity: str, timestamp: str
            ) -> None:
                """Registra predição de bottleneck."""
                # Métricas de bottlenecks são registradas pelo wrapper

        return MetricsAdapter(self.metrics)
