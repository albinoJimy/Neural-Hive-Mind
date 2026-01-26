"""
Gerenciador do servidor gRPC.

NOTA: Será atualizado após compilação do proto.
"""
import asyncio
import socket
import time
from typing import Optional, Tuple, Any

import grpc
import structlog
from neural_hive_observability import create_instrumented_grpc_server, get_config
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, before_sleep_log

logger = structlog.get_logger(__name__)

# gRPC Health Check imports
try:
    from grpc_health.v1 import health_pb2, health_pb2_grpc
    from grpc_health.v1.health import HealthServicer
    HEALTH_CHECK_AVAILABLE = True
except ImportError:
    HEALTH_CHECK_AVAILABLE = False
    logger.warning('grpc_health_not_available: grpc-health-checking package not installed')


def _check_port_available(port: int) -> bool:
    """
    Verifica se a porta está disponível para bind.
    
    Args:
        port: Número da porta a verificar
        
    Returns:
        True se a porta está disponível, False caso contrário
    """
    try:
        with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(('::', port))
            return True
    except OSError:
        return False


async def _bind_port_with_retry(server, port: int, max_attempts: int, initial_delay: float, max_delay: float) -> None:
    """
    Tenta fazer bind da porta gRPC com retry e exponential backoff.
    
    Args:
        server: Instância do servidor gRPC
        port: Porta para bind
        max_attempts: Número máximo de tentativas
        initial_delay: Delay inicial entre retries (segundos)
        max_delay: Delay máximo entre retries (segundos)
        
    Raises:
        RuntimeError: Se todas as tentativas falharem
    """
    last_error = None
    
    for attempt in range(1, max_attempts + 1):
        try:
            # Verificar disponibilidade da porta antes de tentar bind
            if not _check_port_available(port):
                logger.warning(
                    'grpc_port_in_use',
                    port=port,
                    attempt=attempt,
                    max_attempts=max_attempts
                )
                raise OSError(f'Porta {port} está em uso')
            
            bound_port = server.add_insecure_port(f'[::]:{port}')
            if bound_port <= 0:
                raise RuntimeError(f'Falha ao fazer bind da porta gRPC {port}: add_insecure_port retornou {bound_port}')
            
            logger.info(
                'grpc_port_bound',
                port=port,
                bound_port=bound_port,
                attempt=attempt,
                attempts_needed=attempt
            )
            return
            
        except (OSError, RuntimeError) as e:
            last_error = e
            
            if attempt == max_attempts:
                logger.error(
                    'grpc_bind_failed_all_attempts',
                    port=port,
                    attempts=max_attempts,
                    last_error=str(e),
                    exc_info=True
                )
                raise RuntimeError(
                    f'Falha ao fazer bind da porta gRPC {port} após {max_attempts} tentativas. '
                    f'Último erro: {e}'
                ) from e
            
            # Calcular delay com exponential backoff
            delay = min(initial_delay * (2 ** (attempt - 1)), max_delay)
            
            logger.warning(
                'grpc_bind_retry',
                port=port,
                attempt=attempt,
                max_attempts=max_attempts,
                delay_seconds=delay,
                error=str(e)
            )
            
            await asyncio.sleep(delay)


async def start_grpc_server(settings) -> Tuple[Any, Optional[Any]]:
    """
    Inicia servidor gRPC com retry logic para bind de porta.

    Args:
        settings: TicketServiceSettings

    Returns:
        Tupla (gRPC server instance, health_servicer ou None)

    Raises:
        ImportError: Se os arquivos protobuf não foram gerados
        RuntimeError: Se falhar ao iniciar o servidor após todas as tentativas
    """
    start_time = time.monotonic()
    
    # Verificar se os módulos protobuf estão disponíveis
    try:
        from ..proto_gen import ticket_service_pb2_grpc
        from .ticket_servicer import TicketServiceServicer
    except ImportError as e:
        logger.error(
            'grpc_protobuf_import_failed',
            extra={
                'error': str(e),
                'hint': 'Run: ./scripts/compile_protos.sh to generate protobuf files'
            }
        )
        raise

    logger.info(
        'grpc_server_initializing',
        port=settings.grpc_port,
        max_workers=settings.grpc_max_workers,
        retry_attempts=settings.grpc_bind_retry_attempts
    )

    # Sempre usar grpc.aio.server() para compatibilidade com async context
    # O create_instrumented_grpc_server retorna servidor síncrono, não compatível com await
    server = grpc.aio.server(
        options=[
            ('grpc.max_concurrent_streams', settings.grpc_max_concurrent_rpcs),
            ('grpc.keepalive_time_ms', 30000),
            ('grpc.keepalive_timeout_ms', 10000),
        ]
    )
    
    observability_config = get_config()
    if observability_config is None:
        logger.warning('observability_config_not_initialized: usando servidor gRPC básico')

    # Registrar servicer
    ticket_service_pb2_grpc.add_TicketServiceServicer_to_server(
        TicketServiceServicer(),
        server
    )
    logger.info('grpc_servicer_registered')

    # Registrar Health Check gRPC padrão
    health_servicer = None
    if HEALTH_CHECK_AVAILABLE:
        health_servicer = HealthServicer()
        health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
        
        # Definir status inicial como SERVING para serviço global e específico
        health_servicer.set('', health_pb2.HealthCheckResponse.SERVING)
        health_servicer.set('ticket_service.TicketService', health_pb2.HealthCheckResponse.SERVING)
        logger.info('grpc_health_check_registered')
    else:
        logger.warning('grpc_health_check_not_registered: grpc-health-checking not installed')

    # Bind da porta com retry logic
    await _bind_port_with_retry(
        server=server,
        port=settings.grpc_port,
        max_attempts=settings.grpc_bind_retry_attempts,
        initial_delay=settings.grpc_bind_retry_initial_delay,
        max_delay=settings.grpc_bind_retry_max_delay
    )

    # Iniciar servidor
    await server.start()
    
    elapsed_time = time.monotonic() - start_time
    logger.info(
        'grpc_server_started',
        port=settings.grpc_port,
        initialization_time_seconds=round(elapsed_time, 3)
    )

    return server, health_servicer


async def stop_grpc_server(server, health_servicer=None):
    """
    Para servidor gRPC gracefully.

    Args:
        server: gRPC server instance
        health_servicer: Health servicer instance (opcional)
    """
    if server is None:
        return

    # Atualizar health check para NOT_SERVING antes de parar
    if HEALTH_CHECK_AVAILABLE and health_servicer is not None:
        health_servicer.set('', health_pb2.HealthCheckResponse.NOT_SERVING)
        health_servicer.set('ticket_service.TicketService', health_pb2.HealthCheckResponse.NOT_SERVING)
        logger.info('grpc_health_check_set_not_serving')

    logger.info('Stopping gRPC server...')
    await server.stop(grace=5)
    logger.info('gRPC server stopped')
