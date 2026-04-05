"""
Schemas Pydantic para API de inferência ML.
"""
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class DecisionType(str, Enum):
    """Tipos de decisão aprovados pelo modelo."""
    APPROVE = "approve"
    REJECT = "reject"
    REVIEW_REQUIRED = "review_required"


class PredictRequest(BaseModel):
    """Request para predição individual."""

    intent_text: str = Field(
        ...,
        description="Texto da intenção do usuário",
        min_length=1,
        max_length=5000,
    )
    specialist_confidence: float = Field(
        default=0.5,
        description="Confiança do especialista (0.0 - 1.0)",
        ge=0.0,
        le=1.0,
    )
    specialist_type: Optional[str] = Field(
        default=None,
        description="Tipo de especialista (opcional, para tracing)",
    )
    options: Optional["PredictOptions"] = Field(
        default=None, description="Opções adicionais de predição"
    )


class PredictOptions(BaseModel):
    """Opções adicionais para predição."""
    return_probabilities: bool = Field(
        default=True, description="Retornar probabilidades de cada classe"
    )
    return_features: bool = Field(
        default=False, description="Retornar features extraídas"
    )
    threshold: Optional[float] = Field(
        default=None, description="Threshold customizado para decisão"
    )


class PredictResponse(BaseModel):
    """Response de predição individual."""

    decision: DecisionType = Field(..., description="Decisão do modelo")
    confidence: float = Field(
        ..., description="Confiança da predição (0.0 - 1.0)", ge=0.0, le=1.0
    )
    probabilities: Optional[Dict[str, float]] = Field(
        default=None, description="Probabilidades por classe"
    )
    features: Optional[Dict[str, float]] = Field(
        default=None, description="Features extraídas (se solicitado)"
    )
    model_version: str = Field(..., description="Versão do modelo usado")
    inference_time_ms: float = Field(
        ..., description="Tempo de inferência em milissegundos"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Timestamp da predição"
    )


class BatchPredictRequest(BaseModel):
    """Request para predição em batch."""

    requests: List[PredictRequest] = Field(
        ...,
        description="Lista de requests de predição",
        min_length=1,
        max_length=100,
    )
    options: Optional["BatchOptions"] = Field(
        default=None, description="Opções de batch"
    )

    @field_validator("requests")
    @classmethod
    def validate_requests(cls, v: List[PredictRequest]) -> List[PredictRequest]:
        """Validar tamanho da lista."""
        if len(v) > 100:
            raise ValueError("Maximum batch size is 100")
        return v


class BatchOptions(BaseModel):
    """Opções de processamento em batch."""
    parallel: bool = Field(
        default=True, description="Processar em paralelo"
    )
    max_workers: Optional[int] = Field(
        default=None, description="Número máximo de workers"
    )
    aggregate_results: bool = Field(
        default=True, description="Agregar estatísticas dos resultados"
    )


class BatchPredictResponse(BaseModel):
    """Response de predição em batch."""

    results: List[PredictResponse] = Field(
        ..., description="Resultados individuais"
    )
    total_processed: int = Field(..., description="Total de itens processados")
    successful: int = Field(..., description="Número de predições bem-sucedidas")
    failed: int = Field(..., description="Número de predições falhadas")
    aggregate_stats: Optional[Dict[str, Any]] = Field(
        default=None, description="Estatísticas agregadas"
    )
    total_inference_time_ms: float = Field(
        ..., description="Tempo total de inferência em ms"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Timestamp do batch"
    )


class ModelInfo(BaseModel):
    """Informações sobre o modelo carregado."""

    name: str = Field(..., description="Nome do modelo")
    version: str = Field(..., description="Versão do modelo")
    type: str = Field(..., description="Tipo do modelo (ex: GradientBoostingClassifier)")
    trained_at: Optional[datetime] = Field(
        default=None, description="Data de treinamento"
    )
    training_samples: Optional[int] = Field(
        default=None, description="Número de amostras de treinamento"
    )
    features: List[str] = Field(
        ..., description="Lista de features usadas pelo modelo"
    )
    metrics: Optional[Dict[str, float]] = Field(
        default=None, description="Métricas de avaliação do modelo"
    )
    is_loaded: bool = Field(..., description="Se o modelo está carregado")
    loading_time_ms: Optional[float] = Field(
        default=None, description="Tempo de carregamento do modelo"
    )


class ErrorResponse(BaseModel):
    """Response de erro padrão."""

    error: str = Field(..., description="Tipo do erro")
    message: str = Field(..., description="Mensagem de erro detalhada")
    detail: Optional[str] = Field(
        default=None, description="Detalhes adicionais do erro"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Timestamp do erro"
    )


class HealthResponse(BaseModel):
    """Response de health check."""
    status: str = Field(..., description="Status do serviço (healthy/unhealthy)")
    service: str = Field(..., description="Nome do serviço")
    version: str = Field(..., description="Versão do serviço")


class ReadyResponse(BaseModel):
    """Response de readiness check."""
    status: str = Field(..., description="Status (ready/not_ready)")
    checks: Dict[str, bool] = Field(
        ..., description="Status das dependências"
    )
