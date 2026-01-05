"""Testes de integração para validação de injeção de dependências nas APIs do SLA Management System."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.mark.integration
class TestPoliciesAPIDependencies:
    """Validar que dependências da API de políticas foram configuradas."""

    def test_policies_api_list_with_dependencies(self):
        """Validar que endpoint de listagem funciona com dependências configuradas."""
        from src.api import policies

        # Criar app de teste
        app = FastAPI()
        app.include_router(policies.router)

        # Criar mocks
        mock_pg_client = MagicMock()
        mock_pg_client.list_policies = AsyncMock(return_value=[])

        # Configurar dependency overrides
        app.dependency_overrides[policies.get_postgresql_client] = lambda: mock_pg_client

        client = TestClient(app)
        response = client.get('/api/v1/policies')
        # Com dependências configuradas, deve retornar 200
        assert response.status_code == 200
        assert response.json()['total'] == 0

    def test_policies_api_get_freezes_active_with_dependencies(self):
        """Validar que endpoint de freezes ativos funciona com dependências."""
        from src.api import policies

        # Criar app de teste
        app = FastAPI()
        app.include_router(policies.router)

        # Criar mocks
        mock_enforcer = MagicMock()
        mock_enforcer.get_active_freezes = AsyncMock(return_value=[])

        # Configurar dependency overrides
        app.dependency_overrides[policies.get_policy_enforcer] = lambda: mock_enforcer

        client = TestClient(app)
        response = client.get('/api/v1/policies/freezes/active')
        assert response.status_code == 200

    def test_policies_api_without_dependencies_raises_error(self):
        """Validar que sem dependency overrides retorna erro."""
        from src.api import policies

        # Criar app de teste SEM dependency overrides
        app = FastAPI()
        app.include_router(policies.router)

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get('/api/v1/policies')
        # Sem overrides, a função get_postgresql_client() lançará NotImplementedError
        assert response.status_code == 500


@pytest.mark.integration
class TestDependencyOverridesConfiguration:
    """Validar que dependency overrides são configurados corretamente."""

    def test_policies_dependency_functions_exist(self):
        """Validar que todas as funções de dependency existem."""
        from src.api import policies

        assert callable(policies.get_policy_enforcer)
        assert callable(policies.get_postgresql_client)

    def test_dependency_functions_raise_not_implemented_without_override(self):
        """Validar que funções de dependency lançam NotImplementedError sem override."""
        from src.api import policies

        with pytest.raises(NotImplementedError):
            policies.get_policy_enforcer()

        with pytest.raises(NotImplementedError):
            policies.get_postgresql_client()
