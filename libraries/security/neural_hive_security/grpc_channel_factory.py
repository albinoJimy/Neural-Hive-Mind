"""
Factory para criação de canais gRPC seguros com SPIFFE/SPIRE mTLS.
Centraliza lógica de criação de canais para reutilização em todos os serviços.
"""

import grpc
import structlog
from typing import Optional, List, Tuple
from prometheus_client import Counter

from .spiffe_manager import SPIFFEManager, X509SVID, SPIFFEFetchError
from .config import SPIFFEConfig

logger = structlog.get_logger(__name__)

# Métricas Prometheus
mtls_channel_created_total = Counter(
    'mtls_channel_created_total',
    'Total de canais gRPC mTLS criados',
    ['status']
)

insecure_channel_created_total = Counter(
    'insecure_channel_created_total',
    'Total de canais gRPC inseguros criados (apenas dev)',
    ['environment']
)


async def create_secure_grpc_channel(
    target: str,
    spiffe_config: SPIFFEConfig,
    spiffe_manager: Optional[SPIFFEManager] = None,
    fallback_insecure: bool = False
) -> grpc.aio.Channel:
    """
    Cria canal gRPC seguro com mTLS via SPIFFE X.509-SVID.

    Args:
        target: Endereço do servidor (host:port)
        spiffe_config: Configuração SPIFFE
        spiffe_manager: Manager existente (opcional, cria novo se None)
        fallback_insecure: Permitir fallback para insecure em dev (default: False)

    Returns:
        Canal gRPC (secure ou insecure se fallback habilitado em dev)

    Raises:
        RuntimeError: Se mTLS requerido mas SPIFFE indisponível
    """
    # Verificar se SPIFFE X.509 está habilitado
    if spiffe_config.enable_x509:
        try:
            # Criar ou reutilizar SPIFFE manager
            manager = spiffe_manager
            manager_created = False

            if manager is None:
                manager = SPIFFEManager(spiffe_config)
                await manager.initialize()
                manager_created = True

            try:
                # Buscar X.509-SVID
                x509_svid = await manager.fetch_x509_svid()

                # Criar credenciais SSL
                credentials = grpc.ssl_channel_credentials(
                    root_certificates=x509_svid.ca_bundle.encode('utf-8'),
                    private_key=x509_svid.private_key.encode('utf-8'),
                    certificate_chain=x509_svid.certificate.encode('utf-8')
                )

                # Criar canal seguro
                channel = grpc.aio.secure_channel(target, credentials)

                mtls_channel_created_total.labels(status='success').inc()
                logger.info(
                    'mtls_channel_created',
                    target=target,
                    spiffe_id=x509_svid.spiffe_id,
                    expires_at=x509_svid.expires_at.isoformat()
                )

                return channel

            finally:
                # Se criamos o manager internamente e houve erro, fechar
                if manager_created and manager:
                    # Não fechar em caso de sucesso - será gerenciado externamente
                    pass

        except SPIFFEFetchError as e:
            mtls_channel_created_total.labels(status='error').inc()
            logger.error('mtls_channel_creation_failed', target=target, error=str(e))

            # Verificar se fallback é permitido
            if not fallback_insecure:
                raise RuntimeError(f"Failed to create mTLS channel: {e}")

            # Fallback apenas em desenvolvimento
            is_dev_env = spiffe_config.environment.lower() in ('dev', 'development')
            if not is_dev_env:
                raise RuntimeError(
                    f"mTLS required in {spiffe_config.environment} but failed. "
                    f"Insecure fallback disabled for security. Error: {e}"
                )

        except Exception as e:
            mtls_channel_created_total.labels(status='error').inc()
            logger.error('mtls_channel_creation_failed', target=target, error=str(e))

            if not fallback_insecure:
                raise RuntimeError(f"Failed to create mTLS channel: {e}")

            # Fallback apenas em desenvolvimento
            is_dev_env = spiffe_config.environment.lower() in ('dev', 'development')
            if not is_dev_env:
                raise RuntimeError(
                    f"mTLS required in {spiffe_config.environment} but failed. "
                    f"Insecure fallback disabled for security. Error: {e}"
                )

    # Fallback para canal inseguro (apenas desenvolvimento)
    is_dev_env = spiffe_config.environment.lower() in ('dev', 'development')
    if not is_dev_env:
        raise RuntimeError(
            f"mTLS is required in {spiffe_config.environment} but SPIFFE X.509 is disabled. "
            "Set enable_x509=True in SPIFFEConfig."
        )

    insecure_channel_created_total.labels(environment=spiffe_config.environment).inc()
    logger.warning(
        'using_insecure_channel',
        target=target,
        environment=spiffe_config.environment,
        warning='mTLS disabled - NOT FOR PRODUCTION USE'
    )

    return grpc.aio.insecure_channel(target)


def create_secure_grpc_channel_sync(
    target: str,
    x509_svid: X509SVID
) -> grpc.Channel:
    """
    Cria canal gRPC seguro síncrono com X.509-SVID já obtido.

    Args:
        target: Endereço do servidor (host:port)
        x509_svid: X.509-SVID já obtido do SPIFFE manager

    Returns:
        Canal gRPC síncrono seguro
    """
    credentials = grpc.ssl_channel_credentials(
        root_certificates=x509_svid.ca_bundle.encode('utf-8'),
        private_key=x509_svid.private_key.encode('utf-8'),
        certificate_chain=x509_svid.certificate.encode('utf-8')
    )

    channel = grpc.secure_channel(target, credentials)

    mtls_channel_created_total.labels(status='success').inc()
    logger.info(
        'mtls_channel_created_sync',
        target=target,
        spiffe_id=x509_svid.spiffe_id,
        expires_at=x509_svid.expires_at.isoformat()
    )

    return channel


async def get_grpc_metadata_with_jwt(
    spiffe_manager: SPIFFEManager,
    audience: str,
    environment: str = 'development'
) -> List[Tuple[str, str]]:
    """
    Obtém metadata gRPC com JWT-SVID para autenticação.

    Args:
        spiffe_manager: SPIFFE manager inicializado
        audience: Audience do JWT-SVID
        environment: Ambiente de execução

    Returns:
        Lista de tuplas (key, value) para metadata gRPC
    """
    metadata: List[Tuple[str, str]] = []

    try:
        jwt_svid = await spiffe_manager.fetch_jwt_svid(audience=audience)
        metadata.append(('authorization', f'Bearer {jwt_svid.token}'))

        logger.debug(
            'jwt_svid_added_to_metadata',
            spiffe_id=jwt_svid.spiffe_id,
            expiry=jwt_svid.expiry.isoformat()
        )

    except Exception as e:
        logger.warning('jwt_svid_fetch_failed', error=str(e))

        # Falhar em produção, continuar em dev
        is_dev_env = environment.lower() in ('dev', 'development')
        if not is_dev_env:
            raise

    return metadata
