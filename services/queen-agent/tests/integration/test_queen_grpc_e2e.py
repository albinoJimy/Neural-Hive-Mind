"""
Testes de integração E2E para o Queen Agent gRPC

Valida fluxo completo dos métodos gRPC com servidor real:
- GetStrategicDecision: busca decisão no MongoDB
- ListStrategicDecisions: lista decisões com filtros e paginação
- GetSystemStatus: agrega métricas do Prometheus
- GetActiveConflicts: consulta conflitos no Neo4j
- MakeStrategicDecision: cria nova decisão estratégica
"""
import pytest
import asyncio
import uuid
import socket
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import grpc
from grpc import aio

from src.grpc_server.queen_servicer import QueenAgentServicer
from src.proto import queen_agent_pb2, queen_agent_pb2_grpc


def get_free_port() -> int:
    """Obtém uma porta livre para o servidor gRPC"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


@pytest.fixture
def mock_mongodb_client():
    """Mock do cliente MongoDB com comportamento realista"""
    client = AsyncMock()
    client.db = MagicMock()
    client.db.analyst_insights = MagicMock()
    client.db.analyst_insights.insert_one = AsyncMock()
    client.client = MagicMock()
    client.client.admin = MagicMock()
    client.client.admin.command = AsyncMock(return_value={'ok': 1})
    return client


@pytest.fixture
def mock_neo4j_client():
    """Mock do cliente Neo4j com comportamento realista"""
    client = AsyncMock()
    client.driver = MagicMock()
    client.driver.verify_connectivity = AsyncMock()
    return client


@pytest.fixture
def mock_redis_client():
    """Mock do cliente Redis com comportamento realista"""
    client = AsyncMock()
    client.client = MagicMock()
    client.client.ping = AsyncMock(return_value=True)
    return client


@pytest.fixture
def mock_telemetry_aggregator():
    """Mock do TelemetryAggregator com comportamento realista"""
    return AsyncMock()


@pytest.fixture
def mock_exception_service():
    """Mock do ExceptionApprovalService"""
    return AsyncMock()


@pytest.fixture
def mock_decision_engine():
    """Mock do StrategicDecisionEngine"""
    return AsyncMock()


@pytest.fixture
def servicer(mock_mongodb_client, mock_neo4j_client, mock_exception_service, mock_telemetry_aggregator, mock_decision_engine):
    """Instância do servicer com mocks"""
    return QueenAgentServicer(
        mongodb_client=mock_mongodb_client,
        neo4j_client=mock_neo4j_client,
        exception_service=mock_exception_service,
        telemetry_aggregator=mock_telemetry_aggregator,
        decision_engine=mock_decision_engine
    )


@pytest.fixture
async def grpc_server_and_stub(mock_mongodb_client, mock_neo4j_client, mock_exception_service, mock_telemetry_aggregator, mock_decision_engine):
    """
    Fixture que inicia um servidor gRPC real em porta efêmera
    e retorna o stub para chamadas de cliente.
    """
    port = get_free_port()
    server = aio.server()

    servicer = QueenAgentServicer(
        mongodb_client=mock_mongodb_client,
        neo4j_client=mock_neo4j_client,
        exception_service=mock_exception_service,
        telemetry_aggregator=mock_telemetry_aggregator,
        decision_engine=mock_decision_engine
    )

    queen_agent_pb2_grpc.add_QueenAgentServicer_to_server(servicer, server)
    server.add_insecure_port(f'[::]:{port}')
    await server.start()

    channel = aio.insecure_channel(f'localhost:{port}')
    stub = queen_agent_pb2_grpc.QueenAgentStub(channel)

    yield {
        'server': server,
        'channel': channel,
        'stub': stub,
        'servicer': servicer,
        'mongodb_client': mock_mongodb_client,
        'neo4j_client': mock_neo4j_client,
        'telemetry_aggregator': mock_telemetry_aggregator,
        'decision_engine': mock_decision_engine
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
# TESTES E2E: GetStrategicDecision
# =============================================================================


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_get_strategic_decision_e2e_success(servicer, mock_mongodb_client, mock_context):
    """
    Teste E2E: busca decisão estratégica completa
    Valida fluxo completo desde request até response
    """
    decision_id = f'dec-{uuid.uuid4().hex[:8]}'
    mock_decision = {
        'decision_id': decision_id,
        'decision_type': 'REPLANNING',
        'confidence_score': 0.92,
        'risk_assessment': {
            'risk_score': 0.18,
            'risk_factors': ['latencia_alta', 'sla_proximo_violacao'],
            'mitigations': ['escalar_recursos', 'redirecionar_trafego']
        },
        'reasoning_summary': 'Replanning necessário devido a alta latência detectada em 3 pods',
        'created_at': int(datetime.now().timestamp() * 1000),
        'decision': {
            'target_entities': ['plan-001', 'plan-002', 'pod-xyz'],
            'action': 'trigger_replanning'
        }
    }
    mock_mongodb_client.get_strategic_decision.return_value = mock_decision

    request = queen_agent_pb2.GetStrategicDecisionRequest(decision_id=decision_id)
    response = await servicer.GetStrategicDecision(request, mock_context)

    # Validar resposta completa
    assert response.decision_id == decision_id
    assert response.decision_type == 'REPLANNING'
    assert response.confidence_score == 0.92
    assert response.risk_score == 0.18
    assert 'Replanning necessário' in response.reasoning_summary
    assert len(response.target_entities) == 3
    assert response.action == 'trigger_replanning'

    # Validar que MongoDB foi chamado corretamente
    mock_mongodb_client.get_strategic_decision.assert_called_once_with(decision_id)

    # Validar que não houve erro
    mock_context.set_code.assert_not_called()


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_get_strategic_decision_e2e_not_found(servicer, mock_mongodb_client, mock_context):
    """
    Teste E2E: decisão não encontrada
    Valida código de erro NOT_FOUND
    """
    mock_mongodb_client.get_strategic_decision.return_value = None

    request = queen_agent_pb2.GetStrategicDecisionRequest(decision_id='dec-inexistente')
    response = await servicer.GetStrategicDecision(request, mock_context)

    # Validar código de erro
    mock_context.set_code.assert_called_once_with(grpc.StatusCode.NOT_FOUND)
    assert response.decision_id == ''


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_get_strategic_decision_e2e_mongodb_error(servicer, mock_mongodb_client, mock_context):
    """
    Teste E2E: erro de conexão com MongoDB
    Valida código de erro INTERNAL
    """
    mock_mongodb_client.get_strategic_decision.side_effect = Exception("MongoDB connection timeout")

    request = queen_agent_pb2.GetStrategicDecisionRequest(decision_id='dec-123')
    response = await servicer.GetStrategicDecision(request, mock_context)

    # Validar código de erro
    mock_context.set_code.assert_called_once_with(grpc.StatusCode.INTERNAL)
    mock_context.set_details.assert_called_once_with("MongoDB connection timeout")


# =============================================================================
# TESTES E2E: ListStrategicDecisions
# =============================================================================


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_list_strategic_decisions_e2e_with_filters(servicer, mock_mongodb_client, mock_context):
    """
    Teste E2E: listagem com filtros aplicados
    Valida construção correta de query MongoDB
    """
    now = int(datetime.now().timestamp() * 1000)
    start_date = now - 3600000  # 1 hora atrás
    end_date = now

    mock_decisions = [
        {
            'decision_id': 'dec-001',
            'decision_type': 'REPLANNING',
            'confidence_score': 0.95,
            'risk_assessment': {'risk_score': 0.10},
            'reasoning_summary': 'Decisão 1',
            'created_at': now - 1800000,
            'decision': {'target_entities': ['plan-001'], 'action': 'replanning'}
        },
        {
            'decision_id': 'dec-002',
            'decision_type': 'REPLANNING',
            'confidence_score': 0.88,
            'risk_assessment': {'risk_score': 0.22},
            'reasoning_summary': 'Decisão 2',
            'created_at': now - 1200000,
            'decision': {'target_entities': ['plan-002'], 'action': 'replanning'}
        }
    ]
    mock_mongodb_client.list_strategic_decisions.return_value = mock_decisions
    mock_mongodb_client.count_strategic_decisions.return_value = 2

    request = queen_agent_pb2.ListStrategicDecisionsRequest(
        decision_type='REPLANNING',
        start_date=start_date,
        end_date=end_date,
        limit=20,
        offset=0
    )
    response = await servicer.ListStrategicDecisions(request, mock_context)

    # Validar resposta
    assert len(response.decisions) == 2
    assert response.total == 2
    assert response.decisions[0].decision_id == 'dec-001'
    assert response.decisions[1].decision_id == 'dec-002'

    # Validar filtros passados ao MongoDB
    call_args = mock_mongodb_client.list_strategic_decisions.call_args
    filters = call_args[0][0]
    assert filters['decision_type'] == 'REPLANNING'
    assert filters['created_at']['$gte'] == start_date
    assert filters['created_at']['$lte'] == end_date
    assert call_args.kwargs['limit'] == 20
    assert call_args.kwargs['skip'] == 0


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_list_strategic_decisions_e2e_pagination(servicer, mock_mongodb_client, mock_context):
    """
    Teste E2E: paginação correta
    Valida limit e offset passados ao MongoDB e total retorna contagem real
    """
    mock_decisions = [
        {
            'decision_id': f'dec-{i:03d}',
            'decision_type': 'ESCALATION',
            'confidence_score': 0.85 + (i * 0.01),
            'risk_assessment': {'risk_score': 0.15},
            'reasoning_summary': f'Decisão {i}',
            'created_at': int(datetime.now().timestamp() * 1000),
            'decision': {'target_entities': [], 'action': 'escalate'}
        }
        for i in range(21, 41)  # Simulando página 2 (offset=20)
    ]
    mock_mongodb_client.list_strategic_decisions.return_value = mock_decisions
    mock_mongodb_client.count_strategic_decisions.return_value = 100  # Total real de decisões

    request = queen_agent_pb2.ListStrategicDecisionsRequest(
        limit=20,
        offset=20
    )
    response = await servicer.ListStrategicDecisions(request, mock_context)

    # Validar paginação - total deve ser contagem real, não tamanho da página
    assert len(response.decisions) == 20
    assert response.total == 100
    assert response.decisions[0].decision_id == 'dec-021'

    # Validar parâmetros de paginação
    call_args = mock_mongodb_client.list_strategic_decisions.call_args
    assert call_args.kwargs['limit'] == 20
    assert call_args.kwargs['skip'] == 20


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_list_strategic_decisions_e2e_empty_result(servicer, mock_mongodb_client, mock_context):
    """
    Teste E2E: listagem vazia
    Valida comportamento quando não há decisões
    """
    mock_mongodb_client.list_strategic_decisions.return_value = []
    mock_mongodb_client.count_strategic_decisions.return_value = 0

    request = queen_agent_pb2.ListStrategicDecisionsRequest(
        decision_type='RESOURCE_ALLOCATION',
        limit=50
    )
    response = await servicer.ListStrategicDecisions(request, mock_context)

    assert len(response.decisions) == 0
    assert response.total == 0
    mock_context.set_code.assert_not_called()


# =============================================================================
# TESTES E2E: GetSystemStatus
# =============================================================================


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_get_system_status_e2e_healthy_system(servicer, mock_telemetry_aggregator, mock_context):
    """
    Teste E2E: sistema saudável
    Valida métricas agregadas corretamente
    """
    mock_health = {
        'system_score': 0.95,
        'sla_compliance': 0.98,
        'error_rate': 0.02,
        'resource_saturation': 0.45,
        'active_incidents': 0,
        'timestamp': int(datetime.now().timestamp() * 1000)
    }
    mock_telemetry_aggregator.aggregate_system_health.return_value = mock_health

    request = queen_agent_pb2.GetSystemStatusRequest()
    response = await servicer.GetSystemStatus(request, mock_context)

    # Validar métricas
    assert response.system_score == 0.95
    assert response.sla_compliance == 0.98
    assert response.error_rate == 0.02
    assert response.resource_saturation == 0.45
    assert response.active_incidents == 0
    assert response.timestamp > 0

    mock_context.set_code.assert_not_called()


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_get_system_status_e2e_degraded_system(servicer, mock_telemetry_aggregator, mock_context):
    """
    Teste E2E: sistema degradado
    Valida métricas com valores críticos
    """
    mock_health = {
        'system_score': 0.42,
        'sla_compliance': 0.68,
        'error_rate': 0.35,
        'resource_saturation': 0.92,
        'active_incidents': 8,
        'timestamp': int(datetime.now().timestamp() * 1000)
    }
    mock_telemetry_aggregator.aggregate_system_health.return_value = mock_health

    request = queen_agent_pb2.GetSystemStatusRequest()
    response = await servicer.GetSystemStatus(request, mock_context)

    # Validar métricas críticas
    assert response.system_score == 0.42
    assert response.sla_compliance == 0.68
    assert response.error_rate == 0.35
    assert response.resource_saturation == 0.92
    assert response.active_incidents == 8


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_get_system_status_e2e_prometheus_unavailable(servicer, mock_telemetry_aggregator, mock_context):
    """
    Teste E2E: Prometheus indisponível
    Valida código de erro INTERNAL
    """
    mock_telemetry_aggregator.aggregate_system_health.side_effect = Exception(
        "Prometheus query failed: connection refused"
    )

    request = queen_agent_pb2.GetSystemStatusRequest()
    response = await servicer.GetSystemStatus(request, mock_context)

    mock_context.set_code.assert_called_once_with(grpc.StatusCode.INTERNAL)


# =============================================================================
# TESTES E2E: GetActiveConflicts
# =============================================================================


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_get_active_conflicts_e2e_with_conflicts(servicer, mock_neo4j_client, mock_context):
    """
    Teste E2E: conflitos ativos encontrados
    Valida consulta Neo4j e conversão de dados
    """
    now = int(datetime.now().timestamp() * 1000)
    mock_conflicts = [
        {
            'decision_id': 'dec-001',
            'conflicts_with': 'dec-002',
            'created_at': now - 60000
        },
        {
            'decision_id': 'dec-003',
            'conflicts_with': 'dec-004',
            'created_at': now - 30000
        },
        {
            'decision_id': 'dec-005',
            'conflicts_with': 'dec-001',
            'created_at': now
        }
    ]
    mock_neo4j_client.list_active_conflicts.return_value = mock_conflicts

    request = queen_agent_pb2.GetActiveConflictsRequest()
    response = await servicer.GetActiveConflicts(request, mock_context)

    assert len(response.conflicts) == 3
    assert response.conflicts[0].decision_id == 'dec-001'
    assert response.conflicts[0].conflicts_with == 'dec-002'
    assert response.conflicts[2].decision_id == 'dec-005'

    mock_neo4j_client.list_active_conflicts.assert_called_once()
    mock_context.set_code.assert_not_called()


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_get_active_conflicts_e2e_no_conflicts(servicer, mock_neo4j_client, mock_context):
    """
    Teste E2E: nenhum conflito ativo
    """
    mock_neo4j_client.list_active_conflicts.return_value = []

    request = queen_agent_pb2.GetActiveConflictsRequest()
    response = await servicer.GetActiveConflicts(request, mock_context)

    assert len(response.conflicts) == 0
    mock_context.set_code.assert_not_called()


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_get_active_conflicts_e2e_neo4j_error(servicer, mock_neo4j_client, mock_context):
    """
    Teste E2E: erro de conexão com Neo4j
    """
    mock_neo4j_client.list_active_conflicts.side_effect = Exception("Neo4j connection refused")

    request = queen_agent_pb2.GetActiveConflictsRequest()
    response = await servicer.GetActiveConflicts(request, mock_context)

    mock_context.set_code.assert_called_once_with(grpc.StatusCode.INTERNAL)
    assert len(response.conflicts) == 0


# =============================================================================
# TESTES E2E: Fluxo Completo de Tomada de Decisão
# =============================================================================


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_full_decision_flow_e2e(servicer, mock_mongodb_client, mock_neo4j_client, mock_telemetry_aggregator, mock_context):
    """
    Teste E2E: fluxo completo de consulta de decisão
    1. Verifica status do sistema
    2. Lista decisões recentes
    3. Busca decisão específica
    4. Verifica conflitos
    """
    now = int(datetime.now().timestamp() * 1000)

    # 1. Setup: status do sistema
    mock_telemetry_aggregator.aggregate_system_health.return_value = {
        'system_score': 0.75,
        'sla_compliance': 0.88,
        'error_rate': 0.08,
        'resource_saturation': 0.65,
        'active_incidents': 2,
        'timestamp': now
    }

    # 2. Setup: lista de decisões
    mock_mongodb_client.list_strategic_decisions.return_value = [
        {
            'decision_id': 'dec-flow-001',
            'decision_type': 'REPLANNING',
            'confidence_score': 0.90,
            'risk_assessment': {'risk_score': 0.15},
            'reasoning_summary': 'Decisão do fluxo',
            'created_at': now,
            'decision': {'target_entities': ['plan-001'], 'action': 'replanning'}
        }
    ]
    mock_mongodb_client.count_strategic_decisions.return_value = 1

    # 3. Setup: decisão específica
    mock_mongodb_client.get_strategic_decision.return_value = {
        'decision_id': 'dec-flow-001',
        'decision_type': 'REPLANNING',
        'confidence_score': 0.90,
        'risk_assessment': {'risk_score': 0.15},
        'reasoning_summary': 'Decisão do fluxo',
        'created_at': now,
        'decision': {'target_entities': ['plan-001'], 'action': 'replanning'}
    }

    # 4. Setup: sem conflitos
    mock_neo4j_client.list_active_conflicts.return_value = []

    # Executar fluxo completo

    # Passo 1: Verificar status
    status_response = await servicer.GetSystemStatus(
        queen_agent_pb2.GetSystemStatusRequest(),
        mock_context
    )
    assert status_response.system_score == 0.75
    assert status_response.active_incidents == 2

    # Passo 2: Listar decisões recentes
    list_response = await servicer.ListStrategicDecisions(
        queen_agent_pb2.ListStrategicDecisionsRequest(limit=10),
        mock_context
    )
    assert len(list_response.decisions) == 1
    decision_id = list_response.decisions[0].decision_id

    # Passo 3: Buscar decisão específica
    get_response = await servicer.GetStrategicDecision(
        queen_agent_pb2.GetStrategicDecisionRequest(decision_id=decision_id),
        mock_context
    )
    assert get_response.decision_id == decision_id
    assert get_response.confidence_score == 0.90

    # Passo 4: Verificar conflitos
    conflicts_response = await servicer.GetActiveConflicts(
        queen_agent_pb2.GetActiveConflictsRequest(),
        mock_context
    )
    assert len(conflicts_response.conflicts) == 0

    # Validar que não houve erros em nenhum passo
    mock_context.set_code.assert_not_called()


# =============================================================================
# TESTES E2E: SubmitInsight
# =============================================================================


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_submit_insight_e2e_success(servicer, mock_mongodb_client, mock_context):
    """
    Teste E2E: submissão de insight aceita
    """
    insight_id = f'insight-{uuid.uuid4().hex[:8]}'

    request = queen_agent_pb2.SubmitInsightRequest(
        insight_id=insight_id,
        version='1.0.0',
        correlation_id='corr-123',
        trace_id='trace-456',
        span_id='span-789',
        insight_type='ANOMALY_DETECTION',
        priority='HIGH',
        title='Alta latência detectada',
        summary='Latência média acima de 500ms nos últimos 5 minutos',
        detailed_analysis='Análise detalhada...',
        confidence_score=0.95,
        impact_score=0.8,
        created_at=int(datetime.now().timestamp() * 1000),
        hash='abc123',
        schema_version=1
    )
    request.data_sources.extend(['prometheus', 'logs'])
    request.tags.extend(['performance', 'latency'])

    response = await servicer.SubmitInsight(request, mock_context)

    assert response.accepted is True
    assert response.insight_id == insight_id
    assert 'aceito com sucesso' in response.message

    # Validar que foi salvo no MongoDB
    mock_mongodb_client.db.analyst_insights.insert_one.assert_called_once()


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_submit_insight_e2e_mongodb_error(servicer, mock_mongodb_client, mock_context):
    """
    Teste E2E: erro ao salvar insight
    """
    mock_mongodb_client.db.analyst_insights.insert_one.side_effect = Exception("MongoDB write error")

    request = queen_agent_pb2.SubmitInsightRequest(
        insight_id='insight-error',
        version='1.0.0',
        insight_type='ANOMALY_DETECTION',
        priority='MEDIUM',
        title='Test',
        summary='Test',
        confidence_score=0.5,
        impact_score=0.5,
        created_at=int(datetime.now().timestamp() * 1000),
        schema_version=1
    )

    response = await servicer.SubmitInsight(request, mock_context)

    assert response.accepted is False
    mock_context.set_code.assert_called_once_with(grpc.StatusCode.INTERNAL)


# =============================================================================
# TESTES E2E COM SERVIDOR gRPC REAL E STUB
# =============================================================================


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_grpc_server_get_strategic_decision_via_stub(grpc_server_and_stub):
    """
    Teste E2E com servidor gRPC real: GetStrategicDecision via stub
    Valida chamada completa cliente -> servidor -> resposta
    """
    stub = grpc_server_and_stub['stub']
    mongodb_client = grpc_server_and_stub['mongodb_client']

    decision_id = f'dec-{uuid.uuid4().hex[:8]}'
    mock_decision = {
        'decision_id': decision_id,
        'decision_type': 'REPLANNING',
        'confidence_score': 0.92,
        'risk_assessment': {'risk_score': 0.18},
        'reasoning_summary': 'Replanning necessário via stub test',
        'created_at': int(datetime.now().timestamp() * 1000),
        'decision': {'target_entities': ['plan-001'], 'action': 'trigger_replanning'}
    }
    mongodb_client.get_strategic_decision.return_value = mock_decision

    request = queen_agent_pb2.GetStrategicDecisionRequest(decision_id=decision_id)
    response = await stub.GetStrategicDecision(request)

    assert response.decision_id == decision_id
    assert response.decision_type == 'REPLANNING'
    assert response.confidence_score == 0.92
    mongodb_client.get_strategic_decision.assert_called_once_with(decision_id)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_grpc_server_list_strategic_decisions_via_stub(grpc_server_and_stub):
    """
    Teste E2E com servidor gRPC real: ListStrategicDecisions via stub
    Valida paginação e total correto
    """
    stub = grpc_server_and_stub['stub']
    mongodb_client = grpc_server_and_stub['mongodb_client']

    now = int(datetime.now().timestamp() * 1000)
    mock_decisions = [
        {
            'decision_id': f'dec-{i:03d}',
            'decision_type': 'REPLANNING',
            'confidence_score': 0.90,
            'risk_assessment': {'risk_score': 0.10},
            'reasoning_summary': f'Decisão {i}',
            'created_at': now,
            'decision': {'target_entities': [], 'action': 'replanning'}
        }
        for i in range(1, 6)
    ]
    mongodb_client.list_strategic_decisions.return_value = mock_decisions
    mongodb_client.count_strategic_decisions.return_value = 100  # Total real maior que página

    request = queen_agent_pb2.ListStrategicDecisionsRequest(limit=5, offset=0)
    response = await stub.ListStrategicDecisions(request)

    assert len(response.decisions) == 5
    assert response.total == 100  # Deve retornar total real, não tamanho da página
    assert response.decisions[0].decision_id == 'dec-001'


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_grpc_server_get_system_status_via_stub(grpc_server_and_stub):
    """
    Teste E2E com servidor gRPC real: GetSystemStatus via stub
    Valida métricas do sistema
    """
    stub = grpc_server_and_stub['stub']
    telemetry_aggregator = grpc_server_and_stub['telemetry_aggregator']

    mock_health = {
        'system_score': 0.95,
        'sla_compliance': 0.98,
        'error_rate': 0.02,
        'resource_saturation': 0.45,
        'active_incidents': 0,
        'timestamp': int(datetime.now().timestamp() * 1000)
    }
    telemetry_aggregator.aggregate_system_health.return_value = mock_health

    request = queen_agent_pb2.GetSystemStatusRequest()
    response = await stub.GetSystemStatus(request)

    assert response.system_score == 0.95
    assert response.sla_compliance == 0.98
    assert response.active_incidents == 0


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_grpc_server_get_active_conflicts_via_stub(grpc_server_and_stub):
    """
    Teste E2E com servidor gRPC real: GetActiveConflicts via stub
    Valida consulta de conflitos
    """
    stub = grpc_server_and_stub['stub']
    neo4j_client = grpc_server_and_stub['neo4j_client']

    now = int(datetime.now().timestamp() * 1000)
    mock_conflicts = [
        {'decision_id': 'dec-001', 'conflicts_with': 'dec-002', 'created_at': now}
    ]
    neo4j_client.list_active_conflicts.return_value = mock_conflicts

    request = queen_agent_pb2.GetActiveConflictsRequest()
    response = await stub.GetActiveConflicts(request)

    assert len(response.conflicts) == 1
    assert response.conflicts[0].decision_id == 'dec-001'
    assert response.conflicts[0].conflicts_with == 'dec-002'


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_grpc_server_make_strategic_decision_via_stub(grpc_server_and_stub):
    """
    Teste E2E com servidor gRPC real: MakeStrategicDecision via stub
    Valida criação de nova decisão estratégica
    """
    stub = grpc_server_and_stub['stub']
    decision_engine = grpc_server_and_stub['decision_engine']

    # Mock do retorno do StrategicDecisionEngine
    mock_decision = MagicMock()
    mock_decision.decision_id = 'dec-new-001'
    mock_decision.decision_type.value = 'REPLANNING'
    mock_decision.confidence_score = 0.88
    mock_decision.risk_assessment.risk_score = 0.15
    mock_decision.reasoning_summary = 'Decisão estratégica criada via gRPC'
    decision_engine.make_strategic_decision.return_value = mock_decision

    request = queen_agent_pb2.MakeStrategicDecisionRequest(
        event_type='sla_violation',
        source_id='service-xyz'
    )
    response = await stub.MakeStrategicDecision(request)

    assert response.success is True
    assert response.decision_id == 'dec-new-001'
    assert response.decision_type == 'REPLANNING'
    assert response.confidence_score == 0.88
    assert 'criada com sucesso' in response.message
    decision_engine.make_strategic_decision.assert_called_once()


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_grpc_server_full_flow_via_stub(grpc_server_and_stub):
    """
    Teste E2E com servidor gRPC real: fluxo completo via stub
    1. Verificar status do sistema
    2. Criar decisão estratégica
    3. Buscar decisão criada
    4. Listar decisões
    """
    stub = grpc_server_and_stub['stub']
    mongodb_client = grpc_server_and_stub['mongodb_client']
    telemetry_aggregator = grpc_server_and_stub['telemetry_aggregator']
    decision_engine = grpc_server_and_stub['decision_engine']

    now = int(datetime.now().timestamp() * 1000)

    # Setup mocks
    telemetry_aggregator.aggregate_system_health.return_value = {
        'system_score': 0.75,
        'sla_compliance': 0.88,
        'error_rate': 0.08,
        'resource_saturation': 0.65,
        'active_incidents': 2,
        'timestamp': now
    }

    mock_decision = MagicMock()
    mock_decision.decision_id = 'dec-flow-via-stub'
    mock_decision.decision_type.value = 'REPLANNING'
    mock_decision.confidence_score = 0.90
    mock_decision.risk_assessment.risk_score = 0.12
    mock_decision.reasoning_summary = 'Decisão do fluxo E2E'
    decision_engine.make_strategic_decision.return_value = mock_decision

    mongodb_client.get_strategic_decision.return_value = {
        'decision_id': 'dec-flow-via-stub',
        'decision_type': 'REPLANNING',
        'confidence_score': 0.90,
        'risk_assessment': {'risk_score': 0.12},
        'reasoning_summary': 'Decisão do fluxo E2E',
        'created_at': now,
        'decision': {'target_entities': ['plan-001'], 'action': 'replanning'}
    }

    mongodb_client.list_strategic_decisions.return_value = [{
        'decision_id': 'dec-flow-via-stub',
        'decision_type': 'REPLANNING',
        'confidence_score': 0.90,
        'risk_assessment': {'risk_score': 0.12},
        'reasoning_summary': 'Decisão do fluxo E2E',
        'created_at': now,
        'decision': {'target_entities': ['plan-001'], 'action': 'replanning'}
    }]
    mongodb_client.count_strategic_decisions.return_value = 1

    # Passo 1: Verificar status do sistema
    status_response = await stub.GetSystemStatus(queen_agent_pb2.GetSystemStatusRequest())
    assert status_response.system_score == 0.75
    assert status_response.active_incidents == 2

    # Passo 2: Criar decisão estratégica
    make_response = await stub.MakeStrategicDecision(
        queen_agent_pb2.MakeStrategicDecisionRequest(
            event_type='sla_violation',
            source_id='service-test'
        )
    )
    assert make_response.success is True
    decision_id = make_response.decision_id

    # Passo 3: Buscar decisão criada
    get_response = await stub.GetStrategicDecision(
        queen_agent_pb2.GetStrategicDecisionRequest(decision_id=decision_id)
    )
    assert get_response.decision_id == decision_id
    assert get_response.confidence_score == 0.90

    # Passo 4: Listar decisões
    list_response = await stub.ListStrategicDecisions(
        queen_agent_pb2.ListStrategicDecisionsRequest(limit=10)
    )
    assert len(list_response.decisions) == 1
    assert list_response.total == 1
