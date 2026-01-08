"""
Servidor gRPC para Orchestrator Dynamic.

Gerencia lifecycle do servidor gRPC com suporte a mTLS via SPIFFE/SPIRE.
"""

import grpc
import structlog
from typing import Optional

from src.proto import orchestrator_strategic_pb2_grpc
from .orchestrator_servicer import OrchestratorStrategicServicer

# Import SPIFFE se disponível
try:
    from neural_hive_security import SPIFFEManager
    SECURITY_LIB_AVAILABLE = True
except ImportError:
    SECURITY_LIB_AVAILABLE = False
    SPIFFEManager = None

logger = structlog.get_logger(__name__)


async def start_grpc_server(
    servicer: OrchestratorStrategicServicer,
    port: int,
    spiffe_manager: Optional['SPIFFEManager'] = None,
    enable_mtls: bool = True
) -> grpc.aio.Server:
    """
    Iniciar servidor gRPC com mTLS opcional.

    Args:
        servicer: Implementação do servicer OrchestratorStrategic
        port: Porta para o servidor
        spiffe_manager: Manager SPIFFE para mTLS (opcional)
        enable_mtls: Habilitar mTLS via SPIFFE (default: True)

    Returns:
        Servidor gRPC iniciado
    """
    server = grpc.aio.server(
        options=[
            ('grpc.max_send_message_length', 100 * 1024 * 1024),
            ('grpc.max_receive_message_length', 100 * 1024 * 1024),
            ('grpc.keepalive_time_ms', 30000),
            ('grpc.keepalive_timeout_ms', 10000),
            ('grpc.http2.min_ping_interval_without_data_ms', 30000),
        ]
    )

    orchestrator_strategic_pb2_grpc.add_OrchestratorStrategicServicer_to_server(
        servicer, server
    )

    if enable_mtls and spiffe_manager and SECURITY_LIB_AVAILABLE:
        try:
            # Buscar X.509-SVID para mTLS
            x509_svid = await spiffe_manager.fetch_x509_svid()

            credentials = grpc.ssl_server_credentials(
                [(
                    x509_svid.private_key.encode('utf-8'),
                    x509_svid.certificate.encode('utf-8')
                )],
                root_certificates=x509_svid.ca_bundle.encode('utf-8'),
                require_client_auth=True
            )
            server.add_secure_port(f'[::]:{port}', credentials)

            logger.info(
                'grpc_server_mtls_configured',
                port=port,
                spiffe_id=x509_svid.spiffe_id
            )

        except Exception as e:
            logger.warning(
                'grpc_server_mtls_failed_fallback_insecure',
                error=str(e),
                port=port
            )
            server.add_insecure_port(f'[::]:{port}')
    else:
        if enable_mtls:
            logger.warning(
                'grpc_server_mtls_not_available',
                spiffe_manager_available=spiffe_manager is not None,
                security_lib_available=SECURITY_LIB_AVAILABLE
            )
        server.add_insecure_port(f'[::]:{port}')
        logger.info('grpc_server_insecure_configured', port=port)

    await server.start()
    logger.info('grpc_server_started', port=port)

    return server


async def stop_grpc_server(server: grpc.aio.Server, grace_seconds: int = 5):
    """
    Parar servidor gRPC graciosamente.

    Args:
        server: Servidor gRPC a parar
        grace_seconds: Segundos de grace period
    """
    if server:
        logger.info('grpc_server_stopping', grace_seconds=grace_seconds)
        await server.stop(grace=grace_seconds)
        logger.info('grpc_server_stopped')
