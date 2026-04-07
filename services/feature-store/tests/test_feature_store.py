"""
Testes para Feature Store Service

Testa operações CRUD, cache hit/miss e integração com MongoDB/Redis.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient

# Import lineage models FIRST to resolve forward references
from src.models.lineage import (
    SourceType,
    TransformationType,
    LineageMetadata,
    FeatureLineage,
    LineageTree,
    LineageImpact,
    LineageIntegrityReport,
)

# Then import feature models
from src.models.feature import (
    FeatureVector,
    MetadataFeatures,
    FeatureComputationRequest,
    ComputationStatus,
)

from src.services.feature_store import FeatureStoreService
from src.services.cache_service import RedisCacheService
from src.services.computation import FeatureComputationPipeline


@pytest.fixture
def mock_settings():
    """Mock das configurações"""
    settings = MagicMock()
    settings.mongodb_database = "test_db"
    settings.mongodb_features_collection = "test_features"
    settings.redis_cache_ttl_seconds = 3600
    settings.computation_timeout_seconds = 30
    return settings


@pytest.fixture
def mock_mongo_client():
    """Mock do cliente MongoDB"""
    client = MagicMock()
    client.__getitem__ = MagicMock(return_value=MagicMock())
    return client


@pytest.fixture
def mock_cache_service():
    """Mock do serviço de cache"""
    cache = MagicMock(spec=RedisCacheService)
    cache.is_available = MagicMock(return_value=True)
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock(return_value=True)
    cache.delete = AsyncMock(return_value=True)
    cache.get_stats = AsyncMock(return_value={"keys_count": 10})
    return cache


@pytest.fixture
def sample_feature_vector():
    """FeatureVector de exemplo"""
    return FeatureVector(
        plan_id="test-plan-123",
        metadata=MetadataFeatures(
            num_tasks=5,
            priority_score=0.7,
            total_duration_ms=5000.0,
            avg_duration_ms=1000.0,
            risk_score=0.3,
            complexity_score=0.6,
        ),
        computation_status=ComputationStatus.COMPLETED,
    )


@pytest.fixture
def sample_cognitive_plan():
    """Plano cognitivo de exemplo"""
    return {
        "plan_id": "test-plan-123",
        "priority": "high",
        "risk_score": 0.3,
        "tasks": [
            {
                "task_id": "task-1",
                "type": "query",
                "estimated_duration_ms": 1000,
                "is_destructive": False,
                "complexity_factor": 0.5,
            },
            {
                "task_id": "task-2",
                "type": "transform",
                "estimated_duration_ms": 2000,
                "is_destructive": False,
                "complexity_factor": 0.7,
            },
        ],
        "dependency_graph": {
            "edges": [{"source": "task-1", "target": "task-2"}],
            "critical_path_length": 2,
        },
    }


@pytest.fixture
def feature_store_service(mock_settings, mock_mongo_client, mock_cache_service):
    """Instância do FeatureStoreService para testes"""
    # Mock database e collection
    mock_db = MagicMock()
    mock_collection = MagicMock()
    mock_collection.find_one = AsyncMock(return_value=None)
    mock_collection.update_one = AsyncMock(
        return_value=MagicMock(upserted_id=123, modified_count=1)
    )
    mock_collection.delete_one = AsyncMock(return_value=MagicMock(deleted_count=1))
    mock_collection.count_documents = AsyncMock(return_value=0)
    mock_collection.find = MagicMock()
    mock_collection.create_index = AsyncMock()

    mock_db.__getitem__ = MagicMock(return_value=mock_collection)
    mock_mongo_client.__getitem__ = MagicMock(return_value=mock_db)

    service = FeatureStoreService(
        settings=mock_settings, mongodb_client=mock_mongo_client, cache_service=mock_cache_service
    )

    # Sobrescreve collection para usar o mock
    service.db = mock_db
    service.collection = mock_collection

    return service


class TestFeatureStoreServiceInit:
    """Testes para inicialização do FeatureStoreService"""

    def test_init_with_mocks(self, mock_settings, mock_mongo_client, mock_cache_service):
        """Testa inicialização com mocks"""
        service = FeatureStoreService(
            settings=mock_settings,
            mongodb_client=mock_mongo_client,
            cache_service=mock_cache_service,
        )

        assert service.settings == mock_settings
        assert service.mongodb_client == mock_mongo_client
        assert service.cache_service == mock_cache_service
        assert isinstance(service.computation_pipeline, FeatureComputationPipeline)
        assert service._computation_count == 0


class TestGetFeatures:
    """Testes para get_features"""

    @pytest.mark.asyncio
    async def test_get_features_from_cache_hit(
        self, feature_store_service, mock_cache_service, sample_feature_vector
    ):
        """Testa cache hit - busca do Redis"""
        cached_data = sample_feature_vector.model_dump(mode="json")
        mock_cache_service.get.return_value = cached_data

        result = await feature_store_service.get_features("test-plan-123")

        assert result is not None
        assert result.plan_id == "test-plan-123"
        assert result.cache_hit is True
        mock_cache_service.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_features_cache_miss_mongodb_hit(
        self, feature_store_service, mock_cache_service, sample_feature_vector
    ):
        """Testa cache miss mas MongoDB hit"""
        mock_cache_service.get.return_value = None

        # Mock MongoDB response
        mongo_data = sample_feature_vector.model_dump(mode="json")
        feature_store_service.collection.find_one = AsyncMock(return_value=mongo_data)

        result = await feature_store_service.get_features("test-plan-123")

        assert result is not None
        assert result.plan_id == "test-plan-123"
        mock_cache_service.set.assert_called_once()  # Salvo no cache após buscar do MongoDB

    @pytest.mark.asyncio
    async def test_get_features_not_found(self, feature_store_service, mock_cache_service):
        """Testa quando features não existem"""
        mock_cache_service.get.return_value = None
        feature_store_service.collection.find_one = AsyncMock(return_value=None)

        result = await feature_store_service.get_features("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_features_skip_cache(self, feature_store_service, mock_cache_service):
        """Testa skip_cache=True"""
        feature_store_service.collection.find_one = AsyncMock(return_value=None)

        await feature_store_service.get_features("test-plan-123", use_cache=False)

        # Não deve chamar cache
        mock_cache_service.get.assert_not_called()


class TestSaveFeatures:
    """Testes para save_features"""

    @pytest.mark.asyncio
    async def test_save_features_success(self, feature_store_service, sample_feature_vector):
        """Testa salvar features com sucesso"""
        feature_store_service.collection.update_one = AsyncMock(
            return_value=MagicMock(upserted_id=123)
        )

        result = await feature_store_service.save_features(sample_feature_vector)

        assert result is True
        feature_store_service.collection.update_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_features_with_cache_update(
        self, feature_store_service, sample_feature_vector, mock_cache_service
    ):
        """Testa salvar features atualizando cache"""
        feature_store_service.collection.update_one = AsyncMock(
            return_value=MagicMock(upserted_id=123)
        )

        result = await feature_store_service.save_features(sample_feature_vector, update_cache=True)

        assert result is True
        mock_cache_service.set.assert_called_once()


class TestComputeAndSave:
    """Testes para compute_and_save"""

    @pytest.mark.asyncio
    async def test_compute_and_save_new_features(
        self, feature_store_service, sample_cognitive_plan
    ):
        """Testa computar e salvar novas features"""
        # Mock: não existe, precisa computar
        mock_cache_service = feature_store_service.cache_service
        mock_cache_service.get.return_value = None
        feature_store_service.collection.find_one = AsyncMock(return_value=None)

        # Mock save
        feature_store_service.collection.update_one = AsyncMock(
            return_value=MagicMock(upserted_id=123)
        )

        request = FeatureComputationRequest(
            plan_id="test-plan-123", cognitive_plan=sample_cognitive_plan
        )

        result = await feature_store_service.compute_and_save(request)

        assert result is not None
        assert result.plan_id == "test-plan-123"
        assert result.computation_status == ComputationStatus.COMPLETED
        assert result.metadata.num_tasks == 2  # 2 tarefas no plano de exemplo

    @pytest.mark.asyncio
    async def test_compute_and_skip_existing(
        self, feature_store_service, sample_feature_vector, sample_cognitive_plan
    ):
        """Testa pular features existentes (force_recompute=False)"""
        # Mock: já existe
        feature_store_service.cache_service.get.return_value = sample_feature_vector.model_dump(
            mode="json"
        )

        request = FeatureComputationRequest(
            plan_id="test-plan-123", cognitive_plan=sample_cognitive_plan, force_recompute=False
        )

        result = await feature_store_service.compute_and_save(request)

        assert result.plan_id == "test-plan-123"
        # Não deve computar novamente

    @pytest.mark.asyncio
    async def test_compute_with_force_recompute(self, feature_store_service, sample_cognitive_plan):
        """Testa forçar recomputação"""
        feature_store_service.cache_service.get.return_value = None
        feature_store_service.collection.find_one = AsyncMock(return_value=None)
        feature_store_service.collection.update_one = AsyncMock(
            return_value=MagicMock(upserted_id=123)
        )

        request = FeatureComputationRequest(
            plan_id="test-plan-123", cognitive_plan=sample_cognitive_plan, force_recompute=True
        )

        result = await feature_store_service.compute_and_save(request)

        assert result is not None


class TestDeleteFeatures:
    """Testes para delete_features"""

    @pytest.mark.asyncio
    async def test_delete_features_success(self, feature_store_service, mock_cache_service):
        """Testa deletar features com sucesso"""
        feature_store_service.collection.delete_one = AsyncMock(
            return_value=MagicMock(deleted_count=1)
        )
        mock_cache_service.delete.return_value = True

        result = await feature_store_service.delete_features("test-plan-123")

        assert result is True
        feature_store_service.collection.delete_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_features_not_found(self, feature_store_service, mock_cache_service):
        """Testa deletar features inexistentes"""
        feature_store_service.collection.delete_one = AsyncMock(
            return_value=MagicMock(deleted_count=0)
        )
        mock_cache_service.delete.return_value = False

        result = await feature_store_service.delete_features("nonexistent")

        assert result is False


class TestListFeatures:
    """Testes para list_features"""

    @pytest.mark.asyncio
    async def test_list_features_default(self, feature_store_service):
        """Testa listagem com parâmetros padrão"""
        # Mock cursor
        mock_cursor = MagicMock()
        mock_cursor.sort = MagicMock(return_value=mock_cursor)
        mock_cursor.skip = MagicMock(return_value=mock_cursor)
        mock_cursor.limit = MagicMock(return_value=AsyncMock(return_value=[]))
        feature_store_service.collection.find = MagicMock(return_value=mock_cursor)

        result = await feature_store_service.list_features(limit=50, offset=0)

        assert result.success is True
        assert result.count == 0


class TestGetMetrics:
    """Testes para get_metrics"""

    @pytest.mark.asyncio
    async def test_get_metrics(self, feature_store_service, mock_cache_service):
        """Testa obter métricas"""
        feature_store_service.collection.count_documents = AsyncMock(return_value=100)
        mock_cache_service.get_stats = AsyncMock(return_value={"keys_count": 80})

        # Incrementa métricas
        feature_store_service._cache_hits = 80
        feature_store_service._cache_misses = 20
        feature_store_service._computation_count = 50

        metrics = await feature_store_service.get_metrics()

        assert metrics["total_features"] == 100
        assert metrics["cached_features"] == 80
        assert metrics["computation_count"] == 50
        assert metrics["cache_hits"] == 80
        assert metrics["cache_misses"] == 20
        assert metrics["cache_hit_rate"] == 0.8


class TestGetFeaturesByPlanIds:
    """Testes para get_features_by_plan_ids"""

    @pytest.mark.asyncio
    async def test_get_features_by_multiple_plan_ids(
        self, feature_store_service, sample_feature_vector
    ):
        """Testa buscar features por múltiplos IDs"""

        # Create async iterator function
        async def async_cursor():
            docs = [
                {
                    **sample_feature_vector.model_dump(mode="json"),
                    "plan_id": "plan-1",
                    "_id": "id1",
                },
                {
                    **sample_feature_vector.model_dump(mode="json"),
                    "plan_id": "plan-2",
                    "_id": "id2",
                },
            ]
            for doc in docs:
                yield doc

        # Mock cursor properly
        class AsyncCursor:
            def __init__(self):
                self._iter = async_cursor()

            def __aiter__(self):
                return self._aiter_gen()

            async def _aiter_gen(self):
                async for item in self._iter:
                    yield item

        feature_store_service.collection.find = MagicMock(return_value=AsyncCursor())

        result = await feature_store_service.get_features_by_plan_ids(["plan-1", "plan-2"])

        assert len(result) == 2
        assert "plan-1" in result
        assert "plan-2" in result


class TestCacheIntegration:
    """Testes para integração com cache"""

    @pytest.mark.asyncio
    async def test_cache_hit_increments_counter(
        self, feature_store_service, mock_cache_service, sample_feature_vector
    ):
        """Testa que cache hit incrementa contador"""
        mock_cache_service.get.return_value = sample_feature_vector.model_dump(mode="json")

        await feature_store_service.get_features("test-plan-123")

        assert feature_store_service._cache_hits == 1

    @pytest.mark.asyncio
    async def test_cache_miss_increments_counter(self, feature_store_service, mock_cache_service):
        """Testa que cache miss incrementa contador"""
        mock_cache_service.get.return_value = None
        feature_store_service.collection.find_one = AsyncMock(return_value=None)

        await feature_store_service.get_features("test-plan-123")

        assert feature_store_service._cache_misses == 1
