"""Cliente MongoDB para Doc Ingestion Service."""

from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient
from structlog import get_logger

from src.config.settings import get_settings

logger = get_logger(__name__)


class AsyncMongoDBClient:
    """Cliente MongoDB assíncrono."""

    _instance: Optional["AsyncMongoDBClient"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        settings = get_settings()
        self._client: Optional[AsyncIOMotorClient] = None
        self._database_name = settings.mongodb_database
        self._initialized = True

    async def connect(self) -> None:
        """Conecta ao MongoDB."""
        if self._client is None:
            settings = get_settings()
            self._client = AsyncIOMotorClient(settings.mongodb_url)
            logger.info("mongodb_connected", database=self._database_name)

    async def disconnect(self) -> None:
        """Desconecta do MongoDB."""
        if self._client:
            self._client.close()
            self._client = None
            logger.info("mongodb_disconnected")
            # Reset singleton para permitir re-inicialização em testes
            type(self)._instance = None
            if hasattr(self, "_initialized"):
                delattr(self, "_initialized")

    async def ping(self) -> bool:
        """Verifica conexão com MongoDB."""
        if self._client is None:
            raise RuntimeError("MongoDB client not connected. Call connect() first.")
        try:
            result = await self._client.admin.command("ping")
            return result.get("ok") == 1
        except Exception as e:
            logger.error("mongodb_ping_failed", error=str(e))
            return False

    @property
    def client(self) -> AsyncIOMotorClient:
        """Retorna o cliente MongoDB."""
        if self._client is None:
            raise RuntimeError("MongoDB client not connected. Call connect() first.")
        return self._client

    @property
    def database(self):
        """Retorna o database."""
        if self._client is None:
            raise RuntimeError("MongoDB client not connected. Call connect() first.")
        return self._client[self._database_name]

    @property
    def documents_collection(self):
        """Retorna coleção de documentos."""
        return self.database["documents"]

    @property
    def entities_collection(self):
        """Retorna coleção de entidades."""
        return self.database["entities"]

    @property
    def parsing_jobs_collection(self):
        """Retorna coleção de jobs de parsing."""
        return self.database["parsing_jobs"]


_async_client: Optional[AsyncMongoDBClient] = None


async def get_mongodb_client() -> AsyncMongoDBClient:
    """Retorna instância do cliente MongoDB (singleton)."""
    global _async_client
    if _async_client is None:
        _async_client = AsyncMongoDBClient()
        await _async_client.connect()
    return _async_client
