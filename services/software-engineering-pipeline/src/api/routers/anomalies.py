"""Router para anomalias detectadas."""

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from src.models.schemas import AnomalyType, Severity
from src.repositories.pipeline_repository import AnomalyRepository

router = APIRouter(prefix="/anomalies", tags=["anomalies"])
repo = AnomalyRepository()


class AnomalyResponse(BaseModel):
    """Response de anomalia."""

    model_config = ConfigDict(extra="forbid")

    anomaly_id: str
    repo_url: str
    type: str
    severity: str
    description: str
    affected_component: str | None = None
    detected_at: str | None = None
    resolved: bool
    resolved_at: str | None = None
    run_id: str | None = None
    suggested_action: str | None = None


class AnomalyListResponse(BaseModel):
    """Response de lista de anomalias."""

    model_config = ConfigDict(extra="forbid")

    total: int
    items: list[AnomalyResponse]
    unresolved_count: int


class ResolveAnomalyRequest(BaseModel):
    """Request para resolver anomalia."""

    model_config = ConfigDict(extra="forbid")

    resolution_notes: str | None = Field(None, description="Notas sobre a resolução")


@router.get("", response_model=AnomalyListResponse)
async def list_anomalies(
    repo_url: str | None = Query(None, description="Filtrar por URL do repositório"),
    type_filter: AnomalyType | None = Query(None, alias="type"),
    resolved: bool | None = Query(None, description="Filtrar por status de resolução"),
    severity: Severity | None = Query(None, description="Filtrar por severidade"),
    limit: int = Query(50, ge=1, le=200, description="Limite de itens"),
) -> AnomalyListResponse:
    """Lista anomalias detectadas."""
    filter_dict: dict[str, Any] = {}
    if repo_url:
        filter_dict["repo_url"] = repo_url
    if type_filter:
        filter_dict["type"] = type_filter.value
    if resolved is not None:
        filter_dict["resolved"] = resolved
    if severity:
        filter_dict["severity"] = severity.value

    anomalies = await repo.find_many(
        filter_dict=filter_dict,
        limit=limit,
        sort=[("detected_at", -1)],
    )

    # Contar não resolvidas
    unresolved_anomalies = [a for a in anomalies if not a.get("resolved", False)]
    unresolved_count = len(unresolved_anomalies)

    return AnomalyListResponse(
        total=len(anomalies),
        items=[_anomaly_to_response_from_dict(a) for a in anomalies],
        unresolved_count=unresolved_count,
    )


@router.get("/{anomaly_id}", response_model=AnomalyResponse)
async def get_anomaly(anomaly_id: str) -> AnomalyResponse:
    """Obtém detalhes de uma anomalia específica."""
    anomaly = await repo.find_by_id(anomaly_id)
    if not anomaly:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Anomaly {anomaly_id} not found",
        )

    return _anomaly_to_response_from_dict(anomaly)


@router.get("/repositories/{repo_url:path}/unresolved", response_model=list[AnomalyResponse])
async def get_unresolved_anomalies(
    repo_url: str,
    limit: int = Query(20, ge=1, le=100, description="Limite de itens"),
) -> list[AnomalyResponse]:
    """Obtém anomalias não resolvidas de um repositório."""
    full_repo_url = f"https://{repo_url}" if not repo_url.startswith("http") else repo_url

    anomalies = await repo.find_unresolved(full_repo_url)

    return [_anomaly_to_response_from_dict(a) for a in anomalies[:limit]]


@router.post("/{anomaly_id}/resolve", response_model=AnomalyResponse)
async def resolve_anomaly(anomaly_id: str, request: ResolveAnomalyRequest) -> AnomalyResponse:
    """Marca uma anomalia como resolvida."""
    # Primeiro verifica se existe
    anomaly = await repo.find_by_id(anomaly_id)
    if not anomaly:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Anomaly {anomaly_id} not found",
        )

    # Se já está resolvida, retorna erro
    if anomaly.get("resolved", False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Anomaly {anomaly_id} is already resolved",
        )

    # Marca como resolvida
    resolved = await repo.mark_resolved(anomaly_id)
    if not resolved:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to resolve anomaly",
        )

    # Busca anomalia atualizada
    updated = await repo.find_by_id(anomaly_id)
    return _anomaly_to_response_from_dict(updated)


@router.delete("/{anomaly_id}", status_code=204)
async def delete_anomaly(anomaly_id: str) -> None:
    """Deleta uma anomalia."""
    deleted = await repo.delete(anomaly_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Anomaly {anomaly_id} not found",
        )


def _anomaly_to_response_from_dict(anomaly: dict) -> AnomalyResponse:
    """Converte um dict para AnomalyResponse."""
    return AnomalyResponse(
        anomaly_id=anomaly.get("anomaly_id", anomaly.get("_id", "")),
        repo_url=anomaly.get("repo_url", ""),
        type=anomaly.get("type", "unknown"),
        severity=anomaly.get("severity", "medium"),
        description=anomaly.get("description", ""),
        affected_component=anomaly.get("affected_component"),
        detected_at=anomaly.get("detected_at"),
        resolved=anomaly.get("resolved", False),
        resolved_at=anomaly.get("resolved_at"),
        run_id=anomaly.get("run_id"),
        suggested_action=anomaly.get("suggested_action"),
    )
