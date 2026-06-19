"""
Ponto de entrada do Behavior Specialist.
"""

import asyncio
import logging
import signal
import sys
import threading

import structlog
from config import BehaviorSpecialistConfig
from specialist import BehaviorSpecialist

# Tentar usar FastAPI server se disponível, senão fallback para HTTPServer
USE_FASTAPI = True
try:
    from http_server_fastapi import create_fastapi_app, run_fastapi_server
except ImportError:
    USE_FASTAPI = False
    from http_server import create_http_server

# Import from neural_hive_specialists (installed as pip package)
from neural_hive_specialists import create_grpc_server_with_observability

logger = structlog.get_logger()


def main():
    """Função principal de inicialização do Behavior Specialist."""

    logger.info("Starting Behavior Specialist")

    # Carregar configuração
    try:
        config = BehaviorSpecialistConfig()
        logger.info(
            "Configuration loaded",
            specialist_type=config.specialist_type,
            environment=config.environment,
            log_level=config.log_level,
        )
    except Exception as e:
        logger.error("Failed to load configuration", error=str(e), exc_info=True)
        sys.exit(1)

    # Configurar logging
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, config.log_level.upper(), logging.INFO)
        ),
    )

    # Criar especialista
    try:
        specialist = BehaviorSpecialist(config)
        logger.info("Behavior Specialist initialized successfully")
    except Exception as e:
        logger.error("Failed to initialize specialist", error=str(e), exc_info=True)
        sys.exit(1)

    # Criar servidor HTTP (health/metrics) ANTES do warmup.
    # O startup probe do Kubernetes bate em /health:8000 a partir do segundo 10. Se o
    # warmup (que pode demorar dezenas de segundos em I/O lento ou MLflow frio) correr
    # antes do bind da porta 8000, as probes recebem 'connection refused' e consomem
    # falhas do failureThreshold, podendo causar restart loop do pod. Ao iniciar o
    # servidor HTTP primeiro, /health (e /health/startup) respondem imediatamente
    # enquanto o warmup decorre.
    http_server = None

    if USE_FASTAPI:
        try:
            # Criar app FastAPI
            fastapi_app = create_fastapi_app(specialist, config)

            # Criar event loop em thread separada para FastAPI
            def run_fastapi_in_thread():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(
                    run_fastapi_server(fastapi_app, "0.0.0.0", config.http_port)
                )

            http_server_thread = threading.Thread(target=run_fastapi_in_thread, daemon=True)
            http_server_thread.start()
            logger.info(
                "FastAPI HTTP server started",
                port=config.http_port,
                features=["circuit_breakers", "retry_logic", "async"],
            )
        except Exception as e:
            logger.error("Failed to start FastAPI server", error=str(e), exc_info=True)
            sys.exit(1)
    else:
        try:
            http_server = create_http_server(specialist, config)
            http_server_thread = threading.Thread(target=http_server.serve_forever, daemon=True)
            http_server_thread.start()
            logger.info("HTTP server started", port=config.http_port)
        except Exception as e:
            logger.error("Failed to start HTTP server", error=str(e), exc_info=True)
            sys.exit(1)

    # Pre-warm do modelo ML antes de servir tráfego gRPC (elimina cold-start lazy do MLflow).
    # A 1ª inferência fria pode demorar dezenas de segundos a carregar embeddings/modelo
    # e disparar o circuit-breaker, forçando fallback heurístico (semantic_pipeline) com
    # confiança reduzida. O warmup carrega o modelo e executa uma inferência dummy para
    # que a 1ª requisição real chegue com o modelo quente e use model_source=ml_model.
    # O servidor HTTP já está bound (acima), pelo que as probes respondem durante o warmup.
    #
    # As feature flags warmup_enabled (WARMUP_ENABLED) e warmup_on_startup
    # (WARMUP_ON_STARTUP) permitem desabilitar o warmup via env var em situações de
    # degradação (e.g. MLflow indisponível, disco do CP sob carga).
    if getattr(config, "warmup_enabled", True) and getattr(config, "warmup_on_startup", True):
        try:
            warmup_result = specialist.warmup()
            if warmup_result.get("status") == "success":
                logger.info(
                    "Specialist warmup completed successfully",
                    duration_seconds=warmup_result.get("duration_seconds"),
                    model_loaded=warmup_result.get("model_loaded"),
                )
            else:
                # Não bloquear o arranque em falha de warmup: o specialist continua em modo
                # degradado (heurístico) e o readiness probe trata a disponibilidade.
                logger.warning(
                    "Specialist warmup did not complete successfully - proceeding in degraded mode",
                    warmup_status=warmup_result.get("status"),
                    error=warmup_result.get("error"),
                )
        except Exception as e:
            logger.exception(
                "Specialist warmup raised an exception - proceeding",
                error=str(e),
            )
    else:
        logger.info(
            "Specialist warmup skipped by configuration",
            warmup_enabled=getattr(config, "warmup_enabled", True),
            warmup_on_startup=getattr(config, "warmup_on_startup", True),
        )

    # Criar servidor gRPC
    try:
        grpc_server = create_grpc_server_with_observability(specialist, config)
        grpc_server.start()
        logger.info("gRPC server started", port=config.grpc_port)
    except Exception as e:
        logger.error("Failed to start gRPC server", error=str(e), exc_info=True)
        sys.exit(1)

    # Graceful shutdown handler
    def shutdown_handler(signum, frame):
        logger.info("Shutdown signal received", signal=signum)

        logger.info("Stopping gRPC server...")
        grpc_server.stop(grace=5)

        if not USE_FASTAPI and http_server:
            logger.info("Stopping HTTP server...")
            http_server.shutdown()
        else:
            logger.info("FastAPI server will stop on thread termination")

        logger.info("Behavior Specialist shut down successfully")
        sys.exit(0)

    # Registrar signal handlers
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    logger.info(
        "Behavior Specialist is ready",
        grpc_port=config.grpc_port,
        http_port=config.http_port,
        prometheus_port=config.prometheus_port,
    )

    # Wait for termination
    try:
        grpc_server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
        shutdown_handler(signal.SIGINT, None)


if __name__ == "__main__":
    main()
