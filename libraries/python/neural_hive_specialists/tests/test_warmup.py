"""
Testes para warmup de especialistas.
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock

from neural_hive_specialists.config import SpecialistConfig
from neural_hive_specialists.base_specialist import BaseSpecialist


class MockSpecialist(BaseSpecialist):
    """Especialista mock para testes."""

    def _get_specialist_type(self) -> str:
        return 'test'

    def _load_model(self):
        return Mock(name='MockModel')

    def _evaluate_plan_internal(self, cognitive_plan, context):
        return {
            'confidence_score': 0.85,
            'risk_score': 0.15,
            'recommendation': 'approve',
            'reasoning_summary': 'Test evaluation',
            'reasoning_factors': [],
            'metadata': {}
        }


@pytest.fixture
def specialist_config():
    """Configuração mock para testes."""
    return SpecialistConfig(
        specialist_type='test',
        service_name='test-specialist',
        mlflow_tracking_uri='http://localhost:5000',
        mlflow_experiment_name='test',
        mlflow_model_name='test-model',
        mongodb_uri='mongodb://localhost:27017',
        redis_cluster_nodes='localhost:6379',
        neo4j_uri='bolt://localhost:7687',
        neo4j_password='test',
        warmup_enabled=True,
        warmup_on_startup=True,
        opinion_cache_enabled=False,
        enable_drift_monitoring=False
    )


@pytest.fixture
def specialist(specialist_config):
    """Especialista mock para testes."""
    with patch('neural_hive_specialists.base_specialist.MLflowClient'):
        with patch('neural_hive_specialists.base_specialist.LedgerClient'):
            with patch('neural_hive_specialists.base_specialist.FeatureStore'):
                return MockSpecialist(specialist_config)


class TestWarmupSuccess:
    """Testes de warmup bem-sucedido."""

    def test_warmup_loads_model(self, specialist):
        """Testa que warmup carrega o modelo."""
        specialist.model = None

        result = specialist.warmup()

        assert result['status'] == 'success'
        assert specialist.model is not None
        assert result['model_loaded'] is True

    def test_warmup_with_model_already_loaded(self, specialist):
        """Testa warmup quando modelo já está carregado."""
        specialist.model = Mock(name='PreloadedModel')

        result = specialist.warmup()

        assert result['status'] == 'success'
        assert result['model_loaded'] is True

    def test_warmup_executes_dummy_evaluation(self, specialist):
        """Testa que warmup executa avaliação dummy."""
        specialist.evaluate_plan = Mock(return_value={'opinion_id': 'warmup-opinion'})

        result = specialist.warmup()

        assert result['status'] == 'success'
        specialist.evaluate_plan.assert_called_once()

        # Verificar que request dummy foi criado
        call_args = specialist.evaluate_plan.call_args[0][0]
        assert call_args.plan_id == 'warmup-dummy'
        assert call_args.intent_id == 'warmup-intent'

    def test_warmup_returns_duration(self, specialist):
        """Testa que warmup retorna duração."""
        result = specialist.warmup()

        assert 'duration_seconds' in result
        assert result['duration_seconds'] > 0

    def test_warmup_checks_cache_readiness(self, specialist):
        """Testa que warmup verifica se cache está pronto."""
        specialist.opinion_cache = Mock()
        specialist.opinion_cache.is_connected.return_value = True

        result = specialist.warmup()

        assert result['cache_ready'] is True

    def test_warmup_without_cache(self, specialist):
        """Testa warmup sem cache configurado."""
        specialist.opinion_cache = None

        result = specialist.warmup()

        assert result['status'] == 'success'
        assert result['cache_ready'] is False


class TestWarmupFailure:
    """Testes de falha no warmup."""

    def test_warmup_handles_model_load_failure(self, specialist):
        """Testa tratamento de falha ao carregar modelo."""
        specialist.model = None
        specialist._load_model = Mock(side_effect=RuntimeError("Model load failed"))

        result = specialist.warmup()

        assert result['status'] == 'error'
        assert 'error' in result
        assert 'Model load failed' in result['error']
        assert 'duration_seconds' in result

    def test_warmup_handles_evaluation_failure(self, specialist):
        """Testa tratamento de falha na avaliação dummy."""
        specialist.evaluate_plan = Mock(side_effect=ValueError("Evaluation failed"))

        result = specialist.warmup()

        assert result['status'] == 'error'
        assert 'error' in result
        assert 'Evaluation failed' in result['error']


class TestWarmupMetrics:
    """Testes de métricas de warmup."""

    def test_warmup_records_success_metrics(self, specialist):
        """Testa que métricas de sucesso são registradas."""
        specialist.metrics.observe_warmup_duration = Mock()

        result = specialist.warmup()

        specialist.metrics.observe_warmup_duration.assert_called_once()
        call_args = specialist.metrics.observe_warmup_duration.call_args[0]

        assert call_args[0] > 0  # duration
        assert call_args[1] == 'success'  # status

    def test_warmup_records_error_metrics(self, specialist):
        """Testa que métricas de erro são registradas."""
        specialist.metrics.observe_warmup_duration = Mock()
        specialist.evaluate_plan = Mock(side_effect=RuntimeError("Test error"))

        result = specialist.warmup()

        specialist.metrics.observe_warmup_duration.assert_called_once()
        call_args = specialist.metrics.observe_warmup_duration.call_args[0]

        assert call_args[1] == 'error'  # status


class TestDummyPlanCreation:
    """Testes de criação de plano dummy."""

    def test_create_dummy_plan_structure(self, specialist):
        """Testa estrutura do plano dummy."""
        dummy_plan = specialist._create_dummy_plan()

        assert 'version' in dummy_plan
        assert 'plan_id' in dummy_plan
        assert 'intent_id' in dummy_plan
        assert 'original_domain' in dummy_plan
        assert 'original_priority' in dummy_plan
        assert 'tasks' in dummy_plan
        assert len(dummy_plan['tasks']) > 0

    def test_create_dummy_plan_valid_task(self, specialist):
        """Testa que task dummy é válida."""
        dummy_plan = specialist._create_dummy_plan()
        task = dummy_plan['tasks'][0]

        assert 'task_id' in task
        assert 'name' in task
        assert 'task_type' in task
        assert 'description' in task
        assert 'estimated_duration_ms' in task
        assert 'dependencies' in task

    def test_create_dummy_plan_is_serializable(self, specialist):
        """Testa que plano dummy é serializável."""
        dummy_plan = specialist._create_dummy_plan()

        # Deve ser possível serializar para JSON
        json_str = json.dumps(dummy_plan)
        assert len(json_str) > 0

        # Deve ser possível deserializar
        deserialized = json.loads(json_str)
        assert deserialized == dummy_plan


class TestWarmupIntegration:
    """Testes de integração de warmup."""

    def test_warmup_end_to_end(self, specialist):
        """Testa warmup end-to-end."""
        # Garantir que modelo não está carregado
        specialist.model = None

        # Executar warmup
        result = specialist.warmup()

        # Verificar resultado
        assert result['status'] == 'success'
        assert result['model_loaded'] is True
        assert result['duration_seconds'] > 0

        # Verificar que modelo foi carregado
        assert specialist.model is not None

    def test_warmup_multiple_times(self, specialist):
        """Testa que warmup pode ser executado múltiplas vezes."""
        result1 = specialist.warmup()
        result2 = specialist.warmup()
        result3 = specialist.warmup()

        assert result1['status'] == 'success'
        assert result2['status'] == 'success'
        assert result3['status'] == 'success'
