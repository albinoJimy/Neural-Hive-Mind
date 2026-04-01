"""
Testes unitários para models do evolution_hooks.

Este módulo testa todos os modelos Pydantic usados pelo sistema
Evolution Hooks.
"""

import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

from neural_hive_specialists.evolution_hooks.models import (
    Fingerprint,
    TaskCountRange,
    DurationRange,
    EvolutionEvaluation,
    PatternMetrics,
    FeedbackData,
    FeedbackOutcome,
    FeedbackSource,
    DEFAULT_WEIGHTS,
    PatternRecord,
    FeedbackMessage,
)


class TestFingerprint:
    """Testes para Fingerprint."""

    def test_create_fingerprint_minimal(self):
        """Cria fingerprint com campos mínimos."""
        fingerprint = Fingerprint(
            domain="technical",
            priority="high",
            task_count_range=TaskCountRange.MEDIUM,
            avg_dependency_count=0.0,
            complexity_signature="TEST"
        )
        assert fingerprint.domain == "technical"
        assert fingerprint.priority == "high"
        assert fingerprint.task_count_range == TaskCountRange.MEDIUM
        assert fingerprint.task_types == []
        assert fingerprint.has_conditional_deps is False
        assert fingerprint.complexity_signature == "TEST"

    def test_create_fingerprint_full(self):
        """Cria fingerprint com todos os campos."""
        fingerprint = Fingerprint(
            domain="business",
            priority="normal",
            task_count_range=TaskCountRange.LARGE,
            task_types=["BUILD", "TEST", "DEPLOY", "MONITOR"],
            avg_dependency_count=2.5,
            has_conditional_deps=True,
            estimated_duration_range=DurationRange.LONG,
            complexity_signature="B-L-B-T-D-M"
        )
        assert len(fingerprint.task_types) == 4
        assert fingerprint.avg_dependency_count == 2.5
        assert fingerprint.has_conditional_deps is True
        assert fingerprint.estimated_duration_range == DurationRange.LONG

    def test_fingerprint_model_dump(self):
        """Testa serialização do fingerprint."""
        fingerprint = Fingerprint(
            domain="technical",
            priority="high",
            task_count_range=TaskCountRange.MEDIUM,
            task_types=["BUILD", "TEST"],
            avg_dependency_count=1.0,
            complexity_signature="T-M-B-T"
        )
        data = fingerprint.model_dump()
        assert data["domain"] == "technical"
        assert data["task_count_range"] == "medium"  # enum value
        assert isinstance(data["task_types"], list)


class TestDefaultWeights:
    """Testes para DEFAULT_WEIGHTS."""

    def test_default_weights_sum_to_one(self):
        """Verifica que pesos somam 1.0."""
        total = sum(DEFAULT_WEIGHTS.values())
        assert total == pytest.approx(1.0, abs=0.01)

    def test_default_weights_have_all_five_dimensions(self):
        """Verifica que todas as 5 dimensões estão presentes."""
        expected_keys = {
            "maintainability",
            "scalability",
            "extensibility",
            "modularity",
            "tech_debt_prevention"
        }
        assert set(DEFAULT_WEIGHTS.keys()) == expected_keys

    def test_default_weights_match_specialist(self):
        """
        Verifica que pesos batem com EvolutionSpecialist.

        services/specialist-evolution/src/specialist.py linhas 132-138
        """
        assert DEFAULT_WEIGHTS["maintainability"] == 0.25
        assert DEFAULT_WEIGHTS["scalability"] == 0.25
        assert DEFAULT_WEIGHTS["extensibility"] == 0.20
        assert DEFAULT_WEIGHTS["modularity"] == 0.15
        assert DEFAULT_WEIGHTS["tech_debt_prevention"] == 0.15


class TestEvolutionEvaluation:
    """Testes para EvolutionEvaluation."""

    def test_create_evaluation_minimal(self):
        """Cria avaliação com campos mínimos."""
        evaluation = EvolutionEvaluation(
            confidence_score=0.75,
            risk_score=0.25,
            recommendation="approve"
        )
        assert evaluation.confidence_score == 0.75
        assert evaluation.risk_score == 0.25
        assert evaluation.recommendation == "approve"
        assert evaluation.weights_used == DEFAULT_WEIGHTS

    def test_create_evaluation_full(self):
        """Cria avaliação com todos os campos."""
        custom_weights = {**DEFAULT_WEIGHTS, "maintainability": 0.30}
        evaluation = EvolutionEvaluation(
            confidence_score=0.80,
            risk_score=0.20,
            recommendation="approve",
            weights_used=custom_weights,
            reasoning_factors=[
                {
                    "factor_name": "maintainability",
                    "weight": 0.30,
                    "score": 0.8,
                    "description": "Good maintainability"
                }
            ]
        )
        assert evaluation.weights_used["maintainability"] == 0.30
        assert len(evaluation.reasoning_factors) == 1

    def test_evaluation_invalid_confidence(self):
        """Rejeita confiança fora do range [0, 1]."""
        with pytest.raises(ValidationError):
            EvolutionEvaluation(
                confidence_score=1.5,
                risk_score=0.25,
                recommendation="approve"
            )

    def test_evaluation_invalid_risk(self):
        """Rejeita risco fora do range [0, 1]."""
        with pytest.raises(ValidationError):
            EvolutionEvaluation(
                confidence_score=0.75,
                risk_score=-0.1,
                recommendation="approve"
            )

    def test_evaluation_invalid_recommendation(self):
        """Rejeita recomendação inválida."""
        with pytest.raises(ValidationError):
            EvolutionEvaluation(
                confidence_score=0.75,
                risk_score=0.25,
                recommendation="invalid_recommendation"
            )

    def test_evaluation_valid_recommendations(self):
        """Aceita todas as recomendações válidas."""
        valid_recommendations = ["approve", "reject", "review_required", "conditional"]
        for rec in valid_recommendations:
            evaluation = EvolutionEvaluation(
                confidence_score=0.75,
                risk_score=0.25,
                recommendation=rec
            )
            assert evaluation.recommendation == rec


class TestPatternMetrics:
    """Testes para PatternMetrics."""

    def test_create_metrics_default(self):
        """Cria métricas com valores default."""
        metrics = PatternMetrics()
        assert metrics.times_matched == 0
        assert metrics.success_rate == 0.5
        assert isinstance(metrics.last_updated, datetime)

    def test_create_metrics_custom(self):
        """Cria métricas com valores customizados."""
        now = datetime.now(timezone.utc)
        metrics = PatternMetrics(
            times_matched=100,
            success_rate=0.85,
            last_updated=now
        )
        assert metrics.times_matched == 100
        assert metrics.success_rate == 0.85
        assert metrics.last_updated == now

    def test_metrics_validation(self):
        """Valida constraints de métricas."""
        # times_matched deve ser >= 0
        with pytest.raises(ValidationError):
            PatternMetrics(times_matched=-1)

        # success_rate deve estar entre 0 e 1
        with pytest.raises(ValidationError):
            PatternMetrics(success_rate=1.5)


class TestFeedbackData:
    """Testes para FeedbackData."""

    def test_create_feedback_minimal(self):
        """Cria feedback com campos mínimos."""
        feedback = FeedbackData(
            outcome=FeedbackOutcome.APPROVE,
            source=FeedbackSource.HUMAN
        )
        assert feedback.outcome == FeedbackOutcome.APPROVE
        assert feedback.source == FeedbackSource.HUMAN
        assert feedback.reasoning is None
        assert isinstance(feedback.timestamp, datetime)

    def test_create_feedback_full(self):
        """Cria feedback com todos os campos."""
        feedback = FeedbackData(
            outcome=FeedbackOutcome.REJECT,
            source=FeedbackSource.AUTOMATED,
            reasoning="Failed validation",
            corrected_weights={"maintainability": 0.30}
        )
        assert feedback.outcome == FeedbackOutcome.REJECT
        assert feedback.source == FeedbackSource.AUTOMATED
        assert feedback.reasoning == "Failed validation"
        assert feedback.corrected_weights == {"maintainability": 0.30}

    def test_feedback_enum_values(self):
        """Testa valores de enums de feedback."""
        # Testar todos os outcomes
        assert FeedbackOutcome.APPROVE.value == "approve"
        assert FeedbackOutcome.REJECT.value == "reject"

        # Testar todas as sources
        assert FeedbackSource.HUMAN.value == "human"
        assert FeedbackSource.AUTOMATED.value == "automated"
        assert FeedbackSource.SYSTEM.value == "system"


class TestPatternRecord:
    """Testes para PatternRecord."""

    def test_create_record_minimal(self):
        """Cria registro com campos mínimos."""
        fingerprint = Fingerprint(
            domain="technical",
            priority="high",
            task_count_range=TaskCountRange.MEDIUM,
            avg_dependency_count=0.0,
            complexity_signature="TEST"
        )
        evaluation = EvolutionEvaluation(
            confidence_score=0.75,
            risk_score=0.25,
            recommendation="approve"
        )

        record = PatternRecord(
            plan_id="plan-123",
            fingerprint=fingerprint,
            evaluation=evaluation
        )
        assert record.plan_id == "plan-123"
        assert record.feedback is None
        assert record.metrics.times_matched == 0

    def test_create_record_full(self):
        """Cria registro com todos os campos."""
        fingerprint = Fingerprint(
            domain="technical",
            priority="high",
            task_count_range=TaskCountRange.MEDIUM,
            avg_dependency_count=1.5,
            complexity_signature="TEST"
        )
        evaluation = EvolutionEvaluation(
            confidence_score=0.75,
            risk_score=0.25,
            recommendation="approve"
        )
        feedback = FeedbackData(
            outcome=FeedbackOutcome.APPROVE,
            source=FeedbackSource.HUMAN
        )

        record = PatternRecord(
            plan_id="plan-123",
            id="record-456",
            fingerprint=fingerprint,
            evaluation=evaluation,
            feedback=feedback,
            metrics=PatternMetrics(times_matched=10, success_rate=0.8)
        )
        assert record.id == "record-456"
        assert record.feedback is not None
        assert record.metrics.times_matched == 10


class TestFeedbackMessage:
    """Testes para FeedbackMessage."""

    def test_create_feedback_message(self):
        """Cria mensagem de feedback Kafka."""
        fingerprint = Fingerprint(
            domain="technical",
            priority="high",
            task_count_range=TaskCountRange.MEDIUM,
            task_types=["BUILD", "TEST"],
            avg_dependency_count=1.0,
            complexity_signature="T-M-B-T"
        )
        evaluation = EvolutionEvaluation(
            confidence_score=0.75,
            risk_score=0.25,
            recommendation="approve"
        )
        feedback = FeedbackData(
            outcome=FeedbackOutcome.APPROVE,
            source=FeedbackSource.HUMAN
        )

        message = FeedbackMessage(
            plan_id="plan-123",
            fingerprint=fingerprint,
            evaluation=evaluation,
            feedback=feedback
        )
        assert message.plan_id == "plan-123"
        assert message.fingerprint.domain == "technical"
        assert message.evaluation.confidence_score == 0.75
        assert message.feedback.outcome == FeedbackOutcome.APPROVE

    def test_feedback_message_serialization(self):
        """Testa serialização da mensagem de feedback."""
        message = FeedbackMessage(
            plan_id="plan-123",
            fingerprint=Fingerprint(
                domain="technical",
                priority="high",
                task_count_range=TaskCountRange.MEDIUM,
                avg_dependency_count=0.0,
                complexity_signature="TEST"
            ),
            evaluation=EvolutionEvaluation(
                confidence_score=0.75,
                risk_score=0.25,
                recommendation="approve"
            ),
            feedback=FeedbackData(
                outcome=FeedbackOutcome.APPROVE,
                source=FeedbackSource.HUMAN
            )
        )
        data = message.model_dump()
        assert data["plan_id"] == "plan-123"
        assert "fingerprint" in data
        assert "evaluation" in data
        assert "feedback" in data


class TestEdgeCases:
    """Testes de casos extremos."""

    def test_fingerprint_empty_task_types(self):
        """Fingerprint com lista vazia de task_types."""
        fingerprint = Fingerprint(
            domain="technical",
            priority="low",
            task_count_range=TaskCountRange.SMALL,
            task_types=[],
            avg_dependency_count=0.0,
            complexity_signature="T-S"
        )
        assert fingerprint.task_types == []

    def test_evaluation_zero_scores(self):
        """Avaliação com scores zero."""
        evaluation = EvolutionEvaluation(
            confidence_score=0.0,
            risk_score=0.0,
            recommendation="reject"
        )
        assert evaluation.confidence_score == 0.0
        assert evaluation.risk_score == 0.0

    def test_evaluation_perfect_scores(self):
        """Avaliação com scores perfeitos."""
        evaluation = EvolutionEvaluation(
            confidence_score=1.0,
            risk_score=1.0,
            recommendation="approve"
        )
        assert evaluation.confidence_score == 1.0
        assert evaluation.risk_score == 1.0

    def test_pattern_record_copy_weights(self):
        """Garante que weights_used é uma cópia, não referência."""
        evaluation1 = EvolutionEvaluation(
            confidence_score=0.75,
            risk_score=0.25,
            recommendation="approve"
        )
        evaluation1.weights_used["maintainability"] = 0.5

        evaluation2 = EvolutionEvaluation(
            confidence_score=0.75,
            risk_score=0.25,
            recommendation="approve"
        )
        # Deve ter valor default, não o modificado
        assert evaluation2.weights_used["maintainability"] == 0.25
