import asyncio
import signal
import grpc
import structlog
from grpc_health.v1 import health, health_pb2_grpc
from neural_hive_observability import init_observability, create_instrumented_grpc_server

from src.config import get_settings
from src.clients import EtcdClient, PheromoneClient
from src.services import RegistryService, HealthCheckManager, MatchingEngine
from src.grpc_server import ServiceRegistryServicer
from src.grpc_server.auth_interceptor import SPIFFEAuthInterceptor
from src.proto import service_registry_pb2_grpc

# Import SPIFFE manager if available
try:
    from neural_hive_security import SPIFFEManager, SPIFFEConfig
    SECURITY_LIB_AVAILABLE = True
except ImportError:
    SECURITY_LIB_AVAILABLE = False
    SPIFFEManager = None
    SPIFFEConfig = None


# Configurar structured logging
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
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


class ServiceRegistryServer:
    """Servidor gRPC do Service Registry"""

    def __init__(self):
        self.settings = get_settings()
        self.server = None
        self.etcd_client = None
        self.pheromone_client = None
        self.registry_service = None
        self.matching_engine = None
        self.health_check_manager = None
        self.spiffe_manager = None
        self.auth_interceptor = None
        self._shutdown_event = asyncio.Event()

    async def initialize(self):
        """Inicializa componentes do serviço"""
        logger.info(
            "initializing_service_registry",
            service_name=self.settings.SERVICE_NAME,
            version=self.settings.SERVICE_VERSION,
            environment=self.settings.ENVIRONMENT
        )

        # Inicializar OpenTelemetry
        try:
            init_observability(
                service_name=self.settings.SERVICE_NAME,
                service_version=self.settings.SERVICE_VERSION,
                neural_hive_component="service-registry",
                neural_hive_layer="coordination",
                environment=self.settings.ENVIRONMENT,
                otel_endpoint=self.settings.OTEL_EXPORTER_ENDPOINT,
                prometheus_port=self.settings.METRICS_PORT,
                log_level=self.settings.LOG_LEVEL,
                enable_kafka=False,
                enable_grpc=True
            )
        except Exception as e:
            logger.warning(
                "observability_init_failed",
                error=str(e),
                otel_endpoint=self.settings.OTEL_EXPORTER_ENDPOINT,
                prometheus_port=self.settings.METRICS_PORT
            )

        # Inicializar clientes
        self.etcd_client = EtcdClient(
            endpoints=self.settings.ETCD_ENDPOINTS,
            prefix=self.settings.ETCD_PREFIX,
            timeout=self.settings.ETCD_TIMEOUT_SECONDS
        )
        await self.etcd_client.initialize()

        self.pheromone_client = PheromoneClient(
            cluster_nodes=self.settings.REDIS_CLUSTER_NODES,
            password=self.settings.REDIS_PASSWORD
        )
        await self.pheromone_client.initialize()

        # Inicializar serviços
        self.registry_service = RegistryService(self.etcd_client)

        self.matching_engine = MatchingEngine(
            self.etcd_client,
            self.pheromone_client
        )

        self.health_check_manager = HealthCheckManager(
            etcd_client=self.etcd_client,
            check_interval_seconds=self.settings.HEALTH_CHECK_INTERVAL_SECONDS,
            heartbeat_timeout_seconds=self.settings.HEARTBEAT_TIMEOUT_SECONDS
        )

        # Inicializar SPIFFE manager se habilitado
        if self.settings.SPIFFE_ENABLED and SECURITY_LIB_AVAILABLE:
            try:
                logger.info("initializing_spiffe_manager")

                spiffe_config = SPIFFEConfig(
                    workload_api_socket=self.settings.SPIFFE_SOCKET_PATH,
                    trust_domain=self.settings.SPIFFE_TRUST_DOMAIN
                )

                self.spiffe_manager = SPIFFEManager(spiffe_config)
                await self.spiffe_manager.initialize()

                # Criar auth interceptor se verificação de peer estiver habilitada
                if self.settings.SPIFFE_VERIFY_PEER:
                    self.auth_interceptor = SPIFFEAuthInterceptor(
                        self.spiffe_manager,
                        self.settings
                    )
                    logger.info("spiffe_auth_interceptor_created")

                logger.info("spiffe_manager_initialized")

            except Exception as e:
                logger.error("spiffe_initialization_failed", error=str(e))
                # Continue without SPIFFE if it fails
                self.spiffe_manager = None
                self.auth_interceptor = None

        # Preparar interceptors para o servidor gRPC
        interceptors = []
        if self.auth_interceptor:
            interceptors.append(self.auth_interceptor)

        # Iniciar servidor gRPC
        self.server = create_instrumented_grpc_server(
            max_workers=10,
            interceptors=interceptors if interceptors else None,
            options=[
                ('grpc.max_send_message_length', 50 * 1024 * 1024),
                ('grpc.max_receive_message_length', 50 * 1024 * 1024),
            ]
        )

        # Registrar servicer
        servicer = ServiceRegistryServicer(
            self.registry_service,
            self.matching_engine
        )

        service_registry_pb2_grpc.add_ServiceRegistryServicer_to_server(
            servicer,
            self.server
        )

        # Registrar health check
        health_servicer = health.HealthServicer()
        health_pb2_grpc.add_HealthServicer_to_server(health_servicer, self.server)
        health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)

        # Adicionar porta
        self.server.add_insecure_port(f'[::]:{self.settings.GRPC_PORT}')

        logger.info(
            "service_registry_initialized",
            grpc_port=self.settings.GRPC_PORT,
            metrics_port=self.settings.METRICS_PORT
        )

    async def start(self):
        """Inicia o servidor"""
        logger.info("starting_service_registry")

        # Inicializar
        await self.initialize()

        # Iniciar servidor gRPC
        await self.server.start()

        # Iniciar health check manager
        await self.health_check_manager.start()

        logger.info(
            "service_registry_started",
            grpc_port=self.settings.GRPC_PORT,
            metrics_port=self.settings.METRICS_PORT
        )

        # Aguardar shutdown
        await self._shutdown_event.wait()

    async def stop(self):
        """Para o servidor gracefully"""
        logger.info("stopping_service_registry")

        # Parar health check manager
        if self.health_check_manager:
            await self.health_check_manager.stop()

        # Parar servidor gRPC
        if self.server:
            await self.server.stop(grace=5)

        # Fechar SPIFFE manager
        if self.spiffe_manager:
            try:
                await self.spiffe_manager.close()
                logger.info("spiffe_manager_closed")
            except Exception as e:
                logger.warning("spiffe_manager_close_failed", error=str(e))

        # Fechar clientes
        if self.etcd_client:
            await self.etcd_client.close()

        if self.pheromone_client:
            await self.pheromone_client.close()

        logger.info("service_registry_stopped")

        # Sinalizar shutdown
        self._shutdown_event.set()

    def _handle_signal(self, signum):
        """Handler para sinais de shutdown"""
        logger.info("shutdown_signal_received", signal=signum)
        asyncio.create_task(self.stop())


async def main():
    """Entry point principal"""
    server = ServiceRegistryServer()

    # Registrar handlers de sinais
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(
            sig,
            lambda s=sig: server._handle_signal(s)
        )

    try:
        await server.start()
    except KeyboardInterrupt:
        logger.info("keyboard_interrupt_received")
    except Exception as e:
        logger.error("service_registry_error", error=str(e))
        raise
    finally:
        await server.stop()


if __name__ == "__main__":
    asyncio.run(main())
