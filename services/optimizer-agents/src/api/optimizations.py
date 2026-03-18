"""Optimizations API endpoints."""
import logging
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from src.repositories.optimization_repository import OptimizationRepository, get_repository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/optimizations", tags=["optimizations"])


# Dependency para injetar repository
async def get_optimization_repository() -> OptimizationRepository:
    """Retorna instância do repository."""
    # TODO: Obter cliente MongoDB do contexto da aplicação
    from src.config.settings import get_settings
    from motor.motor_asyncio import AsyncIOMotorClient

    settings = get_settings()
    client = AsyncIOMotorClient(settings.mongodb_url)
    return await get_repository(client, settings.mongodb_database_name)


# Models Request/Response
class RecommendationListResponse(BaseModel):
    """Resposta da lista de recomendações."""
    total: int
    offset: int
    limit: int
    items: List[dict]


class RecommendationResponse(BaseModel):
    """Resposta detalhada de recomendação."""
    id: str
    ticket_id: str
    workflow_id: str
    status: str
    created_at: datetime
    updated_at: datetime
    performance_analysis: dict
    recommendations: List[dict]


class ApproveRequest(BaseModel):
    """Request para aprovar recomendação."""
    recommendation_ids: List[str] = Field(..., min_items=1)
    approved_by: str


class ApplyRequest(BaseModel):
    """Request para aplicar otimização."""
    recommendation_ids: List[str] = Field(..., min_items=1)
    validate: bool = True


class MetricsResponse(BaseModel):
    """Resposta de métricas."""
    period: dict
    summary: dict
    performance: dict
    top_issues: List[dict]


class DashboardResponse(BaseModel):
    """Resposta do dashboard."""
    total_recommendations: int
    pending_approval: int
    applied: int
    avg_improvement_pct: float
    top_issue_types: List[dict]
    recent_recommendations: List[dict]


@router.get("/recommendations", response_model=RecommendationListResponse)
async def list_recommendations(
    status: Optional[str] = Query(None),
    workflow_id: Optional[str] = Query(None),
    target_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    repo: OptimizationRepository = Depends(get_optimization_repository),
):
    """Lista recomendações de otimização."""
    result = await repo.list_by_filters(
        status=status,
        workflow_id=workflow_id,
        target_type=target_type,
        limit=limit,
        offset=offset,
    )

    return RecommendationListResponse(**result)


@router.get("/recommendations/{recommendation_id}", response_model=RecommendationResponse)
async def get_recommendation(
    recommendation_id: str,
    repo: OptimizationRepository = Depends(get_optimization_repository),
):
    """Obtém detalhes de uma recomendação específica."""
    rec = await repo.get_by_id(recommendation_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    return RecommendationResponse(**rec)


@router.post("/recommendations/{recommendation_id}/approve")
async def approve_recommendation(
    recommendation_id: str,
    body: ApproveRequest,
    repo: OptimizationRepository = Depends(get_optimization_repository),
):
    """Aprova uma recomendação para aplicação."""
    success = await repo.update_status(
        recommendation_id,
        "approved",
        approved_by=body.approved_by,
    )

    if not success:
        raise HTTPException(status_code=404, detail="Recommendation not found")

    return {
        "id": recommendation_id,
        "status": "approved",
        "approved_recommendations": body.recommendation_ids,
        "approved_at": datetime.utcnow().isoformat(),
    }


@router.post("/recommendations/{recommendation_id}/apply")
async def apply_recommendation(
    recommendation_id: str,
    body: ApplyRequest,
    repo: OptimizationRepository = Depends(get_optimization_repository),
):
    """Aplica uma otimização aprovada."""
    # Primeiro verificar se está aprovada
    rec = await repo.get_by_id(recommendation_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")

    if rec.get("status") != "approved":
        raise HTTPException(status_code=400, detail="Recommendation must be approved first")

    # Aplicar
    success = await repo.update_status(recommendation_id, "applied")

    if not success:
        raise HTTPException(status_code=404, detail="Recommendation not found")

    return {
        "id": recommendation_id,
        "status": "applied",
        "applied_recommendations": body.recommendation_ids,
        "applied_at": datetime.utcnow().isoformat(),
        "files_modified": [],
    }


@router.get("/metrics")
async def get_metrics(
    from_date: Optional[datetime] = Query(None),
    to_date: Optional[datetime] = Query(None),
    repo: OptimizationRepository = Depends(get_optimization_repository),
):
    """Obtém métricas agregadas de otimizações."""
    metrics = await repo.get_metrics(from_date=from_date, to_date=to_date)

    return {
        "period": {
            "from": from_date.isoformat() if from_date else None,
            "to": to_date.isoformat() if to_date else None,
        },
        "summary": {
            "total_recommendations": metrics["total"],
            "pending": metrics["by_status"].get("pending", 0),
            "approved": metrics["by_status"].get("approved", 0),
            "applied": metrics["by_status"].get("applied", 0),
            "rejected": metrics["by_status"].get("rejected", 0),
        },
        "performance": {
            "avg_improvement_pct": metrics["avg_improvement_pct"],
            "total_time_saved_ms": 0,  # TODO: Calcular
            "best_improvement_pct": 0,  # TODO: Calcular
        },
        "top_issues": [],  # TODO: Implementar
    }


@router.get("/dashboard")
async def get_dashboard(
    repo: OptimizationRepository = Depends(get_optimization_repository),
):
    """Dashboard agregado para UI."""
    data = await repo.get_dashboard_data()
    return DashboardResponse(**data)


@router.get("/timeline/{workflow_id}")
async def get_workflow_timeline(
    workflow_id: str,
    repo: OptimizationRepository = Depends(get_optimization_repository),
):
    """Timeline de otimizações para um workflow específico."""
    optimizations = await repo.get_timeline(workflow_id)

    return {
        "workflow_id": workflow_id,
        "optimizations": optimizations,
    }
