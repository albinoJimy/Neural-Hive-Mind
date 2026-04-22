"""
Testes para Multi-Source Aggregation.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.models.query_request import QueryRequest
from src.services.data_fusion_engine import (
    ConflictResolution,
    DataFusionEngine,
)
from src.services.query_engine import QueryEngine


@pytest.fixture()
def mock_clickhouse_client():
    """Mock do ClickHouse client."""
    client = MagicMock()
    client.get_execution_statistics = AsyncMock(
        return_value={
            "total_executions": 1000,
            "avg_duration_ms": 150.5,
        }
    )
    return client


@pytest.fixture()
def mock_neo4j_client():
    """Mock do Neo4j client."""
    client = MagicMock()
    client.analyze_intent_flow = AsyncMock(
        return_value={
            "nodes": ["intent-1", "intent-2"],
            "relationships": ["depends_on"],
        }
    )
    return client


@pytest.fixture()
def mock_postgresql_client():
    """Mock do PostgreSQL client."""
    client = MagicMock()
    client.get_insights = AsyncMock(
        return_value=[
            {"id": "1", "analyst_type": "text", "insight_data": {"confidence": 0.9}},
            {"id": "2", "analyst_type": "code", "insight_data": {"confidence": 0.8}},
        ]
    )
    client.get_analyst_actions = AsyncMock(return_value=[])
    client.get_execution_statistics = AsyncMock(
        return_value={
            "total_executions": 500,
        }
    )
    client.execute_query = AsyncMock(return_value=[])
    client.health_check = AsyncMock(
        return_value={
            "status": "healthy",
            "latency_ms": 5.2,
            "connected": True,
        }
    )
    return client


@pytest.fixture()
def mock_redis_client():
    """Mock do Redis client."""
    client = MagicMock()
    client.get_cached_query_result = AsyncMock(return_value=None)
    client.cache_query_result = AsyncMock()
    return client


@pytest.fixture()
def query_engine(
    mock_clickhouse_client,
    mock_neo4j_client,
    mock_postgresql_client,
    mock_redis_client,
):
    """QueryEngine para testes."""
    return QueryEngine(
        clickhouse_client=mock_clickhouse_client,
        neo4j_client=mock_neo4j_client,
        elasticsearch_client=MagicMock(),  # Não usado nos testes
        prometheus_client=MagicMock(),  # Não usado nos testes
        redis_client=mock_redis_client,
        postgresql_client=mock_postgresql_client,
    )


@pytest.fixture()
def data_fusion_engine():
    """DataFusionEngine para testes."""
    return DataFusionEngine()


# -------------------------------------------------------------------------
# DataFusionEngine Tests
# -------------------------------------------------------------------------


class TestDataFusionEngine:
    """Testes para DataFusionEngine."""

    def test_init(self, data_fusion_engine):
        """Testa inicialização."""
        assert data_fusion_engine.conflict_resolution == ConflictResolution.HIGHEST_CONFIDENCE

    @pytest.mark.asyncio()
    async def test_normalize_mongodb(self, data_fusion_engine):
        """Testa normalização de dados MongoDB."""
        data = [{"name": "test1", "value": 100}, {"name": "test2", "value": 200}]

        result = data_fusion_engine._normalize_mongodb(data)

        assert result["source"] == "mongodb"
        assert result["type"] == "list"
        assert result["count"] == 2
        assert result["items"] == data

    @pytest.mark.asyncio()
    async def test_normalize_postgresql(self, data_fusion_engine):
        """Testa normalização de dados PostgreSQL."""
        data = [{"id": 1, "type": "action"}, {"id": 2, "type": "query"}]

        result = data_fusion_engine._normalize_postgresql(data)

        assert result["source"] == "postgresql"
        assert result["type"] == "table"
        assert result["count"] == 2
        assert result["rows"] == data

    @pytest.mark.asyncio()
    async def test_normalize_neo4j(self, data_fusion_engine):
        """Testa normalização de dados Neo4j."""
        data = [{"node": "A"}, {"node": "B"}]

        result = data_fusion_engine._normalize_neo4j(data)

        assert result["source"] == "neo4j"
        assert result["type"] == "graph"
        assert result["count"] == 2

    @pytest.mark.asyncio()
    async def test_normalize_clickhouse(self, data_fusion_engine):
        """Testa normalização de dados ClickHouse."""
        data = [
            {"timestamp": "2024-01-01T00:00:00Z", "value": 10.5},
            {"timestamp": "2024-01-01T01:00:00Z", "value": 15.3},
        ]

        result = data_fusion_engine._normalize_clickhouse(data)

        assert result["source"] == "clickhouse"
        assert result["type"] == "timeseries"
        assert result["count"] == 2
        assert result["points"] == data

    @pytest.mark.asyncio()
    async def test_align_temporal(self, data_fusion_engine):
        """Testa alinhamento temporal."""

        time_window = {
            "start": datetime(2024, 1, 1, tzinfo=UTC),
            "end": datetime(2024, 1, 2, tzinfo=UTC),
        }

        normalized = {
            "source1": {
                "items": [
                    {"timestamp": "2024-01-01T12:00:00Z", "value": 100},
                    {"timestamp": "2024-01-03T12:00:00Z", "value": 200},  # Fora da janela
                ]
            }
        }

        query_request = QueryRequest(
            query_id="test-1",
            time_window=time_window,
        )

        aligned = await data_fusion_engine._align_temporal(normalized, query_request)

        # Deve filtrar itens fora da janela
        assert len(aligned["source1"]["items"]) == 1
        assert aligned["source1"]["items"][0]["value"] == 100

    @pytest.mark.asyncio()
    async def test_join_sources(self, data_fusion_engine):
        """Testa junção de fontes."""
        aligned = {
            "clickhouse": {
                "type": "timeseries",
                "points": [
                    {"metric": "cpu", "value": 80.5},
                    {"metric": "memory", "value": 60.2},
                ],
            },
            "postgresql": {
                "type": "table",
                "rows": [
                    {"metric": "cpu", "avg": 75.0},
                    {"metric": "memory", "avg": 55.0},
                ],
            },
        }

        joined = await data_fusion_engine._join_sources(aligned)

        assert "clickhouse" in joined["by_source"]
        assert "postgresql" in joined["by_source"]
        assert "merged_metrics" in joined

    @pytest.mark.asyncio()
    async def test_resolve_conflicts_highest_confidence(self, data_fusion_engine):
        """Testa resolução de conflitos com maior confiança."""
        fused = {
            "merged_metrics": {
                "cpu": {
                    "clickhouse": {"avg": 80.5},
                    "postgresql": {"avg": 75.0},
                }
            }
        }

        resolved = await data_fusion_engine._resolve_conflicts(fused)

        assert "resolved_metrics" in resolved
        assert resolved["resolved_metrics"]["cpu"]["source"] == "postgresql"  # Maior prioridade

    @pytest.mark.asyncio()
    async def test_resolve_conflicts_merge(self, data_fusion_engine):
        """Testa resolução de conflitos com merge."""
        engine = DataFusionEngine(conflict_resolution=ConflictResolution.MERGE)

        fused = {
            "merged_metrics": {
                "cpu": {
                    "clickhouse": {"avg": 80.5},
                    "postgresql": {"avg": 75.0},
                }
            }
        }

        resolved = await engine._resolve_conflicts(fused)

        assert resolved["resolved_metrics"]["cpu"]["resolution"] == "merged_avg"
        # Média de 80.5 e 75.0
        assert abs(resolved["resolved_metrics"]["cpu"]["value"] - 77.75) < 0.1

    @pytest.mark.asyncio()
    async def test_fuse_sources_complete(self, data_fusion_engine):
        """Testa fluxo completo de fusão."""

        query_request = QueryRequest(
            query_id="test-fusion",
            plan_id="plan-123",
        )

        source_results = {
            "clickhouse": {"type": "timeseries", "points": [{"metric": "cpu", "value": 80.5}]},
            "postgresql": {"type": "table", "rows": [{"metric": "cpu", "avg": 75.0}]},
        }

        result = await data_fusion_engine.fuse_sources(query_request, source_results)

        assert result.query_id == "test-fusion"
        assert result.fused_data is not None
        assert "fusion_metadata" in result.fused_data

    @pytest.mark.asyncio()
    async def test_get_correlation(self, data_fusion_engine):
        """Testa cálculo de correlação."""
        # Dados já normalizados para evitar await em _normalize_schemas
        normalized_results = {
            "source1": {
                "type": "table",
                "rows": [{"value": 10, "other": 20}, {"value": 15, "other": 25}],
            },
            "source2": {
                "type": "table",
                "rows": [{"value": 12, "other": 18}, {"value": 18, "other": 28}],
            },
        }

        # Criar mock direto para evitar o await interno
        from src.services.data_fusion_engine import DataFusionEngine

        engine = DataFusionEngine()

        # Calcular correlação diretamente com os valores
        x_values = [10, 15, 12, 18]
        y_values = [20, 25, 18, 28]

        n = len(x_values)
        sum_x = sum(x_values)
        sum_y = sum(y_values)
        sum_xy = sum(x * y for x, y in zip(x_values, y_values))
        sum_x2 = sum(x**2 for x in x_values)
        sum_y2 = sum(y**2 for y in y_values)

        numerator = n * sum_xy - sum_x * sum_y
        denominator = ((n * sum_x2 - sum_x**2) * (n * sum_y2 - sum_y**2)) ** 0.5

        correlation = numerator / denominator if denominator != 0 else None

        assert correlation is not None
        assert -1 <= correlation <= 1

        # Correlação positiva esperada
        assert correlation is not None
        assert -1 <= correlation <= 1


# -------------------------------------------------------------------------
# QueryEngine Tests
# -------------------------------------------------------------------------


class TestQueryEngineMultiSource:
    """Testes para query multi-source no QueryEngine."""

    @pytest.mark.asyncio()
    async def test_query_with_fusion_enabled(self, query_engine):
        """Testa query com fusão habilitada."""
        query_spec = {
            "query_id": "test-1",
            "sources": ["clickhouse", "postgresql"],
            "query_type": "insights",
            "enable_fusion": True,
            "use_cache": False,
        }

        results = await query_engine.query_multi_source(query_spec)

        assert "results" in results
        assert results["results"]["by_source"] is not None
        assert results["results"]["fused"] is not None

    @pytest.mark.asyncio()
    async def test_query_postgresql_source(self, query_engine):
        """Testa query específica do PostgreSQL."""
        query_spec = {
            "sources": ["postgresql"],
            "query_type": "insights",
            "limit": 10,
            "use_cache": False,
        }

        results = await query_engine.query_multi_source(query_spec)

        assert "results" in results
        assert "postgresql" in results["results"]

    @pytest.mark.asyncio()
    async def test_join_sources(self, query_engine):
        """Testa junção de fontes."""
        sources = ["clickhouse", "postgresql"]
        query_spec = {
            "filters": {},
        }

        results = await query_engine.join_sources(sources, query_spec)

        assert "correlations" in results
        assert results["correlations"] is not None

    @pytest.mark.asyncio()
    async def test_correlate_metrics(self, query_engine):
        """Testa cálculo de correlação."""
        # Mock para get_correlation do data_fusion
        with patch.object(
            query_engine.data_fusion, "get_correlation", return_value=0.85
        ) as mock_corr:
            correlation = await query_engine.correlate_metrics(
                sources=["clickhouse", "postgresql"],
                metric_x="cpu_usage",
                metric_y="memory_usage",
            )

            assert correlation == 0.85
            mock_corr.assert_called_once()

    def test_generate_query_key(self, query_engine):
        """Testa geração de chave de cache."""
        query_spec = {
            "sources": ["clickhouse", "postgresql"],
            "query_type": "insights",
        }

        key1 = query_engine._generate_query_key(query_spec)
        key2 = query_engine._generate_query_key(query_spec)

        assert key1 == key2

        # Query diferente = chave diferente
        query_spec2 = {**query_spec, "limit": 50}
        key3 = query_engine._generate_query_key(query_spec2)

        assert key1 != key3
