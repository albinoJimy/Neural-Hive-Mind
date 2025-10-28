import asyncio
import uuid
from datetime import datetime
from typing import Dict, Any
import structlog

from ..models.execution_ticket import ExecutionTicket, TicketStatus
from ..models.pipeline_context import PipelineContext
from ..models.artifact import PipelineResult, PipelineStage, StageStatus
from ..clients.kafka_result_producer import KafkaResultProducer
from ..clients.execution_ticket_client import ExecutionTicketClient
from ..clients.postgres_client import PostgresClient
from ..clients.mongodb_client import MongoDBClient

logger = structlog.get_logger()


class PipelineEngine:
    """
    Orquestrador principal que coordena execução dos 6 subpipelines
    """

    def __init__(
        self,
        template_selector,
        code_composer,
        validator,
        test_runner,
        packager,
        approval_gate,
        kafka_producer: KafkaResultProducer,
        ticket_client: ExecutionTicketClient,
        postgres_client: PostgresClient,
        mongodb_client: MongoDBClient,
        max_concurrent: int = 3,
        pipeline_timeout: int = 3600,
        auto_approval_threshold: float = 0.9,
        min_quality_score: float = 0.5
    ):
        self.template_selector = template_selector
        self.code_composer = code_composer
        self.validator = validator
        self.test_runner = test_runner
        self.packager = packager
        self.approval_gate = approval_gate

        self.kafka_producer = kafka_producer
        self.ticket_client = ticket_client
        self.postgres_client = postgres_client
        self.mongodb_client = mongodb_client

        self.max_concurrent = max_concurrent
        self.pipeline_timeout = pipeline_timeout
        self.auto_approval_threshold = auto_approval_threshold
        self.min_quality_score = min_quality_score

        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._active_pipelines: Dict[str, PipelineContext] = {}

    async def execute_pipeline(self, ticket: ExecutionTicket) -> PipelineResult:
        """
        Executa pipeline completo para um Execution Ticket

        Args:
            ticket: Execution Ticket do tipo BUILD

        Returns:
            PipelineResult com status e artefatos gerados
        """
        async with self._semaphore:
            pipeline_id = str(uuid.uuid4())
            trace_id = ticket.trace_id or str(uuid.uuid4())
            span_id = ticket.span_id or str(uuid.uuid4())

            # Criar contexto do pipeline
            context = PipelineContext(
                pipeline_id=pipeline_id,
                ticket=ticket,
                trace_id=trace_id,
                span_id=span_id
            )

            self._active_pipelines[pipeline_id] = context

            try:
                logger.info(
                    'pipeline_started',
                    pipeline_id=pipeline_id,
                    ticket_id=ticket.ticket_id,
                    trace_id=trace_id
                )

                # Validar ticket
                if not ticket.is_build_task():
                    raise ValueError(f'Ticket não é do tipo BUILD: {ticket.task_type}')

                # Atualizar status do ticket para RUNNING
                await self.ticket_client.update_status(
                    ticket.ticket_id,
                    TicketStatus.RUNNING,
                    {'pipeline_id': pipeline_id}
                )

                # Executar 6 subpipelines sequencialmente
                await self._execute_stage(context, 'template_selection', self.template_selector.select)
                await self._execute_stage(context, 'code_composition', self.code_composer.compose)
                await self._execute_stage(context, 'validation', self.validator.validate)
                await self._execute_stage(context, 'testing', self.test_runner.run_tests)
                await self._execute_stage(context, 'packaging', self.packager.package)
                await self._execute_stage(context, 'approval_gate', self.approval_gate.check_approval)

                # Pipeline completado
                context.completed_at = datetime.now()

                # Converter para PipelineResult
                pipeline_result = context.to_pipeline_result(
                    self.auto_approval_threshold,
                    self.min_quality_score
                )

                # Persistir resultado
                await self.postgres_client.save_pipeline(pipeline_result)

                # Publicar resultado no Kafka
                await self.kafka_producer.publish_result(pipeline_result)

                # Atualizar status do ticket baseado no status do pipeline
                if pipeline_result.status == 'COMPLETED':
                    final_status = TicketStatus.COMPLETED
                elif pipeline_result.status in ('REQUIRES_REVIEW', 'PARTIAL'):
                    # Tickets que requerem revisão permanecem em RUNNING
                    final_status = TicketStatus.RUNNING
                else:
                    final_status = TicketStatus.FAILED

                await self.ticket_client.update_status(
                    ticket.ticket_id,
                    final_status,
                    {'pipeline_id': pipeline_id, 'status': pipeline_result.status}
                )

                logger.info(
                    'pipeline_completed',
                    pipeline_id=pipeline_id,
                    status=pipeline_result.status,
                    duration_ms=pipeline_result.total_duration_ms
                )

                return pipeline_result

            except Exception as e:
                logger.error(
                    'pipeline_failed',
                    pipeline_id=pipeline_id,
                    error=str(e),
                    exc_info=True
                )

                context.error = e
                context.completed_at = datetime.now()

                # Criar ticket de compensação
                try:
                    await self.ticket_client.create_compensation_ticket(
                        ticket.ticket_id,
                        f'Pipeline falhou: {str(e)}'
                    )
                except Exception as comp_error:
                    logger.error('compensation_ticket_failed', error=str(comp_error))

                # Atualizar status do ticket
                await self.ticket_client.update_status(
                    ticket.ticket_id,
                    TicketStatus.FAILED,
                    {'pipeline_id': pipeline_id, 'error': str(e)}
                )

                # Criar PipelineResult com erro
                pipeline_result = context.to_pipeline_result(
                    self.auto_approval_threshold,
                    self.min_quality_score
                )

                # Publicar resultado de falha
                await self.kafka_producer.publish_result(pipeline_result)

                return pipeline_result

            finally:
                # Remover do tracking de pipelines ativos
                self._active_pipelines.pop(pipeline_id, None)

    async def _execute_stage(self, context: PipelineContext, stage_name: str, stage_func):
        """
        Executa um stage do pipeline

        Args:
            context: Contexto do pipeline
            stage_name: Nome do stage
            stage_func: Função assíncrona do stage
        """
        stage = PipelineStage(
            stage_name=stage_name,
            status=StageStatus.RUNNING,
            started_at=datetime.now(),
            duration_ms=0
        )
        context.add_stage(stage)

        start_time = datetime.now()

        try:
            logger.info('stage_started', stage=stage_name, pipeline_id=context.pipeline_id)

            # Executar stage com timeout
            await asyncio.wait_for(
                stage_func(context),
                timeout=self.pipeline_timeout
            )

            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            context.mark_stage_completed(stage_name, duration_ms)

            logger.info('stage_completed', stage=stage_name, duration_ms=duration_ms)

        except asyncio.TimeoutError:
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            error_msg = f'Stage {stage_name} timeout após {self.pipeline_timeout}s'
            context.mark_stage_failed(stage_name, error_msg, duration_ms)
            logger.error('stage_timeout', stage=stage_name)
            raise

        except Exception as e:
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            context.mark_stage_failed(stage_name, str(e), duration_ms)
            logger.error('stage_failed', stage=stage_name, error=str(e))
            raise

    def get_active_pipelines_count(self) -> int:
        """Retorna número de pipelines ativos"""
        return len(self._active_pipelines)

    def get_pipeline_context(self, pipeline_id: str) -> PipelineContext:
        """Retorna contexto de um pipeline ativo"""
        return self._active_pipelines.get(pipeline_id)
