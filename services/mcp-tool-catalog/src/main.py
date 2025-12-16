"""Main entry point for MCP Tool Catalog Service."""
import asyncio
import signal
import sys
from contextlib import asynccontextmanager

import structlog
import uvicorn
from fastapi import FastAPI
from prometheus_client import make_asgi_app, start_http_server
from neural_hive_observability import (
    get_tracer,
    init_observability,
    instrument_kafka_consumer,
    instrument_kafka_producer,
)

from src.api.http_server import create_app
from src.config import get_settings
from src.observability import MCPToolCatalogMetrics, setup_logging

logger = structlog.get_logger()


class MCPToolCatalogService:
    """MCP Tool Catalog Service orchestrator."""

    def __init__(self):
        """Initialize service components."""
        self.settings = get_settings()
        self.metrics = MCPToolCatalogMetrics()
        self.shutdown_event = asyncio.Event()
        self.app: FastAPI = None

        # Clients and services will be initialized in startup
        self.mongodb_client = None
        self.redis_client = None
        self.kafka_consumer = None
        self.kafka_producer = None
        self.service_registry_client = None
        self.tool_registry = None
        self.genetic_selector = None

    async def startup(self):
        """Initialize all service components."""
        logger.info("starting_mcp_tool_catalog", version=self.settings.SERVICE_VERSION)

        init_observability(
            service_name=self.settings.SERVICE_NAME,
            service_version=self.settings.SERVICE_VERSION,
            neural_hive_component='mcp-tool-catalog',
            neural_hive_layer='ferramentas',
            neural_hive_domain='tool-selection',
            otel_endpoint=self.settings.otel_endpoint,
            enable_kafka=True
        )

        try:
            # Initialize MongoDB client
            from src.clients.mongodb_client import MongoDBClient

            self.mongodb_client = MongoDBClient(
                self.settings.MONGODB_URL, self.settings.MONGODB_DATABASE
            )
            await self.mongodb_client.start()
            logger.info("mongodb_connected")

            # Initialize Redis client
            from src.clients.redis_client import RedisClient

            self.redis_client = RedisClient(self.settings.REDIS_URL, self.settings.CACHE_TTL_SECONDS)
            await self.redis_client.start()
            logger.info("redis_connected")

            # Initialize Tool Registry
            from src.services.tool_registry import ToolRegistry

            self.tool_registry = ToolRegistry(self.mongodb_client, self.redis_client, self.metrics)
            await self.tool_registry.bootstrap_initial_catalog()
            logger.info("tool_registry_initialized")

            # Initialize Genetic Tool Selector
            from src.services.genetic_tool_selector import GeneticToolSelector

            self.genetic_selector = GeneticToolSelector(self.tool_registry, self.settings, self.metrics)
            logger.info("genetic_selector_initialized")

            # Initialize Tool Executor
            from src.services.tool_executor import ToolExecutor

            self.tool_executor = ToolExecutor()
            logger.info("tool_executor_initialized")

            # Initialize Kafka clients
            from src.clients.kafka_request_consumer import KafkaRequestConsumer
            from src.clients.kafka_response_producer import KafkaResponseProducer

            self.kafka_consumer = KafkaRequestConsumer(
                self.settings.KAFKA_BOOTSTRAP_SERVERS,
                self.settings.KAFKA_TOOL_SELECTION_REQUEST_TOPIC,
                self.settings.KAFKA_CONSUMER_GROUP_ID,
            )
            await self.kafka_consumer.start()
            self.kafka_consumer = instrument_kafka_consumer(self.kafka_consumer)
            logger.info("kafka_consumer_started")

            self.kafka_producer = KafkaResponseProducer(
                self.settings.KAFKA_BOOTSTRAP_SERVERS,
                self.settings.KAFKA_TOOL_SELECTION_RESPONSE_TOPIC,
            )
            await self.kafka_producer.start()
            self.kafka_producer = instrument_kafka_producer(self.kafka_producer)
            logger.info("kafka_producer_started")

            # Initialize Service Registry client
            from src.clients.service_registry_client import ServiceRegistryClient

            self.service_registry_client = ServiceRegistryClient(
                self.settings.SERVICE_REGISTRY_HOST, self.settings.SERVICE_REGISTRY_PORT
            )
            await self.service_registry_client.register(
                self.settings.SERVICE_NAME,
                ["tool_discovery", "tool_selection", "genetic_optimization"],
                {"version": self.settings.SERVICE_VERSION},
            )
            logger.info("service_registered")

            # Start background tasks
            asyncio.create_task(self._process_requests())
            asyncio.create_task(self._heartbeat_loop())

            logger.info("mcp_tool_catalog_started")

        except Exception as e:
            logger.error("startup_failed", error=str(e))
            raise

    async def shutdown(self):
        """Graceful shutdown of all components."""
        logger.info("shutting_down_mcp_tool_catalog")

        self.shutdown_event.set()

        # Stop Kafka clients
        if self.kafka_consumer:
            await self.kafka_consumer.stop()
        if self.kafka_producer:
            await self.kafka_producer.stop()

        # Deregister from Service Registry
        if self.service_registry_client:
            await self.service_registry_client.deregister()

        # Stop database clients
        if self.redis_client:
            await self.redis_client.stop()
        if self.mongodb_client:
            await self.mongodb_client.stop()

        logger.info("mcp_tool_catalog_stopped")

    async def _process_requests(self):
        """Background task to process tool selection requests from Kafka."""
        logger.info("request_processor_started")

        try:
            async for request in self.kafka_consumer.consume():
                if self.shutdown_event.is_set():
                    break

                try:
                    self.metrics.active_tool_selections.inc()

                    tracer = get_tracer()
                    with tracer.start_as_current_span("genetic_tool_selection") as span:
                        span.set_attribute("neural.hive.request_id", request.request_id)
                        span.set_attribute("neural.hive.tool_count", len(request.required_capabilities))

                        # Process selection request
                        response = await self.genetic_selector.select_tools(request)
                        span.set_attribute("neural.hive.selected_tools", len(response.selected_tools))

                    # Increment usage counters for selected tools
                    for selected_tool in response.selected_tools:
                        await self.redis_client.increment_tool_usage(selected_tool.tool_id)

                    # Publish response
                    await self.kafka_producer.publish_response(response)

                    # Commit offset
                    await self.kafka_consumer.commit()

                except Exception as e:
                    logger.error("request_processing_failed", error=str(e), request_id=request.request_id)

                finally:
                    self.metrics.active_tool_selections.dec()

        except Exception as e:
            logger.error("request_processor_error", error=str(e))

    async def _heartbeat_loop(self):
        """Background task to send periodic heartbeats to Service Registry."""
        while not self.shutdown_event.is_set():
            try:
                health_data = {
                    "status": "healthy",
                    "active_selections": self.metrics.active_tool_selections._value.get(),
                }
                await self.service_registry_client.send_heartbeat(health_data)
            except Exception as e:
                logger.warning("heartbeat_failed", error=str(e))

            await asyncio.sleep(self.settings.HEARTBEAT_INTERVAL_SECONDS)


# Global service instance
service = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for FastAPI."""
    global service
    service = MCPToolCatalogService()
    await service.startup()

    # Inject dependencies into API routers
    from src.api import tools, selections
    tools.set_tool_registry(service.tool_registry)
    selections.set_genetic_selector(service.genetic_selector)

    yield
    await service.shutdown()


def create_service_app() -> FastAPI:
    """Create FastAPI application with lifespan."""
    app = create_app(lifespan=lifespan)

    # Start Prometheus metrics on dedicated port 9091
    settings = get_settings()
    if hasattr(settings, 'METRICS_PORT'):
        try:
            start_http_server(settings.METRICS_PORT)
            logger.info("prometheus_metrics_server_started", port=settings.METRICS_PORT)
        except Exception as e:
            logger.warning("prometheus_metrics_server_failed", error=str(e))

    return app


def handle_shutdown(sig, frame):
    """Handle shutdown signals."""
    logger.info("received_shutdown_signal", signal=sig)
    sys.exit(0)


async def main():
    """Main entry point."""
    # Setup logging
    settings = get_settings()
    setup_logging(settings.LOG_LEVEL, settings.LOG_FORMAT)

    logger.info(
        "initializing_mcp_tool_catalog",
        service=settings.SERVICE_NAME,
        version=settings.SERVICE_VERSION,
    )

    # Register signal handlers
    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    # Create and run FastAPI app
    app = create_service_app()

    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=settings.HTTP_PORT,
        log_level=settings.LOG_LEVEL.lower(),
        access_log=False,
    )

    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
