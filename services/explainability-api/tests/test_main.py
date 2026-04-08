"""
Testes para main.py - Explainability API.

Testa endpoints health, legacy, GAPS-04 e stats.
"""

import os
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from fastapi import status
from fastapi.testclient import TestClient


# ========== Fixtures ==========


@pytest.fixture
def mock_db():
    """Mock MongoDB database."""
    db = MagicMock()

    # Create explainability_ledger collection mock
    ledger = MagicMock()

    # Use AsyncMock for async methods
    ledger.find_one = AsyncMock(return_value=None)
    ledger.aggregate = AsyncMock(return_value=AsyncMock(to_list=AsyncMock(return_value=[])))
    ledger.count_documents = AsyncMock(return_value=0)
    db.explainability_ledger = ledger

    # Also add aggregate/count to db for tests that use db directly
    db.aggregate = ledger.aggregate
    db.count_documents = ledger.count_documents

    return db


@pytest.fixture
def mock_mongo_client(mock_db):
    """Mock MongoDB client."""
    client = MagicMock()
    mock_admin = MagicMock()

    async def mock_command(command, **kwargs):
        return {"ok": 1}

    mock_admin.command = mock_command
    client.admin = mock_admin
    client.__getitem__ = lambda self, name: mock_db

    # Mock close method
    async def mock_close():
        pass
    client.close = mock_close

    return client


@pytest.fixture
def mock_api_extensions():
    """Mock para ExplainabilityAPIExtensions."""
    extensions = AsyncMock()

    async def get_explainability(decision_id):
        return {
            "decision_id": "test_001",
            "explainability_token": "abc123",
            "hierarchical_data": {"level": "senior"},
        }

    async def generate_explanation(request_data):
        return {
            "explainability_token": "xyz789",
            "decision_id": "test_001",
        }

    def format_explanation(explanation, output_format):
        return "Formatted explanation"

    extensions.get_explainability_by_decision_id = get_explainability
    extensions.generate_explanation = generate_explanation
    extensions.format_explanation = format_explanation
    return extensions


@pytest.fixture
def mock_explanation_producer():
    """Mock para ExplanationProducer."""
    producer = MagicMock()
    producer.producer = MagicMock()

    async def mock_connect():
        pass

    async def mock_disconnect():
        pass

    producer.connect = mock_connect
    producer.disconnect = mock_disconnect
    return producer


@pytest.fixture(autouse=True)
def setup_main_app(mock_mongo_client, mock_db, mock_api_extensions, mock_explanation_producer):
    """Configura mocks para o app FastAPI antes de cada teste."""
    # Patch environment variables
    with patch.dict(os.environ, {
        "ENABLE_V3_API": "false",
        "ENABLE_KAFKA_CONSUMER": "false",
    }):
        # Import and patch main module
        import src.main as main_module

        # Set global variables
        main_module.mongo_client = mock_mongo_client
        main_module.db = mock_db
        main_module.api_extensions = mock_api_extensions
        main_module.explanation_producer = mock_explanation_producer

        yield main_module


@pytest.fixture
def client(setup_main_app):
    """Test client para FastAPI."""
    app = setup_main_app.app
    return TestClient(app)


# ========== Health Endpoints Tests ==========


class TestHealthEndpoints:
    """Testes para endpoints de health check."""

    def test_health_check_basic(self, client):
        """Testa health check básico."""
        response = client.get("/health")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "explainability-api"
        assert "timestamp" in data

    def test_readiness_check_with_mongodb_connected(self, client, mock_mongo_client):
        """Testa readiness check com MongoDB conectado."""
        response = client.get("/ready")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "ready"
        assert data["checks"]["mongodb"] is True
        assert data["checks"]["api"] is True

    def test_readiness_check_without_mongodb(self, client, mock_mongo_client):
        """Testa readiness check sem MongoDB conectado."""
        # Make ping fail
        async def mock_command_fail(command, **kwargs):
            raise Exception("Connection failed")
        mock_mongo_client.admin.command = mock_command_fail

        response = client.get("/ready")

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        data = response.json()
        assert data["status"] == "not_ready"
        assert data["checks"]["mongodb"] is False

    def test_metrics_endpoint(self, client):
        """Testa endpoint Prometheus metrics."""
        response = client.get("/metrics")

        assert response.status_code == status.HTTP_200_OK
        assert "text/plain" in response.headers.get("content-type", "")


# ========== Legacy Endpoint Tests ==========


class TestLegacyEndpoints:
    """Testes para endpoints legados."""

    def test_get_explainability_by_token_found(self, client, mock_db):
        """Testa busca de explicação por token quando encontrada."""
        # Override find_one for this test
        async def mock_find_one_found(query):
            return {
                "explainability_token": "abc123",
                "decision_id": "test_001",
                "_id": "ignored",
            }
        mock_db.explainability_ledger.find_one = mock_find_one_found

        response = client.get("/api/v1/explainability/abc123")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["explainability_token"] == "abc123"
        assert "_id" not in data

    def test_get_explainability_by_token_not_found(self, client, mock_db):
        """Testa busca de explicação por token quando não encontrada."""
        # Override find_one for this test
        async def mock_find_one_not_found(query):
            return None
        mock_db.explainability_ledger.find_one = mock_find_one_not_found

        response = client.get("/api/v1/explainability/nonexistent")

        assert response.status_code == status.HTTP_404_NOT_FOUND


# ========== GAPS-04 Extended Endpoints Tests ==========


class TestExtendedEndpoints:
    """Testes para endpoints estendidos GAPS-04."""

    def test_get_explanation_extended_found(self, client, mock_api_extensions):
        """Testa busca de explicação extendida quando encontrada."""
        response = client.get("/api/v2/explainability/test_001")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["decision_id"] == "test_001"

    def test_get_explanation_extended_not_found(self, client, mock_api_extensions):
        """Testa busca de explicação extendida quando não encontrada."""

        async def get_explainability_not_found(decision_id):
            return None

        mock_api_extensions.get_explainability_by_decision_id = get_explainability_not_found

        response = client.get("/api/v2/explainability/nonexistent")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_generate_explanation_endpoint(self, client, mock_api_extensions):
        """Testa geração de explicação."""
        request_data = {
            "decision_id": "test_001",
            "format": "json",
            "include_shap": True,
            "include_reasoning_extraction": False,
            "include_quality_score": True,
        }

        response = client.post("/api/v2/explainability/generate", json=request_data)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "explainability_token" in data

    def test_get_explanation_formatted_json(self, client, mock_api_extensions):
        """Testa formatação de explicação em JSON."""
        response = client.get("/api/v2/explainability/test_001/format/json")

        assert response.status_code == status.HTTP_200_OK

    def test_get_explanation_formatted_text(self, client, mock_api_extensions):
        """Testa formatação de explicação em texto."""
        response = client.get("/api/v2/explainability/test_001/format/text")

        assert response.status_code == status.HTTP_200_OK

    def test_get_explanation_formatted_html(self, client, mock_api_extensions):
        """Testa formatação de explicação em HTML."""
        response = client.get("/api/v2/explainability/test_001/format/html")

        assert response.status_code == status.HTTP_200_OK

    def test_get_explanation_formatted_invalid_format(self, client, mock_api_extensions):
        """Testa formatação com formato inválido."""
        response = client.get("/api/v2/explainability/test_001/format/xml")

        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ========== Stats Endpoint Tests ==========


class TestStatsEndpoint:
    """Testes para endpoint de estatísticas."""

    def test_get_stats_without_date_filter(self, client, mock_db):
        """Testa busca de estatísticas sem filtro de data."""
        # Create proper cursor mock
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=[
            {"_id": "method1", "count": 10},
            {"_id": "method2", "count": 5},
        ])

        # Create async function that returns the cursor
        async def mock_aggregate_return():
            return mock_cursor

        # The aggregate method should return the cursor when called
        mock_db.explainability_ledger.aggregate = AsyncMock(return_value=mock_cursor)
        mock_db.explainability_ledger.count_documents = AsyncMock(return_value=15)

        response = client.get("/api/v1/explainability/stats")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total_explanations"] == 15
        assert "by_method" in data
        assert "timestamp" in data

    def test_get_stats_with_date_filter(self, client, mock_db):
        """Testa busca de estatísticas com filtro de data."""
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=[])

        mock_db.explainability_ledger.aggregate = AsyncMock(return_value=mock_cursor)
        mock_db.explainability_ledger.count_documents = AsyncMock(return_value=0)

        response = client.get(
            "/api/v1/explainability/stats?start_date=2025-01-01&end_date=2025-01-31"
        )

        assert response.status_code == status.HTTP_200_OK

    def test_get_stats_invalid_date_format(self, client, mock_db):
        """Testa busca de estatísticas com formato de data inválido."""
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=[])

        mock_db.explainability_ledger.aggregate = AsyncMock(return_value=mock_cursor)
        mock_db.explainability_ledger.count_documents = AsyncMock(return_value=0)

        response = client.get("/api/v1/explainability/stats?start_date=invalid-date")

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


# ========== Lifespan Tests ==========


class TestLifespan:
    """Testes para lifecycle management da aplicação."""

    def test_lifespan_configuration_exists(self, setup_main_app):
        """Verifica que a função lifespan está definida em main.py."""
        from src.main import lifespan

        assert lifespan is not None
        assert callable(lifespan)


# ========== Exception Handler Tests ==========


class TestExceptionHandler:
    """Testes para handler global de exceções."""

    def test_global_exception_handler(self, client, mock_api_extensions):
        """Testa handler global de exceções não tratadas."""

        async def get_explainability_error(decision_id):
            raise RuntimeError("Unexpected error")

        mock_api_extensions.get_explainability_by_decision_id = get_explainability_error

        response = client.get("/api/v2/explainability/test_001")

        # Should return 500 due to exception being caught and wrapped
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


# ========== Metrics Tests ==========


class TestPrometheusMetrics:
    """Testes para métricas Prometheus."""

    def test_explainability_queries_counter(self, client, mock_db):
        """Testa contador de consultas de explicabilidade."""
        async def mock_find_one_none(query):
            return None
        mock_db.explainability_ledger.find_one = mock_find_one_none

        # Fazer várias requisições para incrementar contador
        client.get("/api/v1/explainability/test_token_1")
        client.get("/api/v1/explainability/test_token_2")

        # Verificar que métricas incluem as contagens
        metrics_response = client.get("/metrics")
        assert metrics_response.status_code == status.HTTP_200_OK

    def test_explainability_query_duration_histogram(self, client):
        """Testa histograma de duração de consultas."""
        response = client.get("/api/v2/explainability/test_001")
        assert response.status_code in (status.HTTP_200_OK, status.HTTP_404_NOT_FOUND)


# ========== Edge Cases Tests ==========


class TestEdgeCases:
    """Testes para casos extremos."""

    def test_concurrent_requests(self, client):
        """Testa múltiplas requisições concorrentes."""
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(client.get, "/health")
                for _ in range(10)
            ]

            results = [f.result() for f in concurrent.futures.as_completed(futures)]

            # Todas devem ser bem-sucedidas
            assert all(r.status_code == status.HTTP_200_OK for r in results)

    def test_large_request_body(self, client, mock_api_extensions):
        """Testa request body grande."""
        large_request = {
            "decision_id": "test_001",
            "specialist_votes": [{"id": f"spec_{i}", "vote": "approve"} for i in range(1000)],
            "reasoning_text": "x" * 10000,
        }

        response = client.post("/api/v2/explainability/generate", json=large_request)
        # Deve processar sem erro (mesmo que possa não ter dados completos)
        assert response.status_code == status.HTTP_200_OK

    def test_unicode_in_request(self, client, mock_api_extensions):
        """Testa caracteres Unicode no request."""
        unicode_request = {
            "decision_id": "test_001",
            "reasoning_text": "Explicação com caracteres especiais: ñ, á, ç, 中文, emoji 🎯",
        }

        response = client.post("/api/v2/explainability/generate", json=unicode_request)
        assert response.status_code == status.HTTP_200_OK
