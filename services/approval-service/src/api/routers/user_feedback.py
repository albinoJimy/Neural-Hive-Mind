"""
User Feedback API Router - Coleta de feedback direto de usuários.
"""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from src.services.feedback_loop_service import (
    FeedbackSignal,
    FeedbackSource,
    get_feedback_loop_service,
)

router = APIRouter(prefix="/feedback", tags=["feedback"])


class UserFeedbackRequest(BaseModel):
    """Request para feedback de usuário."""

    deployment_id: str = Field(..., description="ID do deployment")
    plan_id: str = Field(..., description="ID do plano")
    workflow_id: str = Field(..., description="ID do workflow")
    rating: int = Field(..., ge=1, le=5, description="Rating de 1-5")
    feedback_text: str | None = Field(None, description="Comentários opcional")
    categories: list[str] = Field(
        default_factory=list, description="Categorias do feedback (ex: performance, usability)"
    )


class FeedbackSummaryResponse(BaseModel):
    """Response para resumo de feedback."""

    period_days: int
    total_signals: int
    by_type: dict[str, int]
    by_priority: dict[str, int]
    pending_signals: int


@router.post("/user", status_code=status.HTTP_201_CREATED)
async def submit_user_feedback(request: UserFeedbackRequest) -> dict[str, Any]:
    """
    Submete feedback de usuário sobre um deployment.

    Args:
        request: Dados do feedback

    Returns:
        Confirmação do registro
    """
    service = get_feedback_loop_service()

    # Construir dados do feedback
    feedback_data = {
        "rating": request.rating,
        "feedback_text": request.feedback_text,
        "categories": request.categories,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }

    # Gerar sinal de feedback
    signal = FeedbackSignal(
        signal_type="user_feedback",
        source=FeedbackSource.USER,
        plan_id=request.plan_id,
        workflow_id=request.workflow_id,
        data=feedback_data,
        priority=service._calculate_feedback_priority(feedback_data),
    )

    await service._add_feedback_signal(signal)

    return {
        "status": "recorded",
        "feedback_id": f"fb-{request.deployment_id}-{int(datetime.now(timezone.utc).timestamp())}",
        "rating": request.rating,
        "processed": signal.processed,
    }


@router.get("/summary", response_model=FeedbackSummaryResponse)
async def get_feedback_summary(
    plan_id: str | None = None,
    workflow_id: str | None = None,
    days: int = 7,
) -> FeedbackSummaryResponse:
    """
    Obtém resumo de feedback.

    Args:
        plan_id: Filtrar por plano
        workflow_id: Filtrar por workflow
        days: Número de dias para analisar

    Returns:
        Resumo de feedback
    """
    service = get_feedback_loop_service()

    summary = await service.get_feedback_summary(
        plan_id=plan_id,
        workflow_id=workflow_id,
        days=days,
    )

    return FeedbackSummaryResponse(**summary)


@router.get("/metrics/{deployment_id}")
async def get_deployment_metrics(deployment_id: str) -> dict[str, Any]:
    """
    Obtém métricas de um deployment específico.

    Args:
        deployment_id: ID do deployment

    Returns:
        Métricas do deployment
    """
    service = get_feedback_loop_service()

    metrics = service.metrics.get(deployment_id)
    if not metrics:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Metrics not found for deployment {deployment_id}",
        )

    return metrics.to_dict()


@router.post("/ml/training-data/{plan_id}")
async def generate_ml_training_data(
    plan_id: str,
    limit: int = 100,
) -> dict[str, Any]:
    """
    Gera dados de treinamento para modelos ML.

    Args:
        plan_id: ID do plano
        limit: Limite de exemplos

    Returns:
        Dados de treinamento
    """
    service = get_feedback_loop_service()

    training_data = await service.generate_ml_training_data(
        plan_id=plan_id,
        limit=limit,
    )

    return {
        "plan_id": plan_id,
        "examples_count": len(training_data),
        "training_data": training_data,
    }


@router.get("/health")
async def health():
    """Health check do feedback service."""
    service = get_feedback_loop_service()

    return {
        "status": "healthy",
        "service": "feedback-loop",
        "metrics_collected": len(service.metrics),
        "signals_queued": len(service.feedback_signals),
    }
