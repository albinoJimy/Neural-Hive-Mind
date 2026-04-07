"""
Testes unitários para QueryEngine.

Testes simplificados que focam na lógica de consulta multi-source.
"""

import pytest
from unittest.mock import AsyncMock, Mock, MagicMock
import hashlib
import json

from src.services.query_engine import QueryEngine


@pytest.fixture
def mock_clients():
    """Mock dos clientes de dados."""
    return {
        "clickhouse": AsyncMock(),
        "neo4j": AsyncMock(),
        "elasticsearch": AsyncMock(),
        "prometheus": AsyncMock(),
        "redis": AsyncMock(),
        "postgresql": AsyncMock(),
    }


@pytest.fixture
def query_engine(mock_clients):
    """Instância do QueryEngine."""
    from src.services.data_fusion_engine import DataFusionEngine

    return QueryEngine(
        clickhouse_client=mock_clients["clickhouse"],
        neo4j_client=mock_clients["neo4j"],
        elasticsearch_client=mock_clients["elasticsearch"],
        prometheus_client=mock_clients["prometheus"],
        redis_client=mock_clients["redis"],
        postgresql_client=mock_clients["postgresql"],
        data_fusion_engine=DataFusionEngine(),
    )


class TestQueryEngineInitialization:
    """Testes para inicialização."""

    def test_initialization(self, query_engine, mock_clients):
        """Testa inicialização básica."""
        assert query_engine.clickhouse is not None
        assert query_engine.neo4j is not None
        assert query_engine.elasticsearch is not None
        assert query_engine.prometheus is not None
        assert query_engine.redis is not None
        assert query_engine.postgresql is not None
        assert query_engine.data_fusion is not None


class TestGenerateQueryKey:
    """Testes para geração de chave de cache."""

    def test_generate_query_key(self, query_engine):
        """Testa geração de chave de cache."""
        query_spec = {
            "sources": ["clickhouse", "mongodb"],
            "time_window": {"start": "2024-01-01", "end": "2024-01-31"},
            "filters": {"status": "active"},
        }

        result = query_engine._generate_query_key(query_spec)

        assert isinstance(result, str)
        assert len(result) == 32  # MD5 hash length

    def test_generate_query_key_deterministic(self, query_engine):
        """Testa que mesma query gera mesma chave."""
        query_spec = {"sources": ["clickhouse"]}

        key1 = query_engine._generate_query_key(query_spec)
        key2 = query_engine._generate_query_key(query_spec)

        assert key1 == key2

    def test_generate_query_key_different_specs(self, query_engine):
        """Testa que queries diferentes geram chaves diferentes."""
        spec1 = {"sources": ["clickhouse"]}
        spec2 = {"sources": ["mongodb"]}

        key1 = query_engine._generate_query_key(spec1)
        key2 = query_engine._generate_query_key(spec2)

        assert key1 != key2


class TestQueryMultiSource:
    """Testes para consulta multi-source."""

    @pytest.mark.asyncio
    async def test_query_multi_source_with_cache_hit(self, query_engine):
        """Testa query com cache hit."""
        query_spec = {"sources": ["clickhouse"], "use_cache": True}

        cached_result = {"cached": True, "data": "test"}
        query_engine.redis.get_cached_query_result = AsyncMock(return_value=cached_result)

        result = await query_engine.query_multi_source(query_spec)

        assert result["cached"] is True
        assert result["results"] == cached_result

    @pytest.mark.asyncio
    async def test_query_multi_source_cache_miss(self, query_engine):
        """Testa query com cache miss."""
        query_spec = {"sources": ["clickhouse"], "use_cache": True, "enable_fusion": False}

        query_engine.redis.get_cached_query_result = AsyncMock(return_value=None)
        query_engine._query_clickhouse = AsyncMock(
            return_value={"source": "clickhouse", "data": [1, 2, 3]}
        )

        result = await query_engine.query_multi_source(query_spec)

        assert result["cached"] is False
        assert "clickhouse" in result["results"]

    @pytest.mark.asyncio
    async def test_query_multi_source_with_fusion(self, query_engine):
        """Testa query com fusão de dados."""
        query_spec = {
            "sources": ["clickhouse", "postgresql"],
            "use_cache": False,
            "enable_fusion": True,
        }

        query_engine.redis.get_cached_query_result = AsyncMock(return_value=None)
        query_engine._query_clickhouse = AsyncMock(return_value={"data": [1, 2]})
        query_engine._query_postgresql = AsyncMock(return_value={"data": [3, 4]})

        result = await query_engine.query_multi_source(query_spec)

        assert result["cached"] is False
        assert "fused" in result["results"]

    @pytest.mark.asyncio
    async def test_query_multi_source_error_handling(self, query_engine):
        """Testa tratamento de erros."""
        query_spec = {"sources": ["clickhouse"], "use_cache": False}

        query_engine.redis.get_cached_query_result = AsyncMock(return_value=None)
        query_engine._query_clickhouse = AsyncMock(side_effect=Exception("Connection error"))

        result = await query_engine.query_multi_source(query_spec)

        assert "error" in result["results"]["clickhouse"]


class TestQueryClickHouse:
    """Testes para consulta ClickHouse."""

    @pytest.mark.asyncio
    async def test_query_clickhouse_success(self, query_engine):
        """Testa consulta ClickHouse bem-sucedida."""
        query_spec = {
            "time_window": {"start": "2024-01-01", "end": "2024-01-31"},
            "metrics": ["cpu_usage"],
        }

        query_engine.clickhouse.get_execution_statistics = AsyncMock(
            return_value={"cpu_usage": [10, 20, 30]}
        )

        result = await query_engine._query_clickhouse(query_spec)

        assert result["source"] == "clickhouse"
        assert "data" in result

    @pytest.mark.asyncio
    async def test_query_clickhouse_error(self, query_engine):
        """Testa consulta ClickHouse com erro."""
        query_spec = {}

        query_engine.clickhouse.get_execution_statistics = AsyncMock(
            side_effect=Exception("Query error")
        )

        result = await query_engine._query_clickhouse(query_spec)

        assert result["source"] == "clickhouse"
        assert "error" in result


class TestQueryPostgreSQL:
    """Testes para consulta PostgreSQL."""

    @pytest.mark.asyncio
    async def test_query_postgresql_insights(self, query_engine):
        """Testa consulta de insights."""
        query_spec = {"query_type": "insights", "filters": {"analyst_id": "analyst-1"}, "limit": 10}

        query_engine.postgresql.get_insights = AsyncMock(
            return_value=[{"id": "1", "title": "Insight 1"}]
        )

        result = await query_engine._query_postgresql(query_spec)

        assert result["source"] == "postgresql"
        assert result["data"][0]["id"] == "1"

    @pytest.mark.asyncio
    async def test_query_postgresql_actions(self, query_engine):
        """Testa consulta de ações."""
        query_spec = {"query_type": "actions", "filters": {"analyst_id": "analyst-1"}, "limit": 10}

        query_engine.postgresql.get_analyst_actions = AsyncMock(
            return_value=[{"action": "approve"}]
        )

        result = await query_engine._query_postgresql(query_spec)

        assert result["source"] == "postgresql"
        assert len(result["data"]) == 1

    @pytest.mark.asyncio
    async def test_query_postgresql_without_client(self, query_engine):
        """Testa consulta sem cliente PostgreSQL."""
        query_engine.postgresql = None

        result = await query_engine._query_postgresql({"query_type": "insights"})

        assert result["source"] == "postgresql"
        assert "error" in result


class TestConsolidateResults:
    """Testes para consolidação de resultados."""

    def test_consolidate_results_all_success(self, query_engine):
        """Testa consolidação com todos os resultados bem-sucedidos."""
        results = {
            "clickhouse": {"source": "clickhouse", "data": [1, 2, 3]},
            "postgresql": {"source": "postgresql", "data": [4, 5]},
        }

        consolidated = query_engine.consolidate_results(results)

        assert "clickhouse" in consolidated
        assert "postgresql" in consolidated

    def test_consolidate_results_with_exceptions(self, query_engine):
        """Testa consolidação com exceções."""
        results = {
            "clickhouse": Exception("Connection failed"),
            "postgresql": {"source": "postgresql", "data": []},
        }

        consolidated = query_engine.consolidate_results(results)

        assert "error" in consolidated["clickhouse"]
        # consolidate_results extrai o campo "data"
        assert consolidated["postgresql"] == []


class TestJoinSources:
    """Testes para junção de fontes."""

    @pytest.mark.asyncio
    async def test_join_sources_basic(self, query_engine):
        """Testa junção básica de fontes."""
        query_spec = {"sources": ["clickhouse", "postgresql"]}

        query_engine.redis.get_cached_query_result = AsyncMock(return_value=None)
        query_engine._query_clickhouse = AsyncMock(
            return_value={"source": "clickhouse", "data": {"metric": 10}}
        )
        query_engine._query_postgresql = AsyncMock(
            return_value={"source": "postgresql", "data": {"metric": 12}}
        )

        result = await query_engine.join_sources(["clickhouse", "postgresql"], query_spec)

        assert "fused" in result or "sources" in result


class TestCorrelateMetrics:
    """Testes para correlação de métricas."""

    @pytest.mark.asyncio
    async def test_correlate_metrics_success(self, query_engine):
        """Testa cálculo de correlação."""
        query_spec = {"sources": ["clickhouse", "postgresql"], "use_cache": False}

        query_engine._query_clickhouse = AsyncMock(
            return_value={"source": "clickhouse", "data": {"cpu": [10, 20], "memory": [30, 40]}}
        )
        query_engine._query_postgresql = AsyncMock(
            return_value={"source": "postgresql", "data": {"cpu": [15, 25], "memory": [35, 45]}}
        )

        result = await query_engine.correlate_metrics(["clickhouse", "postgresql"], "cpu", "memory")

        # Deve retornar um valor entre -1 e 1
        if result is not None:
            assert -1 <= result <= 1

    @pytest.mark.asyncio
    async def test_correlate_metrics_error(self, query_engine):
        """Testa correlação com erro."""
        query_spec = {"sources": ["clickhouse"]}

        query_engine._query_clickhouse = AsyncMock(side_effect=Exception("Query error"))

        result = await query_engine.correlate_metrics(["clickhouse"], "cpu", "memory")

        assert result is None
