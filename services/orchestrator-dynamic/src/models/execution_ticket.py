"""
Modelo Pydantic para Execution Ticket.
Corresponde ao schema Avro execution-ticket.avsc.
"""
import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, List, Any

from pydantic import BaseModel, Field, field_validator


class TaskType(str, Enum):
    """Tipos de tarefa."""
    BUILD = 'BUILD'
    DEPLOY = 'DEPLOY'
    TEST = 'TEST'
    VALIDATE = 'VALIDATE'
    EXECUTE = 'EXECUTE'
    COMPENSATE = 'COMPENSATE'


class TicketStatus(str, Enum):
    """Status do ticket de execução."""
    PENDING = 'PENDING'
    RUNNING = 'RUNNING'
    COMPLETED = 'COMPLETED'
    FAILED = 'FAILED'
    COMPENSATING = 'COMPENSATING'
    COMPENSATED = 'COMPENSATED'


class Priority(str, Enum):
    """Prioridade de execução."""
    LOW = 'LOW'
    NORMAL = 'NORMAL'
    HIGH = 'HIGH'
    CRITICAL = 'CRITICAL'


class RiskBand(str, Enum):
    """Banda de risco."""
    low = 'low'
    medium = 'medium'
    high = 'high'
    critical = 'critical'


class SecurityLevel(str, Enum):
    """Nível de segurança."""
    PUBLIC = 'PUBLIC'
    INTERNAL = 'INTERNAL'
    CONFIDENTIAL = 'CONFIDENTIAL'
    RESTRICTED = 'RESTRICTED'


class DeliveryMode(str, Enum):
    """Modo de entrega."""
    AT_MOST_ONCE = 'AT_MOST_ONCE'
    AT_LEAST_ONCE = 'AT_LEAST_ONCE'
    EXACTLY_ONCE = 'EXACTLY_ONCE'


class Consistency(str, Enum):
    """Nível de consistência."""
    EVENTUAL = 'EVENTUAL'
    STRONG = 'STRONG'


class Durability(str, Enum):
    """Modo de durabilidade."""
    TRANSIENT = 'TRANSIENT'
    PERSISTENT = 'PERSISTENT'


class SLA(BaseModel):
    """Definições de SLA."""
    deadline: int = Field(..., description='Prazo limite (timestamp millis)')
    timeout_ms: int = Field(..., description='Timeout em milissegundos')
    max_retries: int = Field(..., description='Número máximo de tentativas')

    class Config:
        use_enum_values = True


class QoS(BaseModel):
    """Definições de Quality of Service."""
    delivery_mode: DeliveryMode = Field(..., description='Modo de entrega')
    consistency: Consistency = Field(..., description='Nível de consistência')
    durability: Durability = Field(..., description='Modo de durabilidade')

    class Config:
        use_enum_values = True


class ExecutionTicket(BaseModel):
    """
    Modelo de Execution Ticket.
    Representa uma unidade atômica de trabalho gerada pelo Orquestrador Dinâmico.
    """
    ticket_id: str = Field(..., description='UUID único do ticket')
    plan_id: str = Field(..., description='Referência ao Cognitive Plan')
    intent_id: str = Field(..., description='Referência à intenção original')
    decision_id: str = Field(..., description='Referência à Consolidated Decision')
    correlation_id: Optional[str] = Field(default=None, description='ID de correlação')
    trace_id: Optional[str] = Field(default=None, description='Trace ID OpenTelemetry')
    span_id: Optional[str] = Field(default=None, description='Span ID OpenTelemetry')
    task_id: str = Field(..., description='ID da tarefa no DAG')
    task_type: TaskType = Field(..., description='Tipo da tarefa')
    description: str = Field(..., description='Descrição da tarefa')
    dependencies: List[str] = Field(default_factory=list, description='Ticket IDs dependentes')
    status: TicketStatus = Field(default=TicketStatus.PENDING, description='Status do ticket')
    priority: Priority = Field(..., description='Prioridade de execução')
    risk_band: RiskBand = Field(..., description='Banda de risco')
    sla: SLA = Field(..., description='Definições de SLA')
    qos: QoS = Field(..., description='Definições de QoS')
    parameters: Dict[str, str] = Field(default_factory=dict, description='Parâmetros da tarefa')
    required_capabilities: List[str] = Field(default_factory=list, description='Capacidades necessárias')
    security_level: SecurityLevel = Field(..., description='Nível de segurança')
    created_at: int = Field(..., description='Timestamp de criação (millis)')
    started_at: Optional[int] = Field(default=None, description='Timestamp de início (millis)')
    completed_at: Optional[int] = Field(default=None, description='Timestamp de conclusão (millis)')
    estimated_duration_ms: Optional[int] = Field(default=None, description='Duração estimada')
    actual_duration_ms: Optional[int] = Field(default=None, description='Duração real')
    retry_count: int = Field(default=0, description='Contador de tentativas')
    error_message: Optional[str] = Field(default=None, description='Mensagem de erro')
    compensation_ticket_id: Optional[str] = Field(default=None, description='ID do ticket de compensação')
    metadata: Dict[str, str] = Field(default_factory=dict, description='Metadados adicionais')
    predictions: Optional[Dict[str, Any]] = Field(default=None, description='Predições ML (duração, recursos, anomalias)')
    schema_version: int = Field(default=1, description='Versão do schema')

    class Config:
        use_enum_values = True
        json_encoders = {
            datetime: lambda v: int(v.timestamp() * 1000)
        }

    @field_validator('dependencies')
    @classmethod
    def validate_dependencies(cls, v, info):
        """Valida que dependencies não contém auto-referência."""
        if 'ticket_id' in info.data and info.data['ticket_id'] in v:
            raise ValueError('Ticket não pode depender de si mesmo')
        return v

    @field_validator('completed_at')
    @classmethod
    def validate_completed_at(cls, v, info):
        """Valida que completed_at > started_at."""
        if v is not None and 'started_at' in info.data and info.data['started_at'] is not None:
            if v <= info.data['started_at']:
                raise ValueError('completed_at deve ser maior que started_at')
        return v

    def to_avro_dict(self) -> Dict:
        """
        Converte para dicionário compatível com Avro.

        Returns:
            Dicionário com enums como strings e timestamps como int
        """
        data = self.model_dump()

        # Converter enums para strings
        data['task_type'] = self.task_type.value
        data['status'] = self.status.value
        data['priority'] = self.priority.value
        data['risk_band'] = self.risk_band.value
        data['security_level'] = self.security_level.value

        # Converter SLA
        data['sla'] = {
            'deadline': self.sla.deadline,
            'timeout_ms': self.sla.timeout_ms,
            'max_retries': self.sla.max_retries
        }

        # Converter QoS
        data['qos'] = {
            'delivery_mode': self.qos.delivery_mode.value,
            'consistency': self.qos.consistency.value,
            'durability': self.qos.durability.value
        }

        # Incluir predictions se presente
        if self.predictions is not None:
            data['predictions'] = self.predictions

        return data

    @classmethod
    def from_avro_dict(cls, data: Dict) -> 'ExecutionTicket':
        """
        Cria instância a partir de dicionário Avro.

        Args:
            data: Dicionário com dados do Avro

        Returns:
            Instância de ExecutionTicket
        """
        # Converter SLA
        if 'sla' in data and isinstance(data['sla'], dict):
            data['sla'] = SLA(**data['sla'])

        # Converter QoS
        if 'qos' in data and isinstance(data['qos'], dict):
            data['qos'] = QoS(**data['qos'])

        return cls(**data)

    def calculate_hash(self) -> str:
        """
        Calcula hash SHA-256 para integridade.

        Returns:
            Hash hexadecimal
        """
        # Criar dicionário ordenado para hash consistente
        data = self.to_avro_dict()
        json_str = json.dumps(data, sort_keys=True)
        return hashlib.sha256(json_str.encode()).hexdigest()

    def is_expired(self) -> bool:
        """
        Verifica se deadline foi ultrapassado.

        Returns:
            True se expirado, False caso contrário
        """
        current_time_ms = int(datetime.now().timestamp() * 1000)
        return current_time_ms > self.sla.deadline

    def can_retry(self) -> bool:
        """
        Verifica se ainda pode fazer retry.

        Returns:
            True se pode retry, False caso contrário
        """
        return self.retry_count < self.sla.max_retries

    def calculate_sla_remaining_seconds(self) -> float:
        """
        Calcula tempo restante de SLA em segundos.

        Returns:
            Segundos restantes (pode ser negativo se expirado)
        """
        current_time_ms = int(datetime.now().timestamp() * 1000)
        remaining_ms = self.sla.deadline - current_time_ms
        return remaining_ms / 1000.0

    def is_sla_critical(self, threshold_percent: float = 0.8) -> bool:
        """
        Verifica se SLA está em nível crítico.

        Args:
            threshold_percent: Threshold para considerar crítico (padrão 80%)

        Returns:
            True se crítico, False caso contrário
        """
        if self.started_at is None:
            return False

        elapsed_ms = int(datetime.now().timestamp() * 1000) - self.started_at
        sla_consumed_percent = elapsed_ms / self.sla.timeout_ms

        return sla_consumed_percent >= threshold_percent
