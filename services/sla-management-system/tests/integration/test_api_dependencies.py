"""Testes de integração para validação de injeção de dependências nas APIs do SLA Management System."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.mark.integration
class TestSLOsAPIDependencies:
    """Validar que dependências da API de SLOs foram configuradas."""

    def test_slos_api_list_with_dependencies(self):
        """Validar que endpoint de listagem funciona com dependências."""
        from src.api import slos

        app = FastAPI()
        app.include_router(slos.router)

        mock_manager = MagicMock()
        mock_manager.list_slos = AsyncMock(return_value=[])

        app.dependency_overrides[slos.get_slo_manager] = lambda: mock_manager

        client = TestClient(app)
        response = client.get('/api/v1/slos')
        assert response.status_code == 200
        assert response.json()['total'] == 0

    def test_slos_api_get_with_dependencies(self):
        """Validar que endpoint de busca funciona com dependências."""
        from src.api import slos
        from src.models.slo_definition import SLODefinition, SLIQuery, SLOType

        app = FastAPI()
        app.include_router(slos.router)

        mock_slo = SLODefinition(
            slo_id='slo-123',
            name='Test SLO',
            description='Test',
            slo_type=SLOType.AVAILABILITY,
            service_name='test-service',
            layer='application',
            target=0.999,
            window_days=30,
            sli_query=SLIQuery(
                metric_name='test_metric',
                query='up{job="test"}',
                aggregation='avg'
            ),
            enabled=True
        )
        mock_manager = MagicMock()
        mock_manager.get_slo = AsyncMock(return_value=mock_slo)

        app.dependency_overrides[slos.get_slo_manager] = lambda: mock_manager

        client = TestClient(app)
        response = client.get('/api/v1/slos/slo-123')
        assert response.status_code == 200
        assert response.json()['slo_id'] == 'slo-123'

    def test_slos_api_without_dependencies_raises_error(self):
        """Validar que sem dependency overrides retorna erro 503 (serviço não inicializado)."""
        from src.api import slos

        app = FastAPI()
        app.include_router(slos.router)

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get('/api/v1/slos')
        assert response.status_code == 503
        assert "não inicializado" in response.json()["detail"]


@pytest.mark.integration
class TestBudgetsAPIDependencies:
    """Validar que dependências da API de budgets foram configuradas."""

    def test_budgets_api_get_with_dependencies(self):
        """Validar que endpoint de busca funciona com dependências."""
        from src.api import budgets
        from src.models.error_budget import ErrorBudget, BudgetStatus

        app = FastAPI()
        app.include_router(budgets.router)

        mock_budget = ErrorBudget(
            slo_id='slo-123',
            service_name='test-service',
            calculated_at=datetime.utcnow(),
            window_start=datetime.utcnow(),
            window_end=datetime.utcnow(),
            sli_value=0.999,
            slo_target=0.999,
            error_budget_total=0.1,
            error_budget_consumed=0.05,
            error_budget_remaining=50.0,
            status=BudgetStatus.HEALTHY,
            burn_rates=[]
        )
        mock_calculator = MagicMock()
        mock_calculator.get_budget = AsyncMock(return_value=mock_budget)

        app.dependency_overrides[budgets.get_budget_calculator] = lambda: mock_calculator

        client = TestClient(app)
        response = client.get('/api/v1/budgets/slo-123')
        assert response.status_code == 200
        assert response.json()['slo_id'] == 'slo-123'

    def test_budgets_api_list_with_dependencies(self):
        """Validar que endpoint de listagem funciona com dependências."""
        from src.api import budgets

        app = FastAPI()
        app.include_router(budgets.router)

        mock_pg_client = MagicMock()
        mock_pg_client.list_slos = AsyncMock(return_value=[])

        app.dependency_overrides[budgets.get_postgresql_client] = lambda: mock_pg_client

        client = TestClient(app)
        response = client.get('/api/v1/budgets')
        assert response.status_code == 200
        assert response.json()['total'] == 0

    def test_budgets_api_without_dependencies_raises_error(self):
        """Validar que sem dependency overrides retorna erro 503 (serviço não inicializado)."""
        from src.api import budgets

        app = FastAPI()
        app.include_router(budgets.router)

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get('/api/v1/budgets/slo-123')
        assert response.status_code == 503
        assert "não inicializado" in response.json()["detail"]


@pytest.mark.integration
class TestWebhooksAPIDependencies:
    """Validar que dependências da API de webhooks foram configuradas."""

    def test_webhooks_api_alertmanager_with_dependencies(self):
        """Validar que webhook do Alertmanager funciona com dependências."""
        from src.api import webhooks

        app = FastAPI()
        app.include_router(webhooks.router)

        mock_slo_manager = MagicMock()
        mock_slo_manager.list_slos = AsyncMock(return_value=[])

        mock_calculator = MagicMock()
        mock_enforcer = MagicMock()
        mock_pg_client = MagicMock()

        app.dependency_overrides[webhooks.get_slo_manager] = lambda: mock_slo_manager
        app.dependency_overrides[webhooks.get_budget_calculator] = lambda: mock_calculator
        app.dependency_overrides[webhooks.get_policy_enforcer] = lambda: mock_enforcer
        app.dependency_overrides[webhooks.get_postgresql_client] = lambda: mock_pg_client

        client = TestClient(app)
        response = client.post('/webhooks/alertmanager', json={
            'version': '4',
            'groupKey': 'test',
            'status': 'firing',
            'receiver': 'test',
            'groupLabels': {},
            'commonLabels': {},
            'commonAnnotations': {},
            'externalURL': 'http://test',
            'alerts': []
        })
        assert response.status_code == 200
        assert response.json()['alerts_processed'] == 0

    def test_webhooks_api_without_dependencies_raises_error(self):
        """Validar que sem dependency overrides retorna erro 503 (serviço não inicializado)."""
        from src.api import webhooks

        app = FastAPI()
        app.include_router(webhooks.router)

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post('/webhooks/alertmanager', json={
            'version': '4',
            'groupKey': 'test',
            'status': 'firing',
            'receiver': 'test',
            'groupLabels': {},
            'commonLabels': {},
            'commonAnnotations': {},
            'externalURL': 'http://test',
            'alerts': []
        })
        assert response.status_code == 503
        assert "não inicializado" in response.json()["detail"]


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
        """Validar que sem dependency overrides retorna erro 503 (serviço não inicializado)."""
        from src.api import policies

        # Criar app de teste SEM dependency overrides
        app = FastAPI()
        app.include_router(policies.router)

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get('/api/v1/policies')
        # Sem overrides, a função get_postgresql_client() lançará HTTPException 503
        assert response.status_code == 503
        assert "não inicializado" in response.json()["detail"]


@pytest.mark.integration
class TestDependencyOverridesConfiguration:
    """Validar que dependency overrides são configurados corretamente."""

    def test_policies_dependency_functions_exist(self):
        """Validar que todas as funções de dependency existem."""
        from src.api import policies

        assert callable(policies.get_policy_enforcer)
        assert callable(policies.get_postgresql_client)

    def test_dependency_functions_raise_http_exception_without_override(self):
        """Validar que funções de dependency lançam HTTPException 503 sem override."""
        from src.api import policies
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            policies.get_policy_enforcer()
        assert exc_info.value.status_code == 503
        assert "não inicializado" in exc_info.value.detail

        with pytest.raises(HTTPException) as exc_info:
            policies.get_postgresql_client()
        assert exc_info.value.status_code == 503
        assert "não inicializado" in exc_info.value.detail
