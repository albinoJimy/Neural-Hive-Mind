"""
Testes para ClickHouse Fallback Buffer e Fallback Drainer.
"""
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_clickhouse_fallback_buffer_init():
    """ClickHouseFallbackBuffer deve inicializar corretamente."""
    from src.services.clickhouse_fallback_buffer import ClickHouseFallbackBuffer

    mock_redis = AsyncMock()
    mock_settings = MagicMock()
    mock_settings.clickhouse_fallback_buffer_capacity = 100
    mock_settings.clickhouse_fallback_redis_ttl = 86400

    buffer = ClickHouseFallbackBuffer(
        redis_client=mock_redis,
        settings=mock_settings,
        capacity=100,
        redis_ttl_seconds=86400,
    )

    assert buffer.capacity == 100
    assert buffer.redis_ttl == 86400
    assert await buffer.size() == 0
    assert await buffer.is_empty()


@pytest.mark.asyncio
async def test_clickhouse_fallback_buffer_add_event():
    """Buffer deve adicionar eventos corretamente."""
    from src.services.clickhouse_fallback_buffer import ClickHouseFallbackBuffer

    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock()
    mock_settings = MagicMock()

    buffer = ClickHouseFallbackBuffer(
        redis_client=mock_redis,
        settings=mock_settings,
        capacity=10,
    )
    await buffer.initialize()

    rows = [["plan1", "intent1", "domain", datetime.now(timezone.utc)]]
    column_names = ["plan_id", "intent_id", "domain", "created_at"]

    result = await buffer.add_event(
        table="cognitive_plans_history",
        rows=rows,
        column_names=column_names,
    )

    assert result is True
    assert await buffer.size() == 1
    assert not await buffer.is_empty()


@pytest.mark.asyncio
async def test_clickhouse_fallback_buffer_capacity_limit():
    """Buffer deve descartar eventos quando cheio."""
    from src.services.clickhouse_fallback_buffer import ClickHouseFallbackBuffer

    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock()
    mock_settings = MagicMock()

    buffer = ClickHouseFallbackBuffer(
        redis_client=mock_redis,
        settings=mock_settings,
        capacity=2,  # Capacidade pequena
    )
    await buffer.initialize()

    rows = [["plan1", "intent1"]]
    column_names = ["plan_id", "intent_id"]

    # Adiciona até capacidade
    assert await buffer.add_event("test_table", rows, column_names) is True
    assert await buffer.add_event("test_table", rows, column_names) is True

    # Terceiro evento deve ser descartado
    assert await buffer.add_event("test_table", rows, column_names) is False
    assert await buffer.size() == 2  # Capacidade máxima


@pytest.mark.asyncio
async def test_clickhouse_fallback_buffer_take_events():
    """Buffer deve remover eventos corretamente."""
    from src.services.clickhouse_fallback_buffer import ClickHouseFallbackBuffer

    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock()
    mock_settings = MagicMock()

    buffer = ClickHouseFallbackBuffer(
        redis_client=mock_redis,
        settings=mock_settings,
        capacity=10,
    )
    await buffer.initialize()

    rows = [["plan1", "intent1"]]
    column_names = ["plan_id", "intent_id"]

    # Adiciona 3 eventos
    await buffer.add_event("test_table", rows, column_names)
    await buffer.add_event("test_table", rows, column_names)
    await buffer.add_event("test_table", rows, column_names)

    # Remove 2 eventos
    taken = await buffer.take_events(batch_size=2)

    assert len(taken) == 2
    assert await buffer.size() == 1


@pytest.mark.asyncio
async def test_clickhouse_fallback_buffer_get_stats():
    """Buffer deve retornar estatísticas corretas."""
    from src.services.clickhouse_fallback_buffer import ClickHouseFallbackBuffer

    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock()
    mock_settings = MagicMock()

    buffer = ClickHouseFallbackBuffer(
        redis_client=mock_redis,
        settings=mock_settings,
        capacity=10,
    )
    await buffer.initialize()

    rows = [["plan1", "intent1"]]
    column_names = ["plan_id", "intent_id"]

    await buffer.add_event("table1", rows, column_names)
    await buffer.add_event("table1", rows, column_names)
    await buffer.add_event("table2", rows, column_names)

    stats = await buffer.get_stats()

    assert stats["total_events"] == 3
    assert stats["capacity"] == 10
    assert stats["utilization_percent"] == 30.0
    assert stats["table_counts"]["table1"] == 2
    assert stats["table_counts"]["table2"] == 1


@pytest.mark.asyncio
async def test_clickhouse_fallback_buffer_clear():
    """Buffer deve limpar todos os eventos."""
    from src.services.clickhouse_fallback_buffer import ClickHouseFallbackBuffer

    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock()
    mock_settings = MagicMock()

    buffer = ClickHouseFallbackBuffer(
        redis_client=mock_redis,
        settings=mock_settings,
        capacity=10,
    )
    await buffer.initialize()

    rows = [["plan1", "intent1"]]
    column_names = ["plan_id", "intent_id"]

    await buffer.add_event("test_table", rows, column_names)
    await buffer.add_event("test_table", rows, column_names)

    assert await buffer.size() == 2

    await buffer.clear()

    assert await buffer.size() == 0
    assert await buffer.is_empty()


@pytest.mark.asyncio
async def test_fallback_drainer_init():
    """FallbackDrainer deve inicializar corretamente."""
    from src.services.fallback_drainer import FallbackDrainer

    mock_buffer = AsyncMock()
    mock_mongo = AsyncMock()
    mock_settings = MagicMock()

    drainer = FallbackDrainer(
        fallback_buffer=mock_buffer,
        mongodb_client=mock_mongo,
        settings=mock_settings,
        drain_interval_seconds=30,
        batch_size=100,
    )

    assert drainer.buffer == mock_buffer
    assert drainer.mongodb == mock_mongo
    assert drainer.drain_interval == 30
    assert drainer.batch_size == 100
    assert drainer._running is False


@pytest.mark.asyncio
async def test_fallback_drainer_drain_once_empty():
    """Drainer deve retornar stats corretas quando buffer vazio."""
    from src.services.fallback_drainer import FallbackDrainer

    mock_buffer = AsyncMock()
    mock_buffer.take_events = AsyncMock(return_value=[])
    mock_mongo = AsyncMock()
    mock_settings = MagicMock()

    drainer = FallbackDrainer(
        fallback_buffer=mock_buffer,
        mongodb_client=mock_mongo,
        settings=mock_settings,
    )

    result = await drainer.drain_once()

    assert result["events_attempted"] == 0
    assert result["events_success"] == 0
    assert result["events_failed"] == 0


@pytest.mark.asyncio
async def test_fallback_drainer_drain_once_with_events():
    """Drainer deve persistir eventos no MongoDB."""
    from src.services.fallback_drainer import FallbackDrainer

    mock_buffer = AsyncMock()
    event = {
        "table": "cognitive_plans_history",
        "rows": [["plan1", "intent1"]],
        "column_names": ["plan_id", "intent_id"],
        "metadata": {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    mock_buffer.take_events = AsyncMock(return_value=[event])

    mock_mongo = AsyncMock()
    mock_mongo.insert_one = AsyncMock()

    mock_settings = MagicMock()

    drainer = FallbackDrainer(
        fallback_buffer=mock_buffer,
        mongodb_client=mock_mongo,
        settings=mock_settings,
    )

    result = await drainer.drain_once()

    assert result["events_attempted"] == 1
    assert result["events_success"] == 1
    assert result["events_failed"] == 0

    # Verifica que insert_one foi chamado
    mock_mongo.insert_one.assert_called_once()


@pytest.mark.asyncio
async def test_fallback_drainer_get_stats():
    """Drainer deve retornar estatísticas."""
    from src.services.fallback_drainer import FallbackDrainer

    mock_buffer = AsyncMock()
    mock_buffer.get_stats = AsyncMock(
        return_value={
            "total_events": 10,
            "capacity": 100,
            "utilization_percent": 10.0,
        }
    )

    mock_mongo = AsyncMock()
    mock_mongo.count = AsyncMock(return_value=5)

    mock_settings = MagicMock()

    drainer = FallbackDrainer(
        fallback_buffer=mock_buffer,
        mongodb_client=mock_mongo,
        settings=mock_settings,
        drain_interval_seconds=30,
        batch_size=100,
    )

    stats = await drainer.get_stats()

    assert stats["running"] is False
    assert stats["drain_interval_seconds"] == 30
    assert stats["batch_size"] == 100
    assert stats["buffer_stats"]["total_events"] == 10
    assert stats["pending_drain_in_mongodb"] == 5


@pytest.mark.asyncio
async def test_unified_memory_client_clickhouse_fallback():
    """UnifiedMemoryClient deve usar fallback quando ClickHouse falha."""
    from src.clients.unified_memory_client import UnifiedMemoryClient

    mock_redis = AsyncMock()
    mock_mongo = AsyncMock()
    mock_neo4j = AsyncMock()
    mock_clickhouse = AsyncMock()
    mock_settings = MagicMock()
    mock_kafka = AsyncMock()
    mock_fallback_buffer = AsyncMock()

    # ClickHouse falha
    mock_clickhouse.insert_batch = AsyncMock(side_effect=Exception("ClickHouse unavailable"))

    # Fallback buffer sucesso
    mock_fallback_buffer.add_event = AsyncMock(return_value=True)

    client = UnifiedMemoryClient(
        redis_client=mock_redis,
        mongodb_client=mock_mongo,
        neo4j_client=mock_neo4j,
        clickhouse_client=mock_clickhouse,
        settings=mock_settings,
        kafka_producer=mock_kafka,
        fallback_buffer=mock_fallback_buffer,
    )

    result = await client.insert_clickhouse_with_fallback(
        table="cognitive_plans_history",
        rows=[["plan1", "intent1"]],
        column_names=["plan_id", "intent_id"],
    )

    assert result is True
    # Verifica que fallback buffer foi chamado
    mock_fallback_buffer.add_event.assert_called_once()


@pytest.mark.asyncio
async def test_unified_memory_client_insert_cognitive_plan_history():
    """UnifiedMemoryClient deve inserir plano histórico com fallback."""
    from src.clients.unified_memory_client import UnifiedMemoryClient

    mock_redis = AsyncMock()
    mock_mongo = AsyncMock()
    mock_neo4j = AsyncMock()
    mock_clickhouse = AsyncMock()
    mock_settings = MagicMock()
    mock_kafka = AsyncMock()
    mock_fallback_buffer = AsyncMock()

    # ClickHouse funciona
    mock_clickhouse.insert_batch = AsyncMock(return_value=True)
    mock_fallback_buffer.add_event = AsyncMock(return_value=True)

    client = UnifiedMemoryClient(
        redis_client=mock_redis,
        mongodb_client=mock_mongo,
        neo4j_client=mock_neo4j,
        clickhouse_client=mock_clickhouse,
        settings=mock_settings,
        kafka_producer=mock_kafka,
        fallback_buffer=mock_fallback_buffer,
    )

    plan = {
        "plan_id": "plan123",
        "intent_id": "intent456",
        "domain": "business",
        "risk_score": 0.5,
        "complexity_score": 0.3,
        "plan_data": {"key": "value"},
        "metadata": {},
    }

    result = await client.insert_cognitive_plan_history(plan)

    assert result is True
    mock_clickhouse.insert_batch.assert_called_once()


@pytest.mark.asyncio
async def test_unified_memory_client_insert_consensus_decision_history():
    """UnifiedMemoryClient deve inserir decisão de consenso com fallback."""
    from src.clients.unified_memory_client import UnifiedMemoryClient

    mock_redis = AsyncMock()
    mock_mongo = AsyncMock()
    mock_neo4j = AsyncMock()
    mock_clickhouse = AsyncMock()
    mock_settings = MagicMock()
    mock_kafka = AsyncMock()
    mock_fallback_buffer = AsyncMock()

    mock_clickhouse.insert_batch = AsyncMock(return_value=True)

    client = UnifiedMemoryClient(
        redis_client=mock_redis,
        mongodb_client=mock_mongo,
        neo4j_client=mock_neo4j,
        clickhouse_client=mock_clickhouse,
        settings=mock_settings,
        kafka_producer=mock_kafka,
        fallback_buffer=mock_fallback_buffer,
    )

    decision = {
        "decision_id": "dec123",
        "plan_id": "plan456",
        "aggregated_confidence": 0.85,
        "consensus_type": "hierarchical",
        "decision_data": {"key": "value"},
        "metadata": {},
    }

    result = await client.insert_consensus_decision_history(decision)

    assert result is True
    mock_clickhouse.insert_batch.assert_called_once()


@pytest.mark.asyncio
async def test_unified_memory_client_insert_specialist_opinion_history():
    """UnifiedMemoryClient deve inserir opinião de especialista com fallback."""
    from src.clients.unified_memory_client import UnifiedMemoryClient

    mock_redis = AsyncMock()
    mock_mongo = AsyncMock()
    mock_neo4j = AsyncMock()
    mock_clickhouse = AsyncMock()
    mock_settings = MagicMock()
    mock_kafka = AsyncMock()
    mock_fallback_buffer = AsyncMock()

    mock_clickhouse.insert_batch = AsyncMock(return_value=True)

    client = UnifiedMemoryClient(
        redis_client=mock_redis,
        mongodb_client=mock_mongo,
        neo4j_client=mock_neo4j,
        clickhouse_client=mock_clickhouse,
        settings=mock_settings,
        kafka_producer=mock_kafka,
        fallback_buffer=mock_fallback_buffer,
    )

    opinion = {
        "opinion_id": "op123",
        "specialist_type": "business",
        "plan_id": "plan456",
        "confidence_score": 0.75,
        "opinion_data": {"key": "value"},
        "metadata": {},
    }

    result = await client.insert_specialist_opinion_history(opinion)

    assert result is True
    mock_clickhouse.insert_batch.assert_called_once()
