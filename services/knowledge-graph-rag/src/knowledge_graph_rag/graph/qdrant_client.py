"""Cliente Qdrant para busca vetorial."""

from typing import Any, Dict, List, Optional

import structlog
from qdrant_client import QdrantClient as QdrantSyncClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue

from knowledge_graph_rag.config.settings import get_settings

logger = structlog.get_logger()
settings = get_settings()


class QdrantClient:
    """Cliente para Qdrant Vector Database."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None
    ):
        """Inicializa o cliente Qdrant.

        Args:
            host: Host Qdrant
            port: Porta Qdrant
        """
        self.host = host or settings.qdrant_host
        self.port = port or settings.qdrant_port
        self.client: Optional[QdrantSyncClient] = None
        self.collection_templates = settings.qdrant_collection_templates
        self.collection_code = settings.qdrant_collection_code

    async def connect(self):
        """Estabelece conexão com Qdrant."""
        self.client = QdrantSyncClient(host=self.host, port=self.port)
        await self._ensure_collections()
        logger.info("qdrant_connected", host=self.host)

    async def close(self):
        """Fecha conexão com Qdrant."""
        if self.client:
            self.client.close()
            logger.info("qdrant_closed")

    async def _ensure_collections(self):
        """Garante que as coleções existem."""
        collections = [
            (self.collection_templates, "Templates de código"),
            (self.collection_code, "Código indexado")
        ]

        for collection_name, description in collections:
            try:
                self.client.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(
                        size=settings.embedding_dimension,
                        distance=Distance.COSINE
                    )
                )
                logger.info("qdrant_collection_created", collection=collection_name)
            except Exception:
                # Coleção já existe
                logger.debug("qdrant_collection_exists", collection=collection_name)

    async def search_templates(
        self,
        query_vector: List[float],
        limit: int = 10,
        score_threshold: float = 0.7
    ) -> List[Dict[str, Any]]:
        """Busca templates similares.

        Args:
            query_vector: Vetor de consulta
            limit: Limite de resultados
            score_threshold: Score mínimo

        Returns:
            Lista de templates similares
        """
        results = self.client.search(
            collection_name=self.collection_templates,
            query_vector=query_vector,
            query_filter=None,
            limit=limit,
            score_threshold=score_threshold
        )

        return [
            {
                "id": r.id,
                "score": r.score,
                "payload": r.payload
            }
            for r in results
        ]

    async def search_code(
        self,
        query_vector: List[float],
        limit: int = 10,
        score_threshold: float = 0.7,
        language_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Busca código similar.

        Args:
            query_vector: Vetor de consulta
            limit: Limite de resultados
            score_threshold: Score mínimo
            language_filter: Filtro de linguagem

        Returns:
            Lista de código similar
        """
        query_filter = None
        if language_filter:
            query_filter = Filter(
                must=[FieldCondition(key="language", match=MatchValue(value=language_filter))]
            )

        results = self.client.search(
            collection_name=self.collection_code,
            query_vector=query_vector,
            query_filter=query_filter,
            limit=limit,
            score_threshold=score_threshold
        )

        return [
            {
                "id": r.id,
                "score": r.score,
                "payload": r.payload
            }
            for r in results
        ]

    async def upsert_template(
        self,
        template_id: str,
        vector: List[float],
        payload: Dict[str, Any]
    ):
        """Indexa um template.

        Args:
            template_id: ID do template
            vector: Vetor de embeddings
            payload: Metadados do template
        """
        point = PointStruct(
            id=template_id,
            vector=vector,
            payload=payload
        )

        self.client.upsert(
            collection_name=self.collection_templates,
            points=[point]
        )

        logger.info("template_indexed", template_id=template_id)

    async def upsert_code(
        self,
        code_id: str,
        vector: List[float],
        payload: Dict[str, Any]
    ):
        """Indexa código.

        Args:
            code_id: ID do código
            vector: Vetor de embeddings
            payload: Metadados do código
        """
        point = PointStruct(
            id=code_id,
            vector=vector,
            payload=payload
        )

        self.client.upsert(
            collection_name=self.collection_code,
            points=[point]
        )

        logger.info("code_indexed", code_id=code_id)

    async def delete_points(self, collection_name: str, ids: List[str]):
        """Remove pontos da coleção.

        Args:
            collection_name: Nome da coleção
            ids: IDs dos pontos a remover
        """
        self.client.delete(
            collection_name=collection_name,
            points_selector=ids
        )

        logger.info("points_deleted", count=len(ids))
