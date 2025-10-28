import numpy as np
from scipy import stats
from typing import List, Dict, Any, Tuple
import structlog

logger = structlog.get_logger()


class BayesianAggregator:
    '''Agregador Bayesiano para combinar pareceres de especialistas'''

    def __init__(self, config):
        self.config = config
        self.prior_weight = config.bayesian_prior_weight

    def aggregate_confidence(
        self,
        opinions: List[Dict[str, Any]],
        weights: Dict[str, float]
    ) -> Tuple[float, float]:
        '''Agrega scores de confiança usando Bayesian Model Averaging

        Args:
            opinions: Lista de pareceres dos especialistas
            weights: Pesos dinâmicos por especialista

        Returns:
            Tuple (confiança agregada, variância)
        '''
        scores = []
        specialist_weights = []

        for opinion in opinions:
            specialist_type = opinion['specialist_type']
            confidence = opinion['opinion']['confidence_score']
            weight = weights.get(specialist_type, 0.2)

            scores.append(confidence)
            specialist_weights.append(weight)

        # Normalizar pesos para somar 1.0
        total_weight = sum(specialist_weights)
        normalized_weights = [w / total_weight for w in specialist_weights]

        # Calcular média ponderada (posterior mean)
        # Incorporar prior (assumindo prior uniforme Beta(1,1) → mean=0.5)
        prior_mean = 0.5

        # Weighted average com prior
        posterior_mean = (
            self.prior_weight * prior_mean +
            (1 - self.prior_weight) * np.average(scores, weights=normalized_weights)
        )

        # Calcular variância (incerteza)
        variance = np.average(
            [(score - posterior_mean) ** 2 for score in scores],
            weights=normalized_weights
        )

        logger.debug(
            'Bayesian confidence aggregation',
            num_opinions=len(opinions),
            scores=scores,
            weights=normalized_weights,
            posterior_mean=posterior_mean,
            variance=variance
        )

        return posterior_mean, variance

    def aggregate_risk(
        self,
        opinions: List[Dict[str, Any]],
        weights: Dict[str, float]
    ) -> Tuple[float, float]:
        '''Agrega scores de risco usando Bayesian Model Averaging'''
        scores = []
        specialist_weights = []

        for opinion in opinions:
            specialist_type = opinion['specialist_type']
            risk = opinion['opinion']['risk_score']
            weight = weights.get(specialist_type, 0.2)

            scores.append(risk)
            specialist_weights.append(weight)

        # Normalizar pesos
        total_weight = sum(specialist_weights)
        normalized_weights = [w / total_weight for w in specialist_weights]

        # Prior para risco (assumindo prior conservador → mean=0.5)
        prior_mean = 0.5

        # Weighted average com prior
        posterior_mean = (
            self.prior_weight * prior_mean +
            (1 - self.prior_weight) * np.average(scores, weights=normalized_weights)
        )

        # Variância
        variance = np.average(
            [(score - posterior_mean) ** 2 for score in scores],
            weights=normalized_weights
        )

        logger.debug(
            'Bayesian risk aggregation',
            num_opinions=len(opinions),
            scores=scores,
            weights=normalized_weights,
            posterior_mean=posterior_mean,
            variance=variance
        )

        return posterior_mean, variance

    def calculate_divergence(
        self,
        opinions: List[Dict[str, Any]],
        aggregated_confidence: float,
        aggregated_risk: float
    ) -> float:
        '''Calcula divergência entre especialistas

        Usa desvio padrão normalizado dos scores em relação à média agregada
        '''
        # Calcular divergência de confiança
        confidence_scores = [op['opinion']['confidence_score'] for op in opinions]
        confidence_divergence = np.std(confidence_scores) / (aggregated_confidence + 1e-6)

        # Calcular divergência de risco
        risk_scores = [op['opinion']['risk_score'] for op in opinions]
        risk_divergence = np.std(risk_scores) / (aggregated_risk + 1e-6)

        # Divergência total (média das duas)
        total_divergence = (confidence_divergence + risk_divergence) / 2.0

        # Normalizar para [0, 1]
        total_divergence = min(1.0, total_divergence)

        logger.debug(
            'Divergence calculation',
            confidence_divergence=confidence_divergence,
            risk_divergence=risk_divergence,
            total_divergence=total_divergence
        )

        return total_divergence
