"""
API REST para Load Balancer

Endpoints para gerenciar workers e atribuir tarefas.
"""

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.api.dependencies import get_load_balancer
from src.services import BalancingStrategy, LoadBalancer

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1/workers", tags=["workers"])


class RegisterWorkerRequest(BaseModel):
    """Request para registrar worker"""

    worker_id: str = Field(..., description="ID único do worker")
    capacity: float = Field(default=1.0, ge=0.1, le=10.0, description="Capacidade relativa")
    metadata: dict[str, Any] | None = Field(default=None, description="Metadados adicionais")


class UpdateMetricsRequest(BaseModel):
    """Request para atualizar métricas do worker"""

    active_tasks: int | None = Field(default=None, ge=0)
    completed_tasks: int | None = Field(default=None, ge=0)
    failed_tasks: int | None = Field(default=None, ge=0)
    avg_processing_time_ms: float | None = Field(default=None, ge=0.0)


class AssignTaskRequest(BaseModel):
    """Request para atribuir tarefa"""

    task_id: str = Field(..., description="ID da tarefa")
    task_data: dict[str, Any] | None = Field(default=None, description="Dados da tarefa")
    strategy: str | None = Field(
        default=None,
        description="Estratégia de balanceamento (round_robin, least_loaded, weighted, consistent_hash)",
    )


class CompleteTaskRequest(BaseModel):
    """Request para completar tarefa"""

    worker_id: str = Field(..., description="ID do worker")
    task_id: str = Field(..., description="ID da tarefa")
    success: bool = Field(default=True, description="Se a tarefa foi bem-sucedida")
    processing_time_ms: float | None = Field(
        default=None, ge=0.0, description="Tempo de processamento"
    )


@router.post("/register")
async def register_worker(
    req: RegisterWorkerRequest,
    load_balancer: LoadBalancer = Depends(get_load_balancer),
) -> JSONResponse:
    """
    Registrar um novo worker no balanceador.

    O worker será considerado saudável após registro com heartbeat inicial.
    """
    success = await load_balancer.register_worker(
        worker_id=req.worker_id,
        capacity=req.capacity,
        metadata=req.metadata,
    )

    if success:
        logger.info("worker_registered_via_api", worker_id=req.worker_id)
        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={"message": "Worker registered successfully", "worker_id": req.worker_id},
        )
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Failed to register worker",
    )


@router.delete("/{worker_id}")
async def unregister_worker(
    worker_id: str,
    load_balancer: LoadBalancer = Depends(get_load_balancer),
) -> JSONResponse:
    """
    Remover worker do balanceador.

    O worker não receberá mais novas tarefas.
    """
    success = await load_balancer.unregister_worker(worker_id)

    if success:
        logger.info("worker_unregistered_via_api", worker_id=worker_id)
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"message": "Worker unregistered successfully", "worker_id": worker_id},
        )
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Failed to unregister worker",
    )


@router.post("/{worker_id}/metrics")
async def update_worker_metrics(
    worker_id: str,
    req: UpdateMetricsRequest,
    load_balancer: LoadBalancer = Depends(get_load_balancer),
) -> JSONResponse:
    """
    Atualizar métricas de um worker.

    Usado pelos workers para reportar seu estado atual.
    """
    success = await load_balancer.update_worker_metrics(
        worker_id=worker_id,
        active_tasks=req.active_tasks,
        completed_tasks=req.completed_tasks,
        failed_tasks=req.failed_tasks,
        avg_processing_time_ms=req.avg_processing_time_ms,
    )

    if success:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"message": "Metrics updated successfully"},
        )
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Failed to update metrics",
    )


@router.get("")
async def get_workers_status(
    load_balancer: LoadBalancer = Depends(get_load_balancer),
) -> JSONResponse:
    """
    Obter status de todos os workers registrados.

    Retorna métricas e estado de saúde de cada worker.
    """
    status_data = await load_balancer.get_workers_status()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "workers": status_data,
            "count": len(status_data),
        },
    )


@router.get("/statistics")
async def get_load_balancer_statistics(
    load_balancer: LoadBalancer = Depends(get_load_balancer),
) -> JSONResponse:
    """
    Obter estatísticas do balanceador.

    Retorna informações sobre:
    - Total de workers
    - Workers saudáveis
    - Tarefas ativas, completadas e falhadas
    - Estratégia atual
    """
    stats = await load_balancer.get_statistics()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=stats,
    )


@router.post("/assign")
async def assign_task(
    req: AssignTaskRequest,
    load_balancer: LoadBalancer = Depends(get_load_balancer),
) -> JSONResponse:
    """
    Atribuir tarefa a um worker.

    Usa a estratégia configurada ou a especificada no request.
    """
    # Validar estratégia se fornecida
    strategy = None
    if req.strategy:
        try:
            strategy = BalancingStrategy(req.strategy)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid strategy: {req.strategy}. Valid options: round_robin, least_loaded, weighted, consistent_hash",
            )

    assignment = await load_balancer.assign_task(
        task_id=req.task_id,
        task_data=req.task_data,
        strategy=strategy,
    )

    if assignment:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "task_id": req.task_id,
                "worker_id": assignment.worker_id,
                "strategy": assignment.strategy.value,
                "assigned_at": assignment.assigned_at.isoformat(),
            },
        )
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="No healthy workers available",
    )


@router.post("/complete")
async def complete_task(
    req: CompleteTaskRequest,
    load_balancer: LoadBalancer = Depends(get_load_balancer),
) -> JSONResponse:
    """
    Marcar tarefa como completa.

    Atualiza métricas do worker com o resultado da tarefa.
    """
    success = await load_balancer.complete_task(
        worker_id=req.worker_id,
        task_id=req.task_id,
        success=req.success,
        processing_time_ms=req.processing_time_ms,
    )

    if success:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"message": "Task completed successfully"},
        )
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Failed to complete task",
    )
