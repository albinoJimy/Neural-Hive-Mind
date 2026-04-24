"""
Modelos de Dados para Continuous Feedback (EPIC 3.3 - FASE 0 IA/ML Integration)

Define os modelos Pydantic para o fluxo de feedback continuo para treinamento ML.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class FeedbackType(str, Enum):
    """Tipo de feedback"""

    APPROVAL = "approval"
    PREDICTION = "prediction"
    CORRECTION = "correction"


class ContinuousFeedbackRequest(BaseModel):
    """Request de feedback continuo recebido via API"""

    prediction_id: str = Field(..., description="ID unico da predicao ML")
    prediction: str = Field(..., description="Predicao do modelo (approve/reject)")
    actual_result: str = Field(
        ..., description="Resultado real observado (approve/reject)"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Timestamp da observacao"
    )
    intent_text: Optional[str] = Field(
        None, description="Texto original da intenção para extracao de features NLP"
    )
    plan_id: Optional[str] = Field(None, description="ID do plano (opcional)")
    user_id: Optional[str] = Field(None, description="ID do usuario que observou")
    confidence: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Confianca da predicao original"
    )
    model_version: Optional[str] = Field(None, description="Versao do modelo usada")
    features: Optional[dict[str, Any]] = Field(
        None, description="Features adicionais do contexto"
    )

    model_config = ConfigDict(use_enum_values=True)


class ContinuousFeedbackResponse(BaseModel):
    """Response de feedback continuo para API"""

    feedback_id: str = Field(..., description="ID do feedback criado")
    prediction_id: str = Field(..., description="ID da predicao")
    enrolled: bool = Field(..., description="Se foi enfileirado para treinamento")
    nlp_features_enriched: bool = Field(
        ..., description="Se features NLP foram extraidas e incluidas"
    )
    kafka_published: bool = Field(..., description="Se publicado no Kafka")
    created_at: datetime = Field(..., description="Timestamp de criacao")


class TrainingDataKafkaMessage(BaseModel):
    """Mensagem Kafka para dados de treinamento ML"""

    prediction_id: str = Field(..., description="ID unico da predicao")
    prediction: str = Field(..., description="Predicao do modelo")
    actual_result: str = Field(..., description="Resultado real observado")
    timestamp: datetime = Field(..., description="Timestamp da observacao")
    intent_text: Optional[str] = Field(None, description="Texto da intencao")
    nlp_features: Optional[dict[str, Any]] = Field(
        None, description="Features NLP extraidas do texto"
    )
    plan_id: Optional[str] = Field(None, description="ID do plano")
    user_id: Optional[str] = Field(None, description="ID do usuario")
    confidence: Optional[float] = Field(None, description="Confianca da predicao")
    model_version: Optional[str] = Field(None, description="Versao do modelo")
    features: Optional[dict[str, Any]] = Field(None, description="Features adicionais")

    def to_kafka_dict(self) -> dict[str, Any]:
        """Converte para dicionario compativel com Kafka"""
        return {
            "prediction_id": self.prediction_id,
            "prediction": self.prediction,
            "actual_result": self.actual_result,
            "timestamp": int(self.timestamp.timestamp() * 1000),
            "intent_text": self.intent_text,
            "nlp_features": self.nlp_features,
            "plan_id": self.plan_id,
            "user_id": self.user_id,
            "confidence": self.confidence,
            "model_version": self.model_version,
            "features": self.features,
        }


class ContinuousFeedbackStats(BaseModel):
    """Estatisticas de feedback continuo"""

    total_feedbacks: int = Field(..., description="Total de feedbacks coletados")
    approvals_correct: int = Field(..., description="Predicoes approve corretas")
    approvals_incorrect: int = Field(..., description="Predicoes approve incorretas")
    rejections_correct: int = Field(..., description="Predicoes reject corretas")
    rejections_incorrect: int = Field(..., description="Predicoes reject incorretas")
    accuracy: float = Field(..., description="Acuracia geral (0-1)")
    avg_confidence: Optional[float] = Field(None, description="Confianca media")
    with_nlp_features: int = Field(
        ..., description="Feedbacks com features NLP enriquecidas"
    )
