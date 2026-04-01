"""
Risk Calculator

Cálculo agregado de risco multi-domínio com combinação inteligente de scores.
"""

import structlog
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone
from collections import defaultdict

from .config import RiskBand, RiskScoringConfig
from .models import RiskAssessment, RiskMatrix
from neural_hive_domain import UnifiedDomain


logger = structlog.get_logger(__name__)


class AggregationStrategy:
    """Estratégias de agregação de risco."""

    WEIGHTED_AVERAGE = 'weighted_average'
    MAXIMUM = 'maximum'
    MINIMUM = 'minimum'
    GEOMETRIC_MEAN = 'geometric_mean'
    HARMONIC_MEAN = 'harmonic_mean'


class RiskCalculator:
    """Calculadora de risco agregado multi-domínio."""

    def __init__(
        self,
        config: RiskScoringConfig,
        aggregation_strategy: str = AggregationStrategy.WEIGHTED_AVERAGE,
        domain_weights: Optional[Dict[str, float]] = None
    ):
        """Inicializa calculadora de risco.

        Args:
            config: Configuração do risk scoring
            aggregation_strategy: Estratégia de agregação
            domain_weights: Pesos por domínio (padrão: uniforme)
        """
        self.config = config
        self.aggregation_strategy = aggregation_strategy
        self.domain_weights = domain_weights or self._default_domain_weights()

    def _default_domain_weights(self) -> Dict[str, float]:
        """Pesos padrão por domínio."""
        return {
            UnifiedDomain.BUSINESS.value: 0.25,
            UnifiedDomain.TECHNICAL.value: 0.25,
            UnifiedDomain.SECURITY.value: 0.25,
            UnifiedDomain.OPERATIONAL.value: 0.15,
            UnifiedDomain.COMPLIANCE.value: 0.10,
        }

    def calculate_aggregate_risk(
        self,
        assessments: List[RiskAssessment],
        entity_id: str,
        entity_type: str = 'plan'
    ) -> RiskMatrix:
        """Calcula risco agregado a partir de múltiplas avaliações.

        Args:
            assessments: Lista de avaliações por domínio
            entity_id: ID da entidade avaliada
            entity_type: Tipo da entidade

        Returns:
            RiskMatrix com risco agregado
        """
        if not assessments:
            logger.warning("empty_assessments_list", entity_id=entity_id)
            return self._empty_matrix(entity_id, entity_type)

        # Criar dicionário de avaliações por domínio
        assessments_by_domain: Dict[str, RiskAssessment] = {}
        for assessment in assessments:
            domain_value = assessment.domain.value
            assessments_by_domain[domain_value] = assessment

        # Calcular score agregado
        overall_score, overall_band = self._aggregate_scores(assessments)

        # Encontrar domínio de maior risco
        highest_risk_domain = self._find_highest_risk_domain(assessments)

        # Calcular fatores agregados
        aggregate_factors = self._aggregate_factors(assessments)

        # Gerar reasoning
        reasoning = self._generate_aggregate_reasoning(
            assessments, overall_score, overall_band, highest_risk_domain
        )

        matrix = RiskMatrix(
            entity_id=entity_id,
            entity_type=entity_type,
            assessments=assessments_by_domain,
            overall_score=overall_score,
            overall_band=overall_band,
            highest_risk_domain=highest_risk_domain,
            created_at=datetime.now(timezone.utc)
        )

        logger.info(
            "aggregate_risk_calculated",
            entity_id=entity_id,
            entity_type=entity_type,
            overall_score=overall_score,
            overall_band=overall_band.value,
            highest_risk_domain=highest_risk_domain.value
        )

        return matrix

    def _aggregate_scores(
        self,
        assessments: List[RiskAssessment]
    ) -> Tuple[float, RiskBand]:
        """Agrega scores de múltiplas avaliações.

        Returns:
            Tupla (score_agregado, risk_band)
        """
        scores = [a.score for a in assessments]
        domains = [a.domain for a in assessments]

        if self.aggregation_strategy == AggregationStrategy.WEIGHTED_AVERAGE:
            aggregated = self._weighted_average(scores, domains)
        elif self.aggregation_strategy == AggregationStrategy.MAXIMUM:
            aggregated = max(scores)
        elif self.aggregation_strategy == AggregationStrategy.MINIMUM:
            aggregated = min(scores)
        elif self.aggregation_strategy == AggregationStrategy.GEOMETRIC_MEAN:
            aggregated = self._geometric_mean(scores)
        elif self.aggregation_strategy == AggregationStrategy.HARMONIC_MEAN:
            aggregated = self._harmonic_mean(scores)
        else:
            aggregated = sum(scores) / len(scores)

        # Classificar em risk band
        band = self._classify_aggregate_risk(aggregated)

        return aggregated, band

    def _weighted_average(
        self,
        scores: List[float],
        domains: List[UnifiedDomain]
    ) -> float:
        """Calcula média ponderada por domínio."""
        weighted_sum = 0.0
        total_weight = 0.0

        for score, domain in zip(scores, domains):
            weight = self.domain_weights.get(domain.value, 0.2)
            weighted_sum += score * weight
            total_weight += weight

        return weighted_sum / total_weight if total_weight > 0 else 0.5

    def _geometric_mean(self, scores: List[float]) -> float:
        """Calcula média geométrica."""
        import math
        # Evitar log(0) adicionando epsilon
        epsilon = 1e-6
        adjusted_scores = [max(s, epsilon) for s in scores]
        log_sum = sum(math.log(s) for s in adjusted_scores)
        return math.exp(log_sum / len(scores))

    def _harmonic_mean(self, scores: List[float]) -> float:
        """Calcula média harmônica."""
        # Penaliza valores altos - útil para risco (pior caso importa)
        epsilon = 1e-6
        adjusted_scores = [max(s, epsilon) for s in scores]
        reciprocal_sum = sum(1.0 / s for s in adjusted_scores)
        return len(scores) / reciprocal_sum

    def _classify_aggregate_risk(self, score: float) -> RiskBand:
        """Classifica score agregado em risk band."""
        # Thresholds mais conservadores para agregação
        if score >= 0.85:
            return RiskBand.CRITICAL
        elif score >= 0.65:
            return RiskBand.HIGH
        elif score >= 0.40:
            return RiskBand.MEDIUM
        else:
            return RiskBand.LOW

    def _find_highest_risk_domain(
        self,
        assessments: List[RiskAssessment]
    ) -> UnifiedDomain:
        """Encontra domínio com maior risco.

        Critério: maior score, desempate pela gravidade da band.
        """
        if not assessments:
            return UnifiedDomain.BUSINESS

        # Ordenar por score (descendente) e depois por band (CRITICAL > HIGH > MEDIUM > LOW)
        band_order = {RiskBand.CRITICAL: 4, RiskBand.HIGH: 3, RiskBand.MEDIUM: 2, RiskBand.LOW: 1}

        sorted_assessments = sorted(
            assessments,
            key=lambda a: (a.score, band_order.get(a.band, 0)),
            reverse=True
        )

        return sorted_assessments[0].domain

    def _aggregate_factors(
        self,
        assessments: List[RiskAssessment]
    ) -> Dict[str, float]:
        """Agrega fatores individuais de todos os domínios."""
        aggregate: Dict[str, float] = {}

        for assessment in assessments:
            domain_prefix = f"{assessment.domain.value}_"
            for factor_name, factor_value in assessment.factors.items():
                prefixed_name = f"{domain_prefix}{factor_name}"
                aggregate[prefixed_name] = factor_value

        return aggregate

    def _generate_aggregate_reasoning(
        self,
        assessments: List[RiskAssessment],
        overall_score: float,
        overall_band: RiskBand,
        highest_risk_domain: UnifiedDomain
    ) -> str:
        """Gera justificativa para risco agregado."""
        domain_scores = [
            f"{a.domain.value}={a.score:.2f}"
            for a in assessments
        ]

        return (
            f"Overall risk {overall_score:.2f} ({overall_band.value}). "
            f"Highest risk domain: {highest_risk_domain.value}. "
            f"Domain scores: {', '.join(domain_scores)}."
        )

    def _empty_matrix(self, entity_id: str, entity_type: str) -> RiskMatrix:
        """Cria matriz vazia para entidade sem avaliações."""
        return RiskMatrix(
            entity_id=entity_id,
            entity_type=entity_type,
            assessments={},
            overall_score=0.0,
            overall_band=RiskBand.LOW,
            highest_risk_domain=UnifiedDomain.BUSINESS,
            created_at=datetime.now(timezone.utc)
        )

    def calculate_domain_contribution(
        self,
        matrix: RiskMatrix
    ) -> Dict[str, Dict[str, float]]:
        """Calcula contribuição de cada domínio para o risco total.

        Returns:
            Dict com contribution_ratio e contribution_percentage por domínio
        """
        contributions = {}

        for domain_value, assessment in matrix.assessments.items():
            ratio = assessment.score / matrix.overall_score if matrix.overall_score > 0 else 0
            contributions[domain_value] = {
                'score': assessment.score,
                'contribution_ratio': ratio,
                'contribution_percentage': ratio * 100
            }

        return contributions

    def calculate_risk_velocity(
        self,
        historical_scores: List[Tuple[datetime, float]]
    ) -> Dict[str, float]:
        """Calcula velocidade de mudança do risco.

        Args:
            historical_scores: Lista de (timestamp, score) ordenada por tempo

        Returns:
            Dict com velocity (mudança por hora), acceleration, trend_direction
        """
        if len(historical_scores) < 2:
            return {'velocity': 0.0, 'acceleration': 0.0, 'trend_direction': 'stable'}

        # Calcular mudança absoluta entre pontos consecutivos
        deltas = []
        time_deltas_hours = []

        for i in range(1, len(historical_scores)):
            prev_time, prev_score = historical_scores[i - 1]
            curr_time, curr_score = historical_scores[i]

            score_delta = curr_score - prev_score
            time_delta_hours = (curr_time - prev_time).total_seconds() / 3600

            if time_delta_hours > 0:
                deltas.append(score_delta)
                time_deltas_hours.append(time_delta_hours)

        if not deltas:
            return {'velocity': 0.0, 'acceleration': 0.0, 'trend_direction': 'stable'}

        # Velocidade média (mudança de score por hora)
        total_score_change = sum(deltas)
        total_time = sum(time_deltas_hours)
        velocity = total_score_change / total_time if total_time > 0 else 0

        # Aceleração (mudança na velocidade)
        acceleration = 0.0
        if len(deltas) >= 3:
            # Usar últimas 3 mudanças para estimar aceleração
            recent_velocities = []
            for i in range(1, len(deltas)):
                if time_deltas_hours[i] > 0:
                    recent_velocities.append(deltas[i] / time_deltas_hours[i])

            if len(recent_velocities) >= 2:
                acceleration = (recent_velocities[-1] - recent_velocities[0]) / len(recent_velocities)

        # Direção da tendência
        if abs(velocity) < 0.001:
            trend_direction = 'stable'
        elif velocity > 0:
            trend_direction = 'increasing'
        else:
            trend_direction = 'decreasing'

        return {
            'velocity': velocity,
            'acceleration': acceleration,
            'trend_direction': trend_direction
        }
