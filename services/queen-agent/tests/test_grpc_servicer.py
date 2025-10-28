"""
Testes para QueenAgentServicer - foco em GetActiveConflicts
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
import grpc

from src.grpc_server.queen_servicer import QueenAgentServicer
from src.proto import queen_agent_pb2


@pytest.fixture
def mock_clients():
    """Mock dos clientes"""
    return {
        'mongodb': AsyncMock(),
        'neo4j': AsyncMock(),
        'exception_service': AsyncMock(),
        'telemetry_aggregator': AsyncMock()
    }


@pytest.fixture
def servicer(mock_clients):
    """Instância do servicer com mocks"""
    return QueenAgentServicer(
        mongodb_client=mock_clients['mongodb'],
        neo4j_client=mock_clients['neo4j'],
        exception_service=mock_clients['exception_service'],
        telemetry_aggregator=mock_clients['telemetry_aggregator']
    )


@pytest.fixture
def mock_context():
    """Mock do contexto gRPC"""
    context = MagicMock()
    context.set_code = MagicMock()
    context.set_details = MagicMock()
    return context


@pytest.mark.asyncio
async def test_get_active_conflicts_success(servicer, mock_clients, mock_context):
    """Testa obtenção de conflitos ativos com sucesso"""
    # Configurar mock do Neo4j client
    mock_conflicts = [
        {
            'decision_id': 'dec-001',
            'conflicts_with': 'dec-002',
            'created_at': 1638360000000
        },
        {
            'decision_id': 'dec-003',
            'conflicts_with': 'dec-004',
            'created_at': 1638360001000
        }
    ]
    mock_clients['neo4j'].list_active_conflicts.return_value = mock_conflicts

    # Criar request
    request = queen_agent_pb2.GetActiveConflictsRequest()

    # Executar método
    response = await servicer.GetActiveConflicts(request, mock_context)

    # Verificar resposta
    assert len(response.conflicts) == 2
    assert response.conflicts[0].decision_id == 'dec-001'
    assert response.conflicts[0].conflicts_with == 'dec-002'
    assert response.conflicts[0].created_at == 1638360000000
    assert response.conflicts[1].decision_id == 'dec-003'

    # Verificar que o método correto foi chamado
    mock_clients['neo4j'].list_active_conflicts.assert_called_once()

    # Verificar que não houve erro
    mock_context.set_code.assert_not_called()
    mock_context.set_details.assert_not_called()


@pytest.mark.asyncio
async def test_get_active_conflicts_empty(servicer, mock_clients, mock_context):
    """Testa obtenção quando não há conflitos"""
    mock_clients['neo4j'].list_active_conflicts.return_value = []

    request = queen_agent_pb2.GetActiveConflictsRequest()
    response = await servicer.GetActiveConflicts(request, mock_context)

    assert len(response.conflicts) == 0
    mock_context.set_code.assert_not_called()


@pytest.mark.asyncio
async def test_get_active_conflicts_handles_exception(servicer, mock_clients, mock_context):
    """Testa tratamento de exceção"""
    # Simular exceção no Neo4j
    mock_clients['neo4j'].list_active_conflicts.side_effect = Exception("Neo4j error")

    request = queen_agent_pb2.GetActiveConflictsRequest()
    response = await servicer.GetActiveConflicts(request, mock_context)

    # Deve retornar resposta vazia
    assert len(response.conflicts) == 0

    # Deve ter configurado código de erro
    mock_context.set_code.assert_called_once_with(grpc.StatusCode.INTERNAL)
    mock_context.set_details.assert_called_once()


@pytest.mark.asyncio
async def test_get_active_conflicts_handles_partial_data(servicer, mock_clients, mock_context):
    """Testa tratamento de dados parciais"""
    # Conflitos com campos faltando
    mock_conflicts = [
        {
            'decision_id': 'dec-001',
            # conflicts_with faltando
            'created_at': 1638360000000
        },
        {
            'decision_id': 'dec-002',
            'conflicts_with': 'dec-003'
            # created_at faltando
        }
    ]
    mock_clients['neo4j'].list_active_conflicts.return_value = mock_conflicts

    request = queen_agent_pb2.GetActiveConflictsRequest()
    response = await servicer.GetActiveConflicts(request, mock_context)

    # Deve processar mesmo com dados faltando (usando valores padrão)
    assert len(response.conflicts) == 2
    assert response.conflicts[0].decision_id == 'dec-001'
    assert response.conflicts[0].conflicts_with == ''  # Valor padrão para string
    assert response.conflicts[1].created_at == 0  # Valor padrão para int


@pytest.mark.asyncio
async def test_get_system_status_success(servicer, mock_clients, mock_context):
    """Testa obtenção de status do sistema"""
    mock_health = {
        'system_score': 0.95,
        'sla_compliance': 0.98,
        'error_rate': 0.02,
        'resource_saturation': 0.45,
        'active_incidents': 2,
        'timestamp': 1638360000000
    }
    mock_clients['telemetry_aggregator'].aggregate_system_health.return_value = mock_health

    request = queen_agent_pb2.GetSystemStatusRequest()
    response = await servicer.GetSystemStatus(request, mock_context)

    assert response.system_score == 0.95
    assert response.sla_compliance == 0.98
    assert response.error_rate == 0.02
    assert response.active_incidents == 2
    mock_context.set_code.assert_not_called()
