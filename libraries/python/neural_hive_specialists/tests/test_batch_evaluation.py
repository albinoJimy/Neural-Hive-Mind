"""
Testes para batch evaluation de planos.
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from neural_hive_specialists.config import SpecialistConfig
from neural_hive_specialists.base_specialist import BaseSpecialist


class MockSpecialist(BaseSpecialist):
    """Especialista mock para testes."""

    def _get_specialist_type(self) -> str:
        return 'test'

    def _load_model(self):
        return None

    def _evaluate_plan_internal(self, cognitive_plan, context):
        # Simular avaliação
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
        batch_max_concurrency=5,
        opinion_cache_enabled=False,  # Desabilitar cache para testes
        enable_drift_monitoring=False
    )


@pytest.fixture
def specialist(specialist_config):
    """Especialista mock para testes."""
    with patch('neural_hive_specialists.base_specialist.MLflowClient'):
        with patch('neural_hive_specialists.base_specialist.LedgerClient'):
            with patch('neural_hive_specialists.base_specialist.FeatureStore'):
                return MockSpecialist(specialist_config)


def create_mock_request(plan_id: str, intent_id: str):
    """Cria request mock para testes."""
    plan = {
        'version': '1.0.0',
        'plan_id': plan_id,
        'intent_id': intent_id,
        'original_domain': 'test',
        'original_priority': 'normal',
        'tasks': [
            {
                'task_id': f'{plan_id}-task-1',
                'name': 'Test Task',
                'task_type': 'test',
                'description': 'Test task',
                'estimated_duration_ms': 100,
                'dependencies': []
            }
        ]
    }

    return type('Request', (), {
        'plan_id': plan_id,
        'intent_id': intent_id,
        'cognitive_plan': json.dumps(plan).encode('utf-8'),
        'trace_id': f'trace-{plan_id}',
        'span_id': f'span-{plan_id}',
        'correlation_id': f'corr-{plan_id}',
        'context': {}
    })


class TestBatchEvaluationSuccess:
    """Testes de batch evaluation bem-sucedida."""

    @pytest.mark.asyncio
    async def test_batch_evaluation_single_plan(self, specialist):
        """Testa batch com um único plano."""
        requests = [create_mock_request('plan-1', 'intent-1')]

        result = await specialist.evaluate_plans_batch(requests)

        assert result['statistics']['total'] == 1
        assert result['statistics']['successful'] == 1
        assert result['statistics']['failed'] == 0
        assert result['statistics']['success_rate'] == 1.0
        assert len(result['successful']) == 1
        assert len(result['failed']) == 0

    @pytest.mark.asyncio
    async def test_batch_evaluation_multiple_plans(self, specialist):
        """Testa batch com múltiplos planos."""
        requests = [
            create_mock_request(f'plan-{i}', f'intent-{i}')
            for i in range(10)
        ]

        result = await specialist.evaluate_plans_batch(requests)

        assert result['statistics']['total'] == 10
        assert result['statistics']['successful'] == 10
        assert result['statistics']['failed'] == 0
        assert result['statistics']['success_rate'] == 1.0
        assert len(result['successful']) == 10

    @pytest.mark.asyncio
    async def test_batch_evaluation_custom_concurrency(self, specialist):
        """Testa batch com concorrência customizada."""
        requests = [
            create_mock_request(f'plan-{i}', f'intent-{i}')
            for i in range(5)
        ]

        result = await specialist.evaluate_plans_batch(requests, max_concurrency=2)

        assert result['statistics']['successful'] == 5


class TestBatchEvaluationPartialFailure:
    """Testes de batch com falhas parciais."""

    @pytest.mark.asyncio
    async def test_batch_evaluation_with_some_failures(self, specialist):
        """Testa batch onde alguns planos falham."""
        requests = [
            create_mock_request(f'plan-{i}', f'intent-{i}')
            for i in range(10)
        ]

        # Fazer planos 3, 5, 7 falharem
        original_evaluate = specialist.evaluate_plan

        def failing_evaluate(request):
            if request.plan_id in ['plan-3', 'plan-5', 'plan-7']:
                raise ValueError(f"Simulated failure for {request.plan_id}")
            return original_evaluate(request)

        specialist.evaluate_plan = failing_evaluate

        result = await specialist.evaluate_plans_batch(requests)

        assert result['statistics']['total'] == 10
        assert result['statistics']['successful'] == 7
        assert result['statistics']['failed'] == 3
        assert result['statistics']['success_rate'] == 0.7
        assert len(result['successful']) == 7
        assert len(result['failed']) == 3

    @pytest.mark.asyncio
    async def test_batch_evaluation_all_failures(self, specialist):
        """Testa batch onde todos os planos falham."""
        requests = [
            create_mock_request(f'plan-{i}', f'intent-{i}')
            for i in range(5)
        ]

        specialist.evaluate_plan = Mock(side_effect=RuntimeError("All failed"))

        result = await specialist.evaluate_plans_batch(requests)

        assert result['statistics']['total'] == 5
        assert result['statistics']['successful'] == 0
        assert result['statistics']['failed'] == 5
        assert result['statistics']['success_rate'] == 0.0
        assert len(result['successful']) == 0
        assert len(result['failed']) == 5


class TestBatchEvaluationMetrics:
    """Testes de métricas de batch evaluation."""

    @pytest.mark.asyncio
    async def test_batch_evaluation_records_metrics(self, specialist):
        """Testa que métricas são registradas."""
        requests = [
            create_mock_request(f'plan-{i}', f'intent-{i}')
            for i in range(5)
        ]

        specialist.metrics.observe_batch_evaluation = Mock()

        result = await specialist.evaluate_plans_batch(requests)

        # Verificar que métricas foram chamadas
        specialist.metrics.observe_batch_evaluation.assert_called_once()
        call_args = specialist.metrics.observe_batch_evaluation.call_args[1]

        assert call_args['total'] == 5
        assert call_args['successful'] == 5
        assert call_args['failed'] == 0
        assert 'duration' in call_args

    @pytest.mark.asyncio
    async def test_batch_evaluation_duration_tracking(self, specialist):
        """Testa que duração é rastreada corretamente."""
        requests = [
            create_mock_request(f'plan-{i}', f'intent-{i}')
            for i in range(3)
        ]

        result = await specialist.evaluate_plans_batch(requests)

        assert 'duration_seconds' in result['statistics']
        assert result['statistics']['duration_seconds'] > 0
        assert 'avg_duration_per_plan_ms' in result['statistics']


class TestBatchEvaluationEdgeCases:
    """Testes de casos extremos."""

    @pytest.mark.asyncio
    async def test_batch_evaluation_empty_list(self, specialist):
        """Testa batch com lista vazia."""
        result = await specialist.evaluate_plans_batch([])

        assert result['statistics']['total'] == 0
        assert result['statistics']['successful'] == 0
        assert result['statistics']['failed'] == 0
        assert len(result['successful']) == 0

    @pytest.mark.asyncio
    async def test_batch_evaluation_large_batch(self, specialist):
        """Testa batch com muitos planos."""
        requests = [
            create_mock_request(f'plan-{i}', f'intent-{i}')
            for i in range(50)
        ]

        result = await specialist.evaluate_plans_batch(requests, max_concurrency=20)

        assert result['statistics']['total'] == 50
        assert result['statistics']['successful'] == 50
