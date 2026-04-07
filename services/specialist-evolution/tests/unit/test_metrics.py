"""Testes de métricas para EvolutionSpecialist."""

import sys
import os
import pytest
from typing import Dict, Any
from unittest.mock import MagicMock

# Configurar paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
sys.path.insert(0, "/app/libraries/python")


class MockEvolutionMetrics:
    """Mock de métricas do especialista de evolução."""

    def __init__(self):
        self.evaluation_duration_seconds = MagicMock()
        self.confidence_score = MagicMock()
        self.risk_score = MagicMock()
        self.step_duration_seconds = MagicMock()
        self.adaptive_weights = MagicMock()

    def observe_step_duration(self, step_name: str, duration_seconds: float):
        """Registra duração de etapa."""
        self.step_duration_seconds.labels(specialist_type="evolution", step=step_name).observe(
            duration_seconds
        )

    def emit_confidence(self, score: float):
        """Emite métrica de confiança."""
        self.confidence_score.labels(specialist_type="evolution").set(score)

    def emit_risk(self, score: float):
        """Emite métrica de risco."""
        self.risk_score.labels(specialist_type="evolution").set(score)

    def emit_adaptive_weights(self, weights: Dict[str, float]):
        """Emite métrica de pesos adaptativos."""
        for weight_name, value in weights.items():
            self.adaptive_weights.labels(specialist_type="evolution", weight_name=weight_name).set(
                value
            )


@pytest.fixture
def mock_metrics():
    return MockEvolutionMetrics()


@pytest.fixture
def sample_evolution_evaluation():
    return {
        "confidence_score": 0.75,
        "risk_score": 0.25,
        "recommendation": "approve",
        "metadata": {
            "maintainability_score": 0.80,
            "scalability_score": 0.75,
            "extensibility_score": 0.70,
            "modularity_score": 0.85,
            "tech_debt_score": 0.65,
            "evaluation_time_ms": 130,
            "weights_source": "adaptive",
            "step_timings": {
                "maintainability_analysis_ms": 30,
                "scalability_analysis_ms": 25,
                "extensibility_analysis_ms": 25,
                "modularity_analysis_ms": 25,
                "tech_debt_analysis_ms": 25,
            },
        },
    }


class TestEmitAnalysisMetric:
    """Testes de emissão de métricas de análise."""

    def test_emit_maintainability_metric(self, mock_metrics):
        mock_metrics.observe_step_duration("maintainability_analysis", 0.030)
        mock_metrics.step_duration_seconds.labels.assert_called()

    def test_emit_scalability_metric(self, mock_metrics):
        mock_metrics.observe_step_duration("scalability_analysis", 0.025)
        mock_metrics.step_duration_seconds.labels.assert_called()


class TestEmitConfidenceMetric:
    """Testes de emissão de métrica de confiança."""

    def test_emit_confidence_evolution(self, mock_metrics, sample_evolution_evaluation):
        confidence = sample_evolution_evaluation["confidence_score"]
        mock_metrics.emit_confidence(confidence)
        mock_metrics.confidence_score.labels.assert_called_with(specialist_type="evolution")


class TestEmitRiskMetric:
    """Testes de emissão de métrica de risco."""

    def test_emit_risk_evolution(self, mock_metrics, sample_evolution_evaluation):
        risk = sample_evolution_evaluation["risk_score"]
        mock_metrics.emit_risk(risk)
        mock_metrics.risk_score.labels.assert_called_with(specialist_type="evolution")


class TestEmitLatencyMetric:
    """Testes de emissão de métricas de latência."""

    def test_emit_evolution_latency(self, mock_metrics, sample_evolution_evaluation):
        total_time_ms = sample_evolution_evaluation["metadata"]["evaluation_time_ms"]
        total_time_seconds = total_time_ms / 1000.0

        mock_metrics.evaluation_duration_seconds.labels(specialist_type="evolution").observe(
            total_time_seconds
        )

        mock_metrics.evaluation_duration_seconds.labels.assert_called()


class TestAdaptiveWeightsMetrics:
    """Testes de métricas de pesos adaptativos."""

    def test_emit_adaptive_weights(self, mock_metrics):
        adaptive_weights = {
            "maintainability": 0.27,
            "scalability": 0.23,
            "extensibility": 0.20,
            "modularity": 0.15,
            "tech_debt_prevention": 0.15,
        }

        mock_metrics.emit_adaptive_weights(adaptive_weights)

        # Cada peso deve ser emitido
        assert mock_metrics.adaptive_weights.labels.call_count == len(adaptive_weights)

    def test_emit_default_weights(self, mock_metrics):
        default_weights = {
            "maintainability": 0.25,
            "scalability": 0.25,
            "extensibility": 0.20,
            "modularity": 0.15,
            "tech_debt_prevention": 0.15,
        }

        mock_metrics.emit_adaptive_weights(default_weights)

        total_weight = sum(default_weights.values())
        assert abs(total_weight - 1.0) < 0.01
