"""Modelos de dados para Knowledge Graph."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class NodeType(str, Enum):
    """Tipo de nó no grafo de conhecimento."""

    REQUIREMENT = "requirement"
    USER_STORY = "user_story"
    COMPONENT = "component"
    DOCUMENT = "document"
    DECISION = "decision"
    PERSONA = "persona"
    EPIC = " epic"


class RelationType(str, Enum):
    """Tipo de relação no grafo."""

    DEPENDS_ON = "depends_on"
    RELATES_TO = "relates_to"
    IMPLEMENTS = "implements"
    DERIVES_FROM = "derives_from"
    BLOCKS = "blocks"
    REFINES = "refines"


class KnowledgeNode(BaseModel):
    """Nó no grafo de conhecimento."""

    id: str = Field(..., description="ID único do nó")
    node_type: NodeType = Field(..., description="Tipo do nó")
    name: str = Field(..., description="Nome do nó")
    description: Optional[str] = Field(None, description="Descrição")
    properties: Dict[str, Any] = Field(default_factory=dict, description="Propriedades do nó")
    embedding: Optional[List[float]] = Field(None, description="Vector embedding")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(None)

    class Config:
        populate_by_name = True


class KnowledgeRelation(BaseModel):
    """Relação entre nós no grafo de conhecimento."""

    id: str = Field(..., description="ID único da relação")
    source_id: str = Field(..., description="ID do nó de origem")
    target_id: str = Field(..., description="ID do nó de destino")
    relation_type: RelationType = Field(..., description="Tipo da relação")
    properties: Dict[str, Any] = Field(default_factory=dict)
    weight: float = Field(default=1.0, description="Peso da relação (0-1)")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class GraphQuery(BaseModel):
    """Query para busca no grafo."""

    query_text: str = Field(..., description="Texto da query")
    node_types: Optional[List[NodeType]] = Field(None, description="Filtrar por tipos de nó")
    limit: int = Field(default=10, ge=1, le=100)
    include_relations: bool = Field(default=True)


class GraphSearchResult(BaseModel):
    """Resultado de busca no grafo."""

    nodes: List[KnowledgeNode]
    relations: List[KnowledgeRelation]
    total_found: int
    query_id: str


class RAGContext(BaseModel):
    """Contexto para RAG (Retrieval Augmented Generation)."""

    query: str
    retrieved_nodes: List[KnowledgeNode]
    context_text: str
    relevance_scores: List[float]
