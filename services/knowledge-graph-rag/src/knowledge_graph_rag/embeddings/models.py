"""Data models for embeddings."""

from typing import List, Optional

from pydantic import BaseModel, Field


class EmbeddingRequest(BaseModel):
    """Request para geração de embedding."""

    text: str = Field(..., description="Texto para gerar embedding")
    model: Optional[str] = Field(default=None, description="Modelo de embedding (opcional)")


class EmbeddingResponse(BaseModel):
    """Response para geração de embedding."""

    embedding: List[float] = Field(..., description="Vetor de embedding")
    model: str = Field(..., description="Modelo utilizado")
    dimensions: int = Field(..., description="Dimensões do vetor")


class EmbeddingBatchRequest(BaseModel):
    """Request para geração de embeddings em lote."""

    texts: List[str] = Field(..., description="Lista de textos para gerar embeddings")
    model: Optional[str] = Field(default=None, description="Modelo de embedding (opcional)")


class EmbeddingBatchResponse(BaseModel):
    """Response para geração de embeddings em lote."""

    embeddings: List[List[float]] = Field(..., description="Lista de vetores de embedding")
    model: str = Field(..., description="Modelo utilizado")
    dimensions: int = Field(..., description="Dimensões dos vetores")


class CachedEmbedding(BaseModel):
    """Embedding armazenado em cache."""

    text: str = Field(..., description="Texto original")
    embedding: List[float] = Field(..., description="Vetor de embedding")
    model: str = Field(..., description="Modelo utilizado")
    created_at: str = Field(..., description="Timestamp de criação")
