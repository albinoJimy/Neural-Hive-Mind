"""
Health Check Endpoints

Endpoints para liveness e readiness probes do Kubernetes.
"""

import json
import structlog
from fastapi import APIRouter, Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

logger = structlog.get_logger()

router = APIRouter()

# Referencia global para o estado da aplicacao
_app_state = {}


def set_app_state(state: dict):
    """Define referencia para o estado da aplicacao"""
    global _app_state
    _app_state = state


@router.get("/health")
async def health_check():
    """
    Liveness probe - verifica se a aplicacao esta viva

    Returns:
        Status basico da aplicacao
    """
    return {
        "status": "healthy",
        "service": "approval-service",
        "version": "1.0.0"
    }


@router.get("/ready")
async def readiness_check():
    """
    Readiness probe - verifica se todas as dependencias estao conectadas

    Returns:
        Status detalhado das dependencias
    """
    checks = {
        "kafka_consumer": False,
        "kafka_producer": False,
        "mongodb": False,
    }

    try:
        # Verifica MongoDB
        if 'mongodb' in _app_state and _app_state['mongodb'].client:
            try:
                await _app_state['mongodb'].client.admin.command('ping')
                checks['mongodb'] = True
            except Exception as e:
                logger.warning("MongoDB ping failed", error=str(e))

        # Verifica Kafka producer
        if 'producer' in _app_state and _app_state['producer'].producer:
            try:
                _app_state['producer'].producer.list_topics(timeout=2)
                checks['kafka_producer'] = True
            except Exception as e:
                logger.warning("Kafka producer check failed", error=str(e))

        # Verifica Kafka consumer
        if 'consumer' in _app_state and _app_state['consumer']:
            try:
                is_healthy, reason = _app_state['consumer'].is_healthy(
                    max_poll_age_seconds=60.0
                )
                checks['kafka_consumer'] = is_healthy
                if not is_healthy:
                    logger.warning("Kafka consumer nao saudavel", reason=reason)
            except Exception as e:
                logger.warning("Kafka consumer check failed", error=str(e))

        all_ready = all(checks.values())

        response_data = {
            "ready": all_ready,
            "checks": checks
        }

        if all_ready:
            return response_data
        else:
            return Response(
                content=json.dumps(response_data),
                status_code=503,
                media_type="application/json"
            )

    except Exception as e:
        logger.error("Readiness check failed", error=str(e))
        return Response(
            content=json.dumps({
                "ready": False,
                "checks": checks,
                "error": str(e)
            }),
            status_code=503,
            media_type="application/json"
        )


@router.get("/metrics")
async def metrics():
    """
    Prometheus metrics endpoint

    Returns:
        Metricas no formato Prometheus
    """
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )
