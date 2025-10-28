import structlog
from typing import Dict, Any, List, Optional, TYPE_CHECKING
from datetime import datetime, timedelta
import statistics

from ..config import Settings
from ..models import (
    StrategicDecision, DecisionType, DecisionContext, DecisionAnalysis,
    DecisionAction, RiskAssessment, TriggeredBy
)
from ..clients import (
    MongoDBClient, RedisClient, Neo4jClient, PrometheusClient, PheromoneClient
)

if TYPE_CHECKING:
    from .replanning_coordinator import ReplanningCoordinator


logger = structlog.get_logger()


class StrategicDecisionEngine:
    """
    Core do Queen Agent - Engine de decisão estratégica

    Implementa:
    - Swarm Heuristics (feromônios)
    - Bayesian Analysis (combinação de probabilidades)
    - Multi-Objective Optimization (risco, valor, custo)
    """

    def __init__(
        self,
        mongodb_client: MongoDBClient,
        redis_client: RedisClient,
        neo4j_client: Neo4jClient,
        prometheus_client: PrometheusClient,
        pheromone_client: PheromoneClient,
        replanning_coordinator: 'ReplanningCoordinator',
        settings: Settings
    ):
        self.mongodb_client = mongodb_client
        self.redis_client = redis_client
        self.neo4j_client = neo4j_client
        self.prometheus_client = prometheus_client
        self.pheromone_client = pheromone_client
        self.replanning_coordinator = replanning_coordinator
        self.settings = settings

    async def process_consolidated_decision(self, decision_data: Dict[str, Any]) -> Optional[StrategicDecision]:
        """
        Processar decisão consolidada do Consensus Engine
        Determina se requer ação estratégica
        """
        try:
            decision_id = decision_data.get('decision_id')
            aggregated_risk = decision_data.get('aggregated_risk', 0.0)
            divergence_score = decision_data.get('consensus_metrics', {}).get('divergence_score', 0.0)
            requires_human_review = decision_data.get('requires_human_review', False)
            guardrails_triggered = decision_data.get('guardrails_triggered', [])

            # Critérios para ação estratégica
            needs_action = (
                aggregated_risk > 0.7 or
                divergence_score > 0.05 or
                requires_human_review or
                len(guardrails_triggered) > 0
            )

            if not needs_action:
                logger.debug("consolidated_decision_no_action_needed", decision_id=decision_id)
                return None

            # Acionar decisão estratégica
            logger.info(
                "consolidated_decision_requires_strategic_action",
                decision_id=decision_id,
                risk=aggregated_risk,
                divergence=divergence_score
            )

            trigger = {
                'event_type': 'consolidated_decision',
                'source_id': decision_id,
                'decision_data': decision_data
            }

            return await self.make_strategic_decision(trigger)

        except Exception as e:
            logger.error("process_consolidated_decision_failed", error=str(e))
            return None

    async def process_telemetry_event(self, event: Dict[str, Any]) -> Optional[StrategicDecision]:
        """Processar evento de telemetria agregada"""
        try:
            metric_type = event.get('metric_type')
            value = event.get('value')
            source = event.get('source')

            # Critérios de anomalia
            if metric_type == 'sla_violation' and value > 0.05:
                trigger = {
                    'event_type': 'sla_violation',
                    'source_id': source,
                    'telemetry_data': event
                }
                return await self.make_strategic_decision(trigger)

            elif metric_type == 'resource_saturation' and value > 0.8:
                trigger = {
                    'event_type': 'resource_saturation',
                    'source_id': source,
                    'telemetry_data': event
                }
                return await self.make_strategic_decision(trigger)

            return None

        except Exception as e:
            logger.error("process_telemetry_event_failed", error=str(e))
            return None

    async def process_critical_incident(self, incident: Dict[str, Any]) -> Optional[StrategicDecision]:
        """Processar incidente crítico dos Guards"""
        try:
            incident_id = incident.get('incident_id')
            severity = incident.get('severity')

            if severity not in ['CRITICAL', 'HIGH']:
                return None

            trigger = {
                'event_type': 'critical_incident',
                'source_id': incident_id,
                'incident_data': incident
            }

            return await self.make_strategic_decision(trigger)

        except Exception as e:
            logger.error("process_critical_incident_failed", error=str(e))
            return None

    async def make_strategic_decision(self, trigger: Dict[str, Any]) -> Optional[StrategicDecision]:
        """
        Método principal de decisão estratégica

        Pipeline:
        1. Agregar contexto (Neo4j, Prometheus, Redis, Pheromones)
        2. Identificar conflitos
        3. Aplicar heurísticas swarm + análise Bayesiana
        4. Calcular confidence e risk
        5. Validar guardrails
        6. Gerar StrategicDecision
        7. Persistir no ledger
        8. Publicar no Kafka (delegado ao caller)
        """
        try:
            event_type = trigger.get('event_type')
            source_id = trigger.get('source_id')

            logger.info("making_strategic_decision", event_type=event_type, source_id=source_id)

            # 1. Agregar contexto
            context = await self._aggregate_context(trigger)

            # 2. Análise
            analysis = await self._perform_analysis(context, trigger)

            # 3. Determinar tipo de decisão e ação
            decision_type, action = await self._determine_action(trigger, context, analysis)

            # 4. Calcular confidence e risk
            confidence_score = await self._calculate_confidence(context, analysis)
            risk_assessment = await self._assess_risk(trigger, context, analysis)

            # 5. Validar guardrails
            guardrails_validated = await self._validate_guardrails(decision_type, action, risk_assessment)

            # 6. Gerar reasoning summary
            reasoning_summary = self._generate_reasoning_summary(
                event_type, decision_type, confidence_score, risk_assessment, analysis
            )

            # 7. Criar decisão estratégica
            decision = StrategicDecision(
                decision_type=decision_type,
                triggered_by=TriggeredBy(
                    event_type=event_type,
                    source_id=source_id,
                    timestamp=int(datetime.now().timestamp() * 1000)
                ),
                context=context,
                analysis=analysis,
                decision=action,
                confidence_score=confidence_score,
                risk_assessment=risk_assessment,
                guardrails_validated=guardrails_validated,
                reasoning_summary=reasoning_summary,
                expires_at=int((datetime.now() + timedelta(hours=24)).timestamp() * 1000)
            )

            # Calcular hash
            decision.hash = decision.calculate_hash()

            # 8. Persistir no MongoDB
            await self.mongodb_client.save_strategic_decision(decision)

            # 9. Registrar no Neo4j
            await self.neo4j_client.record_strategic_decision(decision)

            # 10. Atualizar feromônios
            await self._update_pheromones(decision, success=True)

            logger.info(
                "strategic_decision_made",
                decision_id=decision.decision_id,
                decision_type=decision.decision_type.value,
                confidence=confidence_score,
                risk=risk_assessment.risk_score
            )

            return decision

        except Exception as e:
            logger.error("make_strategic_decision_failed", error=str(e))
            return None

    async def _aggregate_context(self, trigger: Dict[str, Any]) -> DecisionContext:
        """Agregar contexto de múltiplas fontes"""
        try:
            # Buscar planos ativos (placeholder - pode vir do trigger ou Neo4j)
            active_plans = trigger.get('decision_data', {}).get('plan_id', [])
            if isinstance(active_plans, str):
                active_plans = [active_plans]

            # Buscar incidentes críticos (Prometheus ou cache)
            critical_incidents = []

            # Buscar violações de SLA (Prometheus)
            sla_violations = []

            # Calcular saturação de recursos
            resource_data = await self.prometheus_client.get_resource_saturation()
            resource_saturation = max(resource_data.values()) if resource_data else 0.0

            return DecisionContext(
                active_plans=active_plans,
                critical_incidents=critical_incidents,
                sla_violations=sla_violations,
                resource_saturation=resource_saturation
            )

        except Exception as e:
            logger.error("aggregate_context_failed", error=str(e))
            return DecisionContext()

    async def _perform_analysis(self, context: DecisionContext, trigger: Dict[str, Any]) -> DecisionAnalysis:
        """Realizar análise do contexto"""
        try:
            # Query Neo4j para contexto estratégico
            neo4j_results = {}
            if context.active_plans:
                neo4j_results = await self.neo4j_client.query_strategic_context(context.active_plans)

            # Buscar sinais de feromônios
            pheromone_signals = {}
            for plan_id in context.active_plans:
                signals = await self.pheromone_client.get_domain_signals(plan_id)
                pheromone_signals[plan_id] = signals.get('SUCCESS', 0.0) - signals.get('FAILURE', 0.0)

            # Snapshot de métricas do Prometheus
            metrics_snapshot = {}
            if context.active_plans:
                for plan_id in context.active_plans[:5]:  # Limitar a 5 para performance
                    sla = await self.prometheus_client.get_sla_compliance(plan_id, '5m')
                    metrics_snapshot[f"{plan_id}_sla"] = sla

            # Identificar domínios em conflito (placeholder)
            conflict_domains = []

            return DecisionAnalysis(
                neo4j_query_results=neo4j_results,
                pheromone_signals=pheromone_signals,
                metrics_snapshot=metrics_snapshot,
                conflict_domains=conflict_domains
            )

        except Exception as e:
            logger.error("perform_analysis_failed", error=str(e))
            return DecisionAnalysis()

    async def _determine_action(
        self,
        trigger: Dict[str, Any],
        context: DecisionContext,
        analysis: DecisionAnalysis
    ) -> tuple[DecisionType, DecisionAction]:
        """Determinar tipo de decisão e ação a tomar"""
        event_type = trigger.get('event_type')

        # Heurísticas baseadas no tipo de evento
        if event_type == 'sla_violation':
            return (
                DecisionType.REPLANNING,
                DecisionAction(
                    action='trigger_replanning',
                    target_entities=context.active_plans,
                    parameters={'reason': 'sla_violation'},
                    rationale='Violações de SLA detectadas, replanejamento necessário para recuperar compliance'
                )
            )

        elif event_type == 'resource_saturation':
            return (
                DecisionType.RESOURCE_REALLOCATION,
                DecisionAction(
                    action='reallocate_resources',
                    target_entities=context.active_plans,
                    parameters={'increase_resources': True},
                    rationale='Saturação de recursos detectada, realocação necessária'
                )
            )

        elif event_type == 'critical_incident':
            incident_type = trigger.get('incident_data', {}).get('incident_type')
            if incident_type == 'security_threat':
                return (
                    DecisionType.QOS_ADJUSTMENT,
                    DecisionAction(
                        action='pause_execution',
                        target_entities=context.active_plans,
                        parameters={'reason': 'security_threat'},
                        rationale='Ameaça de segurança detectada, pausando execução para investigação'
                    )
                )

        elif event_type == 'consolidated_decision':
            # Verificar divergência
            divergence = trigger.get('decision_data', {}).get('consensus_metrics', {}).get('divergence_score', 0.0)
            if divergence > 0.05:
                return (
                    DecisionType.CONFLICT_RESOLUTION,
                    DecisionAction(
                        action='resolve_conflict',
                        target_entities=context.active_plans,
                        parameters={'divergence_score': divergence},
                        rationale=f'Alta divergência ({divergence:.3f}) detectada entre especialistas, arbitragem necessária'
                    )
                )

        # Default: Priorização
        return (
            DecisionType.PRIORITIZATION,
            DecisionAction(
                action='adjust_priorities',
                target_entities=context.active_plans,
                parameters={},
                rationale='Ajuste de prioridades baseado em contexto estratégico'
            )
        )

    async def _calculate_confidence(self, context: DecisionContext, analysis: DecisionAnalysis) -> float:
        """
        Calcular confidence score

        Fórmula: (context_completeness * 0.3) + (pheromone_strength * 0.3) + (historical_success_rate * 0.4)
        """
        try:
            # Context completeness
            context_fields = [
                len(context.active_plans) > 0,
                len(context.critical_incidents) >= 0,
                context.resource_saturation >= 0
            ]
            context_completeness = sum(context_fields) / len(context_fields)

            # Pheromone strength (média dos sinais)
            pheromone_values = list(analysis.pheromone_signals.values())
            pheromone_strength = sum(pheromone_values) / len(pheromone_values) if pheromone_values else 0.5
            pheromone_strength = max(0.0, min(1.0, (pheromone_strength + 1.0) / 2.0))  # Normalizar [-1, 1] -> [0, 1]

            # Historical success rate (placeholder - seria calculado de decisões anteriores)
            historical_success_rate = 0.8

            confidence = (
                context_completeness * 0.3 +
                pheromone_strength * 0.3 +
                historical_success_rate * 0.4
            )

            return min(1.0, max(0.0, confidence))

        except Exception as e:
            logger.error("calculate_confidence_failed", error=str(e))
            return 0.5

    async def _assess_risk(
        self,
        trigger: Dict[str, Any],
        context: DecisionContext,
        analysis: DecisionAnalysis
    ) -> RiskAssessment:
        """Avaliar risco da decisão"""
        try:
            risk_factors = []
            risk_score = 0.0

            # Fator 1: Saturação de recursos
            if context.resource_saturation > 0.8:
                risk_factors.append('high_resource_saturation')
                risk_score += 0.3

            # Fator 2: Incidentes críticos
            if len(context.critical_incidents) > 0:
                risk_factors.append('critical_incidents_active')
                risk_score += 0.2 * len(context.critical_incidents)

            # Fator 3: Violações de SLA
            if len(context.sla_violations) > 0:
                risk_factors.append('sla_violations')
                risk_score += 0.15 * len(context.sla_violations)

            # Fator 4: Feromônios negativos
            negative_pheromones = sum(1 for v in analysis.pheromone_signals.values() if v < -0.5)
            if negative_pheromones > 0:
                risk_factors.append('negative_pheromone_trails')
                risk_score += 0.1 * negative_pheromones

            risk_score = min(1.0, risk_score)

            # Mitigações baseadas em risk_score
            mitigations = []
            if risk_score > 0.7:
                mitigations.append('require_human_approval')
                mitigations.append('increase_monitoring')
            elif risk_score > 0.5:
                mitigations.append('increase_monitoring')
                mitigations.append('prepare_rollback_plan')

            return RiskAssessment(
                risk_score=risk_score,
                risk_factors=risk_factors,
                mitigations=mitigations
            )

        except Exception as e:
            logger.error("assess_risk_failed", error=str(e))
            return RiskAssessment(risk_score=0.5, risk_factors=[], mitigations=[])

    async def _validate_guardrails(
        self,
        decision_type: DecisionType,
        action: DecisionAction,
        risk_assessment: RiskAssessment
    ) -> List[str]:
        """Validar decisão contra guardrails éticos"""
        # TODO: Integrar com OPA policies
        guardrails = []

        # Guardrails básicos
        if risk_assessment.risk_score < 0.9:
            guardrails.append('risk_threshold_acceptable')

        if decision_type != DecisionType.EXCEPTION_APPROVAL:
            guardrails.append('no_guardrail_violations')

        return guardrails

    def _generate_reasoning_summary(
        self,
        event_type: str,
        decision_type: DecisionType,
        confidence: float,
        risk: RiskAssessment,
        analysis: DecisionAnalysis
    ) -> str:
        """Gerar resumo em linguagem natural da lógica de decisão"""
        summary = f"Decisão estratégica do tipo {decision_type.value} acionada por evento {event_type}. "
        summary += f"Confiança: {confidence:.2%}. Risco: {risk.risk_score:.2%}. "

        if risk.risk_factors:
            summary += f"Fatores de risco: {', '.join(risk.risk_factors[:3])}. "

        if analysis.conflict_domains:
            summary += f"Conflitos detectados em: {', '.join(analysis.conflict_domains)}. "

        pheromone_avg = statistics.mean(analysis.pheromone_signals.values()) if analysis.pheromone_signals else 0.0
        if pheromone_avg > 0.5:
            summary += "Feromônios indicam alta taxa de sucesso histórica. "
        elif pheromone_avg < -0.5:
            summary += "Feromônios indicam histórico de falhas. "

        return summary

    async def _update_pheromones(self, decision: StrategicDecision, success: bool) -> None:
        """Atualizar feromônios baseado no resultado da decisão"""
        try:
            pheromone_type = 'SUCCESS' if success else 'FAILURE'
            strength = 1.0 if success else -1.0

            for plan_id in decision.context.active_plans:
                await self.pheromone_client.publish_pheromone(
                    pheromone_type=pheromone_type,
                    domain=plan_id,
                    strength=strength,
                    metadata={
                        'decision_id': decision.decision_id,
                        'decision_type': decision.decision_type.value
                    }
                )

        except Exception as e:
            logger.error("update_pheromones_failed", error=str(e))

    async def execute_decision_action(self, decision: StrategicDecision) -> bool:
        """
        Executar a ação da decisão estratégica no ReplanningCoordinator

        Mapeia DecisionAction.action para métodos do coordinator e emite métricas
        """
        try:
            action = decision.decision.action
            target_entities = decision.decision.target_entities
            parameters = decision.decision.parameters

            logger.info(
                "executing_decision_action",
                decision_id=decision.decision_id,
                action=action,
                target_entities=target_entities
            )

            success = False

            if action == 'trigger_replanning':
                # Disparar replanning para cada entidade alvo
                reason = parameters.get('reason', 'strategic_decision')
                for entity_id in target_entities:
                    entity_success = await self.replanning_coordinator.trigger_replanning(
                        plan_id=entity_id,
                        reason=reason,
                        decision_id=decision.decision_id
                    )
                    success = success or entity_success

            elif action == 'adjust_qos':
                # Ajustar QoS para cada workflow alvo
                from ..models import QoSAdjustment, AdjustmentType
                for entity_id in target_entities:
                    adjustment = QoSAdjustment(
                        adjustment_type=AdjustmentType.INCREASE_PRIORITY,
                        target_workflow_id=entity_id,
                        parameters=parameters,
                        decision_id=decision.decision_id
                    )
                    entity_success = await self.replanning_coordinator.adjust_qos(adjustment)
                    success = success or entity_success

            elif action == 'pause_execution':
                # Pausar execução de workflows
                reason = parameters.get('reason', 'strategic_decision')
                for entity_id in target_entities:
                    entity_success = await self.replanning_coordinator.pause_execution(
                        workflow_id=entity_id,
                        reason=reason
                    )
                    success = success or entity_success

            elif action == 'resume_execution':
                # Retomar execução pausada
                for entity_id in target_entities:
                    entity_success = await self.replanning_coordinator.resume_execution(
                        workflow_id=entity_id
                    )
                    success = success or entity_success

            elif action == 'reallocate_resources':
                # Realocação de recursos - delega para Orchestrator via QoS adjustment
                from ..models import QoSAdjustment, AdjustmentType
                for entity_id in target_entities:
                    adjustment = QoSAdjustment(
                        adjustment_type=AdjustmentType.RESOURCE_REALLOCATION,
                        target_workflow_id=entity_id,
                        parameters=parameters,
                        decision_id=decision.decision_id
                    )
                    entity_success = await self.replanning_coordinator.adjust_qos(adjustment)
                    success = success or entity_success

            elif action in ['adjust_priorities', 'resolve_conflict']:
                # Ações que não requerem execução imediata via coordinator
                # Estas decisões são consumidas downstream por outros serviços
                logger.info(
                    "action_delegated_to_downstream",
                    action=action,
                    decision_id=decision.decision_id
                )
                success = True

            else:
                logger.warning(
                    "unknown_decision_action",
                    action=action,
                    decision_id=decision.decision_id
                )
                success = False

            # Emitir métricas
            from prometheus_client import Counter
            action_metric = Counter(
                'queen_decision_actions_total',
                'Total de ações de decisões estratégicas executadas',
                ['action', 'success']
            )
            action_metric.labels(action=action, success=str(success)).inc()

            if success:
                logger.info(
                    "decision_action_executed_successfully",
                    decision_id=decision.decision_id,
                    action=action
                )
            else:
                logger.error(
                    "decision_action_execution_failed",
                    decision_id=decision.decision_id,
                    action=action
                )

            return success

        except Exception as e:
            logger.error(
                "execute_decision_action_failed",
                decision_id=decision.decision_id,
                action=decision.decision.action,
                error=str(e)
            )
            return False
