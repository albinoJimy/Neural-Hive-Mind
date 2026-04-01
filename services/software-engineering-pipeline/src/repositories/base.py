from typing import Generic, TypeVar

from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
from structlog import get_logger

from src.config.settings import settings

T = TypeVar("T", bound=BaseModel)


class BaseRepository(Generic[T]):
    """Repositório base para operações MongoDB."""

    def __init__(
        self,
        client: AsyncIOMotorClient | None = None,
        database: str | None = None,
        collection: str | None = None,
    ):
        self.logger = get_logger()
        self._client = client or AsyncIOMotorClient(settings.mongodb_url)
        self._database_name = database or settings.mongodb_db_name
        self._collection_name = collection
        self._collection = self._client[self._database_name][self._collection_name]

    @property
    def collection(self):
        return self._collection

    async def create(self, document: T) -> str:
        """Insere um documento e retorna seu ID."""
        self.logger.info("creating_document", collection=self._collection_name)

        doc_dict = document.model_dump(exclude_unset=True)
        result = await self._collection.insert_one(doc_dict)

        self.logger.info("document_created", id=str(result.inserted_id))
        return str(result.inserted_id)

    async def find_by_id(self, id: str) -> dict | None:
        """Encontra um documento por ID."""
        doc = await self._collection.find_one({"_id": id})
        return doc if doc else None

    async def find_one(self, filter_dict: dict) -> dict | None:
        """Encontra um único documento correspondendo ao filtro."""
        doc = await self._collection.find_one(filter_dict)
        return doc if doc else None

    async def find_many(
        self,
        filter_dict: dict | None = None,
        skip: int = 0,
        limit: int = 100,
        sort: list[tuple[str, int]] | None = None,
    ) -> list[dict]:
        """Encontra múltiplos documentos correspondendo ao filtro."""
        cursor = self._collection.find(filter_dict or {})

        if skip:
            cursor = cursor.skip(skip)
        if limit:
            cursor = cursor.limit(limit)
        if sort:
            for field, direction in sort:
                cursor = cursor.sort(field, direction)

        docs = await cursor.to_list(length=limit)
        return docs

    async def update(self, id: str, updates: dict) -> bool:
        """Atualiza um documento por ID."""
        result = await self._collection.update_one({"_id": id}, {"$set": updates})
        return result.modified_count > 0

    async def delete(self, id: str) -> bool:
        """Deleta um documento por ID."""
        result = await self._collection.delete_one({"_id": id})
        return result.deleted_count > 0

    async def count(self, filter_dict: dict | None = None) -> int:
        """Conta documentos correspondendo ao filtro."""
        return await self._collection.count_documents(filter_dict or {})

    async def aggregate(self, pipeline: list[dict]) -> list[dict]:
        """Executa um pipeline de agregação."""
        cursor = self._collection.aggregate(pipeline)
        return await cursor.to_list(length=None)

    async def create_index(self, keys: list[tuple[str, int]], **kwargs) -> str:
        """Cria um índice na coleção."""
        return await self._collection.create_index(keys, **kwargs)

    async def close(self) -> None:
        """Fecha a conexão com o banco de dados."""
        self._client.close()
