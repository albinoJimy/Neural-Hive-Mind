from fastapi import APIRouter, status
from typing import Dict, Any

router = APIRouter()


@router.get("/health", status_code=status.HTTP_200_OK)
async def health() -> Dict[str, Any]:
    """Liveness probe"""
    return {
        "status": "healthy",
        "service": "queen-agent",
        "version": "1.0.0"
    }


@router.get("/ready", status_code=status.HTTP_200_OK)
async def ready() -> Dict[str, Any]:
    """
    Readiness probe
    TODO: Verificar conexões com MongoDB, Redis, Neo4j, Kafka, Prometheus
    """
    checks = {
        "mongodb": True,  # TODO: Verificar conexão real
        "redis": True,
        "neo4j": True,
        "kafka": True,
        "prometheus": True
    }

    ready_status = all(checks.values())

    return {
        "ready": ready_status,
        "checks": checks
    }
