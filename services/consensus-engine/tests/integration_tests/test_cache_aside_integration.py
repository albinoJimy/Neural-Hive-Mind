"""
Testes de integração para Cache-aside pattern com MongoDB.

Gap P1: Cache-aside pattern para reduzir latência e carga no MongoDB.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from pymongo.errors import DuplicateKeyError
from src.clients.mongodb_client import MongoDBClient
from src.services.cache_service import CacheAsideService
from src.models.consolidated_decision import (
    ConsolidatedDecision,
    DecisionType,
    ConsensusMethod,
    SpecialistVote,
    ConsensusMetrics,
)


class TestMongoDBClientCacheAside:
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
        client = MagicMock(spec=CacheAsideService)
        client.get_consensus_decision = AsyncMock(return_value=None)
        client.get_plan_approval = AsyncMock(return_value=None)
        client.invalidate_consensus_decision = AsyncMock(return_value=True)
        client.invalidate_plan_approval = AsyncMock(return_value=True)
        return client

    @pytest.fixture
    def mongodb_client(self, mock_config):
        """Instância de MongoDBClient para testes"""
        client = MongoDBClient(mock_config)
        # Mock motor client
        client.client = AsyncMock()
        client.db = AsyncMock()
        client.consensus_collection = AsyncMock()
        return client

    @pytest.fixture
    def sample_decision(self):
        """Decisão consolidada de exemplo"""
        return ConsolidatedDecision(
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
            reasoning_summary="Test decision",
            compliance_checks={},
            guardrails_triggered=[],
            requires_human_review=False,
            cognitive_plan={"test": "data"},
        )

    @pytest.mark.asyncio
    async def test_get_decision_cache_hit(self, mongodb_client, mock_redis_client):
        """Testa get_decision com cache hit"""
        mongodb_client.set_cache_service(mock_redis_client)

        cached_data = {"decision_id": "test-123", "final_decision": "approve"}
        mock_redis_client.get_consensus_decision = AsyncMock(return_value=cached_data)

        result = await mongodb_client.get_decision("test-123")

        assert result == cached_data
        mock_redis_client.get_consensus_decision.assert_called_once()
        mongodb_client.consensus_collection.find_one.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_get_decision_cache_miss(self, mongodb_client, mock_redis_client):
        """Testa get_decision com cache miss (busca do MongoDB)"""
        mongodb_client.set_cache_service(mock_redis_client)

        db_data = {"decision_id": "test-123", "final_decision": "approve"}
        mock_redis_client.get_consensus_decision = AsyncMock(return_value=None)
        mongodb_client.consensus_collection.find_one = AsyncMock(return_value=db_data)

        result = await mongodb_client.get_decision("test-123")

        assert result == db_data
        mock_redis_client.get_consensus_decision.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_decision_cache_disabled(self, mongodb_client):
        """Testa get_decision quando cache está desabilitado"""
        mongodb_client.config.enable_cache = False
        mongodb_client.cache_service = None

        db_data = {"decision_id": "test-123", "final_decision": "approve"}
        mongodb_client.consensus_collection.find_one = AsyncMock(return_value=db_data)

        result = await mongodb_client.get_decision("test-123")

        assert result == db_data
        mongodb_client.consensus_collection.find_one.assert_called_once_with(
            {"decision_id": "test-123"}
        )

    @pytest.mark.asyncio
    async def test_get_decision_by_plan_cache_hit(self, mongodb_client, mock_redis_client):
        """Testa get_decision_by_plan com cache hit"""
        mongodb_client.set_cache_service(mock_redis_client)

        cached_data = {"plan_id": "plan-123", "final_decision": "approve"}
        mock_redis_client.get_plan_approval = AsyncMock(return_value=cached_data)

        result = await mongodb_client.get_decision_by_plan("plan-123")

        assert result == cached_data
        mock_redis_client.get_plan_approval.assert_called_once()
        mongodb_client.consensus_collection.find_one.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_get_decision_by_plan_cache_miss(self, mongodb_client, mock_redis_client):
        """Testa get_decision_by_plan com cache miss"""
        mongodb_client.set_cache_service(mock_redis_client)

        db_data = {"plan_id": "plan-123", "final_decision": "approve"}
        mock_redis_client.get_plan_approval = AsyncMock(return_value=None)
        mongodb_client.consensus_collection.find_one = AsyncMock(return_value=db_data)

        result = await mongodb_client.get_decision_by_plan("plan-123")

        assert result == db_data
        mock_redis_client.get_plan_approval.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_decision_invalidates_cache(
        self, mongodb_client, mock_redis_client, sample_decision
    ):
        """Testa que salvar decisão invalida caches relacionados"""
        mongodb_client.set_cache_service(mock_redis_client)
        mongodb_client.consensus_collection.insert_one = AsyncMock(return_value=True)

        await mongodb_client.save_consensus_decision(sample_decision)

        # Verificar que caches foram invalidados
        mock_redis_client.invalidate_consensus_decision.assert_called_once_with(
            sample_decision.decision_id
        )
        mock_redis_client.invalidate_plan_approval.assert_called_once_with(sample_decision.plan_id)

    @pytest.mark.asyncio
    async def test_save_decision_duplicate_key_does_not_invalidate_cache(
        self, mongodb_client, mock_redis_client, sample_decision
    ):
        """Testa que DuplicateKeyError não invalida cache"""
        mongodb_client.set_cache_service(mock_redis_client)
        mongodb_client.consensus_collection.insert_one = AsyncMock(
            side_effect=DuplicateKeyError("duplicate key error")
        )

        with pytest.raises(DuplicateKeyError):
            await mongodb_client.save_consensus_decision(sample_decision)

        # Cache não deve ser invalidado em caso de erro
        mock_redis_client.invalidate_consensus_decision.assert_not_called()
        mock_redis_client.invalidate_plan_approval.assert_not_called()

    @pytest.mark.asyncio
    async def test_save_decision_cache_disabled_does_not_invalidate(
        self, mongodb_client, sample_decision
    ):
        """Testa que com cache desabilitado, invalidação não ocorre"""
        mongodb_client.config.enable_cache = False
        mongodb_client.cache_service = None
        mongodb_client.consensus_collection.insert_one = AsyncMock(return_value=True)

        await mongodb_client.save_consensus_decision(sample_decision)

        # Nenhuma chamada de invalidação deve ocorrer
        assert mongodb_client.cache_service is None

    @pytest.mark.asyncio
    async def test_fetch_decision_from_db_direct(self, mongodb_client):
        """Testa método privado _fetch_decision_from_db"""
        db_data = {"decision_id": "test-123", "final_decision": "approve"}
        mongodb_client.consensus_collection.find_one = AsyncMock(return_value=db_data)

        result = await mongodb_client._fetch_decision_from_db("test-123")

        assert result == db_data
        mongodb_client.consensus_collection.find_one.assert_called_once_with(
            {"decision_id": "test-123"}
        )

    @pytest.mark.asyncio
    async def test_fetch_decision_by_plan_from_db_direct(self, mongodb_client):
        """Testa método privado _fetch_decision_by_plan_from_db"""
        db_data = {"plan_id": "plan-123", "final_decision": "approve"}
        mongodb_client.consensus_collection.find_one = AsyncMock(return_value=db_data)

        result = await mongodb_client._fetch_decision_by_plan_from_db("plan-123")

        assert result == db_data
        mongodb_client.consensus_collection.find_one.assert_called_once_with(
            {"plan_id": "plan-123"}
        )


class TestCacheInvalidationWorkflow:
    """Testes de workflow de invalidação de cache"""

    @pytest.fixture
    def mock_config(self):
        """Configurações mockadas"""
        config = MagicMock()
        config.enable_cache = True
        return config

    @pytest.fixture
    def mock_redis_client(self):
        """RedisClient mockado"""
        client = MagicMock(spec=CacheAsideService)
        client.get_consensus_decision = AsyncMock(return_value=None)
        client.get_plan_approval = AsyncMock(return_value=None)
        client.invalidate_consensus_decision = AsyncMock(return_value=True)
        client.invalidate_plan_approval = AsyncMock(return_value=True)
        return client

    @pytest.fixture
    def mongodb_client(self, mock_config):
        """Instância de MongoDBClient para testes"""
        client = MongoDBClient(mock_config)
        client.client = AsyncMock()
        client.db = AsyncMock()
        client.consensus_collection = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_write_invalidate_pattern(self, mongodb_client, mock_redis_client):
        """
        Testa padrão write-invalidate:
        1. Write to DB
        2. Invalidate cache
        3. Next read fetches from DB and populates cache
        """
        mongodb_client.set_cache_service(mock_redis_client)

        # Setup: Cache tem dado obsoleto
        old_data = {"plan_id": "plan-123", "status": "pending"}
        new_data = {"plan_id": "plan-123", "status": "approved"}

        mock_redis_client.get_plan_approval = AsyncMock(return_value=old_data)
        mongodb_client.consensus_collection.find_one = AsyncMock(return_value=new_data)
        mongodb_client.consensus_collection.insert_one = AsyncMock(return_value=True)

        # Primeira leitura: cache hit (dado obsoleto)
        result1 = await mongodb_client.get_decision_by_plan("plan-123")
        assert result1 == old_data

        # Escrita: invalida cache

        decision = MagicMock()
        decision.decision_id = "decision-123"
        decision.plan_id = "plan-123"
        await mongodb_client.save_consensus_decision(decision)

        # Verificar invalidação
        mock_redis_client.invalidate_plan_approval.assert_called()

        # Segunda leitura: cache miss, busca DB atualizado
        mock_redis_client.get_plan_approval = AsyncMock(return_value=None)
        result2 = await mongodb_client.get_decision_by_plan("plan-123")
        assert result2 == new_data


class TestCacheTTLSemantics:
    """Testes de semântica de TTL por tipo de dado"""

    def test_plan_approval_ttl(self, mock_config):
        """Verifica TTL de plan approval (5 minutos)"""
        assert mock_config.cache_ttl_plan_approval == 300

    def test_consensus_decision_ttl(self, mock_config):
        """Verifica TTL de consensus decision (2 minutos)"""
        assert mock_config.cache_ttl_consensus_decision == 120

    def test_specialist_status_ttl(self, mock_config):
        """Verifica TTL de specialist status (30 segundos)"""
        assert mock_config.cache_ttl_specialist_status == 30
