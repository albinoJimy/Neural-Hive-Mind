"""
Testes para ReplanningCoordinator - foco em get_replanning_stats
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from src.services.replanning_coordinator import ReplanningCoordinator


@pytest.fixture()
def mock_settings():
    """Mock de configurações"""
    settings = MagicMock()
    settings.REPLANNING_COOLDOWN_SECONDS = 300
    return settings


@pytest.fixture()
def mock_clients():
    """Mock dos clientes"""
    return {"orchestrator": AsyncMock(), "redis": AsyncMock()}


@pytest.fixture()
def replanning_coordinator(mock_clients, mock_settings):
    """Instância do ReplanningCoordinator com mocks"""
    return ReplanningCoordinator(
        orchestrator_client=mock_clients["orchestrator"],
        redis_client=mock_clients["redis"],
        settings=mock_settings,
    )


# TR-1: o `get_replanning_stats` migrou de `scan(cursor=...)` (incompatível
# com RedisCluster — retorna dict[node, int] como cursor) para `scan_iter`,
# que é stateless e faz fan-out implícito. Os mocks abaixo expõem
# `scan_iter` como async generator, alinhando o contrato do teste com a
# nova interface real.


def _scan_iter_mock(items):
    """Devolve um callable que produz um async generator a cada chamada."""

    async def _gen(*_args, **_kwargs):
        for item in items:
            yield item

    return _gen


@pytest.mark.asyncio()
async def test_get_replanning_stats_with_active_cooldowns(replanning_coordinator, mock_clients):
    """Testa obtenção de estatísticas com cooldowns ativos"""
    mock_redis = AsyncMock()
    mock_redis.scan_iter = _scan_iter_mock(
        [
            b"replanning:cooldown:plan-1",
            b"replanning:cooldown:plan-2",
            b"replanning:cooldown:plan-3",
        ]
    )
    mock_clients["redis"].client = mock_redis

    stats = await replanning_coordinator.get_replanning_stats()

    assert stats["total_replannings"] == 3
    assert stats["active_replannings"] == 3
    assert len(stats["cooldown_plans"]) == 3
    assert "plan-1" in stats["cooldown_plans"]
    assert "plan-2" in stats["cooldown_plans"]
    assert "plan-3" in stats["cooldown_plans"]


@pytest.mark.asyncio()
async def test_get_replanning_stats_no_cooldowns(replanning_coordinator, mock_clients):
    """Testa obtenção de estatísticas sem cooldowns"""
    mock_redis = AsyncMock()
    mock_redis.scan_iter = _scan_iter_mock([])
    mock_clients["redis"].client = mock_redis

    stats = await replanning_coordinator.get_replanning_stats()

    assert stats["total_replannings"] == 0
    assert stats["active_replannings"] == 0
    assert stats["cooldown_plans"] == []


@pytest.mark.asyncio()
async def test_get_replanning_stats_handles_string_keys(replanning_coordinator, mock_clients):
    """Com decode_responses=True o cluster client devolve str directamente."""
    mock_redis = AsyncMock()
    mock_redis.scan_iter = _scan_iter_mock(
        ["replanning:cooldown:plan-1", "replanning:cooldown:plan-2"]
    )
    mock_clients["redis"].client = mock_redis

    stats = await replanning_coordinator.get_replanning_stats()

    assert stats["total_replannings"] == 2
    assert "plan-1" in stats["cooldown_plans"]
    assert "plan-2" in stats["cooldown_plans"]


@pytest.mark.asyncio()
async def test_get_replanning_stats_handles_exception(replanning_coordinator, mock_clients):
    """Testa tratamento de exceção do scan_iter"""

    async def _broken(*_args, **_kwargs):
        msg = "Redis connection error"
        raise RuntimeError(msg)
        yield  # pragma: no cover — necessário para tornar a função um generator

    mock_redis = AsyncMock()
    mock_redis.scan_iter = _broken
    mock_clients["redis"].client = mock_redis

    stats = await replanning_coordinator.get_replanning_stats()

    # Deve retornar estatísticas vazias em caso de erro
    assert stats["total_replannings"] == 0
    assert stats["active_replannings"] == 0
    assert stats["cooldown_plans"] == []


@pytest.mark.asyncio()
async def test_trigger_replanning_success(replanning_coordinator, mock_clients):
    """Testa disparo de replanning com sucesso"""
    # Mock para não estar em cooldown
    mock_clients["redis"].get_cached_context.return_value = None

    # Mock para orchestrator aceitar replanning
    mock_clients["orchestrator"].trigger_replanning.return_value = True

    result = await replanning_coordinator.trigger_replanning(
        plan_id="plan-1", reason="test_reason", decision_id="dec-001"
    )

    assert result is True

    # Verificar que o replanning foi registrado (cooldown iniciado)
    mock_clients["redis"].cache_strategic_context.assert_called_once()


@pytest.mark.asyncio()
async def test_trigger_replanning_in_cooldown(replanning_coordinator, mock_clients):
    """Testa rejeição de replanning quando em cooldown"""
    # Mock para estar em cooldown
    mock_clients["redis"].get_cached_context.return_value = {
        "decision_id": "old-dec",
        "timestamp": 123456789,
    }

    result = await replanning_coordinator.trigger_replanning(
        plan_id="plan-1", reason="test_reason", decision_id="dec-001"
    )

    assert result is False

    # Não deve ter chamado o orchestrator
    mock_clients["orchestrator"].trigger_replanning.assert_not_called()
