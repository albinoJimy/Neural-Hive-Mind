from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import structlog

from src.config.settings import get_settings
from neural_hive_observability.health import HealthStatus

logger = structlog.get_logger()
router = APIRouter(prefix="", tags=["health"])


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    service: str
    version: str


class ReadinessResponse(BaseModel):
    """Readiness check response."""

    status: str
    ready: bool
    checks: dict


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Basic health check."""
    settings = get_settings()
    return HealthResponse(status="healthy", service=settings.service_name, version=settings.service_version)


@router.get("/health/ready", response_model=ReadinessResponse, status_code=status.HTTP_200_OK)
async def readiness_check():
    """Readiness probe for Kubernetes."""
    from src import main as app_main

    checks = {}

    # Verificar MongoDB
    try:
        if app_main.mongodb_client and app_main.mongodb_client.client:
            checks["mongodb"] = "connected"
        else:
            checks["mongodb"] = "disconnected"
    except Exception as e:
        logger.warning("mongodb_health_check_failed", error=str(e))
        checks["mongodb"] = "disconnected"

    # Verificar Redis (com ping)
    try:
        if app_main.redis_client and app_main.redis_client.client:
            await app_main.redis_client.client.ping()
            checks["redis"] = "connected"
        else:
            checks["redis"] = "disconnected"
    except Exception as e:
        logger.warning("redis_health_check_failed", error=str(e))
        checks["redis"] = "disconnected"

    # Verificar Kafka consumer (insights) - valida conexão ativa
    try:
        if app_main.insights_consumer and app_main.insights_consumer.consumer:
            # Verifica se consumer está conectado listando tópicos (chamada leve)
            cluster_metadata = app_main.insights_consumer.consumer.list_topics(timeout=5.0)
            if cluster_metadata and cluster_metadata.brokers:
                checks["kafka_consumer"] = "connected"
            else:
                checks["kafka_consumer"] = "disconnected"
        else:
            checks["kafka_consumer"] = "disconnected"
    except Exception as e:
        logger.warning("kafka_consumer_health_check_failed", error=str(e))
        checks["kafka_consumer"] = "disconnected"

    # Verificar Kafka producer - valida conexão ativa
    try:
        if app_main.optimization_producer and app_main.optimization_producer.producer:
            # Verifica se producer está conectado listando tópicos (chamada leve)
            cluster_metadata = app_main.optimization_producer.producer.list_topics(timeout=5.0)
            if cluster_metadata and cluster_metadata.brokers:
                checks["kafka_producer"] = "connected"
            else:
                checks["kafka_producer"] = "disconnected"
        else:
            checks["kafka_producer"] = "disconnected"
    except Exception as e:
        logger.warning("kafka_producer_health_check_failed", error=str(e))
        checks["kafka_producer"] = "disconnected"

    # Verificar gRPC client (consensus engine)
    try:
        if app_main.consensus_engine_client and app_main.consensus_engine_client.channel:
            checks["grpc_consensus"] = "connected"
        else:
            checks["grpc_consensus"] = "disconnected"
    except Exception as e:
        logger.warning("grpc_consensus_health_check_failed", error=str(e))
        checks["grpc_consensus"] = "disconnected"

    # Verificar gRPC client (orchestrator)
    try:
        if app_main.orchestrator_client and app_main.orchestrator_client.channel:
            checks["grpc_orchestrator"] = "connected"
        else:
            checks["grpc_orchestrator"] = "disconnected"
    except Exception as e:
        logger.warning("grpc_orchestrator_health_check_failed", error=str(e))
        checks["grpc_orchestrator"] = "disconnected"

    # Verificar ClickHouse schema health check
    clickhouse_healthy = True
    try:
        if app_main.health_checker:
            ch_result = await app_main.health_checker.check_single("clickhouse_schema")
            if ch_result:
                if ch_result.status == HealthStatus.HEALTHY:
                    checks["clickhouse_schema"] = "healthy"
                elif ch_result.status == HealthStatus.DEGRADED:
                    checks["clickhouse_schema"] = "degraded"
                    clickhouse_healthy = False
                else:
                    checks["clickhouse_schema"] = "unhealthy"
                    clickhouse_healthy = False
            else:
                checks["clickhouse_schema"] = "not_configured"
        else:
            checks["clickhouse_schema"] = "not_configured"
    except Exception as e:
        logger.warning("clickhouse_schema_health_check_failed", error=str(e))
        checks["clickhouse_schema"] = "unhealthy"
        clickhouse_healthy = False

    all_ready = all(v == "connected" for v in checks.values() if v != "not_configured" and v not in ["healthy", "degraded", "unhealthy"])
    all_ready = all_ready and clickhouse_healthy

    if not all_ready:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "not_ready", "ready": False, "checks": checks}
        )

    return ReadinessResponse(status="ready" if all_ready else "not_ready", ready=all_ready, checks=checks)


@router.get("/health/live")
async def liveness_check():
    """Liveness probe for Kubernetes."""
    return {"status": "alive"}
