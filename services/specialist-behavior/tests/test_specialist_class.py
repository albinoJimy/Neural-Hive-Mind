"""
Testes reais para BehaviorSpecialist - importando código de src/.

Estes testes importam o BehaviorSpecialist real do código fonte,
não mocks ou reimplementações.
"""

import sys
import os
import pytest
from unittest.mock import MagicMock, patch

# Configurar path para importar código real
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# Importar código REAL
from src.specialist import BehaviorSpecialist
from src.config import BehaviorSpecialistConfig


@pytest.fixture
def real_config():
    """Configuração real do BehaviorSpecialistConfig."""
    with patch('src.config.BehaviorSpecialistConfig.__init__', return_value=None):
        config = BehaviorSpecialistConfig()
        config.specialist_id = "test-behavior-specialist"
        config.domain = "BEHAVIOR"
        config.specialist_type = "behavior"
        config.service_name = "specialist-behavior"
        config.mlflow_experiment_name = "behavior-specialist"
        config.mlflow_model_name = "behavior-evaluator"
        config.mlflow_model_stage = "Production"
        config.supported_domains = [
            "ux-analysis",
            "accessibility-evaluation",
            "usability-testing",
            "user-experience",
            "interaction-design"
        ]
        config.accessibility_wcag_level = "AA"
        config.usability_threshold_high = 0.8
        config.usability_threshold_low = 0.5
        config.response_time_threshold_ms = 300
        config.interaction_cost_threshold = 0.7
        config.http_port = 8001
        config.grpc_port = 50051
        config.prometheus_port = 8002
        config.environment = "test"
        config.log_level = "DEBUG"
        config.enable_caching = False
        config.enable_ledger = False
        config.ledger_required = False
        config.model_required = False  # Permitir modo heurístico
        config.enable_feedback_collection = False
        config.feedback_api_enabled = False
        config.enable_pii_detection = False
        return config


@pytest.fixture
def mock_mlflow_client():
    """Mock do cliente MLflow."""
    mock_client = MagicMock()
    mock_client._enabled = False  # MLflow desabilitado para testes
    return mock_client


@pytest.fixture
def mock_ledger_client():
    """Mock do cliente Ledger."""
    mock_client = MagicMock()
    mock_client.check_health.return_value = {"status": "healthy"}
    return mock_client


@pytest.fixture
def real_specialist(real_config, mock_mlflow_client, mock_ledger_client):
    """Instância real do BehaviorSpecialist."""
    with patch('src.specialist.structlog.get_logger'):
        with patch('neural_hive_specialists.BaseSpecialist.__init__', return_value=None):
            specialist = BehaviorSpecialist(real_config)
            specialist.config = real_config
            specialist.specialist_type = "behavior"
            specialist.version = "1.0.0"
            specialist.mlflow_client = mock_mlflow_client
            specialist.ledger_client = mock_ledger_client
            specialist._model = None  # Modo heurístico
            specialist.metrics = MagicMock()
            return specialist


class TestBehaviorSpecialistInit:
    """Testes de inicialização do BehaviorSpecialist."""

    def test_specialist_type(self, real_specialist):
        """Verifica que o tipo do especialista é 'behavior'."""
        assert real_specialist._get_specialist_type() == "behavior"

    def test_specialist_attributes(self, real_specialist):
        """Verifica atributos do especialista."""
        assert hasattr(real_specialist, 'config')
        assert hasattr(real_specialist, 'specialist_type')
        assert hasattr(real_specialist, '_model')
        assert hasattr(real_specialist, 'mlflow_client')


class TestLoadModel:
    """Testes do método _load_model."""

    def test_load_model_mlflow_disabled(self, real_specialist):
        """Testa carregamento quando MLflow está desabilitado."""
        real_specialist.mlflow_client = None
        model = real_specialist._load_model()
        assert model is None

    def test_load_model_mlflow_not_enabled(self, real_specialist):
        """Testa carregamento quando MLflow._enabled é False."""
        real_specialist.mlflow_client._enabled = False
        model = real_specialist._load_model()
        assert model is None

    @patch('src.specialist.logger')
    def test_load_model_exception(self, mock_logger, real_specialist):
        """Testa tratamento de exceção ao carregar modelo."""
        real_specialist.mlflow_client._enabled = True
        real_specialist.mlflow_client.load_model.side_effect = Exception("MLflow error")

        model = real_specialist._load_model()
        assert model is None


class TestAnalyzeUsability:
    """Testes do método _analyze_usability."""

    def test_analyze_usability_ideal_tasks(self, real_specialist):
        """Testa análise de usabilidade com número ideal de tarefas."""
        tasks = [
            {'description': 'Task 1', 'estimated_duration_ms': 100},
            {'description': 'Task 2', 'estimated_duration_ms': 150},
            {'description': 'Task 3', 'estimated_duration_ms': 200},
        ]
        cognitive_plan = {'plan_id': 'test-plan'}

        score = real_specialist._analyze_usability(tasks, cognitive_plan)

        assert 0.0 <= score <= 1.0
        assert score > 0.7  # Deve ser bom com 3 tarefas

    def test_analyze_usability_too_many_tasks(self, real_specialist):
        """Testa análise de usabilidade com muitas tarefas."""
        tasks = [
            {'description': f'Task {i}', 'estimated_duration_ms': 100}
            for i in range(15)
        ]
        cognitive_plan = {'plan_id': 'test-plan'}

        score = real_specialist._analyze_usability(tasks, cognitive_plan)

        assert 0.0 <= score <= 1.0
        assert score < 0.7  # Deve penalizar muitas tarefas

    def test_analyze_usability_empty_tasks(self, real_specialist):
        """Testa análise de usabilidade com lista vazia."""
        score = real_specialist._analyze_usability([], {})
        assert score == 0.5

    def test_analyze_usability_with_duration(self, real_specialist):
        """Testa que considera duração estimada."""
        tasks_fast = [
            {'description': 'Fast task', 'estimated_duration_ms': 50},
            {'description': 'Fast task 2', 'estimated_duration_ms': 80},
        ]
        tasks_slow = [
            {'description': 'Slow task', 'estimated_duration_ms': 1500},
            {'description': 'Slow task 2', 'estimated_duration_ms': 2000},
        ]

        score_fast = real_specialist._analyze_usability(tasks_fast, {})
        score_slow = real_specialist._analyze_usability(tasks_slow, {})

        # Tarefas rápidas devem ter score melhor
        assert score_fast > score_slow


class TestAnalyzeAccessibility:
    """Testes do método _analyze_accessibility."""

    def test_analyze_accessibility_with_context_mentions(self, real_specialist):
        """Testa análise quando contexto menciona acessibilidade."""
        cognitive_plan = {'original_domain': 'ui-design'}
        context = {'accessibility': 'wcag aa compliance required'}

        score = real_specialist._analyze_accessibility(cognitive_plan, context)

        assert score == 0.9  # Contexto menciona acessibilidade

    def test_analyze_accessibility_ui_related_domain(self, real_specialist):
        """Testa análise para domínio relacionado a UI."""
        cognitive_plan = {'original_domain': 'frontend-interface'}
        context = {}

        score = real_specialist._analyze_accessibility(cognitive_plan, context)

        assert score == 0.6  # Domínio UI deve ter score moderado

    def test_analyze_accessibility_non_ui_domain(self, real_specialist):
        """Testa análise para domínio não-UI."""
        cognitive_plan = {'original_domain': 'backend-processing'}
        context = {}

        score = real_specialist._analyze_accessibility(cognitive_plan, context)

        assert score == 0.7  # Domínio não-UI é neutro


class TestAnalyzeResponseTime:
    """Testes do método _analyze_response_time."""

    def test_response_time_instant(self, real_specialist):
        """Testa tempo de resposta instantâneo (< 100ms)."""
        tasks = [{'estimated_duration_ms': 50}]
        score = real_specialist._analyze_response_time(tasks)
        assert score == 1.0

    def test_response_time_fast(self, real_specialist):
        """Testa tempo de resposta rápido (< 300ms)."""
        tasks = [{'estimated_duration_ms': 200}]
        score = real_specialist._analyze_response_time(tasks)
        assert score == 0.9

    def test_response_time_acceptable(self, real_specialist):
        """Testa tempo de resposta aceitável (< 1000ms)."""
        tasks = [{'estimated_duration_ms': 500}]
        score = real_specialist._analyze_response_time(tasks)
        assert score == 0.7

    def test_response_time_slow(self, real_specialist):
        """Testa tempo de resposta lento (> 3000ms)."""
        tasks = [{'estimated_duration_ms': 5000}]
        score = real_specialist._analyze_response_time(tasks)
        assert score < 0.5

    def test_response_time_empty_tasks(self, real_specialist):
        """Testa com lista vazia de tarefas."""
        score = real_specialist._analyze_response_time([])
        assert score == 0.5


class TestAnalyzeInteractionCost:
    """Testes do método _analyze_interaction_cost."""

    def test_interaction_cost_low(self, real_specialist):
        """Testa custo de interação baixo (poucas tarefas)."""
        tasks = [{'description': 'Task'}]
        score = real_specialist._analyze_interaction_cost(tasks)
        assert score >= 0.8

    def test_interaction_cost_medium(self, real_specialist):
        """Testa custo de interação médio."""
        tasks = [{'description': f'Task {i}'} for i in range(5)]
        score = real_specialist._analyze_interaction_cost(tasks)
        assert 0.5 <= score <= 0.8

    def test_interaction_cost_high(self, real_specialist):
        """Testa custo de interação alto (muitas tarefas)."""
        tasks = [{'description': f'Task {i}'} for i in range(15)]
        score = real_specialist._analyze_interaction_cost(tasks)
        assert score < 0.5

    def test_interaction_cost_empty_tasks(self, real_specialist):
        """Testa com lista vazia de tarefas."""
        score = real_specialist._analyze_interaction_cost([])
        assert score == 0.5


class TestCalculateBehavioralRisk:
    """Testes do método _calculate_behavioral_risk."""

    def test_risk_low_scores(self, real_specialist):
        """Testa cálculo de risco com scores baixos (alto risco)."""
        risk = real_specialist._calculate_behavioral_risk(
            cognitive_plan={},
            usability_score=0.3,
            accessibility_score=0.4,
            response_time_score=0.35,
            interaction_cost_score=0.3
        )
        assert risk > 0.6

    def test_risk_high_scores(self, real_specialist):
        """Testa cálculo de risco com scores altos (baixo risco)."""
        risk = real_specialist._calculate_behavioral_risk(
            cognitive_plan={},
            usability_score=0.9,
            accessibility_score=0.85,
            response_time_score=0.8,
            interaction_cost_score=0.75
        )
        assert risk < 0.3

    def test_risk_weights(self, real_specialist):
        """Testa que usabilidade tem maior peso."""
        # Usabilidade baixa deve aumentar mais risco que acessibilidade baixa
        risk_low_usability = real_specialist._calculate_behavioral_risk(
            cognitive_plan={},
            usability_score=0.2,
            accessibility_score=0.8,
            response_time_score=0.8,
            interaction_cost_score=0.8
        )

        risk_low_accessibility = real_specialist._calculate_behavioral_risk(
            cognitive_plan={},
            usability_score=0.8,
            accessibility_score=0.2,
            response_time_score=0.8,
            interaction_cost_score=0.8
        )

        assert risk_low_usability > risk_low_accessibility


class TestDetermineRecommendation:
    """Testes do método _determine_recommendation."""

    def test_recommendation_approve(self, real_specialist):
        """Testa recomendação de aprovação."""
        rec = real_specialist._determine_recommendation(
            confidence_score=0.85,
            risk_score=0.2
        )
        assert rec == 'approve'

    def test_recommendation_reject_low_confidence(self, real_specialist):
        """Testa rejeição por baixa confiança."""
        rec = real_specialist._determine_recommendation(
            confidence_score=0.4,
            risk_score=0.5
        )
        assert rec == 'reject'

    def test_recommendation_reject_high_risk(self, real_specialist):
        """Testa rejeição por alto risco."""
        rec = real_specialist._determine_recommendation(
            confidence_score=0.6,
            risk_score=0.8
        )
        assert rec == 'reject'

    def test_recommendation_review_required(self, real_specialist):
        """Testa recomendação de revisão necessária."""
        rec = real_specialist._determine_recommendation(
            confidence_score=0.6,
            risk_score=0.6
        )
        assert rec == 'review_required'

    def test_recommendation_conditional(self, real_specialist):
        """Testa recomendação condicional."""
        rec = real_specialist._determine_recommendation(
            confidence_score=0.7,
            risk_score=0.4
        )
        assert rec == 'conditional'


class TestGenerateReasoning:
    """Testes do método _generate_reasoning."""

    def test_reasoning_format(self, real_specialist):
        """Testa formato da justificativa gerada."""
        reasoning = real_specialist._generate_reasoning(
            usability_score=0.8,
            accessibility_score=0.75,
            response_time_score=0.7,
            interaction_cost_score=0.65,
            recommendation='approve'
        )

        assert 'usability=0.80' in reasoning
        assert 'accessibility=0.75' in reasoning
        assert 'response_time=0.70' in reasoning
        assert 'interaction_cost=0.65' in reasoning
        assert 'approve' in reasoning


class TestGenerateMitigations:
    """Testes do método _generate_mitigations."""

    def test_mitigations_low_usability(self, real_specialist):
        """Testa geração de mitigação para usabilidade baixa."""
        mitigations = real_specialist._generate_mitigations(
            usability_score=0.4,
            accessibility_score=0.8,
            response_time_score=0.8,
            interaction_cost_score=0.8
        )

        assert any(m['mitigation_type'] == 'improve_usability' for m in mitigations)
        assert any(m['priority'] == 'high' for m in mitigations)

    def test_mitigations_low_accessibility(self, real_specialist):
        """Testa geração de mitigação para acessibilidade baixa."""
        mitigations = real_specialist._generate_mitigations(
            usability_score=0.8,
            accessibility_score=0.4,
            response_time_score=0.8,
            interaction_cost_score=0.8
        )

        assert any(m['mitigation_type'] == 'ensure_accessibility' for m in mitigations)

    def test_mitigations_all_good(self, real_specialist):
        """Testa que não gera mitigações quando tudo está bom."""
        mitigations = real_specialist._generate_mitigations(
            usability_score=0.8,
            accessibility_score=0.8,
            response_time_score=0.8,
            interaction_cost_score=0.8
        )

        assert len(mitigations) == 0
