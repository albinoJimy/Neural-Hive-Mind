"""
Cliente Redis compartilhado para cache de SLA budgets e deduplicação de alertas.
"""
from typing import Optional
from functools import lru_cache
import redis.asyncio as redis
import structlog

from src.config.settings import OrchestratorSettings

logger = structlog.get_logger(__name__)


_redis_client_instance: Optional[redis.Redis] = None


async def get_redis_client(config: Optional[OrchestratorSettings] = None) -> Optional[redis.Redis]:
    """
    Retorna instância singleton do cliente Redis.

    Args:
        config: Configurações do orchestrator (opcional, usa get_settings() se não fornecido)

    Returns:
        Cliente Redis inicializado ou None se configuração estiver incompleta
    """
    global _redis_client_instance

    if _redis_client_instance is not None:
        return _redis_client_instance

    if config is None:
        from src.config.settings import get_settings
        config = get_settings()

    try:
        # Parsear nodes do cluster Redis
        cluster_nodes = config.redis_cluster_nodes
        if not cluster_nodes:
            logger.warning("redis_cluster_nodes_not_configured")
            return None

        # Formato esperado: "host1:port1,host2:port2" ou "host:port"
        nodes = cluster_nodes.split(',')
        if not nodes:
            logger.warning("redis_cluster_nodes_empty")
            return None

        # Usar primeiro node para conexão standalone
        # (Em produção com cluster real, usar RedisCluster)
        first_node = nodes[0].strip()
        host, port = first_node.split(':')

        # Criar cliente Redis
        _redis_client_instance = redis.Redis(
            host=host,
            port=int(port),
            password=config.redis_password,
            ssl=config.redis_ssl_enabled,
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=2
        )

        # Testar conexão
        await _redis_client_instance.ping()

        logger.info(
            "redis_client_initialized",
            host=host,
            port=port,
            ssl=config.redis_ssl_enabled
        )

        return _redis_client_instance

    except Exception as e:
        logger.warning(
            "redis_client_initialization_failed",
            error=str(e)
        )
        # Fail-open: retornar None e permitir operação sem Redis
        _redis_client_instance = None
        return None


async def close_redis_client():
    """Fecha conexão Redis gracefully."""
    global _redis_client_instance

    if _redis_client_instance:
        try:
            await _redis_client_instance.aclose()
            logger.info("redis_client_closed")
        except Exception as e:
            logger.warning("redis_client_close_error", error=str(e))
        finally:
            _redis_client_instance = None
