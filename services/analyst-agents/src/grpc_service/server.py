import asyncio
import structlog
import grpc
from typing import Optional, Any
from neural_hive_observability import (
    create_instrumented_async_grpc_server,
    ObservabilityConfig
)

# Importar SPIFFE/mTLS se disponível
try:
    from neural_hive_security import SPIFFEManager, SPIFFEConfig
    SECURITY_LIB_AVAILABLE = True
except ImportError:
    SECURITY_LIB_AVAILABLE = False
    SPIFFEManager = None
    SPIFFEConfig = None

from .analyst_servicer import AnalystServicer
from ..proto import analyst_agent_pb2_grpc
from ..config import get_settings

logger = structlog.get_logger()


class AnalystGRPCServer:
    """Servidor gRPC para Analyst Agent com suporte a mTLS via SPIFFE"""

    def __init__(
        self,
        host: str,
        port: int,
        mongodb_client,
        redis_client,
        query_engine,
        analytics_engine,
        insight_generator,
        neo4j_client=None,
        max_workers: int = 10
    ):
        self.host = host
        self.port = port
        self.max_workers = max_workers
        self.server = None
        self.spiffe_manager: Optional[Any] = None

        # Dependências
        self.mongodb_client = mongodb_client
        self.redis_client = redis_client
        self.query_engine = query_engine
        self.analytics_engine = analytics_engine
        self.insight_generator = insight_generator
        self.neo4j_client = neo4j_client

    async def start(self):
        """Iniciar servidor gRPC com suporte a mTLS"""
        settings = get_settings()

        try:
            logger.info('starting_grpc_server', host=self.host, port=self.port)

            # Criar configuração de observabilidade para o servidor
            observability_config = ObservabilityConfig(
                service_name=settings.SERVICE_NAME,
                service_version=settings.SERVICE_VERSION,
                neural_hive_component='analyst-agents',
                neural_hive_layer='cognitiva',
                neural_hive_domain='analytics',
                environment=settings.ENVIRONMENT,
                otel_endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT
            )

            # Criar servidor async instrumentado (sem ThreadPoolExecutor)
            self.server = create_instrumented_async_grpc_server(observability_config)

            # Registrar servicer
            servicer = AnalystServicer(
                mongodb_client=self.mongodb_client,
                redis_client=self.redis_client,
                query_engine=self.query_engine,
                analytics_engine=self.analytics_engine,
                insight_generator=self.insight_generator,
                neo4j_client=self.neo4j_client
            )
            analyst_agent_pb2_grpc.add_AnalystAgentServiceServicer_to_server(servicer, self.server)

            # Configurar porta com suporte a mTLS
            mtls_enabled = False
            if settings.SPIFFE_ENABLED and settings.SPIFFE_ENABLE_X509 and SECURITY_LIB_AVAILABLE:
                try:
                    spiffe_config = SPIFFEConfig(
                        workload_api_socket=settings.SPIFFE_SOCKET_PATH,
                        trust_domain=settings.SPIFFE_TRUST_DOMAIN,
                        enable_x509=True,
                        environment=settings.ENVIRONMENT
                    )
                    self.spiffe_manager = SPIFFEManager(spiffe_config)
                    await self.spiffe_manager.initialize()

                    server_credentials = await self.spiffe_manager.get_grpc_server_credentials()
                    self.server.add_secure_port(
                        f'{self.host}:{self.port}',
                        server_credentials
                    )
                    mtls_enabled = True
                    logger.info(
                        'grpc_server_mtls_enabled',
                        address=f'{self.host}:{self.port}'
                    )
                except Exception as e:
                    logger.error('grpc_mtls_setup_failed', error=str(e))
                    if settings.ENVIRONMENT in ['production', 'staging', 'prod']:
                        raise
                    self.server.add_insecure_port(f'{self.host}:{self.port}')
            else:
                self.server.add_insecure_port(f'{self.host}:{self.port}')
                if settings.ENVIRONMENT in ['production', 'staging', 'prod']:
                    logger.warning(
                        'grpc_server_insecure_mode_in_production',
                        address=f'{self.host}:{self.port}'
                    )

            # Iniciar
            await self.server.start()

            logger.info(
                'grpc_server_started',
                address=f'{self.host}:{self.port}',
                mtls=mtls_enabled
            )

        except Exception as e:
            logger.error('grpc_server_start_failed', error=str(e))
            raise

    async def stop(self, grace_period: int = 5):
        """Parar servidor gRPC e fechar SPIFFE manager"""
        if self.server:
            logger.info('stopping_grpc_server', grace_period=grace_period)
            await self.server.stop(grace_period)
            logger.info('grpc_server_stopped')

        if self.spiffe_manager:
            try:
                await self.spiffe_manager.close()
                logger.info('spiffe_manager_closed')
            except Exception as e:
                logger.warning('spiffe_manager_close_error', error=str(e))

    async def wait_for_termination(self):
        """Aguardar terminação"""
        if self.server:
            await self.server.wait_for_termination()
