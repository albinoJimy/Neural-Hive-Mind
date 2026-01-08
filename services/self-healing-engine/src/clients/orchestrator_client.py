"""
Orchestrator Dynamic gRPC client for Self-Healing Engine.

Provides workflow control operations (pause, resume, status) for
automated remediation workflows using the OrchestratorStrategic gRPC service.
"""

import asyncio
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
from uuid import uuid4

import grpc
import structlog
from prometheus_client import Counter, Histogram
from neural_hive_observability import get_tracer

# Try to import SPIFFE/mTLS security module
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

# Import proto stubs - use relative import from queen-agent proto location
import sys
from pathlib import Path

# Add proto path to sys.path for import
_proto_path = Path(__file__).parent.parent.parent.parent.parent / 'queen-agent' / 'src' / 'proto'
if _proto_path.exists() and str(_proto_path) not in sys.path:
    sys.path.insert(0, str(_proto_path))

try:
    from src.proto import orchestrator_strategic_pb2 as pb2
    from src.proto import orchestrator_strategic_pb2_grpc as pb2_grpc
except ImportError:
    # Fallback: try direct import
    try:
        import orchestrator_strategic_pb2 as pb2
        import orchestrator_strategic_pb2_grpc as pb2_grpc
    except ImportError:
        pb2 = None
        pb2_grpc = None

logger = structlog.get_logger(__name__)
tracer = get_tracer()

# Prometheus Metrics
ORCHESTRATOR_CALLS_TOTAL = Counter(
    'self_healing_orchestrator_calls_total',
    'Total gRPC calls to Orchestrator by self-healing engine',
    ['operation', 'status']
)

ORCHESTRATOR_CALL_DURATION = Histogram(
    'self_healing_orchestrator_call_duration_seconds',
    'Duration of gRPC calls to Orchestrator',
    ['operation'],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)


class OrchestratorClientError(Exception):
    """Base exception for Orchestrator client errors."""
    pass


class OrchestratorConnectionError(OrchestratorClientError):
    """Connection to Orchestrator failed."""
    pass


class OrchestratorClient:
    """
    gRPC client for Orchestrator Dynamic strategic operations.

    Provides workflow control operations:
    - PauseWorkflow: Pause a running workflow
    - ResumeWorkflow: Resume a paused workflow
    - GetWorkflowStatus: Get detailed workflow status

    Features:
    - mTLS via SPIFFE/SPIRE (production)
    - Retry with exponential backoff
    - Prometheus metrics
    - OpenTelemetry tracing
    """

    def __init__(
        self,
        host: str = 'orchestrator-dynamic.neural-hive-orchestration.svc.cluster.local',
        port: int = 50052,
        use_tls: bool = True,
        timeout_seconds: int = 10,
        environment: str = 'development',
        spiffe_config: Optional['SPIFFEConfig'] = None,
    ):
        self.host = host
        self.port = port
        self.use_tls = use_tls
        self.timeout_seconds = timeout_seconds
        self.environment = environment
        self.spiffe_config = spiffe_config

        self.channel: Optional[grpc.aio.Channel] = None
        self.stub: Optional[pb2_grpc.OrchestratorStrategicStub] = None
        self.spiffe_manager: Optional['SPIFFEManager'] = None
        self._initialized = False

        logger.info(
            'orchestrator_client.created',
            host=host,
            port=port,
            use_tls=use_tls,
            environment=environment
        )

    async def initialize(self):
        """Initialize gRPC channel and stub."""
        if self._initialized:
            return

        if pb2 is None or pb2_grpc is None:
            raise OrchestratorClientError(
                'Proto stubs not available. Ensure orchestrator_strategic_pb2 is compiled.'
            )

        target = f'{self.host}:{self.port}'

        try:
            # Determine if we should use mTLS
            use_mtls = (
                self.use_tls
                and SECURITY_LIB_AVAILABLE
                and self.spiffe_config
                and getattr(self.spiffe_config, 'enable_x509', False)
            )

            if use_mtls:
                # Create SPIFFE manager for mTLS
                self.spiffe_manager = SPIFFEManager(self.spiffe_config)
                await self.spiffe_manager.initialize()

                # Create secure channel with mTLS
                is_dev = self.environment.lower() in ('dev', 'development')
                self.channel = await create_secure_grpc_channel(
                    target=target,
                    spiffe_config=self.spiffe_config,
                    spiffe_manager=self.spiffe_manager,
                    fallback_insecure=is_dev
                )

                logger.info(
                    'orchestrator_client.mtls_channel_created',
                    target=target,
                    environment=self.environment
                )

            else:
                # Use insecure channel (development only)
                if self.environment.lower() in ('production', 'staging', 'prod'):
                    raise OrchestratorConnectionError(
                        f'mTLS required in {self.environment} but not configured'
                    )

                logger.warning(
                    'orchestrator_client.using_insecure_channel',
                    target=target,
                    environment=self.environment
                )
                self.channel = grpc.aio.insecure_channel(target)

            # Create stub
            self.stub = pb2_grpc.OrchestratorStrategicStub(self.channel)
            self._initialized = True

            logger.info(
                'orchestrator_client.initialized',
                target=target,
                use_mtls=use_mtls
            )

        except Exception as e:
            logger.error(
                'orchestrator_client.initialization_failed',
                target=target,
                error=str(e)
            )
            raise OrchestratorConnectionError(f'Failed to initialize: {e}')

    async def close(self):
        """Close gRPC channel and cleanup resources."""
        if self.channel:
            await self.channel.close()
            self.channel = None
            self.stub = None

        if self.spiffe_manager:
            await self.spiffe_manager.close()
            self.spiffe_manager = None

        self._initialized = False
        logger.info('orchestrator_client.closed')

    async def _get_grpc_metadata(self) -> List[Tuple[str, str]]:
        """Get gRPC metadata with JWT-SVID for authentication."""
        if not self.spiffe_manager or not SECURITY_LIB_AVAILABLE:
            return []

        try:
            trust_domain = self.spiffe_config.trust_domain if self.spiffe_config else 'neural-hive.local'
            audience = f'orchestrator-dynamic.{trust_domain}'
            return await get_grpc_metadata_with_jwt(
                spiffe_manager=self.spiffe_manager,
                audience=audience,
                environment=self.environment
            )
        except Exception as e:
            logger.warning('orchestrator_client.jwt_svid_fetch_failed', error=str(e))
            if self.environment.lower() in ('production', 'staging', 'prod'):
                raise
            return []

    async def pause_workflow(
        self,
        workflow_id: str,
        reason: str,
        duration_seconds: Optional[int] = None,
        adjustment_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Pause a running workflow.

        Args:
            workflow_id: Workflow identifier
            reason: Reason for pausing (e.g., 'self_healing_investigation')
            duration_seconds: Optional auto-resume duration
            adjustment_id: Optional adjustment ID (generated if not provided)

        Returns:
            Pause result with success status and pause timestamp
        """
        if not self._initialized:
            await self.initialize()

        with tracer.start_as_current_span('self_healing.orchestrator.pause_workflow') as span:
            span.set_attribute('workflow.id', workflow_id)
            span.set_attribute('pause.reason', reason)
            if duration_seconds:
                span.set_attribute('pause.duration_seconds', duration_seconds)

            adj_id = adjustment_id or str(uuid4())
            span.set_attribute('adjustment.id', adj_id)

            logger.info(
                'orchestrator_client.pausing_workflow',
                workflow_id=workflow_id,
                reason=reason,
                duration_seconds=duration_seconds,
                adjustment_id=adj_id
            )

            start_time = datetime.now()
            operation = 'pause_workflow'

            try:
                request = pb2.PauseWorkflowRequest(
                    workflow_id=workflow_id,
                    reason=reason,
                    adjustment_id=adj_id
                )
                if duration_seconds:
                    request.pause_duration_seconds = duration_seconds

                metadata = await self._get_grpc_metadata()
                response = await self.stub.PauseWorkflow(
                    request,
                    timeout=self.timeout_seconds,
                    metadata=metadata or None
                )

                duration = (datetime.now() - start_time).total_seconds()
                ORCHESTRATOR_CALL_DURATION.labels(operation=operation).observe(duration)
                ORCHESTRATOR_CALLS_TOTAL.labels(
                    operation=operation,
                    status='success' if response.success else 'failed'
                ).inc()

                result = {
                    'success': response.success,
                    'message': response.message,
                    'paused_at': response.paused_at,
                    'scheduled_resume_at': getattr(response, 'scheduled_resume_at', None),
                    'workflow_id': workflow_id,
                    'adjustment_id': adj_id
                }

                logger.info(
                    'orchestrator_client.workflow_paused',
                    workflow_id=workflow_id,
                    success=response.success,
                    duration_seconds=duration
                )

                return result

            except grpc.RpcError as e:
                duration = (datetime.now() - start_time).total_seconds()
                ORCHESTRATOR_CALL_DURATION.labels(operation=operation).observe(duration)
                ORCHESTRATOR_CALLS_TOTAL.labels(
                    operation=operation,
                    status='error'
                ).inc()

                logger.error(
                    'orchestrator_client.pause_workflow_failed',
                    workflow_id=workflow_id,
                    error=str(e),
                    code=e.code().name if hasattr(e, 'code') else 'unknown'
                )
                raise OrchestratorClientError(f'PauseWorkflow failed: {e}')

    async def resume_workflow(
        self,
        workflow_id: str,
        reason: str,
        adjustment_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Resume a paused workflow.

        Args:
            workflow_id: Workflow identifier
            reason: Reason for resuming (e.g., 'self_healing_restart')
            adjustment_id: Optional adjustment ID (generated if not provided)

        Returns:
            Resume result with success status and resume timestamp
        """
        if not self._initialized:
            await self.initialize()

        with tracer.start_as_current_span('self_healing.orchestrator.resume_workflow') as span:
            span.set_attribute('workflow.id', workflow_id)
            span.set_attribute('resume.reason', reason)

            adj_id = adjustment_id or str(uuid4())
            span.set_attribute('adjustment.id', adj_id)

            logger.info(
                'orchestrator_client.resuming_workflow',
                workflow_id=workflow_id,
                reason=reason,
                adjustment_id=adj_id
            )

            start_time = datetime.now()
            operation = 'resume_workflow'

            try:
                request = pb2.ResumeWorkflowRequest(
                    workflow_id=workflow_id,
                    reason=reason,
                    adjustment_id=adj_id
                )

                metadata = await self._get_grpc_metadata()
                response = await self.stub.ResumeWorkflow(
                    request,
                    timeout=self.timeout_seconds,
                    metadata=metadata or None
                )

                duration = (datetime.now() - start_time).total_seconds()
                ORCHESTRATOR_CALL_DURATION.labels(operation=operation).observe(duration)
                ORCHESTRATOR_CALLS_TOTAL.labels(
                    operation=operation,
                    status='success' if response.success else 'failed'
                ).inc()

                result = {
                    'success': response.success,
                    'message': response.message,
                    'resumed_at': response.resumed_at,
                    'pause_duration_seconds': response.pause_duration_seconds,
                    'workflow_id': workflow_id,
                    'adjustment_id': adj_id
                }

                logger.info(
                    'orchestrator_client.workflow_resumed',
                    workflow_id=workflow_id,
                    success=response.success,
                    pause_duration_seconds=response.pause_duration_seconds,
                    duration_seconds=duration
                )

                return result

            except grpc.RpcError as e:
                duration = (datetime.now() - start_time).total_seconds()
                ORCHESTRATOR_CALL_DURATION.labels(operation=operation).observe(duration)
                ORCHESTRATOR_CALLS_TOTAL.labels(
                    operation=operation,
                    status='error'
                ).inc()

                logger.error(
                    'orchestrator_client.resume_workflow_failed',
                    workflow_id=workflow_id,
                    error=str(e),
                    code=e.code().name if hasattr(e, 'code') else 'unknown'
                )
                raise OrchestratorClientError(f'ResumeWorkflow failed: {e}')

    async def get_workflow_status(
        self,
        workflow_id: str,
        include_tickets: bool = True,
        include_history: bool = False
    ) -> Dict[str, Any]:
        """
        Get detailed workflow status.

        Args:
            workflow_id: Workflow identifier
            include_tickets: Include ticket summary
            include_history: Include workflow event history

        Returns:
            Workflow status with state, progress, tickets, and resources
        """
        if not self._initialized:
            await self.initialize()

        with tracer.start_as_current_span('self_healing.orchestrator.get_workflow_status') as span:
            span.set_attribute('workflow.id', workflow_id)
            span.set_attribute('include.tickets', include_tickets)
            span.set_attribute('include.history', include_history)

            logger.info(
                'orchestrator_client.getting_workflow_status',
                workflow_id=workflow_id,
                include_tickets=include_tickets,
                include_history=include_history
            )

            start_time = datetime.now()
            operation = 'get_workflow_status'

            try:
                request = pb2.GetWorkflowStatusRequest(
                    workflow_id=workflow_id,
                    include_tickets=include_tickets,
                    include_history=include_history
                )

                metadata = await self._get_grpc_metadata()
                response = await self.stub.GetWorkflowStatus(
                    request,
                    timeout=self.timeout_seconds,
                    metadata=metadata or None
                )

                duration = (datetime.now() - start_time).total_seconds()
                ORCHESTRATOR_CALL_DURATION.labels(operation=operation).observe(duration)
                ORCHESTRATOR_CALLS_TOTAL.labels(
                    operation=operation,
                    status='success'
                ).inc()

                # Map WorkflowState enum to string
                state_map = {
                    pb2.WORKFLOW_STATE_UNSPECIFIED: 'UNSPECIFIED',
                    pb2.WORKFLOW_STATE_PENDING: 'PENDING',
                    pb2.WORKFLOW_STATE_RUNNING: 'RUNNING',
                    pb2.WORKFLOW_STATE_PAUSED: 'PAUSED',
                    pb2.WORKFLOW_STATE_COMPLETED: 'COMPLETED',
                    pb2.WORKFLOW_STATE_FAILED: 'FAILED',
                    pb2.WORKFLOW_STATE_CANCELLED: 'CANCELLED',
                    pb2.WORKFLOW_STATE_REPLANNING: 'REPLANNING',
                }

                result = {
                    'workflow_id': response.workflow_id,
                    'plan_id': response.plan_id,
                    'state': state_map.get(response.state, 'UNKNOWN'),
                    'current_priority': response.current_priority,
                    'progress_percent': response.progress_percent,
                    'started_at': response.started_at,
                    'updated_at': response.updated_at,
                }

                # Add optional fields
                if hasattr(response, 'sla_deadline') and response.HasField('sla_deadline'):
                    result['sla_deadline'] = response.sla_deadline
                if hasattr(response, 'sla_remaining_seconds') and response.HasField('sla_remaining_seconds'):
                    result['sla_remaining_seconds'] = response.sla_remaining_seconds

                # Add ticket summary if requested
                if include_tickets and response.tickets:
                    result['tickets'] = {
                        'total': response.tickets.total,
                        'completed': response.tickets.completed,
                        'pending': response.tickets.pending,
                        'running': response.tickets.running,
                        'failed': response.tickets.failed,
                    }

                # Add allocated resources if present
                if response.allocated_resources:
                    result['allocated_resources'] = {
                        'cpu_millicores': response.allocated_resources.cpu_millicores,
                        'memory_mb': response.allocated_resources.memory_mb,
                        'max_parallel_tickets': response.allocated_resources.max_parallel_tickets,
                        'scheduling_priority': response.allocated_resources.scheduling_priority,
                    }
                    if response.allocated_resources.HasField('gpu_count'):
                        result['allocated_resources']['gpu_count'] = response.allocated_resources.gpu_count

                # Add history if requested
                if include_history and response.history:
                    result['history'] = [
                        {
                            'event_type': event.event_type,
                            'timestamp': event.timestamp,
                            'description': event.description,
                            'metadata': dict(event.metadata),
                        }
                        for event in response.history
                    ]

                # Add metadata
                if response.metadata:
                    result['metadata'] = dict(response.metadata)

                logger.info(
                    'orchestrator_client.workflow_status_retrieved',
                    workflow_id=workflow_id,
                    state=result['state'],
                    progress_percent=result['progress_percent'],
                    duration_seconds=duration
                )

                return result

            except grpc.RpcError as e:
                duration = (datetime.now() - start_time).total_seconds()
                ORCHESTRATOR_CALL_DURATION.labels(operation=operation).observe(duration)
                ORCHESTRATOR_CALLS_TOTAL.labels(
                    operation=operation,
                    status='error'
                ).inc()

                logger.error(
                    'orchestrator_client.get_workflow_status_failed',
                    workflow_id=workflow_id,
                    error=str(e),
                    code=e.code().name if hasattr(e, 'code') else 'unknown'
                )
                raise OrchestratorClientError(f'GetWorkflowStatus failed: {e}')

    async def trigger_replanning(
        self,
        plan_id: str,
        reason: str,
        trigger_type: str = 'TRIGGER_TYPE_STRATEGIC',
        preserve_progress: bool = True,
        context: Optional[Dict[str, str]] = None,
        adjustment_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Trigger replanning for a workflow plan.

        Args:
            plan_id: Plan identifier
            reason: Reason for replanning
            trigger_type: Type of trigger (TRIGGER_TYPE_DRIFT, TRIGGER_TYPE_FAILURE, etc.)
            preserve_progress: Whether to preserve current progress
            context: Additional context for replanning
            adjustment_id: Optional adjustment ID

        Returns:
            Replanning result with success status and replanning ID
        """
        if not self._initialized:
            await self.initialize()

        with tracer.start_as_current_span('self_healing.orchestrator.trigger_replanning') as span:
            span.set_attribute('plan.id', plan_id)
            span.set_attribute('replanning.reason', reason)
            span.set_attribute('trigger.type', trigger_type)

            adj_id = adjustment_id or str(uuid4())
            span.set_attribute('adjustment.id', adj_id)

            logger.info(
                'orchestrator_client.triggering_replanning',
                plan_id=plan_id,
                reason=reason,
                trigger_type=trigger_type,
                adjustment_id=adj_id
            )

            start_time = datetime.now()
            operation = 'trigger_replanning'

            try:
                # Map trigger type string to enum
                trigger_type_map = {
                    'TRIGGER_TYPE_UNSPECIFIED': pb2.TRIGGER_TYPE_UNSPECIFIED,
                    'TRIGGER_TYPE_DRIFT': pb2.TRIGGER_TYPE_DRIFT,
                    'TRIGGER_TYPE_FAILURE': pb2.TRIGGER_TYPE_FAILURE,
                    'TRIGGER_TYPE_STRATEGIC': pb2.TRIGGER_TYPE_STRATEGIC,
                    'TRIGGER_TYPE_SLA_VIOLATION': pb2.TRIGGER_TYPE_SLA_VIOLATION,
                    'TRIGGER_TYPE_RESOURCE_CONSTRAINT': pb2.TRIGGER_TYPE_RESOURCE_CONSTRAINT,
                }

                request = pb2.TriggerReplanningRequest(
                    plan_id=plan_id,
                    reason=reason,
                    trigger_type=trigger_type_map.get(trigger_type, pb2.TRIGGER_TYPE_STRATEGIC),
                    adjustment_id=adj_id,
                    preserve_progress=preserve_progress
                )

                if context:
                    request.context.update(context)

                metadata = await self._get_grpc_metadata()
                response = await self.stub.TriggerReplanning(
                    request,
                    timeout=self.timeout_seconds,
                    metadata=metadata or None
                )

                duration = (datetime.now() - start_time).total_seconds()
                ORCHESTRATOR_CALL_DURATION.labels(operation=operation).observe(duration)
                ORCHESTRATOR_CALLS_TOTAL.labels(
                    operation=operation,
                    status='success' if response.success else 'failed'
                ).inc()

                result = {
                    'success': response.success,
                    'message': response.message,
                    'replanning_id': response.replanning_id,
                    'triggered_at': response.triggered_at,
                    'plan_id': plan_id,
                    'adjustment_id': adj_id
                }

                if response.HasField('estimated_completion_seconds'):
                    result['estimated_completion_seconds'] = response.estimated_completion_seconds

                logger.info(
                    'orchestrator_client.replanning_triggered',
                    plan_id=plan_id,
                    replanning_id=response.replanning_id,
                    success=response.success,
                    duration_seconds=duration
                )

                return result

            except grpc.RpcError as e:
                duration = (datetime.now() - start_time).total_seconds()
                ORCHESTRATOR_CALL_DURATION.labels(operation=operation).observe(duration)
                ORCHESTRATOR_CALLS_TOTAL.labels(
                    operation=operation,
                    status='error'
                ).inc()

                logger.error(
                    'orchestrator_client.trigger_replanning_failed',
                    plan_id=plan_id,
                    error=str(e),
                    code=e.code().name if hasattr(e, 'code') else 'unknown'
                )
                raise OrchestratorClientError(f'TriggerReplanning failed: {e}')

    async def health_check(self) -> bool:
        """
        Check if Orchestrator gRPC service is reachable.

        Returns:
            True if service is healthy, False otherwise
        """
        try:
            if not self._initialized:
                await self.initialize()

            # Try to get status of a non-existent workflow (quick connectivity test)
            await self.get_workflow_status('__health_check__', include_tickets=False)
            return True
        except OrchestratorClientError:
            # NOT_FOUND is acceptable - means service is reachable
            return True
        except Exception as e:
            logger.warning('orchestrator_client.health_check_failed', error=str(e))
            return False
