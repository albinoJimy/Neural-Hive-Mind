"""
Testes para Active Learning API Router.

TDD: Testes escritos antes da implementação.
Espec: @.agent-os/specs/2026-03-17-active-learning-feedback/
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, testclient

# Import com skip automático se módulo não disponível
router = pytest.importorskip("src.api.routers.active_learning").router


class TestMetricsEndpoint:
    """Testes do endpoint GET /api/v1/active-learning/metrics."""

    @pytest.fixture()
    def mock_balance_analyzer(self):
        """Mock do DatasetBalanceAnalyzer."""
        # Criar um mock com model_dump() funcional
        metrics_data = {
            "total_feedbacks": 484,
            "balance": {
                "approve": {"count": 450, "percentage": 93.0, "gap": 0.0},
                "reject": {"count": 34, "percentage": 7.0, "gap": 26.0},
            },
            "confidence_distribution": {
                "low": {"count": 242, "percentage": 50.0},
                "medium": {"count": 242, "percentage": 50.0},
                "high": {"count": 0, "percentage": 0.0},
            },
            "domain_distribution": {
                "technical": {"count": 120, "percentage": 24.8},
                "security": {"count": 15, "percentage": 3.1, "gap": 16.9},
            },
            "semantic_features_count": 46,
            "semantic_features_percentage": 9.5,
            "priority_recommendations": [{"type": "class", "value": "reject", "gap": 26.0}],
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

        analyzer = MagicMock()
        mock_result = MagicMock()
        mock_result.model_dump.return_value = metrics_data

        # Criar async function para o mock
        async def mock_calculate():
            return mock_result

        analyzer.calculate_balance_metrics = mock_calculate
        return analyzer

    @pytest.mark.asyncio()
    async def test_get_metrics_returns_balance_metrics(self, mock_balance_analyzer):
        """Testa que retorna métricas de balanceamento."""

        app = FastAPI()
        app.include_router(router)

        # Injetar mock
        app.state.balance_analyzer = mock_balance_analyzer

        client = testclient.TestClient(app)
        response = client.get("/api/v1/active-learning/metrics")

        assert response.status_code == 200
        data = response.json()

        assert data["total_feedbacks"] == 484
        assert "balance" in data
        assert "confidence_distribution" in data
        assert "domain_distribution" in data
        assert data["semantic_features_count"] == 46

    @pytest.mark.asyncio()
    async def test_get_metrics_includes_priority_recommendations(self, mock_balance_analyzer):
        """Testa que inclui recomendações de prioridade."""

        app = FastAPI()
        app.include_router(router)
        app.state.balance_analyzer = mock_balance_analyzer

        client = testclient.TestClient(app)
        response = client.get("/api/v1/active-learning/metrics")

        assert response.status_code == 200
        data = response.json()

        assert "priority_recommendations" in data
        assert len(data["priority_recommendations"]) > 0


class TestQueueEndpoint:
    """Testes do endpoint GET /api/v1/active-learning/queue."""

    @pytest.fixture()
    def mock_feedback_queue(self):
        """Mock do PriorityFeedbackQueue."""
        queue = MagicMock()
        queue.get_queue_size.return_value = 12
        queue.get_pending_cases.return_value = [
            {
                "queue_id": "queue-1",
                "plan_id": "plan-1",
                "intent_preview": "Implementar...",
                "information_value": 0.85,
                "priority_reason": "alta incerteza",
                "status": "pending",
            },
            {
                "queue_id": "queue-2",
                "plan_id": "plan-2",
                "intent_preview": "Adicionar...",
                "information_value": 0.72,
                "priority_reason": "domínio raro",
                "status": "pending",
            },
        ]
        return queue

    @pytest.mark.asyncio()
    async def test_get_queue_returns_pending_cases(self, mock_feedback_queue):
        """Testa que retorna casos pendentes da fila."""

        app = FastAPI()
        app.include_router(router)
        app.state.feedback_queue = mock_feedback_queue

        client = testclient.TestClient(app)
        response = client.get("/api/v1/active-learning/queue")

        assert response.status_code == 200
        data = response.json()

        assert data["queue_size"] == 12
        assert "cases" in data
        assert len(data["cases"]) == 2
        assert data["cases"][0]["queue_id"] == "queue-1"

    @pytest.mark.asyncio()
    async def test_get_queue_respects_limit_parameter(self, mock_feedback_queue):
        """Testa que respeita parâmetro limit."""

        app = FastAPI()
        app.include_router(router)
        app.state.feedback_queue = mock_feedback_queue

        client = testclient.TestClient(app)
        response = client.get("/api/v1/active-learning/queue?limit=5")

        assert response.status_code == 200
        mock_feedback_queue.get_pending_cases.assert_called_once_with(limit=5)

    @pytest.mark.asyncio()
    async def test_get_queue_filters_by_status(self, mock_feedback_queue):
        """Testa filtro por status."""

        app = FastAPI()
        app.include_router(router)
        app.state.feedback_queue = mock_feedback_queue

        client = testclient.TestClient(app)
        response = client.get("/api/v1/active-learning/queue?status=pending")

        assert response.status_code == 200


class TestClaimEndpoint:
    """Testes do endpoint POST /api/v1/active-learning/{queue_id}/claim."""

    @pytest.fixture()
    def mock_feedback_queue(self):
        """Mock do PriorityFeedbackQueue."""
        queue = MagicMock()
        queue.claim_case.return_value = {
            "queue_id": "queue-1",
            "status": "in_review",
            "assigned_to": "user@example.com",
            "claimed_at": datetime.now(timezone.utc),
            "expires_at": datetime.now(timezone.utc),
        }
        return queue

    @pytest.mark.asyncio()
    async def test_claim_case_success(self, mock_feedback_queue):
        """Testa claim bem-sucedido."""

        app = FastAPI()
        app.include_router(router)
        app.state.feedback_queue = mock_feedback_queue

        client = testclient.TestClient(app)
        response = client.post(
            "/api/v1/active-learning/queue-1/claim", json={"assigned_to": "user@example.com"}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["queue_id"] == "queue-1"
        assert data["status"] == "in_review"

    @pytest.mark.asyncio()
    async def test_claim_case_not_found(self, mock_feedback_queue):
        """Testa claim de caso inexistente."""
        mock_feedback_queue.claim_case.return_value = None

        app = FastAPI()
        app.include_router(router)
        app.state.feedback_queue = mock_feedback_queue

        client = testclient.TestClient(app)
        response = client.post(
            "/api/v1/active-learning/nonexistent/claim", json={"assigned_to": "user@example.com"}
        )

        assert response.status_code == 404


class TestFeedbackEndpoint:
    """Testes do endpoint POST /api/v1/active-learning/{queue_id}/feedback."""

    @pytest.fixture()
    def mock_feedback_queue(self):
        """Mock do PriorityFeedbackQueue."""
        queue = MagicMock()
        queue.mark_feedback_submitted.return_value = {
            "queue_id": "queue-1",
            "status": "completed",
            "feedback_id": "feedback-1",
        }
        # Mock collection para find_one
        mock_collection = MagicMock()
        mock_collection.find_one.return_value = {"plan_id": "plan-1"}
        queue.collection = mock_collection
        return queue

    @pytest.mark.asyncio()
    async def test_submit_feedback_success(self, mock_feedback_queue):
        """Testa submissão de feedback bem-sucedida."""

        app = FastAPI()
        app.include_router(router)
        app.state.feedback_queue = mock_feedback_queue
        # Mock feedback_collector
        mock_feedback_collector = MagicMock()
        mock_feedback_collector.submit_feedback.return_value = "feedback-1"
        app.state.feedback_collector = mock_feedback_collector

        client = testclient.TestClient(app)
        response = client.post(
            "/api/v1/active-learning/queue-1/feedback",
            json={
                "human_recommendation": "reject",
                "human_rating": 0.2,
                "feedback_notes": "Análise incompleta",
                "submitted_by": "user@example.com",
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert data["queue_id"] == "queue-1"
        assert data["feedback_id"] == "feedback-1"

    @pytest.mark.asyncio()
    async def test_submit_feedback_validates_rating_range(self, mock_feedback_queue):
        """Testa validação do rating (0-1)."""

        app = FastAPI()
        app.include_router(router)
        app.state.feedback_queue = mock_feedback_queue

        client = testclient.TestClient(app)
        response = client.post(
            "/api/v1/active-learning/queue-1/feedback",
            json={
                "human_recommendation": "approve",
                "human_rating": 1.5,  # Inválido
                "submitted_by": "user@example.com",
            },
        )

        assert response.status_code == 422  # Validation error


class TestReleaseEndpoint:
    """Testes do endpoint POST /api/v1/active-learning/{queue_id}/release."""

    @pytest.mark.asyncio()
    async def test_release_case_success(self):
        """Testa liberação bem-sucedida."""
        mock_queue = MagicMock()
        mock_queue.release_case.return_value = {"queue_id": "queue-1", "status": "pending"}

        app = FastAPI()
        app.include_router(router)
        app.state.feedback_queue = mock_queue

        client = testclient.TestClient(app)
        response = client.post("/api/v1/active-learning/queue-1/release")

        assert response.status_code == 200
        data = response.json()

        assert data["queue_id"] == "queue-1"
        assert data["status"] == "pending"
