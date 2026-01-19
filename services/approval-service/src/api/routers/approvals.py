"""
Approval API Endpoints

Endpoints REST para gerenciamento de aprovacoes de planos cognitivos.
"""

import structlog
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo.errors import DuplicateKeyError

from src.config.settings import Settings, get_settings
from src.models.approval import (
    ApprovalRequest,
    ApprovalDecision,
    ApprovalStats,
    ApproveRequestBody,
    RejectRequestBody,
    RiskBand
)
from src.security.auth import get_current_admin_user
from src.services.approval_service import ApprovalService

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/approvals", tags=["approvals"])

# Referencia global para o servico
_approval_service: Optional[ApprovalService] = None


def set_approval_service(service: ApprovalService):
    """Define referencia para o servico de aprovacao"""
    global _approval_service
    _approval_service = service


def get_approval_service() -> ApprovalService:
    """Obtem servico de aprovacao"""
    if _approval_service is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Servico de aprovacao nao inicializado"
        )
    return _approval_service


@router.get("/pending", response_model=List[ApprovalRequest])
async def list_pending_approvals(
    limit: int = Query(default=50, ge=1, le=100, description="Limite de resultados"),
    offset: int = Query(default=0, ge=0, description="Offset para paginacao"),
    risk_band: Optional[RiskBand] = Query(default=None, description="Filtro por banda de risco"),
    is_destructive: Optional[bool] = Query(default=None, description="Filtro por destrutivo"),
    user: dict = Depends(get_current_admin_user),
    service: ApprovalService = Depends(get_approval_service)
):
    """
    Lista aprovacoes pendentes

    Requer autenticacao JWT e role neural-hive-admin.

    Args:
        limit: Limite de resultados (max 100)
        offset: Offset para paginacao
        risk_band: Filtro opcional por banda de risco
        is_destructive: Filtro opcional por operacoes destrutivas
        user: Usuario admin autenticado
        service: Servico de aprovacao

    Returns:
        Lista de aprovacoes pendentes ordenadas por data (DESC)
    """
    logger.info(
        'Listando aprovacoes pendentes',
        user_id=user['user_id'],
        limit=limit,
        offset=offset,
        risk_band=risk_band,
        is_destructive=is_destructive
    )

    try:
        approvals = await service.get_pending_approvals(
            limit=limit,
            offset=offset,
            risk_band=risk_band.value if risk_band else None,
            is_destructive=is_destructive
        )
        return approvals

    except Exception as e:
        logger.error('Erro ao listar aprovacoes pendentes', error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao listar aprovacoes: {str(e)}"
        )


@router.get("/stats", response_model=ApprovalStats)
async def get_approval_stats(
    user: dict = Depends(get_current_admin_user),
    service: ApprovalService = Depends(get_approval_service)
):
    """
    Retorna estatisticas de aprovacao

    Requer autenticacao JWT e role neural-hive-admin.

    Args:
        user: Usuario admin autenticado
        service: Servico de aprovacao

    Returns:
        Estatisticas agregadas de aprovacoes
    """
    logger.info('Consultando estatisticas de aprovacao', user_id=user['user_id'])

    try:
        stats = await service.get_approval_stats()
        return stats

    except Exception as e:
        logger.error('Erro ao obter estatisticas', error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao obter estatisticas: {str(e)}"
        )


@router.get("/{plan_id}", response_model=ApprovalRequest)
async def get_approval(
    plan_id: str,
    user: dict = Depends(get_current_admin_user),
    service: ApprovalService = Depends(get_approval_service)
):
    """
    Busca aprovacao por plan_id

    Requer autenticacao JWT e role neural-hive-admin.

    Args:
        plan_id: ID do plano cognitivo
        user: Usuario admin autenticado
        service: Servico de aprovacao

    Returns:
        Detalhes da aprovacao incluindo cognitive_plan completo

    Raises:
        404: Se plan_id nao encontrado
    """
    logger.info(
        'Buscando aprovacao',
        plan_id=plan_id,
        user_id=user['user_id']
    )

    try:
        approval = await service.get_approval_by_plan_id(plan_id)
        if not approval:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Plano nao encontrado: {plan_id}"
            )
        return approval

    except HTTPException:
        raise
    except Exception as e:
        logger.error('Erro ao buscar aprovacao', error=str(e), plan_id=plan_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao buscar aprovacao: {str(e)}"
        )


@router.post("/{plan_id}/approve", response_model=ApprovalDecision)
async def approve_plan(
    plan_id: str,
    body: Optional[ApproveRequestBody] = None,
    user: dict = Depends(get_current_admin_user),
    service: ApprovalService = Depends(get_approval_service)
):
    """
    Aprova um plano cognitivo

    Requer autenticacao JWT e role neural-hive-admin.

    Args:
        plan_id: ID do plano cognitivo
        body: Comentarios opcionais
        user: Usuario admin autenticado
        service: Servico de aprovacao

    Returns:
        Decisao de aprovacao

    Raises:
        404: Se plan_id nao encontrado
        409: Se plano ja foi aprovado/rejeitado
    """
    comments = body.comments if body else None

    logger.info(
        'Aprovando plano',
        plan_id=plan_id,
        user_id=user['user_id'],
        has_comments=bool(comments)
    )

    try:
        decision = await service.approve_plan(
            plan_id=plan_id,
            user_id=user['user_id'],
            comments=comments
        )
        return decision

    except ValueError as e:
        error_msg = str(e)
        if 'nao encontrado' in error_msg:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_msg
            )
        elif 'nao esta pendente' in error_msg:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=error_msg
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg
            )
    except Exception as e:
        logger.error('Erro ao aprovar plano', error=str(e), plan_id=plan_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao aprovar plano: {str(e)}"
        )


@router.post("/{plan_id}/reject", response_model=ApprovalDecision)
async def reject_plan(
    plan_id: str,
    body: RejectRequestBody,
    user: dict = Depends(get_current_admin_user),
    service: ApprovalService = Depends(get_approval_service)
):
    """
    Rejeita um plano cognitivo

    Requer autenticacao JWT e role neural-hive-admin.

    Args:
        plan_id: ID do plano cognitivo
        body: Motivo da rejeicao (obrigatorio) e comentarios opcionais
        user: Usuario admin autenticado
        service: Servico de aprovacao

    Returns:
        Decisao de rejeicao

    Raises:
        400: Se motivo da rejeicao vazio
        404: Se plan_id nao encontrado
        409: Se plano ja foi aprovado/rejeitado
    """
    logger.info(
        'Rejeitando plano',
        plan_id=plan_id,
        user_id=user['user_id'],
        reason=body.reason
    )

    try:
        decision = await service.reject_plan(
            plan_id=plan_id,
            user_id=user['user_id'],
            reason=body.reason,
            comments=body.comments
        )
        return decision

    except ValueError as e:
        error_msg = str(e)
        if 'nao encontrado' in error_msg:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_msg
            )
        elif 'nao esta pendente' in error_msg:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=error_msg
            )
        elif 'obrigatorio' in error_msg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg
            )
    except Exception as e:
        logger.error('Erro ao rejeitar plano', error=str(e), plan_id=plan_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao rejeitar plano: {str(e)}"
        )
