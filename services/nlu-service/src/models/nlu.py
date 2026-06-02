"""Modelos de dados para o NLU Service."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class UnifiedDomain(str, Enum):
    """Domínios unificados da NLU (INV-1)."""

    BUSINESS = "BUSINESS"
    TECHNICAL = "TECHNICAL"
    INFRASTRUCTURE = "INFRASTRUCTURE"
    SECURITY = "SECURITY"


class EntityType(str, Enum):
    """Tipos de entidades para NER (spaCy + custom)."""

    UNKNOWN = "UNKNOWN"
    PERSON = "PERSON"
    ORG = "ORG"
    GPE = "GPE"
    LOC = "LOC"
    DATE = "DATE"
    TIME = "TIME"
    MONEY = "MONEY"
    PERCENT = "PERCENT"
    CARDINAL = "CARDINAL"
    ORDINAL = "ORDINAL"
    QUANTITY = "QUANTITY"
    PRODUCT = "PRODUCT"
    EVENT = "EVENT"
    WORK_OF_ART = "WORK_OF_ART"
    LAW = "LAW"
    LANGUAGE = "LANGUAGE"
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    URL = "URL"
    IP_ADDRESS = "IP_ADDRESS"


class Entity(BaseModel):
    """Entidade extraída do texto (INV-1: type, value, confidence, start, end)."""

    type: EntityType = Field(..., description="Tipo da entidade")
    value: str = Field(..., description="Valor da entidade")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0, description="Confiança da extração")
    start: int | None = Field(None, description="Posição inicial no texto")
    end: int | None = Field(None, description="Posição final no texto")
    label: str | None = Field(None, description="Label específico do NER")
    attributes: dict[str, str] = Field(default_factory=dict, description="Atributos adicionais")


class NLUResult(BaseModel):
    """Resultado do pipeline NLU (INV-1: domain, entities, confidence, keywords)."""

    processed_text: str = Field(..., description="Texto processado e normalizado")
    domain: UnifiedDomain = Field(..., description="Domínio classificado (INV-1)")
    classification: str = Field(default="general", description="Classificação específica")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confiança da classificação (INV-1)")
    entities: list[Entity] = Field(default_factory=list, description="Entidades extraídas (INV-1)")
    keywords: list[str] = Field(
        default_factory=list, description="Palavras-chave extraídas (INV-1)"
    )
    original_language: str = Field(default="pt", description="Idioma detectado")
    requires_manual_validation: bool = Field(default=False, description="Requer validação humana")
    confidence_status: str = Field(default="medium", description="Status: high, medium, low")
    adaptive_threshold: float | None = Field(
        None, ge=0.0, le=1.0, description="Threshold adaptativo calculado"
    )
    metadata: dict[str, str] = Field(default_factory=dict, description="Metadados adicionais")

    @field_validator("domain", mode="before")
    @classmethod
    def coerce_domain(cls, v):
        """Coerção para UnifiedDomain."""
        if isinstance(v, UnifiedDomain):
            return v
        if isinstance(v, str):
            try:
                return UnifiedDomain[v.upper()]
            except KeyError:
                return UnifiedDomain.TECHNICAL
        return v


class ParseRequest(BaseModel):
    """Request para processamento NLU completo."""

    text: str = Field(..., min_length=1, max_length=10000, description="Texto para processar")
    language: str = Field(default="pt", description="Idioma do texto (ISO 639-1)")
    correlation_id: str | None = Field(None, description="ID de correlação para tracing")
    trace_id: str | None = Field(None, description="ID de trace OpenTelemetry")
    context: dict[str, str] = Field(
        default_factory=dict, description="Contexto adicional (tenant_id, user_id, etc)"
    )
    enable_cache: bool = Field(default=True, description="Habilitar cache Redis")


class ParseResponse(BaseModel):
    """Response para processamento NLU completo."""

    result: NLUResult = Field(..., description="Resultado NLU completo")
    processing_time_ms: int = Field(..., description="Tempo de processamento em ms")
    processed_at: datetime = Field(
        default_factory=datetime.now, description="Timestamp do processamento"
    )
    cached: bool = Field(default=False, description="Indica se resultado veio do cache")


class ClassifyDomainRequest(BaseModel):
    """Request para classificação de domínio."""

    text: str = Field(..., min_length=1, max_length=10000, description="Texto para classificar")
    language: str = Field(default="pt", description="Idioma do texto")
    correlation_id: str | None = Field(None, description="ID de correlação")
    context: dict[str, str] = Field(default_factory=dict, description="Contexto adicional")


class ClassifyDomainResponse(BaseModel):
    """Response para classificação de domínio."""

    domain: UnifiedDomain = Field(..., description="Domínio classificado")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confiança da classificação")
    reasoning: str = Field(default="", description="Explicação da classificação")
    processing_time_ms: int = Field(..., description="Tempo de processamento")
    classified_at: datetime = Field(
        default_factory=datetime.now, description="Timestamp da classificação"
    )


class ExtractEntitiesRequest(BaseModel):
    """Request para extração de entidades."""

    text: str = Field(
        ..., min_length=1, max_length=10000, description="Texto para extrair entidades"
    )
    language: str = Field(default="pt", description="Idioma do texto")
    correlation_id: str | None = Field(None, description="ID de correlação")
    entity_types: list[EntityType] = Field(
        default_factory=list, description="Tipos de entidades a extrair (vazio = todas)"
    )


class ExtractEntitiesResponse(BaseModel):
    """Response para extração de entidades."""

    entities: list[Entity] = Field(..., description="Entidades extraídas")
    processing_time_ms: int = Field(..., description="Tempo de processamento")
    extracted_at: datetime = Field(
        default_factory=datetime.now, description="Timestamp da extração"
    )


class CalculateConfidenceRequest(BaseModel):
    """Request para cálculo de confiança."""

    nlu_result: NLUResult = Field(..., description="Resultado NLU para calcular confiança")


class CalculateConfidenceResponse(BaseModel):
    """Response para cálculo de confiança."""

    confidence: float = Field(..., ge=0.0, le=1.0, description="Score de confiança")
    confidence_status: str = Field(..., description="Status: high, medium, low")
    adaptive_threshold: float = Field(..., ge=0.0, le=1.0, description="Threshold adaptativo")
    requires_manual_validation: bool = Field(..., description="Indica se requer validação humana")
    factor_scores: dict[str, float] = Field(
        default_factory=dict, description="Scores por fator de confiança"
    )


class DetectLanguageRequest(BaseModel):
    """Request para detecção de idioma."""

    text: str = Field(..., min_length=1, max_length=10000, description="Texto para detectar idioma")


class LanguageCandidate(BaseModel):
    """Candidato de idioma detectado."""

    language: str = Field(..., description="Código do idioma (ISO 639-1)")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confiança da detecção")


class DetectLanguageResponse(BaseModel):
    """Response para detecção de idioma."""

    language: str = Field(..., description="Idioma detectado (ISO 639-1)")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confiança da detecção")
    candidates: list[LanguageCandidate] = Field(
        default_factory=list, description="Candidatos alternativos"
    )


# Health check models


class ServingStatus(str, Enum):
    """Status de serving do serviço."""

    UNKNOWN = "UNKNOWN"
    SERVING = "SERVING"
    NOT_SERVING = "NOT_SERVING"
    SERVICE_UNKNOWN = "SERVICE_UNKNOWN"


class HealthCheckResponse(BaseModel):
    """Response de health check."""

    status: ServingStatus = Field(..., description="Status do serviço")
    details: dict[str, str] = Field(default_factory=dict, description="Detalhes do status")
    version: str = Field(..., description="Versão do serviço")
