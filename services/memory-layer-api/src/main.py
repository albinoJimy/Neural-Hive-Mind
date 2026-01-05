"""
Memory Layer API - Unified access to multicamadas memory
"""
import asyncio
import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from contextlib import asynccontextmanager
from typing import Dict, Any

from src.config.settings import Settings
from src.clients.clickhouse_client import ClickHouseClient
from src.clients.unified_memory_client import UnifiedMemoryClient
from src.clients.kafka_sync_producer import KafkaSyncProducer
from src.consumers.sync_event_consumer import SyncEventConsumer
from src.services.data_quality_monitor import DataQualityMonitor
from src.services.lineage_tracker import LineageTracker
from src.services.retention_policy_manager import RetentionPolicyManager
from src.models.memory_query import (
    MemoryQueryRequest,
    MemoryQueryResponse,
    QueryType,
    DataQualityMetrics
)

# Configure structured logging
logger = structlog.get_logger(__name__)

# Global state
app_state: Dict[str, Any] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle management for FastAPI app"""
    logger.info("Starting Memory Layer API...")

    # Initialize settings
    settings = Settings()
    app_state['settings'] = settings

    # Initialize observability
    from neural_hive_observability import init_observability
    init_observability(
        service_name='memory-layer-api',
        neural_hive_component='memory-layer',
        neural_hive_layer='conhecimento-dados',
        neural_hive_domain='unified-memory',
        otel_endpoint=settings.otel_endpoint,
    )
    logger.info("Observability initialized")

    # Initialize database clients
    logger.info("Initializing database clients...")

    # Redis client (local implementation)
    from src.clients.redis_client import RedisClient
    redis_client = RedisClient(
        cluster_nodes=settings.redis_cluster_nodes,
        password=settings.redis_password,
        ssl_enabled=settings.redis_ssl_enabled
    )
    await redis_client.initialize()
    app_state['redis_client'] = redis_client
    logger.info("Redis client initialized")

    # MongoDB client (local implementation)
    from src.clients.mongodb_client import MongoDBClient
    mongodb_client = MongoDBClient(
        uri=settings.mongodb_uri,
        database=settings.mongodb_database
    )
    await mongodb_client.initialize()
    app_state['mongodb_client'] = mongodb_client
    logger.info("MongoDB client initialized")

    # Neo4j client (optional for local development)
    neo4j_client = None
    try:
        from src.clients.neo4j_client import Neo4jClient
        neo4j_client = Neo4jClient(
            uri=settings.neo4j_uri,
            user=settings.neo4j_user,
            password=settings.neo4j_password,
            database=settings.neo4j_database,
            encrypted=(settings.environment == 'production')
        )
        await neo4j_client.initialize()
        app_state['neo4j_client'] = neo4j_client
        logger.info("Neo4j client initialized")
    except Exception as e:
        logger.warning("Neo4j initialization failed, continuing without it", error=str(e))
        app_state['neo4j_client'] = None

    # ClickHouse client (optional for local development)
    clickhouse_client = None
    try:
        clickhouse_client = ClickHouseClient(settings)
        await clickhouse_client.initialize()
        app_state['clickhouse_client'] = clickhouse_client
        logger.info("ClickHouse client initialized")
    except Exception as e:
        logger.warning("ClickHouse initialization failed, continuing without it", error=str(e))
        app_state['clickhouse_client'] = None

    # Kafka sync producer (para sincronização em tempo real)
    kafka_producer = None
    if settings.enable_realtime_sync:
        try:
            kafka_producer = KafkaSyncProducer(settings)
            await kafka_producer.start()
            app_state['kafka_producer'] = kafka_producer
            logger.info("Kafka sync producer initialized")
        except Exception as e:
            logger.warning("Kafka producer initialization failed, continuing without it", error=str(e))
            app_state['kafka_producer'] = None

    # Initialize unified memory client (com Kafka producer opcional)
    unified_client = UnifiedMemoryClient(
        redis_client,
        mongodb_client,
        neo4j_client,
        clickhouse_client,
        settings,
        kafka_producer=kafka_producer
    )
    app_state['unified_client'] = unified_client
    logger.info("Unified Memory client initialized")

    # Kafka sync consumer (consome eventos e insere no ClickHouse)
    sync_consumer = None
    if settings.enable_realtime_sync and clickhouse_client:
        try:
            sync_consumer = SyncEventConsumer(
                settings,
                clickhouse_client,
                dlq_producer=kafka_producer  # Usa mesmo producer para DLQ
            )
            await sync_consumer.start()
            app_state['sync_consumer'] = sync_consumer
            logger.info("Kafka sync consumer initialized")
        except Exception as e:
            logger.warning("Kafka consumer initialization failed, continuing without it", error=str(e))
            app_state['sync_consumer'] = None

    # Initialize services
    quality_monitor = DataQualityMonitor(mongodb_client, settings)
    app_state['quality_monitor'] = quality_monitor
    logger.info("Data Quality Monitor initialized")

    lineage_tracker = LineageTracker(mongodb_client, neo4j_client, settings)
    app_state['lineage_tracker'] = lineage_tracker
    logger.info("Lineage Tracker initialized")

    retention_manager = RetentionPolicyManager(
        settings,
        mongodb_client=mongodb_client,
        clickhouse_client=clickhouse_client,
        neo4j_client=neo4j_client
    )
    app_state['retention_manager'] = retention_manager
    logger.info("Retention Policy Manager initialized")

    logger.info("Memory Layer API startup complete")

    yield

    # Shutdown
    logger.info("Shutting down Memory Layer API...")

    # Para Kafka consumer primeiro (graceful shutdown)
    if 'sync_consumer' in app_state and app_state['sync_consumer'] is not None:
        await app_state['sync_consumer'].stop()
        logger.info("Kafka sync consumer stopped")

    # Para Kafka producer
    if 'kafka_producer' in app_state and app_state['kafka_producer'] is not None:
        await app_state['kafka_producer'].stop()
        logger.info("Kafka sync producer stopped")

    if 'clickhouse_client' in app_state and app_state['clickhouse_client'] is not None:
        await app_state['clickhouse_client'].close()
    if 'neo4j_client' in app_state and app_state['neo4j_client'] is not None:
        await app_state['neo4j_client'].close()
    if 'mongodb_client' in app_state and app_state['mongodb_client'] is not None:
        await app_state['mongodb_client'].close()
    if 'redis_client' in app_state and app_state['redis_client'] is not None:
        await app_state['redis_client'].close()

    logger.info("Memory Layer API shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="Memory Layer API",
    description="Unified access to Neural Hive-Mind multicamadas memory (Redis, MongoDB, Neo4j, ClickHouse)",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/health")
async def health_check():
    """Basic health check"""
    return {"status": "healthy"}


@app.get("/ready")
async def readiness_check():
    """Readiness check - verify core memory layers are connected"""
    ready = True
    layers = {}
    settings = app_state.get('settings')

    # Core layers (required)
    for layer in ['redis_client', 'mongodb_client']:
        client = app_state.get(layer)
        if client:
            layers[layer.replace('_client', '')] = "connected"
        else:
            layers[layer.replace('_client', '')] = "disconnected"
            ready = False

    # Optional layers (Neo4j, ClickHouse - don't fail readiness if missing)
    for layer in ['neo4j_client', 'clickhouse_client']:
        client = app_state.get(layer)
        if client:
            layers[layer.replace('_client', '')] = "connected"
        else:
            layers[layer.replace('_client', '')] = "not_configured"

    # Kafka sync status (opcional)
    kafka_producer = app_state.get('kafka_producer')
    sync_consumer = app_state.get('sync_consumer')

    if settings and settings.enable_realtime_sync:
        layers['kafka_producer'] = "running" if (kafka_producer and kafka_producer.is_running) else "not_configured"
        layers['kafka_consumer'] = "running" if (sync_consumer and sync_consumer.is_running) else "not_configured"
    else:
        layers['kafka_producer'] = "disabled"
        layers['kafka_consumer'] = "disabled"

    return {
        "ready": ready,
        "layers": layers
    }


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    from starlette.responses import Response
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/api/v1/memory/query", response_model=MemoryQueryResponse)
async def query_memory(request: MemoryQueryRequest):
    """
    Unified query endpoint with automatic routing to appropriate memory layer
    """
    unified_client = app_state['unified_client']

    try:
        result = await unified_client.query(
            query_type=request.query_type.value,
            entity_id=request.entity_id,
            time_range=request.time_range,
            use_cache=request.use_cache
        )
        return result
    except Exception as e:
        logger.error("Query failed", error=str(e), entity_id=request.entity_id)
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")


@app.get("/api/v1/memory/lineage/{entity_id}")
async def get_lineage(entity_id: str, depth: int = 3):
    """Get data lineage for an entity"""
    lineage_tracker = app_state['lineage_tracker']

    try:
        lineage = await lineage_tracker.get_lineage_tree(
            entity_id=entity_id,
            depth=depth
        )
        return lineage
    except Exception as e:
        logger.error("Lineage query failed", error=str(e), entity_id=entity_id)
        raise HTTPException(status_code=500, detail=f"Lineage query failed: {str(e)}")


@app.get("/api/v1/memory/quality/stats")
async def get_quality_stats(data_type: str = None):
    """Get data quality statistics"""
    quality_monitor = app_state['quality_monitor']

    try:
        stats = await quality_monitor.get_quality_trends(
            data_type=data_type or 'context',
            days=7
        )
        return {"data_type": data_type, "stats": stats}
    except Exception as e:
        logger.error("Quality stats query failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Quality stats failed: {str(e)}")


@app.post("/api/v1/memory/invalidate")
async def invalidate_cache(pattern: str, cascade: bool = False):
    """Invalidate cache entries matching pattern"""
    unified_client = app_state['unified_client']

    try:
        await unified_client.invalidate_cache(pattern=pattern, cascade=cascade)
        return {"status": "success", "pattern": pattern, "cascade": cascade}
    except Exception as e:
        logger.error("Cache invalidation failed", error=str(e), pattern=pattern)
        raise HTTPException(status_code=500, detail=f"Cache invalidation failed: {str(e)}")


@app.get("/api/v1/memory/catalog/assets")
async def list_data_assets(limit: int = 100, offset: int = 0):
    """List cataloged data assets"""
    mongodb_client = app_state['mongodb_client']

    try:
        # Query DataAsset collection (assuming CRDs are mirrored to MongoDB)
        assets = await mongodb_client.find(
            collection='data_assets',
            filter={},
            limit=limit,
            skip=offset
        )
        return {"assets": assets, "count": len(assets)}
    except Exception as e:
        logger.error("Asset catalog query failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Asset catalog failed: {str(e)}")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler"""
    logger.error("Unhandled exception", error=str(exc), path=request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
