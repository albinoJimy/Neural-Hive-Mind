from fastapi import APIRouter, HTTPException, Request
from typing import List, Dict, Any
from pydantic import BaseModel
import structlog

router = APIRouter(prefix="/api/v1/exceptions", tags=["exceptions"])
logger = structlog.get_logger()


class ApproveRequest(BaseModel):
    decision_id: str
    conditions: List[str] = []


class RejectRequest(BaseModel):
    reason: str


@router.post("", status_code=201)
async def create_exception(exception_data: Dict[str, Any], request: Request) -> Dict[str, str]:
    """Criar solicitação de exceção"""
    exception_service = request.app.state.app_state.exception_service

    try:
        from ..models import ExceptionApproval
        exception = ExceptionApproval(**exception_data)
        exception_id = await exception_service.request_exception(exception)

        return {"exception_id": exception_id, "status": "pending"}

    except Exception as e:
        logger.error("create_exception_failed", error=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{exception_id}")
async def get_exception(exception_id: str, request: Request) -> Dict[str, Any]:
    """Buscar exceção por ID"""
    mongodb_client = request.app.state.app_state.mongodb_client

    exception = await mongodb_client.get_exception_approval(exception_id)
    if not exception:
        raise HTTPException(status_code=404, detail=f"Exception {exception_id} not found")

    # Remover _id do MongoDB
    exception.pop('_id', None)
    return exception


@router.get("/pending")
async def list_pending_exceptions(request: Request) -> List[Dict[str, Any]]:
    """Listar exceções pendentes"""
    exception_service = request.app.state.app_state.exception_service

    try:
        exceptions = await exception_service.get_pending_exceptions()
        return [exc.to_dict() for exc in exceptions]

    except Exception as e:
        logger.error("list_pending_exceptions_failed", error=str(e))
        return []


@router.post("/{exception_id}/approve")
async def approve_exception(
    exception_id: str,
    approve_request: ApproveRequest,
    request: Request
) -> Dict[str, Any]:
    """Aprovar exceção"""
    exception_service = request.app.state.app_state.exception_service

    try:
        exception = await exception_service.approve_exception(
            exception_id,
            approve_request.decision_id,
            approve_request.conditions
        )

        return exception.to_dict()

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("approve_exception_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{exception_id}/reject")
async def reject_exception(
    exception_id: str,
    reject_request: RejectRequest,
    request: Request
) -> Dict[str, Any]:
    """Rejeitar exceção"""
    exception_service = request.app.state.app_state.exception_service

    try:
        exception = await exception_service.reject_exception(
            exception_id,
            reject_request.reason
        )

        return exception.to_dict()

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("reject_exception_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")
