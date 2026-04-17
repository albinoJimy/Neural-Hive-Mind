"""Repositório para entidades extraídas."""

from datetime import datetime, timezone
from typing import List, Optional

from src.db.mongodb import AsyncMongoDBClient
from src.models.entities import ExtractedEntity


class EntityRepository:
    """Repositório para operações de CRUD de entidades."""

    def __init__(self, mongodb_client: AsyncMongoDBClient):
        """Inicializa repositório.

        Args:
            mongodb_client: Cliente MongoDB assíncrono
        """
        self.mongodb_client = mongodb_client
        self._collection = None

    @property
    def collection(self):
        """Retorna coleção de entidades (lazy initialization)."""
        if self._collection is None:
            self._collection = self.mongodb_client.db.get("entities")
        return self._collection

    async def create_many(self, entities: List[ExtractedEntity], document_id: str) -> List[str]:
        """Cria múltiplas entidades.

        Args:
            entities: Lista de entidades a criar
            document_id: ID do documento origen

        Returns:
            Lista de IDs das entidades criadas
        """
        if not entities:
            return []

        documents = []
        for entity in entities:
            doc = {
                **entity.model_dump(),
                "document_id": document_id,
                "extracted_at": datetime.now(timezone.utc).isoformat(),
                "extracted_by": "entity_extractor",
            }
            documents.append(doc)

        result = await self.collection.insert_many(documents)
        return [str(id) for id in result.inserted_ids]

    async def list_by_document(
        self, document_id: str, entity_type: Optional[str] = None
    ) -> List[dict]:
        """Lista entidades de um documento.

        Args:
            document_id: ID do documento
            entity_type: Filtro opcional por tipo

        Returns:
            Lista de entidades
        """
        query = {"document_id": document_id}
        if entity_type:
            query["type"] = entity_type

        cursor = self.collection.find(query)
        entities = await cursor.to_list(length=None)
        return entities

    async def delete_by_document(self, document_id: str) -> int:
        """Deleta todas as entidades de um documento.

        Args:
            document_id: ID do documento

        Returns:
            Número de entidades deletadas
        """
        result = await self.collection.delete_many({"document_id": document_id})
        return result.deleted_count
