"""
Testes E2E para Analytics API V2.
Usa mocks para evitar dependências externas.
"""
import pytest
import asyncio
from datetime import datetime, timedelta
from httpx import AsyncClient, ASGITransport

from src.main import app
from src.models.insight_extended import (
    InsightCreate,
    AnalysisType,
    InsightSource,
    InsightStatus,
    InsightMetadata,
)


@pytest.fixture
async def mock_app_state():
    """Mock app state com repository mockado."""
    from unittest.mock import AsyncMock, MagicMock
    from src.repositories.insight_repository import InsightRepository
    from src.services.timeseries_analyzer import TimeSeriesAnalyzer
    from src.services.mcp_integration import MCPIntegration
    import uuid
    from datetime import datetime, timedelta
    from src.models.insight_extended import InsightResponse, InsightStatus, InsightMetrics

    # In-memory storage para testes
    storage = {"insights": {}, "cache": {}}

    class MockInsightRepository(InsightRepository):
        def __init__(self):
            self.storage = storage
            self.collection = "insights"
            self.cache_collection = "time_series_cache"
            self._db = MagicMock()

        async def create(self, insight: InsightCreate):
            doc = insight.model_dump()
            doc["insight_id"] = str(uuid.uuid4())
            doc["status"] = InsightStatus.PENDING.value
            doc["created_at"] = datetime.utcnow()
            doc["expires_at"] = datetime.utcnow() + timedelta(days=90)
            doc["metrics"] = InsightMetrics(processing_time_ms=0, confidence_score=0.0, data_points=0).model_dump()
            self.storage["insights"][doc["insight_id"]] = doc
            return InsightResponse(**doc)

        async def get_by_id(self, insight_id: str):
            doc = self.storage["insights"].get(insight_id)
            if doc:
                return InsightResponse(**doc)
            return None

        async def list(self, **kwargs):
            limit = kwargs.get('limit', 50)
            offset = kwargs.get('offset', 0)
            items = list(self.storage["insights"].values())

            if kwargs.get('analysis_type'):
                items = [i for i in items if i.get('analysis_type') == kwargs['analysis_type'].value]
            if kwargs.get('source'):
                items = [i for i in items if i.get('metadata', {}).get('source') == kwargs['source'].value]
            if kwargs.get('tags'):
                tags = kwargs['tags']
                items = [i for i in items if any(t in i.get('tags', []) for t in tags)]
            if kwargs.get('status'):
                items = [i for i in items if i.get('status') == kwargs['status'].value]

            total = len(items)
            items = sorted(items, key=lambda x: x.get('created_at', datetime.min), reverse=True)
            items = items[offset:offset + limit]

            return [InsightResponse(**i) for i in items], total

        async def update_status(self, insight_id: str, status: InsightStatus, data=None):
            if insight_id in self.storage["insights"]:
                doc = self.storage["insights"][insight_id]
                doc["status"] = status.value
                if data:
                    doc["data"] = data
                return InsightResponse(**doc)
            return None

        async def update_metrics(self, insight_id: str, metrics: dict):
            if insight_id in self.storage["insights"]:
                doc = self.storage["insights"][insight_id]
                doc["metrics"] = metrics
                return InsightResponse(**doc)
            return None

        async def get_analytics_summary(self, time_range_hours=24):
            items = list(self.storage["insights"].values())
            insights_by_type = {}
            for item in items:
                at = item.get('analysis_type', 'unknown')
                insights_by_type[at] = insights_by_type.get(at, 0) + 1

            recent_items = sorted(items, key=lambda x: x.get('created_at', datetime.min), reverse=True)[:5]
            recent_responses = [InsightResponse(**i) for i in recent_items]

            return {
                "insights_by_type": insights_by_type,
                "anomalies_detected": 0,
                "avg_processing_time_ms": sum(i.get("metrics", {}).get("processing_time_ms", 0) for i in items) / len(items) if items else 0,
                "confidence_distribution": {"high": 0, "medium": 0, "low": 0},
                "top_sources": [],
                "recent_insights": recent_responses,
            }

        async def initialize(self):
            pass

    repo = MockInsightRepository()

    class MockAppState:
        def __init__(self):
            self.insight_repository = repo
            self.ts_analyzer = TimeSeriesAnalyzer()

            # Mock MCP integration
            mock_mcp = MagicMock()
            mock_mcp.health_check = AsyncMock(return_value={"scout": True, "optimizer": True})
            mock_mcp.initialize = AsyncMock()
            mock_mcp.close = AsyncMock()
            self.mcp_integration = mock_mcp

    app.state.app_state = MockAppState()
    return repo


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_e2e_insight_lifecycle(mock_app_state):
    """Teste E2E: Criar insight → Consultar → Exportar → Deletar."""
    repo = mock_app_state

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Criar insight via API
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
async def test_e2e_timeseries_analysis(mock_app_state):
    """Teste E2E: Buscar série temporal → Detectar anomalias."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
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
async def test_e2e_dashboard_aggregation(mock_app_state):
    """Teste E2E: Criar insights → Ver dashboard agregado."""
    repo = mock_app_state

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

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/analytics/dashboard?time_range=24h")

        assert response.status_code == 200
        data = response.json()
        assert "insights_by_type" in data
        assert "top_sources" in data
        assert "recent_insights" in data
        assert len(data["recent_insights"]) >= 3


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_e2e_mcp_health_check(mock_app_state):
    """Teste E2E: Verificar saúde dos servidores MCP."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/analytics/mcp-health")

        assert response.status_code == 200
        data = response.json()
        assert "scout" in data
        assert "optimizer" in data


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_e2e_metrics_endpoint(mock_app_state):
    """Teste E2E: Verificar endpoint de métricas Prometheus."""
    repo = mock_app_state

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

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/analytics/metrics")

        assert response.status_code == 200
        assert "analyst_insights_total" in response.text
        assert "analyst_processing_time_seconds" in response.text
        assert "text/plain" in response.headers["content-type"]


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_e2e_pagination_and_filters(mock_app_state):
    """Teste E2E: Paginação e filtros de insights."""
    repo = mock_app_state

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

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
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
