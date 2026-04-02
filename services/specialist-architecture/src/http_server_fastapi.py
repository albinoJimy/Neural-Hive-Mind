"""
FastAPI servidor HTTP robusto com circuit breakers e health checks otimizados.
"""

import asyncio
from contextlib import asynccontextmanager
from typing import Any, Dict

import pybreaker
import structlog
from fastapi import FastAPI, Response, status
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from neural_hive_api.health import HealthRouter, BaseHealthCheck, HealthStatus, CheckResult

logger = structlog.get_logger()

# Importar módulo de feedback (lazy import para evitar erros se não disponível)
try:
    from neural_hive_specialists.compliance import AuditLogger, PIIDetector
    from neural_hive_specialists.feedback import FeedbackCollector, create_feedback_router

    FEEDBACK_AVAILABLE = True
except ImportError:
    logger.warning("Feedback module not available - feedback API will not be enabled")
    FEEDBACK_AVAILABLE = False


class HealthCheckCircuitBreaker:
    """Circuit breaker para health checks de dependências externas."""

    def __init__(self):
        self.mongodb_breaker = pybreaker.CircuitBreaker(
            fail_max=3, reset_timeout=60, name="mongodb_health"
        )
        self.neo4j_breaker = pybreaker.CircuitBreaker(
            fail_max=3, reset_timeout=60, name="neo4j_health"
        )
        self.redis_breaker = pybreaker.CircuitBreaker(
            fail_max=3, reset_timeout=60, name="redis_health"
        )


# Circuit breaker global
health_breakers = HealthCheckCircuitBreaker()


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(Exception),
)
async def check_mongodb_health(specialist) -> Dict[str, Any]:
    """Verifica saúde do MongoDB com retry e circuit breaker."""
    try:
        await asyncio.wait_for(
            asyncio.to_thread(
                health_breakers.mongodb_breaker.call,
                lambda: specialist.ledger_client.check_health(),
            ),
            timeout=5.0,
        )
        return {"status": "healthy", "service": "mongodb"}
    except pybreaker.CircuitBreakerError:
        logger.warning("MongoDB circuit breaker open - skipping health check")
        return {"status": "circuit_open", "service": "mongodb"}
    except asyncio.TimeoutError:
        logger.warning("MongoDB health check timeout")
        return {"status": "timeout", "service": "mongodb"}
    except Exception as e:
        logger.error("MongoDB health check failed", error=str(e))
        return {"status": "unhealthy", "service": "mongodb", "error": str(e)}


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(Exception),
)
async def check_neo4j_health(specialist) -> Dict[str, Any]:
    """Verifica saúde do Neo4j com retry e circuit breaker."""
    try:
        # Neo4j health check implementation
        await asyncio.wait_for(
            asyncio.to_thread(
                health_breakers.neo4j_breaker.call,
                lambda: {"connected": True},  # Placeholder - implement real check
            ),
            timeout=5.0,
        )
        return {"status": "healthy", "service": "neo4j"}
    except pybreaker.CircuitBreakerError:
        logger.warning("Neo4j circuit breaker open - skipping health check")
        return {"status": "circuit_open", "service": "neo4j"}
    except asyncio.TimeoutError:
        logger.warning("Neo4j health check timeout")
        return {"status": "timeout", "service": "neo4j"}
    except Exception as e:
        logger.error("Neo4j health check failed", error=str(e))
        return {"status": "unhealthy", "service": "neo4j", "error": str(e)}


# ============================================================================
# Health Check Classes for neural_hive_api
# ============================================================================

class MongoDBHealthCheck(BaseHealthCheck):
    """Health check para MongoDB."""

    def __init__(self, specialist):
        super().__init__("mongodb", critical=True)
        self.specialist = specialist

    async def check(self) -> CheckResult:
        """Verifica conexão com MongoDB."""
        try:
            result = await check_mongodb_health(self.specialist)
            if result.get("status") in ["healthy", "circuit_open"]:
                return CheckResult(name=self.name, status=HealthStatus.HEALTHY)
            return CheckResult(name=self.name, status=HealthStatus.DEGRADED, message=str(result))
        except Exception as e:
            return CheckResult(name=self.name, status=HealthStatus.DEGRADED, message=str(e))


class Neo4jHealthCheck(BaseHealthCheck):
    """Health check para Neo4j."""

    def __init__(self, specialist):
        super().__init__("neo4j", critical=True)
        self.specialist = specialist

    async def check(self) -> CheckResult:
        """Verifica conexão com Neo4j."""
        try:
            result = await check_neo4j_health(self.specialist)
            if result.get("status") in ["healthy", "circuit_open"]:
                return CheckResult(name=self.name, status=HealthStatus.HEALTHY)
            return CheckResult(name=self.name, status=HealthStatus.DEGRADED, message=str(result))
        except Exception as e:
            return CheckResult(name=self.name, status=HealthStatus.DEGRADED, message=str(e))


def create_fastapi_app(specialist, config) -> FastAPI:
    """
    Cria aplicação FastAPI com health checks usando neural_hive_api.

    Args:
        specialist: Instância do especialista
        config: Configuração

    Returns:
        FastAPI app configurada
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Gerencia ciclo de vida da aplicação."""
        logger.info("FastAPI HTTP server starting", port=config.http_port)
        yield
        logger.info("FastAPI HTTP server shutting down")

    app = FastAPI(
        title=f"{specialist.specialist_type.capitalize()} Specialist API",
        version=specialist.version,
        lifespan=lifespan,
        docs_url=None,  # Disable docs in production
        redoc_url=None,
    )

    # HealthRouter (neural_hive_api)
    service_type = specialist.specialist_type.replace("-", "_")
    health_router = HealthRouter(f"specialist-{service_type}")
    health_router.register_check(MongoDBHealthCheck(specialist))
    health_router.register_check(Neo4jHealthCheck(specialist))
    health_router.add_route(app)

    @app.get("/metrics", response_class=PlainTextResponse)
    async def metrics():
        """
        Prometheus metrics endpoint.
        """
        try:
            metrics_data = generate_latest()
            return Response(content=metrics_data, media_type=CONTENT_TYPE_LATEST)
        except Exception as e:
            logger.error("Failed to generate metrics", error=str(e))
            return Response(content="", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @app.get("/status", response_class=JSONResponse)
    async def status_check():
        """
        Status detalhado do specialist e suas dependências.
        Inclui informações completas do health_check() incluindo model_loaded.
        """
        circuit_breaker_states = {
            "mongodb": health_breakers.mongodb_breaker.current_state,
            "neo4j": health_breakers.neo4j_breaker.current_state,
            "redis": health_breakers.redis_breaker.current_state,
        }

        try:
            # Obter health check completo do specialist
            health_info = specialist.health_check()

            # Construir resposta combinando informações básicas e health check
            response = {
                "specialist_type": specialist.specialist_type,
                "version": specialist.version,
                "mlflow_enabled": getattr(specialist.mlflow_client, "_enabled", False)
                if specialist.mlflow_client
                else False,
                "circuit_breakers": circuit_breaker_states,
                "status": health_info.get("status", "UNKNOWN"),
                "details": health_info.get("details", {}),
            }

            return response
        except Exception as e:
            logger.error("Status check failed", error=str(e))
            # Retornar JSON padronizado com campos status e details mesmo em caso de exceção
            return {
                "specialist_type": specialist.specialist_type,
                "version": specialist.version,
                "mlflow_enabled": getattr(specialist.mlflow_client, "_enabled", False)
                if specialist.mlflow_client
                else False,
                "circuit_breakers": circuit_breaker_states,
                "status": "NOT_SERVING",
                "details": {"degraded_reasons": [str(e)]},
            }

    # Integrar Feedback API se habilitado
    if FEEDBACK_AVAILABLE and config.enable_feedback_collection and config.feedback_api_enabled:
        try:
            # Inicializar AuditLogger
            audit_logger = AuditLogger(config, specialist.specialist_type)

            # Inicializar FeedbackCollector
            feedback_collector = FeedbackCollector(config, audit_logger)

            # Inicializar PIIDetector para anonimização de feedback notes
            pii_detector = PIIDetector(config) if config.enable_pii_detection else None

            # Criar e registrar router de feedback com audit_logger e pii_detector
            feedback_router = create_feedback_router(
                feedback_collector,
                config,
                metrics=specialist.metrics,
                pii_detector=pii_detector,
                audit_logger=audit_logger,
            )
            app.include_router(feedback_router, prefix="/api/v1", tags=["feedback"])

            logger.info(
                "Feedback API router registered",
                endpoints=[
                    "/api/v1/feedback",
                    "/api/v1/feedback/opinion/{opinion_id}",
                    "/api/v1/feedback/stats",
                ],
            )
        except Exception as e:
            logger.error("Failed to register feedback router", error=str(e))

    logger.info(
        "FastAPI app created",
        specialist_type=specialist.specialist_type,
        endpoints=["/health", "/ready", "/metrics", "/status", "/api/v1/feedback"],
    )

    return app


async def run_fastapi_server(app: FastAPI, host: str, port: int):
    """
    Executa servidor FastAPI com uvicorn.

    Args:
        app: FastAPI application
        host: Host to bind
        port: Port to bind
    """
    import uvicorn

    config = uvicorn.Config(
        app, host=host, port=port, log_level="info", access_log=False  # Reduce noise
    )

    server = uvicorn.Server(config)
    await server.serve()
