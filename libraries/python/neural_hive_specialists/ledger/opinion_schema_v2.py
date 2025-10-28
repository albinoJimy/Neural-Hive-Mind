"""
OpinionSchemaV2: Schema versionado para opiniões do ledger cognitivo.

Define estrutura imutável com validação Pydantic e suporte a migração
de versões antigas.
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field, field_validator
import structlog

logger = structlog.get_logger(__name__)


class ReasoningFactor(BaseModel):
    """Fator individual de raciocínio."""
    factor_name: str = Field(..., description="Nome do fator")
    weight: float = Field(..., ge=0.0, le=1.0, description="Peso do fator")
    score: float = Field(..., ge=0.0, le=1.0, description="Score do fator")
    description: Optional[str] = Field(None, description="Descrição do fator")


class Mitigation(BaseModel):
    """Mitigação recomendada."""
    mitigation_type: str = Field(..., description="Tipo de mitigação")
    description: str = Field(..., description="Descrição da mitigação")
    priority: str = Field(..., description="Prioridade (high, medium, low)")
    estimated_effort: Optional[str] = Field(None, description="Esforço estimado")


class Opinion(BaseModel):
    """Opinião do especialista."""
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Score de confiança")
    risk_score: float = Field(..., ge=0.0, le=1.0, description="Score de risco")
    recommendation: str = Field(..., description="Recomendação (approve, reject, review_required, conditional)")
    reasoning_summary: str = Field(..., description="Resumo do raciocínio")
    reasoning_factors: List[ReasoningFactor] = Field(..., description="Fatores de raciocínio")
    explainability_token: str = Field(..., description="Token de explicabilidade")
    explainability: Dict[str, Any] = Field(default_factory=dict, description="Metadados de explicabilidade")
    mitigations: List[Mitigation] = Field(default_factory=list, description="Mitigações recomendadas")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadados adicionais")

    @field_validator('recommendation')
    @classmethod
    def validate_recommendation(cls, v):
        """Valida recomendação."""
        valid_recommendations = ['approve', 'reject', 'review_required', 'conditional']
        if v not in valid_recommendations:
            raise ValueError(f"recommendation must be one of {valid_recommendations}")
        return v


class OpinionDocumentV2(BaseModel):
    """Documento completo de opinião no ledger v2."""

    # Schema version
    schema_version: str = Field(default="2.0.0", description="Versão do schema")

    # Identificadores
    opinion_id: str = Field(..., description="ID único da opinião (SHA-256)")
    plan_id: str = Field(..., description="ID do plano cognitivo")
    intent_id: str = Field(..., description="ID do intent")
    specialist_type: str = Field(..., description="Tipo do especialista")
    specialist_version: str = Field(..., description="Versão do especialista")

    # Opinião
    opinion: Opinion = Field(..., description="Parecer do especialista")

    # Rastreamento
    correlation_id: str = Field(..., description="ID de correlação")
    trace_id: Optional[str] = Field(None, description="ID de trace distribuído")
    span_id: Optional[str] = Field(None, description="ID de span")

    # Timestamps
    evaluated_at: datetime = Field(..., description="Timestamp da avaliação")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Timestamp de criação no ledger")

    # Processamento
    processing_time_ms: int = Field(..., description="Tempo de processamento")
    buffered: bool = Field(default=False, description="Se foi bufferizado por indisponibilidade")

    # Segurança e auditoria
    content_hash: str = Field(..., description="Hash SHA-256 do conteúdo")
    digital_signature: Optional[str] = Field(None, description="Assinatura digital do documento")
    signature_algorithm: Optional[str] = Field(None, description="Algoritmo de assinatura (RSA-SHA256, etc.)")

    # Compliance
    retention_policy: Optional[str] = Field(None, description="Política de retenção aplicada")
    masked_fields: List[str] = Field(default_factory=list, description="Campos mascarados por compliance")
    gdpr_consent: Optional[bool] = Field(None, description="Consentimento GDPR se aplicável")

    class Config:
        json_schema_extra = {
            "example": {
                "schema_version": "2.0.0",
                "opinion_id": "abc123...",
                "plan_id": "plan-001",
                "intent_id": "intent-001",
                "specialist_type": "technical",
                "specialist_version": "1.0.0",
                "opinion": {
                    "confidence_score": 0.85,
                    "risk_score": 0.3,
                    "recommendation": "approve",
                    "reasoning_summary": "Plano tecnicamente sólido",
                    "reasoning_factors": [],
                    "explainability_token": "token123",
                    "explainability": {},
                    "mitigations": [],
                    "metadata": {}
                },
                "correlation_id": "corr-001",
                "evaluated_at": "2025-10-10T12:00:00Z",
                "processing_time_ms": 150,
                "content_hash": "hash123...",
                "digital_signature": "sig123..."
            }
        }


class SchemaVersionManager:
    """Gerenciador de versões de schema."""

    CURRENT_VERSION = "2.0.0"
    SUPPORTED_VERSIONS = ["1.0.0", "2.0.0"]

    @staticmethod
    def is_version_compatible(version: str) -> bool:
        """
        Verifica se versão é suportada.

        Args:
            version: Versão do schema

        Returns:
            True se compatível
        """
        return version in SchemaVersionManager.SUPPORTED_VERSIONS

    @staticmethod
    def migrate_to_v2(v1_document: Dict[str, Any]) -> OpinionDocumentV2:
        """
        Migra documento v1 para v2.

        Args:
            v1_document: Documento na versão 1.0.0

        Returns:
            Documento migrado para v2
        """
        logger.info("Migrating opinion document from v1 to v2", opinion_id=v1_document.get('opinion_id'))

        # Extrair opinion de v1
        opinion = Opinion(
            confidence_score=v1_document['opinion']['confidence_score'],
            risk_score=v1_document['opinion']['risk_score'],
            recommendation=v1_document['opinion']['recommendation'],
            reasoning_summary=v1_document['opinion']['reasoning_summary'],
            reasoning_factors=[
                ReasoningFactor(**factor) for factor in v1_document['opinion'].get('reasoning_factors', [])
            ],
            explainability_token=v1_document['opinion']['explainability_token'],
            explainability=v1_document['opinion'].get('explainability', {}),
            mitigations=[
                Mitigation(**m) for m in v1_document['opinion'].get('mitigations', [])
            ],
            metadata=v1_document['opinion'].get('metadata', {})
        )

        # Criar documento v2
        v2_document = OpinionDocumentV2(
            schema_version="2.0.0",
            opinion_id=v1_document['opinion_id'],
            plan_id=v1_document['plan_id'],
            intent_id=v1_document['intent_id'],
            specialist_type=v1_document['specialist_type'],
            specialist_version=v1_document['specialist_version'],
            opinion=opinion,
            correlation_id=v1_document['correlation_id'],
            trace_id=v1_document.get('trace_id'),
            span_id=v1_document.get('span_id'),
            evaluated_at=v1_document['evaluated_at'],
            created_at=v1_document.get('created_at', datetime.utcnow()),
            processing_time_ms=v1_document['processing_time_ms'],
            buffered=v1_document.get('buffered', False),
            content_hash=v1_document.get('content_hash', ''),
            # Novos campos v2 com defaults
            digital_signature=None,
            signature_algorithm=None,
            retention_policy=None,
            masked_fields=[],
            gdpr_consent=None
        )

        return v2_document

    @staticmethod
    def validate_document(document: Dict[str, Any]) -> bool:
        """
        Valida documento contra schema.

        Args:
            document: Documento a validar

        Returns:
            True se válido
        """
        try:
            schema_version = document.get('schema_version', '1.0.0')

            if schema_version == '2.0.0':
                OpinionDocumentV2(**document)
                return True
            elif schema_version == '1.0.0':
                # Tentar migrar e validar
                migrated = SchemaVersionManager.migrate_to_v2(document)
                return True
            else:
                logger.error("Unsupported schema version", version=schema_version)
                return False

        except Exception as e:
            logger.error("Schema validation failed", error=str(e))
            return False
