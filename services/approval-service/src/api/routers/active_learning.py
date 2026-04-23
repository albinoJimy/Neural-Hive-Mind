"""
Active Learning API Router - Endpoints REST para active learning.

Fornece endpoints para consultar métricas de balanceamento,
gerenciar fila de casos prioritários e submeter feedbacks.
"""

from datetime import datetime, timezone
from typing import Any, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/active-learning", tags=["active-learning"])


# Request/Response Models


class ClaimRequest(BaseModel):
    """Request para reivindicar caso da fila."""

    assigned_to: str = Field(..., description="Email do usuário que está fazendo a revisão")


class FeedbackRequest(BaseModel):
    """Request para submeter feedback de caso prioritário."""

    human_recommendation: str = Field(
        ..., description="Decisão humana: approve, reject, review_required, conditional"
    )
    human_rating: float = Field(..., ge=0.0, le=1.0, description="Rating de concordância (0.0-1.0)")
    feedback_notes: str = Field(default="", description="Notas textuais do revisor")
    submitted_by: str = Field(..., description="Identificador do usuário (email, user_id)")

    @field_validator("human_recommendation")
    @classmethod
    def validate_recommendation(cls, v: str) -> str:
        """Valida recomendação."""
        valid = ["approve", "reject", "review_required", "conditional"]
        if v not in valid:
            raise ValueError(f"Deve ser um de: {valid}")
        return v


class MetricsResponse(BaseModel):
    """Resposta com métricas de balanceamento."""

    total_feedbacks: int
    balance: dict[str, dict[str, Any]]
    confidence_distribution: dict[str, dict[str, Any]]
    domain_distribution: dict[str, dict[str, Any]]
    semantic_features_count: int
    semantic_features_percentage: float
    priority_recommendations: list[dict[str, Any]]
    last_updated: str


class QueueResponse(BaseModel):
    """Resposta com casos da fila."""

    queue_size: int
    cases: list[dict[str, Any]]
    filters_applied: dict[str, Any]


class ClaimResponse(BaseModel):
    """Resposta de claim bem-sucedido."""

    queue_id: str
    plan_id: Optional[str] = None
    status: str
    assigned_to: str
    claimed_at: str
    expires_at: str


class FeedbackResponse(BaseModel):
    """Resposta de feedback submetido."""

    queue_id: str
    plan_id: Optional[str] = None
    feedback_id: str
    status: str
    submitted_at: str


# Dependency Injection


async def get_balance_analyzer(http_request: Request) -> Any:
    """Obtém DatasetBalanceAnalyzer do estado da aplicação."""
    analyzer = getattr(http_request.app.state, "balance_analyzer", None)
    if not analyzer:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Balance analyzer not available"
        )
    return analyzer


async def get_feedback_queue(http_request: Request) -> Any:
    """Obtém PriorityFeedbackQueue do estado da aplicação."""
    queue = getattr(http_request.app.state, "feedback_queue", None)
    if not queue:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Feedback queue not available"
        )
    return queue


# Endpoints


@router.get("/metrics", response_model=MetricsResponse)
async def get_metrics(http_request: Request, analyzer=Depends(get_balance_analyzer)):
    """
    Retorna métricas de balanceamento do dataset.

    Fornece análise completa de como o dataset de feedback está balanceado
    em termos de classes, confiança e domínios, além de recomendações
    de prioridade para coleta.
    """
    try:
        metrics = await analyzer.calculate_balance_metrics()

        # Adicionar timestamp
        metrics.last_updated = datetime.now(timezone.utc).isoformat()

        return MetricsResponse(**metrics.model_dump())

    except Exception as e:
        logger.error("Failed to get balance metrics", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate metrics: {e!s}",
        )


@router.get("/queue", response_model=QueueResponse)
async def get_queue(
    http_request: Request,
    limit: int = 10,
    status: str = "pending",
    queue=Depends(get_feedback_queue),
):
    """
    Retorna próximos casos da fila de revisão prioritária.

    Casos são retornados ordenados por valor informacional (decrescente).
    """
    try:
        # Validar limit
        limit = max(1, min(50, limit))

        # Obter tamanho da fila
        queue_size = queue.get_queue_size()

        # Obter casos pendentes
        # Nota: status_filter para uso futuro quando get_pending_cases suportar filtragem
        cases = queue.get_pending_cases(limit=limit)

        return QueueResponse(
            queue_size=queue_size, cases=cases, filters_applied={"limit": limit, "status": status}
        )

    except Exception as e:
        logger.error("Failed to get queue", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get queue: {e!s}",
        )


@router.post("/{queue_id}/claim", response_model=ClaimResponse)
async def claim_case(queue_id: str, request: ClaimRequest, queue=Depends(get_feedback_queue)):
    """
    Reivindica caso da fila para revisão manual.

    Marca o caso como "in_review" e define expiração de 1 hora.
    """
    try:
        result = queue.claim_case(queue_id=queue_id, assigned_to=request.assigned_to)

        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Case {queue_id} not found or already claimed",
            )

        # Converter datetime para string ISO
        result["claimed_at"] = result["claimed_at"].isoformat()
        result["expires_at"] = result["expires_at"].isoformat()

        return ClaimResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to claim case", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to claim case: {e!s}",
        )


@router.post("/{queue_id}/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    queue_id: str,
    http_request: Request,
    request: FeedbackRequest,
    queue=Depends(get_feedback_queue),
):
    """
    Submete feedback manual para caso prioritário.

    Marca o caso como completado e associa feedback submetido.
    """
    try:
        # Submeter feedback via FeedbackCollector
        feedback_collector = getattr(http_request.app.state, "feedback_collector", None)

        feedback_id = None
        if feedback_collector:
            # Criar documento de feedback
            feedback_data = {
                "queue_id": queue_id,
                "human_recommendation": request.human_recommendation,
                "human_rating": request.human_rating,
                "feedback_notes": request.feedback_notes,
                "submitted_by": request.submitted_by,
                "balanced_dataset": True,  # Marcado como balanceado
                "collection_method": "active_learning",
            }

            # Obter plan_id do caso
            queued_case = queue.collection.find_one({"queue_id": queue_id})
            if queued_case:
                feedback_data["plan_id"] = queued_case.get("plan_id")

            feedback_id = feedback_collector.submit_feedback(feedback_data)

        # Marcar caso como completado
        result = queue.mark_feedback_submitted(
            queue_id=queue_id, feedback_id=feedback_id or f"manual-{queue_id}"
        )

        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Case {queue_id} not found"
            )

        return FeedbackResponse(
            queue_id=queue_id,
            feedback_id=feedback_id or "",
            status=result["status"],
            submitted_at=datetime.now(timezone.utc).isoformat(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to submit feedback", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit feedback: {e!s}",
        )


@router.post("/{queue_id}/release")
async def release_case(queue_id: str, queue=Depends(get_feedback_queue)):
    """
    Libera caso da fila (ex: usuário decidiu não revisar).

    Retorna o caso para status "pending" permitindo que outros usuários o reivindiquem.
    """
    try:
        result = queue.release_case(queue_id=queue_id)

        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Case {queue_id} not found"
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to release case", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to release case: {e!s}",
        )
