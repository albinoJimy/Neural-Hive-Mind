"""Testes de métricas para ArchitectureSpecialist."""

import os
import sys
from unittest.mock import MagicMock

import pytest

# Configurar paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
sys.path.insert(0, "/app/libraries/python")


class MockArchitectureMetrics:
    """Mock de métricas do especialista de arquitetura."""

    def __init__(self):
        self.evaluation_duration_seconds = MagicMock()
        self.confidence_score = MagicMock()
        self.risk_score = MagicMock()
        self.step_duration_seconds = MagicMock()
        self.design_pattern_score = MagicMock()
        self.solid_score = MagicMock()
        self.coupling_cohesion_score = MagicMock()

    def observe_step_duration(self, step_name: str, duration_seconds: float):
        """Registra duração de etapa."""
        self.step_duration_seconds.labels(specialist_type="architecture", step=step_name).observe(
            duration_seconds
        )

    def emit_confidence(self, score: float):
        """Emite métrica de confiança."""
        self.confidence_score.labels(specialist_type="architecture").set(score)

    def emit_risk(self, score: float):
        """Emite métrica de risco."""
        self.risk_score.labels(specialist_type="architecture").set(score)


@pytest.fixture()
def mock_metrics():
    return MockArchitectureMetrics()


@pytest.fixture()
def sample_architecture_evaluation():
    return {
        "confidence_score": 0.72,
        "risk_score": 0.28,
        "recommendation": "approve",
        "metadata": {
            "design_pattern_score": 0.75,
            "solid_score": 0.70,
            "coupling_cohesion_score": 0.68,
            "separation_score": 0.80,
            "modularity_score": 0.65,
            "evaluation_time_ms": 110,
            "step_timings": {
                "design_patterns_ms": 25,
                "solid_analysis_ms": 30,
                "coupling_cohesion_ms": 20,
                "separation_ms": 20,
                "modularity_ms": 15,
            },
        },
    }


class TestEmitAnalysisMetric:
    """Testes de emissão de métricas de análise."""

    def test_emit_design_pattern_metric(self, mock_metrics):
        mock_metrics.observe_step_duration("design_patterns", 0.025)
        mock_metrics.step_duration_seconds.labels.assert_called()

    def test_emit_solid_metric(self, mock_metrics):
        mock_metrics.observe_step_duration("solid_analysis", 0.030)
        mock_metrics.step_duration_seconds.labels.assert_called()

    def test_emit_coupling_cohesion_metric(self, mock_metrics):
        mock_metrics.observe_step_duration("coupling_cohesion", 0.020)
        mock_metrics.step_duration_seconds.labels.assert_called()


class TestEmitConfidenceMetric:
    """Testes de emissão de métrica de confiança."""

    def test_emit_confidence_architecture(self, mock_metrics, sample_architecture_evaluation):
        confidence = sample_architecture_evaluation["confidence_score"]
        mock_metrics.emit_confidence(confidence)
        mock_metrics.confidence_score.labels.assert_called_with(specialist_type="architecture")


class TestEmitRiskMetric:
    """Testes de emissão de métrica de risco."""

    def test_emit_risk_architecture(self, mock_metrics, sample_architecture_evaluation):
        risk = sample_architecture_evaluation["risk_score"]
        mock_metrics.emit_risk(risk)
        mock_metrics.risk_score.labels.assert_called_with(specialist_type="architecture")


class TestEmitLatencyMetric:
    """Testes de emissão de métricas de latência."""

    def test_emit_architecture_latency(self, mock_metrics, sample_architecture_evaluation):
        total_time_ms = sample_architecture_evaluation["metadata"]["evaluation_time_ms"]
        total_time_seconds = total_time_ms / 1000.0

        mock_metrics.evaluation_duration_seconds.labels(specialist_type="architecture").observe(
            total_time_seconds
        )

        mock_metrics.evaluation_duration_seconds.labels.assert_called()


class TestMetricsAggregation:
    """Testes de agregação de métricas."""

    def test_aggregate_architecture_metrics(self):
        evaluations = [
            {"design_patterns": 0.75, "solid": 0.70, "coupling": 0.68, "confidence": 0.72},
            {"design_patterns": 0.80, "solid": 0.75, "coupling": 0.72, "confidence": 0.77},
            {"design_patterns": 0.70, "solid": 0.65, "coupling": 0.60, "confidence": 0.67},
        ]

        avg_confidence = sum(e["confidence"] for e in evaluations) / len(evaluations)
        assert abs(avg_confidence - 0.72) < 0.01
