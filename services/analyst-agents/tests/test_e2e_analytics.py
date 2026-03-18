"""
Testes E2E para Analytics API V2.
"""
import pytest
import asyncio
from datetime import datetime, timedelta
from httpx import AsyncClient

from src.main import app
from src.models.insight_extended import (
    InsightCreate,
    AnalysisType,
    InsightSource,
    InsightStatus,
    InsightMetadata,
)
from src.repositories.insight_repository import InsightRepository
from src.services.timeseries_analyzer import TimeSeriesAnalyzer
from src.services.mcp_integration import MCPIntegration


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_e2e_insight_lifecycle(mongodb_client, test_database):
    """Teste E2E: Criar insight → Consultar → Exportar → Deletar."""
    # Setup
    from motor.motor_asyncio import AsyncIOMotorClient

    repo = InsightRepository(
        client=mongodb_client,
        database=test_database.name,
    )
    await repo.initialize()

    class MockAppState:
        def __init__(self):
            self.insight_repository = repo
            self.ts_analyzer = TimeSeriesAnalyzer()
            self.mcp_integration = MCPIntegration(timeout=5.0)
            # Não inicializar MCP para testes E2E locais

    app.state.app_state = MockAppState()

    # Criar insight via API
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/api/v1/analytics/insights/query", json={
            "analysis_type": "timeseries",
            "target": {
                "metric_name": "cpu_usage",
                "time_range": {"start": "2024-01-01T00:00:00", "end": "2024-01-02T00:00:00"}
            },
            "parameters": {}
        })

        assert response.status_code == 200
        data = response.json()
        query_id = data["query_id"]
        assert query_id is not None

        # Consultar insight criado
        response = await client.get(f"/api/v1/analytics/insights?limit=10")
        assert response.status_code == 200
        list_data = response.json()
        assert list_data["total"] >= 1

        # Se tiver insights, testar export
        if list_data["items"]:
            first_id = list_data["items"][0]["insight_id"]

            # Export JSON
            response = await client.get(f"/api/v1/analytics/insights/{first_id}/export?format=json")
            assert response.status_code == 200

            # Export CSV
            response = await client.get(f"/api/v1/analytics/insights/{first_id}/export?format=csv")
            assert response.status_code == 200
            assert "text/csv" in response.headers["content-type"]


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_e2e_timeseries_analysis(mongodb_client, test_database):
    """Teste E2E: Buscar série temporal → Detectar anomalias."""
    repo = InsightRepository(
        client=mongodb_client,
        database=test_database.name,
    )
    await repo.initialize()

    class MockAppState:
        def __init__(self):
            self.insight_repository = repo
            self.ts_analyzer = TimeSeriesAnalyzer()
            self.mcp_integration = MCPIntegration(timeout=5.0)

    app.state.app_state = MockAppState()

    async with AsyncClient(app=app, base_url="http://test") as client:
        start = (datetime.utcnow() - timedelta(hours=1)).isoformat()
        end = datetime.utcnow().isoformat()

        # Buscar série temporal
        response = await client.get(
            f"/api/v1/analytics/timeseries/cpu_usage?start={start}&end={end}&resolution=5m"
        )
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert len(data["data"]) > 0

        # Detectar anomalias
        response = await client.get(
            f"/api/v1/analytics/timeseries/cpu_usage/anomalies?start={start}&end={end}&method=zscore&threshold=2.5"
        )
        assert response.status_code == 200
        anomaly_data = response.json()
        assert "summary" in anomaly_data
        assert "total_anomalies" in anomaly_data["summary"]


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_e2e_dashboard_aggregation(mongodb_client, test_database):
    """Teste E2E: Criar insights → Ver dashboard agregado."""
    repo = InsightRepository(
        client=mongodb_client,
        database=test_database.name,
    )
    await repo.initialize()

    # Criar alguns insights de diferentes tipos
    for i in range(3):
        insight = await repo.create(InsightCreate(
            analysis_type=AnalysisType.TIMESERIES if i % 2 == 0 else AnalysisType.ANOMALY_DETECTION,
            title=f"Dashboard Test {i}",
            description="",
            data={},
            metadata=InsightMetadata(source=InsightSource.API),
            tags=["dashboard-test"],
        ))
        await repo.update_status(insight.insight_id, InsightStatus.COMPLETED)
        await repo.update_metrics(insight.insight_id, {
            "processing_time_ms": 100 + i * 50,
            "confidence_score": 0.8 + i * 0.05,
            "data_points": 100,
        })

    class MockAppState:
        def __init__(self):
            self.insight_repository = repo
            self.ts_analyzer = TimeSeriesAnalyzer()
            self.mcp_integration = MCPIntegration(timeout=5.0)

    app.state.app_state = MockAppState()

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/v1/analytics/dashboard?time_range=24h")

        assert response.status_code == 200
        data = response.json()
        assert "insights_by_type" in data
        assert "top_sources" in data
        assert "recent_insights" in data
        assert len(data["recent_insights"]) >= 3


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_e2e_mcp_health_check(mongodb_client, test_database):
    """Teste E2E: Verificar saúde dos servidores MCP."""
    repo = InsightRepository(
        client=mongodb_client,
        database=test_database.name,
    )
    await repo.initialize()

    class MockAppState:
        def __init__(self):
            self.insight_repository = repo
            self.ts_analyzer = TimeSeriesAnalyzer()
            mcp = MCPIntegration(timeout=5.0)
            # Inicializar para ter o cliente HTTP
            import asyncio
            async def init_and_close():
                await mcp.initialize()
                await mcp.close()
            asyncio.run(init_and_close())
            # Recriar sem inicializar para o teste
            self.mcp_integration = MCPIntegration(timeout=5.0)

    app.state.app_state = MockAppState()

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/v1/analytics/mcp-health")

        assert response.status_code == 200
        data = response.json()
        assert "scout" in data
        assert "optimizer" in data


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_e2e_metrics_endpoint(mongodb_client, test_database):
    """Teste E2E: Verificar endpoint de métricas Prometheus."""
    repo = InsightRepository(
        client=mongodb_client,
        database=test_database.name,
    )
    await repo.initialize()

    # Criar insight com métricas
    insight = await repo.create(InsightCreate(
        analysis_type=AnalysisType.TIMESERIES,
        title="Metrics Test",
        description="",
        data={},
        metadata=InsightMetadata(source=InsightSource.API),
        tags=["metrics"],
    ))
    await repo.update_status(insight.insight_id, InsightStatus.COMPLETED)
    await repo.update_metrics(insight.insight_id, {
        "processing_time_ms": 150,
        "confidence_score": 0.85,
        "data_points": 50,
    })

    class MockAppState:
        def __init__(self):
            self.insight_repository = repo
            self.ts_analyzer = TimeSeriesAnalyzer()
            self.mcp_integration = MCPIntegration(timeout=5.0)

    app.state.app_state = MockAppState()

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/v1/analytics/metrics")

        assert response.status_code == 200
        assert "analyst_insights_total" in response.text
        assert "analyst_processing_time_seconds" in response.text
        assert "text/plain" in response.headers["content-type"]


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_e2e_pagination_and_filters(mongodb_client, test_database):
    """Teste E2E: Paginação e filtros de insights."""
    repo = InsightRepository(
        client=mongodb_client,
        database=test_database.name,
    )
    await repo.initialize()

    # Criar insights de diferentes tipos
    for i in range(5):
        await repo.create(InsightCreate(
            analysis_type=AnalysisType.TIMESERIES if i % 2 == 0 else AnalysisType.ANOMALY_DETECTION,
            title=f"Filter Test {i}",
            description="",
            data={},
            metadata=InsightMetadata(source=InsightSource.API if i % 3 != 0 else InsightSource.KAFKA),
            tags=["test"] if i % 2 == 0 else ["production"],
        ))

    class MockAppState:
        def __init__(self):
            self.insight_repository = repo
            self.ts_analyzer = TimeSeriesAnalyzer()
            self.mcp_integration = MCPIntegration(timeout=5.0)

    app.state.app_state = MockAppState()

    async with AsyncClient(app=app, base_url="http://test") as client:
        # Testar paginação
        response1 = await client.get("/api/v1/analytics/insights?limit=2&offset=0")
        response2 = await client.get("/api/v1/analytics/insights?limit=2&offset=2")

        assert response1.status_code == 200
        assert response2.status_code == 200

        data1 = response1.json()
        data2 = response2.json()

        assert data1["total"] >= 5
        assert len(data1["items"]) == 2
        assert len(data2["items"]) == 2

        # Verificar que são diferentes
        ids1 = {i["insight_id"] for i in data1["items"]}
        ids2 = {i["insight_id"] for i in data2["items"]}
        assert ids1.isdisjoint(ids2)

        # Testar filtro por tipo
        response = await client.get("/api/v1/analytics/insights?analysis_type=timeseries")
        assert response.status_code == 200
        data = response.json()
        assert all(i["analysis_type"] == "timeseries" for i in data["items"])

        # Testar filtro por tags
        response = await client.get("/api/v1/analytics/insights?tags=test")
        assert response.status_code == 200
        data = response.json()
        assert all("test" in i["tags"] for i in data["items"])
