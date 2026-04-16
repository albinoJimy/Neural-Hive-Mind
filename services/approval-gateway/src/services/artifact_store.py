"""Artifact Store para Approval Gateway.

Armazena artefatos aprovados (documentos, código, etc.)
com metadados e versionamento.
"""

import asyncio
import hashlib
import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, BinaryIO

import structlog
from bson import Binary
from pymongo import MongoClient
from gridfs import GridFS

from src.config.settings import get_settings
from src.models.approval import ApprovalDecision

logger = structlog.get_logger(__name__)


class ArtifactStore:
    """Armazenamento de artefatos aprovados."""

    def __init__(
        self,
        mongo_client: Optional[MongoClient] = None,
        db_name: str = "neural_hive"
    ):
        """Inicializa o artifact store."""
        settings = get_settings()
        self._mongo_client = mongo_client or MongoClient(settings.mongodb_url)
        self._db = self._mongo_client[db_name]
        self._gridfs = GridFS(self._db, collection="artifacts")
        self._collection = self._db["artifacts_metadata"]
        self._s3_bucket = getattr(settings, "s3_artifacts_bucket", None)
        self.logger = logger

        # Índices
        self._ensure_indexes()

    def _ensure_indexes(self):
        """Cria índices no MongoDB."""
        self._collection.create_index([("approval_id", 1)], background=True)
        self._collection.create_index([("artifact_type", 1)], background=True)
        self._collection.create_index([("created_at", -1)], background=True)
        self._collection.create_index([("version", -1)], background=True)

    async def store_artifact(
        self,
        approval_id: str,
        artifact_type: str,
        content: str | bytes,
        filename: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        content_type: str = "text/plain",
        version: str = "1.0.0"
    ) -> str:
        """
        Armazena um artefato aprovado.

        Args:
            approval_id: ID da decisão de aprovação
            artifact_type: Tipo do artefato (code, document, diagram, etc.)
            content: Conteúdo do artefato
            filename: Nome do arquivo (opcional)
            metadata: Metadados adicionais
            content_type: MIME type do conteúdo
            version: Versão do artefato

        Returns:
            artifact_id: ID do artefato armazenado
        """
        artifact_id = str(uuid.uuid4())

        # Calcular checksum
        if isinstance(content, str):
            checksum = hashlib.sha256(content.encode()).hexdigest()
            content_bytes = content.encode()
        else:
            checksum = hashlib.sha256(content).hexdigest()
            content_bytes = content

        # Preparar metadados
        artifact_metadata = {
            "artifact_id": artifact_id,
            "approval_id": approval_id,
            "artifact_type": artifact_type,
            "filename": filename or f"{artifact_type}_{artifact_id[:8]}",
            "content_type": content_type,
            "checksum": checksum,
            "size_bytes": len(content_bytes),
            "version": version,
            "metadata": metadata or {},
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }

        # Armazenar no GridFS para arquivos grandes
        try:
            gridfs_file = self._gridfs.put(
                content_bytes,
                filename=artifact_metadata["filename"],
                metadata=artifact_metadata
            )

            # Atualizar metadados com GridFS ID
            artifact_metadata["gridfs_id"] = gridfs_file
            artifact_metadata["storage"] = "gridfs"

            logger.info(
                "artifact_stored_gridfs",
                artifact_id=artifact_id,
                filename=artifact_metadata["filename"],
                size_bytes=artifact_metadata["size_bytes"]
            )

        except Exception as e:
            logger.error("gridfs_storage_failed", error=str(e))
            # Fallback: armazenar como BSON Binary
            artifact_metadata["storage"] = "bson_binary"
            artifact_metadata["content_bson"] = Binary(content_bytes)
            self._collection.insert_one(artifact_metadata)
            logger.info("artifact_stored_bson", artifact_id=artifact_id)
            return artifact_id

        # Inserir metadados na coleção
        self._collection.insert_one(artifact_metadata)

        logger.info(
            "artifact_created",
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            approval_id=approval_id
        )

        return artifact_id

    async def get_artifact(self, artifact_id: str) -> Optional[Dict[str, Any]]:
        """
        Recupera um artefato pelo ID.

        Args:
            artifact_id: ID do artefato

        Returns:
            Dados do artefato ou None se não encontrado
        """
        metadata = self._collection.find_one({"artifact_id": artifact_id})

        if not metadata:
            logger.warning("artifact_not_found", artifact_id=artifact_id)
            return None

        # Recuperar conteúdo do GridFS se aplicável
        if metadata.get("storage") == "gridfs" and "gridfs_id" in metadata:
            try:
                gridfs_file = self._gridfs.get(metadata["gridfs_id"])
                if gridfs_file:
                    content = gridfs_file.read()
                    metadata["content"] = content
                    return metadata
            except Exception as e:
                logger.error("gridfs_retrieval_failed", error=str(e))
        elif metadata.get("storage") == "bson_binary" and "content_bson" in metadata:
            metadata["content"] = metadata["content_bson"].decode()
            del metadata["content_bson"]

        return metadata

    async def get_artifacts_by_approval(
        self,
        approval_id: str,
        artifact_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Lista artefatos por aprovação.

        Args:
            approval_id: ID da aprovação
            artifact_type: Filtrar por tipo (opcional)

        Returns:
            Lista de metadados dos artefatos
        """
        query = {"approval_id": approval_id}
        if artifact_type:
            query["artifact_type"] = artifact_type

        cursor = self._collection.find(query).sort("created_at", -1)

        artifacts = []
        async for artifact in cursor:
            # Incluir apenas metadados (não conteúdo)
            artifacts.append({
                "artifact_id": artifact["artifact_id"],
                "artifact_type": artifact["artifact_type"],
                "filename": artifact.get("filename"),
                "content_type": artifact.get("content_type"),
                "size_bytes": artifact["size_bytes"],
                "version": artifact["version"],
                "created_at": artifact["created_at"],
                "metadata": artifact.get("metadata", {})
            })

        return artifacts

    async def get_artifact_content(
        self,
        artifact_id: str
    ) -> Optional[str | bytes]:
        """
        Recupera o conteúdo de um artefato.

        Args:
            artifact_id: ID do artefato

        Returns:
            Conteúdo do artefato como string ou bytes
        """
        artifact_data = await self.get_artifact(artifact_id)

        if not artifact_data:
            return None

        # Retornar conteúdo
        if "content" in artifact_data:
            return artifact_data["content"]

        # Buscar do GridFS
        if artifact_data.get("storage") == "gridfs" and "gridfs_id" in artifact_data:
            try:
                gridfs_file = self._gridfs.get(artifact_data["gridfs_id"])
                if gridfs_file:
                    content = gridfs_file.read()
                    # Tentar decodificar como string
                    try:
                        return content.decode()
                    except UnicodeDecodeError:
                        return content
            except Exception as e:
                logger.error("artifact_content_retrieval_failed", error=str(e))

        return None

    async def update_artifact_metadata(
        self,
        artifact_id: str,
        metadata: Dict[str, Any]
    ) -> bool:
        """
        Atualiza metadados de um artefato.

        Args:
            artifact_id: ID do artefato
            metadata: Novos metadados

        Returns:
            True se atualizado com sucesso
        """
        result = self._collection.update_one(
            {"artifact_id": artifact_id},
            {
                "$set": {
                    "metadata": metadata,
                    "updated_at": datetime.utcnow()
                }
            }
        )

        if result.modified_count > 0:
            logger.info("artifact_metadata_updated", artifact_id=artifact_id)
            return True

        return False

    async def delete_artifact(self, artifact_id: str) -> bool:
        """
        Remove um artefato do armazenamento.

        Args:
            artifact_id: ID do artefato

        Returns:
            True se removido com sucesso
        """
        metadata = await self.get_artifact(artifact_id)

        if not metadata:
            return False

        # Remover do GridFS se aplicável
        if metadata.get("storage") == "gridfs" and "gridfs_id" in metadata:
            try:
                self._gridfs.delete(metadata["gridfs_id"])
            except Exception as e:
                logger.error("gridfs_deletion_failed", error=str(e))

        # Remover metadados
        result = self._collection.delete_one({"artifact_id": artifact_id})

        if result.deleted_count > 0:
            logger.info("artifact_deleted", artifact_id=artifact_id)
            return True

        return False

    async def list_artifacts(
        self,
        artifact_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Lista artefatos com paginação.

        Args:
            artifact_type: Filtrar por tipo
            limit: Máximo de resultados
            offset: Pular primeiros N resultados

        Returns:
            Lista de metadados dos artefatos
        """
        query = {}
        if artifact_type:
            query["artifact_type"] = artifact_type

        cursor = self._collection.find(query).sort("created_at", -1).skip(offset).limit(limit)

        artifacts = []
        for artifact in await cursor.to_list(length=limit):
            artifacts.append({
                "artifact_id": artifact["artifact_id"],
                "artifact_type": artifact["artifact_type"],
                "filename": artifact.get("filename"),
                "size_bytes": artifact["size_bytes"],
                "version": artifact["version"],
                "created_at": artifact["created_at"],
            })

        return artifacts

    async def get_storage_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas de armazenamento."""
        total_count = await self._collection.count_documents({})
        total_size = await self._collection.aggregate([
            {"$group": None, "$sum": {"size_bytes": 1}}
        ]).to_list(None)

        # Count por tipo
        type_counts = await self._collection.aggregate([
            {"$group": {"_id": "$artifact_type"}, "count": {"count": 1}}
        ]).to_list(None)

        # GridFS stats
        gridfs_count = self._gridfs.list(limit=1)["length"]

        return {
            "total_artifacts": total_count,
            "total_size_bytes": total_size[0].get("size_bytes", 0) if total_size else 0,
            "artifacts_by_type": {
                item["_id"]: item["count"]
                for item in type_counts
            },
            "gridfs_files": gridfs_count
        }

    async def cleanup_old_artifacts(
        self,
        days_to_keep: int = 90,
        artifact_type: Optional[str] = None
    ) -> int:
        """
        Remove artefatos antigos.

        Args:
            days_to_keep: Dias para reter artefatos
            artifact_type: Tipo específico para limpar

        Returns:
            Número de artefatos removidos
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)

        query = {"created_at": {"$lt": cutoff_date}}
        if artifact_type:
            query["artifact_type"] = artifact_type

        result = await self._collection.delete_many(query)

        if result.deleted_count > 0:
            logger.info(
                "old_artifacts_cleaned",
                count=result.deleted_count,
                days_old=days_to_keep,
                artifact_type=artifact_type
            )

        # Limpar arquivos órfãos no GridFS
        # (GridFS não tem garbage collection automática)
        # TODO: Implementar limpeza de chunks órfãos

        return result.deleted_count


# Factory function
async def get_artifact_store() -> ArtifactStore:
    """Retorna instância do ArtifactStore."""
    return ArtifactStore()
