"""Unit tests for impact models."""

from datetime import timezone

import pytest
from src.models.impact import (
    BatchImpactAnalysisRequest,
    ExperimentCorrelation,
    ExperimentImpact,
    ImpactAnalysisRequest,
    ImpactCategory,
    ImpactDirection,
    ImpactMagnitude,
    ImpactTimeframe,
    LongTermImpact,
    MetricImpact,
    ShortTermImpact,
)

UTC = UTC


@pytest.mark.unit()
class TestMetricImpact:
    """Test suite for MetricImpact model."""

    def test_create_metric_impact(self):
        """Test creating a metric impact."""
        impact = MetricImpact(
            metric_name="error_rate",
            baseline_value=0.05,
            post_experiment_value=0.045,
            absolute_change=-0.005,
            relative_change_percent=-10.0,
            statistical_significance=True,
            confidence_interval=(0.043, 0.047),
            p_value=0.01,
        )

        assert impact.metric_name == "error_rate"
        assert impact.baseline_value == 0.05
        assert impact.post_experiment_value == 0.045
        assert impact.relative_change_percent == -10.0
        assert impact.statistical_significance is True


@pytest.mark.unit()
class TestShortTermImpact:
    """Test suite for ShortTermImpact model."""

    def test_create_short_term_impact(self):
        """Test creating short-term impact."""
        impact = ShortTermImpact(
            timeframe_days=7,
            immediate_effects=["Error rate decreased by 10%"],
            metric_impacts={},
            system_stability="improved",
            error_rate_change=-10.0,
        )

        assert impact.timeframe_days == 7
        assert len(impact.immediate_effects) == 1
        assert impact.system_stability == "improved"
        assert impact.error_rate_change == -10.0


@pytest.mark.unit()
class TestLongTermImpact:
    """Test suite for LongTermImpact model."""

    def test_create_long_term_impact(self):
        """Test creating long-term impact."""
        impact = LongTermImpact(
            timeframe_days=90,
            sustained_effects=["Sustained error rate reduction"],
            cumulative_benefit=0.15,
            degradation_detected=False,
            adaptation_observed=True,
            trend_analysis={"error_rate": "decreasing"},
        )

        assert impact.timeframe_days == 90
        assert impact.degradation_detected is False
        assert impact.adaptation_observed is True
        assert "error_rate" in impact.trend_analysis


@pytest.mark.unit()
class TestExperimentImpact:
    """Test suite for ExperimentImpact model."""

    def test_create_experiment_impact(self):
        """Test creating experiment impact."""
        impact = ExperimentImpact(
            experiment_id="test-exp-001",
            hypothesis_id="test-hyp-001",
            overall_direction=ImpactDirection.POSITIVE,
            overall_magnitude=ImpactMagnitude.HIGH,
            categories=[ImpactCategory.PERFORMANCE, ImpactCategory.RELIABILITY],
            recommendation="PROMOTE: Strong positive impact detected.",
            confidence_level=0.95,
        )

        assert impact.experiment_id == "test-exp-001"
        assert impact.overall_direction == ImpactDirection.POSITIVE
        assert impact.overall_magnitude == ImpactMagnitude.HIGH
        assert len(impact.categories) == 2
        assert impact.confidence_level == 0.95

    def test_to_dict(self):
        """Test converting impact to dict."""
        impact = ExperimentImpact(
            experiment_id="test-exp-001",
            overall_direction=ImpactDirection.POSITIVE,
            overall_magnitude=ImpactMagnitude.MEDIUM,
            categories=[ImpactCategory.PERFORMANCE],
            recommendation="ACCEPT: Positive impact.",
            confidence_level=0.8,
        )

        data = impact.to_dict()
        assert "experiment_id" in data
        assert data["experiment_id"] == "test-exp-001"
        assert "overall_direction" in data


@pytest.mark.unit()
class TestImpactAnalysisRequest:
    """Test suite for ImpactAnalysisRequest model."""

    def test_create_request(self):
        """Test creating analysis request."""
        request = ImpactAnalysisRequest(
            experiment_id="test-exp-001",
            timeframes=[ImpactTimeframe.SHORT_TERM, ImpactTimeframe.LONG_TERM],
            include_correlations=True,
            force_refresh=False,
        )

        assert request.experiment_id == "test-exp-001"
        assert len(request.timeframes) == 2
        assert request.include_correlations is True


@pytest.mark.unit()
class TestBatchImpactAnalysisRequest:
    """Test suite for BatchImpactAnalysisRequest model."""

    def test_create_batch_request(self):
        """Test creating batch analysis request."""
        request = BatchImpactAnalysisRequest(
            experiment_ids=["exp-001", "exp-002", "exp-003"],
            timeframes=[ImpactTimeframe.SHORT_TERM],
        )

        assert len(request.experiment_ids) == 3
        assert request.timeframes == [ImpactTimeframe.SHORT_TERM]

    def test_batch_request_validation_too_many(self):
        """Test validation rejects too many experiments."""
        with pytest.raises(Exception):
            BatchImpactAnalysisRequest(
                experiment_ids=[f"exp-{i:03d}" for i in range(51)],
            )


@pytest.mark.unit()
class TestImpactEnums:
    """Test suite for impact enums."""

    def test_impact_direction_values(self):
        """Test ImpactDirection enum values."""
        assert ImpactDirection.POSITIVE.value == "positive"
        assert ImpactDirection.NEGATIVE.value == "negative"
        assert ImpactDirection.NEUTRAL.value == "neutral"
        assert ImpactDirection.MIXED.value == "mixed"

    def test_impact_magnitude_values(self):
        """Test ImpactMagnitude enum values."""
        assert ImpactMagnitude.CRITICAL.value == "critical"
        assert ImpactMagnitude.HIGH.value == "high"
        assert ImpactMagnitude.MEDIUM.value == "medium"
        assert ImpactMagnitude.LOW.value == "low"
        assert ImpactMagnitude.NEGLIGIBLE.value == "negligible"

    def test_impact_category_values(self):
        """Test ImpactCategory enum values."""
        assert ImpactCategory.PERFORMANCE.value == "performance"
        assert ImpactCategory.RELIABILITY.value == "reliability"
        assert ImpactCategory.COST.value == "cost"
        assert ImpactCategory.USER_EXPERIENCE.value == "user_experience"

    def test_impact_timeframe_values(self):
        """Test ImpactTimeframe enum values."""
        assert ImpactTimeframe.SHORT_TERM.value == "short_term"
        assert ImpactTimeframe.LONG_TERM.value == "long_term"
        assert ImpactTimeframe.BOTH.value == "both"


@pytest.mark.unit()
class TestExperimentCorrelation:
    """Test suite for ExperimentCorrelation model."""

    def test_create_correlation(self):
        """Test creating experiment correlation."""
        correlation = ExperimentCorrelation(
            experiment_id="test-exp-002",
            correlation_coefficient=0.85,
            correlation_type="positive",
            shared_metrics=["error_rate", "latency_p95"],
            interaction_effect=0.1,
            description="Strong positive correlation",
        )

        assert correlation.experiment_id == "test-exp-002"
        assert correlation.correlation_coefficient == 0.85
        assert len(correlation.shared_metrics) == 2

    def test_correlation_coefficient_bounds(self):
        """Test correlation coefficient is within bounds."""
        # Valid correlations
        for coeff in [-1.0, -0.5, 0.0, 0.5, 1.0]:
            correlation = ExperimentCorrelation(
                experiment_id="test",
                correlation_coefficient=coeff,
                correlation_type="positive",
                shared_metrics=[],
            )
            assert -1.0 <= correlation.correlation_coefficient <= 1.0
