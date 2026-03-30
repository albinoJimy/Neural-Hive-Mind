"""
MongoDB Client para Feature Store

Fornece interface async para MongoDB para persistência de features.
"""

import structlog
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient

from src.config.settings import Settings

logger = structlog.get_logger()


class MongoDBClient:
    """Cliente async MongoDB para Feature Store"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client: Optional[AsyncIOMotorClient] = None

    async def initialize(self):
        """Inicializa cliente MongoDB"""
        self.client = AsyncIOMotorClient(
            self.settings.mongodb_uri,
            maxPoolSize=self.settings.mongodb_max_pool_size,
            serverSelectionTimeoutMS=self.settings.mongodb_timeout_ms,
            retryWrites=True,
            w='majority'
        )

        # Verifica conectividade
        await self.client.admin.command('ping')

        logger.info(
            'MongoDB client inicializado',
            uri=self.settings.mongodb_uri,
            database=self.settings.mongodb_database
        )

    async def close(self):
        """Fecha cliente MongoDB"""
        if self.client:
            self.client.close()
            logger.info('MongoDB client fechado')
