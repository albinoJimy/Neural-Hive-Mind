"""
Testes para Neo4jClient - foco em list_active_conflicts
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.clients.neo4j_client import Neo4jClient


@pytest.fixture
def mock_settings():
    """Mock de configurações"""
    settings = MagicMock()
    settings.NEO4J_URI = 'bolt://localhost:7687'
    settings.NEO4J_USER = 'neo4j'
    settings.NEO4J_PASSWORD = 'password'
    settings.NEO4J_DATABASE = 'neo4j'
    settings.NEO4J_MAX_CONNECTION_POOL_SIZE = 50
    return settings


@pytest.fixture
async def neo4j_client(mock_settings):
    """Cliente Neo4j com mock"""
    client = Neo4jClient(mock_settings)
    # Mock do driver
    client.driver = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_list_active_conflicts_success(neo4j_client):
    """Testa listagem de conflitos ativos com sucesso"""
    # Mock da sessão e resultado
    mock_session = AsyncMock()
    mock_result = AsyncMock()

    # Dados de exemplo
    mock_data = [
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

    mock_result.data.return_value = mock_data
    mock_session.run.return_value = mock_result
    neo4j_client.driver.session.return_value.__aenter__.return_value = mock_session

    # Executar método
    conflicts = await neo4j_client.list_active_conflicts()

    # Verificar resultado
    assert len(conflicts) == 2
    assert conflicts[0]['decision_id'] == 'dec-001'
    assert conflicts[0]['conflicts_with'] == 'dec-002'
    assert conflicts[1]['decision_id'] == 'dec-003'

    # Verificar que a query foi executada
    mock_session.run.assert_called_once()
    call_args = mock_session.run.call_args[0]
    assert 'CONFLICTS_WITH' in call_args[0]
    assert 'resolved = false' in call_args[0]


@pytest.mark.asyncio
async def test_list_active_conflicts_empty(neo4j_client):
    """Testa listagem quando não há conflitos"""
    mock_session = AsyncMock()
    mock_result = AsyncMock()
    mock_result.data.return_value = []
    mock_session.run.return_value = mock_result
    neo4j_client.driver.session.return_value.__aenter__.return_value = mock_session

    conflicts = await neo4j_client.list_active_conflicts()

    assert conflicts == []


@pytest.mark.asyncio
async def test_list_active_conflicts_handles_exception(neo4j_client):
    """Testa tratamento de exceção"""
    mock_session = AsyncMock()
    mock_session.run.side_effect = Exception("Neo4j connection error")
    neo4j_client.driver.session.return_value.__aenter__.return_value = mock_session

    conflicts = await neo4j_client.list_active_conflicts()

    # Deve retornar lista vazia em caso de erro
    assert conflicts == []


@pytest.mark.asyncio
async def test_list_active_conflicts_partial_data(neo4j_client):
    """Testa listagem com dados parciais (campos faltando)"""
    mock_session = AsyncMock()
    mock_result = AsyncMock()

    # Dados com campos faltando
    mock_data = [
        {
            'decision_id': 'dec-001',
            # conflicts_with está faltando
            'created_at': 1638360000000
        },
        {
            'decision_id': 'dec-002',
            'conflicts_with': 'dec-003'
            # created_at está faltando
        }
    ]

    mock_result.data.return_value = mock_data
    mock_session.run.return_value = mock_result
    neo4j_client.driver.session.return_value.__aenter__.return_value = mock_session

    conflicts = await neo4j_client.list_active_conflicts()

    # Deve retornar dados mesmo com campos faltando (usando .get())
    assert len(conflicts) == 2
    assert conflicts[0]['decision_id'] == 'dec-001'
    assert conflicts[0]['conflicts_with'] is None
    assert conflicts[1]['created_at'] is None
