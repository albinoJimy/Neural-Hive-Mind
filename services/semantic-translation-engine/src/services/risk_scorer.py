"""
Risk Scorer - Evaluates risk for cognitive plans

Adapter para usar a biblioteca compartilhada neural_hive_risk_scoring.
Mantém a interface original para compatibilidade.
Suporta avaliação multi-domínio (BUSINESS, SECURITY, OPERATIONAL) com
integração de detecção de operações destrutivas.
"""

import structlog
from typing import Dict, List, Tuple

from neural_hive_risk_scoring import RiskScoringEngine, RiskScoringConfig, RiskDomain
from neural_hive_risk_scoring import RiskBand as SharedRiskBand

from src.config.settings import Settings
from src.models.cognitive_plan import RiskBand, TaskNode
from src.services.destructive_detector import DestructiveDetector

logger = structlog.get_logger()


class RiskScorer:
    """Risk evaluator for cognitive plans - usa biblioteca compartilhada"""

    # Pesos para agregação multi-domínio
    DOMAIN_WEIGHTS = {
        'business': 0.4,
        'security': 0.35,
        'operational': 0.25
    }

    # Floor de risco por severidade de operação destrutiva
    DESTRUCTIVE_FLOOR = {
        'low': 0.7,
        'medium': 0.7,
        'high': 0.8,
        'critical': 0.9
    }

    def __init__(self, settings: Settings):
        self.settings = settings

        # Instanciar detector de operações destrutivas
        self.destructive_detector = DestructiveDetector(settings)

        # Configurar engine compartilhado com suporte multi-domínio
        config = RiskScoringConfig(
            business_weights={
                'priority': settings.risk_weight_priority,
                'cost': 0.0,
                'kpi_alignment': 0.0,
                'complexity': settings.risk_weight_complexity
            },
            security_weights={
                'security_level': settings.risk_weight_security,
                'pii_exposure': 0.3,
                'authentication': 0.0,
                'encryption': 0.0
            },
            operational_weights={
                'availability': 0.3,
                'reliability': 0.3,
                'maintainability': 0.2,
                'observability': 0.2
            },
            business_thresholds={
                'medium': 0.4,
                'high': settings.risk_threshold_high,
                'critical': settings.risk_threshold_critical
            },
            security_thresholds={
                'medium': 0.3,
                'high': 0.6,
                'critical': 0.8
            },
            operational_thresholds={
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

    def _convert_to_shared_band(self, local_band: RiskBand) -> SharedRiskBand:
        """Converte RiskBand do modelo local para biblioteca compartilhada"""
        mapping = {
            RiskBand.LOW: SharedRiskBand.LOW,
            RiskBand.MEDIUM: SharedRiskBand.MEDIUM,
            RiskBand.HIGH: SharedRiskBand.HIGH,
            RiskBand.CRITICAL: SharedRiskBand.CRITICAL
        }
        return mapping.get(local_band, SharedRiskBand.MEDIUM)

    def score_multi_domain(
        self,
        intermediate_repr: Dict,
        tasks: List[TaskNode]
    ) -> Tuple[float, RiskBand, Dict[str, float], Dict[str, float], Dict[str, any]]:
        """
        Calcula score de risco multi-domínio para plano cognitivo.

        Avalia risco em três domínios (BUSINESS, SECURITY, OPERATIONAL),
        integra detecção de operações destrutivas, e aplica floor de risco
        para operações críticas.

        Args:
            intermediate_repr: Representação intermediária do intent
            tasks: Lista de tasks do plano

        Returns:
            Tupla contendo:
            - overall_score (float): Score agregado (0-1)
            - overall_band (RiskBand): Banda de risco final
            - risk_factors (Dict[str, float]): Fatores individuais
            - risk_matrix (Dict[str, float]): Scores numéricos por domínio
              (compatível com Avro map<string, double>)
            - destructive_analysis (Dict): Análise de operações destrutivas
              (is_destructive, destructive_tasks, severity, count)

        Example:
            >>> scorer = RiskScorer(settings)
            >>> score, band, factors, matrix, destructive = scorer.score_multi_domain(
            ...     intermediate_repr, tasks
            ... )
            >>> print(f"Score: {score}, Band: {band}")
            >>> print(f"Domains: {matrix}")
            >>> print(f"Destructive: {destructive['is_destructive']}")
        """
        # 1. Detectar operações destrutivas
        destructive_analysis = self.destructive_detector.detect(tasks)
        is_destructive = destructive_analysis['is_destructive']
        severity = destructive_analysis['severity']
        num_destructive_tasks = destructive_analysis['total_destructive_count']

        # 2. Preparar entidade base para avaliação
        metadata = intermediate_repr.get('metadata', {})
        intent_id = intermediate_repr.get('intent_id', 'unknown')
        priority = metadata.get('priority', 'normal')
        security_level = metadata.get('security_level', 'internal')

        entity = {
            'priority': priority,
            'security_level': security_level,
            'complexity': self._calculate_complexity_level(tasks),
            'num_tasks': len(tasks),
            'total_dependencies': sum(len(task.dependencies) for task in tasks),
            'is_destructive': is_destructive,
            'destructive_severity': severity
        }

        # 3. Avaliar domínio BUSINESS
        business_assessment = self.engine.score(entity, RiskDomain.BUSINESS)

        # 4. Avaliar domínio SECURITY
        # Enriquecer entidade com campos específicos de segurança
        entity['handles_pii'] = security_level in ['confidential', 'restricted']
        security_assessment = self.engine.score(entity, RiskDomain.SECURITY)

        # 5. Avaliar domínio OPERATIONAL
        # Enriquecer entidade com campos específicos operacionais
        entity['num_destructive_tasks'] = num_destructive_tasks
        operational_assessment = self.engine.score(entity, RiskDomain.OPERATIONAL)

        # 6. Calcular score agregado
        overall_score = self._aggregate_scores(
            business_assessment.score,
            security_assessment.score,
            operational_assessment.score
        )

        # 7. Aplicar floor de risco para operações destrutivas
        adjusted_score = self._apply_risk_floor(overall_score, is_destructive, severity)

        # 8. Classificar banda final (usa thresholds mais conservadores)
        risk_band = self._classify_band_from_score(adjusted_score)

        # 9. Identificar domínio de maior risco para logging
        domain_scores = {
            RiskDomain.BUSINESS: business_assessment.score,
            RiskDomain.SECURITY: security_assessment.score,
            RiskDomain.OPERATIONAL: operational_assessment.score
        }
        highest_risk_domain = max(domain_scores, key=domain_scores.get)

        # 10. Construir risk factors para compatibilidade
        risk_factors = {
            'priority': business_assessment.factors.get('priority', 0.0),
            'security': security_assessment.factors.get('security_level', 0.0),
            'complexity': business_assessment.factors.get('complexity', 0.0),
            'destructive': 1.0 if is_destructive else 0.0,
            'weighted_score': adjusted_score
        }

        # 11. Logging estruturado
        logger.info(
            'Risk score multi-domínio calculado',
            risk_score=adjusted_score,
            risk_band=risk_band.value,
            is_destructive=is_destructive,
            destructive_severity=severity,
            domains_evaluated=['business', 'security', 'operational'],
            highest_risk_domain=highest_risk_domain.value,
            intent_id=intent_id
        )

        # 12. Construir risk_matrix compatível com Avro map<string, double>
        # Contém apenas scores numéricos por domínio
        risk_matrix_numeric: Dict[str, float] = {
            'business': business_assessment.score,
            'security': security_assessment.score,
            'operational': operational_assessment.score,
            'overall': adjusted_score
        }

        # 13. Construir análise destrutiva separada (não vai no risk_matrix)
        destructive_result = {
            'is_destructive': is_destructive,
            'destructive_tasks': destructive_analysis['destructive_tasks'],
            'destructive_severity': severity,
            'destructive_count': num_destructive_tasks
        }

        return adjusted_score, risk_band, risk_factors, risk_matrix_numeric, destructive_result

    def _apply_risk_floor(
        self,
        base_score: float,
        is_destructive: bool,
        severity: str
    ) -> float:
        """
        Aplica floor de risco para operações destrutivas.

        Args:
            base_score: Score base calculado
            is_destructive: Se a operação é destrutiva
            severity: Nível de severidade (low/medium/high/critical)

        Returns:
            Score ajustado com floor aplicado se necessário
        """
        if not is_destructive:
            return base_score

        floor = self.DESTRUCTIVE_FLOOR.get(severity, 0.7)
        adjusted_score = max(base_score, floor)

        if adjusted_score > base_score:
            logger.warning(
                'Floor de risco aplicado para operação destrutiva',
                original_score=base_score,
                adjusted_score=adjusted_score,
                floor=floor,
                severity=severity
            )

        return adjusted_score

    def _aggregate_scores(
        self,
        business_score: float,
        security_score: float,
        operational_score: float
    ) -> float:
        """
        Agrega scores de múltiplos domínios em score final.

        Usa média ponderada: business=0.4, security=0.35, operational=0.25

        Args:
            business_score: Score do domínio BUSINESS
            security_score: Score do domínio SECURITY
            operational_score: Score do domínio OPERATIONAL

        Returns:
            Score agregado normalizado em [0, 1]
        """
        weighted_sum = (
            business_score * self.DOMAIN_WEIGHTS['business'] +
            security_score * self.DOMAIN_WEIGHTS['security'] +
            operational_score * self.DOMAIN_WEIGHTS['operational']
        )
        return max(0.0, min(1.0, weighted_sum))

    def _classify_band_from_score(self, score: float) -> RiskBand:
        """
        Classifica banda de risco a partir do score.

        Usa thresholds conservadores do domínio BUSINESS.

        Args:
            score: Score de risco (0-1)

        Returns:
            RiskBand correspondente
        """
        if score >= self.settings.risk_threshold_critical:
            return RiskBand.CRITICAL
        elif score >= self.settings.risk_threshold_high:
            return RiskBand.HIGH
        elif score >= 0.4:
            return RiskBand.MEDIUM
        else:
            return RiskBand.LOW
