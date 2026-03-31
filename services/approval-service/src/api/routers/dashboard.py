"""
Dashboard API Endpoints

Endpoints REST para dashboard de aprovações com métricas e estatísticas.
"""

from typing import Optional, List
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from src.config.settings import Settings, get_settings
from src.security.auth import get_current_admin_user
from src.services.approval_service import ApprovalService
from .approvals import get_approval_service

logger = __import__('structlog').get_logger()

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


class DashboardStats(BaseModel):
    """Estatísticas gerais do dashboard"""
    total_approvals: int
    pending_approvals: int
    approved_today: int
    rejected_today: int
    auto_approved_rate: float
    avg_response_time_minutes: float


class ApprovalTrend(BaseModel):
    """Tendência de aprovações por período"""
    date: str
    approved: int
    rejected: int
    auto_approved: int
    total: int


class RiskBandStats(BaseModel):
    """Estatísticas por banda de risco"""
    risk_band: str
    total: int
    approved: int
    rejected: int
    pending: int
    approval_rate: float


class SpecialistStats(BaseModel):
    """Estatísticas por especialista"""
    specialist_id: str
    specialist_name: str
    total_opinions: int
    approved: int
    rejected: int
    approval_rate: float


class MLPerformanceStats(BaseModel):
    """Métricas de desempenho do modelo ML"""
    model_version: str
    total_predictions: int
    correct_predictions: int
    accuracy: float
    precision: float
    recall: float
    auto_approve_rate: float
    auto_reject_rate: float


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    days: int = Query(default=7, ge=1, le=90, description="Período em dias"),
    user: dict = Depends(get_current_admin_user),
    service: ApprovalService = Depends(get_approval_service)
):
    """
    Obtém estatísticas gerais para o dashboard.

    Args:
        days: Período de análise em dias (1-90)
        user: Usuário admin autenticado
        service: Serviço de aprovação

    Returns:
        Estatísticas agregadas do dashboard
    """
    logger.info('Obtendo estatísticas do dashboard', user_id=user['user_id'], days=days)

    # Calcular data de início
    start_date = datetime.now(timezone.utc) - timedelta(days=days)

    # Buscar estatísticas do MongoDB
    try:
        total_approvals = await service.db.plan_approvals.count_documents({
            'created_at': {'$gte': start_date}
        })

        pending_approvals = await service.db.plan_approvals.count_documents({
            'status': 'pending'
        })

        # Aprovações de hoje
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        approved_today = await service.db.plan_approvals.count_documents({
            'status': 'approved',
            'decision_timestamp': {'$gte': today_start}
        })

        rejected_today = await service.db.plan_approvals.count_documents({
            'status': 'rejected',
            'decision_timestamp': {'$gte': today_start}
        })

        # Taxa de auto-aprovação (últimos 7 dias)
        week_start = datetime.now(timezone.utc) - timedelta(days=7)
        total_week = await service.db.plan_approvals.count_documents({
            'created_at': {'$gte': week_start}
        })
        auto_approved = await service.db.plan_approvals.count_documents({
            'created_at': {'$gte': week_start},
            'auto_decided': True,
            'status': 'approved'
        })
        auto_approved_rate = (auto_approved / total_week * 100) if total_week > 0 else 0.0

        # Tempo médio de resposta (aproximado)
        # Em produção, calcularíamos a média real dos tempos de decisão
        avg_response_time_minutes = 15.0  # Valor default

        return DashboardStats(
            total_approvals=total_approvals,
            pending_approvals=pending_approvals,
            approved_today=approved_today,
            rejected_today=rejected_today,
            auto_approved_rate=round(auto_approved_rate, 2),
            avg_response_time_minutes=round(avg_response_time_minutes, 2)
        )

    except Exception as e:
        logger.error('Erro ao obter estatísticas', error=str(e))
        # Retornar valores vazios em caso de erro
        return DashboardStats(
            total_approvals=0,
            pending_approvals=0,
            approved_today=0,
            rejected_today=0,
            auto_approved_rate=0.0,
            avg_response_time_minutes=0.0
        )


@router.get("/trends", response_model=List[ApprovalTrend])
async def get_approval_trends(
    days: int = Query(default=30, ge=1, le=90, description="Período em dias"),
    user: dict = Depends(get_current_admin_user),
    service: ApprovalService = Depends(get_approval_service)
):
    """
    Obtém tendência de aprovações por dia.

    Args:
        days: Período de análise em dias
        user: Usuário admin autenticado
        service: Serviço de aprovação

    Returns:
        Lista de tendências diárias
    """
    logger.info('Obtendo tendências de aprovação', user_id=user['user_id'], days=days)

    trends = []
    for i in range(days):
        date = datetime.now(timezone.utc) - timedelta(days=i)
        day_start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)

        try:
            total = await service.db.plan_approvals.count_documents({
                'created_at': {'$gte': day_start, '$lt': day_end}
            })

            approved = await service.db.plan_approvals.count_documents({
                'created_at': {'$gte': day_start, '$lt': day_end},
                'status': 'approved'
            })

            rejected = await service.db.plan_approvals.count_documents({
                'created_at': {'$gte': day_start, '$lt': day_end},
                'status': 'rejected'
            })

            auto_approved = await service.db.plan_approvals.count_documents({
                'created_at': {'$gte': day_start, '$lt': day_end},
                'auto_decided': True,
                'status': 'approved'
            })

            trends.append(ApprovalTrend(
                date=day_start.strftime('%Y-%m-%d'),
                approved=approved,
                rejected=rejected,
                auto_approved=auto_approved,
                total=total
            ))

        except Exception as e:
            logger.warning('Erro ao obter tendências para o dia', date=day_start, error=str(e))
            continue

    # Inverter para ordem cronológica
    return list(reversed(trends))


@router.get("/by-risk-band", response_model=List[RiskBandStats])
async def get_stats_by_risk_band(
    user: dict = Depends(get_current_admin_user),
    service: ApprovalService = Depends(get_approval_service)
):
    """
    Obtém estatísticas agrupadas por banda de risco.

    Args:
        user: Usuário admin autenticado
        service: Serviço de aprovação

    Returns:
        Lista de estatísticas por banda de risco
    """
    logger.info('Obtendo estatísticas por banda de risco', user_id=user['user_id'])

    risk_bands = ['critical', 'high', 'normal', 'low']
    stats = []

    for band in risk_bands:
        try:
            total = await service.db.plan_approvals.count_documents({
                'risk_band': band
            })

            approved = await service.db.plan_approvals.count_documents({
                'risk_band': band,
                'status': 'approved'
            })

            rejected = await service.db.plan_approvals.count_documents({
                'risk_band': band,
                'status': 'rejected'
            })

            pending = await service.db.plan_approvals.count_documents({
                'risk_band': band,
                'status': 'pending'
            })

            approval_rate = (approved / total * 100) if total > 0 else 0.0

            stats.append(RiskBandStats(
                risk_band=band,
                total=total,
                approved=approved,
                rejected=rejected,
                pending=pending,
                approval_rate=round(approval_rate, 2)
            ))

        except Exception as e:
            logger.warning('Erro ao obter estatísticas para banda', band=band, error=str(e))
            continue

    return stats


@router.get("/ml-performance", response_model=MLPerformanceStats)
async def get_ml_performance_stats(
    user: dict = Depends(get_current_admin_user),
    service: ApprovalService = Depends(get_approval_service)
):
    """
    Obtém métricas de desempenho do modelo ML.

    Args:
        user: Usuário admin autenticado
        service: Serviço de aprovação

    Returns:
        Métricas de desempenho do modelo
    """
    logger.info('Obtendo métricas de performance ML', user_id=user['user_id'])

    # Buscar da coleção de feedback do especialista
    try:
        total_predictions = await service.db.specialist_feedback.count_documents({})

        # Predições corretas (feedback coincide com predição)
        correct_predictions = await service.db.specialist_feedback.count_documents({
            '$or': [
                {'prediction': 'approve', 'decision': 'approved'},
                {'prediction': 'reject', 'decision': 'rejected'}
            ]
        })

        # Calcular métricas
        accuracy = (correct_predictions / total_predictions * 100) if total_predictions > 0 else 0.0

        # Precision (predições positivas corretas / total predições positivas)
        predicted_approve = await service.db.specialist_feedback.count_documents({
            'prediction': 'approve'
        })
        true_positive = await service.db.specialist_feedback.count_documents({
            'prediction': 'approve',
            'decision': 'approved'
        })
        precision = (true_positive / predicted_approve * 100) if predicted_approve > 0 else 0.0

        # Recall (positivos reais identificados / total positivos reais)
        actual_approve = await service.db.specialist_feedback.count_documents({
            'decision': 'approved'
        })
        recall = (true_positive / actual_approve * 100) if actual_approve > 0 else 0.0

        # Taxas de auto-decisão
        total_auto = await service.db.plan_approvals.count_documents({
            'auto_decided': True
        })
        auto_approve = await service.db.plan_approvals.count_documents({
            'auto_decided': True,
            'status': 'approved'
        })
        auto_reject = await service.db.plan_approvals.count_documents({
            'auto_decided': True,
            'status': 'rejected'
        })

        auto_approve_rate = (auto_approve / total_auto * 100) if total_auto > 0 else 0.0
        auto_reject_rate = (auto_reject / total_auto * 100) if total_auto > 0 else 0.0

        # Obter versão do modelo
        model_version = "v7.0"  # Default, ou buscar da config

        return MLPerformanceStats(
            model_version=model_version,
            total_predictions=total_predictions,
            correct_predictions=correct_predictions,
            accuracy=round(accuracy, 2),
            precision=round(precision, 2),
            recall=round(recall, 2),
            auto_approve_rate=round(auto_approve_rate, 2),
            auto_reject_rate=round(auto_reject_rate, 2)
        )

    except Exception as e:
        logger.error('Erro ao obter métricas ML', error=str(e))
        return MLPerformanceStats(
            model_version="unknown",
            total_predictions=0,
            correct_predictions=0,
            accuracy=0.0,
            precision=0.0,
            recall=0.0,
            auto_approve_rate=0.0,
            auto_reject_rate=0.0
        )


@router.get("/recent-activity")
async def get_recent_activity(
    limit: int = Query(default=20, ge=1, le=100),
    user: dict = Depends(get_current_admin_user),
    service: ApprovalService = Depends(get_approval_service)
):
    """
    Obtém atividade recente de aprovações.

    Args:
        limit: Limite de resultados
        user: Usuário admin autenticado
        service: Serviço de aprovação

    Returns:
        Lista de atividades recentes
    """
    logger.info('Obtendo atividade recente', user_id=user['user_id'], limit=limit)

    try:
        cursor = service.db.plan_approvals.find().sort('created_at', -1).limit(limit)
        activities = await cursor.to_list(length=limit)

        # Converter para formato de resposta
        result = []
        for activity in activities:
            result.append({
                'plan_id': activity.get('plan_id'),
                'status': activity.get('status'),
                'risk_band': activity.get('risk_band'),
                'is_destructive': activity.get('is_destructive', False),
                'created_at': activity.get('created_at'),
                'auto_decided': activity.get('auto_decided', False),
                'specialist_id': activity.get('specialist_id')
            })

        return result

    except Exception as e:
        logger.error('Erro ao obter atividade recente', error=str(e))
        return []
