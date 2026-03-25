"""
API REST para Load Balancer

Endpoints para gerenciar workers e atribuir tarefas.
"""
from fastapi import APIRouter, Request, status, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
import structlog

from ..services import BalancingStrategy

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1/workers", tags=["workers"])


class RegisterWorkerRequest(BaseModel):
    """Request para registrar worker"""
    worker_id: str = Field(..., description="ID único do worker")
    capacity: float = Field(default=1.0, ge=0.1, le=10.0, description="Capacidade relativa")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Metadados adicionais")


class UpdateMetricsRequest(BaseModel):
    """Request para atualizar métricas do worker"""
    active_tasks: Optional[int] = Field(default=None, ge=0)
    completed_tasks: Optional[int] = Field(default=None, ge=0)
    failed_tasks: Optional[int] = Field(default=None, ge=0)
    avg_processing_time_ms: Optional[float] = Field(default=None, ge=0.0)


class AssignTaskRequest(BaseModel):
    """Request para atribuir tarefa"""
    task_id: str = Field(..., description="ID da tarefa")
    task_data: Optional[Dict[str, Any]] = Field(default=None, description="Dados da tarefa")
    strategy: Optional[str] = Field(
        default=None,
        description="Estratégia de balanceamento (round_robin, least_loaded, weighted, consistent_hash)"
    )


class CompleteTaskRequest(BaseModel):
    """Request para completar tarefa"""
    worker_id: str = Field(..., description="ID do worker")
    task_id: str = Field(..., description="ID da tarefa")
    success: bool = Field(default=True, description="Se a tarefa foi bem-sucedida")
    processing_time_ms: Optional[float] = Field(default=None, ge=0.0, description="Tempo de processamento")


@router.post("/register")
async def register_worker(request: Request, req: RegisterWorkerRequest) -> JSONResponse:
    """
    Registrar um novo worker no balanceador.

    O worker será considerado saudável após registro com heartbeat inicial.
    """
    app_state = request.app.state.app_state

    if not app_state.load_balancer:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Load balancer not enabled",
        )

    success = await app_state.load_balancer.register_worker(
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
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to register worker",
        )


@router.delete("/{worker_id}")
async def unregister_worker(request: Request, worker_id: str) -> JSONResponse:
    """
    Remover worker do balanceador.

    O worker não receberá mais novas tarefas.
    """
    app_state = request.app.state.app_state

    if not app_state.load_balancer:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Load balancer not enabled",
        )

    success = await app_state.load_balancer.unregister_worker(worker_id)

    if success:
        logger.info("worker_unregistered_via_api", worker_id=worker_id)
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"message": "Worker unregistered successfully", "worker_id": worker_id},
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to unregister worker",
        )


@router.post("/{worker_id}/metrics")
async def update_worker_metrics(
    request: Request, worker_id: str, req: UpdateMetricsRequest
) -> JSONResponse:
    """
    Atualizar métricas de um worker.

    Usado pelos workers para reportar seu estado atual.
    """
    app_state = request.app.state.app_state

    if not app_state.load_balancer:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Load balancer not enabled",
        )

    success = await app_state.load_balancer.update_worker_metrics(
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
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update metrics",
        )


@router.get("")
async def get_workers_status(request: Request) -> JSONResponse:
    """
    Obter status de todos os workers registrados.

    Retorna métricas e estado de saúde de cada worker.
    """
    app_state = request.app.state.app_state

    if not app_state.load_balancer:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Load balancer not enabled",
        )

    status_data = await app_state.load_balancer.get_workers_status()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "workers": status_data,
            "count": len(status_data),
        },
    )


@router.get("/statistics")
async def get_load_balancer_statistics(request: Request) -> JSONResponse:
    """
    Obter estatísticas do balanceador.

    Retorna informações sobre:
    - Total de workers
    - Workers saudáveis
    - Tarefas ativas, completadas e falhadas
    - Estratégia atual
    """
    app_state = request.app.state.app_state

    if not app_state.load_balancer:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Load balancer not enabled",
        )

    stats = await app_state.load_balancer.get_statistics()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=stats,
    )


@router.post("/assign")
async def assign_task(request: Request, req: AssignTaskRequest) -> JSONResponse:
    """
    Atribuir tarefa a um worker.

    Usa a estratégia configurada ou a especificada no request.
    """
    app_state = request.app.state.app_state

    if not app_state.load_balancer:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Load balancer not enabled",
        )

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

    assignment = await app_state.load_balancer.assign_task(
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
    else:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No healthy workers available",
        )


@router.post("/complete")
async def complete_task(request: Request, req: CompleteTaskRequest) -> JSONResponse:
    """
    Marcar tarefa como completa.

    Atualiza métricas do worker com o resultado da tarefa.
    """
    app_state = request.app.state.app_state

    if not app_state.load_balancer:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Load balancer not enabled",
        )

    success = await app_state.load_balancer.complete_task(
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
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to complete task",
        )
