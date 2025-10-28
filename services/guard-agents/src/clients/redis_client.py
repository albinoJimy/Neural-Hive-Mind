"""Redis client for Guard Agents"""
from typing import Optional
import redis.asyncio as aioredis
import structlog

logger = structlog.get_logger()


class RedisClient:
    """Cliente Redis assíncrono para Guard Agents"""

    def __init__(self, host: str, port: int, db: int = 0, password: Optional[str] = None):
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self.client: Optional[aioredis.Redis] = None

    async def connect(self):
        """Conecta ao Redis"""
        try:
            self.client = await aioredis.from_url(
                f"redis://{self.host}:{self.port}/{self.db}",
                password=self.password,
                encoding="utf-8",
                decode_responses=True
            )
            # Testa conexão
            await self.client.ping()
            logger.info("redis.connected", host=self.host, port=self.port, db=self.db)
        except Exception as e:
            logger.error("redis.connection_failed", error=str(e))
            raise

    async def close(self):
        """Fecha conexão com Redis"""
        if self.client:
            await self.client.close()
            logger.info("redis.connection_closed")

    def is_healthy(self) -> bool:
        """Verifica se cliente está saudável"""
        return self.client is not None

    async def get(self, key: str) -> Optional[str]:
        """Obtém valor do Redis"""
        if not self.client:
            return None
        return await self.client.get(key)

    async def set(self, key: str, value: str, ex: Optional[int] = None):
        """Define valor no Redis"""
        if not self.client:
            return
        await self.client.set(key, value, ex=ex)

    async def delete(self, key: str):
        """Deleta chave do Redis"""
        if not self.client:
            return
        await self.client.delete(key)
