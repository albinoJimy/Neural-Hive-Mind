"""
Testes para servidores HTTP do Behavior Specialist.

Estes testes validam o http_server.py (HTTPServer) e http_server_fastapi.py.
"""

import sys
import os
import pytest
from unittest.mock import MagicMock, patch, Mock
from io import BytesIO

# Configurar path para importar código real
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from src.http_server import HealthHandler, create_http_server
from src.config import BehaviorSpecialistConfig


@pytest.fixture
def mock_specialist():
    """Mock do especialista para testes do servidor HTTP."""
    specialist = MagicMock()
    specialist.specialist_type = "behavior"
    specialist.version = "1.0.0"
    specialist.health_check.return_value = {"status": "SERVING", "details": {}}
    return specialist


@pytest.fixture
def mock_config():
    """Mock da configuração para testes."""
    config = MagicMock()
    config.http_port = 8888
    return config


class TestHealthHandler:
    """Testes do HealthHandler (HTTPServer)."""

    def test_health_handler_initialization(self):
        """Testa inicialização do HealthHandler."""
        handler = HealthHandler(None, None, None)
        assert handler is not None

    def test_health_endpoint(self, mock_specialist, mock_config):
        """Testa endpoint /health."""
        HealthHandler.specialist = mock_specialist
        HealthHandler.config = mock_config

        handler = HealthHandler(None, ("", 0), None)
        handler.request_version = "HTTP/1.1"
        handler.command = "GET"
        handler.path = "/health"

        # Mock response objects
        handler.wfile = BytesIO()
        handler.send_response = MagicMock()
        handler.send_header = MagicMock()
        handler.end_headers = MagicMock()

        handler._handle_health()

        handler.send_response.assert_called_once_with(200)
        handler.send_header.assert_called()

    def test_ready_endpoint_serving(self, mock_specialist, mock_config):
        """Testa endpoint /ready quando serving."""
        HealthHandler.specialist = mock_specialist
        HealthHandler.config = mock_config

        handler = HealthHandler(None, ("", 0), None)
        handler.request_version = "HTTP/1.1"
        handler.command = "GET"
        handler.path = "/ready"

        handler.wfile = BytesIO()
        handler.send_response = MagicMock()
        handler.send_header = MagicMock()
        handler.end_headers = MagicMock()

        handler._handle_ready()

        # Quando serving, deve retornar 200
        handler.send_response.assert_called_once_with(200)

    def test_ready_endpoint_not_serving(self, mock_specialist, mock_config):
        """Testa endpoint /ready quando not serving."""
        mock_specialist.health_check.return_value = {"status": "NOT_SERVING", "details": {}}
        HealthHandler.specialist = mock_specialist
        HealthHandler.config = mock_config

        handler = HealthHandler(None, ("", 0), None)
        handler.request_version = "HTTP/1.1"
        handler.command = "GET"
        handler.path = "/ready"

        handler.wfile = BytesIO()
        handler.send_response = MagicMock()
        handler.send_header = MagicMock()
        handler.end_headers = MagicMock()

        handler._handle_ready()

        # Quando not serving, deve retornar 503
        handler.send_response.assert_called_once_with(503)

    @patch("src.http_server.generate_latest")
    @patch("src.http_server.CONTENT_TYPE_LATEST", "text/plain; version=0.0.4; charset=utf-8")
    def test_metrics_endpoint(self, mock_generate_latest, mock_specialist, mock_config):
        """Testa endpoint /metrics."""
        mock_generate_latest.return_value = b"# HELP test_metric\n"
        HealthHandler.specialist = mock_specialist
        HealthHandler.config = mock_config

        handler = HealthHandler(None, ("", 0), None)
        handler.request_version = "HTTP/1.1"
        handler.command = "GET"
        handler.path = "/metrics"

        handler.wfile = BytesIO()
        handler.send_response = MagicMock()
        handler.send_header = MagicMock()
        handler.end_headers = MagicMock()

        handler._handle_metrics()

        handler.send_response.assert_called_once_with(200)
        mock_generate_latest.assert_called_once()

    def test_not_found_endpoint(self, mock_specialist, mock_config):
        """Testa endpoint não encontrado."""
        HealthHandler.specialist = mock_specialist
        HealthHandler.config = mock_config

        handler = HealthHandler(None, ("", 0), None)
        handler.request_version = "HTTP/1.1"
        handler.command = "GET"
        handler.path = "/notfound"

        handler.send_error = MagicMock()

        handler.do_GET()

        handler.send_error.assert_called_once_with(404, "Not Found")

    def test_log_message_override(self, mock_specialist, mock_config):
        """Testa override de log_message."""
        HealthHandler.specialist = mock_specialist
        HealthHandler.config = mock_config

        handler = HealthHandler(None, ("", 0), None)

        # Não deve lançar exceção
        handler.log_message("Test message %s", "arg")


class TestCreateHttpServer:
    """Testes da função create_http_server."""

    @patch("src.http_server.HTTPServer")
    @patch("src.http_server.structlog.get_logger")
    def test_create_http_server(
        self, mock_logger, mock_http_server_class, mock_specialist, mock_config
    ):
        """Testa criação do servidor HTTP."""
        mock_server_instance = MagicMock()
        mock_http_server_class.return_value = mock_server_instance

        server = create_http_server(mock_specialist, mock_config)

        # Verificar que servidor foi criado
        mock_http_server_class.assert_called_once()
        assert server == mock_server_instance

        # Verificar que handler foi configurado
        assert HealthHandler.specialist == mock_specialist
        assert HealthHandler.config == mock_config

    @patch("src.http_server.HTTPServer")
    @patch("src.http_server.structlog.get_logger")
    def test_http_server_bind_address(
        self, mock_logger, mock_http_server_class, mock_specialist, mock_config
    ):
        """Testa que servidor binda no endereço correto."""
        mock_server_instance = MagicMock()
        mock_http_server_class.return_value = mock_server_instance

        create_http_server(mock_specialist, mock_config)

        # Verificar argumentos de HTTPServer
        call_args = mock_http_server_class.call_args
        assert call_args[0][0] == ("0.0.0.0", mock_config.http_port)
        assert call_args[0][1] == HealthHandler


@pytest.fixture
def mock_specialist_fastapi():
    """Mock do especialista para testes FastAPI."""
    specialist = MagicMock()
    specialist.specialist_type = "behavior"
    specialist.version = "1.0.0"
    specialist.model = None
    specialist.config = MagicMock()
    specialist.config.model_required = False
    specialist.config.enable_feedback_collection = False
    specialist.config.feedback_api_enabled = False
    specialist.config.enable_pii_detection = False
    specialist.health_check.return_value = {"status": "SERVING", "details": {}}
    return specialist


@pytest.fixture
def config_fastapi():
    """Configuração para testes FastAPI."""
    config = BehaviorSpecialistConfig()
    config.http_port = 8889
    config.enable_feedback_collection = False
    config.feedback_api_enabled = False
    config.enable_pii_detection = False
    config.model_required = False
    return config


class TestFastAPIApp:
    """Testes da aplicação FastAPI."""

    @patch("src.http_server_fastapi.FEEDBACK_AVAILABLE", False)
    @patch("src.http_server_fastapi.create_feedback_router")
    @patch("src.http_server_fastapi.structlog.get_logger")
    def test_create_fastapi_app(
        self, mock_logger, mock_feedback_router, mock_specialist_fastapi, config_fastapi
    ):
        """Testa criação da app FastAPI."""
        from src.http_server_fastapi import create_fastapi_app

        app = create_fastapi_app(mock_specialist_fastapi, config_fastapi)

        assert app is not None
        assert app.title == "Behavior Specialist API"
        assert app.version == "1.0.0"
        # Verificar que rotas existem
        routes = [route.path for route in app.routes]
        assert "/health" in routes
        assert "/ready" in routes
        assert "/metrics" in routes
        assert "/status" in routes

    @patch("src.http_server_fastapi.FEEDBACK_AVAILABLE", False)
    @patch("src.http_server_fastapi.structlog.get_logger")
    def test_health_endpoint_returns_200(
        self, mock_logger, mock_specialist_fastapi, config_fastapi
    ):
        """Testa que /health retorna 200."""
        from src.http_server_fastapi import create_fastapi_app
        from fastapi.testclient import TestClient

        app = create_fastapi_app(mock_specialist_fastapi, config_fastapi)
        client = TestClient(app)

        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["specialist_type"] == "behavior"
        assert data["version"] == "1.0.0"

    @patch("src.http_server_fastapi.FEEDBACK_AVAILABLE", False)
    @patch("src.http_server_fastapi.structlog.get_logger")
    def test_ready_endpoint_when_ready(self, mock_logger, mock_specialist_fastapi, config_fastapi):
        """Testa /ready quando pronto."""
        from src.http_server_fastapi import create_fastapi_app
        from fastapi.testclient import TestClient

        app = create_fastapi_app(mock_specialist_fastapi, config_fastapi)
        client = TestClient(app)

        response = client.get("/ready")

        assert response.status_code in [200, 503]
        data = response.json()
        assert "ready" in data

    @patch("src.http_server_fastapi.FEEDBACK_AVAILABLE", False)
    @patch("src.http_server_fastapi.generate_latest")
    @patch("src.http_server_fastapi.structlog.get_logger")
    def test_metrics_endpoint(
        self, mock_logger, mock_generate_latest, mock_specialist_fastapi, config_fastapi
    ):
        """Testa endpoint /metrics."""
        from src.http_server_fastapi import create_fastapi_app
        from fastapi.testclient import TestClient

        mock_generate_latest.return_value = b"# METRIC data\n"

        app = create_fastapi_app(mock_specialist_fastapi, config_fastapi)
        client = TestClient(app)

        response = client.get("/metrics")

        assert response.status_code == 200
        mock_generate_latest.assert_called_once()

    @patch("src.http_server_fastapi.FEEDBACK_AVAILABLE", False)
    @patch("src.http_server_fastapi.structlog.get_logger")
    def test_status_endpoint(self, mock_logger, mock_specialist_fastapi, config_fastapi):
        """Testa endpoint /status."""
        from src.http_server_fastapi import create_fastapi_app
        from fastapi.testclient import TestClient

        app = create_fastapi_app(mock_specialist_fastapi, config_fastapi)
        client = TestClient(app)

        response = client.get("/status")

        assert response.status_code == 200
        data = response.json()
        assert "specialist_type" in data
        assert "version" in data
        assert "status" in data
