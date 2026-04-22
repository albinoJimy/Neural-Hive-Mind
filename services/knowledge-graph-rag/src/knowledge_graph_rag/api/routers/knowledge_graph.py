"""Router REST para Knowledge Graph RAG."""

from typing import Optional
from fastapi import APIRouter, HTTPException, status
from structlog import get_logger

from knowledge_graph_rag.models.knowledge import (
    KnowledgeNode,
    KnowledgeRelation,
    GraphQuery,
    GraphSearchResult,
)
from knowledge_graph_rag.services.knowledge_graph_rag import KnowledgeGraphRAG
from knowledge_graph_rag.api.schemas.knowledge_graph_requests import (
    CreateNodeRequest,
    CreateRelationRequest,
    SearchRequest,
    RAGQueryRequest,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/graph", tags=["knowledge-graph"])

# Singleton da service
_rag_service: Optional[KnowledgeGraphRAG] = None


def get_rag_service() -> KnowledgeGraphRAG:
    """Retorna instância singleton do serviço RAG."""
    global _rag_service
    if _rag_service is None:
        _rag_service = KnowledgeGraphRAG()
    return _rag_service


@router.post(
    "/nodes",
    response_model=KnowledgeNode,
    status_code=status.HTTP_201_CREATED,
    summary="Criar nó no grafo",
)
async def create_node(request: CreateNodeRequest) -> KnowledgeNode:
    """
    Cria um novo nó no grafo de conhecimento.

    O nó é automaticamente enriquecido com embedding vetorial
    para busca semântica.
    """
    service = get_rag_service()

    try:
        node = await service.create_node(
            node_type=request.node_type,
            name=request.name,
            description=request.description,
            properties=request.properties or {},
        )
        return node

    except Exception as e:
        logger.error("create_node_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Falha ao criar nó: {str(e)}"
        )


@router.get("/nodes/{node_id}", response_model=KnowledgeNode, summary="Buscar nó por ID")
async def get_node(node_id: str) -> KnowledgeNode:
    """Retorna um nó específico pelo seu ID."""
    # TODO: Implementar busca no repositório
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Busca por ID ainda não implementada"
    )


@router.post(
    "/relations",
    response_model=KnowledgeRelation,
    status_code=status.HTTP_201_CREATED,
    summary="Criar relação entre nós",
)
async def create_relation(request: CreateRelationRequest) -> KnowledgeRelation:
    """
    Cria uma relação entre dois nós existentes.

    Valida que ambos os nós existem antes de criar a relação.
    """
    service = get_rag_service()

    try:
        relation = await service.create_relation(
            source_id=request.source_id,
            target_id=request.target_id,
            relation_type=request.relation_type,
            properties=request.properties or {},
        )
        return relation

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("create_relation_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Falha ao criar relação: {str(e)}",
        )


@router.post("/search", response_model=GraphSearchResult, summary="Busca semântica no grafo")
async def search_graph(request: SearchRequest) -> GraphSearchResult:
    """
    Realiza busca semântica no grafo de conhecimento.

    Usa busca vetorial para encontrar nós relevantes baseados
    no texto da query.
    """
    service = get_rag_service()

    try:
        query = GraphQuery(
            query_text=request.query_text,
            node_types=request.node_types,
            limit=request.limit,
            include_relations=request.include_relations,
        )

        result = await service.search(query)
        return result

    except Exception as e:
        logger.error("search_failed", query=request.query_text, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Falha na busca: {str(e)}"
        )


@router.post("/rag/query", response_model=dict, summary="Query com RAG")
async def query_with_rag(request: RAGQueryRequest) -> dict:
    """
    Realiza uma query usando RAG (Retrieval Augmented Generation).

    1. Busca nós relevantes no grafo
    2. Gera contexto estruturado
    3. Envia contexto + query para LLM
    4. Retorna resposta enriquecida
    """
    service = get_rag_service()

    try:
        response = await service.query_with_rag(
            query_text=request.query_text, context=request.context
        )

        return {"query": request.query_text, "response": response, "context_used": True}

    except Exception as e:
        logger.error("rag_query_failed", query=request.query_text, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Falha na query RAG: {str(e)}",
        )


@router.get("/health", summary="Health check do serviço")
async def health_check() -> dict:
    """Verifica saúde do serviço."""
    return {"status": "healthy", "service": "knowledge-graph-rag", "version": "0.1.0"}
