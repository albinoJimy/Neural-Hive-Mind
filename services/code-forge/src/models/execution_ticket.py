from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TaskType(str, Enum):
    """Tipos de tarefas de execução"""

    BUILD = "BUILD"
    DEPLOY = "DEPLOY"
    TEST = "TEST"
    VALIDATE = "VALIDATE"
    EXECUTE = "EXECUTE"
    COMPENSATE = "COMPENSATE"
    QUERY = "QUERY"
    TRANSFORM = "TRANSFORM"


class TicketStatus(str, Enum):
    """Status de um Execution Ticket"""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    COMPENSATING = "COMPENSATING"
    COMPENSATED = "COMPENSATED"


class Priority(str, Enum):
    """Prioridade de execução"""

    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RiskBand(str, Enum):
    """Banda de risco"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DeliveryMode(str, Enum):
    """Modo de entrega"""

    AT_MOST_ONCE = "AT_MOST_ONCE"
    AT_LEAST_ONCE = "AT_LEAST_ONCE"
    EXACTLY_ONCE = "EXACTLY_ONCE"


class Consistency(str, Enum):
    """Nível de consistência"""

    EVENTUAL = "EVENTUAL"
    STRONG = "STRONG"


class Durability(str, Enum):
    """Durabilidade"""

    TRANSIENT = "TRANSIENT"
    PERSISTENT = "PERSISTENT"


class SecurityLevel(str, Enum):
    """Nível de segurança"""

    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    RESTRICTED = "RESTRICTED"


class SLA(BaseModel):
    """Service Level Agreement"""

    deadline: datetime = Field(..., description="Prazo final de execução")
    timeout_ms: int = Field(..., description="Timeout em milissegundos", ge=0)
    max_retries: int = Field(..., description="Número máximo de tentativas", ge=0)


class QoS(BaseModel):
    """Quality of Service"""

    delivery_mode: DeliveryMode = Field(..., description="Modo de entrega")
    consistency: Consistency = Field(..., description="Nível de consistência")
    durability: Durability = Field(..., description="Durabilidade")


class ExecutionTicket(BaseModel):
    """Modelo Pydantic para Execution Ticket"""

    @model_validator(mode="before")
    @classmethod
    def _normalize_legacy_contract(cls, data: Any) -> Any:
        """Normaliza tickets legados para o contrato canónico (Fase 2 j3-build-generate).

        Tolera, sem rejeitar (evita partir tickets em voo / DLQ):
        - ``task_type`` minúsculo (ex.: 'transform') -> MAIÚSCULAS
        - ``priority`` inteiro legado 1-10 -> enum string (1-2 LOW, 3-5 NORMAL,
          6-8 HIGH, 9-10 CRITICAL; valores fora do intervalo são limitados);
          ``priority`` string minúscula -> MAIÚSCULAS.

        Valores genuinamente desconhecidos continuam a falhar na validação do
        enum (anti-verde-falso: normaliza-se, não se inventa).
        """
        if not isinstance(data, dict):
            return data
        data = dict(data)  # cópia rasa: não mutar o dict do chamador

        task_type = data.get("task_type")
        if isinstance(task_type, str):
            data["task_type"] = task_type.upper()

        priority = data.get("priority")
        # bool é subclasse de int: não interpretar True/False como prioridade.
        if isinstance(priority, bool):
            pass
        elif isinstance(priority, int):
            if priority <= 2:
                data["priority"] = "LOW"
            elif priority <= 5:
                data["priority"] = "NORMAL"
            elif priority <= 8:
                data["priority"] = "HIGH"
            else:
                data["priority"] = "CRITICAL"
        elif isinstance(priority, str):
            data["priority"] = priority.upper()

        return data

    ticket_id: str = Field(..., description="Identificador único do ticket")
    plan_id: Optional[str] = Field(None, description="ID do plano cognitivo")
    intent_id: Optional[str] = Field(None, description="ID da intenção")
    decision_id: Optional[str] = Field(None, description="ID da decisão")

    correlation_id: Optional[str] = Field(None, description="ID de correlação")
    trace_id: Optional[str] = Field(None, description="ID de trace OpenTelemetry")
    span_id: Optional[str] = Field(None, description="ID de span OpenTelemetry")

    task_type: TaskType = Field(..., description="Tipo de tarefa")
    status: TicketStatus = Field(..., description="Status atual do ticket")
    priority: Priority = Field(..., description="Prioridade de execução")

    risk_band: RiskBand = Field(..., description="Banda de risco")

    parameters: dict[str, Any] = Field(default_factory=dict, description="Parâmetros da tarefa")

    sla: SLA = Field(..., description="Service Level Agreement")
    qos: QoS = Field(..., description="Quality of Service")

    security_level: SecurityLevel = Field(..., description="Nível de segurança")

    dependencies: list[str] = Field(default_factory=list, description="IDs de tickets dependentes")

    compensation_ticket_id: Optional[str] = Field(None, description="ID do ticket de compensação")

    created_at: datetime = Field(..., description="Timestamp de criação")
    updated_at: Optional[datetime] = Field(None, description="Timestamp de atualização")
    expires_at: Optional[datetime] = Field(None, description="Timestamp de expiração")

    metadata: dict[str, str] = Field(default_factory=dict, description="Metadados adicionais")

    schema_version: int = Field(default=1, description="Versão do schema")

    def is_build_task(self) -> bool:
        """Verifica se é uma tarefa de BUILD"""
        return self.task_type == TaskType.BUILD

    def is_expired(self) -> bool:
        """Verifica se o ticket expirou"""
        if self.expires_at:
            return datetime.now() > self.expires_at
        return False

    def to_dict(self) -> dict[str, Any]:
        """Converte para dicionário"""
        return self.model_dump()

    model_config = ConfigDict(use_enum_values=True)
