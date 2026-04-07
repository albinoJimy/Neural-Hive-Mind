"""
Testes para Analytics API V2 endpoints.
"""

import pytest
from httpx import AsyncClient, ASGITransport
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock
import sys
import os

# Mock MongoDB antes de importar
mock_motor = MagicMock()
mock_motor.AsyncIOMotorClient = MagicMock()
sys.modules["motor"] = mock_motor
sys.modules["motor.motor_asyncio"] = mock_motor

from src.main import app
from src.models.insight_extended import (
    InsightCreate,
    InsightResponse,
    AnalysisType,
    InsightSource,
    InsightStatus,
    InsightMetadata,
    TimeSeriesResponse,
    AnomalyDetectionResponse,
)


def create_mock_insight(insight_id: str, title: str = "Test Insight") -> InsightResponse:
    """Criar mock insight para testes."""
    from src.models.insight_extended import InsightMetrics

    return InsightResponse(
        insight_id=insight_id,
        analysis_type=AnalysisType.TIMESERIES,
        title=title,
        description="Test description",
        data={"metric": "test"},
        metadata=InsightMetadata(source=InsightSource.API),
        tags=["test"],
        status=InsightStatus.COMPLETED,
        created_at=datetime.now(timezone.utc),
        metrics=InsightMetrics(
            processing_time_ms=100,
            confidence_score=0.9,
            data_points=10,
        ),
    )


@pytest.fixture
async def app_client():
    """Cliente HTTP para testes com mocks."""
    # Mock do InsightRepository
    mock_repo = MagicMock()
    mock_repo.list = AsyncMock(return_value=([], 0))
    mock_repo.get_by_id = AsyncMock(return_value=None)
    mock_repo.create = AsyncMock()
    mock_repo.update_status = AsyncMock()
    mock_repo.get_analytics_summary = AsyncMock(
        return_value={
            "insights_by_type": {},
            "anomalies_detected": 0,
            "avg_processing_time_ms": 0,
            "confidence_distribution": {"high": 0, "medium": 0, "low": 0},
            "top_sources": [],
        }
    )

    # Mock do TimeSeriesAnalyzer
    mock_ts = MagicMock()

    # Import TimeSeriesResponse to create proper mock
    from src.models.insight_extended import TimeSeriesResponse, AnomalyDetectionResponse

    start_time = datetime.now(timezone.utc) - timedelta(hours=1)

    # Create proper mock response for analyze_timeseries
    mock_timeseries_response = TimeSeriesResponse(
        metric_name="cpu_usage",
        time_range={"start": start_time, "end": datetime.now(timezone.utc)},
        resolution="5m",
        data=[{"timestamp": start_time.isoformat(), "value": 50.0}],
        statistics={"min": 10, "max": 90, "avg": 50},
    )
    mock_ts.analyze_timeseries = AsyncMock(return_value=mock_timeseries_response)

    # Create proper mock response for detect_anomalies
    mock_anomalies_response = AnomalyDetectionResponse(
        metric_name="cpu_usage",
        method="zscore",
        threshold=2.5,
        anomalies=[],
        summary={"count": 0},
    )
    mock_ts.detect_anomalies_async = AsyncMock(return_value=mock_anomalies_response)

    # Mock do MCPIntegration
    mock_mcp = MagicMock()
    mock_mcp.health_check = AsyncMock(return_value={"scout": True, "optimizer": True})
    mock_mcp.execute_aggregated_analysis = AsyncMock(return_value={"result": "test"})
    mock_mcp.initialize = AsyncMock()
    mock_mcp.close = AsyncMock()

    # Create mock app state
    class MockAppState:
        def __init__(self):
            self.insight_repository = mock_repo
            self.ts_analyzer = mock_ts
            self.mcp_integration = mock_mcp

    app.state.app_state = MockAppState()

    # Usar ASGITransport para testes sem servidor
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ============================================================================
# Testes de Insights
# ============================================================================


@pytest.mark.asyncio
async def test_list_insights_empty(app_client):
    """Testar listar insights quando vazio."""
    response = await app_client.get("/api/v1/analytics/insights")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []


@pytest.mark.asyncio
async def test_list_insights_with_data(app_client):
    """Testar listar insights com dados."""
    # Mock com dados
    mock_insight = create_mock_insight("test-1", "Test Insight")
    app.state.app_state.insight_repository.list = AsyncMock(return_value=([mock_insight], 1))

    response = await app_client.get("/api/v1/analytics/insights")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1


@pytest.mark.asyncio
async def test_list_insights_by_type(app_client):
    """Testar filtrar por tipo de análise."""
    mock_insight = create_mock_insight("test-2", "TS Insight")
    app.state.app_state.insight_repository.list = AsyncMock(return_value=([mock_insight], 1))

    response = await app_client.get("/api/v1/analytics/insights?analysis_type=timeseries")

    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1


@pytest.mark.asyncio
async def test_get_insight_by_id(app_client):
    """Testar obter insight por ID."""
    mock_insight = create_mock_insight("test-3", "Get Test")
    app.state.app_state.insight_repository.get_by_id = AsyncMock(return_value=mock_insight)

    response = await app_client.get("/api/v1/analytics/insights/test-3")

    assert response.status_code == 200
    data = response.json()
    assert data["insight_id"] == "test-3"


@pytest.mark.asyncio
async def test_get_insight_not_found(app_client):
    """Testar obter insight inexistente."""
    app.state.app_state.insight_repository.get_by_id = AsyncMock(return_value=None)

    response = await app_client.get("/api/v1/analytics/insights/non-existent")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_query_timeseries(app_client):
    """Testar criar query de time series."""
    mock_insight = create_mock_insight("query-1")
    app.state.app_state.insight_repository.create = AsyncMock(return_value=mock_insight)
    app.state.app_state.insight_repository.update_status = AsyncMock(return_value=mock_insight)

    response = await app_client.post(
        "/api/v1/analytics/insights/query",
        json={
            "analysis_type": "timeseries",
            "target": {
                "metric_name": "cpu_usage",
                "time_range": {"start": "2024-01-01T00:00:00", "end": "2024-01-02T00:00:00"},
            },
            "parameters": {},
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "query_id" in data


@pytest.mark.asyncio
async def test_export_insight_json(app_client):
    """Testar exportar insight em JSON."""
    mock_insight = create_mock_insight("export-1", "Export Test")
    app.state.app_state.insight_repository.get_by_id = AsyncMock(return_value=mock_insight)

    response = await app_client.get("/api/v1/analytics/insights/export-1/export?format=json")

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Export Test"


@pytest.mark.asyncio
async def test_export_insight_csv(app_client):
    """Testar exportar insight em CSV."""
    mock_insight = create_mock_insight("export-2", "CSV Test")
    app.state.app_state.insight_repository.get_by_id = AsyncMock(return_value=mock_insight)

    response = await app_client.get("/api/v1/analytics/insights/export-2/export?format=csv")

    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_get_metrics(app_client):
    """Testar obter métricas Prometheus."""
    response = await app_client.get("/api/v1/analytics/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "analyst_insights_total" in response.text


@pytest.mark.asyncio
async def test_get_timeseries(app_client):
    """Testar obter série temporal."""
    from urllib.parse import quote

    start = quote((datetime.now(timezone.utc) - timedelta(hours=1)).isoformat())
    end = quote(datetime.now(timezone.utc).isoformat())

    response = await app_client.get(
        f"/api/v1/analytics/timeseries/cpu_usage?start={start}&end={end}&resolution=5m"
    )

    assert response.status_code == 200
    data = response.json()
    assert "metric_name" in data


@pytest.mark.asyncio
async def test_detect_anomalies(app_client):
    """Testar detecção de anomalias."""
    from urllib.parse import quote

    start = quote((datetime.now(timezone.utc) - timedelta(hours=1)).isoformat())
    end = quote(datetime.now(timezone.utc).isoformat())

    response = await app_client.get(
        f"/api/v1/analytics/timeseries/cpu_usage/anomalies?start={start}&end={end}&method=zscore&threshold=2.5"
    )

    assert response.status_code == 200
    data = response.json()
    assert "metric_name" in data
    assert "anomalies" in data


@pytest.mark.asyncio
async def test_get_dashboard(app_client):
    """Testar obter dados do dashboard."""
    response = await app_client.get("/api/v1/analytics/dashboard?time_range=24h")

    assert response.status_code == 200
    data = response.json()
    assert "insights_by_type" in data
    assert "anomalies_detected" in data


@pytest.mark.asyncio
async def test_get_dashboard_1h(app_client):
    """Testar dashboard com range de 1h."""
    response = await app_client.get("/api/v1/analytics/dashboard?time_range=1h")

    assert response.status_code == 200
    data = response.json()
    assert data["time_range"] == "1h"


@pytest.mark.asyncio
async def test_mcp_health_check(app_client):
    """Testar health check de servidores MCP."""
    response = await app_client.get("/api/v1/analytics/mcp-health")

    assert response.status_code == 200
    data = response.json()
    assert "scout" in data
    assert "optimizer" in data


@pytest.mark.asyncio
async def test_pagination(app_client):
    """Testar paginação de insights."""
    mock_insights = [create_mock_insight(f"page-{i}", f"Page Test {i}") for i in range(5)]
    app.state.app_state.insight_repository.list = AsyncMock(return_value=(mock_insights[:2], 5))

    response1 = await app_client.get("/api/v1/analytics/insights?limit=2&offset=0")
    response2 = await app_client.get("/api/v1/analytics/insights?limit=2&offset=2")

    assert response1.status_code == 200
    assert response2.status_code == 200

    data1 = response1.json()
    data2 = response2.json()

    assert data1["total"] == 5
    assert len(data1["items"]) == 2


@pytest.mark.asyncio
async def test_invalid_format_export(app_client):
    """Testar export com formato inválido."""
    mock_insight = create_mock_insight("invalid-1")
    app.state.app_state.insight_repository.get_by_id = AsyncMock(return_value=mock_insight)

    response = await app_client.get("/api/v1/analytics/insights/invalid-1/export?format=invalid")

    # FastAPI retorna 422 para regex pattern inválido
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_invalid_time_range(app_client):
    """Testar range de tempo inválido."""
    response = await app_client.get("/api/v1/analytics/dashboard?time_range=invalid")

    assert response.status_code == 422


# ============================================================================
# Testes de SSE Dashboard Stream
# ============================================================================


@pytest.mark.asyncio
async def test_dashboard_stream_initial_response(app_client):
    """Testar resposta inicial do stream SSE."""
    # Mock com dados
    mock_insight = create_mock_insight("stream-1", "Stream Test")
    app.state.app_state.insight_repository.list = AsyncMock(return_value=([mock_insight], 1))

    response = await app_client.get("/api/v1/analytics/dashboard/stream")

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
    assert "cache-control" in response.headers


@pytest.mark.asyncio
async def test_dashboard_stream_sse_format(app_client):
    """Testar formato dos eventos SSE enviados."""
    mock_insight = create_mock_insight("sse-1", "SSE Test")
    app.state.app_state.insight_repository.list = AsyncMock(return_value=([mock_insight], 1))

    response = await app_client.get("/api/v1/analytics/dashboard/stream?refresh_interval=1")

    assert response.status_code == 200

    # Ler primeiro chunk da resposta
    content = response.content
    # A resposta deve começar com "data: "
    assert b"data: " in content


@pytest.mark.asyncio
async def test_dashboard_stream_custom_interval(app_client):
    """Testar intervalo de refresh customizado."""
    response = await app_client.get("/api/v1/analytics/dashboard/stream?refresh_interval=60")

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_dashboard_stream_invalid_interval(app_client):
    """Testar intervalo de refresh inválido (fora dos limites)."""
    # Intervalo menor que o mínimo (5)
    response = await app_client.get("/api/v1/analytics/dashboard/stream?refresh_interval=2")

    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_dashboard_stream_data_structure(app_client):
    """Testar estrutura dos dados enviados no stream."""
    from src.models.insight_extended import InsightMetrics

    mock_insight = InsightResponse(
        insight_id="data-test-1",
        analysis_type=AnalysisType.SEMANTIC,
        title="Data Structure Test",
        description="Test",
        data={},
        metadata=InsightMetadata(source=InsightSource.MCP),
        tags=["test"],
        status=InsightStatus.COMPLETED,
        created_at=datetime.now(timezone.utc),
        metrics=InsightMetrics(
            processing_time_ms=150,
            confidence_score=0.85,
            data_points=100,
        ),
    )

    app.state.app_state.insight_repository.list = AsyncMock(return_value=([mock_insight], 1))

    response = await app_client.get("/api/v1/analytics/dashboard/stream?refresh_interval=1")

    assert response.status_code == 200
