"""Configuração e fixtures compartilhadas para testes do Deploy Service."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture()
def mock_settings():
    """Mock Settings object."""
    settings = MagicMock()
    settings.service_name = "deploy-service"
    settings.service_version = "1.0.0"
    settings.environment = "test"
    settings.debug = True

    # Kubernetes settings
    settings.k8s_api_host = "http://localhost:8080"
    settings.k8s_namespace = "nhm"
    settings.k8s_verify_ssl = False

    # API settings
    settings.api_host = "0.0.0.0"
    settings.api_port = 8010

    return settings


@pytest.fixture()
def mock_k8s_client():
    """Mock do cliente Kubernetes."""
    client = AsyncMock()
    client.create_deployment = AsyncMock()
    client.create_service = AsyncMock()
    client.create_ingress = AsyncMock()
    client.get_deployment_status = AsyncMock()
    client.delete_deployment = AsyncMock()
    client.delete_service = AsyncMock()
    client.delete_ingress = AsyncMock()
    return client
