"""
API REST para enforcement de políticas e remediação.
"""

from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query, Depends, Request
from pydantic import BaseModel
from datetime import datetime, timezone
import structlog

logger = structlog.get_logger(__name__)

router = APIRouter()


class EnforcementActionRequest(BaseModel):
    """Request para ação de enforcement manual."""
    incident_id: str
    action_type: str
    resources: List[str]
    reason: Optional[str] = None
    requested_by: str


class EnforcementResponse(BaseModel):
    """Response de ação de enforcement."""
    success: bool
    action: str
    details: dict
    timestamp: str


class RemediationActionRequest(BaseModel):
    """Request para ação de remediação manual."""
    incident_id: str
    action_type: str
    playbook: Optional[str] = None
    parameters: Optional[dict] = None
    requested_by: str


class RemediationResponse(BaseModel):
    """Response de ação de remediação."""
    success: bool
    action_type: str
    details: dict
    timestamp: str


class EnforcementHistoryResponse(BaseModel):
    """Response de histórico de enforcement."""
    enforcement_id: str
    incident_id: str
    action: str
    status: str
    applied_at: str
    applied_by: str
    details: dict


@router.post("/enforcement/actions", response_model=EnforcementResponse)
async def execute_enforcement_action(
    request: EnforcementActionRequest,
    fastapi_request: Request
):
    """
    Executa ação de enforcement manual.

    Args:
        request: Request com dados da ação
        fastapi_request: FastAPI Request

    Returns:
        Resultado da ação de enforcement
    """
    try:
        logger.info(
            "enforcement_api.execute_action",
            incident_id=request.incident_id,
            action_type=request.action_type,
            requested_by=request.requested_by
        )

        policy_enforcer = fastapi_request.app.state.policy_enforcer

        # Construir incidente mínimo
        incident = {
            "incident_id": request.incident_id,
            "affected_resources": request.resources
        }

        # Construir plano
        plan = {
            "action": request.action_type,
            "reason": request.reason,
            "manual": True,
            "requested_by": request.requested_by
        }

        # Executar ação baseada no tipo
        if request.action_type == "quarantine":
            result = await policy_enforcer._quarantine_resource(incident, plan)
        elif request.action_type == "isolate":
            result = await policy_enforcer._isolate_pod(incident, plan)
        elif request.action_type == "scale_down":
            result = await policy_enforcer._scale_down_resource(incident, plan)
        elif request.action_type == "rate_limit":
            result = await policy_enforcer._apply_rate_limit(incident, plan)
        elif request.action_type == "revoke_access":
            result = await policy_enforcer._revoke_access(incident, plan)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown action type: {request.action_type}"
            )

        return EnforcementResponse(
            success=result.get("success", False),
            action=result.get("action", request.action_type),
            details=result.get("details", {}),
            timestamp=datetime.now(timezone.utc).isoformat()
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("enforcement_api.execute_action_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/remediation/actions", response_model=RemediationResponse)
async def execute_remediation_action(
    request: RemediationActionRequest,
    fastapi_request: Request
):
    """
    Executa ação de remediação manual.

    Args:
        request: Request com dados da remediação
        fastapi_request: FastAPI Request

    Returns:
        Resultado da ação de remediação
    """
    try:
        logger.info(
            "enforcement_api.execute_remediation",
            incident_id=request.incident_id,
            action_type=request.action_type,
            playbook=request.playbook,
            requested_by=request.requested_by
        )

        remediation_coordinator = fastapi_request.app.state.remediation_coordinator

        # Construir incidente
        incident = {
            "incident_id": request.incident_id,
            "threat_type": request.action_type
        }

        # Construir plano de remediação
        remediation_plan = {
            "action_type": request.action_type,
            "playbook": request.playbook,
            "parameters": request.parameters or {},
            "manual": True,
            "requested_by": request.requested_by
        }

        # Executar remediação
        result = await remediation_coordinator.execute_remediation(
            incident=incident,
            remediation_plan=remediation_plan
        )

        return RemediationResponse(
            success=result.get("success", False),
            action_type=request.action_type,
            details=result.get("details", {}),
            timestamp=datetime.now(timezone.utc).isoformat()
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("enforcement_api.execute_remediation_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/enforcement/history", response_model=List[EnforcementHistoryResponse])
async def get_enforcement_history(
    incident_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    fastapi_request: Request = None
):
    """
    Obtém histórico de ações de enforcement.

    Args:
        incident_id: Filtrar por ID do incidente
        limit: Número máximo de registros
        fastapi_request: FastAPI Request

    Returns:
        Lista de histórico de enforcement
    """
    try:
        logger.info(
            "enforcement_api.get_history",
            incident_id=incident_id,
            limit=limit
        )

        mongodb = fastapi_request.app.state.mongodb

        # Construir filtro
        query_filter = {}
        if incident_id:
            query_filter["incident_id"] = incident_id

        # Buscar histórico
        cursor = mongodb.remediation_collection.find(query_filter).sort("timestamp", -1).limit(limit)

        history = []
        async for doc in cursor:
            history.append(EnforcementHistoryResponse(
                enforcement_id=doc.get("enforcement_id", ""),
                incident_id=doc.get("incident_id", ""),
                action=doc.get("action", "unknown"),
                status=doc.get("status", "unknown"),
                applied_at=doc.get("timestamp", datetime.now(timezone.utc).isoformat()),
                applied_by=doc.get("applied_by", "system"),
                details=doc.get("details", {})
            ))

        return history

    except Exception as e:
        logger.error("enforcement_api.get_history_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
