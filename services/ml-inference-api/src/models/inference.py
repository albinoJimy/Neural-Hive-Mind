"""Modelos de dados para inferência ML."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class ModelType(str, Enum):
    """Tipo de modelo ML."""

    CLASSIFICATION = "classification"
    REGRESSION = "regression"
    CLUSTERING = "clustering"
    ANOMALY_DETECTION = "anomaly_detection"
    RECOMMENDATION = "recommendation"


class InferenceStatus(str, Enum):
    """Status de uma requisição de inferência."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CACHED = "cached"


class InferenceRequest(BaseModel):
    """Requisição de inferência ML."""

    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    request_id: str = Field(..., description="ID único da requisição")
    model_name: str = Field(..., description="Nome do modelo a usar")
    model_version: Optional[str] = Field("latest", description="Versão do modelo")
    model_type: ModelType = Field(..., description="Tipo de modelo")
    features: dict[str, Any] = Field(..., description="Features para predição")
    context: Optional[dict[str, Any]] = Field(None, description="Contexto adicional")
    priority: int = Field(default=5, ge=1, le=10, description="Prioridade (1-10)")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Data de criação")


class InferenceResponse(BaseModel):
    """Resposta de inferência ML."""

    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    request_id: str = Field(..., description="ID da requisição original")
    model_name: str = Field(..., description="Modelo usado")
    model_version: str = Field(..., description="Versão do modelo usado")
    status: InferenceStatus = Field(..., description="Status da inferência")
    prediction: Optional[dict[str, Any]] = Field(None, description="Resultado da predição")
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="Confiança da predição")
    latency_ms: Optional[int] = Field(None, description="Latência em ms")
    error: Optional[str] = Field(None, description="Mensagem de erro se falhou")
    cached: bool = Field(default=False, description="Se veio do cache")
    processed_at: datetime = Field(
        default_factory=datetime.utcnow, description="Data de processamento"
    )


class ModelMetadata(BaseModel):
    """Metadados de um modelo ML."""

    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    name: str = Field(..., description="Nome do modelo")
    version: str = Field(..., description="Versão do modelo")
    model_type: ModelType = Field(..., description="Tipo de modelo")
    feature_names: list[str] = Field(..., description="Nomes das features esperadas")
    loaded_at: datetime = Field(default_factory=datetime.utcnow, description="Data de carregamento")
    memory_mb: Optional[float] = Field(None, description="Uso de memória em MB")
