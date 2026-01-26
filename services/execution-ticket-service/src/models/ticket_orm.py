"""
SQLAlchemy ORM model para persistência de Execution Tickets em PostgreSQL.

Este módulo define o modelo ORM que mapeia a tabela 'execution_tickets' do banco
de dados PostgreSQL para objetos Python, permitindo conversão bidirecional entre
instâncias ORM (banco) e Pydantic (aplicação).

Imports:
    - ExecutionTicket, SLA, QoS: importados via importação relativa do __init__.py
      que carrega dinamicamente os modelos Pydantic compartilhados do orchestrator-dynamic
"""
from datetime import datetime
from typing import Optional, Dict, List
from sqlalchemy import (
    Column, BigInteger, String, Text, Integer, TIMESTAMP,
    CheckConstraint, Index
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base

from . import ExecutionTicket, SLA, QoS

Base = declarative_base()


def _get_enum_value(val) -> str:
    """
    Extrai valor de enum de forma segura.
    
    Com Pydantic ConfigDict(use_enum_values=True), os valores podem vir
    já como strings em vez de objetos Enum. Esta função trata ambos os casos.
    
    Args:
        val: Valor que pode ser um Enum ou uma string
        
    Returns:
        String com o valor
    """
    return val.value if hasattr(val, 'value') else str(val)


class TicketORM(Base):
    """Modelo ORM para tabela execution_tickets."""

    __tablename__ = 'execution_tickets'
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'COMPENSATING', 'COMPENSATED')",
            name='chk_status'
        ),
        CheckConstraint('retry_count >= 0', name='chk_retry_count'),
        CheckConstraint('completed_at IS NULL OR completed_at >= started_at', name='chk_completed_after_started'),
        Index('idx_ticket_id', 'ticket_id', unique=True),
        Index('idx_plan_id', 'plan_id'),
        Index('idx_intent_id', 'intent_id'),
        Index('idx_status', 'status'),
        Index('idx_created_at', 'created_at'),
        Index('idx_status_priority', 'status', 'priority'),
        {'schema': 'public'}
    )

    # Campos
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    ticket_id = Column(String(36), unique=True, nullable=False)
    plan_id = Column(String(36), nullable=False)
    intent_id = Column(String(36), nullable=False)
    decision_id = Column(String(36), nullable=False)
    correlation_id = Column(String(36), nullable=True)
    trace_id = Column(String(64), nullable=True)
    span_id = Column(String(32), nullable=True)
    task_id = Column(String(255), nullable=False)
    task_type = Column(String(20), nullable=False)
    description = Column(Text, nullable=False)
    dependencies = Column(JSONB, default=[], nullable=False)
    status = Column(String(20), default='PENDING', nullable=False)
    priority = Column(String(20), nullable=False)
    risk_band = Column(String(20), nullable=False)
    sla = Column(JSONB, nullable=False)
    qos = Column(JSONB, nullable=False)
    parameters = Column(JSONB, default={}, nullable=False)
    required_capabilities = Column(JSONB, default=[], nullable=False)
    security_level = Column(String(20), nullable=False)
    created_at = Column(TIMESTAMP, nullable=False)
    started_at = Column(TIMESTAMP, nullable=True)
    completed_at = Column(TIMESTAMP, nullable=True)
    estimated_duration_ms = Column(BigInteger, nullable=True)
    actual_duration_ms = Column(BigInteger, nullable=True)
    retry_count = Column(Integer, default=0, nullable=False)
    error_message = Column(Text, nullable=True)
    compensation_ticket_id = Column(String(36), nullable=True)
    ticket_metadata = Column('metadata', JSONB, default={}, nullable=False)
    schema_version = Column(Integer, default=1, nullable=False)
    hash = Column(String(64), nullable=True)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_pydantic(self) -> ExecutionTicket:
        """
        Converte ORM para modelo Pydantic ExecutionTicket.

        Returns:
            Instância de ExecutionTicket
        """
        # Converter timestamps para millis
        created_at_ms = int(self.created_at.timestamp() * 1000)
        started_at_ms = int(self.started_at.timestamp() * 1000) if self.started_at else None
        completed_at_ms = int(self.completed_at.timestamp() * 1000) if self.completed_at else None

        # Reconstruir SLA
        sla = SLA(**self.sla)

        # Reconstruir QoS
        qos = QoS(**self.qos)

        return ExecutionTicket(
            ticket_id=self.ticket_id,
            plan_id=self.plan_id,
            intent_id=self.intent_id,
            decision_id=self.decision_id,
            correlation_id=self.correlation_id,
            trace_id=self.trace_id,
            span_id=self.span_id,
            task_id=self.task_id,
            task_type=self.task_type,
            description=self.description,
            dependencies=self.dependencies,
            status=self.status,
            priority=self.priority,
            risk_band=self.risk_band,
            sla=sla,
            qos=qos,
            parameters=self.parameters,
            required_capabilities=self.required_capabilities,
            security_level=self.security_level,
            created_at=created_at_ms,
            started_at=started_at_ms,
            completed_at=completed_at_ms,
            estimated_duration_ms=self.estimated_duration_ms,
            actual_duration_ms=self.actual_duration_ms,
            retry_count=self.retry_count,
            error_message=self.error_message,
            compensation_ticket_id=self.compensation_ticket_id,
            metadata=self.ticket_metadata,
            schema_version=self.schema_version
        )

    @classmethod
    def from_pydantic(cls, ticket: ExecutionTicket) -> 'TicketORM':
        """
        Cria ORM a partir de modelo Pydantic ExecutionTicket.

        Args:
            ticket: Instância de ExecutionTicket

        Returns:
            Instância de TicketORM
        """
        # Converter timestamps millis para datetime
        created_at = datetime.fromtimestamp(ticket.created_at / 1000.0)
        started_at = datetime.fromtimestamp(ticket.started_at / 1000.0) if ticket.started_at else None
        completed_at = datetime.fromtimestamp(ticket.completed_at / 1000.0) if ticket.completed_at else None

        # Converter SLA para dict
        sla_dict = {
            'deadline': ticket.sla.deadline,
            'timeout_ms': ticket.sla.timeout_ms,
            'max_retries': ticket.sla.max_retries
        }

        # Converter QoS para dict (usando helper para suportar enum ou string)
        qos_dict = {
            'delivery_mode': _get_enum_value(ticket.qos.delivery_mode),
            'consistency': _get_enum_value(ticket.qos.consistency),
            'durability': _get_enum_value(ticket.qos.durability)
        }

        # Calcular hash
        ticket_hash = ticket.calculate_hash()

        return cls(
            ticket_id=ticket.ticket_id,
            plan_id=ticket.plan_id,
            intent_id=ticket.intent_id,
            decision_id=ticket.decision_id,
            correlation_id=ticket.correlation_id,
            trace_id=ticket.trace_id,
            span_id=ticket.span_id,
            task_id=ticket.task_id,
            task_type=_get_enum_value(ticket.task_type),
            description=ticket.description,
            dependencies=ticket.dependencies,
            status=_get_enum_value(ticket.status),
            priority=_get_enum_value(ticket.priority),
            risk_band=_get_enum_value(ticket.risk_band),
            sla=sla_dict,
            qos=qos_dict,
            parameters=ticket.parameters,
            required_capabilities=ticket.required_capabilities,
            security_level=_get_enum_value(ticket.security_level),
            created_at=created_at,
            started_at=started_at,
            completed_at=completed_at,
            estimated_duration_ms=ticket.estimated_duration_ms,
            actual_duration_ms=ticket.actual_duration_ms,
            retry_count=ticket.retry_count,
            error_message=ticket.error_message,
            compensation_ticket_id=ticket.compensation_ticket_id,
            metadata=ticket.metadata,
            schema_version=ticket.schema_version,
            hash=ticket_hash
        )
