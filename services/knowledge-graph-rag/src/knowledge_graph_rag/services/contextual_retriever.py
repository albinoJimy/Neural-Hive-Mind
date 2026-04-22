"""Recuperação contextual para geração de código."""

from typing import Any, Dict, List

import structlog

from knowledge_graph_rag.models.retrieval import RetrievalContext
from knowledge_graph_rag.services.rag_query_engine import RAGQueryEngine

logger = structlog.get_logger()


class ContextualRetriever:
    """Recupera contexto enriquecido para geração."""

    def __init__(self, rag_engine: RAGQueryEngine):
        """Inicializa o retriever.

        Args:
            rag_engine: Motor RAG
        """
        self.rag_engine = rag_engine

    async def retrieve_for_code_generation(
        self,
        requirements: List[str],
        tech_stack: Dict[str, str],
    ) -> Dict[str, Any]:
        """Recupera contexto para geração de código.

        Args:
            requirements: Lista de requisitos
            tech_stack: Stack tecnológico

        Returns:
            Contexto enriquecido
        """
        # Construir query a partir dos requisitos
        query = " ".join(requirements[:3])  # Usar os 3 primeiros requisitos

        # Recuperar contexto
        retrieval_context = await self.rag_engine.retrieve_context(
            query=query, artifact_type="all", limit=5
        )

        # Enriquecer com tech stack
        context = {
            "query": query,
            "tech_stack": tech_stack,
            "similar_architectures": [
                {"id": r.id, "score": r.score, "metadata": r.metadata}
                for r in retrieval_context.similar_architectures
            ],
            "similar_templates": [
                {"id": r.id, "score": r.score, "metadata": r.metadata}
                for r in retrieval_context.similar_templates
            ],
            "code_snippets": [
                {"id": r.id, "score": r.score, "metadata": r.metadata}
                for r in retrieval_context.code_snippets
            ],
            "connections": retrieval_context.connections,
        }

        logger.info(
            "code_generation_context_retrieved",
            architectures_count=len(context["similar_architectures"]),
            templates_count=len(context["similar_templates"]),
            code_snippets_count=len(context["code_snippets"]),
        )

        return context

    async def retrieve_for_architecture_design(
        self,
        requirements: List[str],
        constraints: List[str],
    ) -> Dict[str, Any]:
        """Recupera contexto para design de arquitetura.

        Args:
            requirements: Lista de requisitos
            constraints: Lista de restrições

        Returns:
            Contexto para arquitetura
        """
        query = " ".join(requirements + constraints)

        context = await self.rag_engine.retrieve_context(
            query=query, artifact_type="architecture", limit=10
        )

        return {
            "requirements": requirements,
            "constraints": constraints,
            "similar_architectures": [
                {
                    "plan_id": r.id,
                    "similarity": r.score,
                    "type": r.metadata.get("architecture_type", "unknown"),
                }
                for r in context.similar_architectures
            ],
            "connections": context.connections,
        }

    async def retrieve_context(
        self,
        query: str,
        context_type: str = "general",
        limit: int = 5,
    ) -> RetrievalContext:
        """Recupera contexto baseado no tipo especificado.

        Args:
            query: Query de busca
            context_type: Tipo de contexto (architecture, code, template, all)
            limit: Limite de resultados

        Returns:
            Contexto recuperado
        """
        # Mapear context_type para artifact_type
        artifact_mapping = {
            "architecture": "architecture",
            "code": "code",
            "template": "template",
            "general": "all",
            "all": "all",
        }

        artifact_type = artifact_mapping.get(context_type, "all")

        context = await self.rag_engine.retrieve_context(
            query=query, artifact_type=artifact_type, limit=limit
        )

        logger.info(
            "context_retrieved_by_type",
            context_type=context_type,
            artifact_type=artifact_type,
            architectures=len(context.similar_architectures),
            templates=len(context.similar_templates),
            code_snippets=len(context.code_snippets),
        )

        return context

    async def retrieve_with_filters(
        self,
        query: str,
        filters: Dict[str, Any],
        limit: int = 10,
    ) -> RetrievalContext:
        """Recupera contexto com filtros específicos.

        Args:
            query: Query de busca
            filters: Filtros (language, stack, etc.)
            limit: Limite de resultados

        Returns:
            Contexto filtrado
        """
        context = RetrievalContext(query=query)

        # Buscar código com filtro de linguagem
        if filters.get("language"):
            code_results = await self.rag_engine.search_code(
                query=query, limit=limit, language_filter=filters["language"]
            )
            context.code_snippets = code_results

        # Buscar templates com filtro de stack
        if filters.get("stack"):
            templates = await self.rag_engine.search_templates(query=query, limit=limit)
            # Filtrar por stack no metadata
            context.similar_templates = [
                t for t in templates if t.metadata.get("stack") == filters["stack"]
            ]

        logger.info(
            "filtered_context_retrieved",
            filters=filters,
            code_results=len(context.code_snippets),
            template_results=len(context.similar_templates),
        )

        return context
