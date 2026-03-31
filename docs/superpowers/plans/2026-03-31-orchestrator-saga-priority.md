# Orchestrator Saga Avançada e Priorização Dinâmica — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Completar o Orchestrator Dynamic implementando Saga Pattern avançado e Priorização Dinâmica para elevar a completude de 85% para 100%.

**Architecture:**
- Saga Coordinator com estado persistente no MongoDB e eventos no Kafka
- Priority Queues com 4 níveis (CRITICAL, HIGH, NORMAL, LOW) e round-robin com peso
- Dynamic Re-prioritization baseada em eventos SLA
- Preemption Manager para preempção de tickets de baixa prioridade
- Adaptive Priority Calculator com ajuste baseado em histórico

**Tech Stack:** Python 3.12+, Temporal, MongoDB, Kafka, pytest

---

## Task 1: ORCH-01 - Saga Coordinator Core

**Files:**
- Create: `services/orchestrator-dynamic/src/saga/__init__.py`
- Create: `services/orchestrator-dynamic/src/saga/saga_state.py`
- Create: `services/orchestrator-dynamic/src/saga/saga_event_store.py`
- Create: `services/orchestrator-dynamic/src/saga/saga_repository.py`
- Create: `services/orchestrator-dynamic/src/saga/saga_orchestrator.py`
- Test: `services/orchestrator-dynamic/tests/unit/saga/test_saga_orchestrator.py`

- [ ] **Step 1: Create saga module structure**

```python
# services/orchestrator-dynamic/src/saga/__init__.py
"""
Saga Pattern implementation for distributed transaction coordination.

Provides:
- SagaOrchestrator: Coordinates multi-step transactions with compensation
- SagaState: Persistent state model for saga instances
- SagaEventStore: Event sourcing for saga events
- SagaRepository: MongoDB persistence for saga state
"""

from .saga_state import SagaState, SagaStep, SagaStatus
from .saga_orchestrator import SagaOrchestrator
from .saga_repository import SagaRepository
from .saga_event_store import SagaEventStore, SagaEvent

__all__ = [
    'SagaState',
    'SagaStep',
    'SagaStatus',
    'SagaOrchestrator',
    'SagaRepository',
    'SagaEventStore',
    'SagaEvent',
]
```

- [ ] **Step 2: Create SagaState model**

```python
# services/orchestrator-dynamic/src/saga/saga_state.py
"""
Saga state model for persistent saga coordination.
"""
from datetime import datetime
from enum import Enum
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class SagaStatus(str, Enum):
    """Estados possíveis de uma saga."""
    PENDING = "pending"
    STARTED = "started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    COMPENSATING = "compensating"
    COMPENSATED = "compensated"
    FAILED = "failed"


class SagaStep(BaseModel):
    """Representa um passo individual da saga."""
    step_id: str = Field(..., description="Unique step identifier")
    name: str = Field(..., description="Step name")
    action: str = Field(..., description="Action to execute")
    compensation_action: Optional[str] = Field(None, description="Compensation action")
    status: SagaStatus = Field(default=SagaStatus.PENDING, description="Step status")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = Field(None, description="Completion timestamp")
    compensating_at: Optional[datetime] = Field(None, description="Compensation start timestamp")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Action parameters")
    result: Optional[Dict[str, Any]] = Field(None, description="Execution result")
    error: Optional[str] = Field(None, description="Error message if failed")


class SagaState(BaseModel):
    """
    Estado persistente de uma saga.

    Armazenado no MongoDB para recuperação e coordenação distribuída.
    """
    saga_id: str = Field(..., description="Unique saga identifier")
    workflow_id: str = Field(..., description="Associated workflow ID")
    plan_id: Optional[str] = Field(None, description="Associated plan ID")
    intent_id: Optional[str] = Field(None, description="Associated intent ID")

    status: SagaStatus = Field(default=SagaStatus.PENDING, description="Current saga status")
    steps: List[SagaStep] = Field(default_factory=list, description="Saga steps")

    # Compensation order (topological reverse)
    compensation_order: List[str] = Field(
        default_factory=list,
        description="Step IDs in compensation order"
    )

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = Field(None, description="Saga start timestamp")
    completed_at: Optional[datetime] = Field(None, description="Saga completion timestamp")
    failed_at: Optional[datetime] = Field(None, description="Saga failure timestamp")

    # Retry tracking
    current_step_index: int = Field(default=0, description="Current step being executed")
    retry_count: int = Field(default=0, description="Number of retries attempted")
    max_retries: int = Field(default=3, description="Maximum retry attempts")

    # Error tracking
    last_error: Optional[str] = Field(None, description="Last error message")
    error_step_id: Optional[str] = Field(None, description="Step ID that caused error")

    class Config:
        collection_name = "saga_states"


class SagaEvent(BaseModel):
    """Evento de saga para event sourcing."""
    event_id: str = Field(..., description="Unique event identifier")
    saga_id: str = Field(..., description="Associated saga ID")
    event_type: str = Field(..., description="Event type (saga_created, saga_started, etc.)")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    data: Dict[str, Any] = Field(default_factory=dict, description="Event data")

    class Config:
        collection_name = "saga_events"
```

- [ ] **Step 3: Create SagaEventStore**

```python
# services/orchestrator-dynamic/src/saga/saga_event_store.py
"""
Event store for saga events using MongoDB.
"""
import structlog
from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from .saga_state import SagaEvent, SagaStatus

logger = structlog.get_logger(__name__)


class SagaEventStore:
    """
    Armazena e recupera eventos de saga.

    Implementa event sourcing para rastreabilidade completa
    de execuções de saga.
    """

    EVENT_TYPES = [
        "saga_created",
        "saga_started",
        "saga_step_started",
        "saga_step_completed",
        "saga_step_failed",
        "saga_compensating",
        "saga_step_compensated",
        "saga_compensated",
        "saga_completed",
        "saga_failed",
    ]

    def __init__(self, mongodb_client):
        """
        Inicializa o event store.

        Args:
            mongodb_client: Cliente MongoDB para persistência
        """
        self.mongodb = mongodb_client
        self.logger = logger.bind(component="saga_event_store")
        self._collection = None

    async def _get_collection(self):
        """Lazy load da coleção MongoDB."""
        if self._collection is None:
            self._collection = self.mongodb.db[SagaEvent.Config.collection_name]
            # Criar índices
            await self._collection.create_index([("saga_id", 1)])
            await self._collection.create_index([("timestamp", -1)])
            await self._collection.create_index([("event_type", 1)])
        return self._collection

    async def record_event(
        self,
        saga_id: str,
        event_type: str,
        data: dict
    ) -> SagaEvent:
        """
        Registra um novo evento de saga.

        Args:
            saga_id: ID da saga
            event_type: Tipo do evento
            data: Dados do evento

        Returns:
            SagaEvent criado
        """
        if event_type not in self.EVENT_TYPES:
            self.logger.warning(
                "unknown_event_type",
                saga_id=saga_id,
                event_type=event_type
            )

        event = SagaEvent(
            event_id=str(uuid4()),
            saga_id=saga_id,
            event_type=event_type,
            timestamp=datetime.utcnow(),
            data=data
        )

        collection = await self._get_collection()
        await collection.insert_one(event.dict())

        self.logger.debug(
            "saga_event_recorded",
            saga_id=saga_id,
            event_type=event_type,
            event_id=event.event_id
        )

        return event

    async def get_saga_events(self, saga_id: str) -> List[SagaEvent]:
        """
        Recupera todos os eventos de uma saga.

        Args:
            saga_id: ID da saga

        Returns:
            Lista de eventos ordenada por timestamp
        """
        collection = await self._get_collection()
        cursor = collection.find({"saga_id": saga_id}).sort("timestamp", 1)
        events = [SagaEvent(**doc) async for doc in cursor]
        return events

    async def get_events_by_type(
        self,
        event_type: str,
        limit: int = 100
    ) -> List[SagaEvent]:
        """
        Recupera eventos por tipo.

        Args:
            event_type: Tipo do evento
            limit: Número máximo de eventos

        Returns:
            Lista de eventos
        """
        collection = await self._get_collection()
        cursor = collection.find(
            {"event_type": event_type}
        ).sort("timestamp", -1).limit(limit)
        events = [SagaEvent(**doc) async for doc in cursor]
        return events
```

- [ ] **Step 4: Create SagaRepository**

```python
# services/orchestrator-dynamic/src/saga/saga_repository.py
"""
Repository for saga state persistence using MongoDB.
"""
import structlog
from typing import List, Optional
from datetime import datetime

from .saga_state import SagaState, SagaStatus
from motor.motor_asyncio import AsyncIOMotorClient

logger = structlog.get_logger(__name__)


class SagaRepository:
    """
    Repositório para persistência de estado de saga.

    Fornece operações CRUD para SagaState no MongoDB.
    """

    def __init__(self, mongodb_client):
        """
        Inicializa o repositório.

        Args:
            mongodb_client: Cliente MongoDB com motor
        """
        self.mongodb = mongodb_client
        self.logger = logger.bind(component="saga_repository")
        self._collection = None

    async def _get_collection(self):
        """Lazy load da coleção."""
        if self._collection is None:
            self._collection = self.mongodb.db[SagaState.Config.collection_name]
            # Criar índices
            await self._collection.create_index([("saga_id", 1)], unique=True)
            await self._collection.create_index([("workflow_id", 1)])
            await self._collection.create_index([("status", 1)])
            await self._collection.create_index([("created_at", -1)])
        return self._collection

    async def save(self, saga_state: SagaState) -> SagaState:
        """
        Salva ou actualiza estado de saga.

        Args:
            saga_state: Estado a salvar

        Returns:
            Estado salvo
        """
        collection = await self._get_collection()
        await collection.update_one(
            {"saga_id": saga_state.saga_id},
            {"$set": saga_state.dict()},
            upsert=True
        )

        self.logger.debug(
            "saga_state_saved",
            saga_id=saga_state.saga_id,
            status=saga_state.status
        )

        return saga_state

    async def find_by_id(self, saga_id: str) -> Optional[SagaState]:
        """
        Busca saga por ID.

        Args:
            saga_id: ID da saga

        Returns:
            SagaState ou None
        """
        collection = await self._get_collection()
        doc = await collection.find_one({"saga_id": saga_id})
        return SagaState(**doc) if doc else None

    async def find_by_workflow(self, workflow_id: str) -> Optional[SagaState]:
        """
        Busca saga por workflow ID.

        Args:
            workflow_id: ID do workflow

        Returns:
            SagaState ou None
        """
        collection = await self._get_collection()
        doc = await collection.find_one({"workflow_id": workflow_id})
        return SagaState(**doc) if doc else None

    async def find_by_status(
        self,
        status: SagaStatus,
        limit: int = 50
    ) -> List[SagaState]:
        """
        Busca sagas por status.

        Args:
            status: Status a filtrar
            limit: Limite de resultados

        Returns:
            Lista de SagaState
        """
        collection = await self._get_collection()
        cursor = collection.find(
            {"status": status}
        ).sort("created_at", -1).limit(limit)
        return [SagaState(**doc) async for doc in cursor]

    async def update_status(
        self,
        saga_id: str,
        status: SagaStatus,
        timestamp: Optional[datetime] = None
    ) -> bool:
        """
        Actualiza status da saga.

        Args:
            saga_id: ID da saga
            status: Novo status
            timestamp: Timestamp da mudança (default: now)

        Returns:
            True se actualizado
        """
        collection = await self._get_collection()
        update_data = {"status": status}

        if status == SagaStatus.STARTED:
            update_data["started_at"] = timestamp or datetime.utcnow()
        elif status == SagaStatus.COMPLETED:
            update_data["completed_at"] = timestamp or datetime.utcnow()
        elif status == SagaStatus.FAILED:
            update_data["failed_at"] = timestamp or datetime.utcnow()

        result = await collection.update_one(
            {"saga_id": saga_id},
            {"$set": update_data}
        )

        return result.modified_count > 0
```

- [ ] **Step 5: Create SagaOrchestrator**

```python
# services/orchestrator-dynamic/src/saga/saga_orchestrator.py
"""
Saga orchestrator for distributed transaction coordination.
"""
import structlog
from datetime import datetime
from typing import List, Dict, Any, Optional
from uuid import uuid4

from .saga_state import SagaState, SagaStep, SagaStatus
from .saga_repository import SagaRepository
from .saga_event_store import SagaEventStore

logger = structlog.get_logger(__name__)


class SagaOrchestrator:
    """
    Coordenador de saga para transacções distribuídas.

    Gerencia a execução de multi-passos com compensação
    automática em caso de falha.
    """

    def __init__(
        self,
        repository: SagaRepository,
        event_store: SagaEventStore
    ):
        """
        Inicializa o orquestrador.

        Args:
            repository: Repositório para persistência
            event_store: Event store para event sourcing
        """
        self.repository = repository
        self.event_store = event_store
        self.logger = logger.bind(component="saga_orchestrator")

    async def create_saga(
        self,
        workflow_id: str,
        plan_id: Optional[str],
        intent_id: Optional[str],
        steps: List[Dict[str, Any]]
    ) -> SagaState:
        """
        Cria uma nova saga.

        Args:
            workflow_id: ID do workflow associado
            plan_id: ID do plano associado
            intent_id: ID da intenção associada
            steps: Lista de passos (dict com name, action, compensation_action, parameters)

        Returns:
            SagaState criada
        """
        saga_id = str(uuid4())

        # Criar steps a partir da definição
        saga_steps = []
        compensation_order = []

        for i, step_def in enumerate(steps):
            step_id = step_def.get("step_id", f"step_{i}")
            saga_step = SagaStep(
                step_id=step_id,
                name=step_def.get("name", step_id),
                action=step_def["action"],
                compensation_action=step_def.get("compensation_action"),
                parameters=step_def.get("parameters", {})
            )
            saga_steps.append(saga_step)
            compensation_order.append(step_id)

        # Ordem de compensação é reversa
        compensation_order.reverse()

        saga_state = SagaState(
            saga_id=saga_id,
            workflow_id=workflow_id,
            plan_id=plan_id,
            intent_id=intent_id,
            status=SagaStatus.PENDING,
            steps=saga_steps,
            compensation_order=compensation_order
        )

        # Persistir
        await self.repository.save(saga_state)

        # Registrar evento
        await self.event_store.record_event(
            saga_id=saga_id,
            event_type="saga_created",
            data={
                "workflow_id": workflow_id,
                "step_count": len(saga_steps)
            }
        )

        self.logger.info(
            "saga_created",
            saga_id=saga_id,
            workflow_id=workflow_id,
            step_count=len(saga_steps)
        )

        return saga_state

    async def start_saga(self, saga_id: str) -> SagaState:
        """
        Inicia a execução de uma saga.

        Args:
            saga_id: ID da saga

        Returns:
            SagaState actualizado
        """
        saga_state = await self.repository.find_by_id(saga_id)
        if not saga_state:
            raise ValueError(f"Saga not found: {saga_id}")

        saga_state.status = SagaStatus.STARTED
        saga_state.started_at = datetime.utcnow()

        await self.repository.save(saga_state)
        await self.event_store.record_event(
            saga_id=saga_id,
            event_type="saga_started",
            data={"started_at": saga_state.started_at.isoformat()}
        )

        self.logger.info("saga_started", saga_id=saga_id)

        return saga_state

    async def complete_step(
        self,
        saga_id: str,
        step_id: str,
        result: Dict[str, Any]
    ) -> SagaState:
        """
        Marca um passo como completado.

        Args:
            saga_id: ID da saga
            step_id: ID do passo
            result: Resultado da execução

        Returns:
            SagaState actualizado
        """
        saga_state = await self.repository.find_by_id(saga_id)
        if not saga_state:
            raise ValueError(f"Saga not found: {saga_id}")

        # Encontrar e actualizar step
        for step in saga_state.steps:
            if step.step_id == step_id:
                step.status = SagaStatus.COMPLETED
                step.completed_at = datetime.utcnow()
                step.result = result
                break

        # Avançar para próximo step
        saga_state.current_step_index += 1

        # Verificar se todos completaram
        if all(s.status == SagaStatus.COMPLETED for s in saga_state.steps):
            saga_state.status = SagaStatus.COMPLETED
            saga_state.completed_at = datetime.utcnow()

            await self.event_store.record_event(
                saga_id=saga_id,
                event_type="saga_completed",
                data={"completed_at": saga_state.completed_at.isoformat()}
            )
        else:
            saga_state.status = SagaStatus.IN_PROGRESS
            await self.event_store.record_event(
                saga_id=saga_id,
                event_type="saga_step_completed",
                data={"step_id": step_id, "result": result}
            )

        await self.repository.save(saga_state)

        return saga_state

    async def fail_step(
        self,
        saga_id: str,
        step_id: str,
        error: str
    ) -> SagaState:
        """
        Marca um passo como falhado e inicia compensação.

        Args:
            saga_id: ID da saga
            step_id: ID do passo
            error: Mensagem de erro

        Returns:
            SagaState actualizado
        """
        saga_state = await self.repository.find_by_id(saga_id)
        if not saga_state:
            raise ValueError(f"Saga not found: {saga_id}")

        # Encontrar e actualizar step
        for step in saga_state.steps:
            if step.step_id == step_id:
                step.status = SagaStatus.FAILED
                step.error = error
                break

        saga_state.status = SagaStatus.COMPENSATING
        saga_state.last_error = error
        saga_state.error_step_id = step_id

        await self.event_store.record_event(
            saga_id=saga_id,
            event_type="saga_step_failed",
            data={"step_id": step_id, "error": error}
        )

        await self.event_store.record_event(
            saga_id=saga_id,
            event_type="saga_compensating",
            data={"reason": f"Step {step_id} failed"}
        )

        await self.repository.save(saga_state)

        self.logger.warning(
            "saga_compensating",
            saga_id=saga_id,
            failed_step=step_id,
            error=error
        )

        return saga_state

    async def compensate_step(
        self,
        saga_id: str,
        step_id: str
    ) -> SagaState:
        """
        Marca um passo como compensado.

        Args:
            saga_id: ID da saga
            step_id: ID do passo

        Returns:
            SagaState actualizado
        """
        saga_state = await self.repository.find_by_id(saga_id)
        if not saga_state:
            raise ValueError(f"Saga not found: {saga_id}")

        for step in saga_state.steps:
            if step.step_id == step_id:
                step.status = SagaStatus.COMPENSATED
                step.compensating_at = datetime.utcnow()
                break

        # Verificar se todos os passos foram compensados
        if all(
            s.status in [SagaStatus.COMPENSATED, SagaStatus.PENDING]
            for s in saga_state.steps
        ):
            saga_state.status = SagaStatus.COMPENSATED

            await self.event_store.record_event(
                saga_id=saga_id,
                event_type="saga_compensated",
                data={"compensated_at": datetime.utcnow().isoformat()}
            )
        else:
            await self.event_store.record_event(
                saga_id=saga_id,
                event_type="saga_step_compensated",
                data={"step_id": step_id}
            )

        await self.repository.save(saga_state)

        return saga_state

    async def get_saga_state(self, saga_id: str) -> Optional[SagaState]:
        """
        Retorna estado actual da saga.

        Args:
            saga_id: ID da saga

        Returns:
            SagaState ou None
        """
        return await self.repository.find_by_id(saga_id)
```

- [ ] **Step 6: Write unit tests**

```python
# services/orchestrator-dynamic/tests/unit/saga/test_saga_orchestrator.py
"""
Unit tests for SagaOrchestrator.
"""
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from src.saga.saga_orchestrator import SagaOrchestrator
from src.saga.saga_state import SagaState, SagaStatus


@pytest.fixture
def mock_repository():
    repo = AsyncMock()
    repo.save = AsyncMock(return_value=None)
    repo.find_by_id = AsyncMock()
    return repo


@pytest.fixture
def mock_event_store():
    store = AsyncMock()
    store.record_event = AsyncMock()
    return store


@pytest.fixture
def orchestrator(mock_repository, mock_event_store):
    return SagaOrchestrator(mock_repository, mock_event_store)


@pytest.mark.asyncio
async def test_create_saga(orchestrator, mock_repository):
    """Test creating a new saga."""
    steps = [
        {"name": "step1", "action": "build", "parameters": {"repo": "test"}},
        {"name": "step2", "action": "deploy", "parameters": {"env": "prod"}}
    ]

    saga = await orchestrator.create_saga(
        workflow_id="wf-123",
        plan_id="plan-456",
        intent_id="intent-789",
        steps=steps
    )

    assert saga.status == SagaStatus.PENDING
    assert saga.workflow_id == "wf-123"
    assert len(saga.steps) == 2
    assert len(saga.compensation_order) == 2
    assert saga.compensation_order == ["step1", "step0"]  # Reversed
    assert mock_repository.save.called


@pytest.mark.asyncio
async def test_start_saga(orchestrator, mock_repository):
    """Test starting a saga."""
    saga = SagaState(
        saga_id="saga-123",
        workflow_id="wf-123",
        status=SagaStatus.PENDING,
        steps=[]
    )
    mock_repository.find_by_id = AsyncMock(return_value=saga)

    result = await orchestrator.start_saga("saga-123")

    assert result.status == SagaStatus.STARTED
    assert result.started_at is not None
    assert mock_repository.save.called


@pytest.mark.asyncio
async def test_complete_step(orchestrator, mock_repository):
    """Test completing a step."""
    from src.saga.saga_state import SagaStep

    step1 = SagaStep(step_id="step1", name="step1", action="build")
    step2 = SagaStep(step_id="step2", name="step2", action="deploy")

    saga = SagaState(
        saga_id="saga-123",
        workflow_id="wf-123",
        status=SagaStatus.IN_PROGRESS,
        steps=[step1, step2],
        current_step_index=0
    )
    mock_repository.find_by_id = AsyncMock(return_value=saga)

    result = await orchestrator.complete_step(
        "saga-123",
        "step1",
        {"status": "success"}
    )

    assert result.current_step_index == 1
    assert result.steps[0].status == SagaStatus.COMPLETED
    assert result.steps[0].result == {"status": "success"}


@pytest.mark.asyncio
async def test_fail_step_triggers_compensation(orchestrator, mock_repository):
    """Test that failing a step triggers compensation."""
    from src.saga.saga_state import SagaStep

    step1 = SagaStep(step_id="step1", name="step1", action="build")
    saga = SagaState(
        saga_id="saga-123",
        workflow_id="wf-123",
        status=SagaStatus.IN_PROGRESS,
        steps=[step1]
    )
    mock_repository.find_by_id = AsyncMock(return_value=saga)

    result = await orchestrator.fail_step("saga-123", "step1", "Build failed")

    assert result.status == SagaStatus.COMPENSATING
    assert result.last_error == "Build failed"
    assert result.error_step_id == "step1"


@pytest.mark.asyncio
async def test_get_saga_state(orchestrator, mock_repository):
    """Test retrieving saga state."""
    saga = SagaState(
        saga_id="saga-123",
        workflow_id="wf-123",
        steps=[]
    )
    mock_repository.find_by_id = AsyncMock(return_value=saga)

    result = await orchestrator.get_saga_state("saga-123")

    assert result.saga_id == "saga-123"
```

- [ ] **Step 7: Run tests to verify**

Run: `pytest services/orchestrator-dynamic/tests/unit/saga/test_saga_orchestrator.py -v`
Expected: All 5 tests passing

- [ ] **Step 8: Commit**

```bash
git add services/orchestrator-dynamic/src/saga/ services/orchestrator-dynamic/tests/unit/saga/
git commit -m "feat(orchestrator): implement saga coordinator core

- SagaState, SagaStep, SagaStatus models
- SagaEventStore for event sourcing
- SagaRepository for MongoDB persistence
- SagaOrchestrator with create/start/complete/fail/compensate
- 5 unit tests

Refs: ORCH-01"
```

---

## Task 2: ORCH-02 - Saga Retry Configuration

**Files:**
- Create: `services/orchestrator-dynamic/src/saga/retry_config.py`
- Create: `services/orchestrator-dynamic/src/saga/retry_policy.py`
- Modify: `services/orchestrator-dynamic/src/activities/compensation.py`
- Test: `services/orchestrator-dynamic/tests/unit/saga/test_retry_policy.py`

- [ ] **Step 1: Create SagaRetryConfig**

```python
# services/orchestrator-dynamic/src/saga/retry_config.py
"""
Retry configuration for saga compensation with exponential backoff.
"""
from pydantic import BaseModel, Field
from typing import Optional


class SagaRetryConfig(BaseModel):
    """
    Configuração de retry para compensação de saga.

    Implementa backoff exponencial com jitter para evitar
    thundering herd em compensações em massa.
    """
    max_attempts: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Número máximo de tentativas de compensação"
    )
    initial_delay_ms: int = Field(
        default=1000,
        ge=100,
        description="Delay inicial em milissegundos"
    )
    max_delay_ms: int = Field(
        default=30000,
        ge=1000,
        description="Delay máximo em milissegundos"
    )
    multiplier: float = Field(
        default=2.0,
        ge=1.0,
        le=5.0,
        description="Multiplicador para backoff exponencial"
    )
    jitter: bool = Field(
        default=True,
        description="Adiciona jitter aleatório para evitar sincronização"
    )
    jitter_factor: float = Field(
        default=0.1,
        ge=0.0,
        le=0.5,
        description="Factor de jitter (±jitter_factor * delay)"
    )

    def get_delay(self, attempt: int) -> int:
        """
        Calcula delay para uma tentativa.

        Args:
            attempt: Número da tentativa (1-based)

        Returns:
            Delay em milissegundos
        """
        if attempt < 1:
            attempt = 1

        # Backoff exponencial: initial_delay * (multiplier ^ (attempt - 1))
        exponential_delay = self.initial_delay_ms * (
            self.multiplier ** (attempt - 1)
        )

        # Limitar ao máximo
        delay = min(exponential_delay, self.max_delay_ms)

        # Adicionar jitter se configurado
        if self.jitter:
            import random
            jitter_range = delay * self.jitter_factor
            jitter = random.uniform(-jitter_range, jitter_range)
            delay = int(delay + jitter)

        return max(delay, 0)

    def should_retry(self, attempt: int, error: Optional[str] = None) -> bool:
        """
        Determina se deve tentar novamente.

        Args:
            attempt: Número da tentativa actual
            error: Mensagem de erro (para verificar se é retryable)

        Returns:
            True se deve tentar novamente
        """
        if attempt >= self.max_attempts:
            return False

        # Erros não-retryable
        non_retryable_errors = [
            "validation_error",
            "schema_error",
            "permission_denied",
            "not_found"
        ]

        if error:
            error_lower = error.lower()
            for non_retryable in non_retryable_errors:
                if non_retryable in error_lower:
                    return False

        return True
```

- [ ] **Step 2: Create RetryPolicy**

```python
# services/orchestrator-dynamic/src/saga/retry_policy.py
"""
Retry policy for executing saga actions with automatic retries.
"""
import structlog
import asyncio
from typing import Callable, TypeVar, Optional
from datetime import datetime

from .retry_config import SagaRetryConfig

logger = structlog.get_logger(__name__)

T = TypeVar('T')


class RetryPolicy:
    """
    Política de retry para execução de acções de saga.

    Executa uma função com retries automáticos usando
    backoff exponencial configurável.
    """

    def __init__(self, config: Optional[SagaRetryConfig] = None):
        """
        Inicializa a política de retry.

        Args:
            config: Configuração de retry (default: SagaRetryConfig())
        """
        self.config = config or SagaRetryConfig()
        self.logger = logger.bind(component="retry_policy")

    async def execute(
        self,
        func: Callable[..., T],
        *args,
        operation_name: str = "unknown",
        **kwargs
    ) -> T:
        """
        Executa função com retries automáticos.

        Args:
            func: Função a executar (deve ser async)
            *args: Argumentos posicionais
            operation_name: Nome da operação para logs
            **kwargs: Argumentos nomeados

        Returns:
            Resultado da função

        Raises:
            Exception: Última exceção após esgotar retries
        """
        last_exception = None

        for attempt in range(1, self.config.max_attempts + 1):
            try:
                self.logger.debug(
                    "retry_policy_attempt",
                    operation=operation_name,
                    attempt=attempt,
                    max_attempts=self.config.max_attempts
                )

                result = await func(*args, **kwargs)

                if attempt > 1:
                    self.logger.info(
                        "retry_policy_success",
                        operation=operation_name,
                        attempt=attempt
                    )

                return result

            except Exception as e:
                last_exception = e
                error_msg = str(e)

                self.logger.warning(
                    "retry_policy_failed",
                    operation=operation_name,
                    attempt=attempt,
                    error=error_msg
                )

                # Verificar se deve tentar novamente
                if not self.config.should_retry(attempt, error_msg):
                    self.logger.error(
                        "retry_policy_non_retryable",
                        operation=operation_name,
                        error=error_msg
                    )
                    raise

                # Calcular delay e esperar
                if attempt < self.config.max_attempts:
                    delay_ms = self.config.get_delay(attempt)
                    delay_s = delay_ms / 1000.0

                    self.logger.debug(
                        "retry_policy_waiting",
                        operation=operation_name,
                        delay_ms=delay_ms,
                        next_attempt=attempt + 1
                    )

                    await asyncio.sleep(delay_s)

        # Todos os retries esgotados
        self.logger.error(
            "retry_policy_exhausted",
            operation=operation_name,
            attempts=self.config.max_attempts,
            final_error=str(last_exception)
        )

        raise last_exception

    def get_retry_count(self, started_at: datetime) -> int:
        """
        Estima número de retries baseado no tempo decorrido.

        Args:
            started_at: Timestamp de início

        Returns:
            Número estimado de tentativas
        """
        elapsed_ms = int(
            (datetime.utcnow() - started_at).total_seconds() * 1000
        )

        # Resolver attempt tal que get_delay(attempt) ~= elapsed_ms
        # initial_delay * multiplier^(attempt-1) = elapsed
        # multiplier^(attempt-1) = elapsed / initial_delay
        # attempt-1 = log(elapsed/initial_delay) / log(multiplier)

        if elapsed_ms < self.config.initial_delay_ms:
            return 1

        import math
        attempt = 1 + math.log(
            elapsed_ms / self.config.initial_delay_ms,
            self.config.multiplier
        )

        return int(min(attempt, self.config.max_attempts))
```

- [ ] **Step 3: Integrate with compensate_ticket activity**

```python
# Adicionar em services/orchestrator-dynamic/src/activities/compensation.py

# No início do ficheiro, adicionar:
from src.saga.retry_config import SagaRetryConfig
from src.saga.retry_policy import RetryPolicy

# Actualizar a função compensate_ticket para usar retry policy:

@activity.defn
async def compensate_ticket(
    ticket: Dict[str, Any],
    reason: str,
    retry_config: Optional[Dict[str, Any]] = None
) -> str:
    """
    Cria e publica ticket de compensação para reverter operacao falhada.

    Suporta retries automáticos com backoff exponencial.

    Args:
        ticket: Ticket original que falhou
        reason: Motivo da compensação
        retry_config: Configuração de retry opcional (max_attempts, delays, etc.)

    Returns:
        ID do ticket de compensacao criado
    """
    global _config, _kafka_producer, _mongodb_client, _metrics

    config = _config or get_settings()

    # Criar configuração de retry
    if retry_config:
        saga_retry_config = SagaRetryConfig(**retry_config)
    else:
        saga_retry_config = SagaRetryConfig()  # Defaults

    # Criar política de retry
    retry_policy = RetryPolicy(saga_retry_config)

    # Função interna de compensação
    async def _do_compensate():
        # ... (código existente de compensação)
        # Manter o código actual de criação de ticket aqui
        ...

    # Executar com retries
    return await retry_policy.execute(
        _do_compensate,
        operation_name=f"compensate_{ticket.get('ticket_id', 'unknown')}"
    )
```

- [ ] **Step 4: Write unit tests**

```python
# services/orchestrator-dynamic/tests/unit/saga/test_retry_policy.py
"""
Unit tests for RetryPolicy and SagaRetryConfig.
"""
import pytest
import asyncio

from src.saga.retry_config import SagaRetryConfig
from src.saga.retry_policy import RetryPolicy


def test_retry_config_defaults():
    """Test default retry configuration."""
    config = SagaRetryConfig()

    assert config.max_attempts == 3
    assert config.initial_delay_ms == 1000
    assert config.max_delay_ms == 30000
    assert config.multiplier == 2.0
    assert config.jitter is True


def test_retry_config_get_delay():
    """Test delay calculation."""
    config = SagaRetryConfig(
        initial_delay_ms=1000,
        multiplier=2.0,
        max_delay_ms=10000,
        jitter=False
    )

    assert config.get_delay(1) == 1000
    assert config.get_delay(2) == 2000
    assert config.get_delay(3) == 4000
    assert config.get_delay(4) == 8000
    assert config.get_delay(5) == 10000  # Capped at max


def test_retry_config_jitter():
    """Test jitter is applied."""
    config = SagaRetryConfig(
        initial_delay_ms=1000,
        jitter=True,
        jitter_factor=0.1
    )

    delay1 = config.get_delay(1)
    delay2 = config.get_delay(1)

    # Com jitter, delays devem ser diferentes
    assert delay1 != delay2
    # Mas próximos do valor base
    assert 900 <= delay1 <= 1100
    assert 900 <= delay2 <= 1100


def test_retry_config_should_retry():
    """Test retry decision logic."""
    config = SagaRetryConfig(max_attempts=3)

    assert config.should_retry(1, "temporary_error") is True
    assert config.should_retry(2, "temporary_error") is True
    assert config.should_retry(3, "temporary_error") is False

    # Non-retryable errors
    assert config.should_retry(1, "validation_error: invalid schema") is False
    assert config.should_retry(1, "permission_denied") is False
    assert config.should_retry(1, "resource_not_found") is False


@pytest.mark.asyncio
async def test_retry_policy_success_on_first_attempt():
    """Test successful execution on first try."""
    policy = RetryPolicy()

    async def success_func():
        return "result"

    result = await policy.execute(success_func, operation_name="test")

    assert result == "result"


@pytest.mark.asyncio
async def test_retry_policy_retries_then_succeeds():
    """Test retries then succeeds."""
    policy = RetryPolicy(SagaRetryConfig(
        initial_delay_ms=10,
        multiplier=2.0,
        max_attempts=3,
        jitter=False
    ))

    attempt_count = 0

    async def flaky_func():
        nonlocal attempt_count
        attempt_count += 1
        if attempt_count < 3:
            raise ValueError("temporary failure")
        return "success"

    result = await policy.execute(flaky_func, operation_name="test")

    assert result == "success"
    assert attempt_count == 3


@pytest.mark.asyncio
async def test_retry_policy_fails_after_max_attempts():
    """Test failure after max attempts."""
    policy = RetryPolicy(SagaRetryConfig(
        initial_delay_ms=10,
        multiplier=2.0,
        max_attempts=3,
        jitter=False
    ))

    async def failing_func():
        raise ValueError("persistent failure")

    with pytest.raises(ValueError, match="persistent failure"):
        await policy.execute(failing_func, operation_name="test")


@pytest.mark.asyncio
async def test_retry_policy_non_retryable_fails_immediately():
    """Test non-retryable errors fail immediately."""
    policy = RetryPolicy()

    attempt_count = 0

    async def validation_func():
        nonlocal attempt_count
        attempt_count += 1
        raise ValueError("validation_error: invalid schema")

    with pytest.raises(ValueError):
        await policy.execute(validation_func, operation_name="test")

    # Should fail on first attempt for non-retryable
    assert attempt_count == 1
```

- [ ] **Step 5: Run tests**

Run: `pytest services/orchestrator-dynamic/tests/unit/saga/test_retry_policy.py -v`
Expected: All 9 tests passing

- [ ] **Step 6: Commit**

```bash
git add services/orchestrator-dynamic/src/saga/retry_*.py services/orchestrator-dynamic/src/activities/compensation.py services/orchestrator-dynamic/tests/unit/saga/test_retry_policy.py
git commit -m "feat(orchestrator): implement saga retry with exponential backoff

- SagaRetryConfig with max_attempts, delays, multiplier, jitter
- RetryPolicy with automatic retries for async functions
- Integration with compensate_ticket activity
- 9 unit tests

Refs: ORCH-02"
```

---

## Task 3: ORCH-03 - Saga Events Integration

**Files:**
- Create: `services/orchestrator-dynamic/src/saga/saga_producer.py`
- Create: `services/orchestrator-dynamic/src/saga/saga_metrics.py`
- Modify: `services/orchestrator-dynamic/src/workflows/orchestration_workflow.py`
- Test: `services/orchestrator-dynamic/tests/integration/test_saga_events.py`

- [ ] **Step 1: Create SagaProducer**

```python
# services/orchestrator-dynamic/src/saga/saga_producer.py
"""
Kafka producer for saga events.
"""
import structlog
from typing import Dict, Any, Optional
from datetime import datetime

from src.saga.saga_state import SagaState, SagaStatus

logger = structlog.get_logger(__name__)


class SagaProducer:
    """
    Producer de eventos Kafka para saga.

    Publica eventos no tópico saga.events para
    consumo por serviços de observabilidade e auditoria.
    """

    TOPIC = "saga.events"

    def __init__(self, kafka_producer):
        """
        Inicializa o producer.

        Args:
            kafka_producer: KafkaProducerClient existente
        """
        self.kafka = kafka_producer
        self.logger = logger.bind(component="saga_producer")

    async def publish_saga_created(self, saga: SagaState) -> bool:
        """Publica evento saga_created."""
        return await self._publish_event(
            saga_id=saga.saga_id,
            event_type="saga_created",
            data={
                "workflow_id": saga.workflow_id,
                "plan_id": saga.plan_id,
                "intent_id": saga.intent_id,
                "step_count": len(saga.steps),
                "created_at": saga.created_at.isoformat()
            }
        )

    async def publish_saga_started(self, saga: SagaState) -> bool:
        """Publica evento saga_started."""
        return await self._publish_event(
            saga_id=saga.saga_id,
            event_type="saga_started",
            data={
                "workflow_id": saga.workflow_id,
                "started_at": saga.started_at.isoformat() if saga.started_at else None
            }
        )

    async def publish_saga_step_completed(
        self,
        saga_id: str,
        step_id: str,
        step_name: str,
        result: Dict[str, Any]
    ) -> bool:
        """Publica evento saga_step_completed."""
        return await self._publish_event(
            saga_id=saga_id,
            event_type="saga_step_completed",
            data={
                "step_id": step_id,
                "step_name": step_name,
                "result": result,
                "timestamp": datetime.utcnow().isoformat()
            }
        )

    async def publish_saga_step_failed(
        self,
        saga_id: str,
        step_id: str,
        step_name: str,
        error: str
    ) -> bool:
        """Publica evento saga_step_failed."""
        return await self._publish_event(
            saga_id=saga_id,
            event_type="saga_step_failed",
            data={
                "step_id": step_id,
                "step_name": step_name,
                "error": error,
                "timestamp": datetime.utcnow().isoformat()
            }
        )

    async def publish_saga_compensating(
        self,
        saga_id: str,
        reason: str,
        failed_step_id: Optional[str] = None
    ) -> bool:
        """Publica evento saga_compensating."""
        return await self._publish_event(
            saga_id=saga_id,
            event_type="saga_compensating",
            data={
                "reason": reason,
                "failed_step_id": failed_step_id,
                "timestamp": datetime.utcnow().isoformat()
            }
        )

    async def publish_saga_compensated(
        self,
        saga: SagaState
    ) -> bool:
        """Publica evento saga_compensated."""
        return await self._publish_event(
            saga_id=saga.saga_id,
            event_type="saga_compensated",
            data={
                "workflow_id": saga.workflow_id,
                "compensated_at": datetime.utcnow().isoformat(),
                "steps_compensated": len([
                    s for s in saga.steps
                    if s.status == SagaStatus.COMPENSATED
                ])
            }
        )

    async def publish_saga_completed(
        self,
        saga: SagaState
    ) -> bool:
        """Publica evento saga_completed."""
        return await self._publish_event(
            saga_id=saga.saga_id,
            event_type="saga_completed",
            data={
                "workflow_id": saga.workflow_id,
                "completed_at": saga.completed_at.isoformat() if saga.completed_at else None,
                "total_steps": len(saga.steps)
            }
        )

    async def publish_saga_failed(
        self,
        saga: SagaState,
        final_error: str
    ) -> bool:
        """Publica evento saga_failed."""
        return await self._publish_event(
            saga_id=saga.saga_id,
            event_type="saga_failed",
            data={
                "workflow_id": saga.workflow_id,
                "error": final_error,
                "failed_step_id": saga.error_step_id,
                "timestamp": datetime.utcnow().isoformat()
            }
        )

    async def _publish_event(
        self,
        saga_id: str,
        event_type: str,
        data: Dict[str, Any]
    ) -> bool:
        """
        Publica evento no Kafka.

        Args:
            saga_id: ID da saga
            event_type: Tipo do evento
            data: Dados do evento

        Returns:
            True se publicado com sucesso
        """
        event = {
            "saga_id": saga_id,
            "event_type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            "data": data
        }

        try:
            await self.kafka.produce(
                topic=self.TOPIC,
                key=saga_id.encode(),
                value=event
            )

            self.logger.debug(
                "saga_event_published",
                saga_id=saga_id,
                event_type=event_type
            )

            return True

        except Exception as e:
            self.logger.error(
                "saga_event_publish_failed",
                saga_id=saga_id,
                event_type=event_type,
                error=str(e)
            )
            return False
```

- [ ] **Step 2: Create SagaMetrics**

```python
# services/orchestrator-dynamic/src/saga/saga_metrics.py
"""
Metrics for saga orchestration.
"""
import structlog
from typing import Optional
from datetime import datetime, timedelta

logger = structlog.get_logger(__name__)


class SagaMetrics:
    """
    Coletor de métricas para saga orchestration.

    Rastreia contadores, durações e taxas de sucesso/falha.
    """

    def __init__(self, metrics_client: Optional[Any] = None):
        """
        Inicializa o coletor de métricas.

        Args:
            metrics_client: Cliente de métricas (Prometheus, etc.)
        """
        self.metrics = metrics_client
        self.logger = logger.bind(component="saga_metrics")

        # Contadores locais
        self._counters = {
            "saga_created": 0,
            "saga_started": 0,
            "saga_completed": 0,
            "saga_failed": 0,
            "saga_compensating": 0,
            "saga_compensated": 0,
            "step_completed": 0,
            "step_failed": 0,
        }

    def increment(self, metric_name: str, value: int = 1, tags: dict = None):
        """
        Incrementa um contador.

        Args:
            metric_name: Nome da métrica
            value: Valor a incrementar (default: 1)
            tags: Tags opcionais
        """
        if metric_name in self._counters:
            self._counters[metric_name] += value

        # Enviar para sistema de métricas se disponível
        if self.metrics:
            try:
                self.metrics.increment(
                    f"saga_{metric_name}",
                    value=value,
                    tags=tags or {}
                )
            except Exception as e:
                self.logger.warning(
                    "metric_increment_failed",
                    metric=metric_name,
                    error=str(e)
                )

    def record_duration(
        self,
        operation: str,
        duration_ms: int,
        tags: dict = None
    ):
        """
        Registra duração de operação.

        Args:
            operation: Nome da operação
            duration_ms: Duração em milissegundos
            tags: Tags opcionais
        """
        if self.metrics:
            try:
                self.metrics.histogram(
                    f"saga_{operation}_duration_ms",
                    value=duration_ms,
                    tags=tags or {}
                )
            except Exception as e:
                self.logger.warning(
                    "metric_duration_failed",
                    operation=operation,
                    error=str(e)
                )

    def get_counters(self) -> dict:
        """Retorna cópia dos contadores actuais."""
        return self._counters.copy()

    def reset_counters(self):
        """Reseta todos os contadores."""
        for key in self._counters:
            self._counters[key] = 0
```

- [ ] **Step 3: Integrate with OrchestrationWorkflow**

```python
# Adicionar em services/orchestrator-dynamic/src/workflows/orchestration_workflow.py

# No início, adicionar imports:
from src.saga.saga_orchestrator import SagaOrchestrator
from src.saga.saga_repository import SagaRepository
from src.saga.saga_event_store import SagaEventStore
from src.saga.saga_producer import SagaProducer
from src.saga.saga_metrics import SagaMetrics

# Na classe OrchestrationWorkflow, adicionar ao __init__:

def __init__(self):
    self._status = 'initializing'
    self._tickets_generated = []
    self._rejected_tickets = []
    self._workflow_result = {}
    self._sla_warnings = []
    self._saga_id: Optional[str] = None  # Nova

# No método run, após criar tickets, adicionar:

# === Criar Saga para coordenação ===
saga_steps = []
for ticket in tickets:
    saga_steps.append({
        "step_id": ticket.get("ticket_id"),
        "name": ticket.get("task_type", "UNKNOWN"),
        "action": "execute_ticket",
        "compensation_action": "compensate_ticket",
        "parameters": ticket
    })

saga_orchestrator = SagaOrchestrator(
    repository=SagaRepository(mongodb_client),
    event_store=SagaEventStore(mongodb_client)
)

saga = await saga_orchestrator.create_saga(
    workflow_id=workflow_id,
    plan_id=plan_id,
    intent_id=intent_id,
    steps=saga_steps
)

self._saga_id = saga.saga_id

# Publicar evento
saga_producer = SagaProducer(kafka_producer)
await saga_producer.publish_saga_created(saga)

# Iniciar saga
saga = await saga_orchestrator.start_saga(saga.saga_id)
await saga_producer.publish_saga_started(saga)

# Após cada step completado, publicar evento
await saga_producer.publish_saga_step_completed(
    saga_id=saga.saga_id,
    step_id=ticket["ticket_id"],
    step_name=ticket["task_type"],
    result={"status": "completed"}
)

# Em caso de falha, publicar eventos de compensação
await saga_producer.publish_saga_compensating(
    saga_id=saga.saga_id,
    reason="workflow_inconsistent",
    failed_step_id=failed_ticket_id
)
```

- [ ] **Step 4: Write integration tests**

```python
# services/orchestrator-dynamic/tests/integration/test_saga_events.py
"""
Integration tests for saga events.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.saga.saga_producer import SagaProducer
from src.saga.saga_metrics import SagaMetrics
from src.saga.saga_state import SagaState, SagaStep, SagaStatus


@pytest.mark.asyncio
async def test_saga_producer_publish_saga_created():
    """Test publishing saga_created event."""
    kafka_producer = AsyncMock()
    producer = SagaProducer(kafka_producer)

    saga = SagaState(
        saga_id="saga-123",
        workflow_id="wf-123",
        steps=[SagaStep(step_id="step1", name="test", action="test")]
    )

    result = await producer.publish_saga_created(saga)

    assert result is True
    kafka_producer.produce.assert_called_once()


@pytest.mark.asyncio
async def test_saga_producer_publish_saga_step_completed():
    """Test publishing saga_step_completed event."""
    kafka_producer = AsyncMock()
    producer = SagaProducer(kafka_producer)

    result = await producer.publish_saga_step_completed(
        saga_id="saga-123",
        step_id="step1",
        step_name="BUILD",
        result={"status": "success"}
    )

    assert result is True


def test_saga_metrics_increment():
    """Test incrementing metrics."""
    metrics = SagaMetrics()

    metrics.increment("saga_created")
    metrics.increment("saga_started")
    metrics.increment("step_completed", value=5)

    counters = metrics.get_counters()

    assert counters["saga_created"] == 1
    assert counters["saga_started"] == 1
    assert counters["step_completed"] == 5


def test_saga_metrics_reset():
    """Test resetting metrics."""
    metrics = SagaMetrics()

    metrics.increment("saga_created")
    metrics.increment("saga_failed")

    assert metrics.get_counters()["saga_created"] == 1

    metrics.reset_counters()

    assert metrics.get_counters()["saga_created"] == 0
```

- [ ] **Step 5: Run tests**

Run: `pytest services/orchestrator-dynamic/tests/integration/test_saga_events.py -v`
Expected: All tests passing

- [ ] **Step 6: Commit**

```bash
git add services/orchestrator-dynamic/src/saga/saga_producer.py services/orchestrator-dynamic/src/saga/saga_metrics.py services/orchestrator-dynamic/src/workflows/orchestration_workflow.py services/orchestrator-dynamic/tests/integration/test_saga_events.py
git commit -m "feat(orchestrator): implement saga events integration

- SagaProducer for Kafka events (saga.events topic)
- SagaMetrics for counting and duration tracking
- Integration with OrchestrationWorkflow
- 3 integration tests

Refs: ORCH-03"
```

---

*Continua nos próximos tasks... (ORCH-04 a ORCH-10)*
