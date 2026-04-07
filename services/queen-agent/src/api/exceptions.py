from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.api.dependencies import get_exception_service, get_mongodb_client
from src.clients import MongoDBClient
from src.services import ExceptionApprovalService

router = APIRouter(prefix="/api/v1/exceptions", tags=["exceptions"])
logger = structlog.get_logger()


class ApproveRequest(BaseModel):
    decision_id: str
    conditions: list[str] = []


class RejectRequest(BaseModel):
    reason: str


@router.post("", status_code=201)
async def create_exception(
    exception_data: dict[str, Any],
    exception_service: ExceptionApprovalService = Depends(get_exception_service),
) -> dict[str, str]:
    """Criar solicitação de exceção"""
    try:
        from src.models import ExceptionApproval

        exception = ExceptionApproval(**exception_data)
        exception_id = await exception_service.request_exception(exception)

        return {"exception_id": exception_id, "status": "pending"}

    except Exception as e:
        logger.exception("create_exception_failed", error=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{exception_id}")
async def get_exception(
    exception_id: str,
    mongodb_client: MongoDBClient = Depends(get_mongodb_client),
) -> dict[str, Any]:
    """Buscar exceção por ID"""
    exception = await mongodb_client.get_exception_approval(exception_id)
    if not exception:
        raise HTTPException(status_code=404, detail=f"Exception {exception_id} not found")

    # Remover _id do MongoDB
    exception.pop("_id", None)
    return exception


@router.get("/pending")
async def list_pending_exceptions(
    exception_service: ExceptionApprovalService = Depends(get_exception_service),
) -> list[dict[str, Any]]:
    """Listar exceções pendentes"""
    try:
        exceptions = await exception_service.get_pending_exceptions()
        return [exc.to_dict() for exc in exceptions]

    except Exception as e:
        logger.exception("list_pending_exceptions_failed", error=str(e))
        return []


@router.post("/{exception_id}/approve")
async def approve_exception(
    exception_id: str,
    approve_request: ApproveRequest,
    exception_service: ExceptionApprovalService = Depends(get_exception_service),
) -> dict[str, Any]:
    """Aprovar exceção"""
    try:
        exception = await exception_service.approve_exception(
            exception_id, approve_request.decision_id, approve_request.conditions
        )

        return exception.to_dict()

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("approve_exception_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{exception_id}/reject")
async def reject_exception(
    exception_id: str,
    reject_request: RejectRequest,
    exception_service: ExceptionApprovalService = Depends(get_exception_service),
) -> dict[str, Any]:
    """Rejeitar exceção"""
    try:
        exception = await exception_service.reject_exception(exception_id, reject_request.reason)

        return exception.to_dict()

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("reject_exception_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")
