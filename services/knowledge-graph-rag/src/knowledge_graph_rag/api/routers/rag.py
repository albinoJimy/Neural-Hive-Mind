"""Router REST para RAG."""

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from knowledge_graph_rag.services.rag_query_engine import RAGQueryEngine
from knowledge_graph_rag.services.contextual_retriever import ContextualRetriever
from knowledge_graph_rag.graph.qdrant_client import QdrantClient
from knowledge_graph_rag.graph.neo4j_client import Neo4jClient
from knowledge_graph_rag.embeddings.openai_embedder import OpenAIEmbedder
from knowledge_graph_rag.embeddings.cache import EmbeddingCache
import structlog

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/rag", tags=["rag"])


# Request/Response Models
class SearchRequest(BaseModel):
    """Request para busca RAG."""

    query: str = Field(..., min_length=1, description="Texto da busca")
    alpha: float = Field(default=0.5, ge=0.0, le=1.0, description="Peso vector vs graph")
    limit: int = Field(default=10, ge=1, le=100, description="Limite de resultados")
    artifact_type: str = Field(default="all", description="Tipo de artefato")


class SearchResultItem(BaseModel):
    """Item de resultado da busca."""

    id: str
    type: str
    score: float
    metadata: Dict[str, Any]


class SearchResponse(BaseModel):
    """Response da busca RAG."""

    results: List[SearchResultItem]
    total_count: int


class CodeContextRequest(BaseModel):
    """Request para contexto de geração de código."""

    requirements: List[str] = Field(..., min_length=1, description="Lista de requisitos")
    tech_stack: Dict[str, str] = Field(default_factory=dict, description="Stack tecnológico")


class ContextRequest(BaseModel):
    """Request para recuperação de contexto."""

    query: str = Field(..., min_length=1, description="Query de busca")
    context_type: str = Field(default="general", description="Tipo de contexto")
    limit: int = Field(default=5, ge=1, le=50, description="Limite de resultados")


class ContextItem(BaseModel):
    """Item de contexto."""

    id: str
    score: float
    metadata: Dict[str, Any]


class ContextResponse(BaseModel):
    """Response de contexto."""

    query: str
    similar_architectures: List[ContextItem]
    similar_templates: List[ContextItem]
    code_snippets: List[ContextItem]


def _get_rag_engine() -> RAGQueryEngine:
    """Factory para criar motor RAG."""
    cache = EmbeddingCache()
    embedder = OpenAIEmbedder(cache=cache)
    return RAGQueryEngine(qdrant=QdrantClient(), neo4j=Neo4jClient(), embedder=embedder)


@router.post("/search", response_model=SearchResponse)
async def search(request: SearchRequest) -> SearchResponse:
    """Executa busca RAG híbrida.

    Combina busca vetorial (Qdrant) e busca no grafo (Neo4j).
    """
    try:
        engine = _get_rag_engine()

        results = await engine.hybrid_search(
            query=request.query,
            alpha=request.alpha,
            limit=request.limit,
            artifact_type=request.artifact_type,
        )

        return SearchResponse(
            results=[
                SearchResultItem(id=r.id, type=r.type, score=r.score, metadata=r.metadata)
                for r in results
            ],
            total_count=len(results),
        )

    except Exception as e:
        logger.error("search_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Search failed: {str(e)}"
        )


@router.post("/search/templates", response_model=SearchResponse)
async def search_templates(request: SearchRequest) -> SearchResponse:
    """Busca apenas templates similares."""
    try:
        engine = _get_rag_engine()

        results = await engine.search_templates(query=request.query, limit=request.limit)

        return SearchResponse(
            results=[
                SearchResultItem(id=r.id, type=r.type, score=r.score, metadata=r.metadata)
                for r in results
            ],
            total_count=len(results),
        )

    except Exception as e:
        logger.error("template_search_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Template search failed: {str(e)}",
        )


@router.post("/search/code", response_model=SearchResponse)
async def search_code(request: SearchRequest) -> SearchResponse:
    """Busca apenas código similar."""
    try:
        engine = _get_rag_engine()

        results = await engine.search_code(query=request.query, limit=request.limit)

        return SearchResponse(
            results=[
                SearchResultItem(id=r.id, type=r.type, score=r.score, metadata=r.metadata)
                for r in results
            ],
            total_count=len(results),
        )

    except Exception as e:
        logger.error("code_search_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Code search failed: {str(e)}",
        )


@router.post("/context", response_model=ContextResponse)
async def get_context(request: ContextRequest) -> ContextResponse:
    """Recupera contexto enriquecido para query."""
    try:
        engine = _get_rag_engine()
        retriever = ContextualRetriever(engine)

        context = await retriever.retrieve_context(
            query=request.query, context_type=request.context_type, limit=request.limit
        )

        return ContextResponse(
            query=request.query,
            similar_architectures=[
                ContextItem(id=r.id, score=r.score, metadata=r.metadata)
                for r in context.similar_architectures
            ],
            similar_templates=[
                ContextItem(id=r.id, score=r.score, metadata=r.metadata)
                for r in context.similar_templates
            ],
            code_snippets=[
                ContextItem(id=r.id, score=r.score, metadata=r.metadata)
                for r in context.code_snippets
            ],
        )

    except Exception as e:
        logger.error("context_retrieval_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Context retrieval failed: {str(e)}",
        )


@router.post("/context/code")
async def get_code_generation_context(request: CodeContextRequest) -> Dict[str, Any]:
    """Obtém contexto para geração de código."""
    try:
        engine = _get_rag_engine()
        retriever = ContextualRetriever(engine)

        context = await retriever.retrieve_for_code_generation(
            requirements=request.requirements, tech_stack=request.tech_stack
        )

        return context

    except Exception as e:
        logger.error("code_context_retrieval_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Code context retrieval failed: {str(e)}",
        )


@router.get("/health")
async def health_check():
    """Health check do RAG router."""
    return {"service": "knowledge-graph-rag", "router": "rag", "status": "healthy"}
