import time
from datetime import UTC, datetime
from typing import Any

import psutil
import structlog
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from neural_hive_observability.health import HealthStatus
from pydantic import BaseModel

from src.config.settings import get_settings

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


# === Expanded Health Check Models ===


class ResourceMetrics(BaseModel):
    """Resource usage metrics."""

    cpu_percent: float
    memory_percent: float
    memory_mb: float
    disk_usage_percent: float
    open_file_descriptors: int
    uptime_seconds: float


class ServiceDependencyHealth(BaseModel):
    """Detailed health of a service dependency."""

    name: str
    status: str  # healthy, degraded, unhealthy, unknown
    latency_ms: float | None
    error: str | None
    details: dict[str, Any] | None


class DeepHealthResponse(BaseModel):
    """Deep health diagnostics response."""

    status: str
    service: str
    version: str
    timestamp: str
    uptime_seconds: float
    resources: ResourceMetrics
    dependencies: list[ServiceDependencyHealth]
    ml_models: dict[str, Any]
    checks: dict[str, str]


class StartupResponse(BaseModel):
    """Startup probe response."""

    status: str
    service: str
    version: str
    started_at: str


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Basic health check."""
    settings = get_settings()
    return HealthResponse(
        status="healthy", service=settings.service_name, version=settings.service_version
    )


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

    all_ready = all(
        v == "connected"
        for v in checks.values()
        if v != "not_configured" and v not in ["healthy", "degraded", "unhealthy"]
    )
    all_ready = all_ready and clickhouse_healthy

    if not all_ready:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "not_ready", "ready": False, "checks": checks},
        )

    return ReadinessResponse(
        status="ready" if all_ready else "not_ready", ready=all_ready, checks=checks
    )


@router.get("/health/live")
async def liveness_check():
    """Liveness probe for Kubernetes."""
    return {"status": "alive"}


# === Expanded Health Checks ===


@router.get("/health/startup", response_model=StartupResponse, status_code=status.HTTP_200_OK)
async def startup_check():
    """
    Startup probe for Kubernetes.

    Indicates when the service is ready to accept traffic.
    Returns success only after initialization is complete.
    """
    from src import main as app_main

    settings = get_settings()

    # Verificar se inicialização está completa
    is_started = getattr(app_main, "_startup_complete", False)

    status_code = status.HTTP_200_OK if is_started else status.HTTP_503_SERVICE_UNAVAILABLE

    return JSONResponse(
        status_code=status_code,
        content={
            "status": "started" if is_started else "starting",
            "service": settings.service_name,
            "version": settings.service_version,
            "started_at": getattr(app_main, "_started_at", None),
        },
    )


@router.get("/health/deep", response_model=DeepHealthResponse, status_code=status.HTTP_200_OK)
async def deep_health_check():
    """
    Deep health diagnostics with resource metrics and detailed dependency status.

    Provides comprehensive health information including:
    - Resource usage (CPU, memory, disk, file descriptors)
    - Dependency health with latency measurements
    - ML model status
    - Service uptime
    """
    from src import main as app_main

    settings = get_settings()
    start_time = getattr(app_main, "_start_time", time.time())

    # Resource metrics
    process = psutil.Process()
    cpu_percent = process.cpu_percent(interval=0.1)
    memory_info = process.memory_info()
    memory_mb = memory_info.rss / 1024 / 1024
    memory_percent = process.memory_percent()
    disk_usage = psutil.disk_usage("/")
    disk_usage_percent = disk_usage.percent
    open_fds = process.num_fds()

    try:
        boot_time = psutil.boot_time()
        uptime = time.time() - boot_time
    except Exception:
        uptime = 0

    resources = ResourceMetrics(
        cpu_percent=round(cpu_percent, 2),
        memory_percent=round(memory_percent, 2),
        memory_mb=round(memory_mb, 2),
        disk_usage_percent=round(disk_usage_percent, 2),
        open_file_descriptors=open_fds,
        uptime_seconds=round(uptime, 2),
    )

    # Dependency health with latency
    dependencies = []

    # MongoDB
    mongo_health = await _check_mongodb_with_latency(app_main)
    dependencies.append(mongo_health)

    # Redis
    redis_health = await _check_redis_with_latency(app_main)
    dependencies.append(redis_health)

    # Kafka consumer
    kafka_consumer_health = await _check_kafka_consumer_with_latency(app_main)
    dependencies.append(kafka_consumer_health)

    # Kafka producer
    kafka_producer_health = await _check_kafka_producer_with_latency(app_main)
    dependencies.append(kafka_producer_health)

    # gRPC clients
    grpc_consensus_health = await _check_grpc_consensus_with_latency(app_main)
    dependencies.append(grpc_consensus_health)

    grpc_orchestrator_health = await _check_grpc_orchestrator_with_latency(app_main)
    dependencies.append(grpc_orchestrator_health)

    # ClickHouse
    clickhouse_health = await _check_clickhouse_with_latency(app_main)
    dependencies.append(clickhouse_health)

    # ML Models status
    ml_models = await _check_ml_models(app_main)

    # Overall status
    all_healthy = all(dep.status in ["healthy", "degraded"] for dep in dependencies)
    overall_status = "healthy" if all_healthy else "unhealthy"

    # Determine HTTP status code
    status_code = (
        status.HTTP_200_OK if overall_status == "healthy" else status.HTTP_503_SERVICE_UNAVAILABLE
    )

    return JSONResponse(
        status_code=status_code,
        content={
            "status": overall_status,
            "service": settings.service_name,
            "version": settings.service_version,
            "timestamp": datetime.now(UTC).isoformat(),
            "uptime_seconds": round(time.time() - start_time, 2),
            "resources": resources.dict(),
            "dependencies": [dep.dict() for dep in dependencies],
            "ml_models": ml_models,
            "checks": {dep.name: dep.status for dep in dependencies},
        },
    )


async def _check_mongodb_with_latency(app_main) -> ServiceDependencyHealth:
    """Check MongoDB health with latency measurement."""
    start = time.time()
    try:
        if app_main.mongodb_client and app_main.mongodb_client.client:
            # Ping com timeout
            await app_main.mongodb_client.client.admin.command("ping", timeout=5.0)
            latency_ms = (time.time() - start) * 1000

            status = "healthy" if latency_ms < 100 else "degraded"
            return ServiceDependencyHealth(
                name="mongodb",
                status=status,
                latency_ms=round(latency_ms, 2),
                error=None,
                details={"latency_ms": round(latency_ms, 2)},
            )
    except Exception as e:
        logger.warning("mongodb_deep_health_check_failed", error=str(e))
        return ServiceDependencyHealth(
            name="mongodb",
            status="unhealthy",
            latency_ms=None,
            error=str(e),
            details=None,
        )

    return ServiceDependencyHealth(
        name="mongodb",
        status="unknown",
        latency_ms=None,
        error="not_initialized",
        details=None,
    )


async def _check_redis_with_latency(app_main) -> ServiceDependencyHealth:
    """Check Redis health with latency measurement."""
    start = time.time()
    try:
        if app_main.redis_client and app_main.redis_client.client:
            await app_main.redis_client.client.ping()
            latency_ms = (time.time() - start) * 1000

            status = "healthy" if latency_ms < 50 else "degraded"
            return ServiceDependencyHealth(
                name="redis",
                status=status,
                latency_ms=round(latency_ms, 2),
                error=None,
                details={"latency_ms": round(latency_ms, 2)},
            )
    except Exception as e:
        logger.warning("redis_deep_health_check_failed", error=str(e))
        return ServiceDependencyHealth(
            name="redis",
            status="unhealthy",
            latency_ms=None,
            error=str(e),
            details=None,
        )

    return ServiceDependencyHealth(
        name="redis",
        status="unknown",
        latency_ms=None,
        error="not_initialized",
        details=None,
    )


async def _check_kafka_consumer_with_latency(app_main) -> ServiceDependencyHealth:
    """Check Kafka consumer health with latency measurement."""
    start = time.time()
    try:
        if app_main.insights_consumer and app_main.insights_consumer.consumer:
            cluster_metadata = app_main.insights_consumer.consumer.list_topics(timeout=5.0)
            latency_ms = (time.time() - start) * 1000

            if cluster_metadata and cluster_metadata.brokers:
                status = "healthy" if latency_ms < 200 else "degraded"
                return ServiceDependencyHealth(
                    name="kafka_consumer",
                    status=status,
                    latency_ms=round(latency_ms, 2),
                    error=None,
                    details={
                        "brokers": len(cluster_metadata.brokers),
                        "latency_ms": round(latency_ms, 2),
                    },
                )
    except Exception as e:
        logger.warning("kafka_consumer_deep_health_check_failed", error=str(e))
        return ServiceDependencyHealth(
            name="kafka_consumer",
            status="unhealthy",
            latency_ms=None,
            error=str(e),
            details=None,
        )

    return ServiceDependencyHealth(
        name="kafka_consumer",
        status="unknown",
        latency_ms=None,
        error="not_initialized",
        details=None,
    )


async def _check_kafka_producer_with_latency(app_main) -> ServiceDependencyHealth:
    """Check Kafka producer health with latency measurement."""
    start = time.time()
    try:
        if app_main.optimization_producer and app_main.optimization_producer.producer:
            cluster_metadata = app_main.optimization_producer.producer.list_topics(timeout=5.0)
            latency_ms = (time.time() - start) * 1000

            if cluster_metadata and cluster_metadata.brokers:
                status = "healthy" if latency_ms < 200 else "degraded"
                return ServiceDependencyHealth(
                    name="kafka_producer",
                    status=status,
                    latency_ms=round(latency_ms, 2),
                    error=None,
                    details={
                        "brokers": len(cluster_metadata.brokers),
                        "latency_ms": round(latency_ms, 2),
                    },
                )
    except Exception as e:
        logger.warning("kafka_producer_deep_health_check_failed", error=str(e))
        return ServiceDependencyHealth(
            name="kafka_producer",
            status="unhealthy",
            latency_ms=None,
            error=str(e),
            details=None,
        )

    return ServiceDependencyHealth(
        name="kafka_producer",
        status="unknown",
        latency_ms=None,
        error="not_initialized",
        details=None,
    )


async def _check_grpc_consensus_with_latency(app_main) -> ServiceDependencyHealth:
    """Check gRPC consensus engine health with latency measurement."""
    start = time.time()
    try:
        if app_main.consensus_engine_client and app_main.consensus_engine_client.channel:
            # Try a simple call to check connectivity
            # TODO: Adicionar dependência grpcio-health ao requirements.txt
            try:
                from grpc.health.v1 import health, health_pb2

                stub = health.HealthStub(app_main.consensus_engine_client.channel)
                response = await stub.check(health_pb2.HealthCheckRequest(), timeout=5.0)
                latency_ms = (time.time() - start) * 1000

                grpc_status = response.status.name
                status = "healthy" if grpc_status == "SERVING" else "degraded"

                return ServiceDependencyHealth(
                    name="grpc_consensus",
                    status=status,
                    latency_ms=round(latency_ms, 2),
                    error=None,
                    details={"grpc_status": grpc_status, "latency_ms": round(latency_ms, 2)},
                )
            except ImportError:
                # Fallback: verificar apenas conectividade básica do canal
                latency_ms = (time.time() - start) * 1000
                grpc_status = "UNKNOWN_NO_HEALTH_CHECK"

                return ServiceDependencyHealth(
                    name="grpc_consensus",
                    status="degraded",
                    latency_ms=round(latency_ms, 2),
                    error="grpcio-health not installed, using fallback check",
                    details={"grpc_status": grpc_status, "latency_ms": round(latency_ms, 2)},
                )
    except Exception as e:
        logger.warning("grpc_consensus_deep_health_check_failed", error=str(e))
        return ServiceDependencyHealth(
            name="grpc_consensus",
            status="unhealthy",
            latency_ms=None,
            error=str(e),
            details=None,
        )

    return ServiceDependencyHealth(
        name="grpc_consensus",
        status="unknown",
        latency_ms=None,
        error="not_initialized",
        details=None,
    )


async def _check_grpc_orchestrator_with_latency(app_main) -> ServiceDependencyHealth:
    """Check gRPC orchestrator health with latency measurement."""
    start = time.time()
    try:
        if app_main.orchestrator_client and app_main.orchestrator_client.channel:
            # Try a simple call to check connectivity
            # TODO: Adicionar dependência grpcio-health ao requirements.txt
            try:
                from grpc.health.v1 import health, health_pb2

                stub = health.HealthStub(app_main.orchestrator_client.channel)
                response = await stub.check(health_pb2.HealthCheckRequest(), timeout=5.0)
                latency_ms = (time.time() - start) * 1000

                grpc_status = response.status.name
                status = "healthy" if grpc_status == "SERVING" else "degraded"

                return ServiceDependencyHealth(
                    name="grpc_orchestrator",
                    status=status,
                    latency_ms=round(latency_ms, 2),
                    error=None,
                    details={"grpc_status": grpc_status, "latency_ms": round(latency_ms, 2)},
                )
            except ImportError:
                # Fallback: verificar apenas conectividade básica do canal
                latency_ms = (time.time() - start) * 1000
                grpc_status = "UNKNOWN_NO_HEALTH_CHECK"

                return ServiceDependencyHealth(
                    name="grpc_orchestrator",
                    status="degraded",
                    latency_ms=round(latency_ms, 2),
                    error="grpcio-health not installed, using fallback check",
                    details={"grpc_status": grpc_status, "latency_ms": round(latency_ms, 2)},
                )
    except Exception as e:
        logger.warning("grpc_orchestrator_deep_health_check_failed", error=str(e))
        return ServiceDependencyHealth(
            name="grpc_orchestrator",
            status="unhealthy",
            latency_ms=None,
            error=str(e),
            details=None,
        )

    return ServiceDependencyHealth(
        name="grpc_orchestrator",
        status="unknown",
        latency_ms=None,
        error="not_initialized",
        details=None,
    )


async def _check_clickhouse_with_latency(app_main) -> ServiceDependencyHealth:
    """Check ClickHouse health with latency measurement."""
    start = time.time()
    try:
        if app_main.health_checker:
            ch_result = await app_main.health_checker.check_single("clickhouse_schema")
            latency_ms = (time.time() - start) * 1000

            if ch_result:
                health_status = ch_result.status.name
                if health_status == "HEALTHY":
                    status = "healthy"
                elif health_status == "DEGRADED":
                    status = "degraded"
                else:
                    status = "unhealthy"

                return ServiceDependencyHealth(
                    name="clickhouse_schema",
                    status=status,
                    latency_ms=round(latency_ms, 2),
                    error=None,
                    details={
                        "health_status": health_status,
                        "latency_ms": round(latency_ms, 2),
                    },
                )
    except Exception as e:
        logger.warning("clickhouse_deep_health_check_failed", error=str(e))
        return ServiceDependencyHealth(
            name="clickhouse_schema",
            status="unhealthy",
            latency_ms=None,
            error=str(e),
            details=None,
        )

    return ServiceDependencyHealth(
        name="clickhouse_schema",
        status="unknown",
        latency_ms=None,
        error="not_initialized",
        details=None,
    )


async def _check_ml_models(app_main) -> dict[str, Any]:
    """Check ML model status and performance."""
    ml_models = {}

    try:
        # Check Q-Learning agent status
        if app_main.q_learning_agent:
            ql_agent = app_main.q_learning_agent
            ml_models["q_learning"] = {
                "name": "Q-Learning Agent",
                "version": getattr(ql_agent, "version", "unknown"),
                "status": "loaded",
                "last_trained_at": getattr(ql_agent, "last_trained_at", None),
                "performance_metrics": {
                    "exploration_rate": getattr(ql_agent, "exploration_rate", None),
                    "total_episodes": getattr(ql_agent, "total_episodes", None),
                },
            }
        else:
            ml_models["q_learning"] = {
                "name": "Q-Learning Agent",
                "status": "not_loaded",
            }

        # Check A/B testing engine status
        if app_main.ab_testing_engine:
            ab_engine = app_main.ab_testing_engine
            ml_models["ab_testing"] = {
                "name": "A/B Testing Engine",
                "version": getattr(ab_engine, "version", "unknown"),
                "status": "loaded",
                "active_experiments": getattr(ab_engine, "active_experiments_count", 0),
            }
        else:
            ml_models["ab_testing"] = {
                "name": "A/B Testing Engine",
                "status": "not_loaded",
            }

    except Exception as e:
        logger.warning("ml_models_health_check_failed", error=str(e))
        ml_models["error"] = str(e)

    return ml_models
