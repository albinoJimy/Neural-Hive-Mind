"""Cliente MongoDB para Data Migration Service."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorClient
from structlog import get_logger

from src.config.settings import get_settings

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
        self._client: Optional[AsyncIOMotorClient] = None
        self._database_name = settings.mongodb_database
        self._initialized = True

    async def connect(self) -> None:
        """Conecta ao MongoDB."""
        if self._client is not None:
            return

        settings = get_settings()
        self._client = AsyncIOMotorClient(settings.mongodb_url)
        logger.info(
            "mongodb_connected",
            database=self._database_name,
        )

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

    @classmethod
    def _reset_for_tests(cls) -> None:
        """Reseta singleton para testes."""
        cls._instance = None

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
    def migration_jobs_collection(self):
        """Retorna coleção de migration_jobs."""
        return self.database["migration_jobs"]

    @property
    def schema_mappings_collection(self):
        """Retorna coleção de schema_mappings."""
        return self.database["schema_mappings"]

    async def insert_migration_job(self, job_data: Dict[str, Any]) -> str:
        """
        Insere um novo migration job.

        Args:
            job_data: Dicionário com dados do job

        Returns:
            ID do job inserido
        """
        collection = self.migration_jobs_collection
        result = await collection.insert_one(job_data)
        return str(result.inserted_id)

    async def find_migration_job_by_id(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Busca migration job por ID.

        Args:
            job_id: ID do job

        Returns:
            Dicionário com dados do job ou None
        """
        collection = self.migration_jobs_collection
        return await collection.find_one({"job_id": job_id})

    async def update_migration_job_status(
        self,
        job_id: str,
        status: str,
        error_message: Optional[str] = None,
        progress_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Atualiza status de um migration job.

        Args:
            job_id: ID do job
            status: Novo status
            error_message: Mensagem de erro (opcional)
            progress_data: Dados de progresso (opcional)
        """
        collection = self.migration_jobs_collection
        update_data: Dict[str, Any] = {
            "$set": {
                "status": status,
                "updated_at": datetime.now(timezone.utc),
            }
        }

        if error_message:
            update_data["$set"]["error_message"] = error_message

        if progress_data:
            update_data["$set"].update(progress_data)

        await collection.update_one({"job_id": job_id}, update_data)

    async def list_migration_jobs_by_status(
        self, status: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Lista migration jobs por status.

        Args:
            status: Status para filtrar
            limit: Limite de resultados

        Returns:
            Lista de jobs
        """
        collection = self.migration_jobs_collection
        cursor = collection.find({"status": status}).sort("created_at", -1).limit(limit)
        return await cursor.to_list(length=limit)

    async def count_migration_jobs_by_status(self, status: str) -> int:
        """
        Conta migration jobs por status.

        Args:
            status: Status para contar

        Returns:
            Número de jobs
        """
        collection = self.migration_jobs_collection
        return await collection.count_documents({"status": status})

    async def insert_schema_mapping(self, mapping_data: Dict[str, Any]) -> str:
        """
        Insere um novo schema mapping.

        Args:
            mapping_data: Dicionário com dados do mapping

        Returns:
            ID do mapping inserido
        """
        collection = self.schema_mappings_collection
        result = await collection.insert_one(mapping_data)
        return str(result.inserted_id)

    async def find_schema_mapping_by_id(self, mapping_id: str) -> Optional[Dict[str, Any]]:
        """
        Busca schema mapping por ID.

        Args:
            mapping_id: ID do mapping

        Returns:
            Dicionário com dados do mapping ou None
        """
        collection = self.schema_mappings_collection
        return await collection.find_one({"_id": mapping_id})

    async def find_schema_mappings_by_connection(
        self, connection_id: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Busca schema mappings por ID de conexão.

        Args:
            connection_id: ID da conexão legada
            limit: Limite de resultados

        Returns:
            Lista de mappings
        """
        collection = self.schema_mappings_collection
        cursor = collection.find({"legacy_connection_id": connection_id}).limit(limit)
        return await cursor.to_list(length=limit)


_mongodb_client: Optional[MongoDBClient] = None


async def get_mongodb_client() -> MongoDBClient:
    """Retorna instância do cliente MongoDB (singleton)."""
    global _mongodb_client
    if _mongodb_client is None:
        _mongodb_client = MongoDBClient()
        await _mongodb_client.connect()
    return _mongodb_client
