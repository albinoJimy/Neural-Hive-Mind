import asyncio
import structlog
import grpc
from concurrent import futures
from neural_hive_observability import create_instrumented_grpc_server

from .analyst_servicer import AnalystServicer
from ..proto import analyst_agent_pb2_grpc

logger = structlog.get_logger()


class AnalystGRPCServer:
    """Servidor gRPC para Analyst Agent"""

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

        # Dependências
        self.mongodb_client = mongodb_client
        self.redis_client = redis_client
        self.query_engine = query_engine
        self.analytics_engine = analytics_engine
        self.insight_generator = insight_generator
        self.neo4j_client = neo4j_client

    async def start(self):
        """Iniciar servidor gRPC"""
        try:
            logger.info('starting_grpc_server', host=self.host, port=self.port)

            # Criar servidor
            base_server = grpc.aio.server(
                futures.ThreadPoolExecutor(max_workers=self.max_workers)
            )
            self.server = create_instrumented_grpc_server(base_server)

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

            # Adicionar porta
            self.server.add_insecure_port(f'{self.host}:{self.port}')

            # Iniciar
            await self.server.start()

            logger.info('grpc_server_started', address=f'{self.host}:{self.port}')

        except Exception as e:
            logger.error('grpc_server_start_failed', error=str(e))
            raise

    async def stop(self, grace_period: int = 5):
        """Parar servidor gRPC"""
        if self.server:
            logger.info('stopping_grpc_server', grace_period=grace_period)
            await self.server.stop(grace_period)
            logger.info('grpc_server_stopped')

    async def wait_for_termination(self):
        """Aguardar terminação"""
        if self.server:
            await self.server.wait_for_termination()
