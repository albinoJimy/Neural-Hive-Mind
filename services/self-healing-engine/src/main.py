import asyncio
import signal
import json
import os
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
import structlog
from neural_hive_observability import (
    get_tracer,
    init_observability,
    instrument_kafka_consumer,
)

from src.config.settings import get_settings
from src.api import health, remediation
from src.services.playbook_executor import PlaybookExecutor
from src.services.remediation_manager import RemediationManager
from src.clients.service_registry_client import ServiceRegistryClient
from src.consumers.remediation_consumer import RemediationConsumer
from src.consumers.orchestration_incident_consumer import OrchestrationIncidentConsumer

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

    init_observability(
        service_name='self-healing-engine',
        service_version=settings.service_version,
        neural_hive_component='self-healing',
        neural_hive_layer='governanca',
        neural_hive_domain='remediation',
        otel_endpoint=os.getenv('OTEL_EXPORTER_OTLP_ENDPOINT', 'http://otel-collector:4317'),
    )

    # Initialize Service Registry client (fail-open)
    service_registry_client = ServiceRegistryClient(
        host=settings.service_registry_host,
        port=settings.service_registry_port,
        timeout_seconds=settings.service_registry_timeout_seconds
    )
    await service_registry_client.initialize()
    app.state.service_registry_client = service_registry_client

    # Initialize Playbook Executor
    logger.info("self_healing_engine.initializing_playbook_executor")
    playbook_executor = PlaybookExecutor(
        playbooks_dir=settings.playbooks_dir,
        k8s_in_cluster=settings.kubernetes_in_cluster,
        default_timeout_seconds=settings.playbook_timeout_seconds,
        service_registry_client=service_registry_client
    )
    await playbook_executor.initialize()
    app.state.playbook_executor = playbook_executor

    # Initialize Remediation Manager
    app.state.remediation_manager = RemediationManager(default_timeout_seconds=settings.playbook_timeout_seconds)

    # Initialize Kafka Consumer
    logger.info("self_healing_engine.initializing_kafka_consumer")
    remediation_consumer = RemediationConsumer(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=settings.kafka_consumer_group,
        topic=settings.kafka_remediation_topic,
        playbook_executor=playbook_executor
    )
    await remediation_consumer.start()
    remediation_consumer = instrument_kafka_consumer(remediation_consumer)
    app.state.remediation_consumer = remediation_consumer

    # Initialize Orchestration Incident Consumer (Kafka)
    incident_schema = None
    schema_path = Path(settings.schemas_base_path) / "orchestration-incident" / "orchestration-incident.avsc"
    if schema_path.exists():
        try:
            incident_schema = json.loads(schema_path.read_text())
        except Exception as exc:  # noqa: BLE001
            logger.warning("incident_consumer.schema_load_failed", error=str(exc), schema_path=str(schema_path))

    incident_consumer = OrchestrationIncidentConsumer(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=settings.kafka_incident_group,
        topic=settings.kafka_incident_topic,
        playbook_executor=playbook_executor,
        remediation_manager=app.state.remediation_manager,
        incident_schema=incident_schema
    )
    await incident_consumer.start()
    incident_consumer = instrument_kafka_consumer(incident_consumer)
    app.state.incident_consumer = incident_consumer

    logger.info("self_healing_engine.startup_complete")

    yield

    # Shutdown
    logger.info("self_healing_engine.shutdown", service=settings.service_name)

    # Stop consumer
    logger.info("self_healing_engine.stopping_kafka_consumer")
    await app.state.remediation_consumer.stop()

    # Stop incident consumer
    incident_consumer = getattr(app.state, "incident_consumer", None)
    if incident_consumer:
        logger.info("self_healing_engine.stopping_incident_consumer")
        await incident_consumer.stop()

    # Close Service Registry client
    service_registry_client = getattr(app.state, "service_registry_client", None)
    if service_registry_client:
        await service_registry_client.close()

    logger.info("self_healing_engine.shutdown_complete")


# Create FastAPI application
app = FastAPI(
    title="Self-Healing Engine",
    description="Neural Hive-Mind Self-Healing Engine - Automated Remediation Execution",
    version=settings.service_version,
    lifespan=lifespan
)

# Include routers
app.include_router(health.router, tags=["health"])
app.include_router(remediation.router, tags=["remediation"])


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
