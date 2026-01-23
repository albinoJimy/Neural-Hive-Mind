"""
Testes de idempotência para o ExecutionEngine.

Verifica que tickets duplicados são detectados e ignorados corretamente,
e que o sistema continua funcionando mesmo quando Redis está indisponível (fail-open).
"""
import sys
import os
from pathlib import Path

# Add worker-agents src to path
WORKER_SRC = Path(__file__).parent.parent.parent / "services" / "worker-agents" / "src"
if str(WORKER_SRC) not in sys.path:
    sys.path.insert(0, str(WORKER_SRC))

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_config():
    """Fixture para configuração mockada."""
    config = MagicMock()
    config.max_concurrent_tasks = 10
    config.agent_id = 'worker-test-001'
    return config


@pytest.fixture
def mock_redis_client():
    """Fixture para Redis client mockado."""
    redis_mock = AsyncMock()
    return redis_mock


@pytest.fixture
def mock_ticket_client():
    """Fixture para ticket client mockado."""
    return AsyncMock()


@pytest.fixture
def mock_result_producer():
    """Fixture para result producer mockado."""
    return AsyncMock()


@pytest.fixture
def mock_dependency_coordinator():
    """Fixture para dependency coordinator mockado."""
    return AsyncMock()


@pytest.fixture
def mock_executor_registry():
    """Fixture para executor registry mockado."""
    registry = MagicMock()
    registry.get_executor = MagicMock(return_value=None)
    return registry


@pytest.fixture
def mock_metrics():
    """Fixture para métricas mockadas."""
    metrics = MagicMock()
    metrics.duplicates_detected_total = MagicMock()
    metrics.duplicates_detected_total.labels = MagicMock(return_value=MagicMock())
    return metrics


@pytest.mark.asyncio
async def test_duplicate_ticket_is_skipped(
    mock_config,
    mock_redis_client,
    mock_ticket_client,
    mock_result_producer,
    mock_dependency_coordinator,
    mock_executor_registry
):
    """Testar que tickets duplicados são ignorados (two-phase scheme)."""
    from engine.execution_engine import ExecutionEngine

    # Setup: exists retorna False (não processado), set retorna True/False
    mock_redis_client.exists = AsyncMock(side_effect=[False, False])
    mock_redis_client.set = AsyncMock(side_effect=[True, False])

    engine = ExecutionEngine(
        config=mock_config,
        ticket_client=mock_ticket_client,
        result_producer=mock_result_producer,
        dependency_coordinator=mock_dependency_coordinator,
        executor_registry=mock_executor_registry,
        redis_client=mock_redis_client,
        metrics=None
    )

    # Primeira vez - não é duplicata
    is_dup_1 = await engine._is_duplicate_ticket("ticket-789")
    assert is_dup_1 is False

    # Segunda vez - é duplicata (processing key já existe)
    is_dup_2 = await engine._is_duplicate_ticket("ticket-789")
    assert is_dup_2 is True


@pytest.mark.asyncio
async def test_redis_failure_allows_processing(
    mock_config,
    mock_ticket_client,
    mock_result_producer,
    mock_dependency_coordinator,
    mock_executor_registry
):
    """Testar fail-open quando Redis falha."""
    from engine.execution_engine import ExecutionEngine

    redis_mock = AsyncMock()
    redis_mock.exists = AsyncMock(side_effect=Exception("Redis connection failed"))

    engine = ExecutionEngine(
        config=mock_config,
        ticket_client=mock_ticket_client,
        result_producer=mock_result_producer,
        dependency_coordinator=mock_dependency_coordinator,
        executor_registry=mock_executor_registry,
        redis_client=redis_mock,
        metrics=None
    )

    # Deve retornar False (não é duplicata) para permitir processamento
    is_dup = await engine._is_duplicate_ticket("ticket-456")
    assert is_dup is False


@pytest.mark.asyncio
async def test_no_redis_client_allows_processing(
    mock_config,
    mock_ticket_client,
    mock_result_producer,
    mock_dependency_coordinator,
    mock_executor_registry
):
    """Testar que processamento continua quando Redis não está disponível."""
    from engine.execution_engine import ExecutionEngine

    engine = ExecutionEngine(
        config=mock_config,
        ticket_client=mock_ticket_client,
        result_producer=mock_result_producer,
        dependency_coordinator=mock_dependency_coordinator,
        executor_registry=mock_executor_registry,
        redis_client=None,  # Redis não disponível
        metrics=None
    )

    # Deve retornar False (não é duplicata) para permitir processamento
    is_dup = await engine._is_duplicate_ticket("ticket-789")
    assert is_dup is False


@pytest.mark.asyncio
async def test_process_ticket_skips_duplicate(
    mock_config,
    mock_redis_client,
    mock_ticket_client,
    mock_result_producer,
    mock_dependency_coordinator,
    mock_executor_registry,
    mock_metrics
):
    """Testar que process_ticket ignora duplicatas (two-phase scheme)."""
    from engine.execution_engine import ExecutionEngine

    # Simular duplicata: exists retorna False (não processado), set retorna False (já em processing)
    mock_redis_client.exists = AsyncMock(return_value=False)
    mock_redis_client.set = AsyncMock(return_value=False)

    engine = ExecutionEngine(
        config=mock_config,
        ticket_client=mock_ticket_client,
        result_producer=mock_result_producer,
        dependency_coordinator=mock_dependency_coordinator,
        executor_registry=mock_executor_registry,
        redis_client=mock_redis_client,
        metrics=mock_metrics
    )

    ticket = {"ticket_id": "ticket-999", "task_type": "BUILD"}

    # Processar ticket duplicado
    await engine.process_ticket(ticket)

    # Verificar que não foi adicionado a active_tasks
    assert "ticket-999" not in engine.active_tasks


@pytest.mark.asyncio
async def test_deduplication_ttl_is_correct(
    mock_config,
    mock_redis_client,
    mock_ticket_client,
    mock_result_producer,
    mock_dependency_coordinator,
    mock_executor_registry
):
    """Testar que o TTL correto é usado na deduplicação (two-phase scheme)."""
    from engine.execution_engine import ExecutionEngine

    mock_redis_client.exists = AsyncMock(return_value=False)
    mock_redis_client.set = AsyncMock(return_value=True)

    engine = ExecutionEngine(
        config=mock_config,
        ticket_client=mock_ticket_client,
        result_producer=mock_result_producer,
        dependency_coordinator=mock_dependency_coordinator,
        executor_registry=mock_executor_registry,
        redis_client=mock_redis_client,
        metrics=None
    )

    await engine._is_duplicate_ticket("ticket-ttl-test")

    # Verificar que set foi chamado com TTL de PROCESSING (600 segundos) na fase 2
    mock_redis_client.set.assert_called_once()
    call_args = mock_redis_client.set.call_args

    # Verificar argumentos - agora usa chave processing com TTL curto
    assert call_args[0][0] == "ticket:processing:ticket-ttl-test"  # key
    assert call_args[0][1] == "1"  # value
    assert call_args[1]['ex'] == 600  # TTL 10 minutos (processing)
    assert call_args[1]['nx'] is True  # Only set if not exists


@pytest.mark.asyncio
async def test_different_tickets_are_not_duplicates(
    mock_config,
    mock_redis_client,
    mock_ticket_client,
    mock_result_producer,
    mock_dependency_coordinator,
    mock_executor_registry
):
    """Testar que tickets diferentes não são considerados duplicatas entre si (two-phase scheme)."""
    from engine.execution_engine import ExecutionEngine

    # exists sempre retorna False (não processado), set sempre retorna True (chave criada)
    mock_redis_client.exists = AsyncMock(return_value=False)
    mock_redis_client.set = AsyncMock(return_value=True)

    engine = ExecutionEngine(
        config=mock_config,
        ticket_client=mock_ticket_client,
        result_producer=mock_result_producer,
        dependency_coordinator=mock_dependency_coordinator,
        executor_registry=mock_executor_registry,
        redis_client=mock_redis_client,
        metrics=None
    )

    # Tickets diferentes - nenhum deve ser duplicata
    is_dup_1 = await engine._is_duplicate_ticket("ticket-A")
    is_dup_2 = await engine._is_duplicate_ticket("ticket-B")
    is_dup_3 = await engine._is_duplicate_ticket("ticket-C")

    assert is_dup_1 is False
    assert is_dup_2 is False
    assert is_dup_3 is False

    # Verificar que Redis set foi chamado 3 vezes com chaves de processing diferentes
    assert mock_redis_client.set.call_count == 3
    calls = mock_redis_client.set.call_args_list
    assert calls[0][0][0] == "ticket:processing:ticket-A"
    assert calls[1][0][0] == "ticket:processing:ticket-B"
    assert calls[2][0][0] == "ticket:processing:ticket-C"


@pytest.mark.asyncio
async def test_concurrent_duplicate_detection(
    mock_config,
    mock_redis_client,
    mock_ticket_client,
    mock_result_producer,
    mock_dependency_coordinator,
    mock_executor_registry
):
    """Testar detecção de duplicata em cenário concorrente (two-phase scheme)."""
    from engine.execution_engine import ExecutionEngine

    # Simular race condition: exists retorna False, primeiro set sucesso, segundo falha
    mock_redis_client.exists = AsyncMock(return_value=False)
    mock_redis_client.set = AsyncMock(side_effect=[True, False])

    engine = ExecutionEngine(
        config=mock_config,
        ticket_client=mock_ticket_client,
        result_producer=mock_result_producer,
        dependency_coordinator=mock_dependency_coordinator,
        executor_registry=mock_executor_registry,
        redis_client=mock_redis_client,
        metrics=None
    )

    # Simular duas chamadas "simultâneas"
    results = await asyncio.gather(
        engine._is_duplicate_ticket("ticket-concurrent"),
        engine._is_duplicate_ticket("ticket-concurrent"),
    )

    # Uma deve passar (False), outra deve detectar duplicata (True)
    assert False in results
    assert True in results
