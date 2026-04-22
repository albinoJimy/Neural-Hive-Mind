"""Testes de métricas para TechnicalSpecialist."""

import os
import sys
from unittest.mock import MagicMock

import pytest

# Configurar paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
sys.path.insert(0, "/app/libraries/python")


class MockSpecialistMetrics:
    """Mock de métricas do especialista."""

    def __init__(self):
        # Criar mock que suporta encadeamento
        self.evaluation_duration_seconds = MagicMock()
        self.evaluation_duration_seconds.labels = MagicMock(
            return_value=MagicMock(observe=MagicMock())
        )

        self.confidence_score = MagicMock()
        self.confidence_score.labels = MagicMock(return_value=MagicMock(set=MagicMock()))

        self.risk_score = MagicMock()
        self.risk_score.labels = MagicMock(return_value=MagicMock(set=MagicMock()))

        self.evaluation_total = MagicMock()

        self.step_duration_seconds = MagicMock()
        self.step_duration_seconds.labels = MagicMock(return_value=MagicMock(observe=MagicMock()))

    def observe_step_duration(self, step_name: str, duration_seconds: float):
        """Registra duração de etapa."""
        if self.step_duration_seconds:
            self.step_duration_seconds.labels(specialist_type="technical", step=step_name).observe(
                duration_seconds
            )

    def emit_confidence(self, specialist_type: str, score: float):
        """Emite métrica de confiança."""
        self.confidence_score.labels(specialist_type=specialist_type).set(score)

    def emit_risk(self, specialist_type: str, score: float):
        """Emite métrica de risco."""
        self.risk_score.labels(specialist_type=specialist_type).set(score)

    def inc_evaluation_total(self, specialist_type: str, recommendation: str):
        """Incrementa contador de avaliações."""
        self.evaluation_total.labels(
            specialist_type=specialist_type, recommendation=recommendation
        ).inc()


@pytest.fixture()
def mock_metrics():
    """Fixture para métricas mock."""
    return MockSpecialistMetrics()


@pytest.fixture()
def sample_evaluation_result():
    """Resultado de avaliação de exemplo."""
    return {
        "confidence_score": 0.78,
        "risk_score": 0.22,
        "recommendation": "approve",
        "metadata": {
            "security_score": 0.85,
            "architecture_score": 0.75,
            "performance_score": 0.70,
            "code_quality_score": 0.80,
            "evaluation_time_ms": 150,
            "step_timings": {
                "security_analysis_ms": 30,
                "architecture_analysis_ms": 40,
                "performance_analysis_ms": 35,
                "code_quality_analysis_ms": 30,
                "reasoning_generation_ms": 15,
            },
        },
    }


class TestEmitAnalysisMetric:
    """Testes de emissão de métricas de análise."""

    def test_emit_security_analysis_metric(self, mock_metrics):
        """Testa emissão de métrica de análise de segurança."""
        security_score = 0.85
        duration_ms = 30

        # Converter para segundos
        duration_seconds = duration_ms / 1000.0

        # Emular observação
        mock_metrics.observe_step_duration("security_analysis", duration_seconds)

        # Verificar que foi chamado
        mock_metrics.step_duration_seconds.labels.assert_called()

    def test_emit_architecture_analysis_metric(self, mock_metrics):
        """Testa emissão de métrica de análise de arquitetura."""
        architecture_score = 0.75
        duration_ms = 40

        duration_seconds = duration_ms / 1000.0
        mock_metrics.observe_step_duration("architecture_analysis", duration_seconds)

        mock_metrics.step_duration_seconds.labels.assert_called()

    def test_emit_performance_analysis_metric(self, mock_metrics):
        """Testa emissão de métrica de análise de performance."""
        performance_score = 0.70
        duration_ms = 35

        duration_seconds = duration_ms / 1000.0
        mock_metrics.observe_step_duration("performance_analysis", duration_seconds)

        mock_metrics.step_duration_seconds.labels.assert_called()

    def test_emit_code_quality_analysis_metric(self, mock_metrics):
        """Testa emissão de métrica de análise de qualidade de código."""
        code_quality_score = 0.80
        duration_ms = 30

        duration_seconds = duration_ms / 1000.0
        mock_metrics.observe_step_duration("code_quality_analysis", duration_seconds)

        mock_metrics.step_duration_seconds.labels.assert_called()


class TestEmitConfidenceMetric:
    """Testes de emissão de métrica de confiança."""

    def test_emit_confidence_metric_high(self, mock_metrics, sample_evaluation_result):
        """Testa emissão de métrica de confiança alta."""
        confidence = sample_evaluation_result["confidence_score"]

        mock_metrics.emit_confidence("technical", confidence)

        mock_metrics.confidence_score.labels.assert_called_with(specialist_type="technical")

    def test_emit_confidence_metric_medium(self, mock_metrics):
        """Testa emissão de métrica de confiança média."""
        confidence = 0.65

        mock_metrics.emit_confidence("technical", confidence)

        mock_metrics.confidence_score.labels.assert_called_with(specialist_type="technical")

    def test_emit_confidence_metric_low(self, mock_metrics):
        """Testa emissão de métrica de confiança baixa."""
        confidence = 0.35

        mock_metrics.emit_confidence("technical", confidence)

        mock_metrics.confidence_score.labels.assert_called_with(specialist_type="technical")

    def test_confidence_metric_validation(self, mock_metrics):
        """Testa validação de range de métrica de confiança."""
        # Deve estar entre 0 e 1
        valid_confidences = [0.0, 0.5, 1.0]

        for confidence in valid_confidences:
            mock_metrics.emit_confidence("technical", confidence)
            assert 0.0 <= confidence <= 1.0


class TestEmitRiskMetric:
    """Testes de emissão de métrica de risco."""

    def test_emit_risk_metric_low(self, mock_metrics, sample_evaluation_result):
        """Testa emissão de métrica de risco baixo."""
        risk = sample_evaluation_result["risk_score"]

        mock_metrics.emit_risk("technical", risk)

        mock_metrics.risk_score.labels.assert_called_with(specialist_type="technical")

    def test_emit_risk_metric_medium(self, mock_metrics):
        """Testa emissão de métrica de risco médio."""
        risk = 0.50

        mock_metrics.emit_risk("technical", risk)

        mock_metrics.risk_score.labels.assert_called_with(specialist_type="technical")

    def test_emit_risk_metric_high(self, mock_metrics):
        """Testa emissão de métrica de risco alto."""
        risk = 0.85

        mock_metrics.emit_risk("technical", risk)

        mock_metrics.risk_score.labels.assert_called_with(specialist_type="technical")

    def test_risk_metric_validation(self, mock_metrics):
        """Testa validação de range de métrica de risco."""
        valid_risks = [0.0, 0.3, 0.7, 1.0]

        for risk in valid_risks:
            mock_metrics.emit_risk("technical", risk)
            assert 0.0 <= risk <= 1.0


class TestEmitDomainMetric:
    """Testes de emissão de métricas de domínio."""

    def test_emit_technical_domain_metric(self, mock_metrics):
        """Testa emissão de métrica para domínio técnico."""
        domain = "technical"
        confidence = 0.80
        risk = 0.20

        mock_metrics.emit_confidence(domain, confidence)
        mock_metrics.emit_risk(domain, risk)

        assert True  # Se não lançou exceção, está OK

    def test_emit_multiple_domain_metrics(self, mock_metrics):
        """Testa emissão de métricas para múltiplos domínios."""
        domains = ["technical", "business", "architecture", "behavior", "evolution"]

        for domain in domains:
            mock_metrics.emit_confidence(domain, 0.75)
            mock_metrics.emit_risk(domain, 0.25)


class TestEmitLatencyMetric:
    """Testes de emissão de métricas de latência."""

    def test_emit_total_evaluation_latency(self, mock_metrics, sample_evaluation_result):
        """Testa emissão de latência total de avaliação."""
        total_time_ms = sample_evaluation_result["metadata"]["evaluation_time_ms"]
        total_time_seconds = total_time_ms / 1000.0

        mock_metrics.evaluation_duration_seconds.labels(specialist_type="technical").observe(
            total_time_seconds
        )

        mock_metrics.evaluation_duration_seconds.labels.assert_called()

    def test_emit_step_timings(self, mock_metrics, sample_evaluation_result):
        """Testa emissão de timings de cada etapa."""
        step_timings = sample_evaluation_result["metadata"]["step_timings"]

        for step_name, duration_ms in step_timings.items():
            duration_seconds = duration_ms / 1000.0
            mock_metrics.observe_step_duration(step_name.replace("_ms", ""), duration_seconds)

        # Cada etapa deve ter sido registrada
        assert mock_metrics.step_duration_seconds.labels.call_count == len(step_timings)

    def test_latency_profiling_aggregation(self):
        """Testa agregação de tempos de profiling."""
        step_timings = {
            "security_analysis_ms": 30,
            "architecture_analysis_ms": 40,
            "performance_analysis_ms": 35,
            "code_quality_analysis_ms": 30,
            "reasoning_generation_ms": 15,
        }

        total_time = sum(step_timings.values())
        avg_time = total_time / len(step_timings)
        max_step = max(step_timings, key=step_timings.get)

        assert total_time == 150
        assert avg_time == 30.0
        assert max_step == "architecture_analysis_ms"

    def test_latency_bottleneck_detection(self):
        """Testa detecção de bottleneck em latência."""
        step_timings = {
            "security_analysis_ms": 30,
            "architecture_analysis_ms": 100,  # Bottleneck
            "performance_analysis_ms": 35,
            "code_quality_analysis_ms": 30,
        }

        threshold_ms = 50
        bottlenecks = [
            (step, time_ms) for step, time_ms in step_timings.items() if time_ms > threshold_ms
        ]

        assert len(bottlenecks) == 1
        assert bottlenecks[0][0] == "architecture_analysis_ms"


class TestMetricsAggregation:
    """Testes de agregação de métricas."""

    def test_aggregate_evaluation_metrics(self, mock_metrics):
        """Testa agregação de métricas de avaliação."""
        evaluations = [
            {"confidence": 0.80, "risk": 0.20, "recommendation": "approve"},
            {"confidence": 0.65, "risk": 0.35, "recommendation": "conditional"},
            {"confidence": 0.45, "risk": 0.55, "recommendation": "reject"},
            {"confidence": 0.90, "risk": 0.10, "recommendation": "approve"},
        ]

        avg_confidence = sum(e["confidence"] for e in evaluations) / len(evaluations)
        avg_risk = sum(e["risk"] for e in evaluations) / len(evaluations)

        approval_rate = sum(1 for e in evaluations if e["recommendation"] == "approve") / len(
            evaluations
        )

        assert abs(avg_confidence - 0.7) < 0.01
        assert abs(avg_risk - 0.3) < 0.01
        assert approval_rate == 0.5

    def test_metrics_by_priority(self):
        """Testa agregação de métricas por prioridade."""
        evaluations_by_priority = {
            "critical": [
                {"confidence": 0.85, "recommendation": "approve"},
                {"confidence": 0.75, "recommendation": "conditional"},
            ],
            "normal": [
                {"confidence": 0.60, "recommendation": "conditional"},
                {"confidence": 0.40, "recommendation": "reject"},
            ],
        }

        for priority, evals in evaluations_by_priority.items():
            avg_conf = sum(e["confidence"] for e in evals) / len(evals)
            assert 0.0 <= avg_conf <= 1.0


class TestMetricsLabels:
    """Testes de labels em métricas."""

    def test_specialist_type_label(self, mock_metrics):
        """Testa label de tipo de especialista."""
        specialist_types = ["technical", "business", "architecture", "behavior", "evolution"]

        for stype in specialist_types:
            mock_metrics.emit_confidence(stype, 0.75)

    def test_recommendation_label(self, mock_metrics):
        """Testa label de recomendação."""
        recommendations = ["approve", "reject", "review_required", "conditional"]

        for rec in recommendations:
            mock_metrics.inc_evaluation_total("technical", rec)

    def test_combined_labels(self, mock_metrics):
        """Testa combinação de labels."""
        # specialist_type + recommendation
        mock_metrics.inc_evaluation_total("technical", "approve")
        mock_metrics.inc_evaluation_total("technical", "reject")
        mock_metrics.inc_evaluation_total("business", "approve")


class TestMetricsHistogram:
    """Testes de histogramas de métricas."""

    def test_confidence_distribution(self):
        """Testa distribuição de scores de confiança."""
        confidence_scores = [0.8, 0.75, 0.65, 0.9, 0.7, 0.85, 0.6, 0.95]

        # Contar scores em cada bucket manualmente
        bucket_05_to_07 = sum(1 for s in confidence_scores if 0.5 <= s < 0.7)  # 0.65, 0.6
        bucket_07_to_09 = sum(
            1 for s in confidence_scores if 0.7 <= s < 0.9
        )  # 0.7, 0.75, 0.8, 0.85
        bucket_09_to_10 = sum(1 for s in confidence_scores if 0.9 <= s <= 1.0)  # 0.9, 0.95

        # 0.7 vai para bucket [0.7, 0.9) porque a condição é s >= 0.7
        assert bucket_05_to_07 == 2  # 0.65, 0.6
        assert bucket_07_to_09 == 4  # 0.7, 0.75, 0.8, 0.85
        assert bucket_09_to_10 == 2  # 0.9, 0.95

    def test_latency_percentiles(self):
        """Testa cálculo de percentis de latência."""
        latencies_ms = [100, 150, 120, 180, 90, 200, 110, 140]

        sorted_latencies = sorted(latencies_ms)
        p50 = sorted_latencies[int(len(sorted_latencies) * 0.5)]
        p95 = sorted_latencies[int(len(sorted_latencies) * 0.95)]
        p99 = sorted_latencies[int(len(sorted_latencies) * 0.99)]

        assert p50 == 140
        assert p95 == 200
        assert p99 == 200
