"""
Testes reais para BehaviorSpecialist - importando código de src/.

Estes testes importam o BehaviorSpecialist real do código fonte.
"""

import sys
import os
import pytest
from unittest.mock import MagicMock, patch

# Configurar path para importar código real
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
SRC_DIR = os.path.join(os.path.dirname(__file__), "src")
LIB_DIR = os.path.join(ROOT_DIR, "libraries/python")

sys.path.insert(0, SRC_DIR)
sys.path.insert(0, LIB_DIR)


@pytest.fixture(scope="function")
def env_setup():
    """Configura variáveis de ambiente para testes."""
    original_env = os.environ.copy()
    os.environ.update(
        {
            "ENVIRONMENT": "test",
            "LOG_LEVEL": "DEBUG",
            "MLFLOW_TRACKING_URI": "http://localhost:5000",
            "MONGODB_URI": "mongodb://localhost:27017/test",
            "REDIS_CLUSTER_NODES": "localhost:6379",
            "NEO4J_URI": "bolt://localhost:7687",
            "NEO4J_PASSWORD": "test_password",
            "JWT_SECRET_KEY": "test_secret_key_for_testing_only",
            "ENABLE_JWT_AUTH": "false",
            "ENABLE_CACHING": "false",
            "ENABLE_LEDGER": "false",
            "MODEL_REQUIRED": "false",
            "ENABLE_FEEDBACK_COLLECTION": "false",
            "FEEDBACK_API_ENABLED": "false",
            "ENABLE_PII_DETECTION": "false",
            "HTTP_PORT": "8001",
            "GRPC_PORT": "50051",
            "PROMETHEUS_PORT": "8002",
        }
    )
    yield
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def real_config(env_setup):
    """Configuração real do BehaviorSpecialistConfig."""
    from config import BehaviorSpecialistConfig

    return BehaviorSpecialistConfig()


@pytest.fixture
def mock_mlflow_client():
    """Mock do cliente MLflow."""
    mock_client = MagicMock()
    mock_client._enabled = False
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
    from specialist import BehaviorSpecialist

    with patch("neural_hive_specialists.BaseSpecialist.__init__", return_value=None):
        with patch("specialist.structlog.get_logger"):
            specialist = BehaviorSpecialist(real_config)
            specialist.config = real_config
            specialist.specialist_type = "behavior"
            specialist.version = "1.0.0"
            specialist.mlflow_client = mock_mlflow_client
            specialist.ledger_client = mock_ledger_client
            specialist._model = None
            specialist.metrics = MagicMock()
            return specialist


class TestBehaviorSpecialistInit:
    """Testes de inicialização do BehaviorSpecialist."""

    def test_specialist_type(self, real_specialist):
        """Verifica que o tipo do especialista é 'behavior'."""
        assert real_specialist._get_specialist_type() == "behavior"

    def test_specialist_attributes(self, real_specialist):
        """Verifica atributos do especialista."""
        assert hasattr(real_specialist, "config")
        assert hasattr(real_specialist, "specialist_type")
        assert hasattr(real_specialist, "_model")
        assert hasattr(real_specialist, "mlflow_client")


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

    @patch("specialist.logger")
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
            {"description": "Task 1", "estimated_duration_ms": 100},
            {"description": "Task 2", "estimated_duration_ms": 150},
            {"description": "Task 3", "estimated_duration_ms": 200},
        ]
        cognitive_plan = {"plan_id": "test-plan"}

        score = real_specialist._analyze_usability(tasks, cognitive_plan)

        assert 0.0 <= score <= 1.0
        assert score > 0.7  # Deve ser bom com 3 tarefas

    def test_analyze_usability_too_many_tasks(self, real_specialist):
        """Testa análise de usabilidade com muitas tarefas."""
        tasks = [{"description": f"Task {i}", "estimated_duration_ms": 100} for i in range(15)]
        cognitive_plan = {"plan_id": "test-plan"}

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
            {"description": "Fast task", "estimated_duration_ms": 50},
            {"description": "Fast task 2", "estimated_duration_ms": 80},
        ]
        tasks_slow = [
            {"description": "Slow task", "estimated_duration_ms": 1500},
            {"description": "Slow task 2", "estimated_duration_ms": 2000},
        ]

        score_fast = real_specialist._analyze_usability(tasks_fast, {})
        score_slow = real_specialist._analyze_usability(tasks_slow, {})

        # Tarefas rápidas devem ter score melhor
        assert score_fast > score_slow


class TestAnalyzeAccessibility:
    """Testes do método _analyze_accessibility."""

    def test_analyze_accessibility_with_context_mentions(self, real_specialist):
        """Testa análise quando contexto menciona acessibilidade."""
        cognitive_plan = {"original_domain": "ui-design"}
        context = {"accessibility": "wcag aa compliance required"}

        score = real_specialist._analyze_accessibility(cognitive_plan, context)

        assert score == 0.9  # Contexto menciona acessibilidade

    def test_analyze_accessibility_ui_related_domain(self, real_specialist):
        """Testa análise para domínio relacionado a UI."""
        cognitive_plan = {"original_domain": "frontend-interface"}
        context = {}

        score = real_specialist._analyze_accessibility(cognitive_plan, context)

        assert score == 0.6  # Domínio UI deve ter score moderado

    def test_analyze_accessibility_non_ui_domain(self, real_specialist):
        """Testa análise para domínio não-UI."""
        cognitive_plan = {"original_domain": "backend-processing"}
        context = {}

        score = real_specialist._analyze_accessibility(cognitive_plan, context)

        assert score == 0.7  # Domínio não-UI é neutro


class TestAnalyzeResponseTime:
    """Testes do método _analyze_response_time."""

    def test_response_time_instant(self, real_specialist):
        """Testa tempo de resposta instantâneo (< 100ms)."""
        tasks = [{"estimated_duration_ms": 50}]
        score = real_specialist._analyze_response_time(tasks)
        assert score == 1.0

    def test_response_time_fast(self, real_specialist):
        """Testa tempo de resposta rápido (< 300ms)."""
        tasks = [{"estimated_duration_ms": 200}]
        score = real_specialist._analyze_response_time(tasks)
        assert score == 0.9

    def test_response_time_acceptable(self, real_specialist):
        """Testa tempo de resposta aceitável (< 1000ms)."""
        tasks = [{"estimated_duration_ms": 500}]
        score = real_specialist._analyze_response_time(tasks)
        assert score == 0.7

    def test_response_time_slow(self, real_specialist):
        """Testa tempo de resposta lento (> 3000ms)."""
        tasks = [{"estimated_duration_ms": 5000}]
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
        tasks = [{"description": "Task"}]
        score = real_specialist._analyze_interaction_cost(tasks)
        assert score >= 0.8

    def test_interaction_cost_medium(self, real_specialist):
        """Testa custo de interação médio."""
        tasks = [{"description": f"Task {i}"} for i in range(5)]
        score = real_specialist._analyze_interaction_cost(tasks)
        assert 0.5 <= score <= 0.8

    def test_interaction_cost_high(self, real_specialist):
        """Testa custo de interação alto (muitas tarefas)."""
        tasks = [{"description": f"Task {i}"} for i in range(15)]
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
            interaction_cost_score=0.3,
        )
        assert risk > 0.6

    def test_risk_high_scores(self, real_specialist):
        """Testa cálculo de risco com scores altos (baixo risco)."""
        risk = real_specialist._calculate_behavioral_risk(
            cognitive_plan={},
            usability_score=0.9,
            accessibility_score=0.85,
            response_time_score=0.8,
            interaction_cost_score=0.75,
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
            interaction_cost_score=0.8,
        )

        risk_low_accessibility = real_specialist._calculate_behavioral_risk(
            cognitive_plan={},
            usability_score=0.8,
            accessibility_score=0.2,
            response_time_score=0.8,
            interaction_cost_score=0.8,
        )

        assert risk_low_usability > risk_low_accessibility


class TestDetermineRecommendation:
    """Testes do método _determine_recommendation."""

    def test_recommendation_approve(self, real_specialist):
        """Testa recomendação de aprovação."""
        rec = real_specialist._determine_recommendation(confidence_score=0.85, risk_score=0.2)
        assert rec == "approve"

    def test_recommendation_reject_low_confidence(self, real_specialist):
        """Testa rejeição por baixa confiança."""
        rec = real_specialist._determine_recommendation(confidence_score=0.4, risk_score=0.5)
        assert rec == "reject"

    def test_recommendation_reject_high_risk(self, real_specialist):
        """Testa rejeição por alto risco."""
        rec = real_specialist._determine_recommendation(confidence_score=0.6, risk_score=0.8)
        assert rec == "reject"

    def test_recommendation_review_required(self, real_specialist):
        """Testa recomendação de revisão necessária."""
        rec = real_specialist._determine_recommendation(confidence_score=0.6, risk_score=0.6)
        assert rec == "review_required"

    def test_recommendation_conditional(self, real_specialist):
        """Testa recomendação condicional."""
        rec = real_specialist._determine_recommendation(confidence_score=0.7, risk_score=0.4)
        assert rec == "conditional"


class TestGenerateReasoning:
    """Testes do método _generate_reasoning."""

    def test_reasoning_format(self, real_specialist):
        """Testa formato da justificativa gerada."""
        reasoning = real_specialist._generate_reasoning(
            usability_score=0.8,
            accessibility_score=0.75,
            response_time_score=0.7,
            interaction_cost_score=0.65,
            recommendation="approve",
        )

        assert "usability=0.80" in reasoning
        assert "accessibility=0.75" in reasoning
        assert "response_time=0.70" in reasoning
        assert "interaction_cost=0.65" in reasoning
        assert "approve" in reasoning


class TestGenerateMitigations:
    """Testes do método _generate_mitigations."""

    def test_mitigations_low_usability(self, real_specialist):
        """Testa geração de mitigação para usabilidade baixa."""
        mitigations = real_specialist._generate_mitigations(
            usability_score=0.4,
            accessibility_score=0.8,
            response_time_score=0.8,
            interaction_cost_score=0.8,
        )

        assert any(m["mitigation_type"] == "improve_usability" for m in mitigations)
        assert any(m["priority"] == "high" for m in mitigations)

    def test_mitigations_low_accessibility(self, real_specialist):
        """Testa geração de mitigação para acessibilidade baixa."""
        mitigations = real_specialist._generate_mitigations(
            usability_score=0.8,
            accessibility_score=0.4,
            response_time_score=0.8,
            interaction_cost_score=0.8,
        )

        assert any(m["mitigation_type"] == "ensure_accessibility" for m in mitigations)

    def test_mitigations_all_good(self, real_specialist):
        """Testa que não gera mitigações quando tudo está bom."""
        mitigations = real_specialist._generate_mitigations(
            usability_score=0.8,
            accessibility_score=0.8,
            response_time_score=0.8,
            interaction_cost_score=0.8,
        )

        assert len(mitigations) == 0


class TestEvaluatePlanInternal:
    """Testes do método _evaluate_plan_internal."""

    @patch("specialist.logger")
    def test_evaluate_plan_basic_structure(self, mock_logger, real_specialist):
        """Testa estrutura básica do resultado da avaliação."""
        plan = {
            "plan_id": "test-plan-123",
            "original_domain": "ux-analysis",
            "original_priority": "high",
            "tasks": [
                {"task_id": "task-1", "description": "Design UI", "estimated_duration_ms": 100}
            ],
        }
        context = {}

        result = real_specialist._evaluate_plan_internal(plan, context)

        # Verificar campos obrigatórios
        assert "confidence_score" in result
        assert "risk_score" in result
        assert "recommendation" in result
        assert "reasoning_summary" in result
        assert "reasoning_factors" in result
        assert "mitigations" in result
        assert "metadata" in result

    @patch("specialist.logger")
    def test_evaluate_plan_scores_in_range(self, mock_logger, real_specialist):
        """Testa que scores estão entre 0 e 1."""
        plan = {
            "plan_id": "test-plan",
            "original_domain": "ux-analysis",
            "tasks": [{"task_id": "task-1", "description": "Task", "estimated_duration_ms": 100}],
        }
        context = {}

        result = real_specialist._evaluate_plan_internal(plan, context)

        assert 0.0 <= result["confidence_score"] <= 1.0
        assert 0.0 <= result["risk_score"] <= 1.0

    @patch("specialist.logger")
    def test_evaluate_plan_reasoning_factors_structure(self, mock_logger, real_specialist):
        """Testa estrutura dos fatores de raciocínio."""
        plan = {"plan_id": "test-plan", "original_domain": "ux-analysis", "tasks": []}
        context = {}

        result = real_specialist._evaluate_plan_internal(plan, context)

        factors = result["reasoning_factors"]
        assert len(factors) == 4

        factor_names = [f["factor_name"] for f in factors]
        assert "usability" in factor_names
        assert "accessibility" in factor_names
        assert "response_time" in factor_names
        assert "interaction_cost" in factor_names

        # Verificar estrutura de cada fator
        for factor in factors:
            assert "weight" in factor
            assert "score" in factor
            assert "description" in factor

    @patch("specialist.logger")
    def test_evaluate_plan_metadata(self, mock_logger, real_specialist):
        """Testa metadados do resultado."""
        plan = {
            "plan_id": "test-plan",
            "original_domain": "ux-analysis",
            "original_priority": "high",
            "tasks": [{"task_id": "task-1", "description": "Task", "estimated_duration_ms": 100}],
        }
        context = {}

        result = real_specialist._evaluate_plan_internal(plan, context)

        metadata = result["metadata"]
        assert "usability_score" in metadata
        assert "accessibility_score" in metadata
        assert "response_time_score" in metadata
        assert "interaction_cost_score" in metadata
        assert "domain" in metadata
        assert "priority" in metadata
        assert "num_tasks" in metadata

        assert metadata["domain"] == "ux-analysis"
        assert metadata["priority"] == "high"
        assert metadata["num_tasks"] == 1

    @patch("specialist.logger")
    def test_evaluate_plan_empty_tasks(self, mock_logger, real_specialist):
        """Testa avaliação com lista de tarefas vazia."""
        plan = {"plan_id": "test-plan", "original_domain": "ux-analysis", "tasks": []}
        context = {}

        result = real_specialist._evaluate_plan_internal(plan, context)

        assert result is not None
        assert result["confidence_score"] >= 0.0

    @patch("specialist.logger")
    def test_evaluate_plan_recommendation_valid(self, mock_logger, real_specialist):
        """Testa que recomendação é um valor válido."""
        plan = {"plan_id": "test-plan", "original_domain": "ux-analysis", "tasks": []}
        context = {}

        result = real_specialist._evaluate_plan_internal(plan, context)

        valid_recommendations = ["approve", "reject", "review_required", "conditional"]
        assert result["recommendation"] in valid_recommendations


class TestEstimateFeedbackQuality:
    """Testes do método _estimate_feedback_quality."""

    def test_feedback_quality_very_fast(self, real_specialist):
        """Testa qualidade de feedback para tarefas muito rápidas (< 100ms)."""
        tasks = [{"estimated_duration_ms": 50}, {"estimated_duration_ms": 80}]
        score = real_specialist._estimate_feedback_quality(tasks)
        assert score == 1.0

    def test_feedback_quality_fast(self, real_specialist):
        """Testa qualidade de feedback para tarefas rápidas (< 300ms)."""
        tasks = [{"estimated_duration_ms": 150}, {"estimated_duration_ms": 250}]
        score = real_specialist._estimate_feedback_quality(tasks)
        assert score == 0.9

    def test_feedback_quality_acceptable(self, real_specialist):
        """Testa qualidade de feedback para tarefas aceitáveis (< 1000ms)."""
        tasks = [{"estimated_duration_ms": 500}, {"estimated_duration_ms": 800}]
        score = real_specialist._estimate_feedback_quality(tasks)
        assert score == 0.7

    def test_feedback_quality_slow(self, real_specialist):
        """Testa qualidade de feedback para tarefas lentas (> 1000ms)."""
        tasks = [{"estimated_duration_ms": 1500}, {"estimated_duration_ms": 2000}]
        score = real_specialist._estimate_feedback_quality(tasks)
        assert score == 0.5

    def test_feedback_quality_empty_tasks(self, real_specialist):
        """Testa qualidade de feedback com lista vazia."""
        score = real_specialist._estimate_feedback_quality([])
        assert score == 0.5
