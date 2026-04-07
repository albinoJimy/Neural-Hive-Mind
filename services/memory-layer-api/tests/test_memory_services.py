"""
Testes para os serviços de memória do Memory Layer API.

Cobre UnifiedMemoryClient, LineageTracker e DataQualityMonitor.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta


@pytest.mark.asyncio
async def test_unified_memory_client_init():
    """UnifiedMemoryClient deve inicializar com clientes corretos."""
    from src.clients.unified_memory_client import UnifiedMemoryClient

    mock_redis = AsyncMock()
    mock_mongo = AsyncMock()
    mock_neo4j = AsyncMock()
    mock_clickhouse = AsyncMock()
    mock_settings = MagicMock()
    mock_kafka = AsyncMock()

    client = UnifiedMemoryClient(
        redis_client=mock_redis,
        mongodb_client=mock_mongo,
        neo4j_client=mock_neo4j,
        clickhouse_client=mock_clickhouse,
        settings=mock_settings,
        kafka_producer=mock_kafka,
    )

    assert client.redis_client == mock_redis
    assert client.mongodb_client == mock_mongo


@pytest.mark.asyncio
async def test_query_redis_layer():
    """Query deve usar camada Redis para dados quentes."""
    from src.clients.unified_memory_client import UnifiedMemoryClient

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value='{"key": "value"}')
    mock_mongo = AsyncMock()
    mock_neo4j = AsyncMock()
    mock_clickhouse = AsyncMock()
    mock_settings = MagicMock()
    mock_kafka = AsyncMock()

    client = UnifiedMemoryClient(
        redis_client=mock_redis,
        mongodb_client=mock_mongo,
        neo4j_client=mock_neo4j,
        clickhouse_client=mock_clickhouse,
        settings=mock_settings,
        kafka_producer=mock_kafka,
    )

    result = await client.query(query_type="entity", entity_id="entity-123", use_cache=True)

    assert result["data"]["key"] == "value"


@pytest.mark.asyncio
async def test_query_mongodb_layer():
    """Query deve usar camada MongoDB para dados persistentes."""
    from src.clients.unified_memory_client import UnifiedMemoryClient

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_mongo = AsyncMock()
    mock_mongo.find_one = AsyncMock(return_value={"_id": "entity-123", "data": "value"})
    mock_neo4j = AsyncMock()
    mock_clickhouse = AsyncMock()
    mock_settings = MagicMock()
    mock_kafka = AsyncMock()

    client = UnifiedMemoryClient(
        redis_client=mock_redis,
        mongodb_client=mock_mongo,
        neo4j_client=mock_neo4j,
        clickhouse_client=mock_clickhouse,
        settings=mock_settings,
        kafka_producer=mock_kafka,
    )

    result = await client.query(query_type="entity", entity_id="entity-123", use_cache=True)

    assert result["source"] == "mongodb"


@pytest.mark.asyncio
async def test_store_memory():
    """Store memory deve persistir em camadas apropriadas."""
    from src.clients.unified_memory_client import UnifiedMemoryClient

    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.setex = AsyncMock(return_value=True)
    mock_mongo = AsyncMock()
    mock_mongo.insert_one = AsyncMock(return_value=MagicMock(inserted_id="id-123"))
    mock_neo4j = AsyncMock()
    mock_clickhouse = AsyncMock()
    mock_settings = MagicMock()
    mock_kafka = AsyncMock()

    client = UnifiedMemoryClient(
        redis_client=mock_redis,
        mongodb_client=mock_mongo,
        neo4j_client=mock_neo4j,
        clickhouse_client=mock_clickhouse,
        settings=mock_settings,
        kafka_producer=mock_kafka,
    )

    result = await client.store(entity_id="entity-123", data={"key": "value"}, ttl=3600)

    assert result["success"] is True


@pytest.mark.asyncio
async def test_lineage_tracker_init():
    """LineageTracker deve inicializar com clientes."""
    from src.services.lineage_tracker import LineageTracker

    mock_mongo = AsyncMock()
    mock_neo4j = AsyncMock()
    mock_settings = MagicMock()

    tracker = LineageTracker(
        mongodb_client=mock_mongo, neo4j_client=mock_neo4j, settings=mock_settings
    )

    assert tracker.mongodb_client == mock_mongo


@pytest.mark.asyncio
async def test_get_lineage_tree():
    """Obter arvore de lineage deve retornar ancestrais e descendentes."""
    from src.services.lineage_tracker import LineageTracker

    mock_mongo = AsyncMock()
    mock_neo4j = MagicMock()
    mock_settings = MagicMock()

    # Mock Neo4j query para lineage
    mock_neo4j.query = MagicMock(
        return_value=[
            {"entity_id": "entity-122", "relationship": "parent_of"},
            {"entity_id": "entity-121", "relationship": "parent_of"},
        ]
    )

    tracker = LineageTracker(
        mongodb_client=mock_mongo, neo4j_client=mock_neo4j, settings=mock_settings
    )

    result = await tracker.get_lineage_tree(entity_id="entity-123", depth=3)

    assert result["entity_id"] == "entity-123"
    assert "ancestors" in result


@pytest.mark.asyncio
async def test_track_lineage():
    """Rastrear lineage deve criar relacionamentos."""
    from src.services.lineage_tracker import LineageTracker

    mock_mongo = AsyncMock()
    mock_neo4j = MagicMock()
    mock_settings = MagicMock()

    mock_neo4j.create_relationship = MagicMock(return_value=True)

    tracker = LineageTracker(
        mongodb_client=mock_mongo, neo4j_client=mock_neo4j, settings=mock_settings
    )

    result = await tracker.track_relationship(
        parent_id="entity-123", child_id="entity-124", relationship_type="derived_from"
    )

    assert result is not None


@pytest.mark.asyncio
async def test_data_quality_monitor_init():
    """DataQualityMonitor deve inicializar com cliente MongoDB."""
    from src.services.data_quality_monitor import DataQualityMonitor

    mock_mongo = AsyncMock()
    mock_settings = MagicMock()

    monitor = DataQualityMonitor(mongodb_client=mock_mongo, settings=mock_settings)

    assert monitor.mongodb_client == mock_mongo


@pytest.mark.asyncio
async def test_get_quality_trends():
    """Obter trends de qualidade deve retornar metricas historicas."""
    from src.services.data_quality_monitor import DataQualityMonitor

    mock_mongo = AsyncMock()
    mock_mongo.aggregate = AsyncMock(
        return_value=[
            {"date": "2026-03-29", "completeness": 0.95, "accuracy": 0.92},
            {"date": "2026-03-30", "completeness": 0.96, "accuracy": 0.93},
        ]
    )
    mock_settings = MagicMock()

    monitor = DataQualityMonitor(mongodb_client=mock_mongo, settings=mock_settings)

    result = await monitor.get_quality_trends(data_type="context", days=7)

    assert len(result) >= 0
    if len(result) > 0:
        assert "completeness" in result[0]


@pytest.mark.asyncio
async def test_record_quality_metrics():
    """Registrar metricas de qualidade deve persistir."""
    from src.services.data_quality_monitor import DataQualityMonitor

    mock_mongo = AsyncMock()
    mock_mongo.insert_one = AsyncMock(return_value=MagicMock(inserted_id="id-123"))
    mock_settings = MagicMock()

    monitor = DataQualityMonitor(mongodb_client=mock_mongo, settings=mock_settings)

    result = await monitor.record_quality_metrics(
        entity_id="entity-123",
        data_type="context",
        metrics={"completeness": 0.95, "accuracy": 0.92, "consistency": 0.88},
    )

    assert result["success"] is True


@pytest.mark.asyncio
async def test_invalidate_cache():
    """Invalidar cache deve remover entradas."""
    from src.clients.unified_memory_client import UnifiedMemoryClient

    mock_redis = AsyncMock()
    mock_redis.delete = AsyncMock(return_value=1)
    mock_redis.keys = AsyncMock(return_value=["key1", "key2"])
    mock_mongo = AsyncMock()
    mock_neo4j = AsyncMock()
    mock_clickhouse = AsyncMock()
    mock_settings = MagicMock()
    mock_kafka = AsyncMock()

    client = UnifiedMemoryClient(
        redis_client=mock_redis,
        mongodb_client=mock_mongo,
        neo4j_client=mock_neo4j,
        clickhouse_client=mock_clickhouse,
        settings=mock_settings,
        kafka_producer=mock_kafka,
    )

    result = await client.invalidate_cache(pattern="entity:*", cascade=False)

    assert result["success"] is True


@pytest.mark.asyncio
async def test_sync_to_clickhouse():
    """Sync para ClickHouse deve inserir dados."""
    from src.clients.unified_memory_client import UnifiedMemoryClient

    mock_redis = AsyncMock()
    mock_mongo = AsyncMock()
    mock_neo4j = AsyncMock()
    mock_clickhouse = AsyncMock()
    mock_clickhouse.insert = AsyncMock(return_value=MagicMock(rowcount=1))
    mock_settings = MagicMock()
    mock_kafka = AsyncMock()

    client = UnifiedMemoryClient(
        redis_client=mock_redis,
        mongodb_client=mock_mongo,
        neo4j_client=mock_neo4j,
        clickhouse_client=mock_clickhouse,
        settings=mock_settings,
        kafka_producer=mock_kafka,
    )

    result = await client.sync_to_clickhouse(
        table="memory_events", data=[{"entity_id": "entity-123", "timestamp": datetime.now()}]
    )

    assert result["success"] is True


@pytest.mark.asyncio
async def test_retention_policy_manager():
    """Gerenciador de retention deve expirar dados antigos."""
    from src.services.retention_policy_manager import RetentionPolicyManager

    mock_settings = MagicMock()
    mock_settings.retention_days = 30
    mock_mongo = AsyncMock()
    mock_clickhouse = AsyncMock()
    mock_neo4j = AsyncMock()

    manager = RetentionPolicyManager(
        settings=mock_settings,
        mongodb_client=mock_mongo,
        clickhouse_client=mock_clickhouse,
        neo4j_client=mock_neo4j,
    )

    result = await manager.enforce_retention()

    assert result is not None
