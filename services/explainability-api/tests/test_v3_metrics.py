"""
Testes unitários para métricas Prometheus v3.

TDD: Testes escritos antes da implementação (Explainability API v3 Task 7).
"""

import pytest
import time
from typing import Dict, Any
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Importar métricas e wrapper
from metrics.v3_metrics import (
    v3_generation_duration,
    v3_explanations_generated,
    consensus_strength_gauge,
    dominant_level_counter,
    counterfactual_outcome_counter,
    V3Metrics,
)


# Helper para limpar métricas entre testes
def clear_metrics():
    """Limpa todos os metric values entre testes."""
    # Clear Histogram (apenas _sum, não tem _count separado)
    for labels in list(v3_generation_duration._metrics.keys()):
        v3_generation_duration._metrics[labels]._sum.set(0)

    # Clear Counters
    for labels in list(v3_explanations_generated._metrics.keys()):
        v3_explanations_generated._metrics[labels]._value.set(0)

    for labels in list(dominant_level_counter._metrics.keys()):
        dominant_level_counter._metrics[labels]._value.set(0)

    for labels in list(counterfactual_outcome_counter._metrics.keys()):
        counterfactual_outcome_counter._metrics[labels]._value.set(0)

    # Clear Gauges
    for labels in list(consensus_strength_gauge._metrics.keys()):
        consensus_strength_gauge._metrics[labels]._value.set(0)


class TestGenerationDurationMetric:
    """Testes para métrica de duração de geração."""

    def test_metric_exists(self):
        """Testa que a métrica de duração foi criada."""
        assert v3_generation_duration is not None
        assert v3_generation_duration._name == "neural_hive_v3_generation_duration_seconds"
        assert "component" in v3_generation_duration._labelnames

    def test_observe_duration(self):
        """Testa observação de duração de geração."""
        clear_metrics()

        V3Metrics.observe_generation_duration(0.5, "hierarchical_explainer")

        # Verificar que a métrica foi registada verificando o _sum
        labels = ("hierarchical_explainer",)
        assert labels in v3_generation_duration._metrics
        assert v3_generation_duration._metrics[labels]._sum.get() == 0.5

    def test_observe_duration_multiple_components(self):
        """Testa observação de duração para múltiplos componentes."""
        clear_metrics()

        V3Metrics.observe_generation_duration(0.3, "counterfactual_analyzer")
        V3Metrics.observe_generation_duration(0.7, "temporal_tracker")

        counterfactual_labels = ("counterfactual_analyzer",)
        temporal_labels = ("temporal_tracker",)

        assert counterfactual_labels in v3_generation_duration._metrics
        assert temporal_labels in v3_generation_duration._metrics
        assert v3_generation_duration._metrics[counterfactual_labels]._sum.get() == 0.3
        assert v3_generation_duration._metrics[temporal_labels]._sum.get() == 0.7

    def test_observe_duration_invalid_component_does_not_crash(self):
        """Testa que componente inválido não causa crash."""
        clear_metrics()

        # Não deve causar erro
        V3Metrics.observe_generation_duration(0.5, "invalid_component")
        V3Metrics.observe_generation_duration(0.5, "hierarchical_explainer")

        # Métrica válida deve ser registada
        labels = ("hierarchical_explainer",)
        assert labels in v3_generation_duration._metrics


class TestExplanationsGeneratedMetric:
    """Testes para métrica de explicações geradas."""

    def test_metric_exists(self):
        """Testa que a métrica de explicações geradas foi criada."""
        assert v3_explanations_generated is not None
        # Counter não tem _total no nome interno
        assert "neural_hive_v3_explanations_generated" in v3_explanations_generated._name
        assert "format" in v3_explanations_generated._labelnames
        assert "components" in v3_explanations_generated._labelnames

    def test_increment_explanations(self):
        """Testa incremento de explicações geradas."""
        clear_metrics()

        V3Metrics.increment_explanations_generated("json", "hierarchical")

        labels = ("json", "hierarchical")
        assert labels in v3_explanations_generated._metrics
        assert v3_explanations_generated._metrics[labels]._value.get() == 1.0

    def test_increment_multiple_formats(self):
        """Testa incremento de múltiplos formatos."""
        clear_metrics()

        V3Metrics.increment_explanations_generated("json", "hierarchical")
        V3Metrics.increment_explanations_generated("text", "hierarchical")
        V3Metrics.increment_explanations_generated("html", "counterfactual")

        json_labels = ("json", "hierarchical")
        text_labels = ("text", "hierarchical")
        html_labels = ("html", "counterfactual")

        assert v3_explanations_generated._metrics[json_labels]._value.get() == 1.0
        assert v3_explanations_generated._metrics[text_labels]._value.get() == 1.0
        assert v3_explanations_generated._metrics[html_labels]._value.get() == 1.0


class TestConsensusStrengthGauge:
    """Testes para gauge de força de consenso."""

    def test_metric_exists(self):
        """Testa que o gauge de força de consenso foi criado."""
        assert consensus_strength_gauge is not None
        assert consensus_strength_gauge._name == "neural_hive_v3_consensus_strength"
        assert "dominant_level" in consensus_strength_gauge._labelnames

    def test_set_consensus_strength(self):
        """Testa definição de força de consenso."""
        clear_metrics()

        V3Metrics.set_consensus_strength(0.85, "senior")

        labels = ("senior",)
        assert labels in consensus_strength_gauge._metrics
        assert consensus_strength_gauge._metrics[labels]._value.get() == 0.85

    def test_set_consensus_strength_clamps_value(self):
        """Testa que valores fora do range são limitados."""
        clear_metrics()

        V3Metrics.set_consensus_strength(1.5, "expert")  # Acima de 1.0
        V3Metrics.set_consensus_strength(-0.5, "trainee")  # Abaixo de 0.0

        expert_labels = ("expert",)
        trainee_labels = ("trainee",)

        assert consensus_strength_gauge._metrics[expert_labels]._value.get() == 1.0
        assert consensus_strength_gauge._metrics[trainee_labels]._value.get() == 0.0

    def test_set_consensus_strength_none_level(self):
        """Testa que nível None usa label 'unknown'."""
        clear_metrics()

        V3Metrics.set_consensus_strength(0.5, None)

        labels = ("unknown",)
        assert labels in consensus_strength_gauge._metrics
        assert consensus_strength_gauge._metrics[labels]._value.get() == 0.5


class TestDominantLevelCounter:
    """Testes para contador de nível dominante."""

    def test_metric_exists(self):
        """Testa que o contador de nível dominante foi criado."""
        assert dominant_level_counter is not None
        assert "neural_hive_v3_dominant_level" in dominant_level_counter._name
        assert "level" in dominant_level_counter._labelnames

    def test_increment_dominant_level(self):
        """Testa incremento de nível dominante."""
        clear_metrics()

        V3Metrics.increment_dominant_level("senior")

        labels = ("senior",)
        assert labels in dominant_level_counter._metrics
        assert dominant_level_counter._metrics[labels]._value.get() == 1.0

    def test_increment_multiple_levels(self):
        """Testa incremento de múltiplos níveis."""
        clear_metrics()

        V3Metrics.increment_dominant_level("expert")
        V3Metrics.increment_dominant_level("expert")
        V3Metrics.increment_dominant_level("senior")
        V3Metrics.increment_dominant_level("mid_level")

        expert_labels = ("expert",)
        senior_labels = ("senior",)
        mid_labels = ("mid_level",)

        assert dominant_level_counter._metrics[expert_labels]._value.get() == 2.0
        assert dominant_level_counter._metrics[senior_labels]._value.get() == 1.0
        assert dominant_level_counter._metrics[mid_labels]._value.get() == 1.0


class TestCounterfactualOutcomeCounter:
    """Testes para contador de outcomes contrafactuais."""

    def test_metric_exists(self):
        """Testa que o contador de outcomes foi criado."""
        assert counterfactual_outcome_counter is not None
        assert "neural_hive_v3_counterfactual_outcome" in counterfactual_outcome_counter._name
        assert "scenario_type" in counterfactual_outcome_counter._labelnames
        assert "outcome" in counterfactual_outcome_counter._labelnames

    def test_increment_counterfactual_outcome(self):
        """Testa incremento de outcome contrafactual."""
        clear_metrics()

        V3Metrics.increment_counterfactual_outcome("feature_removal", "decision_changed")

        labels = ("feature_removal", "decision_changed")
        assert labels in counterfactual_outcome_counter._metrics
        assert counterfactual_outcome_counter._metrics[labels]._value.get() == 1.0

    def test_increment_multiple_outcomes(self):
        """Testa incremento de múltiplos outcomes."""
        clear_metrics()

        V3Metrics.increment_counterfactual_outcome("feature_removal", "decision_changed")
        V3Metrics.increment_counterfactual_outcome("feature_removal", "decision_unchanged")
        V3Metrics.increment_counterfactual_outcome("seniority_change", "decision_changed")

        removal_changed_labels = ("feature_removal", "decision_changed")
        removal_unchanged_labels = ("feature_removal", "decision_unchanged")
        seniority_changed_labels = ("seniority_change", "decision_changed")

        assert counterfactual_outcome_counter._metrics[removal_changed_labels]._value.get() == 1.0
        assert counterfactual_outcome_counter._metrics[removal_unchanged_labels]._value.get() == 1.0
        assert counterfactual_outcome_counter._metrics[seniority_changed_labels]._value.get() == 1.0


class TestCompositeMethods:
    """Testes para métodos compostos do V3Metrics."""

    def test_record_explanation_generation(self):
        """Testa registo completo de geração de explicação."""
        clear_metrics()

        V3Metrics.record_explanation_generation(
            duration_seconds=0.75,
            component="hierarchical_explainer",
            format_type="json",
            components_used="hierarchical"
        )

        # Verificar duração
        duration_labels = ("hierarchical_explainer",)
        assert duration_labels in v3_generation_duration._metrics
        assert v3_generation_duration._metrics[duration_labels]._sum.get() == 0.75

        # Verificar contagem
        count_labels = ("json", "hierarchical")
        assert count_labels in v3_explanations_generated._metrics
        assert v3_explanations_generated._metrics[count_labels]._value.get() == 1.0

    def test_record_hierarchical_consensus(self):
        """Testa registo completo de consenso hierárquico."""
        clear_metrics()

        V3Metrics.record_hierarchical_consensus(
            strength=0.9,
            dominant_level="expert"
        )

        # Verificar gauge
        gauge_labels = ("expert",)
        assert gauge_labels in consensus_strength_gauge._metrics
        assert consensus_strength_gauge._metrics[gauge_labels]._value.get() == 0.9

        # Verificar contador
        count_labels = ("expert",)
        assert count_labels in dominant_level_counter._metrics
        assert dominant_level_counter._metrics[count_labels]._value.get() == 1.0

    def test_record_hierarchical_consensus_none_level(self):
        """Testa registo de consenso com nível None."""
        clear_metrics()

        V3Metrics.record_hierarchical_consensus(
            strength=0.5,
            dominant_level=None
        )

        # Gauge deve ter label "unknown"
        gauge_labels = ("unknown",)
        assert gauge_labels in consensus_strength_gauge._metrics
        assert consensus_strength_gauge._metrics[gauge_labels]._value.get() == 0.5

        # Contador não deve ser incrementado para None
        count_labels = ("unknown",)
        # O método não incrementa quando dominant_level é None
        assert count_labels not in dominant_level_counter._metrics

    def test_record_counterfactual_analysis(self):
        """Testa registo de análise contrafactual."""
        clear_metrics()

        V3Metrics.record_counterfactual_analysis(
            scenario_type="vote_flip",
            outcome="decision_changed"
        )

        labels = ("vote_flip", "decision_changed")
        assert labels in counterfactual_outcome_counter._metrics
        assert counterfactual_outcome_counter._metrics[labels]._value.get() == 1.0


class TestV3MetricsConstants:
    """Testes para constantes de validação do V3Metrics."""

    def test_valid_components(self):
        """Testa lista de componentes válidos."""
        expected_components = [
            "hierarchical_explainer",
            "counterfactual_analyzer",
            "temporal_tracker",
            "shap_calculator",
            "quality_scorer",
            "reasoning_extractor",
        ]
        assert V3Metrics.VALID_COMPONENTS == expected_components

    def test_valid_formats(self):
        """Testa lista de formatos válidos."""
        assert V3Metrics.VALID_FORMATS == ["json", "text", "html"]

    def test_valid_levels(self):
        """Testa lista de níveis válidos."""
        expected_levels = [
            "trainee",
            "junior",
            "mid_level",
            "senior",
            "expert",
            None,
        ]
        assert V3Metrics.VALID_LEVELS == expected_levels

    def test_valid_scenario_types(self):
        """Testa lista de tipos de cenário válidos."""
        expected_types = [
            "feature_removal",
            "confidence_change",
            "seniority_change",
            "vote_flip",
        ]
        assert V3Metrics.VALID_SCENARIO_TYPES == expected_types

    def test_valid_outcomes(self):
        """Testa lista de outcomes válidos."""
        assert V3Metrics.VALID_OUTCOMES == [
            "decision_changed",
            "decision_unchanged",
            "unknown",
        ]
