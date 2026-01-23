"""API endpoints para operações de tickets."""
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import uuid4

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


class CompensationTicketRequest(BaseModel):
    """Request para criação de ticket de compensação."""
    original_ticket_id: str
    reason: str
    compensation_action: str
    parameters: Dict[str, Any] = {}


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


@router.post('/compensation', response_model=dict)
async def create_compensation_ticket(request: CompensationTicketRequest):
    """
    Cria ticket de compensacao para reverter operacao falhada.

    Args:
        request: Dados do ticket de compensacao

    Returns:
        Ticket de compensacao criado
    """
    postgres_client = await get_postgres_client()

    # Buscar ticket original
    original_ticket_orm = await postgres_client.get_ticket_by_id(request.original_ticket_id)
    if not original_ticket_orm:
        raise HTTPException(
            status_code=404,
            detail=f'Ticket original nao encontrado: {request.original_ticket_id}'
        )

    original_ticket = original_ticket_orm.to_pydantic()

    # Validar que ticket original esta em estado FAILED ou RUNNING
    if original_ticket.status not in [TicketStatus.FAILED, TicketStatus.RUNNING]:
        raise HTTPException(
            status_code=400,
            detail=f'Ticket original deve estar em estado FAILED ou RUNNING, atual: {original_ticket.status.value}'
        )

    # Criar ticket de compensacao
    compensation_ticket_id = str(uuid4())
    compensation_parameters = {
        'action': request.compensation_action,
        'reason': request.reason,
        'original_ticket_id': request.original_ticket_id,
        'original_task_type': original_ticket.task_type,
        **request.parameters
    }

    # Criar modelo do ticket de compensacao
    compensation_ticket_data = {
        'ticket_id': compensation_ticket_id,
        'task_id': f'compensate-{request.original_ticket_id[:8]}',
        'plan_id': original_ticket.plan_id,
        'intent_id': original_ticket.intent_id,
        'task_type': 'COMPENSATE',
        'status': TicketStatus.PENDING.value,
        'priority': original_ticket.priority,
        'risk_band': original_ticket.risk_band or 'high',
        'parameters': compensation_parameters,
        'dependencies': [],  # Compensacao nao tem dependencias
        'compensation_ticket_id': None,  # Este E o ticket de compensacao
        'sla': {
            'timeout_ms': 120000,  # 2 minutos para compensacao
            'deadline': None
        },
        'created_at': int(datetime.utcnow().timestamp() * 1000),
        'metadata': {
            'compensation_reason': request.reason,
            'original_task_type': original_ticket.task_type,
            'original_status': original_ticket.status.value
        }
    }

    # Persistir ticket de compensacao
    try:
        await postgres_client.create_ticket(compensation_ticket_data)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f'Falha ao criar ticket de compensacao: {str(e)}'
        )

    # Atualizar ticket original com referencia ao ticket de compensacao
    try:
        await postgres_client.update_ticket_compensation(
            ticket_id=request.original_ticket_id,
            compensation_ticket_id=compensation_ticket_id,
            status=TicketStatus.COMPENSATING.value if hasattr(TicketStatus, 'COMPENSATING') else 'COMPENSATING'
        )
    except Exception as e:
        # Log warning mas nao falhar a operacao
        pass

    return {
        'ticket_id': compensation_ticket_id,
        'original_ticket_id': request.original_ticket_id,
        'status': 'PENDING',
        'action': request.compensation_action,
        'reason': request.reason
    }
