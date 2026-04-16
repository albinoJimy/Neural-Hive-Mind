"""Motor de busca RAG (Retrieval-Augmented Generation)."""

from typing import Any, Dict, List, Optional

import structlog

from knowledge_graph_rag.config.settings import get_settings
from knowledge_graph_rag.embeddings.openai_embedder import OpenAIEmbedder
from knowledge_graph_rag.graph.neo4j_client import Neo4jClient
from knowledge_graph_rag.graph.qdrant_client import QdrantClient
from knowledge_graph_rag.models.retrieval import (
    RetrievalContext,
    RetrievalResult,
)

logger = structlog.get_logger()
settings = get_settings()


class RAGQueryEngine:
    """Motor de busca RAG combinando Neo4j e Qdrant."""

    def __init__(
        self,
        neo4j: Optional[Neo4jClient] = None,
        qdrant: Optional[QdrantClient] = None,
        embedder: Optional[OpenAIEmbedder] = None,
    ):
        """Inicializa o motor RAG.

        Args:
            neo4j: Cliente Neo4j
            qdrant: Cliente Qdrant
            embedder: Serviço de embeddings
        """
        self.neo4j = neo4j
        self.qdrant = qdrant
        self.embedder = embedder
        self.settings = settings

    async def hybrid_search(
        self,
        query: str,
        alpha: float = 0.5,
        limit: int = 10,
        artifact_type: str = "all",
    ) -> List[RetrievalResult]:
        """Executa busca híbrida (graph + vector).

        Args:
            query: Query de busca
            alpha: Peso vector vs graph (0=only graph, 1=only vector)
            limit: Limite de resultados
            artifact_type: Tipo de artefacto

        Returns:
            Lista de resultados ordenados
        """
        # Gerar embedding da query
        query_vector = await self.embedder.embed(query)

        # Busca vectorial (Qdrant)
        vector_results: List[Dict[str, Any]] = []
        if self.qdrant and alpha > 0:
            if artifact_type in ["all", "template"]:
                vector_results.extend(
                    await self.qdrant.search_templates(
                        query_vector=query_vector,
                        limit=limit
                    )
                )
            if artifact_type in ["all", "code"]:
                vector_results.extend(
                    await self.qdrant.search_code(
                        query_vector=query_vector,
                        limit=limit
                    )
                )

        # Busca no grafo (Neo4j)
        graph_results: List[Dict[str, Any]] = []
        if self.neo4j and alpha < 1:
            # Extrair palavras-chave da query
            keywords = self._extract_keywords(query)

            if artifact_type in ["all", "architecture"] and keywords:
                graph_results.extend(
                    await self.neo4j.find_similar_architectures(
                        requirements=keywords,
                        limit=limit
                    )
                )

        # Combinar resultados com pesos
        combined = self._combine_results(
            vector_results=vector_results,
            graph_results=graph_results,
            alpha=alpha
        )

        # Ordenar e limitar
        combined.sort(key=lambda r: r.score, reverse=True)

        return combined[:limit]

    async def retrieve_context(
        self,
        query: str,
        artifact_type: str = "architecture",
        limit: int = 5,
    ) -> RetrievalContext:
        """Recupera contexto enriquecido para geração.

        Args:
            query: Query original
            artifact_type: Tipo de artefacto
            limit: Limite por categoria

        Returns:
            Contexto recuperado
        """
        context = RetrievalContext(query=query)

        # Buscar arquiteturas similares
        if artifact_type in ["all", "architecture"]:
            arch_results = await self.hybrid_search(
                query=query,
                alpha=0.5,
                limit=limit,
                artifact_type="architecture"
            )
            context.similar_architectures = arch_results

        # Buscar templates similares
        if artifact_type in ["all", "template"]:
            query_vector = await self.embedder.embed(query)

            if self.qdrant:
                template_results = await self.qdrant.search_templates(
                    query_vector=query_vector,
                    limit=limit
                )
                context.similar_templates = [
                    RetrievalResult(
                        id=str(r["id"]),
                        type="template",
                        score=r["score"],
                        metadata=r.get("payload", r)
                    )
                    for r in template_results
                ]

        # Buscar code snippets similares
        if artifact_type in ["all", "code"]:
            query_vector = await self.embedder.embed(query)

            if self.qdrant:
                code_results = await self.qdrant.search_code(
                    query_vector=query_vector,
                    limit=limit
                )
                context.code_snippets = [
                    RetrievalResult(
                        id=str(r["id"]),
                        type="code",
                        score=r["score"],
                        metadata=r.get("payload", r)
                    )
                    for r in code_results
                ]

        # Buscar conexões no grafo
        if self.neo4j and context.similar_architectures:
            first_arch = context.similar_architectures[0]
            connections = await self.neo4j.get_connections_context(
                node_id=first_arch.id
            )
            context.connections = connections

        logger.info(
            "context_retrieved",
            architectures=len(context.similar_architectures),
            templates=len(context.similar_templates),
            code_snippets=len(context.code_snippets),
            connections=len(context.connections),
        )

        return context

    async def search_templates(
        self,
        query: str,
        limit: int = 10,
        score_threshold: float = 0.7,
    ) -> List[RetrievalResult]:
        """Busca templates similares.

        Args:
            query: Query de busca
            limit: Limite de resultados
            score_threshold: Score mínimo

        Returns:
            Lista de templates similares
        """
        if not self.qdrant or not self.embedder:
            logger.warning("search_templates_missing_clients")
            return []

        query_vector = await self.embedder.embed(query)

        results = await self.qdrant.search_templates(
            query_vector=query_vector,
            limit=limit,
            score_threshold=score_threshold
        )

        return [
            RetrievalResult(
                id=str(r["id"]),
                type="template",
                score=r["score"],
                metadata=r.get("payload", r)
            )
            for r in results
        ]

    async def search_code(
        self,
        query: str,
        limit: int = 10,
        score_threshold: float = 0.7,
        language_filter: Optional[str] = None,
    ) -> List[RetrievalResult]:
        """Busca código similar.

        Args:
            query: Query de busca
            limit: Limite de resultados
            score_threshold: Score mínimo
            language_filter: Filtro de linguagem

        Returns:
            Lista de código similar
        """
        if not self.qdrant or not self.embedder:
            logger.warning("search_code_missing_clients")
            return []

        query_vector = await self.embedder.embed(query)

        results = await self.qdrant.search_code(
            query_vector=query_vector,
            limit=limit,
            score_threshold=score_threshold,
            language_filter=language_filter
        )

        return [
            RetrievalResult(
                id=str(r["id"]),
                type="code",
                score=r["score"],
                metadata=r.get("payload", r)
            )
            for r in results
        ]

    def _extract_keywords(self, query: str) -> List[str]:
        """Extrai palavras-chave da query.

        Args:
            query: Query original

        Returns:
            Lista de palavras-chave
        """
        # Implementação simples - pode ser melhorada com NLP
        stop_words = {
            "a", "o", "de", "para", "com", "sem", "um", "uma",
            "create", "make", "get", "find", "search", "the",
            "and", "or", "but", "in", "on", "at", "to", "for"
        }
        words = query.lower().split()

        keywords = [w for w in words if len(w) > 3 and w not in stop_words]

        return keywords[:10]  # Limitar a 10 keywords

    def _combine_results(
        self,
        vector_results: List[Dict[str, Any]],
        graph_results: List[Dict[str, Any]],
        alpha: float,
    ) -> List[RetrievalResult]:
        """Combina resultados de vector e graph.

        Args:
            vector_results: Resultados da busca vectorial
            graph_results: Resultados da busca no grafo
            alpha: Peso (0=only graph, 1=only vector)

        Returns:
            Lista combinada de resultados
        """
        combined_map: Dict[str, RetrievalResult] = {}

        # Adicionar resultados vectoriais
        for r in vector_results:
            result = RetrievalResult(
                id=str(r["id"]),
                type="vector",
                score=alpha * r["score"],  # Aplicar peso alpha
                metadata=r.get("payload", r)
            )
            combined_map[result.id] = result

        # Adicionar resultados do grafo
        for r in graph_results:
            plan_id = r.get("plan_id", r.get("id"))
            if not plan_id:
                continue

            similarity = r.get("similarity", r.get("score", 0))

            if plan_id in combined_map:
                # Combinar scores
                combined_map[plan_id].score += (1 - alpha) * similarity
                combined_map[plan_id].type = "hybrid"
            else:
                result = RetrievalResult(
                    id=str(plan_id),
                    type="graph",
                    score=(1 - alpha) * similarity,
                    metadata=r
                )
                combined_map[plan_id] = result

        return list(combined_map.values())
