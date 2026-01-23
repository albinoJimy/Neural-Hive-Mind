from typing import Dict, Any, List
from datetime import datetime, timedelta
import uuid
import structlog

from neural_hive_domain import DomainMapper, UnifiedDomain
from neural_hive_observability import get_tracer
from src.models.consolidated_decision import (
    ConsolidatedDecision,
    DecisionType,
    ConsensusMethod,
    SpecialistVote,
    ConsensusMetrics
)
from src.observability.metrics import ConsensusMetrics as ObservabilityMetrics
from src.services.bayesian_aggregator import BayesianAggregator
from src.services.voting_ensemble import VotingEnsemble
from src.services.compliance_fallback import ComplianceFallback

logger = structlog.get_logger()


class ConsensusOrchestrator:
    '''Orquestrador do pipeline de consenso multi-agente'''

    def __init__(self, config, pheromone_client):
        self.config = config
        self.pheromone_client = pheromone_client
        self.bayesian = BayesianAggregator(config)
        self.voting = VotingEnsemble(config)
        self.compliance = ComplianceFallback(config)

    async def process_consensus(
        self,
        cognitive_plan: Dict[str, Any],
        specialist_opinions: List[Dict[str, Any]]
    ) -> ConsolidatedDecision:
        '''Processa consenso completo

        Args:
            cognitive_plan: Plano cognitivo do Cognitive Orchestrator
            specialist_opinions: Lista de pareceres dos especialistas

        Returns:
            ConsolidatedDecision pronta para persistência e publicação
        '''
        start_time = datetime.utcnow()

        logger.info(
            'Iniciando processamento de consenso',
            plan_id=cognitive_plan['plan_id'],
            num_opinions=len(specialist_opinions)
        )

        # 1. Calcular pesos dinâmicos com feromônios
        weights = await self._calculate_dynamic_weights(
            cognitive_plan,
            specialist_opinions
        )

        tracer = get_tracer()
        with tracer.start_as_current_span("bayesian_aggregation") as span:
            span.set_attribute("neural.hive.plan_id", cognitive_plan.get('plan_id'))
            span.set_attribute("neural.hive.specialist_count", len(specialist_opinions))

            # 2. Agregação Bayesiana
            aggregated_confidence, conf_variance = self.bayesian.aggregate_confidence(
                specialist_opinions,
                weights
            )
            aggregated_risk, risk_variance = self.bayesian.aggregate_risk(
                specialist_opinions,
                weights
            )
            divergence = self.bayesian.calculate_divergence(
                specialist_opinions,
                aggregated_confidence,
                aggregated_risk
            )
            span.set_attribute("neural.hive.consensus_confidence", aggregated_confidence)

        # 3. Voting Ensemble
        final_recommendation, vote_distribution = self.voting.aggregate_recommendations(
            specialist_opinions,
            weights
        )
        is_unanimous = self.voting.check_unanimity(specialist_opinions)

        # 4. Determinar método de consenso
        consensus_method = self._determine_consensus_method(
            aggregated_confidence,
            divergence,
            is_unanimous
        )

        # 5. Verificar compliance
        is_compliant, violations, adaptive_thresholds = self.compliance.check_compliance(
            cognitive_plan,
            specialist_opinions,
            aggregated_confidence,
            aggregated_risk,
            divergence,
            is_unanimous
        )

        # 6. Decisão final
        if is_compliant:
            final_decision = self._map_recommendation_to_decision(final_recommendation)
            requires_review = False
        else:
            # Aplicar fallback determinístico
            fallback_decision = self.compliance.apply_fallback_decision(
                cognitive_plan,
                specialist_opinions,
                violations
            )
            # Convert string to DecisionType enum
            final_decision = DecisionType[fallback_decision.upper()]
            requires_review = True
            consensus_method = ConsensusMethod.FALLBACK

        # 7. Construir votos estruturados
        specialist_votes = self._build_specialist_votes(
            specialist_opinions,
            weights
        )

        # 8. Calcular métricas
        convergence_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

        # Obter força de feromônio agregada
        pheromone_strength = await self._get_average_pheromone_strength(
            specialist_opinions,
            cognitive_plan.get('domain', 'general')
        )

        consensus_metrics = ConsensusMetrics(
            divergence_score=divergence,
            convergence_time_ms=convergence_time_ms,
            unanimous=is_unanimous,
            fallback_used=(consensus_method == ConsensusMethod.FALLBACK),
            pheromone_strength=pheromone_strength,
            bayesian_confidence=aggregated_confidence,
            voting_confidence=vote_distribution.get(final_recommendation, 0.0)
        )

        # 9. Construir decisão consolidada
        # Extrair correlation_id com fallback UUID para garantir rastreabilidade
        # VULNERABILIDADE CORRIGIDA: Escalar para ERROR e adicionar contexto de debug
        correlation_id = cognitive_plan.get('correlation_id')
        if not correlation_id or (isinstance(correlation_id, str) and not correlation_id.strip()):
            correlation_id = str(uuid.uuid4())

            # Registrar métricas
            ObservabilityMetrics.increment_correlation_id_missing()
            ObservabilityMetrics.increment_correlation_id_generated()

            # ERROR: Isso quebra rastreamento distribuído - deve ser investigado
            logger.error(
                'VULN-001: correlation_id ausente no cognitive_plan - rastreamento distribuído comprometido',
                plan_id=cognitive_plan['plan_id'],
                intent_id=cognitive_plan['intent_id'],
                generated_correlation_id=correlation_id,
                upstream_source='semantic-translation-engine',
                action_required='Verificar propagação de correlation_id no STE',
                trace_id=cognitive_plan.get('trace_id'),
                span_id=cognitive_plan.get('span_id')
            )

        decision = ConsolidatedDecision(
            plan_id=cognitive_plan['plan_id'],
            intent_id=cognitive_plan['intent_id'],
            correlation_id=correlation_id,
            trace_id=cognitive_plan.get('trace_id'),
            span_id=cognitive_plan.get('span_id'),
            final_decision=final_decision,
            consensus_method=consensus_method,
            aggregated_confidence=aggregated_confidence,
            aggregated_risk=aggregated_risk,
            specialist_votes=specialist_votes,
            consensus_metrics=consensus_metrics,
            explainability_token=f"explain-{cognitive_plan['plan_id']}",
            reasoning_summary=self._generate_reasoning_summary(
                final_decision,
                aggregated_confidence,
                aggregated_risk,
                is_unanimous,
                violations
            ),
            compliance_checks={
                # Base thresholds (compatibilidade legado)
                'confidence_threshold': aggregated_confidence >= self.config.min_confidence_score,
                'divergence_threshold': divergence <= self.config.max_divergence_threshold,
                # Campos explícitos de base
                'base_confidence_threshold_passed': aggregated_confidence >= self.config.min_confidence_score,
                'base_divergence_threshold_passed': divergence <= self.config.max_divergence_threshold,
                'base_thresholds': {
                    'min_confidence': self.config.min_confidence_score,
                    'max_divergence': self.config.max_divergence_threshold
                },
                # Campos adaptativos (refletem thresholds efetivamente aplicados pelo ComplianceFallback)
                'adaptive_confidence_threshold_passed': aggregated_confidence >= adaptive_thresholds['min_confidence'],
                'adaptive_divergence_threshold_passed': divergence <= adaptive_thresholds['max_divergence'],
                'adaptive_thresholds': {
                    'min_confidence': adaptive_thresholds['min_confidence'],
                    'max_divergence': adaptive_thresholds['max_divergence'],
                    'health_status': adaptive_thresholds['health_status'],
                    'degraded_count': adaptive_thresholds['degraded_count'],
                    'adjustment_reason': adaptive_thresholds['adjustment_reason'],
                },
                'risk_acceptable': aggregated_risk < self.config.critical_risk_threshold,
                'adaptive_thresholds_used': True
            },
            guardrails_triggered=violations,
            requires_human_review=requires_review,
            cognitive_plan=cognitive_plan,  # Incluir plano para downstream (Orchestrator)
            metadata={
                'num_specialists': str(len(specialist_opinions)),
                'vote_distribution': str(vote_distribution),
                'domain': cognitive_plan.get('domain', 'general')
            }
        )

        # Calcular hash de integridade
        decision.hash = decision.calculate_hash()

        # 10. Publicar feromônios
        await self._publish_pheromones(decision, cognitive_plan, specialist_opinions)

        logger.info(
            'Consenso processado',
            decision_id=decision.decision_id,
            plan_id=decision.plan_id,
            final_decision=decision.final_decision.value,
            consensus_method=decision.consensus_method.value,
            convergence_time_ms=convergence_time_ms
        )

        return decision

    async def _calculate_dynamic_weights(
        self,
        cognitive_plan: Dict[str, Any],
        specialist_opinions: List[Dict[str, Any]]
    ) -> Dict[str, float]:
        '''Calcula pesos dinâmicos baseados em feromônios'''
        weights = {}
        domain_str = cognitive_plan.get('domain', 'general')

        # Normalizar domain para UnifiedDomain
        try:
            domain = DomainMapper.normalize(domain_str, 'intent_envelope')
        except ValueError:
            logger.warning(
                'domain_normalization_failed_using_default',
                original_domain=domain_str,
                default_domain='BUSINESS'
            )
            domain = UnifiedDomain.BUSINESS

        for opinion in specialist_opinions:
            specialist_type = opinion['specialist_type']

            if self.config.enable_pheromones and self.pheromone_client:
                weight = await self.pheromone_client.calculate_dynamic_weight(
                    specialist_type,
                    domain,
                    base_weight=0.2
                )
            else:
                # Peso estático se feromônios desabilitados
                weight = 0.2

            weights[specialist_type] = weight

        logger.debug('Pesos dinâmicos calculados', weights=weights, domain=domain.value)
        return weights

    async def _get_average_pheromone_strength(
        self,
        specialist_opinions: List[Dict[str, Any]],
        domain: str
    ) -> float:
        '''Obtém força média de feromônios para os especialistas'''
        if not self.config.enable_pheromones or not self.pheromone_client:
            return 0.0

        # Normalizar domain para UnifiedDomain
        try:
            normalized_domain = DomainMapper.normalize(domain, 'intent_envelope')
        except ValueError:
            logger.warning(
                'domain_normalization_failed_using_default',
                original_domain=domain,
                default_domain='BUSINESS'
            )
            normalized_domain = UnifiedDomain.BUSINESS

        strengths = []
        for opinion in specialist_opinions:
            specialist_type = opinion['specialist_type']
            pheromones = await self.pheromone_client.get_aggregated_pheromone(
                specialist_type,
                normalized_domain
            )
            strengths.append(pheromones['net_strength'])

        return sum(strengths) / len(strengths) if strengths else 0.0

    def _determine_consensus_method(
        self,
        aggregated_confidence: float,
        divergence: float,
        is_unanimous: bool
    ) -> ConsensusMethod:
        '''Determina qual método de consenso foi dominante'''
        if is_unanimous:
            return ConsensusMethod.UNANIMOUS
        elif self.config.enable_bayesian_averaging:
            return ConsensusMethod.BAYESIAN
        else:
            return ConsensusMethod.VOTING

    def _map_recommendation_to_decision(self, recommendation: str) -> DecisionType:
        '''Mapeia recomendação de especialista para DecisionType'''
        mapping = {
            'approve': DecisionType.APPROVE,
            'reject': DecisionType.REJECT,
            'review_required': DecisionType.REVIEW_REQUIRED,
            'conditional': DecisionType.CONDITIONAL
        }
        return mapping.get(recommendation, DecisionType.REVIEW_REQUIRED)

    def _build_specialist_votes(
        self,
        specialist_opinions: List[Dict[str, Any]],
        weights: Dict[str, float]
    ) -> List[SpecialistVote]:
        '''Constrói lista de votos estruturados'''
        votes = []
        for opinion in specialist_opinions:
            specialist_type = opinion['specialist_type']
            op = opinion['opinion']

            vote = SpecialistVote(
                specialist_type=specialist_type,
                opinion_id=opinion['opinion_id'],
                confidence_score=op['confidence_score'],
                risk_score=op['risk_score'],
                recommendation=op['recommendation'],
                weight=weights.get(specialist_type, 0.2),
                processing_time_ms=opinion.get('processing_time_ms', 0)
            )
            votes.append(vote)

        return votes

    def _generate_reasoning_summary(
        self,
        final_decision: DecisionType,
        confidence: float,
        risk: float,
        is_unanimous: bool,
        violations: List[str]
    ) -> str:
        '''Gera resumo da justificativa da decisão'''
        if is_unanimous:
            summary = f"Decisão unânime: {final_decision.value}. "
        else:
            summary = f"Decisão por consenso: {final_decision.value}. "

        summary += f"Confiança agregada: {confidence:.2f}, Risco agregado: {risk:.2f}. "

        if violations:
            summary += f"Guardrails acionados: {len(violations)}. "

        return summary

    async def _publish_pheromones(
        self,
        decision: ConsolidatedDecision,
        cognitive_plan: Dict[str, Any],
        specialist_opinions: List[Dict[str, Any]]
    ):
        '''Publica feromônios baseados na decisão final'''
        if not self.config.enable_pheromones or not self.pheromone_client:
            return

        domain_str = cognitive_plan.get('domain', 'general')

        # Normalizar domain para UnifiedDomain
        try:
            domain = DomainMapper.normalize(domain_str, 'intent_envelope')
        except ValueError:
            logger.warning(
                'domain_normalization_failed_using_default',
                original_domain=domain_str,
                default_domain='BUSINESS'
            )
            domain = UnifiedDomain.BUSINESS

        # Determinar tipo de feromônio baseado na decisão
        from src.models.pheromone_signal import PheromoneType

        if decision.final_decision == DecisionType.APPROVE:
            pheromone_type = PheromoneType.SUCCESS
            strength = decision.aggregated_confidence
        elif decision.final_decision == DecisionType.REJECT:
            pheromone_type = PheromoneType.FAILURE
            strength = decision.aggregated_risk
        else:
            pheromone_type = PheromoneType.WARNING
            strength = 0.5

        # Publicar feromônio para cada especialista
        for opinion in specialist_opinions:
            specialist_type = opinion['specialist_type']

            await self.pheromone_client.publish_pheromone(
                specialist_type=specialist_type,
                domain=domain,
                pheromone_type=pheromone_type,
                strength=strength,
                plan_id=decision.plan_id,
                intent_id=decision.intent_id,
                decision_id=decision.decision_id
            )

        logger.debug(
            'Feromônios publicados',
            decision_id=decision.decision_id,
            pheromone_type=pheromone_type.value,
            domain=domain.value,
            num_specialists=len(specialist_opinions)
        )
