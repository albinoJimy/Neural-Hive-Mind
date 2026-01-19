"""
Semantic Translation Orchestrator - Coordinates Fluxo B (B1-B6)

Main orchestrator that coordinates all steps of plan generation.
"""

import time
import structlog
from datetime import datetime, timedelta
from typing import Dict, List

from neural_hive_observability import get_tracer
from src.services.semantic_parser import SemanticParser
from src.services.dag_generator import DAGGenerator
from src.services.risk_scorer import RiskScorer
from src.services.explainability_generator import ExplainabilityGenerator
from src.clients.mongodb_client import MongoDBClient
from src.clients.neo4j_client import Neo4jClient
from src.producers.plan_producer import KafkaPlanProducer
from src.producers.approval_producer import KafkaApprovalProducer
from src.models.cognitive_plan import CognitivePlan, PlanStatus, ApprovalStatus, RiskBand

logger = structlog.get_logger()


class SemanticTranslationOrchestrator:
    """Main orchestrator for Semantic Translation (Fluxo B)"""

    def __init__(
        self,
        semantic_parser: SemanticParser,
        dag_generator: DAGGenerator,
        risk_scorer: RiskScorer,
        explainability_generator: ExplainabilityGenerator,
        mongodb_client: MongoDBClient,
        neo4j_client: Neo4jClient,
        plan_producer: KafkaPlanProducer,
        approval_producer: KafkaApprovalProducer,
        metrics
    ):
        self.parser = semantic_parser
        self.dag_gen = dag_generator
        self.risk_scorer = risk_scorer
        self.explainability = explainability_generator
        self.mongodb = mongodb_client
        self.neo4j = neo4j_client
        self.producer = plan_producer
        self.approval_producer = approval_producer
        self.metrics = metrics

    async def process_intent(
        self,
        intent_envelope: Dict,
        trace_context: Dict
    ):
        """
        Process Intent Envelope and generate Cognitive Plan (Fluxo B complete)

        Args:
            intent_envelope: Intent Envelope dict
            trace_context: OpenTelemetry trace context
        """
        start_time = time.time()
        intent_id = intent_envelope.get('id')
        intent = intent_envelope.get('intent', {})
        domain = intent.get('domain')
        tracer = get_tracer()

        # Log de debug para rastrear propagação do correlation_id
        # Buscar correlation_id em ambos os formatos (camelCase do Gateway e snake_case legado)
        envelope_correlation_id = intent_envelope.get('correlationId') or intent_envelope.get('correlation_id')
        envelope_format = (
            'camelCase' if intent_envelope.get('correlationId')
            else ('snake_case' if intent_envelope.get('correlation_id') else 'none')
        )
        trace_correlation_id = trace_context.get('correlation_id')
        logger.debug(
            'Rastreamento de correlation_id',
            intent_id=intent_id,
            correlation_id_envelope=envelope_correlation_id,
            correlation_id_trace_context=trace_correlation_id,
            correlation_id_selecionado=trace_correlation_id or envelope_correlation_id,
            origem='trace_context' if trace_correlation_id else 'intent_envelope',
            envelope_format=envelope_format
        )

        try:
            # B1: Validate Intent Envelope
            self._validate_intent_envelope(intent_envelope)

            # B2: Enrich context (Semantic Parser)
            logger.info('B2: Enriquecendo contexto', intent_id=intent_id)
            with tracer.start_as_current_span("semantic_parsing") as span:
                span.set_attribute("neural.hive.intent_id", intent_id)
                intermediate_repr = await self.parser.parse(intent_envelope)

            # B3: Decompose into DAG
            logger.info('B3: Gerando DAG de tarefas', intent_id=intent_id)
            with tracer.start_as_current_span("dag_generation") as span:
                span.set_attribute("neural.hive.plan_id", intent_envelope.get('plan_id'))
                tasks, execution_order = self.dag_gen.generate(intermediate_repr)
                span.set_attribute("neural.hive.dag_node_count", len(tasks))

            # B4: Evaluate risk (multi-domain com deteccao destrutiva)
            logger.info('B4: Avaliando risco multi-dominio', intent_id=intent_id)
            with tracer.start_as_current_span("risk_scoring_multi_domain") as span:
                # Call multi-domain risk scorer (returns 5-tuple)
                # risk_matrix contains only numeric scores (map<string, double> compatible)
                # destructive_analysis contains destructive operation details
                risk_score, risk_band, risk_factors, risk_matrix, destructive_analysis = self.risk_scorer.score_multi_domain(
                    intermediate_repr,
                    tasks
                )

                # Extract destructive analysis from separate return value
                is_destructive = destructive_analysis.get('is_destructive', False)
                destructive_tasks = destructive_analysis.get('destructive_tasks', [])
                destructive_severity = destructive_analysis.get('destructive_severity', 'low')

                span.set_attribute("neural.hive.risk_score", risk_score)
                span.set_attribute("neural.hive.risk_band", risk_band.value)
                span.set_attribute("neural.hive.is_destructive", is_destructive)
                span.set_attribute("neural.hive.destructive_severity", destructive_severity)

            # Determinar se plano requer aprovacao
            requires_approval = (
                risk_score >= 0.7 or
                is_destructive or
                risk_band in [RiskBand.HIGH, RiskBand.CRITICAL]
            )

            if requires_approval:
                logger.warning(
                    'Plano requer aprovacao - criterios atingidos',
                    intent_id=intent_id,
                    approval_criteria={
                        'risk_score_threshold': risk_score >= 0.7,
                        'is_destructive': is_destructive,
                        'risk_band_critical': risk_band in [RiskBand.HIGH, RiskBand.CRITICAL]
                    },
                    risk_score=risk_score,
                    risk_band=risk_band.value,
                    is_destructive=is_destructive,
                    destructive_severity=destructive_severity,
                    destructive_tasks=destructive_tasks
                )

            # Generate explainability
            explainability_token, reasoning_summary = self.explainability.generate(
                intermediate_repr,
                tasks,
                risk_factors
            )

            # B5: Version and register plan
            logger.info('B5: Versionando plano', intent_id=intent_id)
            cognitive_plan = self._create_cognitive_plan(
                intent_envelope,
                tasks,
                execution_order,
                risk_score,
                risk_band,
                risk_factors,
                explainability_token,
                reasoning_summary,
                intermediate_repr,
                trace_context,
                requires_approval=requires_approval,
                is_destructive=is_destructive,
                destructive_tasks=destructive_tasks,
                risk_matrix=risk_matrix
            )

            # Register in immutable ledger
            ledger_hash = await self.mongodb.append_to_ledger(cognitive_plan)
            logger.info(
                'Plano registrado no ledger com status de aprovacao',
                plan_id=cognitive_plan.plan_id,
                ledger_hash=ledger_hash,
                requires_approval=cognitive_plan.requires_approval,
                approval_status=cognitive_plan.approval_status.value if cognitive_plan.approval_status else None
            )

            # B6: Publish plan (conditional routing based on approval requirement)
            if cognitive_plan.requires_approval:
                logger.warning(
                    'Plano bloqueado aguardando aprovacao humana',
                    plan_id=cognitive_plan.plan_id,
                    intent_id=intent_id,
                    risk_score=risk_score,
                    risk_band=risk_band.value,
                    is_destructive=is_destructive,
                    destructive_severity=destructive_severity,
                    destructive_task_count=len(destructive_tasks)
                )

                # Record approval blocking metric
                self.metrics.record_plan_blocked_for_approval(
                    risk_band=risk_band.value,
                    is_destructive=is_destructive,
                    channel=domain or 'unknown'
                )

                # Publish to approval topic
                await self.approval_producer.send_approval_request(cognitive_plan)

                logger.info(
                    'Plano publicado no topico de aprovacao',
                    plan_id=cognitive_plan.plan_id,
                    topic=self.approval_producer.settings.kafka_approval_topic
                )
            else:
                # Normal flow: publish to execution topic
                logger.info('B6: Publicando plano para execucao', plan_id=cognitive_plan.plan_id)
                await self.producer.send_plan(cognitive_plan)

            # Persistir intent no grafo de conhecimento Neo4j (não bloqueia fluxo principal)
            try:
                neo4j_success = await self.neo4j.persist_intent_to_graph(
                    intent_envelope,
                    cognitive_plan.plan_id,
                    'success'
                )
                if neo4j_success:
                    logger.info(
                        'Intent persistido no grafo de conhecimento',
                        intent_id=intent_id,
                        plan_id=cognitive_plan.plan_id
                    )
            except Exception as neo4j_error:
                # Não propagar exceção - persistência Neo4j é opcional
                logger.warning(
                    'Falha ao persistir intent no Neo4j',
                    intent_id=intent_id,
                    error=str(neo4j_error)
                )

            # Record metrics with approval status
            duration = time.time() - start_time
            self.metrics.observe_geracao_duration(
                duration,
                channel=domain or 'unknown',
                trace_id=trace_context.get('trace_id'),
                span_id=trace_context.get('span_id')
            )
            plan_status = 'blocked_for_approval' if cognitive_plan.requires_approval else 'success'
            self.metrics.increment_plans(channel=domain or 'unknown', status=plan_status)

            logger.info(
                'Plano gerado com sucesso',
                intent_id=intent_id,
                plan_id=cognitive_plan.plan_id,
                num_tasks=len(tasks),
                risk_band=risk_band.value,
                duration_ms=duration * 1000
            )

        except Exception as e:
            # Record error metrics
            duration = time.time() - start_time
            self.metrics.observe_geracao_duration(duration, channel=domain or 'unknown')
            self.metrics.increment_plans(channel=domain or 'unknown', status='error')

            # Persistir intent com outcome='error' no Neo4j (para análise de falhas)
            try:
                await self.neo4j.persist_intent_to_graph(
                    intent_envelope,
                    'N/A',
                    'error'
                )
            except Exception as neo4j_error:
                logger.warning(
                    'Falha ao persistir intent com erro no Neo4j',
                    intent_id=intent_id,
                    error=str(neo4j_error)
                )

            import traceback
            logger.error(
                'Erro gerando plano',
                intent_id=intent_id,
                error=str(e),
                duration_ms=duration * 1000,
                traceback=traceback.format_exc()
            )
            raise

    def _validate_intent_envelope(self, intent_envelope: Dict):
        """Validate Intent Envelope (B1)"""
        if not intent_envelope.get('id'):
            raise ValueError('Intent ID ausente')

        confidence = intent_envelope.get('confidence', 0)
        if confidence < 0.5:
            logger.warning(
                'Confiança muito baixa',
                intent_id=intent_envelope.get('id'),
                confidence=confidence
            )

    def _create_cognitive_plan(
        self,
        intent_envelope: Dict,
        tasks,
        execution_order,
        risk_score,
        risk_band,
        risk_factors,
        explainability_token,
        reasoning_summary,
        intermediate_repr,
        trace_context: Dict,
        requires_approval: bool = False,
        is_destructive: bool = False,
        destructive_tasks: List[str] = None,
        risk_matrix: Dict = None
    ) -> CognitivePlan:
        """Create CognitivePlan from components with approval and destructive analysis fields"""
        if destructive_tasks is None:
            destructive_tasks = []
        # Calculate total duration
        total_duration = sum(task.estimated_duration_ms or 0 for task in tasks)

        # Calculate complexity score
        complexity_score = len(tasks) / 10.0

        # Determine plan validity (24h default)
        valid_until = datetime.utcnow() + timedelta(hours=24)

        constraints = intent_envelope.get('constraints') or {}
        intent = intent_envelope.get('intent') or {}

        # Extrair correlation_id prioritariamente do trace_context (headers Kafka)
        # com fallback para intent_envelope em ambos formatos (camelCase e snake_case)
        correlation_id = (
            trace_context.get('correlation_id') or
            intent_envelope.get('correlationId') or
            intent_envelope.get('correlation_id')
        )
        # Determinar origem do correlation_id para logs
        if trace_context.get('correlation_id'):
            correlation_id_origem = 'trace_context'
            formato_envelope = None
        elif intent_envelope.get('correlationId'):
            correlation_id_origem = 'intent_envelope_camelCase'
            formato_envelope = 'camelCase'
        elif intent_envelope.get('correlation_id'):
            correlation_id_origem = 'intent_envelope_snake_case'
            formato_envelope = 'snake_case'
        else:
            correlation_id_origem = 'none'
            formato_envelope = None

        logger.debug(
            'correlation_id selecionado para CognitivePlan',
            correlation_id=correlation_id,
            origem=correlation_id_origem,
            formato_envelope=formato_envelope,
            intent_id=intent_envelope.get('id')
        )

        return CognitivePlan(
            intent_id=intent_envelope.get('id'),
            correlation_id=correlation_id,
            trace_id=trace_context.get('trace_id') or intent_envelope.get('trace_id'),
            span_id=trace_context.get('span_id') or intent_envelope.get('span_id'),
            tasks=tasks,
            execution_order=execution_order,
            risk_score=risk_score,
            risk_band=risk_band,
            risk_factors=risk_factors,
            explainability_token=explainability_token,
            reasoning_summary=reasoning_summary,
            status=PlanStatus.VALIDATED,
            valid_until=valid_until,
            estimated_total_duration_ms=total_duration,
            complexity_score=complexity_score,
            original_domain=intent.get('domain', 'unknown'),
            original_priority=constraints.get('priority', 'normal'),
            original_security_level=constraints.get('security_level', 'internal'),
            metadata={
                'original_confidence': intent_envelope.get('confidence'),
                'num_similar_intents': len(
                    ((intermediate_repr or {}).get('historical_context') or {}).get('similar_intents', [])
                ),
                'generator_version': '1.0.0'
            },
            # Approval workflow fields
            requires_approval=requires_approval,
            approval_status=ApprovalStatus.PENDING if requires_approval else None,
            # Destructive operation analysis fields
            is_destructive=is_destructive,
            destructive_tasks=destructive_tasks,
            risk_matrix=risk_matrix
        )
