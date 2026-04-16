"""Repositório para persistência de documentos."""

import uuid
from datetime import datetime
from typing import List, Optional

from src.db.mongodb import get_mongodb_client
from src.models.document import (
    Document,
    DocumentCreate,
    DocumentStatus,
    DocumentUpdate,
)
from structlog import get_logger

logger = get_logger(__name__)


class DocumentRepository:
    """Repositório para operações de CRUD de documentos."""

    def __init__(self):
        """Inicializa o repositório."""
        self._mongodb = None

    async def _get_db(self):
        """Obtém conexão MongoDB."""
        if self._mongodb is None:
            self._mongodb = await get_mongodb_client()
        return self._mongodb

    async def create(self, document_data: DocumentCreate) -> Document:
        """Cria um novo documento.

        Args:
            document_data: Dados para criação do documento.

        Returns:
            Documento criado com ID gerado.
        """
        db = await self._get_db()

        doc_id = f"DOC-{uuid.uuid4().hex[:8].upper()}"

        doc = {
            "id": doc_id,
            "filename": document_data.filename,
            "format": document_data.format,
            "status": DocumentStatus.UPLOADED,
            "file_size_bytes": document_data.file_size_bytes,
            "s3_key": document_data.s3_key,
            "uploaded_by": document_data.uploaded_by,
            "title": document_data.title,
            "description": document_data.description,
            "project_id": document_data.project_id,
            "tags": document_data.tags,
            "metadata": document_data.metadata,
            "parsed_text": None,
            "entity_count": 0,
            "extracted_entity_types": [],
            "parsing_error": None,
            "created_at": datetime.utcnow(),
            "updated_at": None,
            "parsed_at": None,
            "extracted_at": None,
            "version": 1,
        }

        await db.documents_collection.insert_one(doc)

        logger.info(
            "document_created",
            id=doc_id,
            filename=document_data.filename,
            format=document_data.format,
        )

        return Document(**doc)

    async def get_by_id(self, document_id: str) -> Optional[Document]:
        """Busca documento por ID.

        Args:
            document_id: ID do documento.

        Returns:
            Documento encontrado ou None.
        """
        db = await self._get_db()
        doc = await db.documents_collection.find_one({"id": document_id})

        if doc:
            doc.pop("_id", None)
            return Document(**doc)
        return None

    async def list(
        self,
        status_filter: Optional[DocumentStatus] = None,
        format_filter: Optional[str] = None,
        project_id: Optional[str] = None,
        uploaded_by: Optional[str] = None,
        tags: Optional[list[str]] = None,
        limit: int = 50,
        skip: int = 0,
    ) -> tuple[list[Document], int]:
        """Lista documentos com filtros.

        Args:
            status_filter: Filtra por status do documento.
            format_filter: Filtra por formato do documento.
            project_id: Filtra por ID do projeto.
            uploaded_by: Filtra por usuário que fez upload.
            tags: Filtra por tags (qualquer uma das tags).
            limit: Limite de resultados.
            skip: Quantidade de resultados a pular.

        Returns:
            Tupla com lista de documentos e total de registros.
        """
        db = await self._get_db()

        filters = {}
        if status_filter:
            filters["status"] = status_filter.value
        if format_filter:
            filters["format"] = format_filter
        if project_id:
            filters["project_id"] = project_id
        if uploaded_by:
            filters["uploaded_by"] = uploaded_by
        if tags:
            filters["tags"] = {"$in": tags}

        cursor = (
            db.documents_collection.find(filters)
            .skip(skip)
            .limit(limit)
            .sort("created_at", -1)
        )

        docs = await cursor.to_list(length=limit)
        total = await db.documents_collection.count_documents(filters)

        documents = []
        for doc in docs:
            doc.pop("_id", None)
            documents.append(Document(**doc))

        return documents, total

    async def update(
        self, document_id: str, update_data: DocumentUpdate
    ) -> Optional[Document]:
        """Atualiza um documento.

        Args:
            document_id: ID do documento.
            update_data: Dados para atualização.

        Returns:
            Documento atualizado ou None se não encontrado.
        """
        db = await self._get_db()

        # Construir update dict apenas com campos não-None
        update_dict = {
            k: v for k, v in update_data.model_dump(exclude_unset=True).items() if v is not None
        }

        if not update_dict:
            return await self.get_by_id(document_id)

        update_dict["updated_at"] = datetime.utcnow()

        result = await db.documents_collection.update_one(
            {"id": document_id}, {"$set": update_dict}
        )

        if result.modified_count:
            logger.info("document_updated", id=document_id)
            return await self.get_by_id(document_id)

        return None

    async def delete(self, document_id: str) -> bool:
        """Deleta um documento.

        Args:
            document_id: ID do documento.

        Returns:
            True se deletado, False caso contrário.
        """
        db = await self._get_db()
        result = await db.documents_collection.delete_one({"id": document_id})

        if result.deleted_count:
            logger.info("document_deleted", id=document_id)
            return True
        return False

    async def update_status(
        self, document_id: str, status: DocumentStatus, error: Optional[str] = None
    ) -> Optional[Document]:
        """Atualiza status de processamento do documento.

        Args:
            document_id: ID do documento.
            status: Novo status.
            error: Mensagem de erro (se aplicável).

        Returns:
            Documento atualizado ou None.
        """
        update_data = DocumentUpdate(status=status)
        if error:
            update_data.parsing_error = error

        return await self.update(document_id, update_data)

    async def update_parsed_content(
        self,
        document_id: str,
        parsed_text: str,
    ) -> Optional[Document]:
        """Atualiza documento com conteúdo parseado.

        Args:
            document_id: ID do documento.
            parsed_text: Texto extraído do documento.

        Returns:
            Documento atualizado ou None.
        """
        update_data = DocumentUpdate(
            status=DocumentStatus.PARSED,
            parsed_text=parsed_text,
            parsed_at=datetime.utcnow(),
        )
        return await self.update(document_id, update_data)

    async def update_extraction_results(
        self,
        document_id: str,
        entity_count: int,
        extracted_entity_types: List[str],
    ) -> Optional[Document]:
        """Atualiza documento com resultados de extração.

        Args:
            document_id: ID do documento.
            entity_count: Número de entidades extraídas.
            extracted_entity_types: Tipos de entidades extraídas.

        Returns:
            Documento atualizado ou None.
        """
        update_data = DocumentUpdate(
            status=DocumentStatus.EXTRACTED,
            entity_count=entity_count,
            extracted_entity_types=extracted_entity_types,
            extracted_at=datetime.utcnow(),
        )
        return await self.update(document_id, update_data)
