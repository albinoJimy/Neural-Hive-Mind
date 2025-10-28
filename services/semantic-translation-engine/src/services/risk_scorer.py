"""
Risk Scorer - Evaluates risk for cognitive plans

Adapter para usar a biblioteca compartilhada neural_hive_risk_scoring.
Mantém a interface original para compatibilidade.
"""

import structlog
from typing import Dict, List, Tuple

from neural_hive_risk_scoring import RiskScoringEngine, RiskScoringConfig, RiskDomain
from neural_hive_risk_scoring import RiskBand as SharedRiskBand

from src.config.settings import Settings
from src.models.cognitive_plan import RiskBand, TaskNode

logger = structlog.get_logger()


class RiskScorer:
    """Risk evaluator for cognitive plans - usa biblioteca compartilhada"""

    def __init__(self, settings: Settings):
        self.settings = settings

        # Configurar engine compartilhado
        config = RiskScoringConfig(
            business_weights={
                'priority': settings.risk_weight_priority,
                'cost': 0.0,
                'kpi_alignment': 0.0,
                'complexity': settings.risk_weight_complexity
            },
            security_weights={
                'security_level': settings.risk_weight_security,
                'pii_exposure': 0.0,
                'authentication': 0.0,
                'encryption': 0.0
            },
            business_thresholds={
                'medium': 0.4,
                'high': settings.risk_threshold_high,
                'critical': settings.risk_threshold_critical
            }
        )
        self.engine = RiskScoringEngine(config)

    def score(
        self,
        intermediate_repr: Dict,
        tasks: List[TaskNode]
    ) -> Tuple[float, RiskBand, Dict[str, float]]:
        """
        Calculate risk score for plan usando biblioteca compartilhada

        Args:
            intermediate_repr: Parsed intent representation
            tasks: Generated tasks

        Returns:
            Tuple of (risk_score, risk_band, risk_factors)
        """
        # Preparar entidade para avaliação
        entity = {
            'priority': intermediate_repr['metadata']['priority'],
            'security_level': intermediate_repr['metadata']['security_level'],
            'complexity': self._calculate_complexity_level(tasks),
            'num_tasks': len(tasks),
            'total_dependencies': sum(len(task.dependencies) for task in tasks)
        }

        # Usar engine compartilhado - domínio BUSINESS
        assessment = self.engine.score(entity, RiskDomain.BUSINESS)

        # Converter RiskBand da biblioteca para o modelo local
        risk_band = self._convert_risk_band(assessment.band)

        # Extrair fatores individuais para compatibilidade
        risk_factors = {
            'priority': assessment.factors.get('priority', 0.0),
            'security': entity.get('security_level_risk', 0.0),
            'complexity': assessment.factors.get('complexity', 0.0),
            'weighted_score': assessment.score
        }

        logger.info(
            'Risk score calculado (via shared library)',
            risk_score=assessment.score,
            risk_band=risk_band.value,
            factors=risk_factors,
            domain='business'
        )

        return assessment.score, risk_band, risk_factors

    def _calculate_complexity_level(self, tasks: List[TaskNode]) -> str:
        """Calcula nível de complexidade baseado em tarefas"""
        num_tasks = len(tasks)

        if num_tasks >= 15:
            return 'very_high'
        elif num_tasks >= 10:
            return 'high'
        elif num_tasks >= 5:
            return 'medium'
        else:
            return 'low'

    def _convert_risk_band(self, shared_band: SharedRiskBand) -> RiskBand:
        """Converte RiskBand da biblioteca compartilhada para modelo local"""
        mapping = {
            SharedRiskBand.LOW: RiskBand.LOW,
            SharedRiskBand.MEDIUM: RiskBand.MEDIUM,
            SharedRiskBand.HIGH: RiskBand.HIGH,
            SharedRiskBand.CRITICAL: RiskBand.CRITICAL
        }
        return mapping.get(shared_band, RiskBand.MEDIUM)
