"""
Testes para Analytics API V2 endpoints.
"""
import pytest
from httpx import AsyncClient
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from src.main import app
from src.models.insight_extended import (
    InsightCreate,
    AnalysisType,
    InsightSource,
    InsightStatus,
    InsightMetadata,
)


@pytest.fixture
async def app_client(mongodb_client, test_database):
    """Cliente HTTP para testes."""
    # Mock app state
    from src.repositories.insight_repository import InsightRepository
    from src.services.timeseries_analyzer import TimeSeriesAnalyzer
    from src.services.mcp_integration import MCPIntegration

    repo = InsightRepository(
        client=mongodb_client,
        database=test_database.name,
    )
    await repo.initialize()

    ts_analyzer = TimeSeriesAnalyzer()

    mcp_integration = MCPIntegration(
        scout_url="http://localhost:8000",
        optimizer_url="http://localhost:8001",
        timeout=5.0,
    )
    await mcp_integration.initialize()

    # Create mock app state
    class MockAppState:
        def __init__(self):
            self.insight_repository = repo
            self.ts_analyzer = ts_analyzer
            self.mcp_integration = mcp_integration

    app.state.app_state = MockAppState()

    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

    await mcp_integration.close()


@pytest.mark.asyncio
async def test_list_insights_empty(app_client):
    """Testar listar insights quando vazio."""
    response = await app_client.get("/api/v1/analytics/insights")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []


@pytest.mark.asyncio
async def test_list_insights_with_data(app_client, insight_repository):
    """Testar listar insights com dados."""
    # Criar insight
    await insight_repository.create(InsightCreate(
        analysis_type=AnalysisType.TIMESERIES,
        title="Test Insight",
        description="Test",
        data={},
        metadata=InsightMetadata(source=InsightSource.API),
        tags=["test"],
    ))

    response = await app_client.get("/api/v1/analytics/insights")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert len(data["items"]) >= 1


@pytest.mark.asyncio
async def test_list_insights_by_type(app_client, insight_repository):
    """Testar filtrar por tipo de análise."""
    await insight_repository.create(InsightCreate(
        analysis_type=AnalysisType.TIMESERIES,
        title="TS Insight",
        description="",
        data={},
        metadata=InsightMetadata(source=InsightSource.API),
        tags=[],
    ))

    response = await app_client.get("/api/v1/analytics/insights?analysis_type=timeseries")

    assert response.status_code == 200
    data = response.json()
    assert all(i["analysis_type"] == "timeseries" for i in data["items"])


@pytest.mark.asyncio
async def test_get_insight_by_id(app_client, insight_repository):
    """Testar obter insight por ID."""
    created = await insight_repository.create(InsightCreate(
        analysis_type=AnalysisType.TIMESERIES,
        title="Get Test",
        description="",
        data={},
        metadata=InsightMetadata(source=InsightSource.API),
        tags=[],
    ))

    response = await app_client.get(f"/api/v1/analytics/insights/{created.insight_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["insight_id"] == created.insight_id
    assert data["title"] == "Get Test"


@pytest.mark.asyncio
async def test_get_insight_not_found(app_client):
    """Testar obter insight inexistente."""
    response = await app_client.get("/api/v1/analytics/insights/non-existent")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_query_timeseries(app_client):
    """Testar criar query de time series."""
    response = await app_client.post("/api/v1/analytics/insights/query", json={
        "analysis_type": "timeseries",
        "target": {
            "metric_name": "cpu_usage",
            "time_range": {"start": "2024-01-01T00:00:00", "end": "2024-01-02T00:00:00"}
        },
        "parameters": {}
    })

    assert response.status_code == 200
    data = response.json()
    assert "query_id" in data
    assert data["status"] in ["pending", "completed"]


@pytest.mark.asyncio
async def test_export_insight_json(app_client, insight_repository):
    """Testar exportar insight em JSON."""
    created = await insight_repository.create(InsightCreate(
        analysis_type=AnalysisType.TIMESERIES,
        title="Export Test",
        description="Test export",
        data={"value": 123},
        metadata=InsightMetadata(source=InsightSource.API),
        tags=["export"],
    ))

    response = await app_client.get(f"/api/v1/analytics/insights/{created.insight_id}/export?format=json")

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Export Test"


@pytest.mark.asyncio
async def test_export_insight_csv(app_client, insight_repository):
    """Testar exportar insight em CSV."""
    created = await insight_repository.create(InsightCreate(
        analysis_type=AnalysisType.TIMESERIES,
        title="CSV Test",
        description="",
        data={},
        metadata=InsightMetadata(source=InsightSource.API),
        tags=[],
    ))

    response = await app_client.get(f"/api/v1/analytics/insights/{created.insight_id}/export?format=csv")

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert "CSV Test" in response.text


@pytest.mark.asyncio
async def test_get_metrics(app_client):
    """Testar obter métricas Prometheus."""
    response = await app_client.get("/api/v1/analytics/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/plain; charset=utf-8"
    assert "analyst_insights_total" in response.text


@pytest.mark.asyncio
async def test_get_timeseries(app_client):
    """Testar obter série temporal."""
    start = (datetime.utcnow() - timedelta(hours=1)).isoformat()
    end = datetime.utcnow().isoformat()

    response = await app_client.get(
        f"/api/v1/analytics/timeseries/cpu_usage?start={start}&end={end}&resolution=5m"
    )

    assert response.status_code == 200
    data = response.json()
    assert data["metric_name"] == "cpu_usage"
    assert "data" in data
    assert "statistics" in data


@pytest.mark.asyncio
async def test_detect_anomalies(app_client):
    """Testar detecção de anomalias."""
    start = (datetime.utcnow() - timedelta(hours=1)).isoformat()
    end = datetime.utcnow().isoformat()

    response = await app_client.get(
        f"/api/v1/analytics/timeseries/cpu_usage/anomalies?start={start}&end={end}&method=zscore&threshold=2.5"
    )

    assert response.status_code == 200
    data = response.json()
    assert data["metric_name"] == "cpu_usage"
    assert "anomalies" in data
    assert "summary" in data


@pytest.mark.asyncio
async def test_get_dashboard(app_client):
    """Testar obter dados do dashboard."""
    response = await app_client.get("/api/v1/analytics/dashboard?time_range=24h")

    assert response.status_code == 200
    data = response.json()
    assert "insights_by_type" in data
    assert "anomalies_detected" in data
    assert "top_sources" in data


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
async def test_pagination(app_client, insight_repository):
    """Testar paginação de insights."""
    # Criar 5 insights
    for i in range(5):
        await insight_repository.create(InsightCreate(
            analysis_type=AnalysisType.TIMESERIES,
            title=f"Page Test {i}",
            description="",
            data={"index": i},
            metadata=InsightMetadata(source=InsightSource.API),
            tags=[],
        ))

    response1 = await app_client.get("/api/v1/analytics/insights?limit=2&offset=0")
    response2 = await app_client.get("/api/v1/analytics/insights?limit=2&offset=2")

    assert response1.status_code == 200
    assert response2.status_code == 200

    data1 = response1.json()
    data2 = response2.json()

    assert data1["total"] >= 5
    assert len(data1["items"]) == 2
    assert len(data2["items"]) == 2


@pytest.mark.asyncio
async def test_invalid_format_export(app_client, insight_repository):
    """Testar export com formato inválido."""
    created = await insight_repository.create(InsightCreate(
        analysis_type=AnalysisType.TIMESERIES,
        title="Test",
        description="",
        data={},
        metadata=InsightMetadata(source=InsightSource.API),
        tags=[],
    ))

    response = await app_client.get(f"/api/v1/analytics/insights/{created.insight_id}/export?format=invalid")

    assert response.status_code == 422  # Unprocessable Entity


@pytest.mark.asyncio
async def test_invalid_time_range(app_client):
    """Testar range de tempo inválido."""
    response = await app_client.get("/api/v1/analytics/dashboard?time_range=invalid")

    assert response.status_code == 422
