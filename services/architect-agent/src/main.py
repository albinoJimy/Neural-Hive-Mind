"""Main entry point for Architect Agent service"""

import asyncio
import signal

import structlog
from uvicorn import Config, Server

from src.api.app import create_app
from src.config.settings import get_settings
from src.consumers import CognitivePlanConsumer, ConsumerManager
from src.observability.metrics import init_metrics
from src.producers import ArchitecturePlanProducer

logger = structlog.get_logger(__name__)


def configure_logging():
    """Configure structured logging"""
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.stdlib.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


async def main():
    """Main entry point"""
    settings = get_settings()

    # Configure logging
    configure_logging()

    # Get FastAPI app
    app = create_app()

    # Initialize metrics
    init_metrics(app)

    # Setup Kafka consumers and producer
    consumer_manager = ConsumerManager()
    architecture_plan_producer = None

    # Verificar se Kafka está habilitado
    if settings.kafka.bootstrap_servers != "disabled":
        # Inicializar producer
        architecture_plan_producer = ArchitecturePlanProducer()
        await architecture_plan_producer.start()

        # Inicializar consumer com producer injetado
        cognitive_plan_consumer = CognitivePlanConsumer(producer=architecture_plan_producer)
        consumer_manager.register(cognitive_plan_consumer)
        logger.info("kafka_consumer_enabled")
    else:
        logger.info("kafka_consumer_disabled")

    # Set up signal handlers
    shutdown_event = asyncio.Event()

    def handle_signal(signum, frame):
        logger.info("shutdown_signal_received", signal=signum)
        shutdown_event.set()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    logger.info(
        "starting_architect_agent",
        service=settings.service.service_name,
        version=settings.service.version,
        environment=settings.service.environment,
    )

    # Start HTTP server
    config = Config(
        app, host="0.0.0.0", port=settings.service.http_port, log_config=None, access_log=False
    )

    server = Server(config)

    # Start consumers and server concurrently
    consumer_task = None
    if consumer_manager.consumers:
        consumer_task = asyncio.create_task(consumer_manager.start_all())

    try:
        # Run server (blocking)
        await server.serve()
    except KeyboardInterrupt:
        logger.info("keyboard_interrupt_received")
    finally:
        # Stop consumers and producer
        if consumer_task:
            await consumer_manager.stop_all()
            if not consumer_task.done():
                consumer_task.cancel()

        if architecture_plan_producer:
            await architecture_plan_producer.stop()

        logger.info("architect_agent_shutdown_complete")


if __name__ == "__main__":
    asyncio.run(main())
