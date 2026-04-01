"""
Métricas Prometheus para Explainability API v3.

Este módulo define métricas específicas para a versão 3 da API de
explicabilidade, incluindo:

1. Métricas de geração de explicações (duração, contagem por formato/componente)
2. Métricas de consenso hierárquico (força de consenso, nível dominante)
3. Métricas de análises contrafactuais (cenários, outcomes)

Explainability API v3 - Task 7
"""

from typing import Optional

import structlog
from prometheus_client import Counter, Gauge, Histogram

logger = structlog.get_logger(__name__)


# =============================================================================
# MÉTRICAS DE GERACAO DE EXPLICACOES
# =============================================================================

v3_generation_duration = Histogram(
    "neural_hive_v3_generation_duration_seconds",
    "Duração da geração de explicações v3 por componente",
    ["component"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0],
)

v3_explanations_generated = Counter(
    "neural_hive_v3_explanations_generated_total",
    "Total de explicações v3 geradas por formato e componentes",
    ["format", "components"],
)


# =============================================================================
# MÉTRICAS DE CONSENSO HIERARQUICO
# =============================================================================

consensus_strength_gauge = Gauge(
    "neural_hive_v3_consensus_strength",
    "Força do consenso hierárquico actual (0.0 a 1.0)",
    ["dominant_level"],
)

dominant_level_counter = Counter(
    "neural_hive_v3_dominant_level_total",
    "Total de decisões por nível hierárquico dominante",
    ["level"],
)


# =============================================================================
# MÉTRICAS DE ANALISES CONTRAFACTUAIS
# =============================================================================

counterfactual_outcome_counter = Counter(
    "neural_hive_v3_counterfactual_outcome_total",
    "Total de outcomes de análises contrafactuais",
    ["scenario_type", "outcome"],
)


# =============================================================================
# WRAPPER CLASS PARA CONVENIENCIA
# =============================================================================


class V3Metrics:
    """
    Wrapper para métricas v3 com métodos de conveniência.

    Fornece interface amigável para registar métricas de explicabilidade v3.
    """

    # Valores válidos para labels
    VALID_COMPONENTS = [
        "hierarchical_explainer",
        "counterfactual_analyzer",
        "temporal_tracker",
        "shap_calculator",
        "quality_scorer",
        "reasoning_extractor",
    ]

    VALID_FORMATS = ["json", "text", "html"]

    VALID_LEVELS = [
        "trainee",
        "junior",
        "mid_level",
        "senior",
        "expert",
        None,
    ]

    VALID_SCENARIO_TYPES = [
        "feature_removal",
        "confidence_change",
        "seniority_change",
        "vote_flip",
    ]

    VALID_OUTCOMES = [
        "decision_changed",
        "decision_unchanged",
        "unknown",
    ]

    @staticmethod
    def observe_generation_duration(duration_seconds: float, component: str) -> None:
        """
        Regista duração de geração de explicação.

        Args:
            duration_seconds: Duração em segundos
            component: Nome do componente que gerou a explicação
        """
        if component not in V3Metrics.VALID_COMPONENTS:
            logger.warning(
                "invalid_component_label",
                component=component,
                valid_components=V3Metrics.VALID_COMPONENTS,
            )

        v3_generation_duration.labels(component=component).observe(duration_seconds)

    @staticmethod
    def increment_explanations_generated(format_type: str, components: str) -> None:
        """
        Incrementa contador de explicações geradas.

        Args:
            format_type: Formato da explicação (json, text, html)
            components: Componentes usados (ex: "hierarchical,counterfactual")
        """
        if format_type not in V3Metrics.VALID_FORMATS:
            logger.warning(
                "invalid_format_label",
                format_type=format_type,
                valid_formats=V3Metrics.VALID_FORMATS,
            )

        v3_explanations_generated.labels(format=format_type, components=components).inc()

    @staticmethod
    def set_consensus_strength(strength: float, dominant_level: Optional[str] = None) -> None:
        """
        Define força de consenso actual.

        Args:
            strength: Força do consenso (0.0 a 1.0)
            dominant_level: Nível hierárquico dominante
        """
        level_label = dominant_level or "unknown"

        if level_label not in V3Metrics.VALID_LEVELS:
            logger.warning(
                "invalid_level_label", level=level_label, valid_levels=V3Metrics.VALID_LEVELS
            )

        # Clamp value entre 0.0 e 1.0
        clamped_strength = max(0.0, min(1.0, strength))

        consensus_strength_gauge.labels(dominant_level=level_label).set(clamped_strength)

    @staticmethod
    def increment_dominant_level(level: str) -> None:
        """
        Incrementa contador de nível hierárquico dominante.

        Args:
            level: Nível hierárquico dominante na decisão
        """
        if level not in V3Metrics.VALID_LEVELS:
            logger.warning("invalid_level_label", level=level, valid_levels=V3Metrics.VALID_LEVELS)

        level_label = level or "unknown"
        dominant_level_counter.labels(level=level_label).inc()

    @staticmethod
    def increment_counterfactual_outcome(scenario_type: str, outcome: str) -> None:
        """
        Incrementa contador de outcomes contrafactuais.

        Args:
            scenario_type: Tipo de cenário contrafactual
            outcome: Outcome da análise (decision_changed, decision_unchanged)
        """
        if scenario_type not in V3Metrics.VALID_SCENARIO_TYPES:
            logger.warning(
                "invalid_scenario_type_label",
                scenario_type=scenario_type,
                valid_types=V3Metrics.VALID_SCENARIO_TYPES,
            )

        if outcome not in V3Metrics.VALID_OUTCOMES:
            logger.warning(
                "invalid_outcome_label", outcome=outcome, valid_outcomes=V3Metrics.VALID_OUTCOMES
            )

        counterfactual_outcome_counter.labels(scenario_type=scenario_type, outcome=outcome).inc()

    # Métodos compostos para operações comuns

    @staticmethod
    def record_explanation_generation(
        duration_seconds: float,
        component: str,
        format_type: str = "json",
        components_used: str = "hierarchical",
    ) -> None:
        """
        Regista geração completa de explicação (duração + contagem).

        Args:
            duration_seconds: Duração em segundos
            component: Nome do componente principal
            format_type: Formato da explicação
            components_used: String com componentes usados
        """
        V3Metrics.observe_generation_duration(duration_seconds, component)
        V3Metrics.increment_explanations_generated(format_type, components_used)

    @staticmethod
    def record_hierarchical_consensus(strength: float, dominant_level: Optional[str]) -> None:
        """
        Regista métricas completas de consenso hierárquico.

        Args:
            strength: Força do consenso (0.0 a 1.0)
            dominant_level: Nível hierárquico dominante
        """
        V3Metrics.set_consensus_strength(strength, dominant_level)
        if dominant_level:
            V3Metrics.increment_dominant_level(dominant_level)

    @staticmethod
    def record_counterfactual_analysis(scenario_type: str, outcome: str) -> None:
        """
        Registra outcome de análise contrafactual.

        Args:
            scenario_type: Tipo de cenário analisado
            outcome: Resultado da análise
        """
        V3Metrics.increment_counterfactual_outcome(scenario_type, outcome)
