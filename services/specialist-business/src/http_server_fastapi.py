"""
FastAPI servidor HTTP robusto com circuit breakers e health checks otimizados.
"""

import asyncio
from typing import Dict, Any, Optional
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Response, status
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
import pybreaker
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = structlog.get_logger()

# Importar módulo de feedback (lazy import para evitar erros se não disponível)
try:
    from neural_hive_specialists.feedback import create_feedback_router, FeedbackCollector
    from neural_hive_specialists.compliance import AuditLogger
    FEEDBACK_AVAILABLE = True
except ImportError:
    logger.warning("Feedback module not available - feedback API will not be enabled")
    FEEDBACK_AVAILABLE = False


class HealthCheckCircuitBreaker:
    """Circuit breaker para health checks de dependências externas."""

    def __init__(self):
        self.mongodb_breaker = pybreaker.CircuitBreaker(
            fail_max=3,
            reset_timeout=60,
            name="mongodb_health"
        )
        self.neo4j_breaker = pybreaker.CircuitBreaker(
            fail_max=3,
            reset_timeout=60,
            name="neo4j_health"
        )
        self.redis_breaker = pybreaker.CircuitBreaker(
            fail_max=3,
            reset_timeout=60,
            name="redis_health"
        )


# Circuit breaker global
health_breakers = HealthCheckCircuitBreaker()


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(Exception)
)
async def check_mongodb_health(specialist) -> Dict[str, Any]:
    """Verifica saúde do MongoDB com retry e circuit breaker.

    Se ledger_client é None ou ledger está desabilitado/não obrigatório,
    retorna healthy para não bloquear readiness.
    """
    # Guard: skip check if ledger_client is None or ledger is disabled
    if specialist.ledger_client is None:
        ledger_enabled = getattr(specialist.config, 'enable_ledger', True)
        ledger_required = getattr(specialist.config, 'ledger_required', False)
        logger.debug(
            "Ledger client not available - skipping MongoDB health check",
            ledger_enabled=ledger_enabled,
            ledger_required=ledger_required
        )
        # Return healthy if ledger is not required, otherwise circuit_open
        if not ledger_required:
            return {"status": "healthy", "service": "mongodb", "reason": "ledger_not_required"}
        else:
            return {"status": "circuit_open", "service": "mongodb", "reason": "ledger_required_but_unavailable"}

    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(
                health_breakers.mongodb_breaker.call,
                lambda: specialist.ledger_client.check_health()
            ),
            timeout=5.0
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
    retry=retry_if_exception_type(Exception)
)
async def check_neo4j_health(specialist) -> Dict[str, Any]:
    """Verifica saúde do Neo4j com retry e circuit breaker."""
    try:
        # Neo4j health check implementation
        result = await asyncio.wait_for(
            asyncio.to_thread(
                health_breakers.neo4j_breaker.call,
                lambda: {"connected": True}  # Placeholder - implement real check
            ),
            timeout=5.0
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


def create_fastapi_app(specialist, config) -> FastAPI:
    """
    Cria aplicação FastAPI com health checks robustos.

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
        redoc_url=None
    )

    @app.get("/health", response_class=JSONResponse, status_code=200)
    async def health_check():
        """
        Liveness probe - verifica apenas se o processo está vivo.
        Responde rapidamente sem verificar dependências.
        """
        return {
            "status": "healthy",
            "specialist_type": specialist.specialist_type,
            "version": specialist.version
        }

    @app.get("/ready", response_class=JSONResponse)
    async def readiness_check(response: Response):
        """
        Readiness probe - verifica dependências críticas com circuit breakers.
        Retorna 200 se pronto, 503 se não pronto.
        Considera model_required para permitir modo heurístico.
        """
        try:
            # Executar health checks em paralelo com timeout total
            health_checks = await asyncio.wait_for(
                asyncio.gather(
                    check_mongodb_health(specialist),
                    check_neo4j_health(specialist),
                    return_exceptions=True
                ),
                timeout=8.0  # Timeout total de 8s para todos os checks
            )

            # Processar resultados
            mongodb_health, neo4j_health = health_checks

            # Determinar se está pronto
            # Circuit breaker aberto é considerado "ready" (fail open)
            mongodb_ready = isinstance(mongodb_health, dict) and mongodb_health.get("status") in ["healthy", "circuit_open"]
            neo4j_ready = isinstance(neo4j_health, dict) and neo4j_health.get("status") in ["healthy", "circuit_open"]

            # Verificar model_required para modo heurístico
            model_required = getattr(specialist.config, 'model_required', True)
            model_loaded = specialist.model is not None
            heuristic_mode = not model_loaded and not model_required

            # Log modo de operação
            if heuristic_mode:
                logger.info(
                    "Specialist em modo heurístico (sem modelo ML)",
                    specialist_type=specialist.specialist_type,
                    model_required=model_required
                )

            is_ready = mongodb_ready and neo4j_ready

            # Se modelo é obrigatório e não está carregado, não está pronto
            if model_required and not model_loaded:
                is_ready = False
                logger.warning(
                    "Readiness falhou: modelo obrigatório não carregado",
                    specialist_type=specialist.specialist_type,
                    model_required=model_required,
                    model_loaded=model_loaded
                )

            if not is_ready:
                response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
                logger.warning(
                    "Readiness check failed",
                    specialist_type=specialist.specialist_type,
                    mongodb_ready=mongodb_ready,
                    neo4j_ready=neo4j_ready,
                    model_loaded=model_loaded,
                    model_required=model_required
                )

            return {
                "ready": is_ready,
                "specialist_type": specialist.specialist_type,
                "heuristic_mode": heuristic_mode,
                "model_loaded": model_loaded,
                "dependencies": {
                    "mongodb": mongodb_health if isinstance(mongodb_health, dict) else {"status": "error"},
                    "neo4j": neo4j_health if isinstance(neo4j_health, dict) else {"status": "error"}
                }
            }

        except asyncio.TimeoutError:
            logger.warning("Readiness check timeout - dependencies slow")
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return {
                "ready": False,
                "specialist_type": specialist.specialist_type,
                "error": "health_check_timeout"
            }
        except Exception as e:
            logger.error("Readiness check failed", error=str(e))
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return {
                "ready": False,
                "specialist_type": specialist.specialist_type,
                "error": str(e)
            }

    @app.get("/metrics", response_class=PlainTextResponse)
    async def metrics():
        """
        Prometheus metrics endpoint.
        """
        try:
            metrics_data = generate_latest()
            return Response(
                content=metrics_data,
                media_type=CONTENT_TYPE_LATEST
            )
        except Exception as e:
            logger.error("Failed to generate metrics", error=str(e))
            return Response(
                content="",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @app.get("/status", response_class=JSONResponse)
    async def status_check():
        """
        Status detalhado do specialist e suas dependências.
        Inclui informações completas do health_check() incluindo model_loaded.
        """
        circuit_breaker_states = {
            "mongodb": health_breakers.mongodb_breaker.current_state,
            "neo4j": health_breakers.neo4j_breaker.current_state,
            "redis": health_breakers.redis_breaker.current_state
        }

        try:
            # Obter health check completo do specialist
            health_info = specialist.health_check()

            # Construir resposta combinando informações básicas e health check
            response = {
                "specialist_type": specialist.specialist_type,
                "version": specialist.version,
                "mlflow_enabled": getattr(specialist.mlflow_client, '_enabled', False) if specialist.mlflow_client else False,
                "circuit_breakers": circuit_breaker_states,
                "status": health_info.get('status', 'UNKNOWN'),
                "details": health_info.get('details', {})
            }

            return response
        except Exception as e:
            logger.error("Status check failed", error=str(e))
            # Retornar JSON padronizado com campos status e details mesmo em caso de exceção
            return {
                "specialist_type": specialist.specialist_type,
                "version": specialist.version,
                "mlflow_enabled": getattr(specialist.mlflow_client, '_enabled', False) if specialist.mlflow_client else False,
                "circuit_breakers": circuit_breaker_states,
                "status": "NOT_SERVING",
                "details": {
                    "degraded_reasons": [str(e)]
                }
            }

    # Integrar Feedback API se habilitado
    if FEEDBACK_AVAILABLE and config.enable_feedback_collection and config.feedback_api_enabled:
        try:
            # Inicializar AuditLogger
            audit_logger = AuditLogger(config, specialist.specialist_type)

            # Inicializar FeedbackCollector
            feedback_collector = FeedbackCollector(config, audit_logger)

            # Criar e registrar router de feedback com audit_logger
            feedback_router = create_feedback_router(
                feedback_collector,
                config,
                metrics=specialist.metrics,
                audit_logger=audit_logger
            )
            app.include_router(feedback_router, prefix="/api/v1", tags=["feedback"])

            logger.info(
                "Feedback API router registered",
                endpoints=["/api/v1/feedback", "/api/v1/feedback/opinion/{opinion_id}", "/api/v1/feedback/stats"]
            )
        except Exception as e:
            logger.error("Failed to register feedback router", error=str(e))

    logger.info(
        "FastAPI app created",
        specialist_type=specialist.specialist_type,
        endpoints=["/health", "/ready", "/metrics", "/status", "/api/v1/feedback"]
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
        app,
        host=host,
        port=port,
        log_level="info",
        access_log=False  # Reduce noise
    )

    server = uvicorn.Server(config)
    await server.serve()
