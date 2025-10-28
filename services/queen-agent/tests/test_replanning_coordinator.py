"""
Testes para ReplanningCoordinator - foco em get_replanning_stats
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.services.replanning_coordinator import ReplanningCoordinator


@pytest.fixture
def mock_settings():
    """Mock de configurações"""
    settings = MagicMock()
    settings.REPLANNING_COOLDOWN_SECONDS = 300
    return settings


@pytest.fixture
def mock_clients():
    """Mock dos clientes"""
    return {
        'orchestrator': AsyncMock(),
        'redis': AsyncMock()
    }


@pytest.fixture
def replanning_coordinator(mock_clients, mock_settings):
    """Instância do ReplanningCoordinator com mocks"""
    return ReplanningCoordinator(
        orchestrator_client=mock_clients['orchestrator'],
        redis_client=mock_clients['redis'],
        settings=mock_settings
    )


@pytest.mark.asyncio
async def test_get_replanning_stats_with_active_cooldowns(replanning_coordinator, mock_clients):
    """Testa obtenção de estatísticas com cooldowns ativos"""
    # Mock do Redis SCAN para retornar chaves de cooldown
    mock_redis = AsyncMock()

    # Primeira iteração do SCAN retorna algumas chaves
    mock_redis.scan.side_effect = [
        (5, [b'replanning:cooldown:plan-1', b'replanning:cooldown:plan-2']),
        (0, [b'replanning:cooldown:plan-3'])  # cursor 0 indica fim
    ]

    mock_clients['redis'].client = mock_redis

    stats = await replanning_coordinator.get_replanning_stats()

    # Verificar estatísticas
    assert stats['total_replannings'] == 3
    assert stats['active_replannings'] == 3
    assert len(stats['cooldown_plans']) == 3
    assert 'plan-1' in stats['cooldown_plans']
    assert 'plan-2' in stats['cooldown_plans']
    assert 'plan-3' in stats['cooldown_plans']


@pytest.mark.asyncio
async def test_get_replanning_stats_no_cooldowns(replanning_coordinator, mock_clients):
    """Testa obtenção de estatísticas sem cooldowns"""
    mock_redis = AsyncMock()
    mock_redis.scan.return_value = (0, [])  # Sem chaves
    mock_clients['redis'].client = mock_redis

    stats = await replanning_coordinator.get_replanning_stats()

    assert stats['total_replannings'] == 0
    assert stats['active_replannings'] == 0
    assert stats['cooldown_plans'] == []


@pytest.mark.asyncio
async def test_get_replanning_stats_handles_string_keys(replanning_coordinator, mock_clients):
    """Testa tratamento de chaves como strings (não bytes)"""
    mock_redis = AsyncMock()
    # Algumas implementações do Redis retornam strings em vez de bytes
    mock_redis.scan.return_value = (
        0,
        ['replanning:cooldown:plan-1', 'replanning:cooldown:plan-2']
    )
    mock_clients['redis'].client = mock_redis

    stats = await replanning_coordinator.get_replanning_stats()

    assert stats['total_replannings'] == 2
    assert 'plan-1' in stats['cooldown_plans']
    assert 'plan-2' in stats['cooldown_plans']


@pytest.mark.asyncio
async def test_get_replanning_stats_handles_exception(replanning_coordinator, mock_clients):
    """Testa tratamento de exceção"""
    mock_redis = AsyncMock()
    mock_redis.scan.side_effect = Exception("Redis connection error")
    mock_clients['redis'].client = mock_redis

    stats = await replanning_coordinator.get_replanning_stats()

    # Deve retornar estatísticas vazias em caso de erro
    assert stats['total_replannings'] == 0
    assert stats['active_replannings'] == 0
    assert stats['cooldown_plans'] == []


@pytest.mark.asyncio
async def test_trigger_replanning_success(replanning_coordinator, mock_clients):
    """Testa disparo de replanning com sucesso"""
    # Mock para não estar em cooldown
    mock_clients['redis'].get_cached_context.return_value = None

    # Mock para orchestrator aceitar replanning
    mock_clients['orchestrator'].trigger_replanning.return_value = True

    result = await replanning_coordinator.trigger_replanning(
        plan_id='plan-1',
        reason='test_reason',
        decision_id='dec-001'
    )

    assert result is True

    # Verificar que o replanning foi registrado (cooldown iniciado)
    mock_clients['redis'].cache_strategic_context.assert_called_once()


@pytest.mark.asyncio
async def test_trigger_replanning_in_cooldown(replanning_coordinator, mock_clients):
    """Testa rejeição de replanning quando em cooldown"""
    # Mock para estar em cooldown
    mock_clients['redis'].get_cached_context.return_value = {
        'decision_id': 'old-dec',
        'timestamp': 123456789
    }

    result = await replanning_coordinator.trigger_replanning(
        plan_id='plan-1',
        reason='test_reason',
        decision_id='dec-001'
    )

    assert result is False

    # Não deve ter chamado o orchestrator
    mock_clients['orchestrator'].trigger_replanning.assert_not_called()
