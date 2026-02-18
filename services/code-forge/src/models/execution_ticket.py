from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class TaskType(str, Enum):
    """Tipos de tarefas de execução"""
    BUILD = 'BUILD'
    DEPLOY = 'DEPLOY'
    TEST = 'TEST'
    VALIDATE = 'VALIDATE'
    EXECUTE = 'EXECUTE'
    COMPENSATE = 'COMPENSATE'
    QUERY = 'QUERY'


class TicketStatus(str, Enum):
    """Status de um Execution Ticket"""
    PENDING = 'PENDING'
    RUNNING = 'RUNNING'
    COMPLETED = 'COMPLETED'
    FAILED = 'FAILED'
    COMPENSATING = 'COMPENSATING'
    COMPENSATED = 'COMPENSATED'


class Priority(str, Enum):
    """Prioridade de execução"""
    LOW = 'LOW'
    NORMAL = 'NORMAL'
    HIGH = 'HIGH'
    CRITICAL = 'CRITICAL'


class RiskBand(str, Enum):
    """Banda de risco"""
    LOW = 'low'
    MEDIUM = 'medium'
    HIGH = 'high'
    CRITICAL = 'critical'


class DeliveryMode(str, Enum):
    """Modo de entrega"""
    AT_MOST_ONCE = 'AT_MOST_ONCE'
    AT_LEAST_ONCE = 'AT_LEAST_ONCE'
    EXACTLY_ONCE = 'EXACTLY_ONCE'


class Consistency(str, Enum):
    """Nível de consistência"""
    EVENTUAL = 'EVENTUAL'
    STRONG = 'STRONG'


class Durability(str, Enum):
    """Durabilidade"""
    TRANSIENT = 'TRANSIENT'
    PERSISTENT = 'PERSISTENT'


class SecurityLevel(str, Enum):
    """Nível de segurança"""
    PUBLIC = 'PUBLIC'
    INTERNAL = 'INTERNAL'
    CONFIDENTIAL = 'CONFIDENTIAL'
    RESTRICTED = 'RESTRICTED'


class SLA(BaseModel):
    """Service Level Agreement"""
    deadline: datetime = Field(..., description='Prazo final de execução')
    timeout_ms: int = Field(..., description='Timeout em milissegundos', ge=0)
    max_retries: int = Field(..., description='Número máximo de tentativas', ge=0)


class QoS(BaseModel):
    """Quality of Service"""
    delivery_mode: DeliveryMode = Field(..., description='Modo de entrega')
    consistency: Consistency = Field(..., description='Nível de consistência')
    durability: Durability = Field(..., description='Durabilidade')


class ExecutionTicket(BaseModel):
    """Modelo Pydantic para Execution Ticket"""

    ticket_id: str = Field(..., description='Identificador único do ticket')
    plan_id: str = Field(..., description='ID do plano cognitivo')
    intent_id: str = Field(..., description='ID da intenção')
    decision_id: str = Field(..., description='ID da decisão')

    correlation_id: Optional[str] = Field(None, description='ID de correlação')
    trace_id: Optional[str] = Field(None, description='ID de trace OpenTelemetry')
    span_id: Optional[str] = Field(None, description='ID de span OpenTelemetry')

    task_type: TaskType = Field(..., description='Tipo de tarefa')
    status: TicketStatus = Field(..., description='Status atual do ticket')
    priority: Priority = Field(..., description='Prioridade de execução')

    risk_band: RiskBand = Field(..., description='Banda de risco')

    parameters: Dict[str, Any] = Field(default_factory=dict, description='Parâmetros da tarefa')

    sla: SLA = Field(..., description='Service Level Agreement')
    qos: QoS = Field(..., description='Quality of Service')

    security_level: SecurityLevel = Field(..., description='Nível de segurança')

    dependencies: list[str] = Field(default_factory=list, description='IDs de tickets dependentes')

    compensation_ticket_id: Optional[str] = Field(None, description='ID do ticket de compensação')

    created_at: datetime = Field(..., description='Timestamp de criação')
    updated_at: Optional[datetime] = Field(None, description='Timestamp de atualização')
    expires_at: Optional[datetime] = Field(None, description='Timestamp de expiração')

    metadata: Dict[str, str] = Field(default_factory=dict, description='Metadados adicionais')

    schema_version: int = Field(default=1, description='Versão do schema')

    def is_build_task(self) -> bool:
        """Verifica se é uma tarefa de BUILD"""
        return self.task_type == TaskType.BUILD

    def is_expired(self) -> bool:
        """Verifica se o ticket expirou"""
        if self.expires_at:
            return datetime.now() > self.expires_at
        return False

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário"""
        return self.model_dump()

    class Config:
        use_enum_values = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
