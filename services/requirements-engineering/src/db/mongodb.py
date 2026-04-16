"""Cliente MongoDB para Requirements Engineering."""

from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient
from src.config.settings import get_settings
from structlog import get_logger

logger = get_logger(__name__)


class MongoDBClient:
    """Cliente MongoDB assíncrono."""

    _instance: Optional["MongoDBClient"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        settings = get_settings()
        self._client: AsyncIOMotorClient | None = None
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

    @property
    def db(self):
        """Retorna o database."""
        if self._client is None:
            raise RuntimeError("MongoDB client not connected. Call connect() first.")
        return self._client[self._database_name]

    @property
    def requirements_collection(self):
        """Retorna coleção de requisitos."""
        return self.db["requirements"]

    @property
    def user_stories_collection(self):
        """Retorna coleção de user stories."""
        return self.db["user_stories"]

    @property
    def requirements_sets_collection(self):
        """Retorna coleção de conjuntos de requisitos."""
        return self.db["requirements_sets"]


async def get_mongodb() -> MongoDBClient:
    """Retorna instância do cliente MongoDB."""
    client = MongoDBClient()
    await client.connect()
    return client
