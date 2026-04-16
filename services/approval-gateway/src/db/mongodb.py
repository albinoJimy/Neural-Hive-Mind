"""Cliente MongoDB para Approval Gateway."""

from functools import lru_cache
from motor.motor_asyncio import AsyncIOMotorClient
import structlog

from src.config.settings import get_settings

logger = structlog.get_logger(__name__)


@lru_cache
def get_mongodb_client():
    """Retorna cliente MongoDB singleton."""
    settings = get_settings()
    return AsyncMongoDBClient(
        url=settings.mongodb_url,
        database=settings.mongodb_database
    )


class AsyncMongoDBClient:
    """Cliente MongoDB assíncrono."""

    def __init__(self, url: str, database: str):
        """Inicializa cliente."""
        self._url = url
        self._database_name = database
        self._client: AsyncIOMotorClient | None = None
        self._db = None
        self._logger = logger

    async def connect(self):
        """Conecta ao MongoDB."""
        if self._client is None:
            self._logger.info("connecting_mongodb", database=self._database_name)
            self._client = AsyncIOMotorClient(self._url)
            self._db = self._client[self._database_name]
            self._logger.info("mongodb_connected")

    async def disconnect(self):
        """Desconecta do MongoDB."""
        if self._client:
            self._logger.info("disconnecting_mongodb")
            self._client.close()
            self._client = None
            self._db = None

    @property
    def client(self) -> AsyncIOMotorClient:
        """Retorna cliente bruto."""
        if self._client is None:
            raise RuntimeError("MongoDB client not connected. Call connect() first.")
        return self._client

    @property
    def database(self):
        """Retorna database."""
        if self._db is None:
            raise RuntimeError("MongoDB not connected. Call connect() first.")
        return self._db

    async def ping(self) -> bool:
        """Verifica conexão."""
        try:
            await self._client.admin.command('ping')
            return True
        except Exception as e:
            self._logger.error("mongodb_ping_failed", error=str(e))
            return False
