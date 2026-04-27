"""Cache Redis para embeddings."""

import json
from datetime import datetime, timezone
from typing import List, Optional

import structlog
from redis.asyncio import ConnectionPool, Redis

from knowledge_graph_rag.config.settings import get_settings
from knowledge_graph_rag.embeddings.models import CachedEmbedding

logger = structlog.get_logger()
settings = get_settings()


class EmbeddingCache:
    """Cache Redis para embeddings."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        db: Optional[int] = None,
        password: Optional[str] = None,
        prefix: Optional[str] = None,
        ttl: Optional[int] = None,
    ):
        """Inicializa o cache de embeddings.

        Args:
            host: Host Redis
            port: Porta Redis
            db: Database Redis
            password: Senha Redis
            prefix: Prefixo para chaves
            ttl: Time to live em segundos
        """
        self.host = host or settings.redis_host
        self.port = port or settings.redis_port
        self.db = db or settings.redis_db
        self.password = password or settings.redis_password
        self.prefix = prefix or settings.embedding_cache_prefix
        self.ttl = ttl or settings.embedding_cache_ttl
        self._pool: Optional[ConnectionPool] = None
        self._client: Optional[Redis] = None

    async def connect(self):
        """Estabelece conexão com Redis."""
        try:
            self._pool = ConnectionPool(
                host=self.host,
                port=self.port,
                db=self.db,
                password=self.password,
                decode_responses=True,
            )
            self._client = Redis(connection_pool=self._pool)
            await self._client.ping()
            logger.info(
                "embedding_cache_connected",
                host=self.host,
                port=self.port,
                db=self.db,
            )
        except Exception as e:
            logger.warning(
                "embedding_cache_connection_failed",
                host=self.host,
                error=str(e),
            )
            self._client = None

    async def close(self):
        """Fecha conexão com Redis."""
        if self._client:
            await self._client.close()
            logger.info("embedding_cache_closed")

    def _generate_key(self, text: str, model: str) -> str:
        """Gera chave para cache.

        Args:
            text: Texto para gerar chave
            model: Modelo de embedding

        Returns:
            Chave hash para o cache
        """
        import hashlib

        content = f"{model}:{text}"
        hash_key = hashlib.sha256(content.encode()).hexdigest()[:32]
        return f"{self.prefix}{hash_key}"

    async def get(self, text: str, model: str) -> Optional[List[float]]:
        """Recupera embedding do cache.

        Args:
            text: Texto original
            model: Modelo de embedding

        Returns:
            Vetor de embedding ou None se não encontrado
        """
        if not self._client:
            return None

        try:
            key = self._generate_key(text, model)
            cached = await self._client.get(key)

            if cached:
                data = json.loads(cached)
                logger.debug("embedding_cache_hit", key=key)
                return data.get("embedding")
            else:
                logger.debug("embedding_cache_miss", key=key)
                return None

        except Exception as e:
            logger.warning("embedding_cache_get_error", error=str(e))
            return None

    async def set(self, text: str, embedding: List[float], model: str) -> bool:
        """Armazena embedding no cache.

        Args:
            text: Texto original
            embedding: Vetor de embedding
            model: Modelo de embedding

        Returns:
            True se armazenado com sucesso
        """
        if not self._client:
            return False

        try:
            key = self._generate_key(text, model)

            cached = CachedEmbedding(
                text=text,
                embedding=embedding,
                model=model,
                created_at=datetime.now(timezone.utc).isoformat(),
            )

            await self._client.setex(
                key,
                self.ttl,
                cached.model_dump_json(),
            )

            logger.debug("embedding_cached", key=key, ttl=self.ttl)
            return True

        except Exception as e:
            logger.warning("embedding_cache_set_error", error=str(e))
            return False

    async def exists(self, text: str, model: str) -> bool:
        """Verifica se embedding existe no cache.

        Args:
            text: Texto original
            model: Modelo de embedding

        Returns:
            True se existe no cache
        """
        if not self._client:
            return False

        try:
            key = self._generate_key(text, model)
            return await self._client.exists(key) > 0

        except Exception as e:
            logger.warning("embedding_cache_exists_error", error=str(e))
            return False

    async def clear(self):
        """Limpa todos os embeddings do cache."""
        if not self._client:
            return

        try:
            pattern = f"{self.prefix}*"
            keys = []

            async for key in self._client.scan_iter(match=pattern):
                keys.append(key)

            if keys:
                await self._client.delete(*keys)
                logger.info("embedding_cache_cleared", count=len(keys))
            else:
                logger.debug("embedding_cache_no_keys_to_clear")

        except Exception as e:
            logger.warning("embedding_cache_clear_error", error=str(e))

    async def delete(self, text: str, model: str) -> bool:
        """Remove um embedding específico do cache.

        Args:
            text: Texto original
            model: Modelo de embedding

        Returns:
            True se removido com sucesso
        """
        if not self._client:
            return False

        try:
            key = self._generate_key(text, model)
            result = await self._client.delete(key)

            if result:
                logger.debug("embedding_deleted", key=key)
                return True
            else:
                logger.debug("embedding_not_found_for_deletion", key=key)
                return False

        except Exception as e:
            logger.warning("embedding_cache_delete_error", error=str(e))
            return False

    @property
    def is_connected(self) -> bool:
        """Verifica se está conectado ao Redis.

        Returns:
            True se conectado
        """
        return self._client is not None
