"""
Testes de integração para OrchestratorClient gRPC

Valida comunicação entre Queen Agent e Orchestrator Dynamic via gRPC:
- AdjustPriorities: ajuste de prioridade de workflows
- RebalanceResources: rebalanceamento de recursos
- PauseWorkflow: pausar workflow
- ResumeWorkflow: retomar workflow
- TriggerReplanning: acionar replanejamento
- GetWorkflowStatus: obter status de workflow
"""
import pytest
import asyncio
import socket
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import grpc
from grpc import aio

from src.clients.orchestrator_client import OrchestratorClient
from src.proto import orchestrator_strategic_pb2, orchestrator_strategic_pb2_grpc
from src.config import Settings


def get_free_port() -> int:
    """Obtém uma porta livre para o servidor gRPC"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


class MockOrchestratorStrategicServicer(orchestrator_strategic_pb2_grpc.OrchestratorStrategicServicer):
    """Servicer mock para testes de integração"""

    def __init__(self):
        self.adjust_priorities_calls = []
        self.rebalance_resources_calls = []
        self.pause_workflow_calls = []
        self.resume_workflow_calls = []
        self.trigger_replanning_calls = []
        self.get_workflow_status_calls = []

    async def AdjustPriorities(self, request, context):
        self.adjust_priorities_calls.append(request)
        return orchestrator_strategic_pb2.AdjustPrioritiesResponse(
            success=True,
            message=f"Prioridade ajustada para workflow {request.workflow_id}",
            previous_priority=5,
            applied_priority=request.new_priority,
            applied_at=int(datetime.now().timestamp() * 1000)
        )

    async def RebalanceResources(self, request, context):
        self.rebalance_resources_calls.append(request)
        results = []
        for workflow_id in request.workflow_ids:
            results.append(orchestrator_strategic_pb2.WorkflowRebalanceResult(
                workflow_id=workflow_id,
                success=True,
                message=f"Recursos rebalanceados para {workflow_id}"
            ))
        return orchestrator_strategic_pb2.RebalanceResourcesResponse(
            success=True,
            message="Rebalanceamento concluído",
            results=results,
            applied_at=int(datetime.now().timestamp() * 1000)
        )

    async def PauseWorkflow(self, request, context):
        self.pause_workflow_calls.append(request)
        return orchestrator_strategic_pb2.PauseWorkflowResponse(
            success=True,
            message=f"Workflow {request.workflow_id} pausado",
            paused_at=int(datetime.now().timestamp() * 1000)
        )

    async def ResumeWorkflow(self, request, context):
        self.resume_workflow_calls.append(request)
        return orchestrator_strategic_pb2.ResumeWorkflowResponse(
            success=True,
            message=f"Workflow {request.workflow_id} retomado",
            resumed_at=int(datetime.now().timestamp() * 1000),
            pause_duration_seconds=120
        )

    async def TriggerReplanning(self, request, context):
        self.trigger_replanning_calls.append(request)
        return orchestrator_strategic_pb2.TriggerReplanningResponse(
            success=True,
            message=f"Replanejamento acionado para plano {request.plan_id}",
            replanning_id=f"replan-{request.plan_id}",
            triggered_at=int(datetime.now().timestamp() * 1000),
            estimated_completion_seconds=60
        )

    async def GetWorkflowStatus(self, request, context):
        self.get_workflow_status_calls.append(request)
        return orchestrator_strategic_pb2.GetWorkflowStatusResponse(
            workflow_id=request.workflow_id,
            plan_id="plan-001",
            state=orchestrator_strategic_pb2.WORKFLOW_STATE_RUNNING,
            current_priority=7,
            allocated_resources=orchestrator_strategic_pb2.ResourceAllocation(
                cpu_millicores=2000,
                memory_mb=4096,
                max_parallel_tickets=20,
                scheduling_priority=7
            ),
            tickets=orchestrator_strategic_pb2.TicketSummary(
                total=100,
                completed=45,
                pending=30,
                running=20,
                failed=5
            ),
            progress_percent=45.0,
            started_at=int(datetime.now().timestamp() * 1000) - 3600000,
            updated_at=int(datetime.now().timestamp() * 1000)
        )


class MockFailingServicer(orchestrator_strategic_pb2_grpc.OrchestratorStrategicServicer):
    """Servicer mock que simula falhas"""

    async def AdjustPriorities(self, request, context):
        context.set_code(grpc.StatusCode.INTERNAL)
        context.set_details("Erro interno do Orchestrator")
        return orchestrator_strategic_pb2.AdjustPrioritiesResponse()

    async def PauseWorkflow(self, request, context):
        context.set_code(grpc.StatusCode.NOT_FOUND)
        context.set_details(f"Workflow {request.workflow_id} não encontrado")
        return orchestrator_strategic_pb2.PauseWorkflowResponse()


@pytest.fixture
def mock_settings():
    """Configurações mock para testes"""
    settings = MagicMock(spec=Settings)
    settings.ORCHESTRATOR_GRPC_HOST = 'localhost'
    settings.ORCHESTRATOR_GRPC_PORT = 50053
    settings.ORCHESTRATOR_GRPC_TIMEOUT = 10
    settings.SPIFFE_ENABLED = False
    settings.CIRCUIT_BREAKER_ENABLED = False
    settings.CIRCUIT_BREAKER_FAIL_MAX = 5
    settings.CIRCUIT_BREAKER_TIMEOUT = 60
    settings.CIRCUIT_BREAKER_RECOVERY_TIMEOUT = 30
    return settings


@pytest.fixture
async def grpc_server_and_client(mock_settings):
    """
    Fixture que inicia um servidor gRPC mock e retorna um cliente configurado
    """
    port = get_free_port()
    mock_settings.ORCHESTRATOR_GRPC_PORT = port

    server = aio.server()
    servicer = MockOrchestratorStrategicServicer()

    orchestrator_strategic_pb2_grpc.add_OrchestratorStrategicServicer_to_server(servicer, server)
    server.add_insecure_port(f'[::]:{port}')
    await server.start()

    # Criar cliente
    client = OrchestratorClient(mock_settings)
    await client.connect()

    yield {
        'server': server,
        'servicer': servicer,
        'client': client,
        'settings': mock_settings
    }

    await client.close()
    await server.stop(grace=0)


@pytest.fixture
async def grpc_failing_server_and_client(mock_settings):
    """
    Fixture que inicia um servidor gRPC que simula falhas
    """
    port = get_free_port()
    mock_settings.ORCHESTRATOR_GRPC_PORT = port

    server = aio.server()
    servicer = MockFailingServicer()

    orchestrator_strategic_pb2_grpc.add_OrchestratorStrategicServicer_to_server(servicer, server)
    server.add_insecure_port(f'[::]:{port}')
    await server.start()

    # Criar cliente
    client = OrchestratorClient(mock_settings)
    await client.connect()

    yield {
        'server': server,
        'servicer': servicer,
        'client': client,
        'settings': mock_settings
    }

    await client.close()
    await server.stop(grace=0)


# =============================================================================
# TESTES: AdjustPriorities
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_adjust_priorities_success(grpc_server_and_client):
    """
    Teste: ajuste de prioridade bem-sucedido
    """
    client = grpc_server_and_client['client']
    servicer = grpc_server_and_client['servicer']

    success = await client.adjust_priorities(
        workflow_id='wf-001',
        plan_id='plan-001',
        new_priority=9,
        reason='Urgência alta'
    )

    assert success is True
    assert len(servicer.adjust_priorities_calls) == 1
    call = servicer.adjust_priorities_calls[0]
    assert call.workflow_id == 'wf-001'
    assert call.plan_id == 'plan-001'
    assert call.new_priority == 9
    assert call.reason == 'Urgência alta'


@pytest.mark.integration
@pytest.mark.asyncio
async def test_adjust_priorities_with_metadata(grpc_server_and_client):
    """
    Teste: ajuste de prioridade com metadata
    """
    client = grpc_server_and_client['client']
    servicer = grpc_server_and_client['servicer']

    success = await client.adjust_priorities(
        workflow_id='wf-002',
        plan_id='plan-002',
        new_priority=8,
        reason='SLA violation',
        metadata={'decision_id': 'dec-123', 'source': 'queen-agent'}
    )

    assert success is True
    call = servicer.adjust_priorities_calls[0]
    assert call.metadata['decision_id'] == 'dec-123'
    assert call.metadata['source'] == 'queen-agent'


@pytest.mark.integration
@pytest.mark.asyncio
async def test_adjust_priorities_server_error(grpc_failing_server_and_client):
    """
    Teste: erro do servidor ao ajustar prioridade
    """
    client = grpc_failing_server_and_client['client']

    success = await client.adjust_priorities(
        workflow_id='wf-003',
        plan_id='plan-003',
        new_priority=7,
        reason='Test error'
    )

    assert success is False


# =============================================================================
# TESTES: RebalanceResources
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rebalance_resources_success(grpc_server_and_client):
    """
    Teste: rebalanceamento de recursos bem-sucedido
    """
    client = grpc_server_and_client['client']
    servicer = grpc_server_and_client['servicer']

    target_allocation = {
        'wf-001': {
            'cpu_millicores': 3000,
            'memory_mb': 8192,
            'max_parallel_tickets': 30,
            'scheduling_priority': 9
        }
    }

    result = await client.rebalance_resources(
        workflow_ids=['wf-001'],
        target_allocation=target_allocation,
        reason='Aumentar capacidade'
    )

    assert result['success'] is True
    assert len(servicer.rebalance_resources_calls) == 1
    call = servicer.rebalance_resources_calls[0]
    assert 'wf-001' in call.workflow_ids


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rebalance_resources_multiple_workflows(grpc_server_and_client):
    """
    Teste: rebalanceamento para múltiplos workflows
    """
    client = grpc_server_and_client['client']
    servicer = grpc_server_and_client['servicer']

    target_allocation = {
        'wf-001': {'cpu_millicores': 2000, 'memory_mb': 4096},
        'wf-002': {'cpu_millicores': 3000, 'memory_mb': 8192},
        'wf-003': {'cpu_millicores': 1000, 'memory_mb': 2048}
    }

    result = await client.rebalance_resources(
        workflow_ids=['wf-001', 'wf-002', 'wf-003'],
        target_allocation=target_allocation,
        reason='Rebalanceamento em massa',
        force=True
    )

    assert result['success'] is True
    assert len(result['results']) == 3
    call = servicer.rebalance_resources_calls[0]
    assert call.force is True


# =============================================================================
# TESTES: PauseWorkflow
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pause_workflow_success(grpc_server_and_client):
    """
    Teste: pausar workflow bem-sucedido
    """
    client = grpc_server_and_client['client']
    servicer = grpc_server_and_client['servicer']

    success = await client.pause_workflow(
        workflow_id='wf-001',
        reason='Manutenção programada'
    )

    assert success is True
    assert len(servicer.pause_workflow_calls) == 1
    call = servicer.pause_workflow_calls[0]
    assert call.workflow_id == 'wf-001'
    assert call.reason == 'Manutenção programada'


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pause_workflow_with_duration(grpc_server_and_client):
    """
    Teste: pausar workflow com duração definida
    """
    client = grpc_server_and_client['client']
    servicer = grpc_server_and_client['servicer']

    success = await client.pause_workflow(
        workflow_id='wf-002',
        reason='Pausa temporária',
        duration_seconds=3600
    )

    assert success is True
    call = servicer.pause_workflow_calls[0]
    assert call.pause_duration_seconds == 3600


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pause_workflow_not_found(grpc_failing_server_and_client):
    """
    Teste: workflow não encontrado
    """
    client = grpc_failing_server_and_client['client']

    success = await client.pause_workflow(
        workflow_id='wf-inexistente',
        reason='Test'
    )

    assert success is False


# =============================================================================
# TESTES: ResumeWorkflow
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_resume_workflow_success(grpc_server_and_client):
    """
    Teste: retomar workflow bem-sucedido
    """
    client = grpc_server_and_client['client']
    servicer = grpc_server_and_client['servicer']

    success = await client.resume_workflow(
        workflow_id='wf-001',
        reason='Manutenção concluída'
    )

    assert success is True
    assert len(servicer.resume_workflow_calls) == 1
    call = servicer.resume_workflow_calls[0]
    assert call.workflow_id == 'wf-001'
    assert call.reason == 'Manutenção concluída'


# =============================================================================
# TESTES: TriggerReplanning
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_trigger_replanning_success(grpc_server_and_client):
    """
    Teste: acionar replanejamento bem-sucedido
    """
    client = grpc_server_and_client['client']
    servicer = grpc_server_and_client['servicer']

    replanning_id = await client.trigger_replanning(
        plan_id='plan-001',
        reason='SLA violation',
        trigger_type='SLA_VIOLATION'
    )

    assert replanning_id is not None
    assert replanning_id == 'replan-plan-001'
    assert len(servicer.trigger_replanning_calls) == 1
    call = servicer.trigger_replanning_calls[0]
    assert call.plan_id == 'plan-001'
    assert call.trigger_type == orchestrator_strategic_pb2.TRIGGER_TYPE_SLA_VIOLATION


@pytest.mark.integration
@pytest.mark.asyncio
async def test_trigger_replanning_with_context(grpc_server_and_client):
    """
    Teste: acionar replanejamento com contexto adicional
    """
    client = grpc_server_and_client['client']
    servicer = grpc_server_and_client['servicer']

    replanning_id = await client.trigger_replanning(
        plan_id='plan-002',
        reason='Drift detectado',
        trigger_type='DRIFT',
        context={'drift_score': '0.15', 'affected_models': 'model-a,model-b'},
        preserve_progress=True,
        priority=8
    )

    assert replanning_id is not None
    call = servicer.trigger_replanning_calls[0]
    assert call.preserve_progress is True
    assert call.priority == 8
    assert call.context['drift_score'] == '0.15'


@pytest.mark.integration
@pytest.mark.asyncio
async def test_trigger_replanning_strategic(grpc_server_and_client):
    """
    Teste: acionar replanejamento estratégico
    """
    client = grpc_server_and_client['client']
    servicer = grpc_server_and_client['servicer']

    replanning_id = await client.trigger_replanning(
        plan_id='plan-003',
        reason='Decisão estratégica da Queen Agent',
        trigger_type='STRATEGIC'
    )

    assert replanning_id is not None
    call = servicer.trigger_replanning_calls[0]
    assert call.trigger_type == orchestrator_strategic_pb2.TRIGGER_TYPE_STRATEGIC


# =============================================================================
# TESTES: GetWorkflowStatus
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_workflow_status_success(grpc_server_and_client):
    """
    Teste: obter status de workflow bem-sucedido
    """
    client = grpc_server_and_client['client']
    servicer = grpc_server_and_client['servicer']

    status = await client.get_workflow_status(
        workflow_id='wf-001'
    )

    assert status is not None
    assert status['workflow_id'] == 'wf-001'
    assert status['state'] == 'RUNNING'
    assert status['current_priority'] == 7
    assert status['progress_percent'] == 45.0
    assert status['tickets']['total'] == 100
    assert status['tickets']['completed'] == 45


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_workflow_status_with_tickets(grpc_server_and_client):
    """
    Teste: obter status com detalhes de tickets
    """
    client = grpc_server_and_client['client']

    status = await client.get_workflow_status(
        workflow_id='wf-001',
        include_tickets=True
    )

    assert status is not None
    assert 'tickets' in status
    assert status['tickets']['running'] == 20
    assert status['tickets']['failed'] == 5


# =============================================================================
# TESTES: Conexão e Reconexão
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_client_connect_disconnect(mock_settings):
    """
    Teste: conectar e desconectar cliente
    """
    port = get_free_port()
    mock_settings.ORCHESTRATOR_GRPC_PORT = port

    server = aio.server()
    servicer = MockOrchestratorStrategicServicer()
    orchestrator_strategic_pb2_grpc.add_OrchestratorStrategicServicer_to_server(servicer, server)
    server.add_insecure_port(f'[::]:{port}')
    await server.start()

    client = OrchestratorClient(mock_settings)
    await client.connect()

    # Verificar que está conectado
    assert client._channel is not None
    assert client._stub is not None

    # Fechar conexão
    await client.close()

    # Verificar que está desconectado
    assert client._channel is None
    assert client._stub is None

    await server.stop(grace=0)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_client_connection_failure(mock_settings):
    """
    Teste: falha de conexão com servidor indisponível
    """
    mock_settings.ORCHESTRATOR_GRPC_PORT = 59999  # Porta sem servidor

    client = OrchestratorClient(mock_settings)
    await client.connect()

    # Tentar operação - deve falhar graciosamente
    success = await client.adjust_priorities(
        workflow_id='wf-001',
        plan_id='plan-001',
        new_priority=8,
        reason='Test'
    )

    assert success is False

    await client.close()


# =============================================================================
# TESTES: Fluxo Completo
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_workflow_management_flow(grpc_server_and_client):
    """
    Teste E2E: fluxo completo de gerenciamento de workflow
    1. Verificar status inicial
    2. Ajustar prioridade
    3. Pausar workflow
    4. Retomar workflow
    5. Rebalancear recursos
    6. Acionar replanejamento
    """
    client = grpc_server_and_client['client']
    servicer = grpc_server_and_client['servicer']

    workflow_id = 'wf-e2e-001'
    plan_id = 'plan-e2e-001'

    # 1. Verificar status inicial
    status = await client.get_workflow_status(workflow_id)
    assert status is not None
    assert status['state'] == 'RUNNING'

    # 2. Ajustar prioridade
    priority_success = await client.adjust_priorities(
        workflow_id=workflow_id,
        plan_id=plan_id,
        new_priority=10,
        reason='E2E test - alta prioridade'
    )
    assert priority_success is True

    # 3. Pausar workflow
    pause_success = await client.pause_workflow(
        workflow_id=workflow_id,
        reason='E2E test - pausa'
    )
    assert pause_success is True

    # 4. Retomar workflow
    resume_success = await client.resume_workflow(
        workflow_id=workflow_id,
        reason='E2E test - retomar'
    )
    assert resume_success is True

    # 5. Rebalancear recursos
    rebalance_result = await client.rebalance_resources(
        workflow_ids=[workflow_id],
        target_allocation={
            workflow_id: {
                'cpu_millicores': 4000,
                'memory_mb': 16384,
                'max_parallel_tickets': 50
            }
        },
        reason='E2E test - rebalanceamento'
    )
    assert rebalance_result['success'] is True

    # 6. Acionar replanejamento
    replanning_id = await client.trigger_replanning(
        plan_id=plan_id,
        reason='E2E test - replanejamento',
        trigger_type='STRATEGIC'
    )
    assert replanning_id is not None

    # Validar que todas as chamadas foram feitas
    assert len(servicer.get_workflow_status_calls) == 1
    assert len(servicer.adjust_priorities_calls) == 1
    assert len(servicer.pause_workflow_calls) == 1
    assert len(servicer.resume_workflow_calls) == 1
    assert len(servicer.rebalance_resources_calls) == 1
    assert len(servicer.trigger_replanning_calls) == 1
