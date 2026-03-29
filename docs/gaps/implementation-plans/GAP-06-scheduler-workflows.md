# GAP-06: Scheduler de Workflows Faltando

**Status:** 🟡 Planejado
**Prioridade:** P2 - MÉDIA (Funcionalidade)
**Esforço Estimado:** 2 semanas (80 horas)
**Responsável:** Backend Team (SLA Management System)

---

## Problema

Fase 2.2 - SLA Management System possui:
- ✅ Budget calculator
- ✅ SLO/SLA monitoring
- ✅ Prometheus integration
- ❌ **Scheduler de workflows NÃO implementado**

### O que Existe

```
services/sla-management-system/
├── src/services/budget_calculator.py    ✅
├── src/observability/metrics.py         ✅
└── src/api/                              ✅ (apenas budgets/SLOs)
```

### O que Falta

```
services/sla-management-system/
├── src/services/scheduler.py             ❌
├── src/api/schedules.py                  ❌
└── src/models/schedule.py                ❌
```

---

## Requisitos

### Workflows para Scheduling

| ID | Workflow | Trigger | Frequência |
|----|----------|---------|------------|
| 1 | BudgetRecalculation | Cron (hora em hora) | `0 * * * *` |
| 2 | ReportGeneration | Cron (diário) | `0 0 * * *` |
| 3 | Maintenance | Cron (semanal) | `0 2 * * 0` |
| 4 | Remediation | Event (SLO violation) | `slo.violation` |
| 5 | PolicyEvaluation | Event (budget crítico) | `sla.budgets` |

### Triggers Necessários

| Tipo | Trigger | Workflow |
|------|---------|----------|
| **Time-based** | `0 * * * *` | BudgetRecalculationWorkflow |
| **Time-based** | `0 0 * * *` | ReportGenerationWorkflow |
| **Time-based** | `0 2 * * 0` | MaintenanceWorkflow |
| **Event-based** | `slo.violation` | RemediationWorkflow |
| **Event-based** | `sla.budgets` | PolicyEvaluationWorkflow |

---

## Implementação

### Fase 1: Criar Scheduler Service

**CRIAR:** `services/sla-management-system/src/services/scheduler.py`

```python
"""
Scheduler de workflows Temporal para SLA Management System
"""
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum
import structlog
from temporalio.client import Client

from ..models.schedule import (
    Schedule, ScheduleType, ScheduleStatus, ScheduleTrigger
)
from ..clients.postgresql_client import PostgreSQLClient
from ..clients.temporal_client import TemporalClientWrapper

logger = structlog.get_logger(__name__)


class SchedulePriority(IntEnum):
    """Prioridade de schedules."""
    CRITICAL = 1  # SLO violations, freeze triggers
    HIGH = 2      # Remediation, policy enforcement
    MEDIUM = 3    # Budget recalculation
    LOW = 4       # Reports, maintenance


class ScheduleManager:
    """Gerenciador de schedules para workflows Temporal."""

    def __init__(
        self,
        postgresql_client: PostgreSQLClient,
        temporal_client: TemporalClientWrapper,
        temporal_namespace: str = "default",
        temporal_task_queue: str = "sla-tasks"
    ):
        self.postgresql_client = postgresql_client
        self.temporal_client = temporal_client
        self.temporal_namespace = temporal_namespace
        self.temporal_task_queue = temporal_task_queue
        self.logger = logger

    async def create_schedule(
        self,
        workflow: str,
        schedule_type: ScheduleType,
        trigger: ScheduleTrigger,
        priority: int = 3,
        metadata: Dict[str, Any] = None
    ) -> str:
        """Cria novo schedule."""
        from uuid import uuid4

        schedule_id = str(uuid4())

        # Criar schedule no Temporal
        if schedule_type == ScheduleType.CRON:
            await self._register_temporal_cron(
                schedule_id, workflow, trigger.cron_expression
            )
        elif schedule_type == ScheduleType.EVENT:
            await self._register_event_subscription(
                schedule_id, workflow, trigger
            )

        # Persistir no PostgreSQL
        schedule = Schedule(
            schedule_id=schedule_id,
            workflow=workflow,
            schedule_type=schedule_type,
            trigger=trigger,
            priority=priority,
            status=ScheduleStatus.ACTIVE,
            created_at=datetime.utcnow(),
            metadata=metadata or {}
        )

        await self.postgresql_client.create_schedule(schedule)

        self.logger.info(
            "schedule_created",
            schedule_id=schedule_id,
            workflow=workflow,
            type=schedule_type.value
        )

        return schedule_id

    async def _register_temporal_cron(
        self,
        schedule_id: str,
        workflow: str,
        cron_expression: str
    ) -> None:
        """Registra cron schedule no Temporal."""
        # Implementação usando Temporal Client
        # Ver documentação Temporal para schedules
        pass

    async def _register_event_subscription(
        self,
        schedule_id: str,
        workflow: str,
        trigger: ScheduleTrigger
    ) -> None:
        """Registra subscrição de evento Kafka."""
        # Implementação usando Kafka consumer
        pass

    async def trigger_workflow(
        self,
        schedule_id: str,
        manual: bool = False
    ) -> Dict[str, Any]:
        """Dispara workflow baseado no schedule."""
        schedule = await self.postgresql_client.get_schedule(schedule_id)

        # Iniciar workflow Temporal
        handle = await self.temporal_client.start_workflow(
            workflow=schedule.workflow,
            id=f"{schedule.workflow}-{schedule_id}-{datetime.utcnow().timestamp()}",
            task_queue=self.temporal_task_queue,
            args=schedule.trigger.parameters or {}
        )

        # Atualizar última execução
        await self.postgresql_client.update_schedule_last_run(
            schedule_id, datetime.utcnow()
        )

        return {
            "schedule_id": schedule_id,
            "workflow_id": handle.id,
            "triggered_at": datetime.utcnow().isoformat(),
            "manual": manual
        }
```

### Fase 2: Criar API Router

**CRIAR:** `services/sla-management-system/src/api/schedules.py`

```python
"""API REST para gerenciamento de schedules."""
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from ..models.schedule import (
    Schedule, ScheduleType, ScheduleStatus, ScheduleTrigger
)
from ..services.scheduler import ScheduleManager

router = APIRouter(prefix="/api/v1/schedules", tags=["Schedules"])


class ScheduleCreateRequest(BaseModel):
    workflow: str
    schedule_type: ScheduleType
    trigger: ScheduleTrigger
    priority: int = 3
    metadata: dict = {}


class ScheduleCreateResponse(BaseModel):
    schedule_id: str
    message: str


def get_schedule_manager() -> ScheduleManager:
    """Dependency injection."""
    from .. import main
    if main.schedule_manager is None:
        raise HTTPException(status_code=503, detail="ScheduleManager not initialized")
    return main.schedule_manager


@router.post("", response_model=ScheduleCreateResponse, status_code=201)
async def create_schedule(
    request: ScheduleCreateRequest,
    manager: ScheduleManager = Depends(get_schedule_manager)
):
    """Cria novo schedule."""
    try:
        schedule_id = await manager.create_schedule(
            workflow=request.workflow,
            schedule_type=request.schedule_type,
            trigger=request.trigger,
            priority=request.priority,
            metadata=request.metadata
        )
        return ScheduleCreateResponse(
            schedule_id=schedule_id,
            message="Schedule created successfully"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("")
async def list_schedules(
    workflow_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    manager: ScheduleManager = Depends(get_schedule_manager)
):
    """Lista schedules."""
    schedules = await manager.list_schedules(
        workflow_type=workflow_type,
        status=status
    )
    return {"schedules": schedules, "total": len(schedules)}


@router.get("/{schedule_id}")
async def get_schedule(
    schedule_id: str,
    manager: ScheduleManager = Depends(get_schedule_manager)
):
    """Detalhes de um schedule."""
    return await manager.get_schedule(schedule_id)


@router.post("/{schedule_id}/trigger")
async def trigger_manual(
    schedule_id: str,
    manager: ScheduleManager = Depends(get_schedule_manager)
):
    """Trigger manual de schedule."""
    return await manager.trigger_workflow(schedule_id, manual=True)


@router.post("/{schedule_id}/pause")
async def pause_schedule(
    schedule_id: str,
    manager: ScheduleManager = Depends(get_schedule_manager)
):
    """Pausa schedule."""
    return await manager.pause_schedule(schedule_id)


@router.post("/{schedule_id}/resume")
async def resume_schedule(
    schedule_id: str,
    manager: ScheduleManager = Depends(get_schedule_manager)
):
    """Retoma schedule."""
    return await manager.resume_schedule(schedule_id)
```

### Fase 3: Criar Modelos

**CRIAR:** `services/sla-management-system/src/models/schedule.py`

```python
"""Modelos de dados para Schedule."""
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from uuid import uuid4


class ScheduleType(str, Enum):
    """Tipo de schedule."""
    CRON = "cron"
    EVENT = "event"
    RESOURCE = "resource"
    MANUAL = "manual"


class ScheduleStatus(str, Enum):
    """Status do schedule."""
    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"
    COMPLETED = "completed"


class ScheduleTrigger(BaseModel):
    """Configuração de trigger."""
    cron_expression: Optional[str] = None
    event_type: Optional[str] = None
    event_filter: Optional[Dict[str, Any]] = None
    resource_threshold: Optional[Dict[str, float]] = None
    parameters: Optional[Dict[str, Any]] = None


class Schedule(BaseModel):
    """Schedule de workflow."""
    schedule_id: str = Field(default_factory=lambda: str(uuid4()))
    workflow: str
    schedule_type: ScheduleType
    trigger: ScheduleTrigger
    priority: int = Field(default=3, ge=1, le=5)
    status: ScheduleStatus = Field(default=ScheduleStatus.ACTIVE)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    total_runs: int = Field(default=0)
    failure_count: int = Field(default=0)
    metadata: Dict[str, Any] = Field(default_factory=dict)
```

### Fase 4: Integration com SLA Monitor

**CRIAR:** `services/sla-management-system/src/services/sla_event_handler.py`

```python
"""Processa eventos de SLA e dispara workflows."""
from ..services.scheduler import ScheduleManager
from ..models.schedule import ScheduleType, ScheduleTrigger


class SLAEventHandler:
    """Processa eventos de SLA e dispara workflows."""

    def __init__(self, schedule_manager: ScheduleManager):
        self.schedule_manager = schedule_manager

    async def on_budget_updated(self, budget) -> None:
        """Handler para evento de budget atualizado."""
        # Verificar se precisa acionar policy evaluation
        if budget.status.value in ("CRITICAL", "EXHAUSTED"):
            await self._trigger_policy_evaluation(budget)

    async def on_slo_violation(self, violation: Dict[str, Any]) -> None:
        """Handler para evento de violação de SLO."""
        await self._trigger_remediation_violation(violation)

    async def _trigger_policy_evaluation(self, budget) -> None:
        """Dispara workflow de avaliação de politicas."""
        schedule_id = await self.schedule_manager.create_schedule(
            workflow="PolicyEvaluationWorkflow",
            schedule_type=ScheduleType.EVENT,
            trigger=ScheduleTrigger(
                event_type="sla.budgets",
                event_filter={"slo_id": budget.slo_id},
                parameters={
                    "slo_id": budget.slo_id,
                    "service_name": budget.service_name,
                    "budget_status": budget.status.value
                }
            ),
            priority=2  # HIGH
        )
```

---

## Schema PostgreSQL

```sql
-- migrations/002_add_schedules_table.sql

CREATE TABLE IF NOT EXISTS schedules (
    schedule_id VARCHAR(255) PRIMARY KEY,
    workflow VARCHAR(255) NOT NULL,
    schedule_type VARCHAR(50) NOT NULL,
    trigger_data JSONB NOT NULL,
    priority INTEGER NOT NULL DEFAULT 3 CHECK (priority BETWEEN 1 AND 5),
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    last_run_at TIMESTAMP,
    next_run_at TIMESTAMP,
    total_runs INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    metadata JSONB
);

CREATE INDEX idx_schedules_status ON schedules(status);
CREATE INDEX idx_schedules_workflow ON schedules(workflow);
CREATE INDEX idx_schedules_next_run ON schedules(next_run_at) WHERE status = 'active';

CREATE TABLE IF NOT EXISTS schedule_executions (
    execution_id VARCHAR(255) PRIMARY KEY,
    schedule_id VARCHAR(255) NOT NULL REFERENCES schedules(schedule_id),
    workflow_id VARCHAR(255) NOT NULL,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    status VARCHAR(50) NOT NULL,
    error_message TEXT,
    output JSONB
);

CREATE INDEX idx_schedule_executions_schedule_id ON schedule_executions(schedule_id);
```

---

## Testes

```python
# tests/unit/test_scheduler.py

@pytest.mark.asyncio
async def test_create_cron_schedule(mock_schedule_manager):
    """Testa criacao de schedule cron."""
    trigger = ScheduleTrigger(
        cron_expression="0 * * * *",
        parameters={"slo_id": "test-slo"}
    )

    schedule_id = await mock_schedule_manager.create_schedule(
        workflow="BudgetRecalculationWorkflow",
        schedule_type=ScheduleType.CRON,
        trigger=trigger
    )

    assert schedule_id is not None


@pytest.mark.asyncio
async def test_trigger_workflow(mock_schedule_manager):
    """Testa trigger manual."""
    result = await mock_schedule_manager.trigger_workflow("test-id", manual=True)

    assert result["schedule_id"] == "test-id"
    assert result["manual"] is True
```

---

## API Endpoints

| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/api/v1/schedules` | POST | Criar schedule |
| `/api/v1/schedules` | GET | Listar schedules |
| `/api/v1/schedules/{id}` | GET | Detalhes |
| `/api/v1/schedules/{id}/trigger` | POST | Trigger manual |
| `/api/v1/schedules/{id}/pause` | POST | Pausar |
| `/api/v1/schedules/{id}/resume` | POST | Retomar |

---

## Exemplo de Uso

```python
# Criar schedule para recalcular budgets hora em hora
import httpx

async def create_budget_schedule():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://sla-management-system:8000/api/v1/schedules",
            json={
                "workflow": "BudgetRecalculationWorkflow",
                "schedule_type": "cron",
                "trigger": {
                    "cron_expression": "0 * * * *",
                    "parameters": {"force_recalculate": True}
                },
                "priority": 3,
                "metadata": {
                    "description": "Recalcula budgets periodicamente"
                }
            }
        )
        return response.json()

# Trigger manual
async def trigger_now(schedule_id: str):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"http://sla-management-system:8000/api/v1/schedules/{schedule_id}/trigger"
        )
        return response.json()
```

---

## Arquivos Críticos

| Ação | Arquivo |
|------|---------|
| **CRIAR** | `services/sla-management-system/src/services/scheduler.py` |
| **CRIAR** | `services/sla-management-system/src/api/schedules.py` |
| **CRIAR** | `services/sla-management-system/src/models/schedule.py` |
| **CRIAR** | `services/sla-management-system/src/services/sla_event_handler.py` |
| **CRIAR** | `services/sla-management-system/migrations/002_add_schedules_table.sql` |

---

## Cronograma

| Semana | Atividade | Deliverable |
|--------|-----------|-------------|
| 1 | Scheduler service + Models | Core funcional |
| 1 | API router + Testes unitários | API completa |
| 2 | Integration SLA Monitor + Deploy | Produção |

---

**Documento baseado em análise do agente Plan (2026-03-29)**
