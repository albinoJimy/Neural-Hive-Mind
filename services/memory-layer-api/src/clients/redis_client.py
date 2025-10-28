"""
Redis Client para cache e dados de curto prazo

Fornece interface assíncrona ao Redis Cluster para cache de alta performance.
"""

import json
import structlog
from typing import Dict, Optional, List
from redis.asyncio import RedisCluster
from redis.exceptions import RedisError


logger = structlog.get_logger()


class RedisClient:
    """Cliente Redis assíncrono para operações de cache"""

    def __init__(self, cluster_nodes: str, password: Optional[str] = None, ssl_enabled: bool = False):
        """
        Inicializa o cliente Redis

        Args:
            cluster_nodes: Nós do cluster Redis (separados por vírgula)
            password: Senha do Redis (opcional)
            ssl_enabled: Habilitar SSL
        """
        self.cluster_nodes = cluster_nodes
        self.password = password
        self.ssl_enabled = ssl_enabled
        self.client: Optional[RedisCluster] = None

    async def initialize(self):
        """Inicializa o cliente Redis Cluster"""
        startup_nodes = [
            {"host": node.split(':')[0], "port": int(node.split(':')[1])}
            for node in self.cluster_nodes.split(',')
        ]

        self.client = RedisCluster(
            startup_nodes=startup_nodes,
            password=self.password,
            ssl=self.ssl_enabled,
            decode_responses=True
        )

        # Verifica conectividade
        await self.client.ping()

        logger.info(
            'Redis client inicializado',
            nodes=self.cluster_nodes,
            ssl=self.ssl_enabled
        )

    async def get(self, key: str) -> Optional[str]:
        """
        Obtém valor do cache

        Args:
            key: Chave do cache

        Returns:
            Valor ou None
        """
        try:
            value = await self.client.get(key)
            if value:
                logger.debug('Cache hit', key=key)
                return value
            else:
                logger.debug('Cache miss', key=key)
                return None

        except RedisError as e:
            logger.warning('Redis get error', key=key, error=str(e))
            return None

    async def set(self, key: str, value: str, ttl: Optional[int] = None):
        """
        Define valor no cache

        Args:
            key: Chave do cache
            value: Valor a armazenar
            ttl: Tempo de vida em segundos (opcional)
        """
        try:
            if ttl:
                await self.client.setex(key, ttl, value)
            else:
                await self.client.set(key, value)

            logger.debug('Valor armazenado no cache', key=key, ttl=ttl)

        except RedisError as e:
            logger.warning('Redis set error', key=key, error=str(e))

    async def get_json(self, key: str) -> Optional[Dict]:
        """
        Obtém valor JSON do cache

        Args:
            key: Chave do cache

        Returns:
            Objeto JSON ou None
        """
        value = await self.get(key)
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError as e:
                logger.warning('JSON decode error', key=key, error=str(e))
                return None
        return None

    async def set_json(self, key: str, value: Dict, ttl: Optional[int] = None):
        """
        Armazena valor JSON no cache

        Args:
            key: Chave do cache
            value: Objeto a armazenar
            ttl: Tempo de vida em segundos (opcional)
        """
        try:
            json_str = json.dumps(value, default=str)
            await self.set(key, json_str, ttl)
        except (TypeError, ValueError) as e:
            logger.warning('JSON encode error', key=key, error=str(e))

    async def delete(self, *keys: str) -> int:
        """
        Remove chaves do cache

        Args:
            keys: Chaves a remover

        Returns:
            Número de chaves removidas
        """
        try:
            count = await self.client.delete(*keys)
            logger.debug('Chaves removidas', count=count)
            return count
        except RedisError as e:
            logger.warning('Redis delete error', error=str(e))
            return 0

    async def invalidate_cache(self, pattern: str) -> int:
        """
        Invalida entradas de cache que correspondem ao padrão

        Args:
            pattern: Padrão de chave (suporta wildcards)

        Returns:
            Número de chaves invalidadas
        """
        try:
            cursor = 0
            deleted = 0

            while True:
                cursor, keys = await self.client.scan(
                    cursor=cursor,
                    match=pattern,
                    count=100
                )

                if keys:
                    await self.client.delete(*keys)
                    deleted += len(keys)

                if cursor == 0:
                    break

            logger.info('Cache invalidado', pattern=pattern, deleted=deleted)
            return deleted

        except RedisError as e:
            logger.warning('Redis invalidate error', pattern=pattern, error=str(e))
            return 0

    async def exists(self, *keys: str) -> int:
        """
        Verifica se chaves existem

        Args:
            keys: Chaves a verificar

        Returns:
            Número de chaves que existem
        """
        try:
            return await self.client.exists(*keys)
        except RedisError as e:
            logger.warning('Redis exists error', error=str(e))
            return 0

    async def close(self):
        """Fecha conexão com Redis"""
        if self.client:
            await self.client.close()
            logger.info('Redis client fechado')
