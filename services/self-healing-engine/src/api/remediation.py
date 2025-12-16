from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
import structlog
from uuid import uuid4

from src.models.remediation_models import RemediationRequest, RemediationResponse, RemediationStatusResponse
from src.services.remediation_manager import RemediationManager, RemediationStatus
from src.services.playbook_executor import PlaybookExecutor

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1", tags=["remediation"])


def _get_manager(request: Request) -> RemediationManager:
    manager = getattr(request.app.state, "remediation_manager", None)
    if not manager:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Remediation manager unavailable")
    return manager


def _get_executor(request: Request) -> PlaybookExecutor:
    executor = getattr(request.app.state, "playbook_executor", None)
    if not executor:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Playbook executor unavailable")
    return executor


@router.post("/remediation/execute", response_model=RemediationResponse, status_code=status.HTTP_202_ACCEPTED)
async def execute_remediation(
    remediation_request: RemediationRequest,
    background_tasks: BackgroundTasks,
    manager: RemediationManager = Depends(_get_manager),
    executor: PlaybookExecutor = Depends(_get_executor)
):
    """Aciona playbook de remediação de forma assíncrona."""
    if not executor.playbook_exists(remediation_request.playbook_name):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Playbook not found")

    remediation_request.remediation_id = remediation_request.remediation_id or str(uuid4())

    playbook_metadata = executor.get_playbook_metadata(remediation_request.playbook_name)
    total_actions = len(playbook_metadata.get("actions", []))

    state = manager.start_remediation(remediation_request, total_actions=total_actions)

    background_tasks.add_task(manager.execute_remediation, state, executor, remediation_request)

    logger.info(
        "remediation_api.remediation_accepted",
        remediation_id=state.remediation_id,
        playbook=remediation_request.playbook_name,
        total_actions=total_actions
    )

    return RemediationResponse(
        remediation_id=state.remediation_id,
        status=state.status.value,
        started_at=state.started_at,
        message="Remediation accepted"
    )


@router.get("/remediation/{remediation_id}/status", response_model=RemediationStatusResponse)
async def remediation_status(
    remediation_id: str,
    manager: RemediationManager = Depends(_get_manager)
):
    """Consulta status de uma remediação."""
    state = manager.get_status(remediation_id)
    if not state:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Remediation not found")

    return RemediationStatusResponse(
        remediation_id=state.remediation_id,
        status=state.status.value if isinstance(state.status, RemediationStatus) else state.status,
        progress=state.progress,
        actions_completed=state.actions_completed,
        total_actions=state.total_actions,
        result=state.result,
        error=state.error
    )


@router.post("/remediation/{remediation_id}/cancel", response_model=RemediationResponse)
async def cancel_remediation(
    remediation_id: str,
    manager: RemediationManager = Depends(_get_manager)
):
    """Cancela uma remediação em andamento (best-effort)."""
    state = manager.cancel_remediation(remediation_id)
    if not state:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Remediation not found")

    return RemediationResponse(
        remediation_id=state.remediation_id,
        status=state.status.value if isinstance(state.status, RemediationStatus) else state.status,
        started_at=state.started_at,
        message="Cancellation requested"
    )


@router.get("/playbooks")
async def list_playbooks(
    executor: PlaybookExecutor = Depends(_get_executor)
):
    """Lista playbooks disponíveis."""
    return {"playbooks": executor.list_playbooks()}
