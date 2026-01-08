"""
Testes de integração para OrchestratorStrategicServicer gRPC

Valida implementação do servidor gRPC que recebe comandos estratégicos da Queen Agent:
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

from src.grpc_server.orchestrator_servicer import OrchestratorStrategicServicer
from src.proto import orchestrator_strategic_pb2, orchestrator_strategic_pb2_grpc


def get_free_port() -> int:
    """Obtém uma porta livre para o servidor gRPC"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


@pytest.fixture
def mock_temporal_client():
    """Mock do cliente Temporal"""
    client = AsyncMock()
    client.signal_workflow = AsyncMock(return_value=True)
    client.cancel_workflow = AsyncMock(return_value=True)
    return client


@pytest.fixture
def mock_intelligent_scheduler():
    """Mock do IntelligentScheduler"""
    scheduler = AsyncMock()
    scheduler.update_workflow_priority = AsyncMock(return_value=True)
    scheduler.reallocate_resources = AsyncMock(return_value={
        'success': True,
        'workflow_id': 'wf-001',
        'message': 'Recursos realocados com sucesso'
    })
    scheduler.get_workflow_allocation = AsyncMock(return_value={
        'cpu_millicores': 2000,
        'memory_mb': 4096,
        'max_parallel_tickets': 20,
        'scheduling_priority': 5
    })
    return scheduler


@pytest.fixture
def mock_opa_client():
    """Mock do cliente OPA"""
    client = AsyncMock()
    client.evaluate_policy = AsyncMock(return_value={'allow': True, 'violations': []})
    return client


@pytest.fixture
def mock_mongodb_client():
    """Mock do cliente MongoDB para auditoria"""
    client = AsyncMock()
    client.db = MagicMock()
    client.db.strategic_adjustments = MagicMock()
    client.db.strategic_adjustments.insert_one = AsyncMock()
    return client


@pytest.fixture
def mock_kafka_producer():
    """Mock do Kafka producer"""
    producer = AsyncMock()
    producer.send_and_wait = AsyncMock()
    return producer


@pytest.fixture
def mock_config():
    """Mock de configuração"""
    config = MagicMock()
    config.KAFKA_TOPICS_STRATEGIC = 'strategic.adjustments'
    return config


@pytest.fixture
def servicer(
    mock_temporal_client,
    mock_intelligent_scheduler,
    mock_opa_client,
    mock_mongodb_client,
    mock_kafka_producer,
    mock_config
):
    """Instância do servicer com mocks"""
    return OrchestratorStrategicServicer(
        temporal_client=mock_temporal_client,
        intelligent_scheduler=mock_intelligent_scheduler,
        opa_client=mock_opa_client,
        mongodb_client=mock_mongodb_client,
        kafka_producer=mock_kafka_producer,
        config=mock_config
    )


@pytest.fixture
async def grpc_server_and_stub(
    mock_temporal_client,
    mock_intelligent_scheduler,
    mock_opa_client,
    mock_mongodb_client,
    mock_kafka_producer,
    mock_config
):
    """
    Fixture que inicia um servidor gRPC real em porta efêmera
    e retorna o stub para chamadas de cliente.
    """
    port = get_free_port()
    server = aio.server()

    servicer = OrchestratorStrategicServicer(
        temporal_client=mock_temporal_client,
        intelligent_scheduler=mock_intelligent_scheduler,
        opa_client=mock_opa_client,
        mongodb_client=mock_mongodb_client,
        kafka_producer=mock_kafka_producer,
        config=mock_config
    )

    orchestrator_strategic_pb2_grpc.add_OrchestratorStrategicServicer_to_server(servicer, server)
    server.add_insecure_port(f'[::]:{port}')
    await server.start()

    channel = aio.insecure_channel(f'localhost:{port}')
    stub = orchestrator_strategic_pb2_grpc.OrchestratorStrategicStub(channel)

    yield {
        'server': server,
        'channel': channel,
        'stub': stub,
        'servicer': servicer,
        'temporal_client': mock_temporal_client,
        'intelligent_scheduler': mock_intelligent_scheduler,
        'opa_client': mock_opa_client,
        'mongodb_client': mock_mongodb_client,
        'kafka_producer': mock_kafka_producer
    }

    await channel.close()
    await server.stop(grace=0)


@pytest.fixture
def mock_context():
    """Mock do contexto gRPC com metadata"""
    context = MagicMock()
    context.set_code = MagicMock()
    context.set_details = MagicMock()
    context.invocation_metadata = MagicMock(return_value=[
        ('traceparent', '00-trace123-span456-01'),
        ('x-correlation-id', 'corr-789')
    ])
    return context


# =============================================================================
# TESTES: AdjustPriorities
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_adjust_priorities_success(servicer, mock_intelligent_scheduler, mock_context):
    """
    Teste: ajuste de prioridade bem-sucedido
    """
    request = orchestrator_strategic_pb2.AdjustPrioritiesRequest(
        workflow_id='wf-001',
        plan_id='plan-001',
        new_priority=9,
        reason='Urgência alta',
        adjustment_id='adj-001'
    )

    response = await servicer.AdjustPriorities(request, mock_context)

    assert response.success is True
    assert response.applied_priority == 9
    mock_intelligent_scheduler.update_workflow_priority.assert_called_once()
    mock_context.set_code.assert_not_called()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_adjust_priorities_opa_denied(servicer, mock_opa_client, mock_context):
    """
    Teste: ajuste negado por OPA
    """
    mock_opa_client.evaluate_policy.return_value = {
        'allow': False,
        'violations': [{'rule': 'priority_limit', 'message': 'Prioridade excede limite'}]
    }

    request = orchestrator_strategic_pb2.AdjustPrioritiesRequest(
        workflow_id='wf-001',
        plan_id='plan-001',
        new_priority=11,
        reason='Teste negação OPA',
        adjustment_id='adj-002'
    )

    response = await servicer.AdjustPriorities(request, mock_context)

    assert response.success is False
    mock_context.set_code.assert_called_once_with(grpc.StatusCode.PERMISSION_DENIED)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_adjust_priorities_via_stub(grpc_server_and_stub):
    """
    Teste E2E: ajuste de prioridade via stub
    """
    stub = grpc_server_and_stub['stub']
    intelligent_scheduler = grpc_server_and_stub['intelligent_scheduler']

    request = orchestrator_strategic_pb2.AdjustPrioritiesRequest(
        workflow_id='wf-001',
        plan_id='plan-001',
        new_priority=8,
        reason='Teste via stub',
        adjustment_id='adj-003'
    )

    response = await stub.AdjustPriorities(request)

    assert response.success is True
    assert response.applied_priority == 8
    intelligent_scheduler.update_workflow_priority.assert_called_once()


# =============================================================================
# TESTES: RebalanceResources
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rebalance_resources_success(servicer, mock_intelligent_scheduler, mock_context):
    """
    Teste: rebalanceamento de recursos bem-sucedido
    """
    allocation = orchestrator_strategic_pb2.ResourceAllocation(
        cpu_millicores=3000,
        memory_mb=8192,
        max_parallel_tickets=30,
        scheduling_priority=9
    )

    request = orchestrator_strategic_pb2.RebalanceResourcesRequest(
        workflow_ids=['wf-001'],
        target_allocation={'wf-001': allocation},
        reason='Aumentar capacidade',
        rebalance_id='reb-001'
    )

    response = await servicer.RebalanceResources(request, mock_context)

    assert response.success is True
    assert len(response.results) == 1
    assert response.results[0].workflow_id == 'wf-001'
    assert response.results[0].success is True
    mock_context.set_code.assert_not_called()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rebalance_resources_multiple_workflows(servicer, mock_context):
    """
    Teste: rebalanceamento para múltiplos workflows
    """
    alloc1 = orchestrator_strategic_pb2.ResourceAllocation(cpu_millicores=2000, memory_mb=4096)
    alloc2 = orchestrator_strategic_pb2.ResourceAllocation(cpu_millicores=3000, memory_mb=8192)

    request = orchestrator_strategic_pb2.RebalanceResourcesRequest(
        workflow_ids=['wf-001', 'wf-002'],
        target_allocation={'wf-001': alloc1, 'wf-002': alloc2},
        reason='Rebalanceamento em massa',
        rebalance_id='reb-002',
        force=True
    )

    response = await servicer.RebalanceResources(request, mock_context)

    assert response.success is True
    assert len(response.results) == 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rebalance_resources_via_stub(grpc_server_and_stub):
    """
    Teste E2E: rebalanceamento via stub
    """
    stub = grpc_server_and_stub['stub']

    allocation = orchestrator_strategic_pb2.ResourceAllocation(
        cpu_millicores=4000,
        memory_mb=16384
    )

    request = orchestrator_strategic_pb2.RebalanceResourcesRequest(
        workflow_ids=['wf-001'],
        target_allocation={'wf-001': allocation},
        reason='Teste via stub',
        rebalance_id='reb-003'
    )

    response = await stub.RebalanceResources(request)

    assert response.success is True
    assert len(response.results) == 1


# =============================================================================
# TESTES: PauseWorkflow
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pause_workflow_success(servicer, mock_temporal_client, mock_context):
    """
    Teste: pausar workflow bem-sucedido
    """
    request = orchestrator_strategic_pb2.PauseWorkflowRequest(
        workflow_id='wf-001',
        reason='Manutenção programada',
        adjustment_id='adj-pause-001'
    )

    response = await servicer.PauseWorkflow(request, mock_context)

    assert response.success is True
    assert response.paused_at > 0
    mock_temporal_client.signal_workflow.assert_called_once()
    mock_context.set_code.assert_not_called()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pause_workflow_with_duration(servicer, mock_context):
    """
    Teste: pausar workflow com duração definida
    """
    request = orchestrator_strategic_pb2.PauseWorkflowRequest(
        workflow_id='wf-001',
        reason='Pausa temporária',
        pause_duration_seconds=3600,
        adjustment_id='adj-pause-002'
    )

    response = await servicer.PauseWorkflow(request, mock_context)

    assert response.success is True
    assert response.scheduled_resume_at is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pause_workflow_via_stub(grpc_server_and_stub):
    """
    Teste E2E: pausar workflow via stub
    """
    stub = grpc_server_and_stub['stub']
    temporal_client = grpc_server_and_stub['temporal_client']

    request = orchestrator_strategic_pb2.PauseWorkflowRequest(
        workflow_id='wf-001',
        reason='Teste via stub',
        adjustment_id='adj-pause-003'
    )

    response = await stub.PauseWorkflow(request)

    assert response.success is True
    temporal_client.signal_workflow.assert_called()


# =============================================================================
# TESTES: ResumeWorkflow
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_resume_workflow_success(servicer, mock_temporal_client, mock_context):
    """
    Teste: retomar workflow bem-sucedido
    """
    request = orchestrator_strategic_pb2.ResumeWorkflowRequest(
        workflow_id='wf-001',
        reason='Manutenção concluída',
        adjustment_id='adj-resume-001'
    )

    response = await servicer.ResumeWorkflow(request, mock_context)

    assert response.success is True
    assert response.resumed_at > 0
    mock_temporal_client.signal_workflow.assert_called()
    mock_context.set_code.assert_not_called()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_resume_workflow_via_stub(grpc_server_and_stub):
    """
    Teste E2E: retomar workflow via stub
    """
    stub = grpc_server_and_stub['stub']

    request = orchestrator_strategic_pb2.ResumeWorkflowRequest(
        workflow_id='wf-001',
        reason='Teste via stub',
        adjustment_id='adj-resume-002'
    )

    response = await stub.ResumeWorkflow(request)

    assert response.success is True


# =============================================================================
# TESTES: TriggerReplanning
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_trigger_replanning_success(servicer, mock_temporal_client, mock_context):
    """
    Teste: acionar replanejamento bem-sucedido
    """
    request = orchestrator_strategic_pb2.TriggerReplanningRequest(
        plan_id='plan-001',
        reason='SLA violation',
        trigger_type=orchestrator_strategic_pb2.TRIGGER_TYPE_SLA_VIOLATION,
        adjustment_id='adj-replan-001',
        preserve_progress=True,
        priority=8
    )

    response = await servicer.TriggerReplanning(request, mock_context)

    assert response.success is True
    assert response.replanning_id != ''
    assert response.triggered_at > 0
    mock_context.set_code.assert_not_called()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_trigger_replanning_with_context(servicer, mock_context):
    """
    Teste: acionar replanejamento com contexto adicional
    """
    request = orchestrator_strategic_pb2.TriggerReplanningRequest(
        plan_id='plan-002',
        reason='Drift detectado',
        trigger_type=orchestrator_strategic_pb2.TRIGGER_TYPE_DRIFT,
        adjustment_id='adj-replan-002',
        context={'drift_score': '0.15', 'affected_models': 'model-a'},
        preserve_progress=True,
        priority=7
    )

    response = await servicer.TriggerReplanning(request, mock_context)

    assert response.success is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_trigger_replanning_via_stub(grpc_server_and_stub):
    """
    Teste E2E: acionar replanejamento via stub
    """
    stub = grpc_server_and_stub['stub']

    request = orchestrator_strategic_pb2.TriggerReplanningRequest(
        plan_id='plan-001',
        reason='Teste via stub',
        trigger_type=orchestrator_strategic_pb2.TRIGGER_TYPE_STRATEGIC,
        adjustment_id='adj-replan-003'
    )

    response = await stub.TriggerReplanning(request)

    assert response.success is True
    assert response.replanning_id != ''


# =============================================================================
# TESTES: GetWorkflowStatus
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_workflow_status_success(servicer, mock_intelligent_scheduler, mock_context):
    """
    Teste: obter status de workflow bem-sucedido
    """
    request = orchestrator_strategic_pb2.GetWorkflowStatusRequest(
        workflow_id='wf-001'
    )

    response = await servicer.GetWorkflowStatus(request, mock_context)

    assert response.workflow_id == 'wf-001'
    assert response.current_priority >= 1
    mock_context.set_code.assert_not_called()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_workflow_status_via_stub(grpc_server_and_stub):
    """
    Teste E2E: obter status via stub
    """
    stub = grpc_server_and_stub['stub']

    request = orchestrator_strategic_pb2.GetWorkflowStatusRequest(
        workflow_id='wf-001',
        include_tickets=True
    )

    response = await stub.GetWorkflowStatus(request)

    assert response.workflow_id == 'wf-001'


# =============================================================================
# TESTES: Auditoria e Métricas
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_audit_logging_on_adjustment(servicer, mock_mongodb_client, mock_context):
    """
    Teste: verificar que ajustes são registrados no MongoDB
    """
    request = orchestrator_strategic_pb2.AdjustPrioritiesRequest(
        workflow_id='wf-001',
        plan_id='plan-001',
        new_priority=9,
        reason='Teste auditoria',
        adjustment_id='adj-audit-001'
    )

    await servicer.AdjustPriorities(request, mock_context)

    # Verificar que foi salvo no MongoDB
    mock_mongodb_client.db.strategic_adjustments.insert_one.assert_called()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_kafka_event_on_adjustment(servicer, mock_kafka_producer, mock_context):
    """
    Teste: verificar que ajustes são publicados no Kafka
    """
    request = orchestrator_strategic_pb2.AdjustPrioritiesRequest(
        workflow_id='wf-001',
        plan_id='plan-001',
        new_priority=9,
        reason='Teste Kafka',
        adjustment_id='adj-kafka-001'
    )

    await servicer.AdjustPriorities(request, mock_context)

    # Verificar que foi publicado no Kafka
    mock_kafka_producer.send_and_wait.assert_called()


# =============================================================================
# TESTES: Fluxo Completo E2E
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_strategic_adjustment_flow(grpc_server_and_stub):
    """
    Teste E2E: fluxo completo de ajustes estratégicos
    1. Obter status atual
    2. Ajustar prioridade
    3. Pausar workflow
    4. Retomar workflow
    5. Rebalancear recursos
    6. Acionar replanejamento
    """
    stub = grpc_server_and_stub['stub']

    workflow_id = 'wf-e2e-001'
    plan_id = 'plan-e2e-001'

    # 1. Obter status atual
    status_response = await stub.GetWorkflowStatus(
        orchestrator_strategic_pb2.GetWorkflowStatusRequest(workflow_id=workflow_id)
    )
    assert status_response.workflow_id == workflow_id

    # 2. Ajustar prioridade
    priority_response = await stub.AdjustPriorities(
        orchestrator_strategic_pb2.AdjustPrioritiesRequest(
            workflow_id=workflow_id,
            plan_id=plan_id,
            new_priority=10,
            reason='E2E test - alta prioridade',
            adjustment_id='adj-e2e-001'
        )
    )
    assert priority_response.success is True

    # 3. Pausar workflow
    pause_response = await stub.PauseWorkflow(
        orchestrator_strategic_pb2.PauseWorkflowRequest(
            workflow_id=workflow_id,
            reason='E2E test - pausa',
            adjustment_id='adj-e2e-002'
        )
    )
    assert pause_response.success is True

    # 4. Retomar workflow
    resume_response = await stub.ResumeWorkflow(
        orchestrator_strategic_pb2.ResumeWorkflowRequest(
            workflow_id=workflow_id,
            reason='E2E test - retomar',
            adjustment_id='adj-e2e-003'
        )
    )
    assert resume_response.success is True

    # 5. Rebalancear recursos
    allocation = orchestrator_strategic_pb2.ResourceAllocation(
        cpu_millicores=4000,
        memory_mb=16384,
        max_parallel_tickets=50
    )
    rebalance_response = await stub.RebalanceResources(
        orchestrator_strategic_pb2.RebalanceResourcesRequest(
            workflow_ids=[workflow_id],
            target_allocation={workflow_id: allocation},
            reason='E2E test - rebalanceamento',
            rebalance_id='reb-e2e-001'
        )
    )
    assert rebalance_response.success is True

    # 6. Acionar replanejamento
    replanning_response = await stub.TriggerReplanning(
        orchestrator_strategic_pb2.TriggerReplanningRequest(
            plan_id=plan_id,
            reason='E2E test - replanejamento',
            trigger_type=orchestrator_strategic_pb2.TRIGGER_TYPE_STRATEGIC,
            adjustment_id='adj-e2e-004'
        )
    )
    assert replanning_response.success is True
    assert replanning_response.replanning_id != ''
