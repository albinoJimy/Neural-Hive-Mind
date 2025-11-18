"""
Testes unitários para LoadPredictor (preditor local de carga e queue time).
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta

from src.ml.load_predictor import LoadPredictor
from src.config.settings import OrchestratorSettings
from src.observability.metrics import OrchestratorMetrics


@pytest.fixture
def mock_config():
    """Configuração mockada."""
    config = Mock(spec=OrchestratorSettings)
    config.ml_local_load_window_minutes = 60
    config.ml_local_load_cache_ttl_seconds = 30
    config.mongodb_collection_tickets = 'execution_tickets'
    return config


@pytest.fixture
def mock_mongodb():
    """Cliente MongoDB mockado."""
    mock = AsyncMock()
    mock.db = {}
    return mock


@pytest.fixture
def mock_redis():
    """Cliente Redis mockado."""
    mock = AsyncMock()
    mock.get = AsyncMock(return_value=None)
    mock.setex = AsyncMock()
    return mock


@pytest.fixture
def mock_metrics():
    """Métricas mockadas."""
    return Mock(spec=OrchestratorMetrics)


@pytest.fixture
def load_predictor(mock_config, mock_mongodb, mock_redis, mock_metrics):
    """Instância de LoadPredictor para testes."""
    return LoadPredictor(
        config=mock_config,
        mongodb_client=mock_mongodb,
        redis_client=mock_redis,
        metrics=mock_metrics
    )


class TestLoadPredictorQueueTime:
    """Testes de predição de queue time."""

    @pytest.mark.asyncio
    async def test_predict_queue_time_with_cache_hit(
        self,
        load_predictor,
        mock_redis
    ):
        """Testa predição de queue time com cache hit."""
        # Configurar cache hit
        mock_redis.get.return_value = "1500.0"

        result = await load_predictor.predict_queue_time(worker_id="worker-1")

        assert result == 1500.0
        mock_redis.get.assert_called_once()
        # Não deve buscar do MongoDB quando há cache
        assert not hasattr(load_predictor.mongodb_client.db.get('execution_tickets', Mock()), 'find')

    @pytest.mark.asyncio
    async def test_predict_queue_time_no_historical_data(
        self,
        load_predictor,
        mock_mongodb,
        mock_redis,
        mock_config
    ):
        """Testa predição quando não há dados históricos."""
        # Configurar MongoDB para retornar lista vazia
        mock_collection = AsyncMock()
        mock_collection.find.return_value.sort.return_value.limit.return_value.to_list = AsyncMock(
            return_value=[]
        )
        mock_mongodb.db = {mock_config.mongodb_collection_tickets: mock_collection}

        result = await load_predictor.predict_queue_time(worker_id="worker-1")

        # Deve retornar default de 1 segundo
        assert result == 1000.0
        mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_predict_queue_time_with_historical_data(
        self,
        load_predictor,
        mock_mongodb,
        mock_redis,
        mock_config
    ):
        """Testa predição com dados históricos."""
        # Dados históricos simulados
        historical_tickets = [
            {'actual_duration_ms': 2000.0},
            {'actual_duration_ms': 3000.0},
            {'actual_duration_ms': 2500.0}
        ]

        mock_collection = AsyncMock()
        mock_collection.find.return_value.sort.return_value.limit.return_value.to_list = AsyncMock(
            return_value=historical_tickets
        )
        mock_collection.count_documents = AsyncMock(return_value=2)  # Queue depth = 2
        mock_mongodb.db = {mock_config.mongodb_collection_tickets: mock_collection}

        result = await load_predictor.predict_queue_time(worker_id="worker-1")

        # Queue depth (2) * avg duration (2500) = 5000
        assert result == 5000.0
        mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_predict_queue_time_without_mongodb(
        self,
        mock_config,
        mock_redis,
        mock_metrics
    ):
        """Testa predição quando MongoDB não está disponível."""
        predictor = LoadPredictor(
            config=mock_config,
            mongodb_client=None,  # MongoDB indisponível
            redis_client=mock_redis,
            metrics=mock_metrics
        )

        result = await predictor.predict_queue_time(worker_id="worker-1")

        # Deve retornar default sem tentar acessar MongoDB
        assert result == 1000.0

    @pytest.mark.asyncio
    async def test_predict_queue_time_error_handling(
        self,
        load_predictor,
        mock_mongodb,
        mock_config
    ):
        """Testa tratamento de erros durante predição."""
        # Simular erro no MongoDB
        mock_collection = Mock()
        mock_collection.find.side_effect = Exception("MongoDB error")
        mock_mongodb.db = {mock_config.mongodb_collection_tickets: mock_collection}

        result = await load_predictor.predict_queue_time(worker_id="worker-1")

        # Deve retornar fallback conservador
        assert result == 2000.0


class TestLoadPredictorWorkerLoad:
    """Testes de predição de carga de worker."""

    @pytest.mark.asyncio
    async def test_predict_worker_load_with_cache(
        self,
        load_predictor,
        mock_redis
    ):
        """Testa predição de carga com cache hit."""
        mock_redis.get.return_value = "0.6"

        result = await load_predictor.predict_worker_load(worker_id="worker-1")

        assert result == 0.6
        mock_redis.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_predict_worker_load_calculates_from_queue_depth(
        self,
        load_predictor,
        mock_mongodb,
        mock_config
    ):
        """Testa cálculo de carga baseado em queue depth."""
        # Simular queue depth de 5
        mock_collection = AsyncMock()
        mock_collection.count_documents = AsyncMock(return_value=5)
        mock_mongodb.db = {mock_config.mongodb_collection_tickets: mock_collection}

        result = await load_predictor.predict_worker_load(worker_id="worker-1")

        # 5 / 10 (capacidade) = 0.5
        assert result == 0.5

    @pytest.mark.asyncio
    async def test_predict_worker_load_caps_at_100_percent(
        self,
        load_predictor,
        mock_mongodb,
        mock_config
    ):
        """Testa que carga é limitada a 100%."""
        # Simular queue depth muito alta
        mock_collection = AsyncMock()
        mock_collection.count_documents = AsyncMock(return_value=50)
        mock_mongodb.db = {mock_config.mongodb_collection_tickets: mock_collection}

        result = await load_predictor.predict_worker_load(worker_id="worker-1")

        # Deve ser limitado a 1.0 (100%)
        assert result == 1.0

    @pytest.mark.asyncio
    async def test_predict_worker_load_without_mongodb(
        self,
        mock_config,
        mock_redis,
        mock_metrics
    ):
        """Testa predição de carga sem MongoDB."""
        predictor = LoadPredictor(
            config=mock_config,
            mongodb_client=None,
            redis_client=mock_redis,
            metrics=mock_metrics
        )

        result = await predictor.predict_worker_load(worker_id="worker-1")

        # Deve retornar default (carga média)
        assert result == 0.5


class TestLoadPredictorMetrics:
    """Testes de registro de métricas."""

    @pytest.mark.asyncio
    async def test_records_queue_prediction_metrics(
        self,
        load_predictor,
        mock_metrics,
        mock_mongodb,
        mock_config
    ):
        """Testa registro de métricas de predição de queue."""
        mock_collection = AsyncMock()
        mock_collection.find.return_value.sort.return_value.limit.return_value.to_list = AsyncMock(
            return_value=[]
        )
        mock_mongodb.db = {mock_config.mongodb_collection_tickets: mock_collection}

        await load_predictor.predict_queue_time(worker_id="worker-1")

        # Verificar chamadas de métricas
        mock_metrics.record_ml_prediction.assert_called_once()
        mock_metrics.record_predicted_queue_time.assert_called_once_with(
            predicted_ms=1000.0,
            source='local'
        )

    @pytest.mark.asyncio
    async def test_records_load_prediction_metrics(
        self,
        load_predictor,
        mock_metrics,
        mock_mongodb,
        mock_config
    ):
        """Testa registro de métricas de predição de carga."""
        mock_collection = AsyncMock()
        mock_collection.count_documents = AsyncMock(return_value=3)
        mock_mongodb.db = {mock_config.mongodb_collection_tickets: mock_collection}

        await load_predictor.predict_worker_load(worker_id="worker-1")

        # Verificar chamadas de métricas
        mock_metrics.record_ml_prediction.assert_called_once()
        mock_metrics.record_predicted_worker_load.assert_called_once_with(
            predicted_pct=0.3,
            source='local'
        )
