"""
Endpoints para consulta de audit log de modelos ML.

Fornece API REST para consultar histórico de eventos do ciclo de vida
de modelos ML, incluindo treinamentos, validações, promoções e rollbacks.
"""

from fastapi import APIRouter, Query, HTTPException
from typing import List, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel, Field

from ..ml.model_audit_logger import ModelAuditLogger


class AuditEventResponse(BaseModel):
    """Response model para evento de auditoria."""
    audit_id: str
    timestamp: datetime
    event_type: str
    model_name: str
    model_version: str
    user_id: Optional[str] = None
    reason: Optional[str] = None
    duration_seconds: Optional[float] = None
    environment: str
    triggered_by: str
    event_data: dict
    metadata: dict

    class Config:
        """Configuração do modelo."""
        from_attributes = True


class AuditSummaryResponse(BaseModel):
    """Response model para resumo de auditoria."""
    period_days: int
    model_name: str
    events_by_type: dict
    total_events: int


class TimelineResponse(BaseModel):
    """Response model para timeline de eventos."""
    model_name: str
    period_days: int
    versions: dict
    total_events: int


class HealthResponse(BaseModel):
    """Response model para health check."""
    status: str
    enabled: bool
    collection: str


def create_model_audit_router(
    audit_logger: ModelAuditLogger
) -> APIRouter:
    """
    Cria router FastAPI para audit log de modelos.

    Args:
        audit_logger: Instância de ModelAuditLogger

    Returns:
        APIRouter configurado
    """
    router = APIRouter(prefix='/api/v1/ml/audit', tags=['ml-audit'])

    @router.get('/models/{model_name}/history', response_model=List[AuditEventResponse])
    async def get_model_history(
        model_name: str,
        limit: int = Query(100, ge=1, le=1000, description='Número máximo de eventos'),
        event_types: Optional[List[str]] = Query(None, description='Filtrar por tipos de evento')
    ):
        """
        Recupera histórico de eventos de um modelo.

        Args:
            model_name: Nome do modelo
            limit: Número máximo de eventos (1-1000)
            event_types: Filtrar por tipos de evento (opcional)

        Returns:
            Lista de eventos ordenados por timestamp (mais recente primeiro)
        """
        try:
            events = await audit_logger.get_model_history(
                model_name=model_name,
                limit=limit,
                event_types=event_types
            )
            return events
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get('/events/{event_type}', response_model=List[AuditEventResponse])
    async def get_events_by_type(
        event_type: str,
        start_date: Optional[datetime] = Query(None, description='Data inicial'),
        end_date: Optional[datetime] = Query(None, description='Data final'),
        limit: int = Query(100, ge=1, le=1000, description='Número máximo de eventos')
    ):
        """
        Recupera eventos por tipo e período.

        Args:
            event_type: Tipo de evento (training_started, model_promoted, etc)
            start_date: Data inicial (opcional)
            end_date: Data final (opcional)
            limit: Número máximo de eventos

        Returns:
            Lista de eventos
        """
        try:
            events = await audit_logger.get_events_by_type(
                event_type=event_type,
                start_date=start_date,
                end_date=end_date,
                limit=limit
            )
            return events
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get('/summary', response_model=AuditSummaryResponse)
    async def get_audit_summary(
        model_name: Optional[str] = Query(None, description='Nome do modelo (None = todos)'),
        days: int = Query(30, ge=1, le=365, description='Janela de dias')
    ):
        """
        Gera resumo de auditoria.

        Args:
            model_name: Nome do modelo (opcional, None = todos)
            days: Janela de dias (1-365)

        Returns:
            Estatísticas agregadas
        """
        try:
            summary = await audit_logger.get_audit_summary(
                model_name=model_name,
                days=days
            )
            return summary
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get('/models/{model_name}/timeline', response_model=TimelineResponse)
    async def get_model_timeline(
        model_name: str,
        days: int = Query(90, ge=1, le=365, description='Janela de dias')
    ):
        """
        Gera timeline visual de eventos do modelo.

        Args:
            model_name: Nome do modelo
            days: Janela de dias

        Returns:
            Timeline estruturada para visualização
        """
        try:
            timeline = await audit_logger.get_model_timeline(
                model_name=model_name,
                days=days
            )
            return timeline
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get('/events/id/{audit_id}', response_model=Optional[AuditEventResponse])
    async def get_event_by_id(audit_id: str):
        """
        Recupera evento específico por audit_id.

        Args:
            audit_id: ID do evento de auditoria

        Returns:
            Evento de auditoria ou None
        """
        try:
            event = await audit_logger.get_event_by_id(audit_id)
            if not event:
                raise HTTPException(status_code=404, detail='Evento não encontrado')
            return event
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get('/health', response_model=HealthResponse)
    async def health_check():
        """Health check do audit logger."""
        return {
            'status': 'healthy',
            'enabled': audit_logger.enabled,
            'collection': audit_logger.collection_name
        }

    return router
