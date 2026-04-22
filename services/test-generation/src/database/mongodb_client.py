"""Cliente MongoDB para Test Generation.

Autor: Neural Hive Mind
Criado: 2026-04-19 (FEAT-G-002)

Cliente async MongoDB usando motor para persistência
de test suits, test cases e resultados de geração.
"""

from datetime import datetime
from typing import Any, Optional

import structlog
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from src.config.settings import get_settings

logger = structlog.get_logger(__name__)


class MongoDBClient:
    """Cliente MongoDB assíncrono."""

    def __init__(
        self,
        mongodb_url: Optional[str] = None,
        database_name: Optional[str] = None,
    ):
        """Inicializa o cliente MongoDB.

        Args:
            mongodb_url: URL de conexão MongoDB
            database_name: Nome do database
        """
        settings = get_settings()

        self._mongodb_url = mongodb_url or settings.mongodb_url
        self._database_name = database_name or settings.mongodb_database

        self._client: Optional[AsyncIOMotorClient] = None
        self._database: Optional[AsyncIOMotorDatabase] = None
        self._logger = logger

    async def connect(self) -> None:
        """Conecta ao MongoDB."""
        self._client = AsyncIOMotorClient(self._mongodb_url)
        self._database = self._client[self._database_name]

        # Ping para verificar conexão
        await self._client.admin.command("ping")

        self._logger.info(
            "mongodb_connected",
            database=self._database_name,
            url=self._mongodb_url,
        )

    async def disconnect(self) -> None:
        """Desconecta do MongoDB."""
        if self._client:
            self._client.close()
            self._logger.info("mongodb_disconnected")

    async def ping(self) -> bool:
        """Verifica se a conexão está ativa.

        Returns:
            True se conectado, False caso contrário
        """
        if not self._client:
            return False

        try:
            await self._client.admin.command("ping")
            return True
        except Exception:
            return False

    @property
    def database(self) -> AsyncIOMotorDatabase:
        """Retorna o database MongoDB.

        Returns:
            Instância do database

        Raises:
            RuntimeError: Se não conectado
        """
        if not self._database:
            raise RuntimeError("MongoDB not connected. Call connect() first.")
        return self._database

    # Collections helpers

    def test_suites(self) -> Any:
        """Retorna coleção de test suites.

        Returns:
            Collection de test suites
        """
        return self._database.test_suites

    def test_cases(self) -> Any:
        """Retorna coleção de test cases.

        Returns:
            Collection de test cases
        """
        return self._database.test_cases

    def generation_results(self) -> Any:
        """Retorna coleção de resultados de geração.

        Returns:
            Collection de resultados
        """
        return self._database.generation_results

    # CRUD Operations

    async def insert_test_suite(self, test_suite_data: dict[str, Any]) -> str:
        """Insere uma test suite.

        Args:
            test_suite_data: Dados da test suite

        Returns:
            ID do documento inserido
        """
        test_suite_data["created_at"] = datetime.utcnow()
        test_suite_data["updated_at"] = datetime.utcnow()

        result = await self.test_suites().insert_one(test_suite_data)
        return str(result.inserted_id)

    async def get_test_suite(self, suite_id: str) -> Optional[dict[str, Any]]:
        """Busca uma test suite por ID.

        Args:
            suite_id: ID da test suite

        Returns:
            Dados da test suite ou None
        """
        return await self.test_suites().find_one({"id": suite_id})

    async def list_test_suites(
        self,
        plan_id: Optional[str] = None,
        limit: int = 100,
        skip: int = 0,
    ) -> list[dict[str, Any]]:
        """Lista test suites com filtros.

        Args:
            plan_id: Filtrar por plan ID
            limit: Limite de resultados
            skip: Quantos resultados pular

        Returns:
            Lista de test suites
        """
        query = {}
        if plan_id:
            query["plan_id"] = plan_id

        cursor = self.test_suites().find(query).skip(skip).limit(limit)
        return await cursor.to_list(length=limit)

    async def insert_test_cases(self, test_cases: list[dict[str, Any]]) -> list[str]:
        """Insere múltiplos test cases.

        Args:
            test_cases: Lista de test cases

        Returns:
            Lista de IDs inseridos
        """
        for tc in test_cases:
            tc["created_at"] = datetime.utcnow()
            tc["updated_at"] = datetime.utcnow()

        result = await self.test_cases().insert_many(test_cases)
        return [str(id) for id in result.inserted_ids]

    async def get_test_cases_for_suite(self, suite_id: str) -> list[dict[str, Any]]:
        """Busca test cases de uma suite.

        Args:
            suite_id: ID da test suite

        Returns:
            Lista de test cases
        """
        cursor = self.test_cases().find({"test_suite_id": suite_id})
        return await cursor.to_list(length=None)

    async def insert_generation_result(self, result_data: dict[str, Any]) -> str:
        """Insere resultado de geração.

        Args:
            result_data: Dados do resultado

        Returns:
            ID do documento inserido
        """
        result_data["created_at"] = datetime.utcnow()

        result = await self.generation_results().insert_one(result_data)
        return str(result.inserted_id)

    async def get_generation_result(self, request_id: str) -> Optional[dict[str, Any]]:
        """Busca resultado de geração por request ID.

        Args:
            request_id: ID do request

        Returns:
            Dados do resultado ou None
        """
        return await self.generation_results().find_one({"request_id": request_id})

    async def update_test_suite(self, suite_id: str, updates: dict[str, Any]) -> bool:
        """Atualiza uma test suite.

        Args:
            suite_id: ID da test suite
            updates: Campos para atualizar

        Returns:
            True se atualizou, False caso contrário
        """
        updates["updated_at"] = datetime.utcnow()

        result = await self.test_suites().update_one({"id": suite_id}, {"$set": updates})
        return result.modified_count > 0

    async def delete_test_suite(self, suite_id: str) -> bool:
        """Deleta uma test suite e seus test cases.

        Args:
            suite_id: ID da test suite

        Returns:
            True se deletou, False caso contrário
        """
        # Deletar test cases associados
        await self.test_cases().delete_many({"test_suite_id": suite_id})

        # Deletar suite
        result = await self.test_suites().delete_one({"id": suite_id})
        return result.deleted_count > 0

    async def health_check(self) -> dict[str, Any]:
        """Retorna status de saúde do MongoDB.

        Returns:
            Dicionário com status de conexão
        """
        is_connected = await self.ping()

        stats = {}
        if is_connected:
            try:
                stats = {
                    "test_suites_count": await self.test_suites().count_documents({}),
                    "test_cases_count": await self.test_cases().count_documents({}),
                    "generation_results_count": await self.generation_results().count_documents({}),
                }
            except Exception:
                pass

        return {
            "mongodb_connected": is_connected,
            "database": self._database_name,
            **stats,
        }


# Singleton instance
_mongodb_client: Optional[MongoDBClient] = None


async def get_mongodb_client() -> MongoDBClient:
    """Retorna instância singleton do cliente MongoDB.

    Returns:
        Instância do MongoDBClient

    Raises:
        RuntimeError: Se não conectado
    """
    global _mongodb_client

    if _mongodb_client is None:
        _mongodb_client = MongoDBClient()
        await _mongodb_client.connect()

    return _mongodb_client
