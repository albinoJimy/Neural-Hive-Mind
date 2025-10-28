import asyncio
import signal
from contextlib import asynccontextmanager
from fastapi import FastAPI
import structlog
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from src.config.settings import get_settings
from src.api import health
from src.services.playbook_executor import PlaybookExecutor
from src.consumers.remediation_consumer import RemediationConsumer

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle"""
    # Startup
    logger.info("self_healing_engine.startup", service=settings.service_name, version=settings.service_version)

    # Initialize Playbook Executor
    logger.info("self_healing_engine.initializing_playbook_executor")
    playbook_executor = PlaybookExecutor(
        playbooks_dir=settings.playbooks_dir,
        k8s_in_cluster=settings.kubernetes_in_cluster
    )
    await playbook_executor.initialize()
    app.state.playbook_executor = playbook_executor

    # Initialize Kafka Consumer
    logger.info("self_healing_engine.initializing_kafka_consumer")
    remediation_consumer = RemediationConsumer(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=settings.kafka_consumer_group,
        topic=settings.kafka_remediation_topic,
        playbook_executor=playbook_executor
    )
    await remediation_consumer.start()
    app.state.remediation_consumer = remediation_consumer

    logger.info("self_healing_engine.startup_complete")

    yield

    # Shutdown
    logger.info("self_healing_engine.shutdown", service=settings.service_name)

    # Stop consumer
    logger.info("self_healing_engine.stopping_kafka_consumer")
    await app.state.remediation_consumer.stop()

    logger.info("self_healing_engine.shutdown_complete")


# Create FastAPI application
app = FastAPI(
    title="Self-Healing Engine",
    description="Neural Hive-Mind Self-Healing Engine - Automated Remediation Execution",
    version=settings.service_version,
    lifespan=lifespan
)

# Instrument with OpenTelemetry
FastAPIInstrumentor.instrument_app(app)

# Include routers
app.include_router(health.router, tags=["health"])


# Signal handling for graceful shutdown
def handle_shutdown(signum, frame):
    logger.info("self_healing_engine.signal_received", signal=signum)


signal.signal(signal.SIGTERM, handle_shutdown)
signal.signal(signal.SIGINT, handle_shutdown)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8080,
        log_level=settings.log_level.lower(),
        access_log=True
    )
