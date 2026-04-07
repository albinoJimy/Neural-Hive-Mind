"""
Testes unitários para DataFusionEngine.

Testes simplificados que focam na lógica de fusão de dados.
"""

import pytest
from unittest.mock import Mock
from datetime import datetime, timezone

from src.services.data_fusion_engine import DataFusionEngine, ConflictResolution, AggregatedResult


@pytest.fixture
def data_fusion_engine():
    """Instância do DataFusionEngine."""
    return DataFusionEngine(conflict_resolution=ConflictResolution.HIGHEST_CONFIDENCE)


@pytest.fixture
def mock_query_request():
    """Mock de QueryRequest."""
    request = Mock()
    request.query_id = "test-query-1"
    request.plan_id = "plan-1"
    request.analyst_types = ["text"]
    request.time_window = None
    request.filters = {}
    return request


class TestDataFusionEngineInitialization:
    """Testes para inicialização."""

    def test_initialization(self, data_fusion_engine):
        """Testa inicialização básica."""
        assert data_fusion_engine.conflict_resolution == ConflictResolution.HIGHEST_CONFIDENCE
        assert data_fusion_engine.logger is not None

    def test_initialization_default_resolution(self):
        """Testa inicialização com resolução default."""
        engine = DataFusionEngine()
        assert engine.conflict_resolution == ConflictResolution.HIGHEST_CONFIDENCE


class TestNormalizeSchemas:
    """Testes para normalização de esquemas."""

    def test_normalize_mongodb_list(self, data_fusion_engine):
        """Testa normalização de lista MongoDB."""
        data = [{"id": 1, "name": "test"}, {"id": 2, "name": "test2"}]

        result = data_fusion_engine._normalize_mongodb(data)

        assert result["type"] == "list"
        assert result["count"] == 2
        assert result["source"] == "mongodb"

    def test_normalize_mongodb_document(self, data_fusion_engine):
        """Testa normalização de documento MongoDB."""
        data = {"_id": "123", "name": "test"}

        result = data_fusion_engine._normalize_mongodb(data)

        assert result["type"] == "document"
        assert result["source"] == "mongodb"

    def test_normalize_postgresql_list(self, data_fusion_engine):
        """Testa normalização de lista PostgreSQL."""
        data = [{"id": 1}, {"id": 2}]

        result = data_fusion_engine._normalize_postgresql(data)

        assert result["type"] == "table"
        assert result["count"] == 2
        assert result["source"] == "postgresql"

    def test_normalize_clickhouse_list(self, data_fusion_engine):
        """Testa normalização de lista ClickHouse."""
        data = [{"timestamp": "2024-01-01", "value": 10.5}]

        result = data_fusion_engine._normalize_clickhouse(data)

        assert result["type"] == "timeseries"
        assert result["count"] == 1
        assert result["source"] == "clickhouse"

    def test_normalize_neo4j_list(self, data_fusion_engine):
        """Testa normalização de lista Neo4j."""
        data = [{"id": "1", "labels": ["User"]}]

        result = data_fusion_engine._normalize_neo4j(data)

        assert result["type"] == "graph"
        assert result["count"] == 1
        assert result["source"] == "neo4j"

    def test_normalize_generic(self, data_fusion_engine):
        """Testa normalização genérica."""
        data = {"key": "value"}

        result = data_fusion_engine._normalize_generic(data)

        assert result["type"] == "generic"
        assert "data" in result


class TestAlignTemporal:
    """Testes para alinhamento temporal."""

    @pytest.mark.asyncio
    async def test_align_without_time_window(self, data_fusion_engine):
        """Testa alinhamento sem janela temporal."""
        normalized = {"mongodb": {"type": "list", "items": []}}

        result = await data_fusion_engine._align_temporal(normalized, Mock(time_window=None))

        assert result == normalized

    @pytest.mark.asyncio
    async def test_align_with_time_window_filter(self, data_fusion_engine):
        """Testa filtro por janela temporal."""
        time_window = {
            "start": datetime(2024, 1, 1, tzinfo=timezone.utc),
            "end": datetime(2024, 1, 31, tzinfo=timezone.utc),
        }

        normalized = {
            "mongodb": {
                "type": "list",
                "items": [
                    {"timestamp": "2024-01-15T10:00:00Z", "value": 10},
                    {"timestamp": "2024-02-15T10:00:00Z", "value": 20},  # Fora da janela
                ],
            }
        }

        result = await data_fusion_engine._align_temporal(normalized, Mock(time_window=time_window))

        # Apenas um item deve estar na janela
        items = result["mongodb"]["items"]
        assert len(items) == 1
        assert "2024-01-15" in items[0]["timestamp"]


class TestJoinSources:
    """Testes para junção de fontes."""

    @pytest.mark.asyncio
    async def test_join_sources_empty(self, data_fusion_engine):
        """Testa junção com dados vazios."""
        aligned = {}

        result = await data_fusion_engine._join_sources(aligned)

        assert result["sources"] == []
        assert result["by_source"] == aligned

    @pytest.mark.asyncio
    async def test_join_sources_with_data(self, data_fusion_engine):
        """Testa junção com dados."""
        aligned = {
            "mongodb": {"type": "list", "items": [{"metric": "cpu", "value": 80}]},
            "clickhouse": {"type": "timeseries", "points": [{"metric": "cpu", "value": 85}]},
        }

        result = await data_fusion_engine._join_sources(aligned)

        assert result["sources"] == ["mongodb", "clickhouse"]
        assert "merged_metrics" in result


class TestResolveConflicts:
    """Testes para resolução de conflitos."""

    def test_resolve_keep_first(self, data_fusion_engine):
        """Testa resolução KEEP_FIRST."""
        data_fusion_engine.conflict_resolution = ConflictResolution.KEEP_FIRST

        source_values = {"mongodb": {"avg": 80.0}, "clickhouse": {"avg": 85.0}}

        result = data_fusion_engine._resolve_metric_conflict("cpu", source_values)

        assert result["source"] == "mongodb"
        assert result["resolution"] == "keep_first"

    def test_resolve_highest_confidence(self, data_fusion_engine):
        """Testa resolução HIGHEST_CONFIDENCE."""
        data_fusion_engine.conflict_resolution = ConflictResolution.HIGHEST_CONFIDENCE

        source_values = {
            "clickhouse": {"avg": 85.0},
            "postgresql": {"avg": 75.0},
            "mongodb": {"avg": 80.0},
        }

        result = data_fusion_engine._resolve_metric_conflict("cpu", source_values)

        # PostgreSQL tem maior prioridade na lista
        assert result["source"] == "postgresql"
        assert result["resolution"] == "highest_confidence"

    def test_resolve_merge(self, data_fusion_engine):
        """Testa resolução MERGE."""
        data_fusion_engine.conflict_resolution = ConflictResolution.MERGE

        source_values = {"mongodb": {"avg": 80.0}, "clickhouse": {"avg": 85.0}}

        result = data_fusion_engine._resolve_metric_conflict("cpu", source_values)

        assert result["resolution"] == "merged_avg"
        assert result["value"] == 82.5  # Média


class TestFuseSources:
    """Testes para fusão de fontes."""

    @pytest.mark.asyncio
    async def test_fuse_sources_basic(self, data_fusion_engine, mock_query_request):
        """Testa fusão básica de fontes."""
        source_results = {
            "mongodb": [{"metric": "cpu", "value": 80}],
            "clickhouse": [{"metric": "cpu", "value": 85}],
        }

        result = await data_fusion_engine.fuse_sources(mock_query_request, source_results)

        assert isinstance(result, AggregatedResult)
        assert result.query_id == "test-query-1"
        assert result.sources == ["mongodb", "clickhouse"]
        assert result.fused_data is not None

    @pytest.mark.asyncio
    async def test_fuse_sources_with_error(self, data_fusion_engine, mock_query_request):
        """Testa fusão com erro em fonte."""
        source_results = {
            "mongodb": {"error": "Connection failed"},
            "clickhouse": [{"metric": "cpu", "value": 85}],
        }

        result = await data_fusion_engine.fuse_sources(mock_query_request, source_results)

        assert isinstance(result, AggregatedResult)
        assert "mongodb" in result.sources
        assert "clickhouse" in result.sources


class TestGetCorrelation:
    """Testes para cálculo de correlação."""

    @pytest.mark.asyncio
    async def test_get_correlation_insufficient_data(self, data_fusion_engine):
        """Testa correlação com dados insuficientes."""
        source_results = {"mongodb": [{"value": 10}], "clickhouse": [{"value": 20}]}

        result = await data_fusion_engine.get_correlation(source_results, "metric1", "metric2")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_correlation_success(self, data_fusion_engine):
        """Testa cálculo de correlação."""
        source_results = {
            "mongodb": [{"cpu": 10, "memory": 20}, {"cpu": 15, "memory": 25}],
            "clickhouse": [{"cpu": 12, "memory": 22}],
        }

        result = await data_fusion_engine.get_correlation(source_results, "cpu", "memory")

        # Deve retornar um valor entre -1 e 1
        if result is not None:
            assert -1 <= result <= 1


class TestAggregatedResult:
    """Testes para AggregatedResult."""

    def test_aggregated_result_creation(self):
        """Testa criação de AggregatedResult."""
        result = AggregatedResult(
            query_id="test-1", sources=["mongodb", "clickhouse"], results={"data": "test"}
        )

        assert result.query_id == "test-1"
        assert result.sources == ["mongodb", "clickhouse"]
        assert result.results == {"data": "test"}
        assert result.fused_data is None
        assert result.conflicts == []
        assert result.warnings == []

    def test_aggregated_result_to_dict(self):
        """Testa conversão para dicionário."""
        result = AggregatedResult(query_id="test-1", sources=["mongodb"], results={"key": "value"})

        result.fused_data = {"merged": "data"}

        dict_result = result.to_dict()

        assert dict_result["query_id"] == "test-1"
        assert "fused_data" in dict_result
