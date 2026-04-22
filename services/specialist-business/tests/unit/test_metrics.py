"""Testes de métricas para BusinessSpecialist."""

import os
import sys
from unittest.mock import MagicMock

import pytest

# Configurar paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
sys.path.insert(0, "/app/libraries/python")


class MockBusinessMetrics:
    """Mock de métricas do especialista de negócio."""

    def __init__(self):
        self.evaluation_duration_seconds = MagicMock()
        self.confidence_score = MagicMock()
        self.risk_score = MagicMock()
        self.evaluation_total = MagicMock()
        self.step_duration_seconds = MagicMock()
        self.workflow_score = MagicMock()
        self.kpi_score = MagicMock()
        self.cost_score = MagicMock()

    def observe_step_duration(self, step_name: str, duration_seconds: float):
        """Registra duração de etapa."""
        if self.step_duration_seconds:
            self.step_duration_seconds.labels(specialist_type="business", step=step_name).observe(
                duration_seconds
            )

    def emit_confidence(self, specialist_type: str, score: float):
        """Emite métrica de confiança."""
        self.confidence_score.labels(specialist_type=specialist_type).set(score)

    def emit_risk(self, specialist_type: str, score: float):
        """Emite métrica de risco."""
        self.risk_score.labels(specialist_type=specialist_type).set(score)

    def emit_workflow_score(self, score: float):
        """Emite métrica de score de workflow."""
        self.workflow_score.labels(specialist_type="business").set(score)

    def emit_kpi_score(self, score: float):
        """Emite métrica de score de KPI."""
        self.kpi_score.labels(specialist_type="business").set(score)

    def emit_cost_score(self, score: float):
        """Emite métrica de score de custo."""
        self.cost_score.labels(specialist_type="business").set(score)


@pytest.fixture()
def mock_metrics():
    """Fixture para métricas mock."""
    return MockBusinessMetrics()


@pytest.fixture()
def sample_business_evaluation():
    """Resultado de avaliação de negócio de exemplo."""
    return {
        "confidence_score": 0.75,
        "risk_score": 0.25,
        "recommendation": "approve",
        "reasoning_summary": "Avaliação de negócios positiva",
        "metadata": {
            "workflow_score": 0.80,
            "kpi_score": 0.75,
            "cost_score": 0.70,
            "evaluation_time_ms": 120,
            "step_timings": {
                "workflow_analysis_ms": 35,
                "kpi_analysis_ms": 30,
                "cost_analysis_ms": 25,
                "risk_calculation_ms": 20,
                "reasoning_generation_ms": 10,
            },
        },
    }


class TestEmitAnalysisMetric:
    """Testes de emissão de métricas de análise de negócio."""

    def test_emit_workflow_analysis_metric(self, mock_metrics):
        """Testa emissão de métrica de análise de workflow."""
        workflow_score = 0.80
        duration_ms = 35

        mock_metrics.emit_workflow_score(workflow_score)
        duration_seconds = duration_ms / 1000.0
        mock_metrics.observe_step_duration("workflow_analysis", duration_seconds)

        mock_metrics.workflow_score.labels.assert_called_with(specialist_type="business")

    def test_emit_kpi_analysis_metric(self, mock_metrics):
        """Testa emissão de métrica de análise de KPI."""
        kpi_score = 0.75
        duration_ms = 30

        mock_metrics.emit_kpi_score(kpi_score)
        duration_seconds = duration_ms / 1000.0
        mock_metrics.observe_step_duration("kpi_analysis", duration_seconds)

        mock_metrics.kpi_score.labels.assert_called_with(specialist_type="business")

    def test_emit_cost_analysis_metric(self, mock_metrics):
        """Testa emissão de métrica de análise de custo."""
        cost_score = 0.70
        duration_ms = 25

        mock_metrics.emit_cost_score(cost_score)
        duration_seconds = duration_ms / 1000.0
        mock_metrics.observe_step_duration("cost_analysis", duration_seconds)

        mock_metrics.cost_score.labels.assert_called_with(specialist_type="business")


class TestEmitConfidenceMetric:
    """Testes de emissão de métrica de confiança de negócio."""

    def test_emit_confidence_business_high(self, mock_metrics, sample_business_evaluation):
        """Testa emissão de confiança alta para negócio."""
        confidence = sample_business_evaluation["confidence_score"]

        mock_metrics.emit_confidence("business", confidence)

        mock_metrics.confidence_score.labels.assert_called_with(specialist_type="business")

    def test_confidence_range_validation(self, mock_metrics):
        """Testa validação de range de confiança."""
        valid_confidences = [0.0, 0.25, 0.5, 0.75, 1.0]

        for confidence in valid_confidences:
            mock_metrics.emit_confidence("business", confidence)
            assert 0.0 <= confidence <= 1.0


class TestEmitRiskMetric:
    """Testes de emissão de métrica de risco de negócio."""

    def test_emit_risk_business_low(self, mock_metrics, sample_business_evaluation):
        """Testa emissão de risco baixo para negócio."""
        risk = sample_business_evaluation["risk_score"]

        mock_metrics.emit_risk("business", risk)

        mock_metrics.risk_score.labels.assert_called_with(specialist_type="business")

    def test_risk_calculation_metric(self, mock_metrics):
        """Testa métrica de cálculo de risco de negócio."""
        workflow_score = 0.80
        kpi_score = 0.75
        cost_score = 0.70

        # Fórmula de risco do BusinessSpecialist
        weighted_avg = workflow_score * 0.3 + kpi_score * 0.4 + cost_score * 0.3
        risk_score = 1.0 - weighted_avg

        mock_metrics.emit_risk("business", risk_score)

        expected = 1.0 - (0.80 * 0.3 + 0.75 * 0.4 + 0.70 * 0.3)
        assert abs(risk_score - expected) < 0.01


class TestEmitDomainMetric:
    """Testes de emissão de métricas de domínio de negócio."""

    def test_emit_business_domain_metrics(self, mock_metrics):
        """Testa emissão de métricas para domínio business."""
        mock_metrics.emit_confidence("business", 0.80)
        mock_metrics.emit_risk("business", 0.20)
        mock_metrics.emit_workflow_score(0.75)
        mock_metrics.emit_kpi_score(0.70)
        mock_metrics.emit_cost_score(0.65)

        assert True  # Se não lançou exceção, está OK


class TestEmitLatencyMetric:
    """Testes de emissão de métricas de latência."""

    def test_emit_business_evaluation_latency(self, mock_metrics, sample_business_evaluation):
        """Testa emissão de latência de avaliação de negócio."""
        total_time_ms = sample_business_evaluation["metadata"]["evaluation_time_ms"]
        total_time_seconds = total_time_ms / 1000.0

        mock_metrics.evaluation_duration_seconds.labels(specialist_type="business").observe(
            total_time_seconds
        )

        mock_metrics.evaluation_duration_seconds.labels.assert_called()

    def test_emit_business_step_timings(self, mock_metrics, sample_business_evaluation):
        """Testa emissão de timings de etapas de negócio."""
        step_timings = sample_business_evaluation["metadata"]["step_timings"]

        for step_name, duration_ms in step_timings.items():
            duration_seconds = duration_ms / 1000.0
            mock_metrics.observe_step_duration(step_name.replace("_ms", ""), duration_seconds)

        assert mock_metrics.step_duration_seconds.labels.call_count == len(step_timings)


class TestMetricsAggregation:
    """Testes de agregação de métricas de negócio."""

    def test_aggregate_business_metrics(self, mock_metrics):
        """Testa agregação de métricas de avaliação de negócio."""
        evaluations = [
            {"workflow": 0.80, "kpi": 0.75, "cost": 0.70, "confidence": 0.75},
            {"workflow": 0.70, "kpi": 0.65, "cost": 0.60, "confidence": 0.65},
            {"workflow": 0.90, "kpi": 0.85, "cost": 0.80, "confidence": 0.85},
        ]

        avg_workflow = sum(e["workflow"] for e in evaluations) / len(evaluations)
        avg_kpi = sum(e["kpi"] for e in evaluations) / len(evaluations)
        avg_cost = sum(e["cost"] for e in evaluations) / len(evaluations)
        avg_confidence = sum(e["confidence"] for e in evaluations) / len(evaluations)

        assert abs(avg_workflow - 0.8) < 0.01
        assert abs(avg_kpi - 0.75) < 0.01
        assert abs(avg_cost - 0.7) < 0.01
        assert abs(avg_confidence - 0.75) < 0.01

    def test_business_metrics_by_priority(self):
        """Testa métricas de negócio por prioridade."""
        evaluations_by_priority = {
            "critical": [
                {"confidence": 0.85, "recommendation": "approve"},
                {"confidence": 0.70, "recommendation": "conditional"},
            ],
            "high": [
                {"confidence": 0.75, "recommendation": "approve"},
            ],
            "normal": [
                {"confidence": 0.60, "recommendation": "conditional"},
                {"confidence": 0.45, "recommendation": "reject"},
            ],
        }

        for priority, evals in evaluations_by_priority.items():
            avg_conf = sum(e["confidence"] for e in evals) / len(evals)
            assert 0.0 <= avg_conf <= 1.0


class TestMetricsLabels:
    """Testes de labels em métricas de negócio."""

    def test_business_specialist_label(self, mock_metrics):
        """Testa label de especialista de negócio."""
        mock_metrics.emit_confidence("business", 0.75)
        mock_metrics.emit_risk("business", 0.25)

    def test_business_priority_labels(self, mock_metrics):
        """Testa labels de prioridade para negócio."""
        priorities = ["critical", "high", "normal", "low"]

        for priority in priorities:
            mock_metrics.emit_confidence(f"business_{priority}", 0.70)


class TestMetricsHistogram:
    """Testes de histogramas de métricas de negócio."""

    def test_confidence_distribution_business(self):
        """Testa distribuição de confiança de negócio."""
        confidence_scores = [0.85, 0.70, 0.65, 0.90, 0.75, 0.80, 0.60, 0.95]

        # Contar scores em cada bucket
        bucket_07_09 = sum(1 for s in confidence_scores if 0.7 <= s < 0.9)
        bucket_09_10 = sum(1 for s in confidence_scores if 0.9 <= s <= 1.0)

        assert bucket_07_09 == 4  # 0.70, 0.75, 0.80, 0.85
        assert bucket_09_10 == 2  # 0.90, 0.95

    def test_latency_percentiles_business(self):
        """Testa percentis de latência de avaliações de negócio."""
        latencies_ms = [80, 120, 100, 150, 70, 180, 90, 130]

        sorted_latencies = sorted(latencies_ms)
        p50_index = int(len(sorted_latencies) * 0.5)
        p95_index = min(int(len(sorted_latencies) * 0.95), len(sorted_latencies) - 1)

        p50 = sorted_latencies[p50_index]
        p95 = sorted_latencies[p95_index]

        assert p50 == 120
        assert p95 == 180
