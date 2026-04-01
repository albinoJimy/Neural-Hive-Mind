"""
Testes de métodos privados do BehaviorSpecialist - código real.

Estes testes validam métodos internos de análise comportamental.
"""

import sys
import os
import pytest
from unittest.mock import MagicMock, patch

# Configurar path para importar código real
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.specialist import BehaviorSpecialist
from src.config import BehaviorSpecialistConfig


@pytest.fixture
def config():
    """Configuração para testes."""
    config = BehaviorSpecialistConfig()
    config.model_required = False
    config.enable_caching = False
    config.enable_ledger = False
    return config


@pytest.fixture
def specialist(config):
    """Instância do especialista para testes."""
    with patch('neural_hive_specialists.BaseSpecialist.__init__', return_value=None):
        with patch('src.specialist.structlog.get_logger'):
            spec = BehaviorSpecialist(config)
            spec.config = config
            spec.specialist_type = "behavior"
            spec.version = "1.0.0"
            spec.mlflow_client = MagicMock()
            spec.mlflow_client._enabled = False
            spec.ledger_client = MagicMock()
            spec._model = None
            spec.metrics = MagicMock()
            return spec


class TestEstimateFeedbackQuality:
    """Testes do método _estimate_feedback_quality."""

    def test_feedback_quality_very_fast(self, specialist):
        """Testa qualidade de feedback para tarefas muito rápidas (< 100ms)."""
        tasks = [
            {'estimated_duration_ms': 50},
            {'estimated_duration_ms': 80}
        ]
        score = specialist._estimate_feedback_quality(tasks)
        assert score == 1.0

    def test_feedback_quality_fast(self, specialist):
        """Testa qualidade de feedback para tarefas rápidas (< 300ms)."""
        tasks = [
            {'estimated_duration_ms': 150},
            {'estimated_duration_ms': 250}
        ]
        score = specialist._estimate_feedback_quality(tasks)
        assert score == 0.9

    def test_feedback_quality_acceptable(self, specialist):
        """Testa qualidade de feedback para tarefas aceitáveis (< 1000ms)."""
        tasks = [
            {'estimated_duration_ms': 500},
            {'estimated_duration_ms': 800}
        ]
        score = specialist._estimate_feedback_quality(tasks)
        assert score == 0.7

    def test_feedback_quality_slow(self, specialist):
        """Testa qualidade de feedback para tarefas lentas (> 1000ms)."""
        tasks = [
            {'estimated_duration_ms': 1500},
            {'estimated_duration_ms': 2000}
        ]
        score = specialist._estimate_feedback_quality(tasks)
        assert score == 0.5

    def test_feedback_quality_empty_tasks(self, specialist):
        """Testa qualidade de feedback com lista vazia."""
        score = specialist._estimate_feedback_quality([])
        assert score == 0.5

    def test_feedback_quality_missing_duration(self, specialist):
        """Testa qualidade de feedback com duração faltando."""
        tasks = [
            {},
            {'estimated_duration_ms': 100}
        ]
        score = specialist._estimate_feedback_quality(tasks)
        # Média de None (tratado como 0) e 100 = 50ms
        assert score > 0.0


class TestEvaluatePlanInternal:
    """Testes do método _evaluate_plan_internal."""

    @patch('src.specialist.logger')
    def test_evaluate_plan_basic_structure(self, mock_logger, specialist):
        """Testa estrutura básica do resultado da avaliação."""
        plan = {
            'plan_id': 'test-plan-123',
            'original_domain': 'ux-analysis',
            'original_priority': 'high',
            'tasks': [
                {'task_id': 'task-1', 'description': 'Design UI', 'estimated_duration_ms': 100}
            ]
        }
        context = {}

        result = specialist._evaluate_plan_internal(plan, context)

        # Verificar campos obrigatórios
        assert 'confidence_score' in result
        assert 'risk_score' in result
        assert 'recommendation' in result
        assert 'reasoning_summary' in result
        assert 'reasoning_factors' in result
        assert 'mitigations' in result
        assert 'metadata' in result

    @patch('src.specialist.logger')
    def test_evaluate_plan_scores_in_range(self, mock_logger, specialist):
        """Testa que scores estão entre 0 e 1."""
        plan = {
            'plan_id': 'test-plan',
            'original_domain': 'ux-analysis',
            'tasks': [
                {'task_id': 'task-1', 'description': 'Task', 'estimated_duration_ms': 100}
            ]
        }
        context = {}

        result = specialist._evaluate_plan_internal(plan, context)

        assert 0.0 <= result['confidence_score'] <= 1.0
        assert 0.0 <= result['risk_score'] <= 1.0

    @patch('src.specialist.logger')
    def test_evaluate_plan_reasoning_factors_structure(self, mock_logger, specialist):
        """Testa estrutura dos fatores de raciocínio."""
        plan = {
            'plan_id': 'test-plan',
            'original_domain': 'ux-analysis',
            'tasks': []
        }
        context = {}

        result = specialist._evaluate_plan_internal(plan, context)

        factors = result['reasoning_factors']
        assert len(factors) == 4

        factor_names = [f['factor_name'] for f in factors]
        assert 'usability' in factor_names
        assert 'accessibility' in factor_names
        assert 'response_time' in factor_names
        assert 'interaction_cost' in factor_names

        # Verificar estrutura de cada fator
        for factor in factors:
            assert 'weight' in factor
            assert 'score' in factor
            assert 'description' in factor

    @patch('src.specialist.logger')
    def test_evaluate_plan_metadata(self, mock_logger, specialist):
        """Testa metadados do resultado."""
        plan = {
            'plan_id': 'test-plan',
            'original_domain': 'ux-analysis',
            'original_priority': 'high',
            'tasks': [
                {'task_id': 'task-1', 'description': 'Task', 'estimated_duration_ms': 100}
            ]
        }
        context = {}

        result = specialist._evaluate_plan_internal(plan, context)

        metadata = result['metadata']
        assert 'usability_score' in metadata
        assert 'accessibility_score' in metadata
        assert 'response_time_score' in metadata
        assert 'interaction_cost_score' in metadata
        assert 'domain' in metadata
        assert 'priority' in metadata
        assert 'num_tasks' in metadata

        assert metadata['domain'] == 'ux-analysis'
        assert metadata['priority'] == 'high'
        assert metadata['num_tasks'] == 1

    @patch('src.specialist.logger')
    def test_evaluate_plan_empty_tasks(self, mock_logger, specialist):
        """Testa avaliação com lista de tarefas vazia."""
        plan = {
            'plan_id': 'test-plan',
            'original_domain': 'ux-analysis',
            'tasks': []
        }
        context = {}

        result = specialist._evaluate_plan_internal(plan, context)

        assert result is not None
        assert result['confidence_score'] >= 0.0

    @patch('src.specialist.logger')
    def test_evaluate_plan_recommendation_valid(self, mock_logger, specialist):
        """Testa que recomendação é um valor válido."""
        plan = {
            'plan_id': 'test-plan',
            'original_domain': 'ux-analysis',
            'tasks': []
        }
        context = {}

        result = specialist._evaluate_plan_internal(plan, context)

        valid_recommendations = ['approve', 'reject', 'review_required', 'conditional']
        assert result['recommendation'] in valid_recommendations


class TestEvaluatePlanInternalScenarios:
    """Testes de cenários específicos de avaliação."""

    @patch('src.specialist.logger')
    def test_evaluate_good_ux_scenario(self, mock_logger, specialist):
        """Testa cenário de UX boa."""
        plan = {
            'plan_id': 'good-ux',
            'original_domain': 'ux-analysis',
            'original_priority': 'high',
            'tasks': [
                {'task_id': 'task-1', 'description': 'Fast responsive task', 'estimated_duration_ms': 80},
                {'task_id': 'task-2', 'description': 'Another quick task', 'estimated_duration_ms': 120},
            ]
        }
        context = {'accessibility': 'wcag compliance'}

        result = specialist._evaluate_plan_internal(plan, context)

        # Boa UX deve ter scores mais altos
        assert result['confidence_score'] > 0.5

    @patch('src.specialist.logger')
    def test_evaluate_poor_ux_scenario(self, mock_logger, specialist):
        """Testa cenário de UX ruim."""
        plan = {
            'plan_id': 'poor-ux',
            'original_domain': 'ui-development',
            'original_priority': 'normal',
            'tasks': [
                {'task_id': f'task-{i}', 'description': 'Slow task', 'estimated_duration_ms': 2000}
                for i in range(15)
            ]
        }
        context = {}

        result = specialist._evaluate_plan_internal(plan, context)

        # UX ruim deve ter risco mais alto
        assert result['risk_score'] > 0.4

    @patch('src.specialist.logger')
    def test_evaluate_accessibility_focused(self, mock_logger, specialist):
        """Testa cenário com foco em acessibilidade."""
        plan = {
            'plan_id': 'a11y-plan',
            'original_domain': 'ui-development',
            'tasks': [
                {'task_id': 'task-1', 'description': 'Add aria labels', 'estimated_duration_ms': 100},
            ]
        }
        context = {'accessibility': 'wcag aa compliance required'}

        result = specialist._evaluate_plan_internal(plan, context)

        # Acessibilidade deve ter score alto
        assert result['metadata']['accessibility_score'] >= 0.8

    @patch('src.specialist.logger')
    def test_evaluate_with_mitigations(self, mock_logger, specialist):
        """Testa geração de mitigações quando scores são baixos."""
        plan = {
            'plan_id': 'needs-improvement',
            'original_domain': 'ui-development',
            'tasks': [
                {'task_id': f'task-{i}', 'description': 'Task', 'estimated_duration_ms': 2000}
                for i in range(20)
            ]
        }
        context = {}

        result = specialist._evaluate_plan_internal(plan, context)

        # Deve gerar mitigações para scores baixos
        assert len(result['mitigations']) > 0

        # Verificar estrutura das mitigações
        for mitigation in result['mitigations']:
            assert 'mitigation_type' in mitigation
            assert 'description' in mitigation
            assert 'priority' in mitigation


class TestRecommendationLogic:
    """Testes de lógica de recomendação."""

    @patch('src.specialist.logger')
    def test_recommendation_approve_conditions(self, mock_logger, specialist):
        """Testa condições que levam à aprovação."""
        plan = {
            'plan_id': 'approve-test',
            'original_domain': 'ux-analysis',
            'tasks': [
                {'task_id': 'task-1', 'estimated_duration_ms': 50},
                {'task_id': 'task-2', 'estimated_duration_ms': 80},
                {'task_id': 'task-3', 'estimated_duration_ms': 100},
            ]
        }
        context = {'accessibility': 'wcag'}

        result = specialist._evaluate_plan_internal(plan, context)

        # Scores altos devem levar à aprovação
        if result['confidence_score'] >= 0.8 and result['risk_score'] < 0.3:
            assert result['recommendation'] == 'approve'

    @patch('src.specialist.logger')
    def test_recommendation_reject_conditions(self, mock_logger, specialist):
        """Testa condições que levam à rejeição."""
        plan = {
            'plan_id': 'reject-test',
            'original_domain': 'ui-development',
            'tasks': [
                {'task_id': f'task-{i}', 'description': 'Bad task', 'estimated_duration_ms': 5000}
                for i in range(20)
            ]
        }
        context = {}

        result = specialist._evaluate_plan_internal(plan, context)

        # Muito baixa confiança ou alto risco devem levar à rejeição
        if result['confidence_score'] < 0.5 or result['risk_score'] > 0.7:
            assert result['recommendation'] == 'reject'


class TestEdgeCases:
    """Testes de casos extremos."""

    @patch('src.specialist.logger')
    def test_plan_missing_optional_fields(self, mock_logger, specialist):
        """Testa plano com campos opcionais faltando."""
        plan = {
            'plan_id': 'minimal-plan',
            # Sem original_domain, original_priority
            'tasks': []
        }
        context = {}

        result = specialist._evaluate_plan_internal(plan, context)

        assert result is not None
        assert result['confidence_score'] >= 0.0

    @patch('src.specialist.logger')
    def test_tasks_missing_duration(self, mock_logger, specialist):
        """Testa tarefas sem duração estimada."""
        plan = {
            'plan_id': 'no-duration',
            'original_domain': 'ux-analysis',
            'tasks': [
                {'task_id': 'task-1', 'description': 'Task without duration'},
                {'task_id': 'task-2', 'description': 'Another task'},
            ]
        }
        context = {}

        result = specialist._evaluate_plan_internal(plan, context)

        # Deve tratar duração faltando como 0
        assert result is not None

    @patch('src.specialist.logger')
    def test_single_task_plan(self, mock_logger, specialist):
        """Testa plano com apenas uma tarefa."""
        plan = {
            'plan_id': 'single-task',
            'original_domain': 'ux-analysis',
            'tasks': [
                {'task_id': 'only-task', 'description': 'Single task', 'estimated_duration_ms': 100}
            ]
        }
        context = {}

        result = specialist._evaluate_plan_internal(plan, context)

        assert result is not None
        assert result['metadata']['num_tasks'] == 1
