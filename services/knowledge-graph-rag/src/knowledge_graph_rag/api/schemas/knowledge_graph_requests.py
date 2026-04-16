"""Schemas de request para Knowledge Graph RAG API."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from knowledge_graph_rag.models.knowledge import NodeType, RelationType


class CreateNodeRequest(BaseModel):
    """Request para criar nó."""

    node_type: NodeType = Field(..., description="Tipo do nó")
    name: str = Field(..., min_length=1, max_length=200, description="Nome do nó")
    description: str = Field(..., description="Descrição detalhada")
    properties: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Propriedades adicionais"
    )


class CreateRelationRequest(BaseModel):
    """Request para criar relação."""

    source_id: str = Field(..., description="ID do nó de origem")
    target_id: str = Field(..., description="ID do nó de destino")
    relation_type: RelationType = Field(..., description="Tipo da relação")
    properties: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Propriedades da relação"
    )


class SearchRequest(BaseModel):
    """Request para busca no grafo."""

    query_text: str = Field(..., min_length=1, description="Texto da busca")
    node_types: Optional[List[NodeType]] = Field(
        None,
        description="Filtrar por tipos de nó"
    )
    limit: int = Field(default=10, ge=1, le=100, description="Limite de resultados")
    include_relations: bool = Field(default=True, description="Incluir relações")


class RAGQueryRequest(BaseModel):
    """Request para query com RAG."""

    query_text: str = Field(..., min_length=1, description="Pergunta ou query")
    context: Optional[str] = Field(None, description="Contexto adicional opcional")


class RAGQueryResponse(BaseModel):
    """Response de query RAG."""

    query: str
    response: str
    context_used: bool
    sources: List[str] = Field(default_factory=list, description="IDs dos nós usados")
