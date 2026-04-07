"""
Testes unitários para LoadPredictorFactory.

Valida criação e inicialização do LoadPredictor centralizado.
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timedelta

from src.ml.load_predictor_factory import LoadPredictorFactory, LoadPredictorWrapper
from src.config.settings import OrchestratorSettings
from src.observability.metrics import OrchestratorMetrics


# Mock do LoadPredictor centralizado para testes
class MockLoadPredictor:
    """Mock do LoadPredictor de neural_hive_ml."""

    def __init__(
        self, config, model_registry=None, metrics=None, redis_client=None, data_source=None
    ):
        self.config = config
        self.model_registry = model_registry
        self.metrics = metrics
        self.redis_client = redis_client
        self.data_source = data_source
        self.initialized = False

    async def initialize(self):
        """Mock de inicialização."""
        self.initialized = True

    async def predict_load(self, horizon_minutes, include_confidence=True):
        """Mock de predição de carga."""
        return {
            "forecast": [0.5, 0.6, 0.7],
            "timestamps": ["2026-04-05T10:00:00", "2026-04-05T10:01:00", "2026-04-05T10:02:00"],
            "model_type": "prophet",
            "horizon_minutes": horizon_minutes,
            "mape": 5.2,
        }

    async def predict_bottlenecks(self, horizon_minutes=360):
        """Mock de predição de bottlenecks."""
        return []


@pytest.fixture
def mock_config():
    """Configuração mockada com LoadPredictor habilitado."""
    config = Mock(spec=OrchestratorSettings)
    config.load_predictor_enabled = True
    config.load_predictor_forecast_horizons = [60, 360, 1440]
    config.load_predictor_bottleneck_threshold = 0.8
    config.load_predictor_cache_ttl_seconds = 300
    config.mlflow_tracking_uri = "https://mlflow.mlflow.svc.cluster.local:5000"
    config.mlflow_tls_verify = True
    config.environment = "development"
    return config


@pytest.fixture
def mock_redis():
    """Cliente Redis mockado."""
    mock = AsyncMock()
    mock.get = AsyncMock(return_value=None)
    mock.setex = AsyncMock()
    mock.delete = AsyncMock()
    return mock


@pytest.fixture
def mock_metrics():
    """Métricas mockadas."""
    return Mock(spec=OrchestratorMetrics)


@pytest.fixture
def mock_mongodb():
    """Cliente MongoDB mockado."""
    mock = AsyncMock()
    mock.db = {}
    return mock


class TestLoadPredictorFactory:
    """Testes de criação do LoadPredictor."""

    @pytest.mark.asyncio
    async def test_create_load_predictor_with_ml_available(
        self, mock_config, mock_redis, mock_metrics, mock_mongodb
    ):
        """Testa criação do LoadPredictor quando neural_hive_ml está disponível."""
        with patch("src.ml.load_predictor_factory.CentralLoadPredictor", MockLoadPredictor):
            with patch("src.ml.load_predictor_factory.ML_AVAILABLE", True):
                factory = LoadPredictorFactory(
                    config=mock_config,
                    redis_client=mock_redis,
                    mongodb_client=mock_mongodb,
                    metrics=mock_metrics,
                )

                predictor = await factory.create_load_predictor()

                assert predictor is not None
                assert isinstance(predictor, LoadPredictorWrapper)
                assert predictor.enabled is True

    @pytest.mark.asyncio
    async def test_create_load_predictor_when_disabled(
        self, mock_config, mock_redis, mock_metrics, mock_mongodb
    ):
        """Testa criação desabilitada por configuração."""
        mock_config.load_predictor_enabled = False

        factory = LoadPredictorFactory(
            config=mock_config,
            redis_client=mock_redis,
            mongodb_client=mock_mongodb,
            metrics=mock_metrics,
        )

        predictor = await factory.create_load_predictor()

        assert predictor is not None
        assert predictor.enabled is False

    @pytest.mark.asyncio
    async def test_create_load_predictor_ml_not_available(
        self, mock_config, mock_redis, mock_metrics, mock_mongodb
    ):
        """Testa fallback quando neural_hive_ml não está disponível."""
        with patch("src.ml.load_predictor_factory.ML_AVAILABLE", False):
            factory = LoadPredictorFactory(
                config=mock_config,
                redis_client=mock_redis,
                mongodb_client=mock_mongodb,
                metrics=mock_metrics,
            )

            predictor = await factory.create_load_predictor()

            # Deve retornar wrapper desabilitado
            assert predictor is not None
            assert predictor.enabled is False

    @pytest.mark.asyncio
    async def test_initialize_load_predictor_success(
        self, mock_config, mock_redis, mock_metrics, mock_mongodb
    ):
        """Testa inicialização bem-sucedida do LoadPredictor."""
        with patch("src.ml.load_predictor_factory.CentralLoadPredictor", MockLoadPredictor):
            with patch("src.ml.load_predictor_factory.ML_AVAILABLE", True):
                factory = LoadPredictorFactory(
                    config=mock_config,
                    redis_client=mock_redis,
                    mongodb_client=mock_mongodb,
                    metrics=mock_metrics,
                )

                # Criar predictor primeiro
                await factory.create_load_predictor()
                # Depois inicializar
                await factory.initialize()

                # Verificar que predictor foi inicializado
                assert factory._predictor is not None
                assert factory._predictor.initialized is True


class TestLoadPredictorWrapper:
    """Testes do wrapper com cache Redis."""

    @pytest.mark.asyncio
    async def test_predict_load_cache_hit(
        self, mock_config, mock_redis, mock_metrics, mock_mongodb
    ):
        """Testa predição de carga com cache hit."""
        with patch("src.ml.load_predictor_factory.CentralLoadPredictor", MockLoadPredictor):
            with patch("src.ml.load_predictor_factory.ML_AVAILABLE", True):
                mock_cached_data = '{"forecast": [0.5, 0.6, 0.7], "timestamps": ["2026-04-05T10:00:00"], "model_type": "prophet"}'
                mock_redis.get.return_value = mock_cached_data

                factory = LoadPredictorFactory(
                    config=mock_config,
                    redis_client=mock_redis,
                    mongodb_client=mock_mongodb,
                    metrics=mock_metrics,
                )

                wrapper = await factory.create_load_predictor()
                result = await wrapper.predict_load(horizon_minutes=60)

                # Cache hit - deve retornar dados do cache
                assert result["forecast"] == [0.5, 0.6, 0.7]
                mock_redis.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_predict_load_cache_miss(
        self, mock_config, mock_redis, mock_metrics, mock_mongodb
    ):
        """Testa predição de carga com cache miss."""
        with patch("src.ml.load_predictor_factory.CentralLoadPredictor", MockLoadPredictor):
            with patch("src.ml.load_predictor_factory.ML_AVAILABLE", True):
                mock_redis.get.return_value = None  # Cache miss

                factory = LoadPredictorFactory(
                    config=mock_config,
                    redis_client=mock_redis,
                    mongodb_client=mock_mongodb,
                    metrics=mock_metrics,
                )

                wrapper = await factory.create_load_predictor()
                result = await wrapper.predict_load(horizon_minutes=60)

                # Deve retornar forecast do predictor
                assert result["forecast"] == [0.5, 0.6, 0.7]
                # Deve salvar no cache
                mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_predict_load_when_disabled(
        self, mock_config, mock_redis, mock_metrics, mock_mongodb
    ):
        """Testa predição quando wrapper está desabilitado."""
        mock_config.load_predictor_enabled = False

        factory = LoadPredictorFactory(
            config=mock_config,
            redis_client=mock_redis,
            mongodb_client=mock_mongodb,
            metrics=mock_metrics,
        )

        wrapper = await factory.create_load_predictor()
        result = await wrapper.predict_load(horizon_minutes=60)

        # Deve retornar forecast vazio
        assert result["forecast"] == []
        assert "disabled" in result.get("status", "")

    @pytest.mark.asyncio
    async def test_predict_bottlenecks_success(
        self, mock_config, mock_redis, mock_metrics, mock_mongodb
    ):
        """Testa predição de bottlenecks com sucesso."""
        with patch("src.ml.load_predictor_factory.CentralLoadPredictor", MockLoadPredictor):
            with patch("src.ml.load_predictor_factory.ML_AVAILABLE", True):
                factory = LoadPredictorFactory(
                    config=mock_config,
                    redis_client=mock_redis,
                    mongodb_client=mock_mongodb,
                    metrics=mock_metrics,
                )

                wrapper = await factory.create_load_predictor()
                result = await wrapper.predict_bottlenecks(horizon_minutes=360)

                # MockLoadPredictor retorna lista vazia
                assert result == []

    @pytest.mark.asyncio
    async def test_predict_load_error_handling(
        self, mock_config, mock_redis, mock_metrics, mock_mongodb
    ):
        """Testa tratamento de erros na predição."""

        class BrokenLoadPredictor:
            """LoadPredictor que sempre falha."""

            def __init__(self, *args, **kwargs):
                pass

            async def initialize(self):
                pass

            async def predict_load(self, *args, **kwargs):
                raise Exception("Prediction error")

            async def predict_bottlenecks(self, *args, **kwargs):
                return []

        with patch("src.ml.load_predictor_factory.CentralLoadPredictor", BrokenLoadPredictor):
            with patch("src.ml.load_predictor_factory.ML_AVAILABLE", True):
                mock_redis.get.return_value = None  # Cache miss

                factory = LoadPredictorFactory(
                    config=mock_config,
                    redis_client=mock_redis,
                    mongodb_client=mock_mongodb,
                    metrics=mock_metrics,
                )

                wrapper = await factory.create_load_predictor()
                result = await wrapper.predict_load(horizon_minutes=60)

                # Deve retornar resposta de erro gracefully
                assert "error" in result or result["forecast"] == []

    @pytest.mark.asyncio
    async def test_predict_load_records_metrics(
        self, mock_config, mock_redis, mock_metrics, mock_mongodb
    ):
        """Testa registro de métricas Prometheus."""
        with patch("src.ml.load_predictor_factory.CentralLoadPredictor", MockLoadPredictor):
            with patch("src.ml.load_predictor_factory.ML_AVAILABLE", True):
                mock_redis.get.return_value = None  # Cache miss

                factory = LoadPredictorFactory(
                    config=mock_config,
                    redis_client=mock_redis,
                    mongodb_client=mock_mongodb,
                    metrics=mock_metrics,
                )

                wrapper = await factory.create_load_predictor()
                await wrapper.predict_load(horizon_minutes=60)

                # Verificar registro de métricas
                mock_metrics.record_load_forecast_latency.assert_called_once()
                mock_metrics.record_load_forecast_mape.assert_called_once_with(5.2)

    @pytest.mark.asyncio
    async def test_predict_bottlenecks_records_metrics(
        self, mock_config, mock_redis, mock_metrics, mock_mongodb
    ):
        """Testa registro de métricas de bottlenecks."""

        class LoadPredictorWithBottlenecks:
            """LoadPredictor que retorna bottlenecks."""

            def __init__(self, *args, **kwargs):
                pass

            async def initialize(self):
                pass

            async def predict_load(self, *args, **kwargs):
                return {"forecast": [0.5]}

            async def predict_bottlenecks(self, *args, **kwargs):
                return [
                    {"severity": "HIGH", "predicted_load": 0.85},
                    {"severity": "MEDIUM", "predicted_load": 0.75},
                ]

        with patch(
            "src.ml.load_predictor_factory.CentralLoadPredictor", LoadPredictorWithBottlenecks
        ):
            with patch("src.ml.load_predictor_factory.ML_AVAILABLE", True):
                factory = LoadPredictorFactory(
                    config=mock_config,
                    redis_client=mock_redis,
                    mongodb_client=mock_mongodb,
                    metrics=mock_metrics,
                )

                wrapper = await factory.create_load_predictor()
                await wrapper.predict_bottlenecks(horizon_minutes=360)

                # Verificar registro de métricas
                mock_metrics.record_bottlenecks_detected.assert_called_once_with(
                    high_severity=1, medium_severity=1
                )


class TestLoadPredictorWrapperCache:
    """Testes específicos de cache do wrapper."""

    @pytest.mark.asyncio
    async def test_cache_key_format(self, mock_config, mock_redis, mock_metrics, mock_mongodb):
        """Testa formato da chave de cache."""
        with patch("src.ml.load_predictor_factory.ML_AVAILABLE", True):
            mock_response = {
                "forecast": [0.5, 0.6],
                "timestamps": ["2026-04-05T10:00:00", "2026-04-05T10:01:00"],
                "model_type": "prophet",
                "horizon_minutes": 60,
            }

            mock_load_predictor = AsyncMock()
            mock_load_predictor.predict_load = AsyncMock(return_value=mock_response)
            mock_load_predictor.predict_bottlenecks = AsyncMock(return_value=[])

            with patch(
                "src.ml.load_predictor_factory.LoadPredictor", return_value=mock_load_predictor
            ):
                mock_redis.get.return_value = None  # Cache miss

                factory = LoadPredictorFactory(
                    config=mock_config,
                    redis_client=mock_redis,
                    mongodb_client=mock_mongodb,
                    metrics=mock_metrics,
                )

                wrapper = await factory.create_load_predictor()
                await wrapper.predict_load(horizon_minutes=60)

                # Verificar formato da chave
                call_args = mock_redis.setex.call_args
                cache_key = call_args[0][0]
                assert cache_key == "load_forecast:60m"
                assert call_args[0][1] == 300  # TTL

    @pytest.mark.asyncio
    async def test_cache_invalidation(self, mock_config, mock_redis, mock_metrics, mock_mongodb):
        """Testa invalidação de cache."""
        with patch("src.ml.load_predictor_factory.ML_AVAILABLE", True):
            mock_load_predictor = AsyncMock()
            mock_load_predictor.predict_bottlenecks = AsyncMock(return_value=[])

            with patch(
                "src.ml.load_predictor_factory.LoadPredictor", return_value=mock_load_predictor
            ):
                factory = LoadPredictorFactory(
                    config=mock_config,
                    redis_client=mock_redis,
                    mongodb_client=mock_mongodb,
                    metrics=mock_metrics,
                )

                wrapper = await factory.create_load_predictor()
                await wrapper.invalidate_cache(horizon_minutes=60)

                # Deve deletar a chave específica
                mock_redis.delete.assert_called_once_with("load_forecast:60m")

    @pytest.mark.asyncio
    async def test_cache_invalidation_all(
        self, mock_config, mock_redis, mock_metrics, mock_mongodb
    ):
        """Testa invalidação de todo o cache."""
        with patch("src.ml.load_predictor_factory.ML_AVAILABLE", True):
            mock_load_predictor = AsyncMock()
            mock_load_predictor.predict_bottlenecks = AsyncMock(return_value=[])

            with patch(
                "src.ml.load_predictor_factory.LoadPredictor", return_value=mock_load_predictor
            ):
                factory = LoadPredictorFactory(
                    config=mock_config,
                    redis_client=mock_redis,
                    mongodb_client=mock_mongodb,
                    metrics=mock_metrics,
                )

                wrapper = await factory.create_load_predictor()
                await wrapper.invalidate_all_cache()

                # Deve deletar todas as chaves de horizontes configurados
                expected_calls = [
                    (("load_forecast:60m",),),
                    (("load_forecast:360m",),),
                    (("load_forecast:1440m",),),
                ]
                actual_calls = [call[0] for call in mock_redis.delete.call_args_list]

                for expected in expected_calls:
                    assert expected in actual_calls
