import structlog
from typing import Dict, Any, List, Optional, TYPE_CHECKING
from datetime import datetime, timedelta
import statistics

from neural_hive_resilience.circuit_breaker import CircuitBreakerError
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
    from ..clients import OPAClient, OrchestratorClient


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
        opa_client: Optional['OPAClient'],
        orchestrator_client: Optional['OrchestratorClient'],
        settings: Settings
    ):
        self.mongodb_client = mongodb_client
        self.redis_client = redis_client
        self.neo4j_client = neo4j_client
        self.prometheus_client = prometheus_client
        self.pheromone_client = pheromone_client
        self.replanning_coordinator = replanning_coordinator
        self.opa_client = opa_client
        self.orchestrator_client = orchestrator_client
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

            # 5. Gerar reasoning summary (antes da validação para incluir no input OPA)
            reasoning_summary = self._generate_reasoning_summary(
                event_type, decision_type, confidence_score, risk_assessment, analysis
            )

            # 6. Validar guardrails via OPA
            guardrails_validated = await self._validate_guardrails(
                decision_type, action, risk_assessment, confidence_score, context, analysis, reasoning_summary
            )

            # 6.1 Guard: Se guardrails não validados (lista vazia), rejeitar decisão
            if not guardrails_validated:
                logger.warning(
                    "decision_rejected_guardrails_not_validated",
                    event_type=event_type,
                    source_id=source_id,
                    decision_type=decision_type.value,
                    reason="OPA denied or fail-closed policy"
                )
                return None

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
            try:
                await self.mongodb_client.save_strategic_decision(decision)
            except CircuitBreakerError:
                logger.warning(
                    "strategic_decision_persist_circuit_open",
                    decision_id=decision.decision_id
                )
                return None

            # 9. Registrar no Neo4j
            try:
                await self.neo4j_client.record_strategic_decision(decision)
            except CircuitBreakerError:
                logger.warning(
                    "neo4j_circuit_open_record_decision",
                    decision_id=decision.decision_id
                )
                return None

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
            # Buscar planos ativos do Neo4j
            active_plans = await self._get_active_plans(trigger)

            # Buscar incidentes críticos do MongoDB
            critical_incidents = await self._get_critical_incidents()

            # Buscar violações de SLA do Prometheus
            sla_violations = await self._get_sla_violations()

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

    async def _get_active_plans(self, trigger: Dict[str, Any]) -> List[str]:
        """
        Buscar planos ativos do Neo4j ou trigger

        Returns:
            Lista de plan_ids ativos
        """
        try:
            # Primeiro, tentar obter do trigger (se disponível)
            trigger_plans = trigger.get('decision_data', {}).get('plan_id', [])
            if isinstance(trigger_plans, str):
                trigger_plans = [trigger_plans]

            if trigger_plans:
                logger.debug("active_plans_from_trigger", count=len(trigger_plans))
                return trigger_plans

            # Caso contrário, buscar do Neo4j
            async with self.neo4j_client.driver.session(
                database=self.neo4j_client.settings.NEO4J_DATABASE
            ) as session:
                query = """
                MATCH (p:CognitivePlan)
                WHERE p.status = 'ACTIVE' OR p.status = 'IN_PROGRESS'
                RETURN p.plan_id as plan_id
                ORDER BY p.created_at DESC
                LIMIT 50
                """

                result = await session.run(query)
                records = await result.data()

                active_plans = [record['plan_id'] for record in records if 'plan_id' in record]

                logger.debug("active_plans_from_neo4j", count=len(active_plans))
                return active_plans

        except Exception as e:
            logger.error("get_active_plans_failed", error=str(e))
            return []

    async def _get_critical_incidents(self) -> List[str]:
        """
        Buscar incidentes críticos do MongoDB

        Returns:
            Lista de incident_ids críticos
        """
        try:
            # Query MongoDB para incidentes críticos não resolvidos
            incidents = await self.mongodb_client.db.incidents.find({
                'severity': {'$in': ['CRITICAL', 'HIGH']},
                'resolved': False
            }).to_list(length=20)

            incident_ids = [str(inc['_id']) for inc in incidents]

            logger.debug("critical_incidents_found", count=len(incident_ids))
            return incident_ids

        except Exception as e:
            logger.error("get_critical_incidents_failed", error=str(e))
            return []

    async def _get_sla_violations(self) -> List[str]:
        """
        Buscar violações de SLA do Prometheus

        Returns:
            Lista de serviços com violações de SLA
        """
        try:
            # Query PromQL para serviços com SLA < 95%
            query = '''
            (
              sum by (service) (rate(http_requests_total{status=~"2.."}[5m])) /
              sum by (service) (rate(http_requests_total[5m]))
            ) < 0.95
            '''

            result = await self.prometheus_client.query(query)

            violations = []
            if result.get('status') == 'success' and result.get('data', {}).get('result'):
                for item in result['data']['result']:
                    service = item.get('metric', {}).get('service')
                    if service:
                        violations.append(service)

            logger.debug("sla_violations_found", count=len(violations))
            return violations

        except Exception as e:
            logger.error("get_sla_violations_failed", error=str(e))
            return []

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

            # Historical success rate - calcular de decisões anteriores
            historical_success_rate = await self._get_historical_success_rate()

            confidence = (
                context_completeness * 0.3 +
                pheromone_strength * 0.3 +
                historical_success_rate * 0.4
            )

            return min(1.0, max(0.0, confidence))

        except Exception as e:
            logger.error("calculate_confidence_failed", error=str(e))
            return 0.5

    async def _get_historical_success_rate(self) -> float:
        """
        Calcular taxa de sucesso histórica de decisões estratégicas

        Busca decisões dos últimos 7 dias e calcula taxa de sucesso

        Returns:
            Taxa de sucesso (0.0 a 1.0)
        """
        try:
            # Calcular timestamp de 7 dias atrás
            cutoff_timestamp = int((datetime.now() - timedelta(days=7)).timestamp() * 1000)

            # Query MongoDB para decisões recentes
            pipeline = [
                {
                    '$match': {
                        'created_at': {'$gte': cutoff_timestamp}
                    }
                },
                {
                    '$group': {
                        '_id': None,
                        'total': {'$sum': 1},
                        'successful': {
                            '$sum': {
                                '$cond': [
                                    {'$gte': ['$confidence_score', 0.7]},
                                    1,
                                    0
                                ]
                            }
                        }
                    }
                }
            ]

            cursor = self.mongodb_client.db.strategic_decisions.aggregate(pipeline)
            results = await cursor.to_list(length=1)

            if results and results[0]['total'] > 0:
                success_rate = results[0]['successful'] / results[0]['total']
                logger.debug(
                    "historical_success_rate_calculated",
                    rate=success_rate,
                    total=results[0]['total'],
                    successful=results[0]['successful']
                )
                return success_rate

            # Fallback: buscar do Neo4j se MongoDB não tem dados
            success_rate = await self._get_success_rate_from_neo4j()
            if success_rate is not None:
                return success_rate

            # Se não há dados históricos, assumir taxa moderada
            logger.warning("historical_success_rate_no_data_available")
            return 0.75

        except Exception as e:
            logger.error("get_historical_success_rate_failed", error=str(e))
            return 0.75

    async def _get_success_rate_from_neo4j(self) -> Optional[float]:
        """
        Buscar taxa de sucesso do Neo4j como fallback

        Returns:
            Taxa de sucesso ou None se não disponível
        """
        try:
            async with self.neo4j_client.driver.session(
                database=self.neo4j_client.settings.NEO4J_DATABASE
            ) as session:
                query = """
                MATCH (d:StrategicDecision)
                WHERE d.created_at > timestamp() - (7 * 24 * 60 * 60 * 1000)
                RETURN
                    count(d) as total,
                    sum(CASE WHEN d.confidence_score >= 0.7 THEN 1 ELSE 0 END) as successful
                """

                result = await session.run(query)
                record = await result.single()

                if record and record['total'] > 0:
                    success_rate = record['successful'] / record['total']
                    logger.debug("success_rate_from_neo4j", rate=success_rate)
                    return success_rate

            return None

        except Exception as e:
            logger.warning("get_success_rate_from_neo4j_failed", error=str(e))
            return None

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
        risk_assessment: RiskAssessment,
        confidence_score: float,
        context: DecisionContext,
        analysis: DecisionAnalysis,
        reasoning_summary: str
    ) -> List[str]:
        """
        Validar decisão contra guardrails éticos via OPA policies

        Args:
            decision_type: Tipo de decisão
            action: Ação a ser tomada
            risk_assessment: Avaliação de risco
            confidence_score: Score de confiança
            context: Contexto da decisão
            analysis: Análise realizada
            reasoning_summary: Resumo do raciocínio

        Returns:
            Lista de guardrails validados
        """
        from ..observability.metrics import QueenAgentMetrics

        # Se OPA não estiver disponível, verificar configuração fail-closed
        if not self.opa_client or not self.opa_client.is_connected():
            if self.settings.OPA_FAIL_OPEN:
                # Fail-open: usar validação básica como fallback
                logger.warning("opa_client_not_available_fail_open_using_basic_validation")
                return self._basic_guardrail_validation(decision_type, risk_assessment)
            else:
                # Fail-closed: rejeitar decisão retornando lista vazia
                logger.error("opa_client_not_available_fail_closed_rejecting_decision")
                return []

        try:
            # Preparar input para OPA
            opa_input = {
                "decision": {
                    "decision_type": decision_type.value,
                    "confidence_score": confidence_score,
                    "risk_assessment": {
                        "risk_score": risk_assessment.risk_score,
                        "risk_factors": risk_assessment.risk_factors,
                        "mitigations": risk_assessment.mitigations
                    },
                    "decision": {
                        "action": action.action,
                        "target_entities": action.target_entities,
                        "parameters": action.parameters,
                        "rationale": action.rationale
                    },
                    "context": {
                        "active_plans": context.active_plans,
                        "critical_incidents": context.critical_incidents,
                        "sla_violations": context.sla_violations,
                        "resource_saturation": context.resource_saturation
                    },
                    "analysis": {
                        "metrics_snapshot": analysis.metrics_snapshot,
                        "conflict_domains": analysis.conflict_domains
                    },
                    "reasoning_summary": reasoning_summary
                }
            }

            logger.debug(
                "validating_guardrails_with_opa",
                policy_path="neuralhive/queen/ethical_guardrails"
            )

            # Chamar OPA policy
            opa_result = await self.opa_client.evaluate_policy(
                policy_path="neuralhive/queen/ethical_guardrails",
                input_data=opa_input
            )

            # Processar resultado OPA
            allowed = opa_result.get("allow", False)
            violations = opa_result.get("violations", [])
            warnings = opa_result.get("warnings", [])
            guardrails_validated = opa_result.get("guardrails_validated", [])

            # Log violations e warnings
            if violations:
                logger.warning(
                    "opa_guardrail_violations_detected",
                    violations_count=len(violations),
                    violations=[v.get("rule") for v in violations]
                )

                # Incrementar métrica de denials
                for violation in violations:
                    QueenAgentMetrics.opa_denials_total.labels(
                        policy=violation.get("policy", "unknown"),
                        rule=violation.get("rule", "unknown"),
                        severity=violation.get("severity", "unknown")
                    ).inc()

            if warnings:
                logger.info(
                    "opa_guardrail_warnings",
                    warnings_count=len(warnings),
                    warnings=[w.get("rule") for w in warnings]
                )

                # Incrementar métrica de warnings
                for warning in warnings:
                    QueenAgentMetrics.opa_warnings_total.labels(
                        policy=warning.get("policy", "unknown"),
                        rule=warning.get("rule", "unknown")
                    ).inc()

            # Se não permitido, retornar lista vazia (falha na validação)
            if not allowed:
                logger.error(
                    "decision_rejected_by_opa_guardrails",
                    violations=violations
                )
                QueenAgentMetrics.opa_evaluations_total.labels(
                    policy="ethical_guardrails",
                    result="denied"
                ).inc()
                return []

            # Incrementar métrica de policy hits
            QueenAgentMetrics.opa_evaluations_total.labels(
                policy="ethical_guardrails",
                result="allowed"
            ).inc()

            logger.info(
                "guardrails_validated_successfully",
                guardrails_count=len(guardrails_validated)
            )

            return guardrails_validated

        except Exception as e:
            logger.error("opa_guardrail_validation_failed", error=str(e))

            # Fail open ou fail closed baseado em configuração
            if self.settings.OPA_FAIL_OPEN:
                logger.warning("opa_validation_failed_fail_open")
                return self._basic_guardrail_validation(decision_type, risk_assessment)
            else:
                logger.error("opa_validation_failed_fail_closed")
                return []

    def _basic_guardrail_validation(
        self,
        decision_type: DecisionType,
        risk_assessment: RiskAssessment
    ) -> List[str]:
        """
        Validação básica de guardrails (fallback quando OPA não disponível)

        Args:
            decision_type: Tipo de decisão
            risk_assessment: Avaliação de risco

        Returns:
            Lista de guardrails validados
        """
        guardrails = []

        # Guardrail básico: risk score aceitável
        if risk_assessment.risk_score < 0.9:
            guardrails.append('risk_threshold_acceptable')

        # Guardrail básico: não é exception approval
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

            # Invalidar cache de trilhas de sucesso quando publicar SUCCESS
            if success:
                self.pheromone_client.invalidate_success_trails_cache()

        except Exception as e:
            logger.error("update_pheromones_failed", error=str(e))

    async def execute_decision_action(self, decision: StrategicDecision) -> bool:
        """
        Executar a ação da decisão estratégica via Orchestrator gRPC ou ReplanningCoordinator.

        Mapeia DecisionAction.action para métodos do OrchestratorClient (gRPC)
        ou ReplanningCoordinator (fallback) e emite métricas.
        """
        try:
            action = decision.decision.action
            target_entities = decision.decision.target_entities
            parameters = decision.decision.parameters

            logger.info(
                "executing_decision_action",
                decision_id=decision.decision_id,
                action=action,
                target_entities=target_entities,
                orchestrator_client_available=self.orchestrator_client is not None
            )

            success = False

            if action == 'trigger_replanning':
                # Disparar replanning via Orchestrator gRPC
                reason = parameters.get('reason', 'strategic_decision')
                trigger_type = parameters.get('trigger_type', 'STRATEGIC')

                if self.orchestrator_client:
                    for entity_id in target_entities:
                        replanning_id = await self.orchestrator_client.trigger_replanning(
                            plan_id=entity_id,
                            reason=f"{reason} - Decision: {decision.decision_id}",
                            trigger_type=trigger_type,
                            context={'decision_id': decision.decision_id},
                            preserve_progress=parameters.get('preserve_progress', True),
                            priority=parameters.get('priority', 5)
                        )
                        entity_success = replanning_id is not None
                        success = success or entity_success

                        logger.info(
                            "replanning_triggered_via_grpc",
                            plan_id=entity_id,
                            replanning_id=replanning_id
                        )
                else:
                    # Fallback para ReplanningCoordinator
                    for entity_id in target_entities:
                        entity_success = await self.replanning_coordinator.trigger_replanning(
                            plan_id=entity_id,
                            reason=reason,
                            decision_id=decision.decision_id
                        )
                        success = success or entity_success

            elif action == 'adjust_qos' or action == 'adjust_priorities':
                # Ajustar prioridades via Orchestrator gRPC
                new_priority = parameters.get('priority', parameters.get('new_priority', 7))

                if self.orchestrator_client:
                    for entity_id in target_entities:
                        entity_success = await self.orchestrator_client.adjust_priorities(
                            workflow_id=entity_id,
                            plan_id=parameters.get('plan_id', ''),
                            new_priority=new_priority,
                            reason=f"Strategic decision: {decision.decision_id}"
                        )
                        success = success or entity_success

                        logger.info(
                            "priority_adjusted_via_grpc",
                            workflow_id=entity_id,
                            new_priority=new_priority
                        )
                else:
                    # Fallback para ReplanningCoordinator
                    from ..models import QoSAdjustment, AdjustmentType
                    for entity_id in target_entities:
                        adjustment = QoSAdjustment(
                            adjustment_type=AdjustmentType.INCREASE_PRIORITY,
                            target_workflow_id=entity_id,
                            parameters=parameters,
                            reason=f"Strategic decision: {decision.decision_id}"
                        )
                        entity_success = await self.replanning_coordinator.adjust_qos(adjustment)
                        success = success or entity_success

            elif action == 'pause_execution':
                # Pausar execução via Orchestrator gRPC
                reason = parameters.get('reason', 'strategic_decision')
                duration_seconds = parameters.get('duration_seconds')

                if self.orchestrator_client:
                    for entity_id in target_entities:
                        entity_success = await self.orchestrator_client.pause_workflow(
                            workflow_id=entity_id,
                            reason=f"{reason} - Decision: {decision.decision_id}",
                            duration_seconds=duration_seconds
                        )
                        success = success or entity_success

                        logger.info(
                            "workflow_paused_via_grpc",
                            workflow_id=entity_id
                        )
                else:
                    for entity_id in target_entities:
                        entity_success = await self.replanning_coordinator.pause_execution(
                            workflow_id=entity_id,
                            reason=reason
                        )
                        success = success or entity_success

            elif action == 'resume_execution':
                # Retomar execução via Orchestrator gRPC
                if self.orchestrator_client:
                    for entity_id in target_entities:
                        entity_success = await self.orchestrator_client.resume_workflow(
                            workflow_id=entity_id,
                            reason=f"Strategic decision: {decision.decision_id}"
                        )
                        success = success or entity_success

                        logger.info(
                            "workflow_resumed_via_grpc",
                            workflow_id=entity_id
                        )
                else:
                    for entity_id in target_entities:
                        entity_success = await self.replanning_coordinator.resume_execution(
                            workflow_id=entity_id
                        )
                        success = success or entity_success

            elif action == 'reallocate_resources':
                # Realocação de recursos via Orchestrator gRPC
                if self.orchestrator_client:
                    target_allocation = {}
                    for entity_id in target_entities:
                        target_allocation[entity_id] = {
                            'cpu_millicores': parameters.get('cpu_millicores', 2000),
                            'memory_mb': parameters.get('memory_mb', 4096),
                            'max_parallel_tickets': parameters.get('max_parallel_tickets', 20),
                            'scheduling_priority': parameters.get('scheduling_priority', 8)
                        }

                    result = await self.orchestrator_client.rebalance_resources(
                        workflow_ids=target_entities,
                        target_allocation=target_allocation,
                        reason=f"Strategic decision: {decision.decision_id}",
                        force=parameters.get('force', False)
                    )
                    success = result.get('success', False)

                    logger.info(
                        "resources_rebalanced_via_grpc",
                        workflow_count=len(target_entities),
                        success=success
                    )
                else:
                    # Fallback para ReplanningCoordinator
                    from ..models import QoSAdjustment, AdjustmentType
                    for entity_id in target_entities:
                        adjustment = QoSAdjustment(
                            adjustment_type=AdjustmentType.ALLOCATE_MORE_RESOURCES,
                            target_workflow_id=entity_id,
                            parameters=parameters,
                            reason=f"Strategic decision: {decision.decision_id}"
                        )
                        entity_success = await self.replanning_coordinator.adjust_qos(adjustment)
                        success = success or entity_success

            elif action == 'resolve_conflict':
                # Resolução de conflito - delega para Orchestrator se disponível
                if self.orchestrator_client:
                    # Aumentar prioridade dos workflows afetados para resolver conflito
                    for entity_id in target_entities:
                        entity_success = await self.orchestrator_client.adjust_priorities(
                            workflow_id=entity_id,
                            plan_id='',
                            new_priority=parameters.get('conflict_resolution_priority', 9),
                            reason=f"Conflict resolution - Decision: {decision.decision_id}"
                        )
                        success = success or entity_success
                else:
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
            from ..observability.metrics import QueenAgentMetrics
            QueenAgentMetrics.decision_actions_total.labels(
                action=action,
                success=str(success)
            ).inc()

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
