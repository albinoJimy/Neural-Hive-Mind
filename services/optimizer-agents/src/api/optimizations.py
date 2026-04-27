"""Optimizations API endpoints."""

import logging
from datetime import datetime, timezone

UTC = UTC  # type: ignore

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.clients.mongodb_client import MongoDBClient
from src.clients.redis_client import RedisClient
from src.repositories.optimization_repository import (
    OptimizationRepository,
    get_repository,
)
from src.services.optimization_engine import OptimizationEngine
from src.services.slo_adjuster import SLOAdjuster
from src.services.weight_recalibrator import WeightRecalibrator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/optimizations", tags=["optimizations"])


# Dependency para injetar repository
async def get_optimization_repository() -> OptimizationRepository:
    """Retorna instância do repository."""
    # TODO: Obter cliente MongoDB do contexto da aplicação
    from motor.motor_asyncio import AsyncIOMotorClient

    from src.config.settings import get_settings

    settings = get_settings()
    client = AsyncIOMotorClient(settings.mongodb_url)
    return await get_repository(client, settings.mongodb_database_name)


# Models Request/Response
class RecommendationListResponse(BaseModel):
    """Resposta da lista de recomendações."""

    total: int
    offset: int
    limit: int
    items: list[dict]


class RecommendationResponse(BaseModel):
    """Resposta detalhada de recomendação."""

    id: str
    ticket_id: str
    workflow_id: str
    status: str
    created_at: datetime
    updated_at: datetime
    performance_analysis: dict
    recommendations: list[dict]


class ApproveRequest(BaseModel):
    """Request para aprovar recomendação."""

    recommendation_ids: list[str] = Field(..., min_items=1)
    approved_by: str


class ApplyRequest(BaseModel):
    """Request para aplicar otimização."""

    recommendation_ids: list[str] = Field(..., min_items=1)
    validate: bool = True


class MetricsResponse(BaseModel):
    """Resposta de métricas."""

    period: dict
    summary: dict
    performance: dict
    top_issues: list[dict]


class DashboardResponse(BaseModel):
    """Resposta do dashboard."""

    total_recommendations: int
    pending_approval: int
    applied: int
    avg_improvement_pct: float
    top_issue_types: list[dict]
    recent_recommendations: list[dict]


@router.get("/recommendations", response_model=RecommendationListResponse)
async def list_recommendations(
    status: str | None = Query(None),
    workflow_id: str | None = Query(None),
    target_type: str | None = Query(None),
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
        "approved_at": datetime.now(timezone.utc).isoformat(),
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
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "files_modified": [],
    }


@router.get("/metrics")
async def get_metrics(
    from_date: datetime | None = Query(None),
    to_date: datetime | None = Query(None),
    repo: OptimizationRepository = Depends(get_optimization_repository),
):
    """Obtém métricas agregadas de otimizações."""
    metrics = await repo.get_metrics(from_date=from_date, to_date=to_date)

    # Obter top issues do dashboard data
    dashboard_data = await repo.get_dashboard_data()

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
            "total_time_saved_ms": metrics.get("total_time_saved_ms", 0),
            "best_improvement_pct": metrics.get("best_improvement_pct", 0),
        },
        "top_issues": dashboard_data.get("top_issue_types", []),
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


# ============================================================================
# Dependency Injection Functions
# ============================================================================
# These are default providers that return HTTP 503 when not overridden.
# In main.py, app.dependency_overrides replaces these with actual implementations.


def get_mongodb_client() -> MongoDBClient:
    """
    Dependency para injetar MongoDBClient.

    Returns HTTP 503 if not overridden via app.dependency_overrides in main.py.
    """
    raise HTTPException(
        status_code=503, detail="MongoDBClient not available. Service is starting or misconfigured."
    )


def get_redis_client() -> RedisClient:
    """
    Dependency para injetar RedisClient.

    Returns HTTP 503 if not overridden via app.dependency_overrides in main.py.
    """
    raise HTTPException(
        status_code=503, detail="RedisClient not available. Service is starting or misconfigured."
    )


def get_optimization_engine() -> OptimizationEngine:
    """
    Dependency para injetar OptimizationEngine.

    Returns HTTP 503 if not overridden via app.dependency_overrides in main.py.
    """
    raise HTTPException(
        status_code=503,
        detail="OptimizationEngine not available. Service is starting or misconfigured.",
    )


def get_weight_recalibrator() -> WeightRecalibrator:
    """
    Dependency para injetar WeightRecalibrator.

    Returns HTTP 503 if not overridden via app.dependency_overrides in main.py.
    """
    raise HTTPException(
        status_code=503,
        detail="WeightRecalibrator not available. Service is starting or misconfigured.",
    )


def get_slo_adjuster() -> SLOAdjuster:
    """
    Dependency para injetar SLOAdjuster.

    Returns HTTP 503 if not overridden via app.dependency_overrides in main.py.
    """
    raise HTTPException(
        status_code=503,
        detail="SLOAdjuster not available. Service is starting or misconfigured.",
    )
