"""
API REST para Leader Election

Endpoints para consultar estado da eleição e metadados do líder.
"""
from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Dict, Any, Optional
import structlog

from ..services import NodeRole

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1/election", tags=["election"])


class ElectionStatusResponse(BaseModel):
    """Resposta do status da eleição"""
    node_id: str
    role: str
    leader_id: Optional[str]
    is_leader: bool
    term: int


class LeaderMetadataResponse(BaseModel):
    """Resposta dos metadados do líder"""
    node_id: Optional[str]
    term: Optional[int]
    acquired_at: Optional[str]
    ttl: Optional[int]


class LeaderHeartbeatResponse(BaseModel):
    """Resposta do heartbeat do líder"""
    node_id: Optional[str]
    timestamp: Optional[str]


@router.get("/status", response_model=ElectionStatusResponse)
async def get_election_status(request: Request) -> JSONResponse:
    """
    Obter status da eleição para este nó.

    Returns informações sobre:
    - node_id: ID deste nó
    - role: Papel atual (leader, follower, candidate)
    - leader_id: ID do líder atual (se houver)
    - is_leader: Se este nó é o líder
    - term: Termo atual da eleição
    """
    app_state = request.app.state.app_state

    if not app_state.leader_election:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error": "Leader election not enabled"},
        )

    state = app_state.leader_election.get_state()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "node_id": app_state.leader_election.node_id,
            "role": state.role.value,
            "leader_id": state.leader_id,
            "is_leader": state.role == NodeRole.LEADER,
            "term": state.term,
        },
    )


@router.get("/leader", response_model=LeaderMetadataResponse)
async def get_leader_info(request: Request) -> JSONResponse:
    """
    Obter metadados do líder atual.

    Returns informações sobre:
    - node_id: ID do nó líder
    - term: Termo da eleição
    - acquired_at: Quando o líder foi eleito
    - ttl: Time-to-live do lease em segundos
    """
    app_state = request.app.state.app_state

    if not app_state.leader_election:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error": "Leader election not enabled"},
        )

    metadata = await app_state.leader_election.get_leader_metadata()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "node_id": metadata.get("node_id"),
            "term": int(metadata.get("term", 0)) if metadata.get("term") else None,
            "acquired_at": metadata.get("acquired_at"),
            "ttl": int(metadata.get("ttl", 0)) if metadata.get("ttl") else None,
        },
    )


@router.get("/leader/heartbeat", response_model=LeaderHeartbeatResponse)
async def get_leader_heartbeat(request: Request) -> JSONResponse:
    """
    Obter heartbeat do líder atual.

    Usado para verificar se o líder está ativo.
    """
    app_state = request.app.state.app_state

    if not app_state.leader_election:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error": "Leader election not enabled"},
        )

    heartbeat = await app_state.leader_election.get_leader_heartbeat()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "node_id": heartbeat.get("node_id"),
            "timestamp": heartbeat.get("timestamp"),
        },
    )


@router.post("/resign")
async def resign_leadership(request: Request) -> JSONResponse:
    """
    Forçar renúncia à liderança (apenas líder).

    Deve ser usado apenas para manutenção ou testes.
    """
    app_state = request.app.state.app_state

    if not app_state.leader_election:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error": "Leader election not enabled"},
        )

    if not app_state.leader_election.is_leader():
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"error": "Only the leader can resign"},
        )

    await app_state.leader_election._resign_leadership()

    logger.info("leadership_resigned_via_api", node_id=app_state.leader_election.node_id)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": "Leadership resigned successfully"},
    )
