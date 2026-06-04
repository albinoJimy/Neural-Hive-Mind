"""
Modelos de Dados para GDPR Right to Erasure
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, EmailStr


class ErasureStatus(str, Enum):
    """Status da solicitacao de exclusao"""

    PENDING_VERIFICATION = "pending_verification"
    VERIFIED = "verified"
    PROCESSING = "processing"
    PARTIALLY_COMPLETED = "partially_completed"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class ErasureScope(str, Enum):
    """Escopo da exclusao"""

    MINIMAL = "minimal"  # Apenas dados identificaveis diretos
    STANDARD = "standard"  # Dados identificaveis + associados
    FULL = "full"  # Todos os dados incluindo logs anonimizados


class DataType(str, Enum):
    """Tipos de dados a serem excluidos"""

    APPROVALS = "approvals"
    SPECIALIST_FEEDBACK = "specialist_feedback"
    CONTINUOUS_FEEDBACK = "continuous_feedback"
    CONSENSUS_HISTORY = "consensus_history"
    EXECUTION_TICKETS = "execution_tickets"
    MEMORY_ENTRIES = "memory_entries"
    INTENT_HISTORY = "intent_history"
    METRICS_LOGS = "metrics_logs"


class ServiceErasureResult(BaseModel):
    """Resultado da exclusao em um servico"""

    service: str = Field(..., description="Nome do servico")
    data_type: DataType = Field(..., description="Tipo de dados")
    status: Literal["success", "partial", "failed"] = Field(..., description="Status da exclusao")
    records_affected: int = Field(default=0, description="Quantidade de registros excluidos")
    error_message: Optional[str] = Field(None, description="Mensagem de erro se falhou")
    completed_at: Optional[datetime] = Field(None, description="Timestamp de conclusao")


class ErasureRequest(BaseModel):
    """Solicitacao de exclusao de dados"""

    request_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), description="ID unico da solicitacao"
    )
    user_id: str = Field(..., description="ID do usuario solicitante")
    email: EmailStr = Field(..., description="Email para verificacao")
    scope: ErasureScope = Field(default=ErasureScope.STANDARD, description="Escopo da exclusao")
    data_types: list[DataType] = Field(
        default_factory=list, description="Tipos de dados especificos a excluir"
    )
    reason: Optional[str] = Field(None, description="Motivo da solicitacao")
    status: ErasureStatus = Field(
        default=ErasureStatus.PENDING_VERIFICATION, description="Status atual"
    )
    verification_token: Optional[str] = Field(
        None, description="Token de verificacao enviado por email"
    )
    verified_at: Optional[datetime] = Field(None, description="Timestamp da verificacao")
    processing_started_at: Optional[datetime] = Field(
        None, description="Timestamp de inicio do processamento"
    )
    completed_at: Optional[datetime] = Field(None, description="Timestamp de conclusao")
    results: list[ServiceErasureResult] = Field(
        default_factory=list, description="Resultados por servico"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Timestamp de criacao"
    )
    expires_at: Optional[datetime] = Field(None, description="Timestamp de expiracao do token")

    model_config = ConfigDict(use_enum_values=True)


class ErasureRequestInput(BaseModel):
    """Input para criacao de solicitacao"""

    email: EmailStr = Field(..., description="Email para verificacao")
    scope: ErasureScope = Field(default=ErasureScope.STANDARD, description="Escopo da exclusao")
    data_types: list[DataType] = Field(
        default_factory=list, description="Tipos de dados especificos (vazio = todos)"
    )
    reason: Optional[str] = Field(None, max_length=500, description="Motivo da solicitacao")


class VerificationRequest(BaseModel):
    """Request para verificacao de solicitacao"""

    request_id: str = Field(..., description="ID da solicitacao")
    token: str = Field(..., min_length=32, max_length=64, description="Token de verificacao")


class ErasureStatusResponse(BaseModel):
    """Response com status da solicitacao"""

    request_id: str = Field(..., description="ID da solicitacao")
    status: ErasureStatus = Field(..., description="Status atual")
    scope: ErasureScope = Field(..., description="Escopo da solicitacao")
    data_types: list[DataType] = Field(..., description="Tipos de dados")
    created_at: datetime = Field(..., description="Data de criacao")
    verified_at: Optional[datetime] = Field(None, description="Data de verificacao")
    completed_at: Optional[datetime] = Field(None, description="Data de conclusao")
    results_summary: dict[str, int] = Field(
        default_factory=dict, description="Resumo dos resultados"
    )


class ErasureCommand(BaseModel):
    """Comando de exclusao para services"""

    command_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="ID do comando")
    request_id: str = Field(..., description="ID da solicitacao original")
    user_id: str = Field(..., description="ID do usuario")
    data_types: list[DataType] = Field(..., description="Tipos de dados a excluir")
    scope: ErasureScope = Field(..., description="Escopo da exclusao")
    target_service: str = Field(..., description="Servico alvo")
    issued_at: datetime = Field(default_factory=datetime.utcnow)

    def to_kafka_dict(self) -> dict[str, Any]:
        """Converte para dicionario compativel com Kafka"""
        return {
            "command_id": self.command_id,
            "request_id": self.request_id,
            "user_id": self.user_id,
            "data_types": [dt.value for dt in self.data_types],
            "scope": self.scope.value,
            "target_service": self.target_service,
            "issued_at": int(self.issued_at.timestamp() * 1000),
        }


class ErasureReport(BaseModel):
    """Relatorio de conclusao de exclusao"""

    report_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="ID do relatorio")
    command_id: str = Field(..., description="ID do comando original")
    request_id: str = Field(..., description="ID da solicitacao original")
    service: str = Field(..., description="Servico que executou")
    status: Literal["success", "partial", "failed"] = Field(..., description="Status")
    records_affected: int = Field(default=0, description="Registros afetados")
    error_message: Optional[str] = Field(None, description="Erro se falhou")
    completed_at: datetime = Field(default_factory=datetime.utcnow)
