"""
Semantic Translation Orchestrator - Coordinates Fluxo B (B1-B6)

Main orchestrator that coordinates all steps of plan generation.
"""

import time
import structlog
from datetime import datetime, timedelta
from typing import Dict

from src.services.semantic_parser import SemanticParser
from src.services.dag_generator import DAGGenerator
from src.services.risk_scorer import RiskScorer
from src.services.explainability_generator import ExplainabilityGenerator
from src.clients.mongodb_client import MongoDBClient
from src.clients.neo4j_client import Neo4jClient
from src.producers.plan_producer import KafkaPlanProducer
from src.models.cognitive_plan import CognitivePlan, PlanStatus

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
        metrics
    ):
        self.parser = semantic_parser
        self.dag_gen = dag_generator
        self.risk_scorer = risk_scorer
        self.explainability = explainability_generator
        self.mongodb = mongodb_client
        self.neo4j = neo4j_client
        self.producer = plan_producer
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
            intermediate_repr = await self.parser.parse(intent_envelope)

            # B3: Decompose into DAG
            logger.info('B3: Gerando DAG de tarefas', intent_id=intent_id)
            tasks, execution_order = self.dag_gen.generate(intermediate_repr)

            # B4: Evaluate risk
            logger.info('B4: Avaliando risco', intent_id=intent_id)
            risk_score, risk_band, risk_factors = self.risk_scorer.score(
                intermediate_repr,
                tasks
            )

            # Check if requires human review
            if risk_score >= 0.95:
                logger.warning(
                    'Plano requer revisão humana',
                    intent_id=intent_id,
                    risk_score=risk_score
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
                trace_context
            )

            # Register in immutable ledger
            ledger_hash = await self.mongodb.append_to_ledger(cognitive_plan)
            logger.info(
                'Plano registrado no ledger',
                plan_id=cognitive_plan.plan_id,
                hash=ledger_hash
            )

            # B6: Publish plan to Kafka
            logger.info('B6: Publicando plano', plan_id=cognitive_plan.plan_id)
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

            # Record success metrics
            duration = time.time() - start_time
            self.metrics.observe_geracao_duration(
                duration,
                channel=domain or 'unknown',
                trace_id=trace_context.get('trace_id'),
                span_id=trace_context.get('span_id')
            )
            self.metrics.increment_plans(channel=domain or 'unknown', status='success')

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
        trace_context: Dict
    ) -> CognitivePlan:
        """Create CognitivePlan from components"""
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
            }
        )
