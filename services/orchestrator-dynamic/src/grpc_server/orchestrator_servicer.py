"""
Implementação do gRPC Servicer para Orchestrator Dynamic.

Este servicer recebe comandos estratégicos da Queen Agent para:
- Ajustar prioridades de workflows
- Rebalancear recursos entre workflows
- Pausar/retomar workflows
- Acionar replanejamento de planos
- Obter status detalhado de workflows
"""

import grpc
import structlog
import time
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional, Dict, Any

from neural_hive_observability.grpc_instrumentation import extract_grpc_context
from neural_hive_observability.context import set_baggage

from src.proto import (
    orchestrator_strategic_pb2_grpc,
    AdjustPrioritiesRequest,
    AdjustPrioritiesResponse,
    RebalanceResourcesRequest,
    RebalanceResourcesResponse,
    ResourceAllocation,
    WorkflowRebalanceResult,
    PauseWorkflowRequest,
    PauseWorkflowResponse,
    ResumeWorkflowRequest,
    ResumeWorkflowResponse,
    TriggerReplanningRequest,
    TriggerReplanningResponse,
    ReplanningTriggerType,
    GetWorkflowStatusRequest,
    GetWorkflowStatusResponse,
    WorkflowState,
    TicketSummary,
    WorkflowEvent,
)
from src.observability.metrics import OrchestratorMetrics

if TYPE_CHECKING:
    from src.clients.mongodb_client import MongoDBClient
    from src.policies.opa_client import OPAClient
    from src.scheduler.intelligent_scheduler import IntelligentScheduler
    from temporalio.client import Client as TemporalClient

logger = structlog.get_logger(__name__)


class OrchestratorStrategicServicer(orchestrator_strategic_pb2_grpc.OrchestratorStrategicServicer):
    """
    Implementação do serviço gRPC OrchestratorStrategic.

    Recebe comandos estratégicos da Queen Agent e coordena
    com Temporal, IntelligentScheduler e PolicyValidator.
    """

    def __init__(
        self,
        temporal_client: Optional['TemporalClient'],
        intelligent_scheduler: Optional['IntelligentScheduler'],
        opa_client: Optional['OPAClient'],
        mongodb_client: Optional['MongoDBClient'],
        kafka_producer=None,
        config=None
    ):
        """
        Inicializa o servicer com dependências.

        Args:
            temporal_client: Cliente Temporal para sinalizar workflows
            intelligent_scheduler: Scheduler para ajustes de prioridade/recursos
            opa_client: Cliente OPA para validação de políticas
            mongodb_client: Cliente MongoDB para auditoria
            kafka_producer: Producer Kafka para eventos de replanejamento
            config: Configurações do serviço
        """
        self.temporal_client = temporal_client
        self.scheduler = intelligent_scheduler
        self.opa_client = opa_client
        self.mongodb_client = mongodb_client
        self.kafka_producer = kafka_producer
        self.config = config
        self.metrics = OrchestratorMetrics()
        self.logger = logger.bind(component='orchestrator_strategic_servicer')

    async def _validate_with_opa(self, policy_path: str, input_data: Dict[str, Any]) -> bool:
        """
        Valida operação com OPA.

        Args:
            policy_path: Caminho da política OPA
            input_data: Dados de entrada para avaliação

        Returns:
            True se permitido, False caso contrário
        """
        if not self.opa_client:
            self.logger.warning('opa_client_not_available', policy=policy_path)
            # Fail-open apenas em desenvolvimento
            return self.config and self.config.environment.lower() in ('dev', 'development')

        try:
            result = await self.opa_client.evaluate_policy(policy_path, input_data)
            return result.get('allow', False)
        except Exception as e:
            self.logger.error('opa_evaluation_failed', policy=policy_path, error=str(e))
            if self.config and getattr(self.config, 'opa_fail_open', False):
                return True
            return False

    async def _audit_operation(
        self,
        operation: str,
        request_data: Dict[str, Any],
        success: bool,
        message: str
    ):
        """
        Registra operação para auditoria no MongoDB.

        Args:
            operation: Tipo da operação
            request_data: Dados do request
            success: Se foi bem-sucedida
            message: Mensagem de resultado
        """
        if not self.mongodb_client:
            return

        try:
            audit_record = {
                'operation': operation,
                'request_data': request_data,
                'success': success,
                'message': message,
                'timestamp': datetime.utcnow(),
                'source': 'queen-agent'
            }
            await self.mongodb_client.db.strategic_operations_audit.insert_one(audit_record)
        except Exception as e:
            self.logger.warning('audit_insert_failed', error=str(e))

    async def AdjustPriorities(
        self,
        request: AdjustPrioritiesRequest,
        context: grpc.aio.ServicerContext
    ) -> AdjustPrioritiesResponse:
        """
        Ajustar prioridade de um workflow.

        Valida com OPA, atualiza no IntelligentScheduler e sinaliza o Temporal.
        """
        start_time = time.time()
        method_name = 'AdjustPriorities'

        try:
            # Extrair contexto de tracing
            metadata_dict = dict(context.invocation_metadata())
            extract_grpc_context(metadata_dict)
            set_baggage('workflow_id', request.workflow_id)

            self.logger.info(
                'adjust_priorities_request',
                workflow_id=request.workflow_id,
                plan_id=request.plan_id,
                new_priority=request.new_priority,
                adjustment_id=request.adjustment_id
            )

            # Validar prioridade
            if not 1 <= request.new_priority <= 10:
                await context.abort(
                    grpc.StatusCode.INVALID_ARGUMENT,
                    'new_priority deve estar entre 1 e 10'
                )

            # Validar com OPA
            opa_input = {
                'workflow_id': request.workflow_id,
                'new_priority': request.new_priority,
                'reason': request.reason,
                'operation': 'adjust_priority'
            }
            if not await self._validate_with_opa(
                'neuralhive/orchestrator/strategic_adjustments',
                opa_input
            ):
                self.metrics.grpc_requests_total.labels(
                    method=method_name, status='permission_denied'
                ).inc()
                await context.abort(
                    grpc.StatusCode.PERMISSION_DENIED,
                    'Ajuste de prioridade não autorizado pela política OPA'
                )

            # Obter prioridade anterior (se disponível)
            previous_priority = 5  # Default
            if self.mongodb_client:
                workflow_doc = await self.mongodb_client.db.workflows.find_one(
                    {'workflow_id': request.workflow_id}
                )
                if workflow_doc:
                    previous_priority = workflow_doc.get('priority', 5)

            # Atualizar prioridade no scheduler (se disponível)
            if self.scheduler:
                scheduler_updated = await self.scheduler.update_workflow_priority(
                    workflow_id=request.workflow_id,
                    new_priority=request.new_priority,
                    reason=request.reason
                )
                self.logger.info(
                    'scheduler_priority_update',
                    workflow_id=request.workflow_id,
                    old_priority=previous_priority,
                    new_priority=request.new_priority,
                    scheduler_updated=scheduler_updated
                )

            # Atualizar no MongoDB
            if self.mongodb_client:
                await self.mongodb_client.db.workflows.update_one(
                    {'workflow_id': request.workflow_id},
                    {
                        '$set': {
                            'priority': request.new_priority,
                            'priority_updated_at': datetime.utcnow(),
                            'priority_reason': request.reason
                        }
                    },
                    upsert=True
                )

            # Sinalizar workflow Temporal
            if self.temporal_client:
                try:
                    workflow_handle = self.temporal_client.get_workflow_handle(
                        request.workflow_id
                    )
                    await workflow_handle.signal(
                        'priority_adjusted',
                        {
                            'new_priority': request.new_priority,
                            'reason': request.reason,
                            'adjustment_id': request.adjustment_id
                        }
                    )
                    self.logger.info(
                        'temporal_signal_sent',
                        workflow_id=request.workflow_id,
                        signal='priority_adjusted'
                    )
                except Exception as temporal_error:
                    self.logger.warning(
                        'temporal_signal_failed',
                        workflow_id=request.workflow_id,
                        error=str(temporal_error)
                    )

            # Publicar evento Kafka
            if self.kafka_producer:
                try:
                    kafka_event = {
                        'event_type': 'priority_adjusted',
                        'workflow_id': request.workflow_id,
                        'plan_id': request.plan_id,
                        'previous_priority': previous_priority,
                        'new_priority': request.new_priority,
                        'reason': request.reason,
                        'adjustment_id': request.adjustment_id,
                        'timestamp': datetime.utcnow().isoformat(),
                        'source': 'queen-agent'
                    }
                    await self.kafka_producer.send_and_wait(
                        topic=getattr(self.config, 'KAFKA_TOPICS_STRATEGIC', 'strategic.adjustments'),
                        key=request.workflow_id,
                        value=kafka_event
                    )
                    self.logger.info(
                        'kafka_priority_event_published',
                        workflow_id=request.workflow_id,
                        adjustment_id=request.adjustment_id
                    )
                except Exception as kafka_error:
                    self.logger.warning(
                        'kafka_publish_failed',
                        workflow_id=request.workflow_id,
                        error=str(kafka_error)
                    )

            # Auditoria na collection strategic_adjustments (alinhado com testes)
            if self.mongodb_client:
                try:
                    audit_record = {
                        'operation': 'adjust_priorities',
                        'workflow_id': request.workflow_id,
                        'plan_id': request.plan_id,
                        'previous_priority': previous_priority,
                        'new_priority': request.new_priority,
                        'reason': request.reason,
                        'adjustment_id': request.adjustment_id,
                        'success': True,
                        'message': f'Prioridade ajustada de {previous_priority} para {request.new_priority}',
                        'timestamp': datetime.utcnow(),
                        'source': 'queen-agent'
                    }
                    await self.mongodb_client.db.strategic_adjustments.insert_one(audit_record)
                except Exception as audit_error:
                    self.logger.warning('strategic_audit_insert_failed', error=str(audit_error))

            self.metrics.grpc_requests_total.labels(
                method=method_name, status='success'
            ).inc()

            return AdjustPrioritiesResponse(
                success=True,
                message=f'Prioridade ajustada com sucesso para {request.new_priority}',
                previous_priority=previous_priority,
                applied_priority=request.new_priority,
                applied_at=int(datetime.utcnow().timestamp() * 1000)
            )

        except grpc.RpcError:
            raise
        except Exception as e:
            self.logger.error('adjust_priorities_failed', error=str(e))
            self.metrics.grpc_requests_total.labels(
                method=method_name, status='error'
            ).inc()
            await context.abort(grpc.StatusCode.INTERNAL, str(e))

        finally:
            duration = time.time() - start_time
            self.metrics.grpc_request_duration_seconds.labels(
                method=method_name
            ).observe(duration)

    async def RebalanceResources(
        self,
        request: RebalanceResourcesRequest,
        context: grpc.aio.ServicerContext
    ) -> RebalanceResourcesResponse:
        """
        Rebalancear alocação de recursos entre workflows.

        Valida limites com OPA e atualiza alocações no ResourceAllocator.
        """
        start_time = time.time()
        method_name = 'RebalanceResources'

        try:
            metadata_dict = dict(context.invocation_metadata())
            extract_grpc_context(metadata_dict)

            self.logger.info(
                'rebalance_resources_request',
                workflow_count=len(request.workflow_ids),
                rebalance_id=request.rebalance_id
            )

            # Validar com OPA - limites de recursos
            opa_input = {
                'workflow_ids': list(request.workflow_ids),
                'target_allocation': {
                    wf_id: {
                        'cpu_millicores': alloc.cpu_millicores,
                        'memory_mb': alloc.memory_mb,
                        'max_parallel_tickets': alloc.max_parallel_tickets
                    }
                    for wf_id, alloc in request.target_allocation.items()
                },
                'operation': 'rebalance_resources'
            }
            if not await self._validate_with_opa(
                'neuralhive/orchestrator/resource_limits',
                opa_input
            ):
                self.metrics.grpc_requests_total.labels(
                    method=method_name, status='permission_denied'
                ).inc()
                await context.abort(
                    grpc.StatusCode.PERMISSION_DENIED,
                    'Rebalanceamento não autorizado pela política de limites de recursos'
                )

            results = []
            for workflow_id in request.workflow_ids:
                target = request.target_allocation.get(workflow_id)

                # Obter alocação anterior
                previous_alloc = ResourceAllocation(
                    cpu_millicores=1000,
                    memory_mb=2048,
                    max_parallel_tickets=10,
                    scheduling_priority=5
                )
                if self.mongodb_client:
                    wf_doc = await self.mongodb_client.db.workflows.find_one(
                        {'workflow_id': workflow_id}
                    )
                    if wf_doc and 'resources' in wf_doc:
                        res = wf_doc['resources']
                        previous_alloc = ResourceAllocation(
                            cpu_millicores=res.get('cpu_millicores', 1000),
                            memory_mb=res.get('memory_mb', 2048),
                            max_parallel_tickets=res.get('max_parallel_tickets', 10),
                            scheduling_priority=res.get('scheduling_priority', 5)
                        )

                if target:
                    # Chamar scheduler para aplicar rebalanceamento
                    scheduler_result = {'success': True, 'message': 'Recursos realocados'}
                    if self.scheduler:
                        target_dict = {
                            'cpu_millicores': target.cpu_millicores,
                            'memory_mb': target.memory_mb,
                            'max_parallel_tickets': target.max_parallel_tickets,
                            'scheduling_priority': target.scheduling_priority
                        }
                        scheduler_result = await self.scheduler.reallocate_resources(
                            workflow_id=workflow_id,
                            target_allocation=target_dict
                        )
                        self.logger.info(
                            'scheduler_resource_reallocation',
                            workflow_id=workflow_id,
                            scheduler_success=scheduler_result.get('success', False)
                        )

                    # Atualizar no MongoDB
                    if self.mongodb_client:
                        await self.mongodb_client.db.workflows.update_one(
                            {'workflow_id': workflow_id},
                            {
                                '$set': {
                                    'resources': {
                                        'cpu_millicores': target.cpu_millicores,
                                        'memory_mb': target.memory_mb,
                                        'max_parallel_tickets': target.max_parallel_tickets,
                                        'scheduling_priority': target.scheduling_priority
                                    },
                                    'resources_updated_at': datetime.utcnow()
                                }
                            },
                            upsert=True
                        )

                    # Usar resultado do scheduler para determinar sucesso
                    results.append(WorkflowRebalanceResult(
                        workflow_id=workflow_id,
                        success=scheduler_result.get('success', True),
                        message=scheduler_result.get('message', 'Recursos rebalanceados com sucesso'),
                        previous_allocation=previous_alloc,
                        applied_allocation=target
                    ))
                else:
                    results.append(WorkflowRebalanceResult(
                        workflow_id=workflow_id,
                        success=False,
                        message='Alocação alvo não especificada',
                        previous_allocation=previous_alloc
                    ))

            # Auditoria
            await self._audit_operation(
                operation='rebalance_resources',
                request_data={
                    'workflow_ids': list(request.workflow_ids),
                    'rebalance_id': request.rebalance_id,
                    'reason': request.reason
                },
                success=all(r.success for r in results),
                message=f'Rebalanceado {sum(1 for r in results if r.success)}/{len(results)} workflows'
            )

            self.metrics.grpc_requests_total.labels(
                method=method_name, status='success'
            ).inc()

            return RebalanceResourcesResponse(
                success=all(r.success for r in results),
                message=f'Rebalanceamento concluído para {len(results)} workflows',
                results=results,
                applied_at=int(datetime.utcnow().timestamp() * 1000)
            )

        except grpc.RpcError:
            raise
        except Exception as e:
            self.logger.error('rebalance_resources_failed', error=str(e))
            self.metrics.grpc_requests_total.labels(
                method=method_name, status='error'
            ).inc()
            await context.abort(grpc.StatusCode.INTERNAL, str(e))

        finally:
            duration = time.time() - start_time
            self.metrics.grpc_request_duration_seconds.labels(
                method=method_name
            ).observe(duration)

    async def PauseWorkflow(
        self,
        request: PauseWorkflowRequest,
        context: grpc.aio.ServicerContext
    ) -> PauseWorkflowResponse:
        """
        Pausar workflow em execução.

        Envia sinal PAUSE para o workflow Temporal.
        """
        start_time = time.time()
        method_name = 'PauseWorkflow'

        try:
            metadata_dict = dict(context.invocation_metadata())
            extract_grpc_context(metadata_dict)
            set_baggage('workflow_id', request.workflow_id)

            self.logger.info(
                'pause_workflow_request',
                workflow_id=request.workflow_id,
                reason=request.reason,
                adjustment_id=request.adjustment_id
            )

            # Verificar estado atual do workflow
            if self.mongodb_client:
                wf_doc = await self.mongodb_client.db.workflows.find_one(
                    {'workflow_id': request.workflow_id}
                )
                if wf_doc:
                    current_state = wf_doc.get('state', 'RUNNING')
                    if current_state in ('COMPLETED', 'FAILED', 'CANCELLED'):
                        await context.abort(
                            grpc.StatusCode.FAILED_PRECONDITION,
                            f'Workflow em estado terminal ({current_state}) não pode ser pausado'
                        )
                    if current_state == 'PAUSED':
                        return PauseWorkflowResponse(
                            success=True,
                            message='Workflow já está pausado',
                            paused_at=int(wf_doc.get('paused_at', datetime.utcnow()).timestamp() * 1000)
                        )

            paused_at = datetime.utcnow()
            scheduled_resume_at = None

            if request.pause_duration_seconds and request.pause_duration_seconds > 0:
                from datetime import timedelta
                scheduled_resume_at = paused_at + timedelta(seconds=request.pause_duration_seconds)

            # Sinalizar workflow Temporal
            if self.temporal_client:
                try:
                    workflow_handle = self.temporal_client.get_workflow_handle(
                        request.workflow_id
                    )
                    await workflow_handle.signal(
                        'pause',
                        {
                            'reason': request.reason,
                            'duration_seconds': request.pause_duration_seconds,
                            'adjustment_id': request.adjustment_id
                        }
                    )
                    self.logger.info(
                        'temporal_pause_signal_sent',
                        workflow_id=request.workflow_id
                    )
                except Exception as temporal_error:
                    self.logger.warning(
                        'temporal_pause_signal_failed',
                        workflow_id=request.workflow_id,
                        error=str(temporal_error)
                    )

            # Atualizar estado no MongoDB
            if self.mongodb_client:
                update_data = {
                    'state': 'PAUSED',
                    'paused_at': paused_at,
                    'pause_reason': request.reason
                }
                if scheduled_resume_at:
                    update_data['scheduled_resume_at'] = scheduled_resume_at

                await self.mongodb_client.db.workflows.update_one(
                    {'workflow_id': request.workflow_id},
                    {'$set': update_data},
                    upsert=True
                )

            # Auditoria
            await self._audit_operation(
                operation='pause_workflow',
                request_data={
                    'workflow_id': request.workflow_id,
                    'reason': request.reason,
                    'duration_seconds': request.pause_duration_seconds,
                    'adjustment_id': request.adjustment_id
                },
                success=True,
                message=f'Workflow pausado com sucesso'
            )

            self.metrics.grpc_requests_total.labels(
                method=method_name, status='success'
            ).inc()

            response = PauseWorkflowResponse(
                success=True,
                message='Workflow pausado com sucesso',
                paused_at=int(paused_at.timestamp() * 1000)
            )
            if scheduled_resume_at:
                response.scheduled_resume_at = int(scheduled_resume_at.timestamp() * 1000)

            return response

        except grpc.RpcError:
            raise
        except Exception as e:
            self.logger.error('pause_workflow_failed', error=str(e))
            self.metrics.grpc_requests_total.labels(
                method=method_name, status='error'
            ).inc()
            await context.abort(grpc.StatusCode.INTERNAL, str(e))

        finally:
            duration = time.time() - start_time
            self.metrics.grpc_request_duration_seconds.labels(
                method=method_name
            ).observe(duration)

    async def ResumeWorkflow(
        self,
        request: ResumeWorkflowRequest,
        context: grpc.aio.ServicerContext
    ) -> ResumeWorkflowResponse:
        """
        Retomar workflow pausado.

        Envia sinal RESUME para o workflow Temporal.
        """
        start_time = time.time()
        method_name = 'ResumeWorkflow'

        try:
            metadata_dict = dict(context.invocation_metadata())
            extract_grpc_context(metadata_dict)
            set_baggage('workflow_id', request.workflow_id)

            self.logger.info(
                'resume_workflow_request',
                workflow_id=request.workflow_id,
                adjustment_id=request.adjustment_id
            )

            # Verificar estado atual
            pause_duration_seconds = 0
            if self.mongodb_client:
                wf_doc = await self.mongodb_client.db.workflows.find_one(
                    {'workflow_id': request.workflow_id}
                )
                if wf_doc:
                    current_state = wf_doc.get('state', 'RUNNING')
                    if current_state != 'PAUSED':
                        await context.abort(
                            grpc.StatusCode.FAILED_PRECONDITION,
                            f'Workflow não está pausado (estado atual: {current_state})'
                        )
                    paused_at = wf_doc.get('paused_at')
                    if paused_at:
                        pause_duration_seconds = int(
                            (datetime.utcnow() - paused_at).total_seconds()
                        )

            resumed_at = datetime.utcnow()

            # Sinalizar workflow Temporal
            if self.temporal_client:
                try:
                    workflow_handle = self.temporal_client.get_workflow_handle(
                        request.workflow_id
                    )
                    await workflow_handle.signal(
                        'resume',
                        {
                            'reason': request.reason,
                            'adjustment_id': request.adjustment_id
                        }
                    )
                    self.logger.info(
                        'temporal_resume_signal_sent',
                        workflow_id=request.workflow_id
                    )
                except Exception as temporal_error:
                    self.logger.warning(
                        'temporal_resume_signal_failed',
                        workflow_id=request.workflow_id,
                        error=str(temporal_error)
                    )

            # Atualizar estado no MongoDB
            if self.mongodb_client:
                await self.mongodb_client.db.workflows.update_one(
                    {'workflow_id': request.workflow_id},
                    {
                        '$set': {
                            'state': 'RUNNING',
                            'resumed_at': resumed_at,
                            'resume_reason': request.reason
                        },
                        '$unset': {
                            'paused_at': '',
                            'pause_reason': '',
                            'scheduled_resume_at': ''
                        }
                    }
                )

            # Auditoria
            await self._audit_operation(
                operation='resume_workflow',
                request_data={
                    'workflow_id': request.workflow_id,
                    'reason': request.reason,
                    'adjustment_id': request.adjustment_id
                },
                success=True,
                message=f'Workflow retomado após {pause_duration_seconds}s pausado'
            )

            self.metrics.grpc_requests_total.labels(
                method=method_name, status='success'
            ).inc()

            return ResumeWorkflowResponse(
                success=True,
                message='Workflow retomado com sucesso',
                resumed_at=int(resumed_at.timestamp() * 1000),
                pause_duration_seconds=pause_duration_seconds
            )

        except grpc.RpcError:
            raise
        except Exception as e:
            self.logger.error('resume_workflow_failed', error=str(e))
            self.metrics.grpc_requests_total.labels(
                method=method_name, status='error'
            ).inc()
            await context.abort(grpc.StatusCode.INTERNAL, str(e))

        finally:
            duration = time.time() - start_time
            self.metrics.grpc_request_duration_seconds.labels(
                method=method_name
            ).observe(duration)

    async def TriggerReplanning(
        self,
        request: TriggerReplanningRequest,
        context: grpc.aio.ServicerContext
    ) -> TriggerReplanningResponse:
        """
        Acionar replanejamento de um plano.

        Publica evento Kafka para o Consensus Engine processar.
        """
        start_time = time.time()
        method_name = 'TriggerReplanning'

        try:
            metadata_dict = dict(context.invocation_metadata())
            extract_grpc_context(metadata_dict)
            set_baggage('plan_id', request.plan_id)

            self.logger.info(
                'trigger_replanning_request',
                plan_id=request.plan_id,
                trigger_type=ReplanningTriggerType.Name(request.trigger_type),
                adjustment_id=request.adjustment_id
            )

            # Validar com OPA
            opa_input = {
                'plan_id': request.plan_id,
                'trigger_type': ReplanningTriggerType.Name(request.trigger_type),
                'reason': request.reason,
                'operation': 'trigger_replanning'
            }
            if not await self._validate_with_opa(
                'neuralhive/orchestrator/strategic_adjustments',
                opa_input
            ):
                self.metrics.grpc_requests_total.labels(
                    method=method_name, status='permission_denied'
                ).inc()
                await context.abort(
                    grpc.StatusCode.PERMISSION_DENIED,
                    'Replanejamento não autorizado pela política OPA'
                )

            # Gerar ID do replanejamento
            replanning_id = f"replan-{uuid.uuid4().hex[:12]}"
            triggered_at = datetime.utcnow()

            # Publicar evento Kafka para Consensus Engine
            if self.kafka_producer:
                replanning_event = {
                    'replanning_id': replanning_id,
                    'plan_id': request.plan_id,
                    'trigger_type': ReplanningTriggerType.Name(request.trigger_type),
                    'reason': request.reason,
                    'context': dict(request.context),
                    'preserve_progress': request.preserve_progress,
                    'priority': request.priority,
                    'adjustment_id': request.adjustment_id,
                    'triggered_at': triggered_at.isoformat(),
                    'source': 'queen-agent'
                }
                await self.kafka_producer.produce(
                    topic='plans.replanning_requested',
                    key=request.plan_id,
                    value=replanning_event
                )
                self.logger.info(
                    'replanning_event_published',
                    replanning_id=replanning_id,
                    topic='plans.replanning_requested'
                )

            # Registrar no MongoDB
            if self.mongodb_client:
                await self.mongodb_client.db.replanning_requests.insert_one({
                    'replanning_id': replanning_id,
                    'plan_id': request.plan_id,
                    'trigger_type': ReplanningTriggerType.Name(request.trigger_type),
                    'reason': request.reason,
                    'context': dict(request.context),
                    'preserve_progress': request.preserve_progress,
                    'priority': request.priority,
                    'adjustment_id': request.adjustment_id,
                    'triggered_at': triggered_at,
                    'status': 'PENDING'
                })

            # Auditoria
            await self._audit_operation(
                operation='trigger_replanning',
                request_data={
                    'plan_id': request.plan_id,
                    'trigger_type': ReplanningTriggerType.Name(request.trigger_type),
                    'reason': request.reason,
                    'adjustment_id': request.adjustment_id,
                    'replanning_id': replanning_id
                },
                success=True,
                message=f'Replanejamento acionado: {replanning_id}'
            )

            self.metrics.grpc_requests_total.labels(
                method=method_name, status='success'
            ).inc()

            return TriggerReplanningResponse(
                success=True,
                message='Replanejamento acionado com sucesso',
                replanning_id=replanning_id,
                triggered_at=int(triggered_at.timestamp() * 1000)
            )

        except grpc.RpcError:
            raise
        except Exception as e:
            self.logger.error('trigger_replanning_failed', error=str(e))
            self.metrics.grpc_requests_total.labels(
                method=method_name, status='error'
            ).inc()
            await context.abort(grpc.StatusCode.INTERNAL, str(e))

        finally:
            duration = time.time() - start_time
            self.metrics.grpc_request_duration_seconds.labels(
                method=method_name
            ).observe(duration)

    async def GetWorkflowStatus(
        self,
        request: GetWorkflowStatusRequest,
        context: grpc.aio.ServicerContext
    ) -> GetWorkflowStatusResponse:
        """
        Obter status detalhado de um workflow.

        Combina dados do Temporal e MongoDB.
        """
        start_time = time.time()
        method_name = 'GetWorkflowStatus'

        try:
            metadata_dict = dict(context.invocation_metadata())
            extract_grpc_context(metadata_dict)
            set_baggage('workflow_id', request.workflow_id)

            self.logger.info(
                'get_workflow_status_request',
                workflow_id=request.workflow_id,
                include_tickets=request.include_tickets,
                include_history=request.include_history
            )

            # Buscar dados do MongoDB
            workflow_data = {}
            if self.mongodb_client:
                workflow_data = await self.mongodb_client.db.workflows.find_one(
                    {'workflow_id': request.workflow_id}
                ) or {}

            # Mapear estado
            state_map = {
                'PENDING': WorkflowState.WORKFLOW_STATE_PENDING,
                'RUNNING': WorkflowState.WORKFLOW_STATE_RUNNING,
                'PAUSED': WorkflowState.WORKFLOW_STATE_PAUSED,
                'COMPLETED': WorkflowState.WORKFLOW_STATE_COMPLETED,
                'FAILED': WorkflowState.WORKFLOW_STATE_FAILED,
                'CANCELLED': WorkflowState.WORKFLOW_STATE_CANCELLED,
                'REPLANNING': WorkflowState.WORKFLOW_STATE_REPLANNING
            }
            current_state = state_map.get(
                workflow_data.get('state', 'PENDING'),
                WorkflowState.WORKFLOW_STATE_UNSPECIFIED
            )

            # Obter recursos alocados
            resources = workflow_data.get('resources', {})
            allocated_resources = ResourceAllocation(
                cpu_millicores=resources.get('cpu_millicores', 1000),
                memory_mb=resources.get('memory_mb', 2048),
                max_parallel_tickets=resources.get('max_parallel_tickets', 10),
                scheduling_priority=resources.get('scheduling_priority', 5)
            )

            # Buscar tickets se solicitado
            tickets = TicketSummary(total=0, completed=0, pending=0, running=0, failed=0)
            if request.include_tickets and self.mongodb_client:
                pipeline = [
                    {'$match': {'workflow_id': request.workflow_id}},
                    {'$group': {
                        '_id': '$status',
                        'count': {'$sum': 1}
                    }}
                ]
                ticket_counts = {}
                async for doc in self.mongodb_client.db.execution_tickets.aggregate(pipeline):
                    ticket_counts[doc['_id']] = doc['count']

                tickets = TicketSummary(
                    total=sum(ticket_counts.values()),
                    completed=ticket_counts.get('COMPLETED', 0),
                    pending=ticket_counts.get('PENDING', 0),
                    running=ticket_counts.get('RUNNING', 0),
                    failed=ticket_counts.get('FAILED', 0)
                )

            # Calcular progresso
            progress_percent = 0.0
            if tickets.total > 0:
                progress_percent = (tickets.completed / tickets.total) * 100.0

            # Buscar histórico se solicitado
            history = []
            if request.include_history and self.mongodb_client:
                events_cursor = self.mongodb_client.db.workflow_events.find(
                    {'workflow_id': request.workflow_id}
                ).sort('timestamp', -1).limit(50)
                async for event in events_cursor:
                    history.append(WorkflowEvent(
                        event_type=event.get('event_type', ''),
                        timestamp=int(event.get('timestamp', datetime.utcnow()).timestamp() * 1000),
                        description=event.get('description', ''),
                        metadata=event.get('metadata', {})
                    ))

            # Timestamps
            started_at = workflow_data.get('started_at', datetime.utcnow())
            updated_at = workflow_data.get('updated_at', datetime.utcnow())

            self.metrics.grpc_requests_total.labels(
                method=method_name, status='success'
            ).inc()

            response = GetWorkflowStatusResponse(
                workflow_id=request.workflow_id,
                plan_id=workflow_data.get('plan_id', ''),
                state=current_state,
                current_priority=workflow_data.get('priority', 5),
                allocated_resources=allocated_resources,
                tickets=tickets,
                progress_percent=progress_percent,
                started_at=int(started_at.timestamp() * 1000) if started_at else 0,
                updated_at=int(updated_at.timestamp() * 1000) if updated_at else 0,
                history=history,
                metadata=workflow_data.get('metadata', {})
            )

            # SLA info se disponível
            if 'sla_deadline' in workflow_data:
                sla_deadline = workflow_data['sla_deadline']
                response.sla_deadline = int(sla_deadline.timestamp() * 1000)
                remaining = (sla_deadline - datetime.utcnow()).total_seconds()
                response.sla_remaining_seconds = max(0, int(remaining))

            return response

        except Exception as e:
            self.logger.error('get_workflow_status_failed', error=str(e))
            self.metrics.grpc_requests_total.labels(
                method=method_name, status='error'
            ).inc()
            await context.abort(grpc.StatusCode.INTERNAL, str(e))

        finally:
            duration = time.time() - start_time
            self.metrics.grpc_request_duration_seconds.labels(
                method=method_name
            ).observe(duration)
