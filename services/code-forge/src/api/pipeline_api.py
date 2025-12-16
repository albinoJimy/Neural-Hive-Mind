from datetime import datetime, timedelta
from typing import Dict, Optional
import uuid
from fastapi import APIRouter, HTTPException
import structlog

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1/pipelines", tags=["pipelines"])

# Armazenamento em memória para pipelines em ambiente de desenvolvimento.
PIPELINES: Dict[str, Dict] = {}


def _new_pipeline_state(artifact_id: str, parameters: Optional[Dict] = None) -> Dict:
    now = datetime.utcnow()
    pipeline_id = str(uuid.uuid4())
    PIPELINES[pipeline_id] = {
        "pipeline_id": pipeline_id,
        "artifact_id": artifact_id,
        "status": "queued",
        "stage": "QUEUED",
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "duration_ms": 0,
        "artifacts": [],
        "parameters": parameters or {},
        "sbom": None,
        "signature": None,
    }
    return PIPELINES[pipeline_id]


@router.post("", status_code=201)
async def trigger_pipeline(payload: Dict):
    """Dispara pipeline CI/CD (mockado)."""
    artifact_id = payload.get("artifact_id")
    if not artifact_id:
        raise HTTPException(status_code=400, detail="artifact_id is required")
    state = _new_pipeline_state(artifact_id, payload.get("parameters"))
    logger.info("pipeline_triggered", pipeline_id=state["pipeline_id"], artifact_id=artifact_id)
    return {"pipeline_id": state["pipeline_id"], "status": state["status"]}


@router.get("/{pipeline_id}")
async def get_pipeline(pipeline_id: str):
    """Retorna status do pipeline."""
    state = PIPELINES.get(pipeline_id)
    if not state:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    # Evolui estado de forma determinística para ambientes de integração.
    stage_order = ["QUEUED", "BUILDING", "TESTING", "PACKAGING", "COMPLETED"]
    current_index = stage_order.index(state["stage"])
    if state["stage"] != "COMPLETED":
        state["stage"] = stage_order[min(current_index + 1, len(stage_order) - 1)]
        if state["stage"] == "COMPLETED":
            state["status"] = "completed"
            state["duration_ms"] = 5000
            state["artifacts"] = [{"type": "image", "name": f"{state['artifact_id']}:latest"}]
            state["sbom"] = {"status": "generated"}
            state["signature"] = "mock-signature"
        state["updated_at"] = datetime.utcnow().isoformat()

    return {
        "pipeline_id": state["pipeline_id"],
        "status": state["status"],
        "stage": state["stage"].lower(),
        "duration_ms": state["duration_ms"],
        "artifacts": state["artifacts"],
        "sbom": state["sbom"],
        "signature": state["signature"],
    }
