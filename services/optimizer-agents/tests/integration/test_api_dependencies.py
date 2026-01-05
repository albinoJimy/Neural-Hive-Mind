"""Testes de integração para validação de injeção de dependências nas APIs."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.mark.integration
class TestOptimizationsAPIDependencies:
    """Validar que dependências da API de otimizações foram configuradas."""

    def test_optimizations_api_list_with_dependencies(self):
        """Validar que endpoint de listagem funciona com dependências configuradas."""
        from src.api import optimizations

        # Criar app de teste
        app = FastAPI()
        app.include_router(optimizations.router)

        # Criar mocks
        mock_mongodb = MagicMock()
        mock_mongodb.list_optimizations = AsyncMock(return_value=[])

        # Configurar dependency overrides
        app.dependency_overrides[optimizations.get_mongodb_client] = lambda: mock_mongodb

        client = TestClient(app)
        response = client.get('/api/v1/optimizations')
        # Com dependências configuradas, deve retornar 200
        assert response.status_code == 200

    def test_optimizations_api_statistics_with_dependencies(self):
        """Validar que endpoint de estatísticas funciona com dependências."""
        from src.api import optimizations

        # Criar app de teste
        app = FastAPI()
        app.include_router(optimizations.router)

        # Criar mocks
        mock_mongodb = MagicMock()
        mock_mongodb.list_optimizations = AsyncMock(return_value=[])

        # Configurar dependency overrides
        app.dependency_overrides[optimizations.get_mongodb_client] = lambda: mock_mongodb

        client = TestClient(app)
        response = client.get('/api/v1/optimizations/statistics/summary')
        assert response.status_code == 200

    def test_optimizations_api_trigger_with_dependencies(self):
        """Validar que endpoint de trigger funciona com dependências."""
        from src.api import optimizations

        # Criar app de teste
        app = FastAPI()
        app.include_router(optimizations.router)

        # Criar mocks
        mock_weight_recal = MagicMock()
        mock_optimization_event = MagicMock()
        mock_optimization_event.optimization_id = 'test-opt-123'
        mock_weight_recal.apply_weight_recalibration = AsyncMock(return_value=mock_optimization_event)

        mock_slo_adjuster = MagicMock()

        # Configurar dependency overrides
        app.dependency_overrides[optimizations.get_weight_recalibrator] = lambda: mock_weight_recal
        app.dependency_overrides[optimizations.get_slo_adjuster] = lambda: mock_slo_adjuster

        client = TestClient(app)
        response = client.post('/api/v1/optimizations/trigger', json={
            'target_component': 'test-component',
            'optimization_type': 'weight_recalibration',
            'justification': 'Test justification',
            'proposed_adjustments': [{'key': 'value'}]
        })
        assert response.status_code == 200
        assert response.json()['optimization_id'] == 'test-opt-123'

    def test_optimizations_api_without_dependencies_raises_error(self):
        """Validar que sem dependency overrides retorna erro."""
        from src.api import optimizations

        # Criar app de teste SEM dependency overrides
        app = FastAPI()
        app.include_router(optimizations.router)

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get('/api/v1/optimizations')
        # Sem overrides, a função get_mongodb_client() lançará NotImplementedError
        assert response.status_code == 500


@pytest.mark.integration
class TestExperimentsAPIDependencies:
    """Validar que dependências da API de experimentos foram configuradas."""

    def test_experiments_api_list_with_dependencies(self):
        """Validar que endpoint de listagem funciona com dependências configuradas."""
        from src.api import experiments

        # Criar app de teste
        app = FastAPI()
        app.include_router(experiments.router)

        # Criar mocks
        mock_mongodb = MagicMock()
        mock_mongodb.list_experiments = AsyncMock(return_value=[])

        # Configurar dependency overrides
        app.dependency_overrides[experiments.get_mongodb_client] = lambda: mock_mongodb

        client = TestClient(app)
        response = client.get('/api/v1/experiments')
        # Com dependências configuradas, deve retornar 200
        assert response.status_code == 200

    def test_experiments_api_statistics_with_dependencies(self):
        """Validar que endpoint de estatísticas funciona com dependências."""
        from src.api import experiments

        # Criar app de teste
        app = FastAPI()
        app.include_router(experiments.router)

        # Criar mocks
        mock_mongodb = MagicMock()

        # Configurar dependency overrides
        app.dependency_overrides[experiments.get_mongodb_client] = lambda: mock_mongodb

        client = TestClient(app)
        response = client.get('/api/v1/experiments/statistics/summary')
        assert response.status_code == 200

    def test_experiments_api_submit_with_dependencies(self):
        """Validar que endpoint de submit funciona com dependências."""
        from src.api import experiments

        # Criar app de teste
        app = FastAPI()
        app.include_router(experiments.router)

        # Criar mocks
        mock_manager = MagicMock()
        mock_manager.submit_experiment = AsyncMock(return_value='exp-123')

        # Configurar dependency overrides
        app.dependency_overrides[experiments.get_experiment_manager] = lambda: mock_manager

        client = TestClient(app)
        response = client.post('/api/v1/experiments/submit', json={
            'experiment_type': 'ab_test',
            'hypothesis': {'target_component': 'test'},
            'objective': 'Test objective',
            'baseline_configuration': {},
            'experimental_configuration': {},
            'success_criteria': [],
            'guardrails': [],
        })
        assert response.status_code == 200
        assert response.json()['experiment_id'] == 'exp-123'

    def test_experiments_api_without_dependencies_raises_error(self):
        """Validar que sem dependency overrides retorna erro."""
        from src.api import experiments

        # Criar app de teste SEM dependency overrides
        app = FastAPI()
        app.include_router(experiments.router)

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get('/api/v1/experiments')
        # Sem overrides, a função get_mongodb_client() lançará NotImplementedError
        assert response.status_code == 500


@pytest.mark.integration
class TestDependencyOverridesConfiguration:
    """Validar que dependency overrides são configurados corretamente no startup."""

    def test_optimizations_dependency_functions_exist(self):
        """Validar que todas as funções de dependency existem."""
        from src.api import optimizations

        assert callable(optimizations.get_mongodb_client)
        assert callable(optimizations.get_redis_client)
        assert callable(optimizations.get_optimization_engine)
        assert callable(optimizations.get_weight_recalibrator)
        assert callable(optimizations.get_slo_adjuster)

    def test_experiments_dependency_functions_exist(self):
        """Validar que todas as funções de dependency existem."""
        from src.api import experiments

        assert callable(experiments.get_mongodb_client)
        assert callable(experiments.get_experiment_manager)

    def test_dependency_functions_raise_not_implemented_without_override(self):
        """Validar que funções de dependency lançam NotImplementedError sem override."""
        from src.api import optimizations, experiments

        with pytest.raises(NotImplementedError):
            optimizations.get_mongodb_client()

        with pytest.raises(NotImplementedError):
            experiments.get_mongodb_client()
