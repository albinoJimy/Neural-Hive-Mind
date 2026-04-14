from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

logger = structlog.get_logger()
router = APIRouter()


@router.get("/health", status_code=status.HTTP_200_OK)
async def health() -> dict[str, Any]:
    """Liveness probe - verifica se o serviço está ativo"""
    return {"status": "healthy", "service": "queen-agent", "version": "1.0.0"}


@router.get("/health/startup", status_code=status.HTTP_200_OK)
async def startup() -> dict[str, Any]:
    """Startup probe - indica que o serviço completou a inicialização"""
    return {
        "status": "started",
        "service": "queen-agent",
        "version": "1.0.0",
        "started_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/ready")
async def ready(request: Request) -> JSONResponse:
    """
    Readiness probe - verifica conexões com dependências externas
    Retorna 503 se alguma dependência crítica não estiver disponível
    """
    app_state = request.app.state.app_state
    checks: dict[str, bool] = {}

    # MongoDB - dependência crítica
    try:
        if app_state.mongodb_client and app_state.mongodb_client.client:
            await app_state.mongodb_client.client.admin.command("ping")
            checks["mongodb"] = True
        else:
            checks["mongodb"] = False
    except Exception as e:
        logger.exception("health_check_mongodb_failed", error=str(e))
        checks["mongodb"] = False

    # Redis - dependência crítica
    try:
        if app_state.redis_client and app_state.redis_client.client:
            await app_state.redis_client.client.ping()
            checks["redis"] = True
        else:
            checks["redis"] = False
    except Exception as e:
        logger.exception("health_check_redis_failed", error=str(e))
        checks["redis"] = False

    # Neo4j - dependência crítica
    try:
        if app_state.neo4j_client and app_state.neo4j_client.driver:
            await app_state.neo4j_client.driver.verify_connectivity()
            checks["neo4j"] = True
        else:
            checks["neo4j"] = False
    except Exception as e:
        logger.exception("health_check_neo4j_failed", error=str(e))
        checks["neo4j"] = False

    # Kafka consumers - verifica se foram inicializados
    try:
        checks["kafka"] = (
            app_state.consensus_consumer is not None
            and app_state.telemetry_consumer is not None
            and app_state.incident_consumer is not None
        )
    except Exception as e:
        logger.exception("health_check_kafka_failed", error=str(e))
        checks["kafka"] = False

    # Prometheus - dependência opcional
    try:
        if app_state.prometheus_client:
            result = await app_state.prometheus_client.query("up")
            checks["prometheus"] = result.get("status") == "success" if result else False
        else:
            checks["prometheus"] = False
    except Exception as e:
        logger.warning("health_check_prometheus_failed", error=str(e))
        checks["prometheus"] = False

    # gRPC server - verifica se está rodando
    try:
        checks["grpc"] = app_state.grpc_server is not None
    except Exception as e:
        logger.exception("health_check_grpc_failed", error=str(e))
        checks["grpc"] = False

    # Leader Election - opcional, verifica se está rodando
    try:
        checks["leader_election"] = (
            app_state.leader_election is not None and app_state.leader_election.is_running
        )
    except Exception as e:
        logger.exception("health_check_leader_election_failed", error=str(e))
        checks["leader_election"] = False

    # Load Balancer - opcional, verifica se está rodando
    try:
        checks["load_balancer"] = (
            app_state.load_balancer is not None and app_state.load_balancer.is_running
        )
    except Exception as e:
        logger.exception("health_check_load_balancer_failed", error=str(e))
        checks["load_balancer"] = False

    # Dependências críticas: MongoDB, Redis, Neo4j, Kafka
    critical_deps = ["mongodb", "redis", "neo4j", "kafka"]
    all_critical_healthy = all(checks.get(dep, False) for dep in critical_deps)

    status_code = 200 if all_critical_healthy else 503

    return JSONResponse(
        status_code=status_code,
        content={"ready": all_critical_healthy, "checks": checks},
    )
