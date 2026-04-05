"""
Testes unitários para detecção de método de decisão (GAPS-03 SPECIALIST-002).

Testa a inferência de ML vs heurística nas opiniões dos especialistas.
"""

# Importar módulo diretamente para evitar __init__.py issues
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "decision_method",
    Path(__file__).parent.parent / "src" / "models" / "decision_method.py"
)
decision_method_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(decision_method_module)

DecisionMethod = decision_method_module.DecisionMethod
infer_decision_method = decision_method_module.infer_decision_method
get_method_description = decision_method_module.get_method_description


class TestDecisionMethodEnum:
    """Testes do enum DecisionMethod."""

    def test_all_methods_defined(self):
        """Verifica que todos os métodos esperados estão definidos."""
        expected = {"ml", "heuristic", "hybrid"}
        actual = {method.value for method in DecisionMethod}
        assert actual == expected

    def test_method_values_correct(self):
        """Verifica valores dos métodos."""
        assert DecisionMethod.ML.value == "ml"
        assert DecisionMethod.HEURISTIC.value == "heuristic"
        assert DecisionMethod.HYBRID.value == "hybrid"


class TestInferDecisionMethod:
    """Testes da função infer_decision_method."""

    def test_opinion_without_ml_fields_returns_heuristic(self):
        """Opinião sem campos ML deve retornar 'heuristic'."""
        opinion = {
            "confidence_score": 0.8,
            "risk_score": 0.2,
            "recommendation": "approve"
        }
        result = infer_decision_method(opinion)
        assert result == DecisionMethod.HEURISTIC

    def test_opinion_with_ml_confidence_returns_ml(self):
        """Opinião com ml_confidence deve retornar 'ml'."""
        opinion = {
            "confidence_score": 0.8,
            "ml_confidence": 0.85,
            "recommendation": "approve"
        }
        result = infer_decision_method(opinion)
        assert result == DecisionMethod.ML

    def test_opinion_with_model_version_returns_ml(self):
        """Opinião com model_version deve retornar 'ml'."""
        opinion = {
            "confidence_score": 0.8,
            "model_version": "v1.2.3",
            "recommendation": "approve"
        }
        result = infer_decision_method(opinion)
        assert result == DecisionMethod.ML

    def test_opinion_with_ml_model_id_returns_ml(self):
        """Opinião com ml_model_id deve retornar 'ml'."""
        opinion = {
            "confidence_score": 0.8,
            "ml_model_id": "model-abc-123",
            "recommendation": "approve"
        }
        result = infer_decision_method(opinion)
        assert result == DecisionMethod.ML

    def test_opinion_with_heuristic_confidence_returns_heuristic(self):
        """Opinião com heuristic_confidence deve retornar 'heuristic'."""
        opinion = {
            "confidence_score": 0.8,
            "heuristic_confidence": 0.75,
            "recommendation": "approve"
        }
        result = infer_decision_method(opinion)
        assert result == DecisionMethod.HEURISTIC

    def test_opinion_with_rule_id_returns_heuristic(self):
        """Opinião com rule_id deve retornar 'heuristic'."""
        opinion = {
            "confidence_score": 0.8,
            "rule_id": "rule-business-001",
            "recommendation": "approve"
        }
        result = infer_decision_method(opinion)
        assert result == DecisionMethod.HEURISTIC

    def test_opinion_with_both_ml_and_heuristic_returns_hybrid(self):
        """Opinião com campos ML e heurística deve retornar 'hybrid'."""
        opinion = {
            "confidence_score": 0.8,
            "ml_confidence": 0.85,
            "heuristic_confidence": 0.75,
            "recommendation": "approve"
        }
        result = infer_decision_method(opinion)
        assert result == DecisionMethod.HYBRID

    def test_opinion_with_ml_and_rule_id_returns_hybrid(self):
        """Opinião com ML e rule_id deve retornar 'hybrid'."""
        opinion = {
            "confidence_score": 0.8,
            "model_version": "v1.2.3",
            "rule_id": "rule-business-001",
            "recommendation": "approve"
        }
        result = infer_decision_method(opinion)
        assert result == DecisionMethod.HYBRID

    def test_empty_opinion_returns_heuristic(self):
        """Opinião vazia deve retornar 'heuristic' (fallback seguro)."""
        opinion = {}
        result = infer_decision_method(opinion)
        assert result == DecisionMethod.HEURISTIC

    def test_none_opinion_returns_heuristic(self):
        """Opinião None deve retornar 'heuristic' (fallback seguro)."""
        result = infer_decision_method(None)
        assert result == DecisionMethod.HEURISTIC

    def test_invalid_dict_returns_heuristic(self):
        """Dict inválido deve retornar 'heuristic' (fallback seguro)."""
        result = infer_decision_method("not_a_dict")
        assert result == DecisionMethod.HEURISTIC

    @pytest.mark.parametrize("ml_indicator", [
        "ml_confidence",
        "model_version",
        "ml_model_id",
        "ml_model_name",
        "ml_prediction",
        "ml_probability",
        "ml_features",
        "inference_result",
    ])
    def test_all_ml_indicators_detected(self, ml_indicator):
        """Todos os indicadores ML devem ser detectados."""
        opinion = {
            "confidence_score": 0.8,
            ml_indicator: "some_value",
            "recommendation": "approve"
        }
        result = infer_decision_method(opinion)
        assert result == DecisionMethod.ML

    @pytest.mark.parametrize("heuristic_indicator", [
        "heuristic_confidence",
        "rule_id",
        "rule_name",
        "heuristic_score",
        "rule_based_decision",
        "heuristic_result",
    ])
    def test_all_heuristic_indicators_detected(self, heuristic_indicator):
        """Todos os indicadores heurísticos devem ser detectados."""
        opinion = {
            "confidence_score": 0.8,
            heuristic_indicator: "some_value",
            "recommendation": "approve"
        }
        result = infer_decision_method(opinion)
        assert result == DecisionMethod.HEURISTIC


class TestGetMethodDescription:
    """Testes da função get_method_description."""

    def test_ml_description(self):
        """Descrição de ML deve ser legível."""
        desc = get_method_description(DecisionMethod.ML)
        assert "Machine Learning" in desc

    def test_heuristic_description(self):
        """Descrição heurística deve ser legível."""
        desc = get_method_description(DecisionMethod.HEURISTIC)
        assert "regras" in desc.lower() or "heurística" in desc.lower()

    def test_hybrid_description(self):
        """Descrição híbrida deve mencionar ambos."""
        desc = get_method_description(DecisionMethod.HYBRID)
        assert "ML" in desc or "combinada" in desc.lower()

    def test_unknown_method_returns_default(self):
        """Método desconhecido retorna descrição padrão."""
        # Enum inválido
        desc = get_method_description("invalid")
        assert "desconhecido" in desc.lower()


class TestSpecialistVoteWithDecisionMethod:
    """Testes de integração com SpecialistVote."""

    def test_specialist_vote_accepts_decision_method(self):
        """SpecialistVote deve aceitar campo decision_method."""
        from src.models.consolidated_decision import SpecialistVote

        vote = SpecialistVote(
            specialist_type="business",
            opinion_id="op-123",
            confidence_score=0.85,
            risk_score=0.15,
            recommendation="approve",
            weight=0.2,
            processing_time_ms=100,
            decision_method="ml"
        )
        assert vote.decision_method == "ml"

    def test_specialist_vote_without_decision_method_defaults_to_none(self):
        """SpecialistVote sem decision_method deve default para None."""
        from src.models.consolidated_decision import SpecialistVote

        vote = SpecialistVote(
            specialist_type="business",
            opinion_id="op-123",
            confidence_score=0.85,
            risk_score=0.15,
            recommendation="approve",
            weight=0.2,
            processing_time_ms=100
        )
        assert vote.decision_method is None

    def test_specialist_vote_to_avro_includes_decision_method(self):
        """to_avro_dict deve incluir decision_method."""
        from src.models.consolidated_decision import SpecialistVote

        vote = SpecialistVote(
            specialist_type="business",
            opinion_id="op-123",
            confidence_score=0.85,
            risk_score=0.15,
            recommendation="approve",
            weight=0.2,
            processing_time_ms=100,
            decision_method="hybrid"
        )

        # Criar uma ConsolidatedDecision para testar to_avro_dict

        from src.models.consolidated_decision import (
            ConsensusMethod,
            ConsensusMetrics,
            ConsolidatedDecision,
            DecisionType,
        )

        decision = ConsolidatedDecision(
            plan_id="plan-123",
            intent_id="intent-123",
            correlation_id="corr-123",
            final_decision=DecisionType.APPROVE,
            consensus_method=ConsensusMethod.BAYESIAN,
            aggregated_confidence=0.85,
            aggregated_risk=0.15,
            specialist_votes=[vote],
            consensus_metrics=ConsensusMetrics(
                divergence_score=0.1,
                convergence_time_ms=200,
                unanimous=True,
                fallback_used=False,
                pheromone_strength=0.5,
                bayesian_confidence=0.85,
                voting_confidence=0.9
            ),
            explainability_token="explain-123",
            reasoning_summary="Test summary"
        )

        avro_dict = decision.to_avro_dict()
        assert avro_dict["specialist_votes"][0]["decision_method"] == "hybrid"
