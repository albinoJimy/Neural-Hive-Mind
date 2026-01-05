"""MongoDB client for Guard Agents"""
from typing import Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase, AsyncIOMotorCollection
import structlog

logger = structlog.get_logger()


class MongoDBClient:
    """Cliente MongoDB assincrono para Guard Agents"""

    def __init__(self, uri: str, database: str):
        self.uri = uri
        self.database_name = database
        self.client: Optional[AsyncIOMotorClient] = None
        self.db: Optional[AsyncIOMotorDatabase] = None
        self.incidents_collection: Optional[AsyncIOMotorCollection] = None
        self.remediation_collection: Optional[AsyncIOMotorCollection] = None
        self.postmortems_collection: Optional[AsyncIOMotorCollection] = None

    async def connect(
        self,
        incidents_coll: str = "security_incidents",
        remediation_coll: str = "remediation_actions",
        postmortems_coll: str = "incident_postmortems"
    ):
        """Conecta ao MongoDB e inicializa colecoes"""
        try:
            self.client = AsyncIOMotorClient(self.uri)
            self.db = self.client[self.database_name]
            self.incidents_collection = self.db[incidents_coll]
            self.remediation_collection = self.db[remediation_coll]
            self.postmortems_collection = self.db[postmortems_coll]

            # Testa conexao
            await self.client.admin.command('ping')
            logger.info("mongodb.connected", database=self.database_name)

            # Cria indices
            await self._create_indexes()
        except Exception as e:
            logger.error("mongodb.connection_failed", error=str(e))
            raise

    async def _create_indexes(self):
        """Cria indices nas colecoes"""
        try:
            # Indices para incidents
            await self.incidents_collection.create_index("incident_id", unique=True)
            await self.incidents_collection.create_index("timestamp")
            await self.incidents_collection.create_index("severity")
            await self.incidents_collection.create_index("status")

            # Indices para remediation
            await self.remediation_collection.create_index("action_id", unique=True)
            await self.remediation_collection.create_index("incident_id")
            await self.remediation_collection.create_index("created_at")

            # Indices para postmortems
            await self.postmortems_collection.create_index("incident_id", unique=True)
            await self.postmortems_collection.create_index("documented_at")
            await self.postmortems_collection.create_index("severity")
            await self.postmortems_collection.create_index([("threat_type", 1), ("severity", 1)])

            logger.info("mongodb.indexes_created")
        except Exception as e:
            logger.warning("mongodb.index_creation_failed", error=str(e))

    async def close(self):
        """Fecha conexao com MongoDB"""
        if self.client:
            self.client.close()
            logger.info("mongodb.connection_closed")

    def is_healthy(self) -> bool:
        """Verifica se cliente esta saudavel"""
        return self.client is not None and self.db is not None

    async def insert_postmortem(self, postmortem: Dict[str, Any]) -> bool:
        """
        Insere post-mortem no MongoDB

        Args:
            postmortem: Documento de post-mortem a inserir

        Returns:
            True se sucesso, False se falha
        """
        if not self.postmortems_collection:
            logger.warning("mongodb.postmortems_collection_not_initialized")
            return False

        try:
            await self.postmortems_collection.insert_one(postmortem)
            logger.info(
                "mongodb.postmortem_inserted",
                incident_id=postmortem.get("incident_id")
            )
            return True
        except Exception as e:
            logger.error(
                "mongodb.insert_postmortem_failed",
                incident_id=postmortem.get("incident_id"),
                error=str(e)
            )
            return False

    async def get_postmortem(self, incident_id: str) -> Optional[Dict[str, Any]]:
        """
        Busca post-mortem por incident_id

        Args:
            incident_id: ID do incidente

        Returns:
            Documento de post-mortem ou None se nao encontrado
        """
        if not self.postmortems_collection:
            return None

        try:
            return await self.postmortems_collection.find_one({"incident_id": incident_id})
        except Exception as e:
            logger.error(
                "mongodb.get_postmortem_failed",
                incident_id=incident_id,
                error=str(e)
            )
            return None
