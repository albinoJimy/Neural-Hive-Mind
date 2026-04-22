"""Repositório MongoDB para documentos de aprendizado"""

from datetime import datetime
from typing import Any, Optional

import structlog
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError
from src.config import get_settings
from src.models import (
    DocumentStatus,
    DocumentType,
    LearningDocument,
)

logger = structlog.get_logger()


class DocumentRepository:
    """Repositório para documentos de aprendizado no MongoDB"""

    def __init__(self):
        """Inicializa o repositório"""
        self.settings = get_settings()
        self._client: Optional[AsyncIOMotorClient] = None
        self._database = None
        self._collection = None

    async def initialize(self) -> None:
        """Inicializa a conexão com MongoDB"""
        try:
            self._client = AsyncIOMotorClient(self.settings.mongodb_uri)
            self._database = self._client[self.settings.mongodb_database]
            self._collection = self._database[self.settings.mongodb_collection]

            # Criar índices
            await self._create_indexes()

            logger.info(
                "MongoDB inicializado",
                database=self.settings.mongodb_database,
                collection=self.settings.mongodb_collection,
            )

        except Exception as e:
            logger.error("Erro ao inicializar MongoDB", error=str(e), exc_info=True)
            raise

    async def _create_indexes(self) -> None:
        """Cria índices necessários"""
        indexes = [
            {"keys": [("created_at", DESCENDING)], "name": "created_at_idx"},
            {"keys": [("type", ASCENDING), ("created_at", DESCENDING)], "name": "type_created_idx"},
            {"keys": [("status", ASCENDING)], "name": "status_idx"},
            {
                "keys": [("period_start", ASCENDING), ("period_end", ASCENDING)],
                "name": "period_idx",
            },
            {"keys": [("metadata.experiment_ids", ASCENDING)], "name": "experiment_ids_idx"},
            {"keys": [("title", "text"), ("summary", "text")], "name": "text_search_idx"},
        ]

        for index_def in indexes:
            try:
                await self._collection.create_index(
                    keys=index_def["keys"],
                    name=index_def["name"],
                )
                logger.debug("Índice criado", name=index_def["name"])
            except Exception as e:
                logger.warning("Erro ao criar índice", index=index_def["name"], error=str(e))

    async def save(self, document: LearningDocument) -> str:
        """Salva um novo documento

        Args:
            document: Documento a salvar

        Returns:
            ID do documento inserido
        """
        try:
            doc_dict = document.model_dump(exclude={"id"}, exclude_none=True)
            doc_dict["created_at"] = doc_dict.get("created_at", datetime.utcnow())
            doc_dict["updated_at"] = datetime.utcnow()

            result = await self._collection.insert_one(doc_dict)
            doc_id = str(result.inserted_id)

            logger.info("Documento salvo", doc_id=doc_id, type=document.type)
            return doc_id

        except DuplicateKeyError:
            logger.error("Documento duplicado", title=document.title)
            raise
        except Exception as e:
            logger.error("Erro ao salvar documento", error=str(e), exc_info=True)
            raise

    async def update(self, doc_id: str, document: LearningDocument) -> bool:
        """Atualiza um documento existente

        Args:
            doc_id: ID do documento
            document: Dados atualizados

        Returns:
            True se atualizado com sucesso
        """
        try:
            doc_dict = document.model_dump(exclude={"id"}, exclude_none=True)
            doc_dict["updated_at"] = datetime.utcnow()

            result = await self._collection.update_one({"_id": doc_id}, {"$set": doc_dict})

            if result.modified_count > 0:
                logger.info("Documento atualizado", doc_id=doc_id)
                return True
            else:
                logger.warning("Documento não encontrado para atualização", doc_id=doc_id)
                return False

        except Exception as e:
            logger.error("Erro ao atualizar documento", doc_id=doc_id, error=str(e))
            raise

    async def get_by_id(self, doc_id: str) -> Optional[LearningDocument]:
        """Busca documento por ID

        Args:
            doc_id: ID do documento

        Returns:
            Documento ou None
        """
        try:
            doc_dict = await self._collection.find_one({"_id": doc_id})
            if doc_dict:
                doc_dict["id"] = str(doc_dict.pop("_id"))
                return LearningDocument(**doc_dict)
            return None

        except Exception as e:
            logger.error("Erro ao buscar documento", doc_id=doc_id, error=str(e))
            return None

    async def list_documents(
        self,
        doc_type: Optional[DocumentType] = None,
        status: Optional[DocumentStatus] = None,
        period_start: Optional[datetime] = None,
        period_end: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "created_at",
        sort_order: int = -1,
    ) -> tuple[list[LearningDocument], int]:
        """Lista documentos com filtros e paginação

        Args:
            doc_type: Filtrar por tipo
            status: Filtrar por status
            period_start: Filtrar por início do período
            period_end: Filtrar por fim do período
            page: Página (1-indexed)
            page_size: Tamanho da página
            sort_by: Campo para ordenação
            sort_order: -1 para DESC, 1 para ASC

        Returns:
            Tupla (documentos, total)
        """
        try:
            # Construir filtro
            filter_dict: dict[str, Any] = {}

            if doc_type:
                filter_dict["type"] = doc_type.value

            if status:
                filter_dict["status"] = status.value

            if period_start or period_end:
                period_filter = {}
                if period_start:
                    period_filter["$gte"] = period_start
                if period_end:
                    period_filter["$lte"] = period_end
                filter_dict["$or"] = [
                    {"period_start": period_filter},
                    {"period_end": period_filter},
                ]

            # Contar total
            total = await self._collection.count_documents(filter_dict)

            # Buscar documentos
            skip = (page - 1) * page_size
            cursor = (
                self._collection.find(filter_dict)
                .sort(sort_by, sort_order)
                .skip(skip)
                .limit(page_size)
            )

            documents = []
            async for doc_dict in cursor:
                doc_dict["id"] = str(doc_dict.pop("_id"))
                documents.append(LearningDocument(**doc_dict))

            logger.info(
                "Documentos listados",
                count=len(documents),
                total=total,
                page=page,
            )
            return documents, total

        except Exception as e:
            logger.error("Erro ao listar documentos", error=str(e))
            return [], 0

    async def update_status(
        self, doc_id: str, status: DocumentStatus, error_message: Optional[str] = None
    ) -> bool:
        """Atualiza status do documento

        Args:
            doc_id: ID do documento
            status: Novo status
            error_message: Mensagem de erro (se aplicável)

        Returns:
            True se atualizado
        """
        try:
            update_dict: dict[str, Any] = {"status": status.value, "updated_at": datetime.utcnow()}

            if status == DocumentStatus.COMPLETED:
                update_dict["generated_at"] = datetime.utcnow()
            elif status == DocumentStatus.FAILED and error_message:
                update_dict["metadata"] = {"error": error_message}

            result = await self._collection.update_one({"_id": doc_id}, {"$set": update_dict})

            return result.modified_count > 0

        except Exception as e:
            logger.error("Erro ao atualizar status", doc_id=doc_id, error=str(e))
            return False

    async def get_by_period(
        self, period_start: datetime, period_end: datetime, doc_type: Optional[DocumentType] = None
    ) -> list[LearningDocument]:
        """Busca documentos por período

        Args:
            period_start: Início do período
            period_end: Fim do período
            doc_type: Tipo de documento (opcional)

        Returns:
            Lista de documentos
        """
        try:
            filter_dict: dict[str, Any] = {
                "$or": [
                    {
                        "period_start": {"$lte": period_end},
                        "period_end": {"$gte": period_start},
                    },
                    {"period_start": {"$gte": period_start, "$lte": period_end}},
                ]
            }

            if doc_type:
                filter_dict["type"] = doc_type.value

            cursor = self._collection.find(filter_dict).sort("created_at", DESCENDING)

            documents = []
            async for doc_dict in cursor:
                doc_dict["id"] = str(doc_dict.pop("_id"))
                documents.append(LearningDocument(**doc_dict))

            return documents

        except Exception as e:
            logger.error("Erro ao buscar por período", error=str(e))
            return []

    async def get_latest_by_type(
        self, doc_type: DocumentType, limit: int = 10
    ) -> list[LearningDocument]:
        """Busca documentos mais recentes por tipo

        Args:
            doc_type: Tipo do documento
            limit: Número máximo de documentos

        Returns:
            Lista de documentos
        """
        try:
            cursor = (
                self._collection.find({"type": doc_type.value})
                .sort("created_at", DESCENDING)
                .limit(limit)
            )

            documents = []
            async for doc_dict in cursor:
                doc_dict["id"] = str(doc_dict.pop("_id"))
                documents.append(LearningDocument(**doc_dict))

            return documents

        except Exception as e:
            logger.error("Erro ao buscar mais recentes", doc_type=doc_type, error=str(e))
            return []

    async def search_by_experiment_ids(self, experiment_ids: list[str]) -> list[LearningDocument]:
        """Busca documentos que contêm certos experimentos

        Args:
            experiment_ids: IDs dos experimentos

        Returns:
            Lista de documentos
        """
        try:
            cursor = self._collection.find(
                {"metadata.experiment_ids": {"$in": experiment_ids}}
            ).sort("created_at", DESCENDING)

            documents = []
            async for doc_dict in cursor:
                doc_dict["id"] = str(doc_dict.pop("_id"))
                documents.append(LearningDocument(**doc_dict))

            return documents

        except Exception as e:
            logger.error("Erro ao buscar por experimentos", error=str(e))
            return []

    async def delete(self, doc_id: str) -> bool:
        """Deleta um documento

        Args:
            doc_id: ID do documento

        Returns:
            True se deletado
        """
        try:
            result = await self._collection.delete_one({"_id": doc_id})
            return result.deleted_count > 0

        except Exception as e:
            logger.error("Erro ao deletar documento", doc_id=doc_id, error=str(e))
            return False

    async def close(self) -> None:
        """Fecha conexão com MongoDB"""
        if self._client:
            self._client.close()
            logger.info("MongoDB connection closed")
