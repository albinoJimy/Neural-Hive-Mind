"""Repositório para persistência de documentos."""

import builtins
from datetime import datetime

from src.db.mongodb import get_mongodb
from src.models import Document
from structlog import get_logger

logger = get_logger(__name__)


class DocumentsRepository:
    """Repositório para operações de CRUD de documentos."""

    def __init__(self):
        self._mongodb = None

    async def _get_db(self):
        """Obtém conexão MongoDB."""
        if self._mongodb is None:
            self._mongodb = await get_mongodb()
        return self._mongodb

    async def save(self, document: Document) -> Document:
        """Salva um documento."""
        db = await self._get_db()

        doc = document.model_dump()
        doc["created_at"] = datetime.utcnow()

        # Verificar se já existe
        existing = await db.documents_collection.find_one({"id": document.id})

        if existing:
            await db.documents_collection.update_one({"id": document.id}, {"$set": doc})
        else:
            await db.documents_collection.insert_one(doc)

        logger.info("document_saved", id=document.id, doc_type=document.doc_type)

        return document

    async def get_by_id(self, document_id: str) -> Document | None:
        """Busca documento por ID."""
        db = await self._get_db()
        doc = await db.documents_collection.find_one({"id": document_id})

        if doc:
            doc.pop("_id", None)
            return Document(**doc)
        return None

    async def list(
        self,
        doc_type: str | None = None,
        limit: int = 50,
        skip: int = 0,
    ) -> tuple[list[Document], int]:
        """Lista documentos com filtros."""
        db = await self._get_db()

        filters = {}
        if doc_type:
            filters["doc_type"] = doc_type

        cursor = (
            db.documents_collection.find(filters).skip(skip).limit(limit).sort("created_at", -1)
        )

        docs = await cursor.to_list(length=limit)
        total = await db.documents_collection.count_documents(filters)

        documents = []
        for doc in docs:
            doc.pop("_id", None)
            documents.append(Document(**doc))

        return documents, total

    async def delete(self, document_id: str) -> bool:
        """Deleta um documento."""
        db = await self._get_db()
        result = await db.documents_collection.delete_one({"id": document_id})

        if result.deleted_count:
            logger.info("document_deleted", id=document_id)
            return True
        return False

    async def get_by_project(self, project_name: str) -> builtins.list[Document]:
        """Busca documentos por projeto."""
        db = await self._get_db()
        cursor = db.documents_collection.find({"metadata.project": project_name})

        docs = await cursor.to_list(length=None)
        documents = []
        for doc in docs:
            doc.pop("_id", None)
            documents.append(Document(**doc))

        return documents

    async def search(self, query: str, limit: int = 20) -> builtins.list[Document]:
        """Busca documentos por texto."""
        db = await self._get_db()

        # Busca simples por título ou conteúdo
        cursor = db.documents_collection.find(
            {
                "$or": [
                    {"title": {"$regex": query, "$options": "i"}},
                    {"content": {"$regex": query, "$options": "i"}},
                ]
            }
        ).limit(limit)

        docs = await cursor.to_list(length=limit)
        documents = []
        for doc in docs:
            doc.pop("_id", None)
            documents.append(Document(**doc))

        return documents
