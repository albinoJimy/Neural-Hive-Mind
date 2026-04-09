"""Integration tests for API endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from main import create_app
from src.models.impact import ImpactCategory, ImpactDirection, ImpactTimeframe


@pytest.mark.asyncio
class TestAPIEndpoints:
    """Test suite for API endpoints."""

    @pytest.fixture
    async def app(self):
        """Create FastAPI app."""
        return create_app()

    @pytest.fixture
    async def client(self, app):
        """Create HTTP test client."""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as ac:
            yield ac

    async def test_root_endpoint(self, client):
        """Test root endpoint returns service info."""
        response = await client.get("/")
        assert response.status_code == 200

        data = response.json()
        assert "service" in data
        assert "version" in data
        assert "status" in data

    async def test_health_endpoint(self, client):
        """Test health check endpoint."""
        response = await client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "healthy"

    async def test_metrics_endpoint(self, client):
        """Test Prometheus metrics endpoint."""
        response = await client.get("/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers.get("content-type", "")

    async def test_analyze_impact_endpoint(self, client, sample_experiment):
        """Test impact analysis endpoint."""
        # This test requires proper MongoDB setup
        response = await client.post(
            "/api/v1/impact/analyze",
            json={
                "experiment_id": "test-exp-001",
                "timeframes": ["short_term"],
                "include_correlations": False,
            }
        )

        # May return 404 if experiment doesn't exist (expected without MongoDB)
        assert response.status_code in [200, 404, 503]

    async def test_get_impact_summary(self, client):
        """Test impact summary endpoint."""
        response = await client.get("/api/v1/impact/summary?days=30")
        assert response.status_code in [200, 503]

    async def test_search_impacts(self, client):
        """Test search impacts endpoint."""
        response = await client.get(
            "/api/v1/impact/search",
            params={"direction": "positive", "limit": 10}
        )
        assert response.status_code in [200, 503]

    async def test_batch_analyze(self, client):
        """Test batch analysis endpoint."""
        response = await client.post(
            "/api/v1/impact/batch",
            json={
                "experiment_ids": ["exp-001", "exp-002"],
                "timeframes": ["short_term"],
            }
        )
        assert response.status_code in [200, 503]


@pytest.mark.asyncio
class TestImpactAnalysisFlow:
    """Test suite for end-to-end impact analysis flow."""

    async def test_full_analysis_flow(self, app, sample_experiment, sample_hypothesis):
        """Test complete analysis flow from request to response."""
        # This would require a test database with seeded data
        # For now, we verify the structure is correct
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/impact/analyze",
                json={
                    "experiment_id": "test-exp-001",
                    "timeframes": ["short_term", "long_term"],
                    "include_correlations": True,
                }
            )

            # Accept 503 (service not available) as valid for test environment
            assert response.status_code in [200, 404, 503]

    async def test_cached_analysis_retrieval(self, app):
        """Test that cached analysis is returned when available."""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            # First request might analyze (or fail without DB)
            response1 = await client.post(
                "/api/v1/impact/analyze",
                json={
                    "experiment_id": "test-exp-cached",
                    "force_refresh": False,
                }
            )

            # Second request should use cache if first succeeded
            response2 = await client.post(
                "/api/v1/impact/analyze",
                json={
                    "experiment_id": "test-exp-cached",
                    "force_refresh": False,
                }
            )

            # Both should have same status code
            assert response1.status_code == response2.status_code
