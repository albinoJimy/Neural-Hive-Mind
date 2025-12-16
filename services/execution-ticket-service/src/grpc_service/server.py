"""
Gerenciador do servidor gRPC.

NOTA: Será atualizado após compilação do proto.
"""
import asyncio
import logging
from typing import Optional

import grpc
from neural_hive_observability import create_instrumented_grpc_server
from . import ticket_service_pb2_grpc
from .ticket_servicer import TicketServiceServicer

logger = logging.getLogger(__name__)


async def start_grpc_server(settings) -> Optional[object]:
    """
    Inicia servidor gRPC.

    Args:
        settings: TicketServiceSettings

    Returns:
        gRPC server instance
    """
    server = create_instrumented_grpc_server(
        max_workers=settings.grpc_max_workers,
        options=[
            ('grpc.max_concurrent_streams', settings.grpc_max_concurrent_rpcs),
            ('grpc.keepalive_time_ms', 30000),
            ('grpc.keepalive_timeout_ms', 10000),
        ]
    )

    # Registrar servicer
    ticket_service_pb2_grpc.add_TicketServiceServicer_to_server(
        TicketServiceServicer(),
        server
    )

    # Adicionar porta
    server.add_insecure_port(f'[::]:{settings.grpc_port}')

    # Iniciar servidor
    await server.start()
    logger.info(f'gRPC server started on port {settings.grpc_port}')

    return server


async def stop_grpc_server(server):
    """
    Para servidor gRPC gracefully.

    Args:
        server: gRPC server instance
    """
    if server is None:
        return

    logger.info('Stopping gRPC server...')
    await server.stop(grace=5)
    logger.info('gRPC server stopped')
