"""
Cliente gRPC para Orchestrator Dynamic com suporte a mTLS via SPIFFE.

Este cliente permite que a Queen Agent envie comandos estratégicos para
o Orchestrator, incluindo ajustes de prioridade, recursos, pausas de
workflows e acionamento de replanejamento.
"""

import grpc
import structlog
import uuid
from typing import Optional, Dict, List, Tuple, Any

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)

from neural_hive_resilience.circuit_breaker import MonitoredCircuitBreaker, CircuitBreakerError
from neural_hive_observability import instrument_grpc_channel

from ..config import Settings
from ..proto import orchestrator_strategic_pb2, orchestrator_strategic_pb2_grpc

# Import SPIFFE/mTLS se disponível
try:
    from neural_hive_security import (
        SPIFFEManager,
        SPIFFEConfig,
        create_secure_grpc_channel,
        get_grpc_metadata_with_jwt,
    )
    SECURITY_LIB_AVAILABLE = True
except ImportError:
    SECURITY_LIB_AVAILABLE = False
    SPIFFEManager = None
    SPIFFEConfig = None

logger = structlog.get_logger(__name__)


class OrchestratorClient:
    """
    Cliente gRPC para Orchestrator Dynamic com suporte a mTLS via SPIFFE.

    Implementa circuit breaker, retry policies e autenticação JWT-SVID.
    """

    def __init__(self, settings: Settings):
        """
        Inicializa o cliente.

        Args:
            settings: Configurações do serviço
        """
        self.settings = settings
        self.grpc_host = getattr(settings, 'ORCHESTRATOR_GRPC_HOST', 'orchestrator-dynamic')
        self.grpc_port = getattr(settings, 'ORCHESTRATOR_GRPC_PORT', 50053)
        self.grpc_timeout = getattr(settings, 'ORCHESTRATOR_GRPC_TIMEOUT', 10)

        self.channel: Optional[grpc.aio.Channel] = None
        self.stub = None
        # Aliases para compatibilidade com testes e consumidores existentes
        self._channel: Optional[grpc.aio.Channel] = None
        self._stub = None
        self.spiffe_manager: Optional[SPIFFEManager] = None
        self.circuit_breaker: Optional[MonitoredCircuitBreaker] = None

        self.circuit_breaker_enabled = getattr(settings, 'CIRCUIT_BREAKER_ENABLED', True)
        self.logger = logger.bind(component='orchestrator_client')

    async def initialize(self) -> None:
        """
        Inicializar cliente gRPC com mTLS opcional.

        Cria canal seguro via SPIFFE se habilitado, caso contrário usa
        canal inseguro (apenas desenvolvimento).
        """
        target = f"{self.grpc_host}:{self.grpc_port}"

        # Verificar se mTLS via SPIFFE está habilitado
        spiffe_enabled = getattr(self.settings, 'SPIFFE_ENABLED', False)
        spiffe_x509_enabled = (
            spiffe_enabled
            and getattr(self.settings, 'SPIFFE_ENABLE_X509', False)
            and SECURITY_LIB_AVAILABLE
        )

        if spiffe_x509_enabled:
            try:
                # Criar configuração SPIFFE
                spiffe_config = SPIFFEConfig(
                    workload_api_socket=getattr(
                        self.settings, 'SPIFFE_SOCKET_PATH',
                        'unix:///run/spire/sockets/agent.sock'
                    ),
                    trust_domain=getattr(
                        self.settings, 'SPIFFE_TRUST_DOMAIN',
                        'neural-hive.local'
                    ),
                    enable_x509=True,
                    environment=self.settings.ENVIRONMENT
                )

                # Criar SPIFFE manager
                self.spiffe_manager = SPIFFEManager(spiffe_config)
                await self.spiffe_manager.initialize()

                # Criar canal seguro com mTLS
                is_dev_env = self.settings.ENVIRONMENT.lower() in ('dev', 'development')
                self.channel = await create_secure_grpc_channel(
                    target=target,
                    spiffe_config=spiffe_config,
                    spiffe_manager=self.spiffe_manager,
                    fallback_insecure=is_dev_env
                )

                self.logger.info(
                    'mtls_channel_configured',
                    target=target,
                    environment=self.settings.ENVIRONMENT
                )

            except Exception as e:
                self.logger.warning(
                    'mtls_channel_failed_fallback_insecure',
                    error=str(e),
                    target=target
                )
                self._create_insecure_channel(target)
        else:
            # Fallback para canal inseguro (apenas desenvolvimento)
            if self.settings.ENVIRONMENT.lower() in ('production', 'staging', 'prod'):
                self.logger.warning(
                    'insecure_channel_in_production',
                    target=target,
                    warning='mTLS é recomendado em produção'
                )
            self._create_insecure_channel(target)

        # Instrumentar canal com OpenTelemetry
        self.channel = instrument_grpc_channel(
            self.channel,
            service_name='queen-agent',
            target_service='orchestrator-dynamic'
        )

        # Criar stub gRPC
        self.stub = orchestrator_strategic_pb2_grpc.OrchestratorStrategicStub(self.channel)

        # Atualizar aliases para compatibilidade
        self._channel = self.channel
        self._stub = self.stub

        # Inicializar circuit breaker
        if self.circuit_breaker_enabled:
            self.circuit_breaker = MonitoredCircuitBreaker(
                service_name=self.settings.SERVICE_NAME,
                circuit_name='orchestrator_grpc',
                fail_max=getattr(self.settings, 'CIRCUIT_BREAKER_FAIL_MAX', 5),
                timeout_duration=getattr(self.settings, 'CIRCUIT_BREAKER_TIMEOUT', 60),
                recovery_timeout=getattr(self.settings, 'CIRCUIT_BREAKER_RECOVERY_TIMEOUT', 30),
                expected_exception=Exception
            )

        self.logger.info(
            'orchestrator_client_initialized',
            host=self.grpc_host,
            port=self.grpc_port,
            mtls_enabled=self.spiffe_manager is not None
        )

    async def connect(self) -> None:
        """
        Conecta ao servidor gRPC do Orchestrator.

        Alias para initialize() para compatibilidade com testes e consumidores existentes.
        """
        await self.initialize()

    def _create_insecure_channel(self, target: str) -> None:
        """Criar canal gRPC inseguro."""
        self.channel = grpc.aio.insecure_channel(
            target,
            options=[
                ('grpc.max_send_message_length', 100 * 1024 * 1024),
                ('grpc.max_receive_message_length', 100 * 1024 * 1024),
                ('grpc.keepalive_time_ms', 30000),
            ]
        )
        self.logger.info('insecure_channel_created', target=target)

    async def close(self) -> None:
        """Fechar canal gRPC e SPIFFE manager."""
        if self.spiffe_manager:
            await self.spiffe_manager.close()
        if self.channel:
            await self.channel.close()
        # Nullificar ambos os pares para compatibilidade
        self.channel = None
        self._channel = None
        self.stub = None
        self._stub = None
        self.logger.info('orchestrator_client_closed')

    async def _get_grpc_metadata(self) -> List[Tuple[str, str]]:
        """Obter metadata gRPC com JWT-SVID para autenticação."""
        if not self.spiffe_manager:
            return []

        try:
            audience = f"orchestrator-dynamic.{getattr(self.settings, 'SPIFFE_TRUST_DOMAIN', 'neural-hive.local')}"
            return await get_grpc_metadata_with_jwt(
                spiffe_manager=self.spiffe_manager,
                audience=audience,
                environment=self.settings.ENVIRONMENT
            )
        except Exception as e:
            self.logger.warning('jwt_svid_fetch_failed', error=str(e))
            if self.settings.ENVIRONMENT.lower() in ('production', 'staging', 'prod'):
                raise
            return []

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(grpc.RpcError),
        reraise=True
    )
    async def _call_with_retry(
        self,
        method,
        request,
        metadata: List[Tuple[str, str]],
        timeout: int
    ):
        """Executar chamada gRPC com retry automático."""
        return await method(request, metadata=metadata, timeout=timeout)

    async def _call_with_breaker(
        self,
        method,
        request,
        timeout: Optional[int] = None
    ):
        """Executar chamada gRPC com circuit breaker e retry."""
        metadata = await self._get_grpc_metadata()
        timeout = timeout or self.grpc_timeout

        async def _call():
            return await self._call_with_retry(method, request, metadata, timeout)

        if self.circuit_breaker:
            try:
                return await self.circuit_breaker.call_async(_call)
            except CircuitBreakerError:
                self.logger.warning(
                    'orchestrator_circuit_open',
                    operation=method.__name__
                )
                raise
        return await _call()

    async def adjust_priorities(
        self,
        workflow_id: str,
        plan_id: str,
        new_priority: int,
        reason: str,
        adjustment_id: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None
    ) -> bool:
        """
        Ajustar prioridade de um workflow.

        Args:
            workflow_id: ID do workflow
            plan_id: ID do plano associado
            new_priority: Nova prioridade (1-10)
            reason: Razão do ajuste
            adjustment_id: ID único do ajuste (opcional)
            metadata: Metadados adicionais para o request (opcional)

        Returns:
            True se bem-sucedido
        """
        if adjustment_id is None:
            adjustment_id = f"adj-{uuid.uuid4().hex[:12]}"

        request = orchestrator_strategic_pb2.AdjustPrioritiesRequest(
            workflow_id=workflow_id,
            plan_id=plan_id,
            new_priority=new_priority,
            reason=reason,
            adjustment_id=adjustment_id
        )

        # Adicionar metadata se fornecido
        if metadata:
            for key, value in metadata.items():
                request.metadata[key] = value

        try:
            response = await self._call_with_breaker(
                self.stub.AdjustPriorities,
                request
            )

            self.logger.info(
                'priority_adjusted',
                workflow_id=workflow_id,
                new_priority=new_priority,
                success=response.success
            )

            return response.success

        except grpc.RpcError as e:
            self.logger.error(
                'adjust_priorities_failed',
                workflow_id=workflow_id,
                error=str(e),
                code=e.code()
            )
            return False

    async def rebalance_resources(
        self,
        workflow_ids: List[str],
        target_allocation: Dict[str, Dict[str, int]],
        reason: str,
        rebalance_id: Optional[str] = None,
        force: bool = False
    ) -> Dict[str, Any]:
        """
        Rebalancear recursos entre workflows.

        Args:
            workflow_ids: IDs dos workflows
            target_allocation: Mapa workflow_id -> {cpu_millicores, memory_mb, max_parallel_tickets}
            reason: Razão do rebalanceamento
            rebalance_id: ID único (opcional)
            force: Forçar rebalanceamento

        Returns:
            Dict com resultado por workflow
        """
        if rebalance_id is None:
            rebalance_id = f"rebal-{uuid.uuid4().hex[:12]}"

        # Converter target_allocation para proto
        proto_allocations = {}
        for wf_id, alloc in target_allocation.items():
            proto_allocations[wf_id] = orchestrator_strategic_pb2.ResourceAllocation(
                cpu_millicores=alloc.get('cpu_millicores', 1000),
                memory_mb=alloc.get('memory_mb', 2048),
                max_parallel_tickets=alloc.get('max_parallel_tickets', 10),
                scheduling_priority=alloc.get('scheduling_priority', 5)
            )

        request = orchestrator_strategic_pb2.RebalanceResourcesRequest(
            workflow_ids=workflow_ids,
            target_allocation=proto_allocations,
            reason=reason,
            rebalance_id=rebalance_id,
            force=force
        )

        try:
            response = await self._call_with_breaker(
                self.stub.RebalanceResources,
                request
            )

            results = {
                'success': response.success,
                'message': response.message,
                'applied_at': response.applied_at,
                'workflows': {}
            }

            for result in response.results:
                results['workflows'][result.workflow_id] = {
                    'success': result.success,
                    'message': result.message
                }

            self.logger.info(
                'resources_rebalanced',
                workflow_count=len(workflow_ids),
                success=response.success
            )

            return results

        except grpc.RpcError as e:
            self.logger.error(
                'rebalance_resources_failed',
                error=str(e),
                code=e.code()
            )
            return {'success': False, 'error': str(e)}

    async def pause_workflow(
        self,
        workflow_id: str,
        reason: str,
        duration_seconds: Optional[int] = None,
        adjustment_id: Optional[str] = None
    ) -> bool:
        """
        Pausar workflow em execução.

        Args:
            workflow_id: ID do workflow
            reason: Razão da pausa
            duration_seconds: Duração da pausa (0 = indefinido)
            adjustment_id: ID único (opcional)

        Returns:
            True se bem-sucedido
        """
        if adjustment_id is None:
            adjustment_id = f"pause-{uuid.uuid4().hex[:12]}"

        request = orchestrator_strategic_pb2.PauseWorkflowRequest(
            workflow_id=workflow_id,
            reason=reason,
            adjustment_id=adjustment_id
        )
        if duration_seconds:
            request.pause_duration_seconds = duration_seconds

        try:
            response = await self._call_with_breaker(
                self.stub.PauseWorkflow,
                request
            )

            self.logger.info(
                'workflow_paused',
                workflow_id=workflow_id,
                success=response.success
            )

            return response.success

        except grpc.RpcError as e:
            self.logger.error(
                'pause_workflow_failed',
                workflow_id=workflow_id,
                error=str(e),
                code=e.code()
            )
            return False

    async def resume_workflow(
        self,
        workflow_id: str,
        reason: str = '',
        adjustment_id: Optional[str] = None
    ) -> bool:
        """
        Retomar workflow pausado.

        Args:
            workflow_id: ID do workflow
            reason: Razão da retomada (opcional)
            adjustment_id: ID único (opcional)

        Returns:
            True se bem-sucedido
        """
        if adjustment_id is None:
            adjustment_id = f"resume-{uuid.uuid4().hex[:12]}"

        request = orchestrator_strategic_pb2.ResumeWorkflowRequest(
            workflow_id=workflow_id,
            reason=reason,
            adjustment_id=adjustment_id
        )

        try:
            response = await self._call_with_breaker(
                self.stub.ResumeWorkflow,
                request
            )

            self.logger.info(
                'workflow_resumed',
                workflow_id=workflow_id,
                success=response.success,
                pause_duration_seconds=response.pause_duration_seconds
            )

            return response.success

        except grpc.RpcError as e:
            self.logger.error(
                'resume_workflow_failed',
                workflow_id=workflow_id,
                error=str(e),
                code=e.code()
            )
            return False

    async def trigger_replanning(
        self,
        plan_id: str,
        reason: str,
        trigger_type: str = 'STRATEGIC',
        context: Optional[Dict[str, str]] = None,
        preserve_progress: bool = True,
        priority: int = 5,
        adjustment_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Acionar replanejamento de um plano.

        Args:
            plan_id: ID do plano
            reason: Razão do replanejamento
            trigger_type: Tipo de trigger (DRIFT, FAILURE, STRATEGIC, SLA_VIOLATION, RESOURCE_CONSTRAINT)
            context: Contexto adicional
            preserve_progress: Preservar progresso existente
            priority: Prioridade do replanejamento (1-10)
            adjustment_id: ID único (opcional)

        Returns:
            ID do replanejamento ou None se falhar
        """
        if adjustment_id is None:
            adjustment_id = f"replan-{uuid.uuid4().hex[:12]}"

        # Mapear trigger_type string para enum
        trigger_map = {
            'DRIFT': orchestrator_strategic_pb2.TRIGGER_TYPE_DRIFT,
            'FAILURE': orchestrator_strategic_pb2.TRIGGER_TYPE_FAILURE,
            'STRATEGIC': orchestrator_strategic_pb2.TRIGGER_TYPE_STRATEGIC,
            'SLA_VIOLATION': orchestrator_strategic_pb2.TRIGGER_TYPE_SLA_VIOLATION,
            'RESOURCE_CONSTRAINT': orchestrator_strategic_pb2.TRIGGER_TYPE_RESOURCE_CONSTRAINT,
        }
        trigger_enum = trigger_map.get(
            trigger_type.upper(),
            orchestrator_strategic_pb2.TRIGGER_TYPE_STRATEGIC
        )

        request = orchestrator_strategic_pb2.TriggerReplanningRequest(
            plan_id=plan_id,
            reason=reason,
            trigger_type=trigger_enum,
            adjustment_id=adjustment_id,
            context=context or {},
            preserve_progress=preserve_progress,
            priority=priority
        )

        try:
            response = await self._call_with_breaker(
                self.stub.TriggerReplanning,
                request
            )

            if response.success:
                self.logger.info(
                    'replanning_triggered',
                    plan_id=plan_id,
                    replanning_id=response.replanning_id
                )
                return response.replanning_id
            else:
                self.logger.warning(
                    'replanning_trigger_failed',
                    plan_id=plan_id,
                    message=response.message
                )
                return None

        except grpc.RpcError as e:
            self.logger.error(
                'trigger_replanning_failed',
                plan_id=plan_id,
                error=str(e),
                code=e.code()
            )
            return None

    async def get_workflow_status(
        self,
        workflow_id: str,
        include_tickets: bool = False,
        include_history: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Obter status detalhado de um workflow.

        Args:
            workflow_id: ID do workflow
            include_tickets: Incluir resumo de tickets
            include_history: Incluir histórico de eventos

        Returns:
            Dict com status ou None se falhar
        """
        request = orchestrator_strategic_pb2.GetWorkflowStatusRequest(
            workflow_id=workflow_id,
            include_tickets=include_tickets,
            include_history=include_history
        )

        try:
            response = await self._call_with_breaker(
                self.stub.GetWorkflowStatus,
                request
            )

            # Mapear estado enum para string
            state_map = {
                orchestrator_strategic_pb2.WORKFLOW_STATE_PENDING: 'PENDING',
                orchestrator_strategic_pb2.WORKFLOW_STATE_RUNNING: 'RUNNING',
                orchestrator_strategic_pb2.WORKFLOW_STATE_PAUSED: 'PAUSED',
                orchestrator_strategic_pb2.WORKFLOW_STATE_COMPLETED: 'COMPLETED',
                orchestrator_strategic_pb2.WORKFLOW_STATE_FAILED: 'FAILED',
                orchestrator_strategic_pb2.WORKFLOW_STATE_CANCELLED: 'CANCELLED',
                orchestrator_strategic_pb2.WORKFLOW_STATE_REPLANNING: 'REPLANNING',
            }

            status = {
                'workflow_id': response.workflow_id,
                'plan_id': response.plan_id,
                'state': state_map.get(response.state, 'UNKNOWN'),
                'current_priority': response.current_priority,
                'progress_percent': response.progress_percent,
                'started_at': response.started_at,
                'updated_at': response.updated_at,
                'metadata': dict(response.metadata)
            }

            if response.allocated_resources:
                status['allocated_resources'] = {
                    'cpu_millicores': response.allocated_resources.cpu_millicores,
                    'memory_mb': response.allocated_resources.memory_mb,
                    'max_parallel_tickets': response.allocated_resources.max_parallel_tickets,
                    'scheduling_priority': response.allocated_resources.scheduling_priority
                }

            if response.tickets:
                status['tickets'] = {
                    'total': response.tickets.total,
                    'completed': response.tickets.completed,
                    'pending': response.tickets.pending,
                    'running': response.tickets.running,
                    'failed': response.tickets.failed
                }

            if response.sla_deadline:
                status['sla_deadline'] = response.sla_deadline
            if response.sla_remaining_seconds:
                status['sla_remaining_seconds'] = response.sla_remaining_seconds

            if response.history:
                status['history'] = [
                    {
                        'event_type': event.event_type,
                        'timestamp': event.timestamp,
                        'description': event.description,
                        'metadata': dict(event.metadata)
                    }
                    for event in response.history
                ]

            return status

        except grpc.RpcError as e:
            self.logger.error(
                'get_workflow_status_failed',
                workflow_id=workflow_id,
                error=str(e),
                code=e.code()
            )
            return None

    # =========================================================================
    # Métodos de compatibilidade com API anterior (deprecated)
    # =========================================================================

    async def adjust_qos(self, adjustment) -> bool:
        """
        Enviar ajuste de QoS.

        DEPRECATED: Use adjust_priorities() para ajustes de prioridade.
        """
        self.logger.warning('adjust_qos_deprecated', message='Use adjust_priorities()')
        return await self.adjust_priorities(
            workflow_id=adjustment.target_workflow_id,
            plan_id=adjustment.target_plan_id or '',
            new_priority=adjustment.parameters.get('priority', 5),
            reason=adjustment.reason,
            adjustment_id=adjustment.adjustment_id
        )

    async def start_workflow(self, workflow_id: str, payload: Optional[dict] = None) -> bool:
        """
        Iniciar workflow no Orchestrator.

        DEPRECATED: Use a API HTTP do Orchestrator para iniciar workflows.
        """
        self.logger.warning(
            'start_workflow_deprecated',
            message='Use API HTTP do Orchestrator'
        )
        return True

    async def signal_workflow(
        self,
        workflow_id: str,
        signal_name: str,
        input_payload: Optional[dict] = None
    ) -> bool:
        """
        Enviar sinal para workflow.

        DEPRECATED: Use pause_workflow/resume_workflow ou adjust_priorities.
        """
        self.logger.warning(
            'signal_workflow_deprecated',
            message='Use métodos específicos: pause_workflow, resume_workflow, adjust_priorities'
        )

        if signal_name.lower() == 'pause':
            return await self.pause_workflow(
                workflow_id=workflow_id,
                reason=input_payload.get('reason', 'Signal via deprecated API') if input_payload else 'Signal via deprecated API'
            )
        elif signal_name.lower() == 'resume':
            return await self.resume_workflow(workflow_id=workflow_id)
        else:
            self.logger.info(
                'orchestrator_workflow_signal',
                workflow_id=workflow_id,
                signal=signal_name
            )
            return True
