"""Modelos de dados para RAG."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RetrievalResult(BaseModel):
    """Resultado de uma operação de RAG."""

    id: str = Field(..., description="ID do item recuperado")
    type: str = Field(..., description="Tipo: architecture, template, code")
    score: float = Field(..., description="Score de similaridade (0-1)")
    content: Optional[str] = Field(None, description="Conteúdo recuperado")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadados")


class RetrievalContext(BaseModel):
    """Contexto recuperado para geração."""

    query: str = Field(..., description="Query original")
    similar_architectures: List[RetrievalResult] = Field(
        default_factory=list,
        description="Arquiteturas similares"
    )
    similar_templates: List[RetrievalResult] = Field(
        default_factory=list,
        description="Templates similares"
    )
    code_snippets: List[RetrievalResult] = Field(
        default_factory=list,
        description="Trechos de código similar"
    )
    connections: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Conexões no grafo"
    )


class RetrievalRequest(BaseModel):
    """Request para recuperação de contexto."""

    query: str = Field(..., description="Query de busca")
    artifact_type: str = Field(
        default="all",
        description="Tipo de artefacto: all, architecture, template, code"
    )
    limit: int = Field(default=10, ge=1, le=100, description="Limite de resultados")
    alpha: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Peso vector vs graph (0=only graph, 1=only vector)"
    )
