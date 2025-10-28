"""Main entry point for Scout Agents service"""
import asyncio
import signal
import sys
import uuid
from contextlib import asynccontextmanager
import structlog
import uvicorn
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from .config import get_settings
from .engine.exploration_engine import ExplorationEngine
from .api.http_server import app, init_app
from .observability.metrics import ScoutMetrics
from .clients.service_registry_client import ServiceRegistryClient

logger = structlog.get_logger()

# Global state
engine: ExplorationEngine = None
registry_client: ServiceRegistryClient = None
shutdown_event = asyncio.Event()


def configure_logging():
    """Configure structured logging"""
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.stdlib.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer()
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def configure_tracing(settings):
    """Configure OpenTelemetry tracing"""
    if not settings.observability.tracing_enabled:
        return

    try:
        # Set up Jaeger exporter
        jaeger_exporter = JaegerExporter(
            collector_endpoint=settings.observability.jaeger_endpoint,
        )

        # Set up tracer provider
        provider = TracerProvider()
        processor = BatchSpanProcessor(jaeger_exporter)
        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)

        # Instrument FastAPI
        FastAPIInstrumentor.instrument_app(app)

        logger.info("tracing_configured", endpoint=settings.observability.jaeger_endpoint)

    except Exception as e:
        logger.warning("tracing_configuration_failed", error=str(e))


def handle_signal(signum, frame):
    """Handle shutdown signals"""
    logger.info("shutdown_signal_received", signal=signum)
    shutdown_event.set()


async def heartbeat_loop(agent_id: str):
    """Periodic heartbeat to Service Registry"""
    settings = get_settings()
    interval = settings.service_registry.heartbeat_interval

    while not shutdown_event.is_set():
        try:
            await asyncio.sleep(interval)

            if engine and engine._is_running and registry_client:
                stats = engine.get_stats()

                # Prepara telemetria para o heartbeat
                telemetry = {
                    'success_rate': stats['published'] / max(stats['processed'], 1),
                    'total_executions': stats['processed'],
                    'failed_executions': stats['discarded'],
                    'last_execution_at': int(asyncio.get_event_loop().time())
                }

                # Envia heartbeat com telemetria
                success = await registry_client.heartbeat(telemetry)

                if success:
                    logger.debug(
                        "heartbeat_sent",
                        agent_id=agent_id,
                        stats=stats
                    )

                ScoutMetrics.record_heartbeat(success)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("heartbeat_failed", error=str(e))
            ScoutMetrics.record_heartbeat(False)


async def queue_processor_loop():
    """Process internal queue periodically"""
    while not shutdown_event.is_set():
        try:
            await asyncio.sleep(10)  # Process queue every 10 seconds

            if engine and engine._is_running:
                await engine.process_queue()
                ScoutMetrics.set_queue_size(len(engine.signal_queue))

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("queue_processing_failed", error=str(e))


async def startup():
    """Application startup"""
    global engine, registry_client

    settings = get_settings()

    # Generate agent ID
    agent_id = f"scout-{uuid.uuid4().hex[:8]}"

    logger.info(
        "scout_agent_starting",
        agent_id=agent_id,
        version=settings.service.version,
        environment=settings.service.environment
    )

    ScoutMetrics.record_startup()

    try:
        # Initialize exploration engine
        engine = ExplorationEngine(agent_id)
        await engine.start()

        # Initialize HTTP app
        init_app(engine, agent_id)

        # Initialize and register with Service Registry
        registry_client = ServiceRegistryClient(agent_id)
        await registry_client.start()

        registration_success = await registry_client.register()
        if registration_success:
            logger.info("service_registry_registered", agent_id=registry_client.agent_id)
            ScoutMetrics.record_registration()
        else:
            logger.warning("service_registry_registration_failed", agent_id=agent_id)
            # Não registra métrica se falhou

        # Start background tasks
        asyncio.create_task(heartbeat_loop(agent_id))
        asyncio.create_task(queue_processor_loop())

        logger.info("scout_agent_started", agent_id=agent_id)

    except Exception as e:
        logger.error("startup_failed", error=str(e))
        sys.exit(1)


async def shutdown():
    """Application shutdown"""
    logger.info("scout_agent_shutting_down")

    try:
        if engine:
            await engine.stop()

        # Deregister from Service Registry
        if registry_client:
            await registry_client.deregister()
            await registry_client.stop()
            logger.info("service_registry_deregistered")

        ScoutMetrics.record_deregistration()

        logger.info("scout_agent_shutdown_complete")

    except Exception as e:
        logger.error("shutdown_failed", error=str(e))


@asynccontextmanager
async def lifespan(app):
    """FastAPI lifespan context manager"""
    await startup()
    yield
    await shutdown()


app.router.lifespan_context = lifespan


async def main():
    """Main entry point"""
    settings = get_settings()

    # Configure logging
    configure_logging()

    # Configure tracing
    configure_tracing(settings)

    # Set up signal handlers
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # Start HTTP server
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=settings.observability.http_port,
        log_config=None,  # Use structlog instead
        access_log=False
    )

    server = uvicorn.Server(config)

    # Run server with shutdown handling
    try:
        await server.serve()
    except KeyboardInterrupt:
        logger.info("keyboard_interrupt_received")
    finally:
        await shutdown()


if __name__ == "__main__":
    asyncio.run(main())
