"""MongoDB client para Hypothesis Library."""

from __future__ import annotations

import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient

from src.config.settings import Settings, get_settings

logger = logging.getLogger(__name__)


class MongoDBClient:
    """Cliente MongoDB para Hypothesis Library."""

    def __init__(self, settings: Settings | None = None):
        """
        Inicializa cliente.

        Args:
            settings: Configurações (usa get_settings() se None)
        """
        self.settings = settings or get_settings()
        self.client: AsyncIOMotorClient | None = None

    async def connect(self) -> None:
        """Estabelece conexão com MongoDB."""
        try:
            self.client = AsyncIOMotorClient(
                self.settings.mongodb_uri,
                maxPoolSize=self.settings.mongodb_max_pool_size,
                minPoolSize=self.settings.mongodb_min_pool_size,
            )

            # Testar conexão
            await self.client.admin.command("ping")

            logger.info(
                "mongodb_connected",
                database=self.settings.mongodb_database,
            )
        except Exception as e:
            logger.error("mongodb_connection_failed", error=str(e))
            raise

    async def disconnect(self) -> None:
        """Fecha conexão com MongoDB."""
        if self.client:
            self.client.close()
            logger.info("mongodb_disconnected")

    def get_client(self) -> AsyncIOMotorClient:
        """
        Retorna o cliente Motor.

        Returns:
            Instância de AsyncIOMotorClient

        Raises:
            RuntimeError: Se não conectado
        """
        if not self.client:
            raise RuntimeError("MongoDB client not connected")
        return self.client
