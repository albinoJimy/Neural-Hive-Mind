"""
API REST para validação manual e consulta de validações de segurança.
"""

from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query, Depends, Request
from pydantic import BaseModel
import structlog

from src.models.security_validation import (
    SecurityValidation,
    ValidationStatus,
    ValidatorType
)

logger = structlog.get_logger(__name__)

router = APIRouter()


class ValidateTicketRequest(BaseModel):
    """Request para validação manual de ticket."""
    ticket: dict


class ApprovalRequest(BaseModel):
    """Request para aprovação/rejeição de validação."""
    reason: Optional[str] = None
    approved_by: str


class ValidationStatistics(BaseModel):
    """Estatísticas agregadas de validações."""
    total_validations: int
    approved_count: int
    rejected_count: int
    pending_approval_count: int
    approval_rate: float
    top_violations: List[dict]
    avg_risk_score: float


@router.post("/validations/validate-ticket")
async def validate_ticket(request: ValidateTicketRequest, fastapi_request: Request):
    """
    Valida um ExecutionTicket manualmente.

    Args:
        request: Request com ticket a ser validado
        fastapi_request: FastAPI Request para acessar app state

    Returns:
        SecurityValidation resultado
    """
    try:
        from fastapi import Request

        logger.info(
            "validation_api.validate_ticket_requested",
            ticket_id=request.ticket.get("ticket_id")
        )

        # Obter security_validator do app state
        security_validator = fastapi_request.app.state.security_validator

        # Validar ticket
        validation = await security_validator.validate_ticket(request.ticket)

        return validation

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "validation_api.validate_ticket_failed",
            error=str(e)
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/validations/{validation_id}")
async def get_validation(validation_id: str, fastapi_request: Request):
    """
    Obtém validação por ID.

    Args:
        validation_id: ID da validação
        fastapi_request: FastAPI Request para acessar app state

    Returns:
        SecurityValidation
    """
    try:
        logger.info(
            "validation_api.get_validation_requested",
            validation_id=validation_id
        )

        # Obter MongoDB do app state
        mongodb = fastapi_request.app.state.mongodb
        from src.config.settings import get_settings
        settings = get_settings()

        # Buscar validação
        collection = mongodb.db[settings.mongodb_validations_collection]
        validation_data = await collection.find_one({"validation_id": validation_id})

        if not validation_data:
            raise HTTPException(status_code=404, detail="Validation not found")

        # Converter para SecurityValidation
        validation = SecurityValidation.from_avro_dict(validation_data)

        return validation

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "validation_api.get_validation_failed",
            validation_id=validation_id,
            error=str(e)
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/validations")
async def list_validations(
    fastapi_request: Request,
    ticket_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    validator_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """
    Lista validações com filtros e paginação.

    Args:
        fastapi_request: FastAPI Request para acessar app state
        ticket_id: Filtrar por ticket_id
        status: Filtrar por status (APPROVED/REJECTED/REQUIRES_APPROVAL)
        validator_type: Filtrar por tipo de validador
        limit: Número máximo de resultados
        offset: Offset para paginação

    Returns:
        Lista de SecurityValidations
    """
    try:
        logger.info(
            "validation_api.list_validations_requested",
            ticket_id=ticket_id,
            status=status,
            limit=limit,
            offset=offset
        )

        # Obter MongoDB do app state
        mongodb = fastapi_request.app.state.mongodb
        from src.config.settings import get_settings
        settings = get_settings()

        # Construir query
        query = {}
        if ticket_id:
            query["ticket_id"] = ticket_id
        if status:
            query["validation_status"] = status
        if validator_type:
            query["validator_type"] = validator_type

        # Executar busca
        collection = mongodb.db[settings.mongodb_validations_collection]
        cursor = collection.find(query).skip(offset).limit(limit)
        validations_data = await cursor.to_list(length=limit)

        validations = [
            SecurityValidation.from_avro_dict(v) for v in validations_data
        ]

        return {
            "validations": validations,
            "count": len(validations),
            "offset": offset,
            "limit": limit
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "validation_api.list_validations_failed",
            error=str(e)
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/validations/{validation_id}/approve")
async def approve_validation(
    validation_id: str,
    request: ApprovalRequest,
    fastapi_request: Request
):
    """
    Aprova validação pendente.

    Args:
        validation_id: ID da validação
        request: Request com dados de aprovação
        fastapi_request: FastAPI Request para acessar app state

    Returns:
        SecurityValidation atualizada
    """
    try:
        logger.info(
            "validation_api.approve_validation_requested",
            validation_id=validation_id,
            approved_by=request.approved_by
        )

        # Obter MongoDB e producer do app state
        mongodb = fastapi_request.app.state.mongodb
        validation_producer = fastapi_request.app.state.validation_producer
        from src.config.settings import get_settings
        settings = get_settings()

        # 1. Buscar validação no MongoDB
        collection = mongodb.db[settings.mongodb_validations_collection]
        validation_data = await collection.find_one({"validation_id": validation_id})

        if not validation_data:
            raise HTTPException(status_code=404, detail="Validation not found")

        # 2. Verificar se status == REQUIRES_APPROVAL
        if validation_data.get("validation_status") != "REQUIRES_APPROVAL":
            raise HTTPException(
                status_code=400,
                detail=f"Validation status is {validation_data.get('validation_status')}, expected REQUIRES_APPROVAL"
            )

        # 3. Atualizar status para APPROVED
        await collection.update_one(
            {"validation_id": validation_id},
            {"$set": {
                "validation_status": "APPROVED",
                "approved_by": request.approved_by,
                "approval_reason": request.reason
            }}
        )

        # Buscar validação atualizada
        validation_data = await collection.find_one({"validation_id": validation_id})
        validation = SecurityValidation.from_avro_dict(validation_data)

        # 4. Publicar ticket aprovado em execution.tickets.validated
        # (buscar ticket original do MongoDB ou reconstruir a partir dos dados da validação)
        await validation_producer.publish_to_topic(
            topic=settings.kafka_tickets_validated_topic,
            key=validation.ticket_id,
            value={
                "ticket_id": validation.ticket_id,
                "validation_id": validation.validation_id,
                "status": "APPROVED",
                "approved_by": request.approved_by
            }
        )

        logger.info(
            "validation_api.validation_approved",
            validation_id=validation_id,
            approved_by=request.approved_by
        )

        return validation

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "validation_api.approve_validation_failed",
            validation_id=validation_id,
            error=str(e)
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/validations/{validation_id}/reject")
async def reject_validation(
    validation_id: str,
    request: ApprovalRequest,
    fastapi_request: Request
):
    """
    Rejeita validação pendente.

    Args:
        validation_id: ID da validação
        request: Request com razão de rejeição
        fastapi_request: FastAPI Request para acessar app state

    Returns:
        SecurityValidation atualizada
    """
    try:
        logger.info(
            "validation_api.reject_validation_requested",
            validation_id=validation_id,
            reason=request.reason
        )

        # Obter MongoDB e producer do app state
        mongodb = fastapi_request.app.state.mongodb
        validation_producer = fastapi_request.app.state.validation_producer
        from src.config.settings import get_settings
        settings = get_settings()

        # 1. Buscar validação no MongoDB
        collection = mongodb.db[settings.mongodb_validations_collection]
        validation_data = await collection.find_one({"validation_id": validation_id})

        if not validation_data:
            raise HTTPException(status_code=404, detail="Validation not found")

        # 2. Verificar se status == REQUIRES_APPROVAL
        if validation_data.get("validation_status") != "REQUIRES_APPROVAL":
            raise HTTPException(
                status_code=400,
                detail=f"Validation status is {validation_data.get('validation_status')}, expected REQUIRES_APPROVAL"
            )

        # 3. Atualizar status para REJECTED
        await collection.update_one(
            {"validation_id": validation_id},
            {"$set": {
                "validation_status": "REJECTED",
                "rejected_by": request.approved_by,
                "rejection_reason": request.reason
            }}
        )

        # Buscar validação atualizada
        validation_data = await collection.find_one({"validation_id": validation_id})
        validation = SecurityValidation.from_avro_dict(validation_data)

        # 4. Publicar ticket rejeitado em execution.tickets.rejected
        await validation_producer.publish_to_topic(
            topic=settings.kafka_tickets_rejected_topic,
            key=validation.ticket_id,
            value={
                "ticket_id": validation.ticket_id,
                "validation_id": validation.validation_id,
                "status": "REJECTED",
                "rejected_by": request.approved_by,
                "rejection_reason": request.reason,
                "violations": [v.to_dict() for v in validation.violations]
            }
        )

        logger.warning(
            "validation_api.validation_rejected",
            validation_id=validation_id,
            rejected_by=request.approved_by
        )

        return validation

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "validation_api.reject_validation_failed",
            validation_id=validation_id,
            error=str(e)
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/validations/statistics")
async def get_statistics(fastapi_request: Request):
    """
    Retorna estatísticas agregadas de validações.

    Args:
        fastapi_request: FastAPI Request para acessar app state

    Returns:
        ValidationStatistics
    """
    try:
        logger.info("validation_api.get_statistics_requested")

        # Obter MongoDB do app state
        mongodb = fastapi_request.app.state.mongodb
        from src.config.settings import get_settings
        settings = get_settings()

        collection = mongodb.db[settings.mongodb_validations_collection]

        # Total de validações
        total = await collection.count_documents({})

        # Contagem por status
        approved = await collection.count_documents(
            {"validation_status": "APPROVED"}
        )
        rejected = await collection.count_documents(
            {"validation_status": "REJECTED"}
        )
        pending = await collection.count_documents(
            {"validation_status": "REQUIRES_APPROVAL"}
        )

        # Approval rate
        approval_rate = approved / total if total > 0 else 0.0

        # Top violations (agregação)
        pipeline = [
            {"$unwind": "$violations"},
            {"$group": {
                "_id": "$violations.violation_type",
                "count": {"$sum": 1}
            }},
            {"$sort": {"count": -1}},
            {"$limit": 10}
        ]
        top_violations_cursor = collection.aggregate(pipeline)
        top_violations = await top_violations_cursor.to_list(length=10)

        # Risk score médio
        pipeline = [
            {"$group": {
                "_id": None,
                "avg_risk_score": {"$avg": "$risk_assessment.risk_score"}
            }}
        ]
        avg_cursor = collection.aggregate(pipeline)
        avg_result = await avg_cursor.to_list(length=1)
        avg_risk_score = avg_result[0]["avg_risk_score"] if avg_result else 0.0

        return ValidationStatistics(
            total_validations=total,
            approved_count=approved,
            rejected_count=rejected,
            pending_approval_count=pending,
            approval_rate=approval_rate,
            top_violations=top_violations,
            avg_risk_score=avg_risk_score
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "validation_api.get_statistics_failed",
            error=str(e)
        )
        raise HTTPException(status_code=500, detail=str(e))
