"""
Unit tests para Extended Metrics.
"""

import pytest

from neural_hive_llm.registry.extended_metrics import (
    ComplianceInfo,
    Domain,
    ExtendedModelMetadata,
    ModelQualityScores,
    ReliabilityMetrics,
    UserFeedbackMetrics,
)


def test_model_quality_scores():
    """Testa scores de qualidade por domínio."""
    scores = ModelQualityScores(
        coding_score=0.9,
        analysis_score=0.85,
        reasoning_score=0.92,
        chat_score=0.88,
    )

    assert scores.coding_score == 0.9
    assert scores.analysis_score == 0.85
    assert scores.average_score == pytest.approx(0.8875, 0.01)


def test_get_score_for_domain():
    """Testa obtenção de score para domínio específico."""
    scores = ModelQualityScores(
        coding_score=0.9,
        analysis_score=0.85,
    )

    assert scores.get_score_for_domain("coding") == 0.9
    assert scores.get_score_for_domain("analysis") == 0.85
    assert scores.get_score_for_domain("chat") is None


def test_reliability_metrics():
    """Testa métricas de confiabilidade."""
    reliability = ReliabilityMetrics(
        success_rate=0.98,
        uptime_percentage=99.9,
        geographic_regions=["us", "eu"],
    )

    assert reliability.success_rate == 0.98
    assert reliability.uptime_percentage == 99.9
    assert "us" in reliability.geographic_regions


def test_compliance_info():
    """Testa informações de compliance."""
    compliance = ComplianceInfo(
        data_residency="eu",
        compliance_standards=["GDPR", "SOC2"],
        enterprise_tier=True,
        encryption_at_rest=True,
        encryption_in_transit=True,
    )

    assert compliance.data_residency == "eu"
    assert "GDPR" in compliance.compliance_standards
    assert compliance.enterprise_tier
    assert compliance.encryption_at_rest
    assert compliance.encryption_in_transit


def test_user_feedback_metrics():
    """Testa métricas de feedback do utilizador."""
    feedback = UserFeedbackMetrics(
        avg_rating=4.5,
        total_feedback_count=1000,
        helpful_percentage=85.0,
        task_completion_rate=0.92,
        user_satisfaction_score=0.88,
    )

    assert feedback.avg_rating == 4.5
    assert feedback.total_feedback_count == 1000
    assert feedback.helpful_percentage == 85.0
    assert feedback.task_completion_rate == 0.92
    assert feedback.user_satisfaction_score == 0.88


def test_extended_model_metadata():
    """Testa metadados extendidos do modelo."""
    quality_scores = ModelQualityScores(coding_score=0.9)
    reliability = ReliabilityMetrics(success_rate=0.98)
    compliance = ComplianceInfo(data_residency="us")
    feedback = UserFeedbackMetrics(avg_rating=4.5)

    extended = ExtendedModelMetadata(
        model_id="test-model",
        quality_scores=quality_scores,
        reliability=reliability,
        compliance=compliance,
        user_feedback=feedback,
    )

    assert extended.model_id == "test-model"
    assert extended.composite_quality_score > 0
    assert extended.operational_health_score > 0


def test_composite_quality_score():
    """Testa cálculo de score de qualidade composto."""
    quality_scores = ModelQualityScores(
        coding_score=0.9,
        analysis_score=0.85,
    )
    reliability = ReliabilityMetrics(success_rate=0.98)
    compliance = ComplianceInfo(compliance_standards=["SOC2"])
    feedback = UserFeedbackMetrics(user_satisfaction_score=0.88)

    extended = ExtendedModelMetadata(
        model_id="test-model",
        quality_scores=quality_scores,
        reliability=reliability,
        compliance=compliance,
        user_feedback=feedback,
    )

    # Score deve considerar qualidade, confiabilidade e feedback
    assert extended.composite_quality_score > 0
    assert extended.composite_quality_score <= 1.0


def test_operational_health_score():
    """Testa cálculo de score de saúde operacional."""
    reliability = ReliabilityMetrics(
        success_rate=0.98,
        uptime_percentage=99.9,
    )

    extended = ExtendedModelMetadata(
        model_id="test-model",
        quality_scores=ModelQualityScores(coding_score=0.9),
        reliability=reliability,
        compliance=ComplianceInfo(),
    )

    # Score deve considerar uptime, carga e sucesso
    assert extended.operational_health_score > 0
    assert extended.operational_health_score <= 1.0


def test_quality_scores_validation():
    """Testa validação de scores de qualidade."""
    # Scores válidos
    scores = ModelQualityScores(
        coding_score=0.9,
        analysis_score=0.85,
    )
    assert scores.coding_score == 0.9

    # Scores inválidos devem falhar na validação Pydantic
    with pytest.raises(ValueError):
        ModelQualityScores(coding_score=1.5)

    with pytest.raises(ValueError):
        ModelQualityScores(coding_score=-0.1)


def test_reliability_metrics_validation():
    """Testa validação de métricas de confiabilidade."""
    reliability = ReliabilityMetrics(
        success_rate=0.98,
        uptime_percentage=99.9,
    )
    assert reliability.success_rate == 0.98

    # Valores inválidos
    with pytest.raises(ValueError):
        ReliabilityMetrics(success_rate=1.5)

    with pytest.raises(ValueError):
        ReliabilityMetrics(uptime_percentage=101.0)


def test_user_feedback_validation():
    """Testa validação de feedback do utilizador."""
    feedback = UserFeedbackMetrics(
        avg_rating=4.5,
        total_feedback_count=100,
    )
    assert feedback.avg_rating == 4.5

    # Valores inválidos
    with pytest.raises(ValueError):
        UserFeedbackMetrics(avg_rating=6.0)

    with pytest.raises(ValueError):
        UserFeedbackMetrics(total_feedback_count=-10)


def test_extended_metadata_without_feedback():
    """Testa metadados extendidos sem feedback."""
    extended = ExtendedModelMetadata(
        model_id="test-model",
        quality_scores=ModelQualityScores(coding_score=0.9),
        reliability=ReliabilityMetrics(success_rate=0.98),
        compliance=ComplianceInfo(),
        user_feedback=None,
    )

    # Deve lidar com ausência de feedback
    assert extended.composite_quality_score > 0


def test_domain_enum():
    """Testa enum de domínios."""
    assert Domain.CODING.value == "coding"
    assert Domain.ANALYSIS.value == "analysis"
    assert Domain.CHAT.value == "chat"


def test_average_score_with_none_values():
    """Testa score médio com valores None."""
    scores = ModelQualityScores(
        coding_score=0.9,
        analysis_score=None,
        reasoning_score=None,
    )

    # Deve calcular média apenas com valores não-None
    assert scores.average_score == 0.9


def test_average_score_all_none():
    """Testa score médio quando todos são None."""
    scores = ModelQualityScores(
        coding_score=None,
        analysis_score=None,
        reasoning_score=None,
    )

    # Deve retornar 0 quando não há scores
    assert scores.average_score == 0.0
