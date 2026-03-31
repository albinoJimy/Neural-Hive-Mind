"""
Modelos de estado para coordenacao de Saga.

Define os modelos Pydantic para representar o estado de uma transacao
Saga distribuida com compensacao automatica.
"""
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, List, Any
from uuid import uuid4

from pydantic import BaseModel, Field, ConfigDict


class SagaStatus(str, Enum):
    """Status de uma Saga."""
    PENDING = 'PENDING'           # Criada, nao iniciada
    STARTED = 'STARTED'           # Iniciada, primeiro step executando
    IN_PROGRESS = 'IN_PROGRESS'   # Executando steps
    COMPLETED = 'COMPLETED'       # Todos steps completados com sucesso
    COMPENSATING = 'COMPENSATING' # Compensando steps executados
    COMPENSATED = 'COMPENSATED'   # Compensacao concluida
    FAILED = 'FAILED'             # Falha sem compensacao possivel


class SagaEventType(str, Enum):
    """Tipos de eventos de Saga."""
    saga_created = 'saga_created'
    saga_started = 'saga_started'
    saga_step_completed = 'saga_step_completed'
    saga_step_failed = 'saga_step_failed'
    saga_compensating = 'saga_compensating'
    saga_step_compensated = 'saga_step_compensated'
    saga_compensated = 'saga_compensated'
    saga_completed = 'saga_completed'
    saga_failed = 'saga_failed'


class StepStatus(str, Enum):
    """Status de um step individual de Saga."""
    PENDING = 'PENDING'
    IN_PROGRESS = 'IN_PROGRESS'
    COMPLETED = 'COMPLETED'
    FAILED = 'FAILED'
    COMPENSATING = 'COMPENSATING'
    COMPENSATED = 'COMPENSATED'
    SKIPPED = 'SKIPPED'


class SagaStep(BaseModel):
    """
    Representa um step individual dentro de uma Saga.

    Cada step tem uma acao principal e uma acao de compensacao
    que deve ser executada em caso de falha.
    """
    step_id: str = Field(..., description='ID unico do step (UUID)')
    name: str = Field(..., description='Nome descritivo do step')
    action: str = Field(..., description='Acao principal a executar')
    compensation_action: str = Field(
        ...,
        description='Acao de compensacao para reverter este step'
    )
    status: StepStatus = Field(
        default=StepStatus.PENDING,
        description='Status atual do step'
    )
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description='Parametros para a acao principal'
    )
    compensation_parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description='Parametros para a acao de compensacao'
    )
    result: Optional[Dict[str, Any]] = Field(
        default=None,
        description='Resultado da execucao da acao principal'
    )
    compensation_result: Optional[Dict[str, Any]] = Field(
        default=None,
        description='Resultado da execucao da compensacao'
    )
    error: Optional[str] = Field(
        default=None,
        description='Mensagem de erro se falhou'
    )
    created_at: int = Field(
        ...,
        description='Timestamp de criacao (millis)'
    )
    started_at: Optional[int] = Field(
        default=None,
        description='Timestamp de inicio (millis)'
    )
    completed_at: Optional[int] = Field(
        default=None,
        description='Timestamp de conclusao (millis)'
    )
    compensated_at: Optional[int] = Field(
        default=None,
        description='Timestamp de compensacao (millis)'
    )
    retry_count: int = Field(
        default=0,
        description='Numero de tentativas de execucao'
    )
    max_retries: int = Field(
        default=3,
        description='Numero maximo de tentativas'
    )

    model_config = ConfigDict(use_enum_values=True)

    def mark_started(self) -> None:
        """Marca step como iniciado."""
        self.status = StepStatus.IN_PROGRESS
        self.started_at = int(datetime.utcnow().timestamp() * 1000)

    def mark_completed(self, result: Optional[Dict[str, Any]] = None) -> None:
        """Marca step como completado com sucesso."""
        self.status = StepStatus.COMPLETED
        self.completed_at = int(datetime.utcnow().timestamp() * 1000)
        if result is not None:
            self.result = result

    def mark_failed(self, error: str) -> None:
        """Marca step como falhado."""
        self.status = StepStatus.FAILED
        self.error = error
        self.completed_at = int(datetime.utcnow().timestamp() * 1000)

    def mark_compensating(self) -> None:
        """Marca step como em compensacao."""
        self.status = StepStatus.COMPENSATING

    def mark_compensated(
        self,
        compensation_result: Optional[Dict[str, Any]] = None
    ) -> None:
        """Marca step como compensado."""
        self.status = StepStatus.COMPENSATED
        self.compensated_at = int(datetime.utcnow().timestamp() * 1000)
        if compensation_result is not None:
            self.compensation_result = compensation_result

    def can_retry(self) -> bool:
        """Verifica se step pode ser retentado."""
        return self.retry_count < self.max_retries

    def increment_retry(self) -> None:
        """Incrementa contador de retentativas."""
        self.retry_count += 1


class SagaState(BaseModel):
    """
    Representa o estado completo de uma transacao Saga.

    Uma Saga e composta por varios steps que devem ser executados
    sequencialmente. Se algum step falhar, os steps anteriores sao
    compensados em ordem reversa.
    """
    saga_id: str = Field(..., description='ID unico da Saga (UUID)')
    workflow_id: str = Field(
        ...,
        description='ID do workflow Temporal associado'
    )
    plan_id: str = Field(..., description='ID do Cognitive Plan')
    intent_id: str = Field(..., description='ID da intencao original')
    status: SagaStatus = Field(
        default=SagaStatus.PENDING,
        description='Status atual da Saga'
    )
    steps: List[SagaStep] = Field(
        default_factory=list,
        description='Steps da Saga em ordem de execucao'
    )
    compensation_order: List[str] = Field(
        default_factory=list,
        description='Ordem de compensacao (step IDs em ordem reversa)'
    )
    created_at: int = Field(
        ...,
        description='Timestamp de criacao (millis)'
    )
    started_at: Optional[int] = Field(
        default=None,
        description='Timestamp de inicio (millis)'
    )
    completed_at: Optional[int] = Field(
        default=None,
        description='Timestamp de conclusao (millis)'
    )
    compensated_at: Optional[int] = Field(
        default=None,
        description='Timestamp de compensacao concluida (millis)'
    )
    failed_at: Optional[int] = Field(
        default=None,
        description='Timestamp de falha (millis)'
    )
    current_step_index: int = Field(
        default=0,
        description='Indice do step atualmente sendo executado'
    )
    retry_count: int = Field(
        default=0,
        description='Numero de retentativas da Saga inteira'
    )
    max_retries: int = Field(
        default=1,
        description='Numero maximo de retentativas da Saga'
    )
    error: Optional[str] = Field(
        default=None,
        description='Mensagem de erro se falhou'
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description='Metadados adicionais'
    )

    model_config = ConfigDict(use_enum_values=True)

    def get_current_step(self) -> Optional[SagaStep]:
        """Retorna o step atual sendo executado."""
        if 0 <= self.current_step_index < len(self.steps):
            return self.steps[self.current_step_index]
        return None

    def get_completed_steps(self) -> List[SagaStep]:
        """Retorna todos os steps completados."""
        return [
            step for step in self.steps
            if step.status == StepStatus.COMPLETED
        ]

    def get_pending_steps(self) -> List[SagaStep]:
        """Retorna todos os steps pendentes."""
        return [
            step for step in self.steps
            if step.status == StepStatus.PENDING
        ]

    def get_compensation_order(self) -> List[SagaStep]:
        """
        Retorna steps na ordem de compensacao.

        Compensacao ocorre em ordem reversa da execucao,
        incluindo apenas steps que foram completados.
        """
        completed = self.get_completed_steps()
        return list(reversed(completed))

    def can_retry(self) -> bool:
        """Verifica se a Saga pode ser retentada."""
        return self.retry_count < self.max_retries

    def increment_retry(self) -> None:
        """Incrementa contador de retentativas da Saga."""
        self.retry_count += 1

    def reset_for_retry(self) -> None:
        """Reseta estado para nova tentativa."""
        self.status = SagaStatus.PENDING
        self.current_step_index = 0
        self.failed_at = None
        self.error = None
        for step in self.steps:
            if step.status in [StepStatus.FAILED, StepStatus.IN_PROGRESS]:
                step.status = StepStatus.PENDING
                step.started_at = None
                step.completed_at = None
                step.error = None


class SagaEvent(BaseModel):
    """
    Representa um evento de Saga para auditoria e tracing.

    Eventos sao gravados no MongoDB para permitir reconstrucao
    do historico da Saga.
    """
    event_id: str = Field(..., description='ID unico do evento (UUID)')
    saga_id: str = Field(..., description='ID da Saga associada')
    event_type: SagaEventType = Field(
        ...,
        description='Tipo do evento'
    )
    timestamp: int = Field(
        ...,
        description='Timestamp do evento (millis)'
    )
    data: Dict[str, Any] = Field(
        default_factory=dict,
        description='Dados adicionais do evento'
    )

    model_config = ConfigDict(use_enum_values=True)

    @classmethod
    def create(
        cls,
        saga_id: str,
        event_type: SagaEventType,
        data: Optional[Dict[str, Any]] = None
    ) -> 'SagaEvent':
        """
        Cria um novo evento de Saga.

        Args:
            saga_id: ID da Saga
            event_type: Tipo do evento
            data: Dados adicionais

        Returns:
            Nova instancia de SagaEvent
        """
        return cls(
            event_id=str(uuid4()),
            saga_id=saga_id,
            event_type=event_type,
            timestamp=int(datetime.utcnow().timestamp() * 1000),
            data=data or {}
        )
