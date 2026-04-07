"""Testes de métricas para BehaviorSpecialist."""

import sys
import os
import pytest
from unittest.mock import MagicMock

# Configurar paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
sys.path.insert(0, "/app/libraries/python")


class MockBehaviorMetrics:
    """Mock de métricas do especialista comportamental."""

    def __init__(self):
        self.evaluation_duration_seconds = MagicMock()
        self.confidence_score = MagicMock()
        self.risk_score = MagicMock()
        self.step_duration_seconds = MagicMock()

    def observe_step_duration(self, step_name: str, duration_seconds: float):
        """Registra duração de etapa."""
        self.step_duration_seconds.labels(specialist_type="behavior", step=step_name).observe(
            duration_seconds
        )

    def emit_confidence(self, score: float):
        """Emite métrica de confiança."""
        self.confidence_score.labels(specialist_type="behavior").set(score)

    def emit_risk(self, score: float):
        """Emite métrica de risco."""
        self.risk_score.labels(specialist_type="behavior").set(score)


@pytest.fixture
def mock_metrics():
    return MockBehaviorMetrics()


@pytest.fixture
def sample_behavior_evaluation():
    return {
        "confidence_score": 0.78,
        "risk_score": 0.22,
        "recommendation": "approve",
        "metadata": {
            "usability_score": 0.85,
            "accessibility_score": 0.75,
            "response_time_score": 0.80,
            "interaction_cost_score": 0.70,
            "evaluation_time_ms": 90,
            "step_timings": {
                "usability_analysis_ms": 25,
                "accessibility_analysis_ms": 20,
                "response_time_ms": 25,
                "interaction_cost_ms": 20,
            },
        },
    }


class TestEmitAnalysisMetric:
    """Testes de emissão de métricas de análise."""

    def test_emit_usability_metric(self, mock_metrics):
        mock_metrics.observe_step_duration("usability_analysis", 0.025)
        mock_metrics.step_duration_seconds.labels.assert_called()

    def test_emit_accessibility_metric(self, mock_metrics):
        mock_metrics.observe_step_duration("accessibility_analysis", 0.020)
        mock_metrics.step_duration_seconds.labels.assert_called()


class TestEmitConfidenceMetric:
    """Testes de emissão de métrica de confiança."""

    def test_emit_confidence_behavior(self, mock_metrics, sample_behavior_evaluation):
        confidence = sample_behavior_evaluation["confidence_score"]
        mock_metrics.emit_confidence(confidence)
        mock_metrics.confidence_score.labels.assert_called_with(specialist_type="behavior")


class TestEmitRiskMetric:
    """Testes de emissão de métrica de risco."""

    def test_emit_risk_behavior(self, mock_metrics, sample_behavior_evaluation):
        risk = sample_behavior_evaluation["risk_score"]
        mock_metrics.emit_risk(risk)
        mock_metrics.risk_score.labels.assert_called_with(specialist_type="behavior")


class TestEmitLatencyMetric:
    """Testes de emissão de métricas de latência."""

    def test_emit_behavior_latency(self, mock_metrics, sample_behavior_evaluation):
        total_time_ms = sample_behavior_evaluation["metadata"]["evaluation_time_ms"]
        total_time_seconds = total_time_ms / 1000.0

        mock_metrics.evaluation_duration_seconds.labels(specialist_type="behavior").observe(
            total_time_seconds
        )

        mock_metrics.evaluation_duration_seconds.labels.assert_called()
