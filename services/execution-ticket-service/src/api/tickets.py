"""API endpoints para operações de tickets."""
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

import structlog
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..config import get_settings
from ..database import get_mongodb_client, get_postgres_client
from ..models import ExecutionTicket, JWTToken, TicketStatus, generate_token

router = APIRouter(prefix="/api/v1/tickets")


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


@router.get("/{ticket_id}", response_model=ExecutionTicket)
async def get_ticket(ticket_id: str):
    """Busca ticket por ID."""
    postgres_client = await get_postgres_client()
    ticket_orm = await postgres_client.get_ticket_by_id(ticket_id)

    if not ticket_orm:
        raise HTTPException(status_code=404, detail="Ticket not found")

    return ticket_orm.to_pydantic()


@router.post("/", response_model=ExecutionTicket, status_code=201)
async def create_ticket(ticket_data: Dict[str, Any]):
    """
    Cria novo execution ticket via HTTP REST.

    Este endpoint permite criacao sincrona de tickets como alternativa
    ao consumo via Kafka (execution.tickets topic).

    Args:
        ticket_data: Dados do ticket conforme execution-ticket.avsc

    Returns:
        Ticket criado
    """
    logger = structlog.get_logger(__name__)

    postgres_client = await get_postgres_client()

    # Garantir ticket_id se nao fornecido
    if "ticket_id" not in ticket_data or not ticket_data["ticket_id"]:
        ticket_data["ticket_id"] = str(uuid4())

    # Garantir timestamp de criacao se nao fornecido
    if "created_at" not in ticket_data:
        ticket_data["created_at"] = int(datetime.now(timezone.utc).timestamp() * 1000)

    # Garantir status default
    if "status" not in ticket_data:
        ticket_data["status"] = "PENDING"

    # Garantir campos obrigatorios com defaults
    required_defaults = {
        "dependencies": ticket_data.get("dependencies", []),
        "retry_count": ticket_data.get("retry_count", 0),
        "compensation_ticket_id": ticket_data.get("compensation_ticket_id", None),
        "metadata": ticket_data.get("metadata", {}),
        "predictions": ticket_data.get("predictions", None),
        "schema_version": ticket_data.get("schema_version", 1),
    }
    ticket_data.update(required_defaults)

    # Criar modelo Pydantic a partir do dict (Pydantic v2)
    try:
        ticket_pydantic = ExecutionTicket(**ticket_data)
    except Exception as e:
        logger.error("failed_to_validate_ticket", error=str(e), ticket_data=ticket_data)
        raise HTTPException(status_code=422, detail=f"Validation error: {str(e)}")

    # Persistir no PostgreSQL
    try:
        ticket_orm = await postgres_client.create_ticket(ticket_pydantic)
        logger.info(
            "ticket_created_via_http",
            ticket_id=ticket_pydantic.ticket_id,
            plan_id=ticket_pydantic.plan_id,
        )
    except Exception as e:
        logger.error("failed_to_persist_ticket", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to create ticket: {str(e)}")

    # Publicar no Kafka para Worker Agents consumirem
    # NOTA: Publicação é assíncrona e não-bloqueante
    # Se falhar, logamos erro mas não falhamos a criação do ticket
    try:
        from ..kafka.producer import get_kafka_producer

        kafka_producer = await get_kafka_producer()

        # Converter ticket para dict para serialização JSON
        ticket_dict = ticket_orm.to_pydantic().model_dump(mode="json")

        # Publicar de forma assíncrona (fire and forget)
        asyncio.create_task(
            kafka_producer.publish_ticket(ticket=ticket_dict, key=ticket_dict["ticket_id"])
        )
        logger.info(
            "ticket_publish_scheduled",
            ticket_id=ticket_dict["ticket_id"],
            topic=kafka_producer._topic,
        )
    except Exception as e:
        # Kafka producer não está disponível - logar warning mas continuar
        # O ticket já está persistido no PostgreSQL
        logger.warning(
            "kafka_publisher_unavailable_ticket_not_published",
            ticket_id=ticket_pydantic.ticket_id,
            error=str(e),
            note="Ticket persisted in PostgreSQL but not published to Kafka. Workers will not consume this ticket.",
        )

    return ticket_orm.to_pydantic()


@router.get("/", response_model=dict)
async def list_tickets(
    plan_id: Optional[str] = Query(None),
    intent_id: Optional[str] = Query(None),
    status: Optional[TicketStatus] = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
):
    """Lista tickets com filtros."""
    postgres_client = await get_postgres_client()

    filters = {}
    if plan_id:
        filters["plan_id"] = plan_id
    if intent_id:
        filters["intent_id"] = intent_id
    if status:
        # Handle both enum and string values
        filters["status"] = status.value if hasattr(status, "value") else status

    tickets_orm = await postgres_client.list_tickets(filters, offset, limit)
    total = await postgres_client.count_tickets(filters)

    tickets = [t.to_pydantic() for t in tickets_orm]

    return {"tickets": tickets, "total": total, "offset": offset, "limit": limit}


@router.patch("/{ticket_id}/status", response_model=ExecutionTicket)
async def update_ticket_status(ticket_id: str, request: StatusUpdateRequest):
    """Atualiza status do ticket."""
    postgres_client = await get_postgres_client()

    # Verificar se ticket existe
    ticket_orm = await postgres_client.get_ticket_by_id(ticket_id)
    if not ticket_orm:
        raise HTTPException(status_code=404, detail="Ticket not found")

    # Atualizar status
    updated_orm = await postgres_client.update_ticket_status(
        ticket_id, request.status, request.error_message
    )

    if not updated_orm:
        raise HTTPException(status_code=500, detail="Failed to update ticket")

    return updated_orm.to_pydantic()


@router.get("/{ticket_id}/token", response_model=JWTToken)
async def get_ticket_token(ticket_id: str):
    """Gera token JWT escopado para o ticket."""
    postgres_client = await get_postgres_client()
    settings = get_settings()

    # Buscar ticket
    ticket_orm = await postgres_client.get_ticket_by_id(ticket_id)
    if not ticket_orm:
        raise HTTPException(status_code=404, detail="Ticket not found")

    ticket = ticket_orm.to_pydantic()

    # Validar que ticket está PENDING ou RUNNING
    if ticket.status not in [TicketStatus.PENDING, TicketStatus.RUNNING]:
        raise HTTPException(
            status_code=403,
            detail=f"Cannot generate token for ticket with status {ticket.status.value}",
        )

    # Gerar token
    token = generate_token(
        ticket,
        settings.jwt_secret_key,
        settings.jwt_algorithm,
        settings.jwt_token_expiration_seconds,
    )

    return token


@router.post("/compensation", response_model=dict)
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
            status_code=404, detail=f"Ticket original nao encontrado: {request.original_ticket_id}"
        )

    original_ticket = original_ticket_orm.to_pydantic()

    # Validar que ticket original esta em estado FAILED ou RUNNING
    if original_ticket.status not in [TicketStatus.FAILED, TicketStatus.RUNNING]:
        raise HTTPException(
            status_code=400,
            detail=f"Ticket original deve estar em estado FAILED ou RUNNING, atual: {original_ticket.status.value}",
        )

    # Criar ticket de compensacao
    compensation_ticket_id = str(uuid4())
    compensation_parameters = {
        "action": request.compensation_action,
        "reason": request.reason,
        "original_ticket_id": request.original_ticket_id,
        "original_task_type": original_ticket.task_type,
        **request.parameters,
    }

    # Criar modelo do ticket de compensacao
    compensation_ticket_data = {
        "ticket_id": compensation_ticket_id,
        "task_id": f"compensate-{request.original_ticket_id[:8]}",
        "plan_id": original_ticket.plan_id,
        "intent_id": original_ticket.intent_id,
        "task_type": "COMPENSATE",
        "status": TicketStatus.PENDING.value,
        "priority": original_ticket.priority,
        "risk_band": original_ticket.risk_band or "high",
        "parameters": compensation_parameters,
        "dependencies": [],  # Compensacao nao tem dependencias
        "compensation_ticket_id": None,  # Este E o ticket de compensacao
        "sla": {"timeout_ms": 120000, "deadline": None},  # 2 minutos para compensacao
        "created_at": int(datetime.now(timezone.utc).timestamp() * 1000),
        "metadata": {
            "compensation_reason": request.reason,
            "original_task_type": original_ticket.task_type,
            "original_status": original_ticket.status.value,
        },
    }

    # Persistir ticket de compensacao
    try:
        await postgres_client.create_ticket(compensation_ticket_data)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Falha ao criar ticket de compensacao: {str(e)}"
        )

    # Atualizar ticket original com referencia ao ticket de compensacao
    try:
        await postgres_client.update_ticket_compensation(
            ticket_id=request.original_ticket_id,
            compensation_ticket_id=compensation_ticket_id,
            status=TicketStatus.COMPENSATING.value
            if hasattr(TicketStatus, "COMPENSATING")
            else "COMPENSATING",
        )
    except Exception:
        # Log warning mas nao falhar a operacao
        pass

    return {
        "ticket_id": compensation_ticket_id,
        "original_ticket_id": request.original_ticket_id,
        "status": "PENDING",
        "action": request.compensation_action,
        "reason": request.reason,
    }


@router.post("/{ticket_id}/retry", response_model=ExecutionTicket)
async def retry_ticket(ticket_id: str):
    """
    Retry manual de ticket falhado.

    Incrementa o contador de retry e reseta o status para PENDING,
    permitindo que o Worker Agent processe novamente o ticket.

    Args:
        ticket_id: ID do ticket para retry

    Returns:
        Ticket atualizado com status PENDING

    Raises:
        404: Se ticket não encontrado
        400: Se ticket não está em estado FAILED
    """
    logger = structlog.get_logger(__name__)
    postgres_client = await get_postgres_client()

    # Buscar ticket
    ticket_orm = await postgres_client.get_ticket_by_id(ticket_id)
    if not ticket_orm:
        raise HTTPException(status_code=404, detail=f"Ticket não encontrado: {ticket_id}")

    ticket = ticket_orm.to_pydantic()

    # Validar que ticket está em estado FAILED
    if ticket.status != TicketStatus.FAILED:
        raise HTTPException(
            status_code=400,
            detail=f"Ticket deve estar em estado FAILED para retry, atual: {ticket.status.value}",
        )

    # Verificar limite de retries (do SLA)
    max_retries = ticket.sla.max_retries if ticket.sla else 3
    if ticket.retry_count >= max_retries:
        raise HTTPException(
            status_code=400,
            detail=f"Limite de retries excedido: {ticket.retry_count}/{max_retries}",
        )

    # Incrementar retry e resetar para PENDING
    updated_orm = await postgres_client.increment_retry_count(ticket_id)

    if not updated_orm:
        raise HTTPException(status_code=500, detail="Falha ao agendar retry do ticket")

    # Log status change no MongoDB audit trail
    try:
        mongodb_client = await get_mongodb_client()
        await mongodb_client.log_status_change(
            ticket_id=ticket_id,
            old_status="FAILED",
            new_status="PENDING",
            changed_by="api.retry",
            metadata={
                "retry_count": updated_orm.retry_count,
                "trigger": "manual_retry",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
    except Exception as e:
        logger.warning("mongodb_audit_log_failed", ticket_id=ticket_id, error=str(e))

    logger.info("ticket_retried_manually", ticket_id=ticket_id, retry_count=updated_orm.retry_count)

    return updated_orm.to_pydantic()


class TicketHistoryEntry(BaseModel):
    """Entrada de histórico de mudanças do ticket."""

    ticket_id: str
    timestamp: str
    old_status: Optional[str]
    new_status: str
    changed_by: str
    metadata: Dict[str, Any]


@router.get("/{ticket_id}/history", response_model=List[TicketHistoryEntry])
async def get_ticket_history(ticket_id: str, limit: int = Query(100, ge=1, le=1000)):
    """
    Retorna histórico de mudanças de status do ticket.

    Busca do MongoDB audit trail todas as mudanças de status
    registradas para o ticket especificado.

    Args:
        ticket_id: ID do ticket
        limit: Número máximo de entradas a retornar

    Returns:
        Lista de entradas de histórico ordenadas por timestamp (mais recente primeiro)

    Raises:
        404: Se ticket não encontrado
    """
    logger = structlog.get_logger(__name__)
    postgres_client = await get_postgres_client()

    # Verificar se ticket existe
    ticket_orm = await postgres_client.get_ticket_by_id(ticket_id)
    if not ticket_orm:
        raise HTTPException(status_code=404, detail=f"Ticket não encontrado: {ticket_id}")

    # Buscar histórico do MongoDB
    try:
        mongodb_client = await get_mongodb_client()
        audit_collection = mongodb_client.db[mongodb_client.settings.mongodb_collection_audit]
        history_cursor = (
            audit_collection.find({"ticket_id": ticket_id}).sort("timestamp", -1).limit(limit)
        )

        history_docs = await history_cursor.to_list(length=limit)

        # Converter para formato de resposta
        history_entries = []
        for doc in history_docs:
            timestamp = doc.get("timestamp")
            if isinstance(timestamp, datetime):
                timestamp_str = timestamp.isoformat()
            else:
                timestamp_str = datetime.now(timezone.utc).isoformat()

            entry = TicketHistoryEntry(
                ticket_id=doc.get("ticket_id", ticket_id),
                timestamp=timestamp_str,
                old_status=doc.get("old_status"),
                new_status=doc.get("new_status", "UNKNOWN"),
                changed_by=doc.get("changed_by", "unknown"),
                metadata=doc.get("metadata", {}),
            )
            history_entries.append(entry)

        logger.info(
            "ticket_history_retrieved", ticket_id=ticket_id, entries_count=len(history_entries)
        )

        return history_entries

    except Exception as e:
        logger.error("ticket_history_fetch_failed", ticket_id=ticket_id, error=str(e))
        # Retornar lista vazia em caso de erro no MongoDB
        return []
