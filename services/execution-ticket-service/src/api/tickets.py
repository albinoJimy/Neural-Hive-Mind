"""API endpoints para operações de tickets."""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from ..database import get_db_session, get_postgres_client
from ..models import ExecutionTicket, TicketStatus, generate_token, JWTToken
from ..config import get_settings

router = APIRouter(prefix='/api/v1/tickets')


class StatusUpdateRequest(BaseModel):
    """Request para atualização de status."""
    status: TicketStatus
    error_message: Optional[str] = None
    actual_duration_ms: Optional[int] = None


@router.get('/{ticket_id}', response_model=ExecutionTicket)
async def get_ticket(ticket_id: str):
    """Busca ticket por ID."""
    postgres_client = await get_postgres_client()
    ticket_orm = await postgres_client.get_ticket_by_id(ticket_id)

    if not ticket_orm:
        raise HTTPException(status_code=404, detail='Ticket not found')

    return ticket_orm.to_pydantic()


@router.get('/', response_model=dict)
async def list_tickets(
    plan_id: Optional[str] = Query(None),
    intent_id: Optional[str] = Query(None),
    status: Optional[TicketStatus] = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000)
):
    """Lista tickets com filtros."""
    postgres_client = await get_postgres_client()

    filters = {}
    if plan_id:
        filters['plan_id'] = plan_id
    if intent_id:
        filters['intent_id'] = intent_id
    if status:
        filters['status'] = status.value

    tickets_orm = await postgres_client.list_tickets(filters, offset, limit)
    total = await postgres_client.count_tickets(filters)

    tickets = [t.to_pydantic() for t in tickets_orm]

    return {
        'tickets': tickets,
        'total': total,
        'offset': offset,
        'limit': limit
    }


@router.patch('/{ticket_id}/status', response_model=ExecutionTicket)
async def update_ticket_status(ticket_id: str, request: StatusUpdateRequest):
    """Atualiza status do ticket."""
    postgres_client = await get_postgres_client()

    # Verificar se ticket existe
    ticket_orm = await postgres_client.get_ticket_by_id(ticket_id)
    if not ticket_orm:
        raise HTTPException(status_code=404, detail='Ticket not found')

    # Atualizar status
    updated_orm = await postgres_client.update_ticket_status(
        ticket_id,
        request.status,
        request.error_message
    )

    if not updated_orm:
        raise HTTPException(status_code=500, detail='Failed to update ticket')

    return updated_orm.to_pydantic()


@router.get('/{ticket_id}/token', response_model=JWTToken)
async def get_ticket_token(ticket_id: str):
    """Gera token JWT escopado para o ticket."""
    postgres_client = await get_postgres_client()
    settings = get_settings()

    # Buscar ticket
    ticket_orm = await postgres_client.get_ticket_by_id(ticket_id)
    if not ticket_orm:
        raise HTTPException(status_code=404, detail='Ticket not found')

    ticket = ticket_orm.to_pydantic()

    # Validar que ticket está PENDING ou RUNNING
    if ticket.status not in [TicketStatus.PENDING, TicketStatus.RUNNING]:
        raise HTTPException(
            status_code=403,
            detail=f'Cannot generate token for ticket with status {ticket.status.value}'
        )

    # Gerar token
    token = generate_token(
        ticket,
        settings.jwt_secret_key,
        settings.jwt_algorithm,
        settings.jwt_token_expiration_seconds
    )

    return token
