"""Repositório base para operações MongoDB."""

from typing import Any, Dict, Generic, List, Optional, TypeVar

import structlog
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel

from src.config.settings import get_settings

logger = structlog.get_logger(__name__)

T = TypeVar("T", bound=BaseModel)

# Singleton MongoDB client
_mongo_client: AsyncIOMotorClient | None = None


def get_mongo_client() -> AsyncIOMotorClient:
    """Retorna cliente MongoDB singleton."""
    global _mongo_client
    if _mongo_client is None:
        settings = get_settings()
        _mongo_client = AsyncIOMotorClient(settings.mongodb.url)
        logger.info("mongo_client_created", url=settings.mongodb.url)
    return _mongo_client


class BaseRepository(Generic[T]):
    """Repositório base com operações CRUD assíncronas."""

    def __init__(self, collection_name: str, model_class: type[T]):
        """Inicializa repositório.

        Args:
            collection_name: Nome da coleção MongoDB
            model_class: Classe Pydantic para (de)serialização
        """
        settings = get_settings()
        self.client = get_mongo_client()
        self.db = self.client[settings.mongodb.database]
        self.collection = self.db[collection_name]
        self.model_class = model_class
        self.collection_name = collection_name

    async def create(self, item: T) -> str:
        """Cria novo documento.

        Args:
            item: Modelo Pydantic a persistir

        Returns:
            ID do documento criado
        """
        doc = item.model_dump(by_alias=True, exclude_none=True)
        result = await self.collection.insert_one(doc)
        return str(result.inserted_id)

    async def get_by_id(self, doc_id: str) -> Optional[T]:
        """Busca documento por ID.

        Args:
            doc_id: ID do documento

        Returns:
            Modelo Pydantic ou None
        """
        doc = await self.collection.find_one({"_id": doc_id})
        if doc:
            return self.model_class(**doc)
        return None

    async def list_all(
        self, filter_dict: Dict[str, Any] | None = None, limit: int = 100
    ) -> List[T]:
        """Lista documentos com filtro opcional.

        Args:
            filter_dict: Filtro MongoDB
            limit: Número máximo de resultados

        Returns:
            Lista de modelos Pydantic
        """
        query = filter_dict or {}
        cursor = self.collection.find(query).limit(limit)
        docs = await cursor.to_list(length=limit)
        return [self.model_class(**doc) for doc in docs]

    async def update(self, doc_id: str, updates: Dict[str, Any]) -> bool:
        """Atualiza documento.

        Args:
            doc_id: ID do documento
            updates: Campos a atualizar

        Returns:
            True se atualizado, False se não encontrado
        """
        result = await self.collection.update_one({"_id": doc_id}, {"$set": updates})
        return result.modified_count > 0

    async def delete(self, doc_id: str) -> bool:
        """Remove documento.

        Args:
            doc_id: ID do documento

        Returns:
            True se removido, False se não encontrado
        """
        result = await self.collection.delete_one({"_id": doc_id})
        return result.deleted_count > 0

    async def count(self, filter_dict: Dict[str, Any] | None = None) -> int:
        """Conta documentos com filtro.

        Args:
            filter_dict: Filtro MongoDB

        Returns:
            Número de documentos
        """
        query = filter_dict or {}
        return await self.collection.count_documents(query)

    async def close(self):
        """Fecha conexão com MongoDB (no-op para singleton)."""
        # Cliente é singleton, não fecha aqui
        pass
