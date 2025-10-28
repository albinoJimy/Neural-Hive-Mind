"""MongoDB client for Guard Agents"""
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase, AsyncIOMotorCollection
import structlog

logger = structlog.get_logger()


class MongoDBClient:
    """Cliente MongoDB assíncrono para Guard Agents"""

    def __init__(self, uri: str, database: str):
        self.uri = uri
        self.database_name = database
        self.client: Optional[AsyncIOMotorClient] = None
        self.db: Optional[AsyncIOMotorDatabase] = None
        self.incidents_collection: Optional[AsyncIOMotorCollection] = None
        self.remediation_collection: Optional[AsyncIOMotorCollection] = None

    async def connect(self, incidents_coll: str = "security_incidents", remediation_coll: str = "remediation_actions"):
        """Conecta ao MongoDB e inicializa coleções"""
        try:
            self.client = AsyncIOMotorClient(self.uri)
            self.db = self.client[self.database_name]
            self.incidents_collection = self.db[incidents_coll]
            self.remediation_collection = self.db[remediation_coll]

            # Testa conexão
            await self.client.admin.command('ping')
            logger.info("mongodb.connected", database=self.database_name)

            # Cria índices
            await self._create_indexes()
        except Exception as e:
            logger.error("mongodb.connection_failed", error=str(e))
            raise

    async def _create_indexes(self):
        """Cria índices nas coleções"""
        try:
            # Índices para incidents
            await self.incidents_collection.create_index("incident_id", unique=True)
            await self.incidents_collection.create_index("timestamp")
            await self.incidents_collection.create_index("severity")
            await self.incidents_collection.create_index("status")

            # Índices para remediation
            await self.remediation_collection.create_index("action_id", unique=True)
            await self.remediation_collection.create_index("incident_id")
            await self.remediation_collection.create_index("created_at")

            logger.info("mongodb.indexes_created")
        except Exception as e:
            logger.warning("mongodb.index_creation_failed", error=str(e))

    async def close(self):
        """Fecha conexão com MongoDB"""
        if self.client:
            self.client.close()
            logger.info("mongodb.connection_closed")

    def is_healthy(self) -> bool:
        """Verifica se cliente está saudável"""
        return self.client is not None and self.db is not None
