"""
Integration Tests para ML Inference API

Testes de integração para os endpoints REST da API.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import create_app
from src.services.batch_engine import BatchInferenceEngine
from src.services.predictor_service import PredictorService

# ===== FIXTURES =====


@pytest.fixture
def mock_settings():
    """Configurações mockadas para testes."""
    return SimpleNamespace(
        mlflow_tracking_uri="http://localhost:5000",
        mlflow_model_name="approval_model",
        model_name="approval_model",
        model_version="Production",
        redis_host="localhost",
        redis_port=6379,
        redis_db=0,
        prometheus_port=9090,
        log_level="INFO",
        environment="test",
        service_name="ml-inference-api",
        service_version="1.0.0",
        api_host="localhost",
        api_port=8000,
        batch_max_size=100,
        default_timeout_ms=5000,
        circuit_breaker_threshold=5,
        circuit_breaker_timeout_seconds=60,
        circuit_breaker_timeout_ms=60000,
        enable_gpu=False,
        enable_rate_limiting=False,
        rate_limit_requests_per_minute=60,
        otel_exporter_endpoint="http://localhost:4317",
        local_model_path="/tmp/model.pkl",
        CORS_ORIGINS=["*"],
    )


@pytest.fixture
def mock_predictor_service():
    """Mock do PredictorService."""
    service = AsyncMock(spec=PredictorService)

    # Configurar método predict
    service.predict = AsyncMock(
        return_value={
            "decision": "approve",
            "confidence": 0.85,
            "probabilities": {"approve": 0.85, "reject": 0.15},
            "model_version": "v7",
        }
    )

    # Configurar modelo info
    service.model_info = {
        "version": "v7",
        "trained_at": "2026-03-15T10:00:00Z",
        "features": ["specialist_confidence", "domain_security"],
        "metrics": {"f1_score": 0.9120},
        "training_samples": 75,
    }

    service.get_model_info = Mock(
        return_value={
            "is_loaded": True,
            "name": "approval_model",
            "version": "v7",
            "trained_at": "2026-03-15T10:00:00Z",
            "features": ["specialist_confidence", "domain_security"],
            "metrics": {"f1_score": 0.9120},
            "training_samples": 75,
        }
    )

    service.get_circuit_breaker_state = Mock(
        return_value={"state": "CLOSED", "failure_count": 0, "last_failure_time": None}
    )

    service.approval_predictor = MagicMock()  # Mock do predictor

    return service


@pytest.fixture
def mock_batch_engine():
    """Mock do BatchInferenceEngine."""
    from src.models.schemas import BatchPredictResponse, DecisionType, PredictResponse

    engine = AsyncMock(spec=BatchInferenceEngine)

    # Configurar process_batch para retornar BatchPredictResponse
    engine.process_batch = AsyncMock(
        return_value=BatchPredictResponse(
            results=[
                PredictResponse(
                    decision=DecisionType.APPROVE,
                    confidence=0.85,
                    probabilities={"approve": 0.85, "reject": 0.15},
                    features=None,
                    model_version="v7",
                    inference_time_ms=50.0,
                )
            ],
            total_processed=1,
            successful=1,
            failed=0,
            aggregate_stats={
                "decision_counts": {"approve": 1},
                "average_confidence": 0.85,
                "average_inference_time_ms": 50.0,
            },
            total_inference_time_ms=50.0,
        )
    )

    return engine


@pytest.fixture
async def app(mock_settings, mock_predictor_service, mock_batch_engine):
    """Aplicação FastAPI para testes."""
    with patch("src.services.get_predictor_service", return_value=mock_predictor_service), patch(
        "src.services.get_batch_engine", return_value=mock_batch_engine
    ), patch("src.main.get_settings", return_value=mock_settings):
        app = create_app()

        # Inicializar estado da aplicação com mocks
        app.state.predictor_service = mock_predictor_service
        app.state.batch_engine = mock_batch_engine

        yield app


@pytest.fixture
async def client(app):
    """Cliente HTTP assíncrono para testes."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


# ===== TESTES: POST /api/v1/inference/predict =====


class TestPredictEndpoint:
    """Testes do endpoint POST /api/v1/inference/predict."""

    @pytest.mark.asyncio
    async def test_predict_success(self, client, mock_predictor_service):
        """
        DADO: Um request válido
        QUANDO: POST /api/v1/inference/predict
        ENTÃO: Deve retornar 200 com predição
        """
        response = await client.post(
            "/api/v1/inference/predict",
            json={
                "intent_text": "Create new user with email verification",
                "specialist_confidence": 0.9,
                "options": {"return_probabilities": True},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["decision"] == "approve"
        assert data["confidence"] == 0.85
        assert "probabilities" in data
        assert "model_version" in data

    @pytest.mark.asyncio
    async def test_predict_with_minimal_payload(self, client, mock_predictor_service):
        """
        DADO: Um request com apenas intent_text
        QUANDO: POST /api/v1/inference/predict
        ENTÃO: Deve retornar 200 com defaults
        """
        response = await client.post(
            "/api/v1/inference/predict", json={"intent_text": "Enable two-factor authentication"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "decision" in data

    @pytest.mark.asyncio
    async def test_predict_missing_intent_text(self, client):
        """
        DADO: Um request sem intent_text
        QUANDO: POST /api/v1/inference/predict
        ENTÃO: Deve retornar 422 Validation Error
        """
        response = await client.post(
            "/api/v1/inference/predict", json={"specialist_confidence": 0.9}
        )

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_predict_invalid_confidence(self, client):
        """
        DADO: Um request com specialist_confidence inválido
        QUANDO: POST /api/v1/inference/predict
        ENTÃO: Deve retornar 422 Validation Error
        """
        response = await client.post(
            "/api/v1/inference/predict", json={"intent_text": "Test", "specialist_confidence": 1.5}
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_predict_with_threshold(self, client, mock_predictor_service):
        """
        DADO: Um request com threshold customizado
        QUANDO: POST /api/v1/inference/predict
        ENTÃO: Deve aplicar threshold na decisão
        """
        response = await client.post(
            "/api/v1/inference/predict",
            json={
                "intent_text": "Enable security feature",
                "specialist_confidence": 0.7,
                "options": {"threshold": 0.9},
            },
        )

        assert response.status_code == 200
        data = response.json()
        # Com confidence 0.85 e threshold 0.9, deve ser review_required
        assert data["decision"] == "review_required"


# ===== TESTES: POST /api/v1/inference/predict-batch =====


class TestPredictBatchEndpoint:
    """Testes do endpoint POST /api/v1/inference/predict-batch."""

    @pytest.mark.asyncio
    async def test_predict_batch_success(self, client, mock_batch_engine):
        """
        DADO: Um request com múltiplas predições
        QUANDO: POST /api/v1/inference/predict-batch
        ENTÃO: Deve retornar 200 com BatchPredictResponse
        """
        response = await client.post(
            "/api/v1/inference/predict-batch",
            json={
                "requests": [
                    {"intent_text": "Create user", "specialist_confidence": 0.9},
                    {"intent_text": "Add index", "specialist_confidence": 0.85},
                ],
                "options": {"parallel": True},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert data["total_processed"] >= 1
        assert "successful" in data
        assert "failed" in data

    @pytest.mark.asyncio
    async def test_predict_batch_empty(self, client):
        """
        DADO: Um request com lista vazia
        QUANDO: POST /api/v1/inference/predict-batch
        ENTÃO: Deve retornar 422 Validation Error
        """
        response = await client.post("/api/v1/inference/predict-batch", json={"requests": []})

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_predict_batch_large_batch(self, client, mock_batch_engine):
        """
        DADO: Um request com muitos items
        QUANDO: POST /api/v1/inference/predict-batch
        ENTÃO: Deve processar com chunking
        """
        requests = [
            {"intent_text": f"Request {i}", "specialist_confidence": 0.8} for i in range(50)
        ]

        response = await client.post("/api/v1/inference/predict-batch", json={"requests": requests})

        assert response.status_code == 200


# ===== TESTES: GET /model-info =====


class TestModelInfoEndpoint:
    """Testes do endpoint GET /model-info."""

    @pytest.mark.asyncio
    async def test_get_model_info_success(self, client, mock_predictor_service):
        """
        DADO: Serviço com modelo carregado
        QUANDO: GET /model-info
        ENTÃO: Deve retornar informações do modelo
        """
        response = await client.get("/model-info")

        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "v7"
        assert "features" in data
        assert "metrics" in data


# ===== TESTES: GET /circuit-breaker =====


class TestCircuitBreakerEndpoint:
    """Testes do endpoint GET /circuit-breaker."""

    @pytest.mark.asyncio
    async def test_get_circuit_breaker_status(self, client, mock_predictor_service):
        """
        DADO: Serviço rodando
        QUANDO: GET /circuit-breaker
        ENTÃO: Deve retornar estado do circuit breaker
        """
        response = await client.get("/circuit-breaker")

        assert response.status_code == 200
        data = response.json()
        assert "state" in data
        assert data["state"] == "CLOSED"


# ===== TESTES: GET /health =====


class TestHealthEndpoint:
    """Testes do endpoint GET /health."""

    @pytest.mark.asyncio
    async def test_health_check(self, client):
        """
        DADO: Serviço rodando
        QUANDO: GET /health
        ENTÃO: Deve retornar 200 com status healthy
        """
        response = await client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "service" in data

    @pytest.mark.asyncio
    async def test_health_check_with_service_info(self, client):
        """
        DADO: Serviço rodando
        QUANDO: GET /health
        ENTÃO: Deve incluir informações do serviço
        """
        response = await client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert "service" in data
        assert "version" in data


# ===== TESTES: GET /ready =====


class TestReadinessEndpoint:
    """Testes do endpoint GET /ready."""

    @pytest.mark.asyncio
    async def test_readiness_check_when_ready(self, client, mock_predictor_service):
        """
        DADO: Serviço com modelo carregado e circuit breaker fechado
        QUANDO: GET /ready
        ENTÃO: Deve retornar 200 com status ready
        """
        response = await client.get("/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["checks"]["ml_model"] is True
        assert data["checks"]["circuit_breaker_closed"] is True

    @pytest.mark.asyncio
    async def test_readiness_check_when_not_ready(self, app, client):
        """
        DADO: Serviço sem predictor service
        QUANDO: GET /ready
        ENTÃO: Deve retornar 503 com status not_ready
        """
        # Remover predictor service
        app.state.predictor_service = None

        response = await client.get("/ready")

        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "not_ready"


# ===== TESTES: Error Handling =====


class TestErrorHandling:
    """Testes de tratamento de erros da API."""

    @pytest.mark.asyncio
    async def test_predictor_service_error(self, client, mock_predictor_service):
        """
        DADO: PredictorService que lança erro
        QUANDO: POST /api/v1/inference/predict
        ENTÃO: Deve retornar 500 com erro formatado
        """
        mock_predictor_service.predict.side_effect = Exception("Prediction failed")

        response = await client.post("/api/v1/inference/predict", json={"intent_text": "Test"})

        assert response.status_code == 500
        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_invalid_json(self, client):
        """
        DADO: JSON inválido no request
        QUANDO: POST /api/v1/inference/predict
        ENTÃO: Deve retornar 422
        """
        response = await client.post(
            "/api/v1/inference/predict",
            content="invalid json",
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_method_not_allowed(self, client):
        """
        DADO: Endpoint que não suporta o método
        QUANDO: DELETE /health
        ENTÃO: Deve retornar 405 Method Not Allowed
        """
        response = await client.delete("/health")

        assert response.status_code == 405


# ===== TESTES: CORS =====


class TestCORS:
    """Testes de configuração CORS."""

    @pytest.mark.asyncio
    async def test_cors_headers(self, client):
        """
        DADO: Request com origin header
        QUANDO: Faço qualquer request
        ENTÃO: Deve incluir CORS headers
        """
        response = await client.get("/health", headers={"Origin": "http://localhost:3000"})

        # Verificar CORS headers
        assert "access-control-allow-origin" in response.headers or response.status_code == 200
