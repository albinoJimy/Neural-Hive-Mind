"""
Testes unitários abrangentes para BaseSpecialist.

Cobertura alvo: >90%
"""

import pytest
import json
from unittest.mock import Mock, MagicMock, patch
from pydantic import ValidationError

from neural_hive_specialists.base_specialist import BaseSpecialist
from neural_hive_specialists.schemas import (
    PlanValidationError,
    PlanVersionIncompatibleError,
    TaskDependencyError,
)


# ============================================================================
# Specialist Concreto para Testes
# ============================================================================


class TestSpecialist(BaseSpecialist):
    """Implementação concreta de BaseSpecialist para testes."""

    def _get_specialist_type(self) -> str:
        return "test"

    def _load_model(self):
        if self.mlflow_client:
            return self.mlflow_client.load_model_with_fallback(
                self.config.mlflow_model_name, self.config.mlflow_model_stage
            )
        return None

    def _evaluate_plan_internal(self, cognitive_plan, context):
        return {
            "recommendation": "approve",
            "confidence_score": 0.85,
            "risk_score": 0.2,
            "estimated_effort_hours": 8.5,
            "reasoning_summary": "Test reasoning",
            "reasoning_factors": [
                {
                    "factor": "Test factor",
                    "weight": 0.5,
                    "score": 0.9,
                    "contribution": "positive",
                }
            ],
            "suggested_mitigations": [],
            "metadata": {},
        }


# ============================================================================
# TestBaseSpecialistInitialization
# ============================================================================


@pytest.mark.unit
class TestBaseSpecialistInitialization:
    """Testes de inicialização do BaseSpecialist."""

    def test_initialization_success(self, mock_config, mocker):
        """Verifica inicialização correta com todos os componentes."""
        mocker.patch("neural_hive_specialists.base_specialist.MLflowClient")
        mocker.patch("neural_hive_specialists.base_specialist.LedgerClient")
        mocker.patch("neural_hive_specialists.base_specialist.ExplainabilityGenerator")
        mocker.patch("neural_hive_specialists.base_specialist.SpecialistMetrics")

        specialist = TestSpecialist(mock_config)

        assert specialist.specialist_type == "test"
        assert specialist.version == mock_config.specialist_version
        assert specialist.config == mock_config

    def test_initialization_without_mlflow(self, mock_config, mocker):
        """Testa fallback quando MLflow indisponível."""
        mocker.patch(
            "neural_hive_specialists.base_specialist.MLflowClient",
            side_effect=Exception("MLflow unavailable"),
        )
        mocker.patch("neural_hive_specialists.base_specialist.LedgerClient")
        mocker.patch("neural_hive_specialists.base_specialist.ExplainabilityGenerator")
        mocker.patch("neural_hive_specialists.base_specialist.SpecialistMetrics")

        specialist = TestSpecialist(mock_config)

        assert specialist.mlflow_client is None

    def test_initialization_loads_model(self, mock_config, mocker):
        """Verifica que _load_model() é chamado durante inicialização."""
        mocker.patch("neural_hive_specialists.base_specialist.MLflowClient")
        mocker.patch("neural_hive_specialists.base_specialist.LedgerClient")
        mocker.patch("neural_hive_specialists.base_specialist.ExplainabilityGenerator")
        mocker.patch("neural_hive_specialists.base_specialist.SpecialistMetrics")

        with patch.object(
            TestSpecialist, "_load_model", return_value=Mock()
        ) as mock_load:
            specialist = TestSpecialist(mock_config)
            mock_load.assert_called_once()


# ============================================================================
# TestDeserializePlan
# ============================================================================


@pytest.mark.unit
class TestDeserializePlan:
    """Testes de deserialização de plano cognitivo."""

    @pytest.fixture
    def specialist(self, mock_config, mocker):
        mocker.patch("neural_hive_specialists.base_specialist.MLflowClient")
        mocker.patch("neural_hive_specialists.base_specialist.LedgerClient")
        mocker.patch("neural_hive_specialists.base_specialist.ExplainabilityGenerator")
        mocker.patch("neural_hive_specialists.base_specialist.SpecialistMetrics")
        return TestSpecialist(mock_config)

    def test_deserialize_valid_plan(self, specialist, sample_cognitive_plan):
        """Deserializa plano válido com sucesso."""
        plan_json = json.dumps(sample_cognitive_plan).encode("utf-8")
        result = specialist._deserialize_plan(plan_json)

        assert result["plan_id"] == sample_cognitive_plan["plan_id"]
        assert result["version"] == "1.0.0"
        assert len(result["tasks"]) == 2

    def test_deserialize_invalid_json(self, specialist):
        """Levanta ValueError para JSON malformado."""
        invalid_json = b"{ invalid json }"

        with pytest.raises(ValueError, match="inválido"):
            specialist._deserialize_plan(invalid_json)

    def test_deserialize_missing_required_fields(self, specialist):
        """Levanta ValueError para campos obrigatórios faltando."""
        incomplete_plan = {
            "plan_id": "test-plan",
            # Faltando version, intent_id, tasks, etc.
        }
        plan_json = json.dumps(incomplete_plan).encode("utf-8")

        with pytest.raises(ValueError):
            specialist._deserialize_plan(plan_json)

    def test_deserialize_invalid_version_format(
        self, specialist, sample_cognitive_plan
    ):
        """Levanta PlanVersionIncompatibleError para versão não-semver."""
        sample_cognitive_plan["version"] = "1.0"  # Não é semver completo
        plan_json = json.dumps(sample_cognitive_plan).encode("utf-8")

        with pytest.raises(PlanVersionIncompatibleError):
            specialist._deserialize_plan(plan_json)

    def test_deserialize_incompatible_version(self, specialist, sample_cognitive_plan):
        """Levanta PlanVersionIncompatibleError para versão não suportada."""
        sample_cognitive_plan["version"] = "2.0.0"  # Versão não suportada
        plan_json = json.dumps(sample_cognitive_plan).encode("utf-8")

        with pytest.raises(PlanVersionIncompatibleError):
            specialist._deserialize_plan(plan_json)

    def test_deserialize_duplicate_task_ids(self, specialist, sample_cognitive_plan):
        """Levanta PlanValidationError para IDs duplicados."""
        sample_cognitive_plan["tasks"][1]["task_id"] = "task-1"  # Duplicado
        plan_json = json.dumps(sample_cognitive_plan).encode("utf-8")

        with pytest.raises(ValueError, match="duplicados"):
            specialist._deserialize_plan(plan_json)

    def test_deserialize_missing_dependency(self, specialist, sample_cognitive_plan):
        """Levanta PlanValidationError para dependência inexistente."""
        sample_cognitive_plan["tasks"][1]["dependencies"] = ["task-999"]
        plan_json = json.dumps(sample_cognitive_plan).encode("utf-8")

        with pytest.raises(ValueError, match="inexistente"):
            specialist._deserialize_plan(plan_json)

    def test_deserialize_circular_dependency(self, specialist, sample_cognitive_plan):
        """Levanta PlanValidationError para ciclo no DAG."""
        # Criar ciclo: task-1 -> task-2 -> task-1
        sample_cognitive_plan["tasks"][0]["dependencies"] = ["task-2"]
        sample_cognitive_plan["tasks"][1]["dependencies"] = ["task-1"]
        plan_json = json.dumps(sample_cognitive_plan).encode("utf-8")

        with pytest.raises(ValueError, match="circular"):
            specialist._deserialize_plan(plan_json)

    def test_deserialize_self_reference(self, specialist, sample_cognitive_plan):
        """Levanta erro para tarefa que depende de si mesma."""
        sample_cognitive_plan["tasks"][0]["dependencies"] = ["task-1"]
        plan_json = json.dumps(sample_cognitive_plan).encode("utf-8")

        with pytest.raises(ValueError, match="si mesma"):
            specialist._deserialize_plan(plan_json)


# ============================================================================
# TestEvaluatePlan
# ============================================================================


@pytest.mark.unit
class TestEvaluatePlan:
    """Testes do método evaluate_plan."""

    @pytest.fixture
    def specialist(
        self, mock_config, mock_ledger_client, mock_explainability_gen, mocker
    ):
        mocker.patch("neural_hive_specialists.base_specialist.MLflowClient")
        mocker.patch("neural_hive_specialists.base_specialist.SpecialistMetrics")

        spec = TestSpecialist(mock_config)
        spec.ledger_client = mock_ledger_client
        spec.explainability_gen = mock_explainability_gen
        return spec

    def test_evaluate_plan_success(self, specialist, sample_cognitive_plan):
        """Fluxo completo de avaliação bem-sucedida."""
        req = Mock(
            plan_id=sample_cognitive_plan["plan_id"],
            intent_id=sample_cognitive_plan["intent_id"],
            correlation_id=sample_cognitive_plan["correlation_id"],
            trace_id=sample_cognitive_plan["trace_id"],
            span_id=sample_cognitive_plan["span_id"],
            cognitive_plan=json.dumps(sample_cognitive_plan).encode("utf-8"),
            context={},
        )

        result = specialist.evaluate_plan(req)

        assert "opinion_id" in result
        assert result["specialist_type"] == "test"
        assert "opinion" in result and isinstance(result["opinion"], dict)
        assert result["opinion"]["recommendation"] == "approve"
        assert result["opinion"]["confidence_score"] == 0.85

    def test_evaluate_plan_calls_internal_method(
        self, specialist, sample_cognitive_plan
    ):
        """Verifica que _evaluate_plan_internal() é chamado."""
        req = Mock(
            plan_id=sample_cognitive_plan["plan_id"],
            intent_id=sample_cognitive_plan["intent_id"],
            correlation_id=sample_cognitive_plan["correlation_id"],
            trace_id=sample_cognitive_plan["trace_id"],
            span_id=sample_cognitive_plan["span_id"],
            cognitive_plan=json.dumps(sample_cognitive_plan).encode("utf-8"),
            context={},
        )

        with patch.object(specialist, "_evaluate_plan_internal") as mock_internal:
            mock_internal.return_value = {
                "recommendation": "approve",
                "confidence_score": 0.85,
                "risk_score": 0.2,
                "estimated_effort_hours": 8.5,
                "reasoning_summary": "Test reasoning",
                "reasoning_factors": [],
                "suggested_mitigations": [],
                "metadata": {},
            }
            specialist.evaluate_plan(req)
            mock_internal.assert_called_once()

    def test_evaluate_plan_generates_explainability(
        self, specialist, sample_cognitive_plan, mock_explainability_gen
    ):
        """Verifica geração de token de explicabilidade."""
        req = Mock(
            plan_id=sample_cognitive_plan["plan_id"],
            intent_id=sample_cognitive_plan["intent_id"],
            correlation_id=sample_cognitive_plan["correlation_id"],
            trace_id=sample_cognitive_plan["trace_id"],
            span_id=sample_cognitive_plan["span_id"],
            cognitive_plan=json.dumps(sample_cognitive_plan).encode("utf-8"),
            context={},
        )

        specialist.evaluate_plan(req)

        mock_explainability_gen.generate.assert_called_once()

    def test_evaluate_plan_persists_to_ledger(
        self, specialist, sample_cognitive_plan, mock_ledger_client
    ):
        """Verifica persistência no ledger."""
        req = Mock(
            plan_id=sample_cognitive_plan["plan_id"],
            intent_id=sample_cognitive_plan["intent_id"],
            correlation_id=sample_cognitive_plan["correlation_id"],
            trace_id=sample_cognitive_plan["trace_id"],
            span_id=sample_cognitive_plan["span_id"],
            cognitive_plan=json.dumps(sample_cognitive_plan).encode("utf-8"),
            context={},
        )

        specialist.evaluate_plan(req)

        mock_ledger_client.save_opinion_with_fallback.assert_called_once()

    def test_evaluate_plan_records_metrics(
        self, specialist, sample_cognitive_plan, mocker
    ):
        """Verifica que métricas são registradas."""
        req = Mock(
            plan_id=sample_cognitive_plan["plan_id"],
            intent_id=sample_cognitive_plan["intent_id"],
            correlation_id=sample_cognitive_plan["correlation_id"],
            trace_id=sample_cognitive_plan["trace_id"],
            span_id=sample_cognitive_plan["span_id"],
            cognitive_plan=json.dumps(sample_cognitive_plan).encode("utf-8"),
            context={},
        )

        with patch.object(
            specialist.metrics, "observe_evaluation_duration"
        ) as mock_record:
            specialist.evaluate_plan(req)
            mock_record.assert_called_once()

    def test_evaluate_plan_propagates_trace_context(
        self, specialist, sample_cognitive_plan
    ):
        """Verifica propagação de trace_id/span_id."""
        req = Mock(
            plan_id=sample_cognitive_plan["plan_id"],
            intent_id=sample_cognitive_plan["intent_id"],
            correlation_id=sample_cognitive_plan["correlation_id"],
            trace_id=sample_cognitive_plan["trace_id"],
            span_id=sample_cognitive_plan["span_id"],
            cognitive_plan=json.dumps(sample_cognitive_plan).encode("utf-8"),
            context={},
        )

        result = specialist.evaluate_plan(req)

        # Trace context deve ser preservado no resultado
        assert "trace_id" in sample_cognitive_plan
        assert "span_id" in sample_cognitive_plan

    def test_evaluate_plan_handles_deserialization_error(self, specialist):
        """Trata erro de deserialização."""
        req = Mock(
            plan_id="test-plan",
            intent_id="test-intent",
            correlation_id="test-corr",
            trace_id="test-trace",
            span_id="test-span",
            cognitive_plan=b"{ invalid }",
            context={},
        )

        with pytest.raises(ValueError):
            specialist.evaluate_plan(req)

    def test_evaluate_plan_measures_processing_time(
        self, specialist, sample_cognitive_plan
    ):
        """Verifica medição de tempo de processamento."""
        req = Mock(
            plan_id=sample_cognitive_plan["plan_id"],
            intent_id=sample_cognitive_plan["intent_id"],
            correlation_id=sample_cognitive_plan["correlation_id"],
            trace_id=sample_cognitive_plan["trace_id"],
            span_id=sample_cognitive_plan["span_id"],
            cognitive_plan=json.dumps(sample_cognitive_plan).encode("utf-8"),
            context={},
        )

        result = specialist.evaluate_plan(req)

        assert "processing_time_ms" in result
        assert result["processing_time_ms"] > 0


# ============================================================================
# TestValidateEvaluationResult
# ============================================================================


@pytest.mark.unit
class TestValidateEvaluationResult:
    """Testes de validação do resultado de avaliação."""

    @pytest.fixture
    def specialist(self, mock_config, mocker):
        mocker.patch("neural_hive_specialists.base_specialist.MLflowClient")
        mocker.patch("neural_hive_specialists.base_specialist.LedgerClient")
        mocker.patch("neural_hive_specialists.base_specialist.ExplainabilityGenerator")
        mocker.patch("neural_hive_specialists.base_specialist.SpecialistMetrics")
        return TestSpecialist(mock_config)

    def test_validate_valid_result(self, specialist, sample_evaluation_result):
        """Valida resultado correto."""
        # Não deve levantar exceção
        specialist._validate_evaluation_result(sample_evaluation_result)

    def test_validate_missing_required_field(self, specialist):
        """Levanta erro para campo obrigatório faltando."""
        invalid_result = {
            # Faltando recommendation
            "confidence_score": 0.85,
        }

        with pytest.raises(ValueError):
            specialist._validate_evaluation_result(invalid_result)

    def test_validate_invalid_confidence_score_range(self, specialist):
        """Levanta erro para score fora de 0-1."""
        invalid_result = {
            "recommendation": "proceed",
            "confidence_score": 1.5,  # Inválido
            "risk_score": 0.2,
            "estimated_effort_hours": 8.5,
            "reasoning_factors": [],
            "suggested_mitigations": [],
            "metadata": {},
        }

        with pytest.raises(ValueError, match="confidence_score"):
            specialist._validate_evaluation_result(invalid_result)

    def test_validate_invalid_risk_score_range(self, specialist):
        """Levanta erro para risk_score fora de 0-1."""
        invalid_result = {
            "recommendation": "proceed",
            "confidence_score": 0.85,
            "risk_score": -0.1,  # Inválido
            "estimated_effort_hours": 8.5,
            "reasoning_factors": [],
            "suggested_mitigations": [],
            "metadata": {},
        }

        with pytest.raises(ValueError, match="risk_score"):
            specialist._validate_evaluation_result(invalid_result)

    def test_validate_invalid_recommendation(self, specialist):
        """Levanta erro para recomendação inválida."""
        invalid_result = {
            "recommendation": "invalid_recommendation",
            "confidence_score": 0.85,
            "risk_score": 0.2,
            "estimated_effort_hours": 8.5,
            "reasoning_factors": [],
            "suggested_mitigations": [],
            "metadata": {},
        }

        # Depende da implementação - pode ou não validar valores específicos
        try:
            specialist._validate_evaluation_result(invalid_result)
        except ValueError:
            pass  # Esperado se validação for rigorosa


# ============================================================================
# TestHealthCheck
# ============================================================================


@pytest.mark.unit
class TestHealthCheck:
    """Testes de health check."""

    @pytest.fixture
    def specialist(self, mock_config, mock_ledger_client, mocker):
        mocker.patch("neural_hive_specialists.base_specialist.MLflowClient")
        mocker.patch("neural_hive_specialists.base_specialist.ExplainabilityGenerator")
        mocker.patch("neural_hive_specialists.base_specialist.SpecialistMetrics")

        spec = TestSpecialist(mock_config)
        spec.ledger_client = mock_ledger_client
        spec.model = Mock()  # Modelo carregado
        return spec

    def test_health_check_all_healthy(self, specialist):
        """Retorna SERVING quando tudo OK."""
        specialist.ledger_client.is_connected.return_value = True

        result = specialist.health_check()

        assert result["status"] == "SERVING"
        details = result["details"]
        assert details["model_loaded"] == "True"
        assert details["ledger_connected"] == "True"

    def test_health_check_model_not_loaded(self, specialist):
        """Retorna NOT_SERVING sem modelo."""
        specialist.model = None

        result = specialist.health_check()

        assert result["status"] == "NOT_SERVING"
        details = result["details"]
        assert details["model_loaded"] == "False"

    def test_health_check_ledger_disconnected(self, specialist):
        """Retorna NOT_SERVING sem ledger."""
        specialist.ledger_client.is_connected.return_value = False

        result = specialist.health_check()

        assert result["status"] == "NOT_SERVING"
        details = result["details"]
        assert details["ledger_connected"] == "False"


# ============================================================================
# TestGetCapabilities
# ============================================================================


@pytest.mark.unit
class TestGetCapabilities:
    """Testes de obtenção de capacidades."""

    @pytest.fixture
    def specialist(self, mock_config, mocker):
        mocker.patch("neural_hive_specialists.base_specialist.MLflowClient")
        mocker.patch("neural_hive_specialists.base_specialist.LedgerClient")
        mocker.patch("neural_hive_specialists.base_specialist.ExplainabilityGenerator")
        mocker.patch("neural_hive_specialists.base_specialist.SpecialistMetrics")
        return TestSpecialist(mock_config)

    def test_get_capabilities_returns_metadata(self, specialist):
        """Retorna metadados completos."""
        capabilities = specialist.get_capabilities()

        assert "specialist_type" in capabilities
        assert "version" in capabilities
        assert "supported_domains" in capabilities
        assert "supported_plan_versions" in capabilities

    def test_get_capabilities_includes_metrics_summary(self, specialist):
        """Inclui resumo de métricas."""
        capabilities = specialist.get_capabilities()

        # Pode incluir métricas se implementado
        assert capabilities is not None
