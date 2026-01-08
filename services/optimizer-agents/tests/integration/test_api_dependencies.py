"""Testes de integração para validação de injeção de dependências nas APIs."""

import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Mock neural_hive_integration e outras dependências ausentes antes de qualquer importação
mock_neural_hive = MagicMock()
mock_neural_hive.proto_stubs = MagicMock()
mock_neural_hive.proto_stubs.service_registry_pb2 = MagicMock()
mock_neural_hive.proto_stubs.service_registry_pb2_grpc = MagicMock()
sys.modules['neural_hive_integration'] = mock_neural_hive
sys.modules['neural_hive_integration.proto_stubs'] = mock_neural_hive.proto_stubs
sys.modules['neural_hive_integration.proto_stubs.service_registry_pb2'] = mock_neural_hive.proto_stubs.service_registry_pb2
sys.modules['neural_hive_integration.proto_stubs.service_registry_pb2_grpc'] = mock_neural_hive.proto_stubs.service_registry_pb2_grpc

# Mock neural_hive_ml e submodules
mock_neural_hive_ml = MagicMock()
mock_neural_hive_ml.predictive_models = MagicMock()
mock_neural_hive_ml.predictive_models.LoadPredictor = MagicMock()
mock_neural_hive_ml.predictive_models.model_registry = MagicMock()
mock_neural_hive_ml.predictive_models.model_registry.ModelRegistry = MagicMock()
sys.modules['neural_hive_ml'] = mock_neural_hive_ml
sys.modules['neural_hive_ml.predictive_models'] = mock_neural_hive_ml.predictive_models
sys.modules['neural_hive_ml.predictive_models.model_registry'] = mock_neural_hive_ml.predictive_models.model_registry

# Mock prophet
mock_prophet = MagicMock()
mock_prophet.Prophet = MagicMock()
sys.modules['prophet'] = mock_prophet

# Mock statsmodels
mock_statsmodels = MagicMock()
mock_statsmodels.tsa = MagicMock()
mock_statsmodels.tsa.arima = MagicMock()
mock_statsmodels.tsa.arima.model = MagicMock()
mock_statsmodels.tsa.arima.model.ARIMA = MagicMock()
sys.modules['statsmodels'] = mock_statsmodels
sys.modules['statsmodels.tsa'] = mock_statsmodels.tsa
sys.modules['statsmodels.tsa.arima'] = mock_statsmodels.tsa.arima
sys.modules['statsmodels.tsa.arima.model'] = mock_statsmodels.tsa.arima.model

# Mock holidays
mock_holidays = MagicMock()
sys.modules['holidays'] = mock_holidays

# Mock sklearn
mock_sklearn = MagicMock()
mock_sklearn.preprocessing = MagicMock()
mock_sklearn.preprocessing.StandardScaler = MagicMock()
mock_sklearn.preprocessing.MinMaxScaler = MagicMock()
mock_sklearn.model_selection = MagicMock()
mock_sklearn.model_selection.train_test_split = MagicMock()
sys.modules['sklearn'] = mock_sklearn
sys.modules['sklearn.preprocessing'] = mock_sklearn.preprocessing
sys.modules['sklearn.model_selection'] = mock_sklearn.model_selection

# Mock torch and transformers
mock_torch = MagicMock()
mock_torch.nn = MagicMock()
mock_torch.nn.Module = type('Module', (), {})
mock_torch.cuda = MagicMock()
mock_torch.cuda.is_available = MagicMock(return_value=False)
sys.modules['torch'] = mock_torch
sys.modules['torch.nn'] = mock_torch.nn

mock_transformers = MagicMock()
sys.modules['transformers'] = mock_transformers

# Mock mlflow completo
mock_mlflow = MagicMock()
mock_mlflow.entities = MagicMock()
mock_mlflow.entities.Metric = MagicMock()
mock_mlflow.entities.Param = MagicMock()
mock_mlflow.tracking = MagicMock()
mock_mlflow.tracking.MlflowClient = MagicMock()
mock_mlflow.MlflowClient = MagicMock()
sys.modules['mlflow'] = mock_mlflow
sys.modules['mlflow.entities'] = mock_mlflow.entities
sys.modules['mlflow.tracking'] = mock_mlflow.tracking

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
            'optimization_type': 'WEIGHT_RECALIBRATION',
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
            'experiment_type': 'A_B_TEST',
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


@pytest.mark.integration
class TestHealthChecksDependencies:
    """Validar que health checks verificam as dependências corretamente."""

    def test_readiness_check_with_all_connected(self):
        """Validar que readiness retorna ready quando todos os clients estão conectados."""
        from src.api import health
        from src import main as app_main

        # Criar app de teste
        app = FastAPI()
        app.include_router(health.router)

        # Mock dos clients globais
        mock_mongodb = MagicMock()
        mock_mongodb.client = MagicMock()

        mock_redis = MagicMock()
        mock_redis.client = MagicMock()
        mock_redis.client.ping = AsyncMock(return_value=True)

        mock_insights_consumer = MagicMock()
        mock_optimization_producer = MagicMock()

        mock_consensus_client = MagicMock()
        mock_consensus_client.channel = MagicMock()

        mock_orchestrator_client = MagicMock()
        mock_orchestrator_client.channel = MagicMock()

        # Simular clients globais no módulo main
        original_mongodb = getattr(app_main, 'mongodb_client', None)
        original_redis = getattr(app_main, 'redis_client', None)
        original_insights = getattr(app_main, 'insights_consumer', None)
        original_producer = getattr(app_main, 'optimization_producer', None)
        original_consensus = getattr(app_main, 'consensus_engine_client', None)
        original_orchestrator = getattr(app_main, 'orchestrator_client', None)

        try:
            app_main.mongodb_client = mock_mongodb
            app_main.redis_client = mock_redis
            app_main.insights_consumer = mock_insights_consumer
            app_main.optimization_producer = mock_optimization_producer
            app_main.consensus_engine_client = mock_consensus_client
            app_main.orchestrator_client = mock_orchestrator_client

            client = TestClient(app)
            response = client.get('/health/ready')

            assert response.status_code == 200
            data = response.json()
            assert data['ready'] is True
            assert data['status'] == 'ready'
            assert data['checks']['mongodb'] == 'connected'
            assert data['checks']['redis'] == 'connected'
        finally:
            # Restaurar originais
            app_main.mongodb_client = original_mongodb
            app_main.redis_client = original_redis
            app_main.insights_consumer = original_insights
            app_main.optimization_producer = original_producer
            app_main.consensus_engine_client = original_consensus
            app_main.orchestrator_client = original_orchestrator

    def test_readiness_check_with_disconnected_mongodb(self):
        """Validar que readiness retorna not_ready quando MongoDB está desconectado."""
        from src.api import health
        from src import main as app_main

        app = FastAPI()
        app.include_router(health.router)

        # Mock apenas dos clients conectados
        mock_redis = MagicMock()
        mock_redis.client = MagicMock()
        mock_redis.client.ping = AsyncMock(return_value=True)

        mock_insights_consumer = MagicMock()
        mock_optimization_producer = MagicMock()

        mock_consensus_client = MagicMock()
        mock_consensus_client.channel = MagicMock()

        mock_orchestrator_client = MagicMock()
        mock_orchestrator_client.channel = MagicMock()

        original_mongodb = getattr(app_main, 'mongodb_client', None)
        original_redis = getattr(app_main, 'redis_client', None)
        original_insights = getattr(app_main, 'insights_consumer', None)
        original_producer = getattr(app_main, 'optimization_producer', None)
        original_consensus = getattr(app_main, 'consensus_engine_client', None)
        original_orchestrator = getattr(app_main, 'orchestrator_client', None)

        try:
            # MongoDB desconectado (None)
            app_main.mongodb_client = None
            app_main.redis_client = mock_redis
            app_main.insights_consumer = mock_insights_consumer
            app_main.optimization_producer = mock_optimization_producer
            app_main.consensus_engine_client = mock_consensus_client
            app_main.orchestrator_client = mock_orchestrator_client

            client = TestClient(app)
            response = client.get('/health/ready')

            assert response.status_code == 200
            data = response.json()
            assert data['ready'] is False
            assert data['status'] == 'not_ready'
            assert data['checks']['mongodb'] == 'disconnected'
        finally:
            app_main.mongodb_client = original_mongodb
            app_main.redis_client = original_redis
            app_main.insights_consumer = original_insights
            app_main.optimization_producer = original_producer
            app_main.consensus_engine_client = original_consensus
            app_main.orchestrator_client = original_orchestrator

    def test_health_check_liveness(self):
        """Validar que liveness check sempre retorna alive."""
        from src.api import health

        app = FastAPI()
        app.include_router(health.router)

        client = TestClient(app)
        response = client.get('/health/live')

        assert response.status_code == 200
        assert response.json()['status'] == 'alive'

    def test_health_check_basic(self):
        """Validar que health check básico retorna healthy."""
        from src.api import health

        app = FastAPI()
        app.include_router(health.router)

        client = TestClient(app)
        response = client.get('/health')

        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'healthy'
        assert 'service' in data
        assert 'version' in data
