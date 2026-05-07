"""Redis client simplificado para Unified Gateway.

Fornece uma interface simples para operações Redis básicas necessárias
para o Unified Gateway (status tracking, rate limiting, etc.).
"""

import logging
from typing import Any

from redis.asyncio import Redis

from src.config.settings import get_settings

logger = logging.getLogger(__name__)

# Cliente global singleton
_redis_client: Redis | None = None


async def get_redis_client() -> Redis | None:
    """Obter cliente Redis singleton.

    Returns:
        Redis client ou None se Redis não estiver configurado/disponível
    """
    global _redis_client

    settings = get_settings()

    # Verificar se Redis está configurado
    redis_url = getattr(settings, "redis_url", None)
    if not redis_url:
        return None

    # Se já temos um cliente, tentar ping para verificar se ainda está conectado
    if _redis_client is not None:
        try:
            await _redis_client.ping()
            return _redis_client
        except Exception:
            # Conexão perdida, resetar
            _redis_client = None

    # Tentar criar nova conexão
    try:
        _redis_client = Redis.from_url(
            redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
        # Testar conexão
        await _redis_client.ping()
        logger.info("Redis client inicializado com sucesso")
        return _redis_client
    except Exception as e:
        logger.warning(f"Falha ao conectar ao Redis: {e}")
        _redis_client = None
        return None


async def close_redis_client():
    """Fechar cliente Redis global."""
    global _redis_client

    if _redis_client:
        await _redis_client.close()
        _redis_client = None
        logger.info("Redis client fechado")
