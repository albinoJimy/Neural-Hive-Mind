import asyncio
from typing import Optional

import grpc
import structlog
from neural_hive_observability import create_instrumented_grpc_server

from src.config.settings import get_settings
from src.grpc_service.optimizer_servicer import OptimizerServicer

logger = structlog.get_logger()

# Proto imports - will be available after `make proto` compilation
try:
    from src.proto import optimizer_agent_pb2_grpc
    from grpc_reflection.v1alpha import reflection
    PROTO_AVAILABLE = True
except ImportError:
    PROTO_AVAILABLE = False
    logger.warning("proto_not_compiled", message="Run 'make proto' to compile protocol buffers")


class GrpcServer:
    """
    gRPC server para Optimizer Agent.

    Gerencia lifecycle do servidor gRPC.
    """

    def __init__(
        self,
        servicer: OptimizerServicer,
        settings=None,
    ):
        self.servicer = servicer
        self.settings = settings or get_settings()
        self.server: Optional[grpc.aio.Server] = None

    async def start(self):
        """Iniciar servidor gRPC."""
        try:
            # Criar servidor
            base_server = grpc.aio.server(
                options=[
                    ("grpc.max_send_message_length", 100 * 1024 * 1024),
                    ("grpc.max_receive_message_length", 100 * 1024 * 1024),
                    ("grpc.keepalive_time_ms", 30000),
                    ("grpc.keepalive_timeout_ms", 10000),
                    ("grpc.keepalive_permit_without_calls", 1),
                    ("grpc.http2.max_pings_without_data", 0),
                ]
            )
            self.server = create_instrumented_grpc_server(base_server)

            # Registrar servicer quando proto estiver compilado
            if PROTO_AVAILABLE:
                optimizer_agent_pb2_grpc.add_OptimizerAgentServicer_to_server(
                    self.servicer, self.server
                )

                # Habilitar reflexão gRPC para debugging
                from src.proto import optimizer_agent_pb2
                SERVICE_NAMES = (
                    optimizer_agent_pb2.DESCRIPTOR.services_by_name['OptimizerAgent'].full_name,
                    reflection.SERVICE_NAME,
                )
                reflection.enable_server_reflection(SERVICE_NAMES, self.server)
                logger.info("grpc_servicer_registered", reflection_enabled=True)
            else:
                logger.warning("grpc_servicer_not_registered", reason="proto_not_compiled")

            # Adicionar porta
            listen_addr = f"[::]:{self.settings.grpc_port}"
            self.server.add_insecure_port(listen_addr)

            # Iniciar
            await self.server.start()

            logger.info("grpc_server_started", address=listen_addr, port=self.settings.grpc_port)

            # Aguardar shutdown
            await self.server.wait_for_termination()

        except Exception as e:
            logger.error("grpc_server_start_failed", error=str(e))
            raise

    async def stop(self, grace_period: float = 5.0):
        """
        Parar servidor gRPC.

        Args:
            grace_period: Período de graça em segundos
        """
        if self.server:
            logger.info("grpc_server_stopping", grace_period=grace_period)
            await self.server.stop(grace_period)
            logger.info("grpc_server_stopped")


async def serve(servicer: OptimizerServicer, settings=None):
    """
    Função helper para iniciar servidor gRPC.

    Args:
        servicer: OptimizerServicer instance
        settings: Settings instance
    """
    server = GrpcServer(servicer, settings)
    await server.start()
