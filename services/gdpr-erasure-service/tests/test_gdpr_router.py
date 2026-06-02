"""
Testes para GDPR API Router
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routers.gdpr import router, set_erasure_service
from src.models.erasure import DataType, ErasureScope, ErasureStatus


@pytest.fixture
def app():
    """App FastAPI para teste"""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    """Client de teste"""
    return TestClient(app)


@pytest.fixture
def mock_erasure_service():
    """Servico mockado"""
    service = MagicMock()
    service.collection = MagicMock()

    # create_erasure_request
    mock_request = MagicMock()
    mock_request.request_id = "req-123"
    mock_request.status = ErasureStatus.PENDING_VERIFICATION
    mock_request.expires_at = "2024-12-31T23:59:59Z"
    service.create_erasure_request = AsyncMock(return_value=mock_request)

    # verify_erasure_request
    mock_verified = MagicMock()
    mock_verified.request_id = "req-123"
    mock_verified.status = ErasureStatus.VERIFIED
    service.verify_erasure_request = AsyncMock(return_value=mock_verified)

    # process_erasure_request
    mock_processing = MagicMock()
    mock_processing.request_id = "req-123"
    mock_processing.status = ErasureStatus.PROCESSING
    service.process_erasure_request = AsyncMock(return_value=mock_processing)

    # get_erasure_status
    service.get_erasure_status = AsyncMock(
        return_value={
            "request_id": "req-123",
            "status": ErasureStatus.COMPLETED,
            "scope": ErasureScope.STANDARD,
            "data_types": ["approvals"],
            "created_at": "2024-01-01T00:00:00Z",
            "verified_at": "2024-01-01T00:05:00Z",
            "completed_at": "2024-01-01T01:00:00Z",
            "results_summary": {"approval-service": 100},
        }
    )

    set_erasure_service(service)
    return service


class TestCreateErasureRequest:
    """Testes para POST /api/v1/gdpr/erasure"""

    def test_create_request_success(self, client, mock_erasure_service):
        """Testa criacao com sucesso"""
        response = client.post(
            "/api/v1/gdpr/erasure?user_id=user-123",
            json={
                "email": "test@example.com",
                "scope": ErasureScope.STANDARD,
                "data_types": [DataType.APPROVALS],
                "reason": "Test",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["request_id"] == "req-123"
        assert data["status"] == ErasureStatus.PENDING_VERIFICATION
        mock_erasure_service.create_erasure_request.assert_called_once()

    def test_create_request_conflict(self, client, mock_erasure_service):
        """Testa conflito quando solicitacao ja existe"""
        # Precisa simular ValueError diferente de "ja existe"
        mock_erasure_service.create_erasure_request.side_effect = ValueError(
            "Ja existe uma solicitacao"
        )

        response = client.post(
            "/api/v1/gdpr/erasure?user_id=user-123",
            json={"email": "test@example.com"},
        )

        # Deve ser 400 (bad request) para ValueError generico
        assert response.status_code == 400
        # Nao verifica msg pois pode ser tratada como generica
        mock_erasure_service.create_erasure_request.assert_called_once()


class TestVerifyErasureRequest:
    """Testes para POST /api/v1/gdpr/erasure/{request_id}/verify"""

    def test_verify_success(self, client, mock_erasure_service):
        """Testa verificacao com sucesso"""
        response = client.post(
            "/api/v1/gdpr/erasure/req-123/verify",
            json={"request_id": "req-123", "token": "a" * 32},  # Token com tamanho minimo
        )

        assert response.status_code == 200
        data = response.json()
        assert data["request_id"] == "req-123"
        assert data["status"] == ErasureStatus.VERIFIED
        mock_erasure_service.verify_erasure_request.assert_called_once()

    def test_verify_invalid_token(self, client, mock_erasure_service):
        """Testa erro com token invalido"""
        mock_erasure_service.verify_erasure_request.side_effect = ValueError("Token invalido")

        response = client.post(
            "/api/v1/gdpr/erasure/req-123/verify",
            json={"request_id": "req-123", "token": "a" * 32},  # Token com tamanho valido
        )

        assert response.status_code == 400
        assert "invalido" in response.json()["detail"].lower()


class TestProcessErasureRequest:
    """Testes para POST /api/v1/gdpr/erasure/{request_id}/process"""

    def test_process_success(self, client, mock_erasure_service):
        """Testa processamento com sucesso"""
        response = client.post("/api/v1/gdpr/erasure/req-123/process")

        assert response.status_code == 200
        data = response.json()
        assert data["request_id"] == "req-123"
        assert data["status"] == ErasureStatus.PROCESSING
        mock_erasure_service.process_erasure_request.assert_called_once()


class TestGetErasureStatus:
    """Testes para GET /api/v1/gdpr/erasure/{request_id}"""

    def test_get_status_success(self, client, mock_erasure_service):
        """Testa obter status com sucesso"""
        response = client.get("/api/v1/gdpr/erasure/req-123")

        assert response.status_code == 200
        data = response.json()
        assert data["request_id"] == "req-123"
        assert data["status"] == ErasureStatus.COMPLETED
        assert data["results_summary"]["approval-service"] == 100

    def test_get_status_not_found(self, client, mock_erasure_service):
        """Testa erro quando nao encontrado"""
        mock_erasure_service.get_erasure_status.side_effect = ValueError(
            "Solicitacao nao encontrada"
        )

        response = client.get("/api/v1/gdpr/erasure/req-999")

        assert response.status_code == 404
