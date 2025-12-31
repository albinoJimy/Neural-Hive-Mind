"""
Ponto de entrada do Technical Specialist.
"""
import logging
import asyncio

import signal
import sys
import threading
import structlog

from config import TechnicalSpecialistConfig
from specialist import TechnicalSpecialist
from http_server import create_http_server
from http_server_fastapi import create_fastapi_app, run_fastapi_server

# Import from neural_hive_specialists (installed as pip package)
from neural_hive_specialists import create_grpc_server_with_observability

logger = structlog.get_logger()

# Flag para escolher entre FastAPI (async) ou HTTPServer (sync)
# Changed to True to match other specialists - FastAPI readiness check
# doesn't require model_loaded=True, allowing the pod to become Ready
USE_FASTAPI = True


def main():
    """Função principal de inicialização do Technical Specialist."""

    logger.info("Starting Technical Specialist")

    # Carregar configuração
    try:
        config = TechnicalSpecialistConfig()
        logger.info(
            "Configuration loaded",
            specialist_type=config.specialist_type,
            environment=config.environment,
            log_level=config.log_level
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
        specialist = TechnicalSpecialist(config)
        logger.info("Technical Specialist initialized successfully")
    except Exception as e:
        logger.error("Failed to initialize specialist", error=str(e), exc_info=True)
        sys.exit(1)

    # Criar servidor gRPC
    try:
        grpc_server = create_grpc_server_with_observability(specialist, config)
        grpc_server.start()
        logger.info(
            "gRPC server started",
            port=config.grpc_port
        )
    except Exception as e:
        logger.error("Failed to start gRPC server", error=str(e), exc_info=True)
        sys.exit(1)

    # Criar servidor HTTP (health/metrics)
    http_server = None
    http_server_task = None

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

            http_server_thread = threading.Thread(
                target=run_fastapi_in_thread,
                daemon=True
            )
            http_server_thread.start()
            logger.info(
                "FastAPI HTTP server started",
                port=config.http_port,
                features=["circuit_breakers", "retry_logic", "async"]
            )
        except Exception as e:
            logger.error("Failed to start FastAPI server", error=str(e), exc_info=True)
            sys.exit(1)
    else:
        try:
            http_server = create_http_server(specialist, config)
            http_server_thread = threading.Thread(
                target=http_server.serve_forever,
                daemon=True
            )
            http_server_thread.start()
            logger.info(
                "HTTP server started",
                port=config.http_port
            )
        except Exception as e:
            logger.error("Failed to start HTTP server", error=str(e), exc_info=True)
            sys.exit(1)

    # Graceful shutdown handler
    def shutdown_handler(signum, frame):
        logger.info(
            "Shutdown signal received",
            signal=signum
        )

        logger.info("Stopping gRPC server...")
        grpc_server.stop(grace=5)

        if not USE_FASTAPI and http_server:
            logger.info("Stopping HTTP server...")
            http_server.shutdown()
        else:
            logger.info("FastAPI server will stop on thread termination")

        logger.info("Technical Specialist shut down successfully")
        sys.exit(0)

    # Registrar signal handlers
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    logger.info(
        "Technical Specialist is ready",
        grpc_port=config.grpc_port,
        http_port=config.http_port,
        prometheus_port=config.prometheus_port
    )

    # Wait for termination
    try:
        grpc_server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
        shutdown_handler(signal.SIGINT, None)


if __name__ == "__main__":
    main()
