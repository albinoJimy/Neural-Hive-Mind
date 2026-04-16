"""Router REST para Approval Gateway."""

from typing import Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, status, Query
from structlog import get_logger

from src.models.approval import (
    ApprovalRequest,
    ApprovalDecision,
    ApprovalStatus,
    ApprovalType,
    ApprovalMetrics,
)
from src.services.approval_gateway import ApprovalGateway
from src.api.schemas.approval_requests import (
    CreateApprovalRequest,
    UpdateApprovalRequest,
    ApprovalResponse,
    ApprovalListResponse,
)
from src.repositories.approvals_repository import ApprovalsRepository

logger = get_logger(__name__)

router = APIRouter(prefix="/approvals", tags=["approvals"])

# Singleton
_gateway_service: Optional[ApprovalGateway] = None
_repository: Optional[ApprovalsRepository] = None


def get_gateway_service() -> ApprovalGateway:
    """Retorna instância singleton."""
    global _gateway_service
    if _gateway_service is None:
        _gateway_service = ApprovalGateway()
    return _gateway_service


def get_repository() -> ApprovalsRepository:
    """Retorna instância do repositório."""
    global _repository
    if _repository is None:
        _repository = ApprovalsRepository()
    return _repository


@router.post(
    "/request",
    response_model=ApprovalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar solicitação de aprovação"
)
async def create_approval_request(request: CreateApprovalRequest) -> ApprovalResponse:
    """
    Cria uma nova solicitação de aprovação e a avalia automaticamente.

    A avaliação pode resultar em:
    - Aprovação automática (alta confiança)
    - Rejeição automática (baixa confiança)
    - Requer revisão humana (confiança média)
    """
    service = get_gateway_service()

    try:
        # Criar solicitação
        approval_request = ApprovalRequest(
            id=f"REQ-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            type=request.type,
            title=request.title,
            description=request.description,
            requested_by=request.requested_by,
            context=request.context or {},
            expires_at=datetime.utcnow() + timedelta(hours=request.expires_in_hours)
        )

        # Avaliar
        decision = await service.evaluate_request(approval_request)

        return ApprovalResponse(
            request_id=approval_request.id,
            status=decision.status,
            confidence_score=decision.confidence_score,
            reasoning=decision.reasoning,
            approved_by=decision.approved_by,
            requires_human_review=(decision.status == ApprovalStatus.PENDING)
        )

    except Exception as e:
        logger.error("create_approval_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Falha ao criar solicitação: {str(e)}"
        )


@router.get(
    "/{request_id}",
    response_model=ApprovalResponse,
    summary="Buscar solicitação por ID"
)
async def get_approval_request(request_id: str) -> ApprovalResponse:
    """Retorna uma solicitação específica."""
    repository = get_repository()

    doc = await repository.get_by_request_id(request_id)

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Solicitação {request_id} não encontrada"
        )

    return ApprovalResponse(
        request_id=doc["request"]["id"],
        status=ApprovalStatus(doc["decision"]["status"]),
        confidence_score=doc["decision"]["confidence_score"],
        reasoning=doc["decision"]["reasoning"],
        approved_by=doc["decision"].get("approved_by"),
        requires_human_review=(doc["decision"]["status"] == ApprovalStatus.PENDING.value)
    )


@router.put(
    "/{request_id}",
    response_model=ApprovalResponse,
    summary="Atualizar decisão (intervenção humana)"
)
async def update_approval_request(
    request_id: str,
    update: UpdateApprovalRequest
) -> ApprovalResponse:
    """
    Atualiza uma solicitação (intervenção humana).

    Usado quando um revisor humano aprova ou rejeita manualmente
    uma solicitação que estava pendente.
    """
    repository = get_repository()

    # Verificar se existe
    doc = await repository.get_by_request_id(request_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Solicitação {request_id} não encontrada"
        )

    # Atualizar
    updated = await repository.update_decision(
        request_id=request_id,
        status=update.status,
        approved_by=update.reviewed_by,
        feedback=update.feedback
    )

    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao atualizar solicitação"
        )

    # Buscar atualizado
    doc = await repository.get_by_request_id(request_id)

    return ApprovalResponse(
        request_id=doc["request"]["id"],
        status=ApprovalStatus(doc["decision"]["status"]),
        confidence_score=doc["decision"]["confidence_score"],
        reasoning=doc["decision"]["reasoning"],
        approved_by=doc["decision"].get("approved_by"),
        requires_human_review=False
    )


@router.get(
    "",
    response_model=ApprovalListResponse,
    summary="Listar solicitações"
)
async def list_approvals(
    status: Optional[ApprovalStatus] = Query(None, description="Filtrar por status"),
    type: Optional[ApprovalType] = Query(None, description="Filtrar por tipo"),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0)
) -> ApprovalListResponse:
    """Lista solicitações com filtros."""
    repository = get_repository()

    items, total = await repository.list(
        status=status,
        approval_type=type,
        limit=limit,
        skip=offset
    )

    pending_count = await repository.count_by_status(ApprovalStatus.PENDING)

    formatted_items = []
    for item in items:
        formatted_items.append({
            "request_id": item["request"]["id"],
            "type": item["request"]["type"],
            "title": item["request"]["title"],
            "status": item["decision"]["status"],
            "confidence_score": item["decision"]["confidence_score"],
            "requested_by": item["request"]["requested_by"],
            "created_at": item["created_at"],
        })

    return ApprovalListResponse(
        total=total,
        pending=pending_count,
        items=formatted_items
    )


@router.get(
    "/metrics",
    response_model=ApprovalMetrics,
    summary="Métricas de aprovações"
)
async def get_metrics() -> ApprovalMetrics:
    """Retorna métricas agregadas de aprovações."""
    service = get_gateway_service()
    return await service.get_metrics()


@router.post(
    "/expire",
    summary="Expirar solicitações pendentes"
)
async def expire_pending_requests(
    timeout_hours: int = Query(24, ge=1, description="Timeout em horas")
) -> dict:
    """Expira solicitações pendentes antigas."""
    service = get_gateway_service()
    expired = await service.expire_pending_requests(timeout_hours)

    return {
        "expired_count": expired,
        "timeout_hours": timeout_hours
    }


@router.get(
    "/health",
    summary="Health check"
)
async def health_check() -> dict:
    """Verifica saúde do serviço."""
    return {
        "status": "healthy",
        "service": "approval-gateway",
        "version": "0.1.0"
    }
