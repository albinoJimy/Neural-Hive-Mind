"""
Testes isolados para Cache-aside pattern no consensus-engine.

Gap P1: Cache-aside pattern para reduzir latência e carga no MongoDB.
Estes testes não dependem do conftest.py complexo.
"""

import os
import sys
from pathlib import Path
from enum import Enum
from unittest.mock import AsyncMock, MagicMock

import pytest

# Configurar ambiente de teste antes dos imports
os.environ["KAFKA_BOOTSTRAP_SERVERS"] = "localhost:9092"
os.environ["MONGODB_URI"] = "mongodb://localhost:27017/test"
os.environ["REDIS_CLUSTER_NODES"] = "localhost:6379"

# Adicionar src ao path
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))


# Mocks necessários
class UnifiedDomain(str, Enum):
    BUSINESS = "BUSINESS"
    TECHNICAL = "TECHNICAL"
    SECURITY = "SECURITY"


mock_domain = MagicMock()
mock_domain.UnifiedDomain = UnifiedDomain
sys.modules["neural_hive_domain"] = mock_domain

# Mock protobuf
sys.modules["analyst_agent_pb2"] = MagicMock()
sys.modules["analyst_agent_pb2_grpc"] = MagicMock()
sys.modules["specialist_pb2"] = MagicMock()
sys.modules["specialist_pb2_grpc"] = MagicMock()
sys.modules["queen_agent_pb2"] = MagicMock()
sys.modules["queen_agent_pb2_grpc"] = MagicMock()

# Mock observability
mock_obs = MagicMock()
mock_tracer = MagicMock()
mock_span = MagicMock()
mock_span.__enter__ = MagicMock(return_value=mock_span)
mock_span.__exit__ = MagicMock(return_value=False)
mock_tracer.start_as_current_span = MagicMock(return_value=mock_span)
mock_obs.get_tracer = MagicMock(return_value=mock_tracer)
sys.modules["neural_hive_observability"] = mock_obs


class TestCacheEntry:
    """Testes para CacheEntry"""

    def test_cache_entry_creation(self):
        """Testa criação de entrada de cache"""
        from src.clients.redis_client import CacheEntry

        data = {"decision_id": "test-123", "final_decision": "approve"}
        entry = CacheEntry(data=data, cached_at=1000.0, ttl=300)

        assert entry.data == data
        assert entry.cached_at == 1000.0
        assert entry.ttl == 300

    def test_cache_entry_not_expired(self):
        """Testa verificação de expiração (não expirado)"""
        from src.clients.redis_client import CacheEntry

        entry = CacheEntry(data={}, cached_at=1000.0, ttl=300)
        assert not entry.is_expired(current_time=1200.0)  # 200s depois

    def test_cache_entry_expired(self):
        """Testa verificação de expiração (expirado)"""
        from src.clients.redis_client import CacheEntry

        entry = CacheEntry(data={}, cached_at=1000.0, ttl=300)
        assert entry.is_expired(current_time=1400.0)  # 400s depois

    def test_cache_entry_serialization(self):
        """Testa serialização/desserialização de CacheEntry"""
        from src.clients.redis_client import CacheEntry

        data = {"test": "value"}
        entry = CacheEntry(data=data, cached_at=1000.0, ttl=300)

        # Serializar
        entry_dict = entry.to_dict()
        assert entry_dict["data"] == data

        # Desserializar
        restored = CacheEntry.from_dict(entry_dict)
        assert restored.data == data


class TestRedisClient:
    """Testes para RedisClient"""

    @pytest.fixture
    def mock_redis(self):
        """Redis client mockado"""
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock(return_value=True)
        redis.delete = AsyncMock(return_value=1)
        redis.scan_iter = AsyncMock(return_value=[])
        redis.info = AsyncMock(return_value={})
        return redis

    @pytest.fixture
    def config(self):
        """Configurações mockadas"""
        config = MagicMock()
        config.cache_ttl_plan_approval = 300
        config.cache_ttl_consensus_decision = 120
        config.cache_ttl_specialist_status = 30
        return config

    @pytest.fixture
    def redis_client(self, mock_redis, config):
        """Instância de RedisClient para testes"""
        from src.clients.redis_client import RedisClient

        return RedisClient(mock_redis, config)

    def test_initialization(self, redis_client, config):
        """Testa inicialização do RedisClient"""
        assert redis_client.is_enabled()
        assert redis_client.ttl_plan_approval == 300
        assert redis_client.ttl_consensus_decision == 120
        assert redis_client.ttl_specialist_status == 30

    def test_disable_enable_cache(self, redis_client):
        """Testa habilitar/desabilitar cache"""
        assert redis_client.is_enabled()

        redis_client.disable()
        assert not redis_client.is_enabled()

        redis_client.enable()
        assert redis_client.is_enabled()

    @pytest.mark.asyncio
    async def test_get_cache_miss_when_disabled(self, redis_client):
        """Testa que get retorna None quando cache desabilitado"""
        redis_client.disable()
        result = await redis_client.get("test_key")
        assert result is None

    @pytest.mark.asyncio
    async def test_build_keys(self, redis_client):
        """Testa construção de chaves de cache"""
        plan_key = redis_client.build_key_plan_approval("plan-123")
        assert plan_key == "cache:plan_approval:plan-123"

        decision_key = redis_client.build_key_consensus_decision("decision-456")
        assert decision_key == "cache:consensus_decision:decision-456"

        specialist_key = redis_client.build_key_specialist_status("business")
        assert specialist_key == "cache:specialist_status:business"


class TestCacheAsideService:
    """Testes para CacheAsideService"""

    @pytest.fixture
    def mock_redis_client(self):
        """RedisClient mockado"""
        from src.clients.redis_client import RedisClient

        client = MagicMock(spec=RedisClient)
        client.is_enabled = MagicMock(return_value=True)
        client.build_key_plan_approval = MagicMock(return_value="cache:plan_approval:test")
        client.build_key_consensus_decision = MagicMock(
            return_value="cache:consensus_decision:test"
        )
        client.build_key_specialist_status = MagicMock(
            return_value="cache:specialist_status:business"
        )
        client.get = AsyncMock(return_value=None)
        client.set = AsyncMock(return_value=True)
        client.delete = AsyncMock(return_value=True)
        client.ttl_plan_approval = 300
        client.ttl_consensus_decision = 120
        client.ttl_specialist_status = 30
        client.PREFIX_PLAN_APPROVAL = "cache:plan_approval"
        client.PREFIX_CONSENSUS_DECISION = "cache:consensus_decision"
        client.PREFIX_SPECIALIST_STATUS = "cache:specialist_status"
        return client

    @pytest.fixture
    def config(self):
        """Configurações mockadas"""
        return MagicMock(enable_cache=True)

    @pytest.fixture
    def cache_service(self, mock_redis_client, config):
        """Instância de CacheAsideService para testes"""
        from src.services.cache_service import CacheAsideService

        return CacheAsideService(mock_redis_client, config)

    @pytest.mark.asyncio
    async def test_get_plan_approval_cache_hit(self, cache_service, mock_redis_client):
        """Testa get_plan_approval com cache hit"""
        cached_data = {"plan_id": "test", "status": "approved"}
        mock_redis_client.get = AsyncMock(return_value=cached_data)

        db_fetcher = AsyncMock()
        result = await cache_service.get_plan_approval("test", db_fetcher)

        assert result == cached_data
        assert cache_service._hits == 1
        assert cache_service._misses == 0
        db_fetcher.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_get_plan_approval_cache_miss(self, cache_service, mock_redis_client):
        """Testa get_plan_approval com cache miss"""
        db_data = {"plan_id": "test", "status": "approved"}
        db_fetcher = AsyncMock(return_value=db_data)
        mock_redis_client.get = AsyncMock(return_value=None)

        result = await cache_service.get_plan_approval("test", db_fetcher)

        assert result == db_data
        assert cache_service._hits == 0
        assert cache_service._misses == 1
        db_fetcher.assert_awaited_once()
        mock_redis_client.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalidate_plan_approval(self, cache_service, mock_redis_client):
        """Testa invalidação de plan approval"""
        result = await cache_service.invalidate_plan_approval("test")

        assert result is True
        mock_redis_client.delete.assert_called_once_with("cache:plan_approval:test")

    def test_get_metrics(self, cache_service):
        """Testa obtenção de métricas"""
        cache_service._hits = 80
        cache_service._misses = 20
        cache_service._errors = 2

        metrics = cache_service.get_metrics()

        assert metrics["hits"] == 80
        assert metrics["misses"] == 20
        assert metrics["errors"] == 2
        assert metrics["total_requests"] == 100
        assert metrics["hit_rate"] == 0.8

    def test_reset_metrics(self, cache_service):
        """Testa reset de métricas"""
        cache_service._hits = 100
        cache_service._misses = 50

        cache_service.reset_metrics()

        assert cache_service._hits == 0
        assert cache_service._misses == 0
        assert cache_service._errors == 0


class TestMongoDBClientCacheIntegration:
    """Testes de integração MongoDB com cache-aside"""

    @pytest.fixture
    def mock_config(self):
        """Configurações mockadas"""
        config = MagicMock()
        config.mongodb_uri = "mongodb://localhost:27017"
        config.mongodb_database = "test_db"
        config.mongodb_consensus_collection = "consensus_decisions"
        config.enable_cache = True
        config.cache_ttl_plan_approval = 300
        config.cache_ttl_consensus_decision = 120
        config.cache_ttl_specialist_status = 30
        return config

    @pytest.fixture
    def mock_redis_client(self):
        """RedisClient mockado"""
        from src.services.cache_service import CacheAsideService

        client = MagicMock(spec=CacheAsideService)
        client.get_consensus_decision = AsyncMock(return_value=None)
        client.get_plan_approval = AsyncMock(return_value=None)
        client.invalidate_consensus_decision = AsyncMock(return_value=True)
        client.invalidate_plan_approval = AsyncMock(return_value=True)
        return client

    @pytest.fixture
    def mongodb_client(self, mock_config):
        """Instância de MongoDBClient para testes"""
        from src.clients.mongodb_client import MongoDBClient

        client = MongoDBClient(mock_config)
        # Mock motor client
        client.client = AsyncMock()
        client.db = AsyncMock()
        client.consensus_collection = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_get_decision_cache_hit(self, mongodb_client, mock_redis_client):
        """Testa get_decision com cache hit"""
        mongodb_client.set_cache_service(mock_redis_client)

        cached_data = {"decision_id": "test-123", "final_decision": "approve"}
        mock_redis_client.get_consensus_decision = AsyncMock(return_value=cached_data)

        result = await mongodb_client.get_decision("test-123")

        assert result == cached_data
        mock_redis_client.get_consensus_decision.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_decision_invalidates_cache(self, mongodb_client, mock_redis_client):
        """Testa que salvar decisão invalida caches relacionados"""
        from src.models.consolidated_decision import (
            ConsolidatedDecision,
            DecisionType,
            ConsensusMethod,
            SpecialistVote,
            ConsensusMetrics,
        )

        mongodb_client.set_cache_service(mock_redis_client)
        mongodb_client.consensus_collection.insert_one = AsyncMock(return_value=True)

        decision = ConsolidatedDecision(
            plan_id="plan-123",
            intent_id="intent-456",
            correlation_id="corr-789",
            final_decision=DecisionType.APPROVE,
            consensus_method=ConsensusMethod.BAYESIAN,
            aggregated_confidence=0.85,
            aggregated_risk=0.15,
            specialist_votes=[
                SpecialistVote(
                    specialist_type="business",
                    opinion_id="op-1",
                    confidence_score=0.9,
                    risk_score=0.1,
                    recommendation="approve",
                    weight=0.25,
                    processing_time_ms=100,
                )
            ],
            consensus_metrics=ConsensusMetrics(
                divergence_score=0.1,
                convergence_time_ms=500,
                unanimous=False,
                fallback_used=False,
                pheromone_strength=0.8,
                bayesian_confidence=0.85,
                voting_confidence=0.9,
            ),
            explainability_token="explain-test-123",
            reasoning_summary="Test decision",
            compliance_checks={},
            guardrails_triggered=[],
            requires_human_review=False,
            cognitive_plan={"test": "data"},
        )

        await mongodb_client.save_consensus_decision(decision)

        # Verificar que caches foram invalidados
        mock_redis_client.invalidate_consensus_decision.assert_called_once()
        mock_redis_client.invalidate_plan_approval.assert_called_once()


# Testes de TTL
def test_cache_ttl_configuration():
    """Testa que TTLs estão configurados corretamente por tipo de dado"""
    from src.clients.redis_client import RedisClient

    # Verificar constantes de TTL
    assert RedisClient.TTL_PLAN_APPROVAL == 300  # 5 minutos
    assert RedisClient.TTL_CONSENSUS_DECISION == 120  # 2 minutos
    assert RedisClient.TTL_SPECIALIST_STATUS == 30  # 30 segundos
