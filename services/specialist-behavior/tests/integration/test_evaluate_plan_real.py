"""
Testes de integração para BehaviorSpecialist - código real.

Estes testes validam o fluxo completo de avaliação de planos.
"""

import sys
import os
import pytest
from unittest.mock import MagicMock, patch

# Configurar path para importar código real
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
SRC_DIR = os.path.join(os.path.dirname(__file__), "..", "src")
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
    """Configuração para testes de integração."""
    from config import BehaviorSpecialistConfig

    return BehaviorSpecialistConfig()


@pytest.fixture
def real_specialist(real_config):
    """Instância do especialista para integração."""
    from specialist import BehaviorSpecialist

    with patch("neural_hive_specialists.BaseSpecialist.__init__", return_value=None):
        with patch("specialist.structlog.get_logger"):
            spec = BehaviorSpecialist(real_config)
            spec.config = real_config
            spec.specialist_type = "behavior"
            spec.version = "1.0.0"
            spec.mlflow_client = MagicMock()
            spec.mlflow_client._enabled = False
            spec.ledger_client = MagicMock()
            spec._model = None
            spec.metrics = MagicMock()
            return spec


@pytest.fixture
def complete_ux_plan():
    """Plano UX completo para testes."""
    return {
        "plan_id": "ux-improvement-001",
        "original_domain": "ux-analysis",
        "original_priority": "high",
        "description": "Improving user experience with intuitive design",
        "tasks": [
            {
                "task_id": "task-1",
                "description": "Simplify navigation menu",
                "dependencies": [],
                "estimated_duration_ms": 150,
            },
            {
                "task_id": "task-2",
                "description": "Add keyboard shortcuts",
                "dependencies": ["task-1"],
                "estimated_duration_ms": 200,
            },
            {
                "task_id": "task-3",
                "description": "Ensure WCAG AA compliance",
                "dependencies": [],
                "estimated_duration_ms": 300,
            },
            {
                "task_id": "task-4",
                "description": "Optimize page load time",
                "dependencies": ["task-2"],
                "estimated_duration_ms": 100,
            },
        ],
    }


@pytest.fixture
def poor_ux_plan():
    """Plano UX ruim para testes."""
    return {
        "plan_id": "bad-ux-001",
        "original_domain": "ui-development",
        "original_priority": "normal",
        "description": "Complex multi-step process",
        "tasks": [
            {
                "task_id": f"task-{i}",
                "description": f"Complex step {i} requiring multiple clicks",
                "dependencies": [f"task-{i-1}" if i > 0 else []],
                "estimated_duration_ms": 3000,
            }
            for i in range(15)
        ],
    }


class TestFullEvaluationFlow:
    """Testes do fluxo completo de avaliação."""

    @patch("specialist.logger")
    def test_full_evaluation_with_good_ux(self, mock_logger, real_specialist, complete_ux_plan):
        """Testa avaliação completa de um plano UX bom."""
        context = {"accessibility_requirements": ["wcag_2.1_aa"], "target_audience": "all_users"}

        result = real_specialist._evaluate_plan_internal(complete_ux_plan, context)

        # Verificar estrutura completa
        assert "confidence_score" in result
        assert "risk_score" in result
        assert "recommendation" in result
        assert "reasoning_summary" in result
        assert "reasoning_factors" in result
        assert "mitigations" in result
        assert "metadata" in result

        # Verificar tipos
        assert isinstance(result["confidence_score"], (int, float))
        assert isinstance(result["risk_score"], (int, float))
        assert isinstance(result["recommendation"], str)
        assert isinstance(result["reasoning_factors"], list)
        assert isinstance(result["mitigations"], list)

        # Verificar ranges
        assert 0.0 <= result["confidence_score"] <= 1.0
        assert 0.0 <= result["risk_score"] <= 1.0

        # Verificar recomendação válida
        assert result["recommendation"] in ["approve", "reject", "review_required", "conditional"]

    @patch("specialist.logger")
    def test_full_evaluation_with_poor_ux(self, mock_logger, real_specialist, poor_ux_plan):
        """Testa avaliação completa de um plano UX ruim."""
        context = {}

        result = real_specialist._evaluate_plan_internal(poor_ux_plan, context)

        # Plano ruim deve ter risco mais alto
        assert result["risk_score"] > 0.3

        # Deve gerar mitigações
        assert len(result["mitigations"]) > 0


class TestReasoningFactorsIntegration:
    """Testes de integração dos fatores de raciocínio."""

    @patch("specialist.logger")
    def test_all_four_factors_present(self, mock_logger, real_specialist, complete_ux_plan):
        """Testa que todos os 4 fatores estão presentes."""
        result = real_specialist._evaluate_plan_internal(complete_ux_plan, {})

        factor_names = [f["factor_name"] for f in result["reasoning_factors"]]
        assert "usability" in factor_names
        assert "accessibility" in factor_names
        assert "response_time" in factor_names
        assert "interaction_cost" in factor_names

    @patch("specialist.logger")
    def test_factor_weights_sum_to_one(self, mock_logger, real_specialist, complete_ux_plan):
        """Testa que pesos dos fatores somam 1.0."""
        result = real_specialist._evaluate_plan_internal(complete_ux_plan, {})

        weights_sum = sum(f["weight"] for f in result["reasoning_factors"])
        assert abs(weights_sum - 1.0) < 0.01

    @patch("specialist.logger")
    def test_factor_scores_in_range(self, mock_logger, real_specialist, complete_ux_plan):
        """Testa que scores dos fatores estão entre 0 e 1."""
        result = real_specialist._evaluate_plan_internal(complete_ux_plan, {})

        for factor in result["reasoning_factors"]:
            assert 0.0 <= factor["score"] <= 1.0

    @patch("specialist.logger")
    def test_factor_descriptions_present(self, mock_logger, real_specialist, complete_ux_plan):
        """Testa que cada fator tem descrição."""
        result = real_specialist._evaluate_plan_internal(complete_ux_plan, {})

        for factor in result["reasoning_factors"]:
            assert "description" in factor
            assert len(factor["description"]) > 0


class TestMetadataIntegration:
    """Testes de integração de metadados."""

    @patch("specialist.logger")
    def test_metadata_contains_plan_info(self, mock_logger, real_specialist, complete_ux_plan):
        """Testa que metadados contêm informações do plano."""
        result = real_specialist._evaluate_plan_internal(complete_ux_plan, {})

        assert result["metadata"]["domain"] == "ux-analysis"
        assert result["metadata"]["priority"] == "high"
        assert result["metadata"]["num_tasks"] == 4

    @patch("specialist.logger")
    def test_metadata_contains_all_scores(self, mock_logger, real_specialist, complete_ux_plan):
        """Testa que metadados contêm todos os scores individuais."""
        result = real_specialist._evaluate_plan_internal(complete_ux_plan, {})

        assert "usability_score" in result["metadata"]
        assert "accessibility_score" in result["metadata"]
        assert "response_time_score" in result["metadata"]
        assert "interaction_cost_score" in result["metadata"]

        # Verificar ranges
        for score_key in [
            "usability_score",
            "accessibility_score",
            "response_time_score",
            "interaction_cost_score",
        ]:
            score = result["metadata"][score_key]
            assert 0.0 <= score <= 1.0


class TestConfidenceRiskRelationship:
    """Testes de relação entre confiança e risco."""

    @patch("specialist.logger")
    def test_high_confidence_low_risk_correlation(
        self, mock_logger, real_specialist, complete_ux_plan
    ):
        """Testa correlação entre alta confiança e baixo risco."""
        result = real_specialist._evaluate_plan_internal(
            complete_ux_plan, {"accessibility": "wcag"}
        )

        if result["confidence_score"] > 0.7:
            assert result["risk_score"] < 0.5

    @patch("specialist.logger")
    def test_low_confidence_high_risk_correlation(self, mock_logger, real_specialist, poor_ux_plan):
        """Testa correlação entre baixa confiança e alto risco."""
        result = real_specialist._evaluate_plan_internal(poor_ux_plan, {})

        if result["confidence_score"] < 0.5:
            assert result["risk_score"] > 0.4

    @patch("specialist.logger")
    def test_confidence_plus_risk_approximates_one(
        self, mock_logger, real_specialist, complete_ux_plan
    ):
        """Testa que confiança + risco aproximadamente 1.0."""
        result = real_specialist._evaluate_plan_internal(complete_ux_plan, {})

        sum_scores = result["confidence_score"] + result["risk_score"]
        assert abs(sum_scores - 1.0) < 0.1


class TestMitigationGeneration:
    """Testes de geração de mitigações."""

    @patch("specialist.logger")
    def test_mitigations_for_low_usability(self, mock_logger, real_specialist):
        """Testa geração de mitigações para usabilidade baixa."""
        plan = {
            "plan_id": "low-usability",
            "original_domain": "ui-development",
            "tasks": [{"task_id": f"t{i}", "estimated_duration_ms": 1000} for i in range(20)],
        }
        result = real_specialist._evaluate_plan_internal(plan, {})

        usability_mitigations = [
            m for m in result["mitigations"] if m["mitigation_type"] == "improve_usability"
        ]
        assert len(usability_mitigations) > 0

    @patch("specialist.logger")
    def test_mitigations_have_required_fields(self, mock_logger, real_specialist, poor_ux_plan):
        """Testa que mitigações têm campos obrigatórios."""
        result = real_specialist._evaluate_plan_internal(poor_ux_plan, {})

        for mitigation in result["mitigations"]:
            assert "mitigation_type" in mitigation
            assert "description" in mitigation
            assert "priority" in mitigation
            assert "estimated_effort" in mitigation


class TestDifferentDomains:
    """Testes para diferentes domínios."""

    @patch("specialist.logger")
    def test_ux_analysis_domain(self, mock_logger, real_specialist):
        """Testa domínio ux-analysis."""
        plan = {"plan_id": "ux-test", "original_domain": "ux-analysis", "tasks": []}
        result = real_specialist._evaluate_plan_internal(plan, {})

        assert result["metadata"]["domain"] == "ux-analysis"

    @patch("specialist.logger")
    def test_accessibility_evaluation_domain(self, mock_logger, real_specialist):
        """Testa domínio accessibility-evaluation."""
        plan = {"plan_id": "a11y-test", "original_domain": "accessibility-evaluation", "tasks": []}
        result = real_specialist._evaluate_plan_internal(plan, {})

        assert result["metadata"]["domain"] == "accessibility-evaluation"

    @patch("specialist.logger")
    def test_non_ui_domain(self, mock_logger, real_specialist):
        """Testa domínio não-UI (backend)."""
        plan = {"plan_id": "backend-test", "original_domain": "backend-processing", "tasks": []}
        result = real_specialist._evaluate_plan_internal(plan, {})

        assert result["metadata"]["domain"] == "backend-processing"


class TestEmptyAndMinimalPlans:
    """Testes para planos vazios ou mínimos."""

    @patch("specialist.logger")
    def test_empty_plan(self, mock_logger, real_specialist):
        """Testa plano completamente vazio."""
        plan = {"plan_id": "empty", "tasks": []}
        result = real_specialist._evaluate_plan_internal(plan, {})

        assert result is not None
        assert result["confidence_score"] >= 0.0

    @patch("specialist.logger")
    def test_plan_with_missing_fields(self, mock_logger, real_specialist):
        """Testa plano com campos faltando."""
        plan = {"plan_id": "minimal"}
        result = real_specialist._evaluate_plan_internal(plan, {})

        assert result is not None
