"""
Testes para os endpoints principais do Memory Layer API.

Cobre health, ready, metrics, query, lineage e quality.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio()
async def test_health_endpoint():
    """Health check deve retornar status healthy."""
    from src.main import health_check

    response = await health_check()

    assert response["status"] == "healthy"


@pytest.mark.asyncio()
async def test_ready_endpoint_all_connected():
    """Readiness check deve retornar ready quando camadas core conectadas."""
    from src.main import app_state, readiness_check

    # Configurar app state
    app_state["redis_client"] = AsyncMock()
    app_state["mongodb_client"] = AsyncMock()
    app_state["neo4j_client"] = AsyncMock()
    app_state["clickhouse_client"] = AsyncMock()
    app_state["kafka_producer"] = None
    app_state["sync_consumer"] = None
    app_state["settings"] = MagicMock(enable_realtime_sync=False)

    response = await readiness_check()

    assert response["ready"] is True
    assert response["layers"]["redis"] == "connected"
    assert response["layers"]["mongodb"] == "connected"


@pytest.mark.asyncio()
async def test_ready_endpoint_missing_core_layer():
    """Readiness check deve retornar not_ready quando camada core falta."""
    from src.main import app_state, readiness_check

    app_state["redis_client"] = AsyncMock()
    app_state["mongodb_client"] = None  # Faltando
    app_state["neo4j_client"] = None
    app_state["clickhouse_client"] = None
    app_state["kafka_producer"] = None
    app_state["sync_consumer"] = None
    app_state["settings"] = MagicMock(enable_realtime_sync=False)

    response = await readiness_check()

    assert response["ready"] is False
    assert response["layers"]["mongodb"] == "disconnected"


@pytest.mark.asyncio()
async def test_ready_endpoint_optional_layers():
    """Readiness check deve aceitar camadas opcionais como not_configured."""
    from src.main import app_state, readiness_check

    app_state["redis_client"] = AsyncMock()
    app_state["mongodb_client"] = AsyncMock()
    app_state["neo4j_client"] = None
    app_state["clickhouse_client"] = None
    app_state["kafka_producer"] = None
    app_state["sync_consumer"] = None
    app_state["settings"] = MagicMock(enable_realtime_sync=False)

    response = await readiness_check()

    assert response["ready"] is True
    assert response["layers"]["neo4j"] == "not_configured"
    assert response["layers"]["clickhouse"] == "not_configured"


@pytest.mark.asyncio()
async def test_ready_endpoint_with_kafka_sync():
    """Readiness check deve verificar Kafka sync quando habilitado."""
    from src.main import app_state, readiness_check

    mock_producer = MagicMock()
    mock_producer.is_running = True
    mock_consumer = MagicMock()
    mock_consumer.is_running = True

    app_state["redis_client"] = AsyncMock()
    app_state["mongodb_client"] = AsyncMock()
    app_state["neo4j_client"] = None
    app_state["clickhouse_client"] = None
    app_state["kafka_producer"] = mock_producer
    app_state["sync_consumer"] = mock_consumer
    app_state["settings"] = MagicMock(enable_realtime_sync=True)

    response = await readiness_check()

    assert response["ready"] is True
    assert response["layers"]["kafka_producer"] == "running"
    assert response["layers"]["kafka_consumer"] == "running"


@pytest.mark.asyncio()
async def test_metrics_endpoint():
    """Metrics endpoint deve retornar metricas Prometheus."""
    from src.main import metrics

    response = await metrics()

    assert response.headers["media_type"] == "text/plain; version=0.0.4"


@pytest.mark.asyncio()
async def test_query_memory_success():
    """Query de memoria deve retornar resultado."""
    from src.main import app_state, query_memory
    from src.models.memory_query import MemoryQueryRequest, QueryType

    mock_client = AsyncMock()
    mock_client.query = AsyncMock(
        return_value={"entity_id": "entity-123", "data": {"key": "value"}, "source": "redis"}
    )

    app_state["unified_client"] = mock_client

    request = MemoryQueryRequest(query_type=QueryType.ENTITY, entity_id="entity-123")

    response = await query_memory(request)

    assert response["entity_id"] == "entity-123"
    assert "data" in response


@pytest.mark.asyncio()
async def test_query_memory_with_cache():
    """Query com use_cache=True deve usar cache."""
    from src.main import app_state, query_memory
    from src.models.memory_query import MemoryQueryRequest, QueryType

    mock_client = AsyncMock()
    mock_client.query = AsyncMock(return_value={"entity_id": "entity-123", "cached": True})

    app_state["unified_client"] = mock_client

    request = MemoryQueryRequest(
        query_type=QueryType.ENTITY, entity_id="entity-123", use_cache=True
    )

    response = await query_memory(request)

    assert response["cached"] is True


@pytest.mark.asyncio()
async def test_query_memory_error_handling():
    """Query deve tratar erros e retornar 500."""
    from fastapi import HTTPException
    from src.main import app_state, query_memory
    from src.models.memory_query import MemoryQueryRequest, QueryType

    mock_client = AsyncMock()
    mock_client.query = AsyncMock(side_effect=Exception("Database error"))

    app_state["unified_client"] = mock_client

    request = MemoryQueryRequest(query_type=QueryType.ENTITY, entity_id="entity-123")

    with pytest.raises(HTTPException) as exc_info:
        await query_memory(request)

    assert exc_info.value.status_code == 500


@pytest.mark.asyncio()
async def test_get_lineage():
    """Obter lineage deve retornar arvore de relacionamentos."""
    from src.main import app_state, get_lineage

    mock_tracker = AsyncMock()
    mock_tracker.get_lineage_tree = AsyncMock(
        return_value={
            "entity_id": "entity-123",
            "depth": 3,
            "ancestors": ["entity-122", "entity-121"],
            "descendants": ["entity-124", "entity-125"],
        }
    )

    app_state["lineage_tracker"] = mock_tracker

    response = await get_lineage("entity-123", depth=3)

    assert response["entity_id"] == "entity-123"
    assert len(response["ancestors"]) == 2


@pytest.mark.asyncio()
async def test_get_quality_stats():
    """Obter stats de qualidade deve retornar metricas."""
    from src.main import app_state, get_quality_stats

    mock_monitor = AsyncMock()
    mock_monitor.get_quality_trends = AsyncMock(
        return_value={
            "completeness": 0.95,
            "accuracy": 0.92,
            "consistency": 0.88,
            "timeliness": 0.90,
        }
    )

    app_state["quality_monitor"] = mock_monitor

    response = await get_quality_stats(data_type="context")

    assert response["data_type"] == "context"
    assert "stats" in response
    assert response["stats"]["completeness"] >= 0.9


@pytest.mark.asyncio()
async def test_invalidate_cache():
    """Invalidar cache deve retornar sucesso."""
    from src.main import app_state, invalidate_cache

    mock_client = AsyncMock()
    mock_client.invalidate_cache = AsyncMock(return_value=True)

    app_state["unified_client"] = mock_client

    response = await invalidate_cache(pattern="entity:*", cascade=False)

    assert response["status"] == "success"
    assert response["pattern"] == "entity:*"
    assert response["cascade"] is False


@pytest.mark.asyncio()
async def test_list_data_assets():
    """Listar assets deve retornar lista de ativos."""
    from src.main import app_state, list_data_assets

    mock_mongo = AsyncMock()
    mock_mongo.find = AsyncMock(
        return_value=[
            {"name": "asset-1", "type": "collection"},
            {"name": "asset-2", "type": "view"},
        ]
    )

    app_state["mongodb_client"] = mock_mongo

    response = await list_data_assets(limit=100, offset=0)

    assert "assets" in response
    assert response["count"] == 2


@pytest.mark.asyncio()
async def test_query_by_time_range():
    """Query por time range deve filtrar corretamente."""
    from datetime import timedelta

    from src.main import app_state, query_memory
    from src.models.memory_query import MemoryQueryRequest, QueryType, TimeRange

    mock_client = AsyncMock()
    mock_client.query = AsyncMock(
        return_value={"entity_id": "entity-123", "data": {"key": "value"}}
    )

    app_state["unified_client"] = mock_client

    end = datetime.now()
    start = end - timedelta(hours=24)

    request = MemoryQueryRequest(
        query_type=QueryType.TIME_SERIES,
        entity_id="entity-123",
        time_range=TimeRange(start=start.isoformat(), end=end.isoformat()),
    )

    response = await query_memory(request)

    assert response["entity_id"] == "entity-123"


@pytest.mark.asyncio()
async def test_global_exception_handler():
    """Handler global de excecao deve retornar 500."""
    from fastapi import Request
    from src.main import global_exception_handler

    request = MagicMock(spec=Request)
    request.url.path = "/api/v1/memory/query"

    exc = Exception("Test error")

    response = await global_exception_handler(request, exc)

    assert response.status_code == 500
    assert "error" in response.body.decode()
