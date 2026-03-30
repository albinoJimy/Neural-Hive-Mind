"""
API REST para gerenciamento de schedules.

Endpoints para criar, listar, pausar, retomar e disparar schedules.
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field

from src.models.schedule import (
    Schedule,
    ScheduleType,
    ScheduleStatus,
    ScheduleTrigger,
    SchedulePriority,
    ScheduleCreateRequest,
    ScheduleTriggerResponse,
)
from src.services.scheduler import ScheduleManager


router = APIRouter(prefix="/api/v1/schedules", tags=["Schedules"])


class ScheduleCreateResponse(BaseModel):
    """Response para criação de schedule."""

    schedule_id: str = Field(..., description="ID do schedule criado")
    message: str = Field(..., description="Mensagem de confirmação")


class ScheduleListResponse(BaseModel):
    """Response para listagem de schedules."""

    schedules: list[Schedule] = Field(
        default_factory=list, description="Lista de schedules"
    )
    total: int = Field(..., description="Total de schedules")
    page: int = Field(default=1, description="Página atual")
    page_size: int = Field(default=50, description="Tamanho da página")


class SchedulePauseResponse(BaseModel):
    """Response para pausa de schedule."""

    schedule_id: str
    status: str


class ScheduleResumeResponse(BaseModel):
    """Response para retomada de schedule."""

    schedule_id: str
    status: str


class ScheduleDeleteResponse(BaseModel):
    """Response para deleção de schedule."""

    schedule_id: str
    deleted: bool


# Global schedule manager (definido no main.py)
_schedule_manager: Optional[ScheduleManager] = None


def get_schedule_manager() -> ScheduleManager:
    """Dependency injection para ScheduleManager."""
    if _schedule_manager is None:
        raise HTTPException(status_code=503, detail="ScheduleManager not initialized")
    return _schedule_manager


def set_schedule_manager(manager: ScheduleManager) -> None:
    """Define o ScheduleManager global."""
    global _schedule_manager
    _schedule_manager = manager


@router.post(
    "",
    response_model=ScheduleCreateResponse,
    status_code=201,
    summary="Criar schedule",
    description="Cria um novo schedule para execução de workflow",
)
async def create_schedule(
    request: ScheduleCreateRequest,
    manager: ScheduleManager = Depends(get_schedule_manager),
) -> ScheduleCreateResponse:
    """
    Cria novo schedule.

    **Tipos de Schedule:**
    - `cron`: Execução baseada em expressão cron
    - `event`: Execução baseada em evento
    - `manual`: Execução apenas sob demanda

    **Exemplo:**
    ```json
    {
        "workflow": "BudgetRecalculationWorkflow",
        "schedule_type": "cron",
        "trigger": {
            "cron_expression": "0 * * * *",
            "parameters": {"force_recalculate": true}
        },
        "priority": "medium",
        "metadata": {"description": "Recalcula budgets"}
    }
    ```
    """
    try:
        schedule_id = await manager.create_schedule(
            workflow=request.workflow,
            schedule_type=request.schedule_type,
            trigger=request.trigger,
            priority=request.priority,
            metadata=request.metadata,
        )
        return ScheduleCreateResponse(
            schedule_id=schedule_id, message="Schedule created successfully"
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "",
    response_model=ScheduleListResponse,
    summary="Listar schedules",
    description="Lista todos os schedules com filtros opcionais",
)
async def list_schedules(
    workflow_type: Optional[str] = Query(None, description="Filtrar por workflow"),
    status: Optional[str] = Query(None, description="Filtrar por status"),
    limit: int = Query(50, ge=1, le=100, description="Limite de resultados"),
    offset: int = Query(0, ge=0, description="Offset para paginação"),
    manager: ScheduleManager = Depends(get_schedule_manager),
) -> ScheduleListResponse:
    """
    Lista schedules com filtros opcionais.

    **Filtros:**
    - `workflow_type`: Filtra por nome do workflow
    - `status`: Filtra por status (active, paused, disabled)
    - `limit`: Máximo de resultados (1-100)
    - `offset`: Pula N primeiros resultados
    """
    try:
        schedules = await manager.list_schedules(
            workflow_type=workflow_type, status=status, limit=limit, offset=offset
        )
        return ScheduleListResponse(
            schedules=schedules,
            total=len(schedules),
            page=(offset // limit) + 1 if limit else 1,
            page_size=limit,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{schedule_id}",
    response_model=Schedule,
    summary="Obter schedule",
    description="Retorna detalhes de um schedule específico",
)
async def get_schedule(
    schedule_id: str, manager: ScheduleManager = Depends(get_schedule_manager)
) -> Schedule:
    """
    Retorna detalhes de um schedule.

    **Retorna 404** se o schedule não existir.
    """
    schedule = await manager.get_schedule(schedule_id)

    if not schedule:
        raise HTTPException(status_code=404, detail=f"Schedule {schedule_id} not found")

    return schedule


@router.post(
    "/{schedule_id}/trigger",
    response_model=ScheduleTriggerResponse,
    summary="Disparar workflow",
    description="Dispara o workflow de um schedule imediatamente",
)
async def trigger_schedule(
    schedule_id: str, manager: ScheduleManager = Depends(get_schedule_manager)
) -> ScheduleTriggerResponse:
    """
    Dispara workflow imediatamente, independente do schedule.

    Útil para:
    - Execução manual de workflows agendados
    - Testes e debugging
    - Execução sob demanda
    """
    try:
        result = await manager.trigger_workflow(schedule_id, manual=True)
        return ScheduleTriggerResponse(
            schedule_id=result["schedule_id"],
            workflow_id=result["workflow_id"],
            triggered_at=result["triggered_at"],
            manual=result["manual"],
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/{schedule_id}/pause",
    response_model=SchedulePauseResponse,
    summary="Pausar schedule",
    description="Pausa um schedule ativo",
)
async def pause_schedule(
    schedule_id: str, manager: ScheduleManager = Depends(get_schedule_manager)
) -> SchedulePauseResponse:
    """
    Pausa um schedule ativo.

    O schedule não executará automaticamente enquanto estiver pausado,
    mas ainda pode ser disparado manualmente via `/trigger`.
    """
    try:
        result = await manager.pause_schedule(schedule_id)
        return SchedulePauseResponse(
            schedule_id=result["schedule_id"], status=result["status"]
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/{schedule_id}/resume",
    response_model=ScheduleResumeResponse,
    summary="Retomar schedule",
    description="Retoma um schedule pausado",
)
async def resume_schedule(
    schedule_id: str, manager: ScheduleManager = Depends(get_schedule_manager)
) -> ScheduleResumeResponse:
    """
    Retoma um schedule pausado.

    O schedule voltará a executar automaticamente conforme sua configuração.
    """
    try:
        result = await manager.resume_schedule(schedule_id)
        return ScheduleResumeResponse(
            schedule_id=result["schedule_id"], status=result["status"]
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete(
    "/{schedule_id}",
    response_model=ScheduleDeleteResponse,
    summary="Deletar schedule",
    description="Remove um schedule permanentemente",
)
async def delete_schedule(
    schedule_id: str, manager: ScheduleManager = Depends(get_schedule_manager)
) -> ScheduleDeleteResponse:
    """
    Deleta um schedule permanentemente.

    **Atenção:** Esta ação não pode ser desfeita.
    """
    try:
        result = await manager.delete_schedule(schedule_id)
        return ScheduleDeleteResponse(
            schedule_id=result["schedule_id"], deleted=result["deleted"]
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/executions/{schedule_id}",
    summary="Listar execuções",
    description="Lista execuções de um schedule",
)
async def list_schedule_executions(
    schedule_id: str,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    manager: ScheduleManager = Depends(get_schedule_manager),
) -> dict:
    """
    Lista execuções de um schedule específico.

    Retorna histórico de execuções com status, timestamps e erros se houver.
    """
    from src.models.schedule import ScheduleExecution

    executions = await manager.list_schedule_executions(
        schedule_id=schedule_id, limit=limit, offset=offset
    )

    return {
        "schedule_id": schedule_id,
        "total": len(executions),
        "limit": limit,
        "offset": offset,
        "executions": [
            {
                "execution_id": e.execution_id,
                "workflow_id": e.workflow_id,
                "started_at": e.started_at.isoformat() if e.started_at else None,
                "completed_at": e.completed_at.isoformat() if e.completed_at else None,
                "status": e.status,
                "error_message": e.error_message,
                "duration_seconds": (
                    (e.completed_at - e.started_at).total_seconds()
                    if e.started_at and e.completed_at
                    else None
                ),
            }
            for e in executions
        ],
    }
