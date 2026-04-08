"""Rotas da API para hipóteses."""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from src.models.hypothesis import (
    Hypothesis,
    HypothesisCreate,
    HypothesisFilter,
    HypothesisStatus,
    HypothesisPriority,
    HypothesisUpdate,
    HypothesisResults,
)
from src.models.hypothesis_version import VersionDiff
from src.models.workflow import WorkflowTransition
from src.services.hypothesis_service import HypothesisService

router = APIRouter()


# Schemas para requests/responses
class HypothesisResponse(BaseModel):
    """Response schema para hipótese."""

    hypothesis: Hypothesis
    allowed_transitions: list[HypothesisStatus] = Field(
        default_factory=list,
        description="Transições permitidas para o status atual"
    )


class HypothesisListResponse(BaseModel):
    """Response schema para lista de hipóteses."""

    total: int
    offset: int
    limit: int
    items: list[Hypothesis]


class TransitionRequest(BaseModel):
    """Request schema para transições."""

    reason: str = Field(default="", description="Razão da transição")
    metadata: dict[str, Any] = Field(default_factory=dict)


class TransitionResponse(BaseModel):
    """Response schema para transições."""

    hypothesis: Hypothesis
    transition: WorkflowTransition


class VersionResponse(BaseModel):
    """Response schema para versões."""

    versions: list[dict[str, Any]]


class StartTestingRequest(BaseModel):
    """Request schema para iniciar teste."""

    experiment_id: str = Field(..., description="ID do experimento criado")


# ============================================================================
# CRUD Básico
# ============================================================================

@router.post("", response_model=Hypothesis, status_code=status.HTTP_201_CREATED)
async def create_hypothesis(
    data: HypothesisCreate,
    author: Annotated[str, Query(description="Autor da hipótese")],
    service: Annotated[HypothesisService, Depends()],
) -> Hypothesis:
    """
    Cria nova hipótese.

    - **title**: Título da hipótese
    - **description**: Descrição detalhada
    - **expected_outcome**: Resultado esperado
    - **metrics**: Métricas que serão afetadas
    - **priority**: Prioridade (CRITICAL, HIGH, MEDIUM, LOW)
    - **tags**: Tags para categorização
    """
    return await service.create(data, author=author)


@router.get("", response_model=HypothesisListResponse)
async def list_hypotheses(
    service: Annotated[HypothesisService, Depends()],
    status_filter: HypothesisStatus | None = Query(None, alias="status"),
    priority: HypothesisPriority | None = Query(None),
    author: str | None = Query(None),
    reviewer: str | None = Query(None),
    tags: list[str] | None = Query(None),
    search: str | None = Query(None, alias="search_text"),
    requires_experiment: bool | None = Query(None),
    has_experiment: bool | None = Query(None),
    outcome: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    sort_by: str = Query("created_at"),
    sort_order: int = Query(-1, ge=-1, le=1),
) -> HypothesisListResponse:
    """
    Lista hipóteses com filtros.

    - **status**: Filtra por status (DRAFT, PROPOSED, APPROVED, etc)
    - **priority**: Filtra por prioridade
    - **author**: Filtra por autor
    - **reviewer**: Filtra por revisor
    - **tags**: Filtra por tags
    - **search_text**: Busca em title/description
    - **limit**: Limite de resultados (1-200)
    - **offset**: Offset para paginação
    - **sort_by**: Campo para ordenação
    - **sort_order**: -1=desc, 1=asc
    """
    filters = HypothesisFilter(
        status=status_filter,
        priority=priority,
        author=author,
        reviewer=reviewer,
        tags=tags,
        search_text=search,
        requires_experiment=requires_experiment,
        has_experiment=has_experiment,
        outcome=outcome,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    result = await service.list(filters)
    return HypothesisListResponse(**result)


@router.get("/aggregations")
async def get_aggregations(
    service: Annotated[HypothesisService, Depends()],
) -> dict[str, Any]:
    """
    Retorna agregações para dashboard.

    - **total**: Total de hipóteses
    - **by_status**: Contagem por status
    - **by_priority**: Contagem por prioridade
    - **in_testing**: Hipóteses em teste
    - **pending_approval**: Hipóteses aguardando aprovação
    """
    return await service.get_aggregations()


@router.get("/{hypothesis_id}", response_model=HypothesisResponse)
async def get_hypothesis(
    hypothesis_id: str,
    service: Annotated[HypothesisService, Depends()],
    role: str = Query("author", description="Papel para calcular transições permitidas"),
) -> HypothesisResponse:
    """
    Busca hipótese por ID.

    - **hypothesis_id**: ID da hipótese
    - **role**: Papel do usuário (author, reviewer, system)
    """
    hypothesis = await service.get_by_id(hypothesis_id)
    if not hypothesis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hypothesis {hypothesis_id} not found",
        )

    allowed_transitions = await service.get_allowed_transitions(hypothesis_id, role)

    return HypothesisResponse(
        hypothesis=hypothesis,
        allowed_transitions=allowed_transitions,
    )


@router.put("/{hypothesis_id}", response_model=Hypothesis)
async def update_hypothesis(
    hypothesis_id: str,
    data: HypothesisUpdate,
    service: Annotated[HypothesisService, Depends()],
    updated_by: Annotated[str, Query(description="Usuário que está atualizando")],
    create_version: bool = Query(True, description="Criar nova versão"),
) -> Hypothesis:
    """
    Atualiza hipótese.

    - **hypothesis_id**: ID da hipótese
    - **create_version**: Se deve criar nova versão automaticamente
    """
    updated = await service.update(
        hypothesis_id,
        data,
        updated_by=updated_by,
        create_version=create_version,
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hypothesis {hypothesis_id} not found",
        )

    return updated


@router.delete("/{hypothesis_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_hypothesis(
    hypothesis_id: str,
    service: Annotated[HypothesisService, Depends()],
) -> None:
    """
    Remove hipótese (soft delete via arquivo).

    - **hypothesis_id**: ID da hipótese
    """
    deleted = await service.delete(hypothesis_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hypothesis {hypothesis_id} not found",
        )


# ============================================================================
# Workflow
# ============================================================================

@router.post("/{hypothesis_id}/propose", response_model=TransitionResponse)
async def propose_hypothesis(
    hypothesis_id: str,
    request: TransitionRequest,
    proposed_by: Annotated[str, Query(description="Usuário que está propondo")],
    service: Annotated[HypothesisService, Depends()],
) -> TransitionResponse:
    """
    Propõe hipótese para revisão.

    Transição: DRAFT -> PROPOSED
    """
    hypothesis, transition = await service.propose(
        hypothesis_id,
        proposed_by=proposed_by,
        reason=request.reason,
    )

    if not hypothesis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hypothesis {hypothesis_id} not found",
        )

    return TransitionResponse(hypothesis=hypothesis, transition=transition)


@router.post("/{hypothesis_id}/approve", response_model=TransitionResponse)
async def approve_hypothesis(
    hypothesis_id: str,
    request: TransitionRequest,
    approved_by: Annotated[str, Query(description="Revisor que está aprovando")],
    service: Annotated[HypothesisService, Depends()],
) -> TransitionResponse:
    """
    Aprova hipótese para teste.

    Transição: PROPOSED -> APPROVED
    """
    hypothesis, transition = await service.approve(
        hypothesis_id,
        approved_by=approved_by,
        reason=request.reason,
    )

    if not hypothesis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hypothesis {hypothesis_id} not found",
        )

    return TransitionResponse(hypothesis=hypothesis, transition=transition)


@router.post("/{hypothesis_id}/reject", response_model=TransitionResponse)
async def reject_hypothesis(
    hypothesis_id: str,
    request: TransitionRequest,
    rejected_by: Annotated[str, Query(description="Usuário que está rejeitando")],
    service: Annotated[HypothesisService, Depends()],
) -> TransitionResponse:
    """
    Rejeita hipótese.

    Transição: PROPOSED/COMPLETED -> REJECTED
    """
    hypothesis, transition = await service.reject(
        hypothesis_id,
        rejected_by=rejected_by,
        reason=request.reason,
    )

    if not hypothesis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hypothesis {hypothesis_id} not found",
        )

    return TransitionResponse(hypothesis=hypothesis, transition=transition)


@router.post("/{hypothesis_id}/start-test", response_model=TransitionResponse)
async def start_testing(
    hypothesis_id: str,
    request: StartTestingRequest,
    started_by: Annotated[str, Query(default="system", description="Usuário/sistema")],
    service: Annotated[HypothesisService, Depends()],
) -> TransitionResponse:
    """
    Inicia teste de hipótese.

    Transição: APPROVED -> IN_TESTING

    - **experiment_id**: ID do experimento criado no ExperimentationEngine
    """
    hypothesis, transition = await service.start_testing(
        hypothesis_id,
        experiment_id=request.experiment_id,
        started_by=started_by,
    )

    if not hypothesis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hypothesis {hypothesis_id} not found",
        )

    return TransitionResponse(hypothesis=hypothesis, transition=transition)


@router.post("/{hypothesis_id}/complete", response_model=TransitionResponse)
async def complete_testing(
    hypothesis_id: str,
    results: HypothesisResults,
    completed_by: Annotated[str, Query(default="system", description="Usuário/sistema")],
    service: Annotated[HypothesisService, Depends()],
) -> TransitionResponse:
    """
    Completa teste com resultados.

    Transição: IN_TESTING -> COMPLETED

    - **results**: Resultados do experimento
    """
    hypothesis, transition = await service.complete(
        hypothesis_id,
        results=results,
        completed_by=completed_by,
    )

    if not hypothesis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hypothesis {hypothesis_id} not found",
        )

    return TransitionResponse(hypothesis=hypothesis, transition=transition)


@router.post("/{hypothesis_id}/accept", response_model=TransitionResponse)
async def accept_hypothesis(
    hypothesis_id: str,
    request: TransitionRequest,
    accepted_by: Annotated[str, Query(description="Revisor que aceita")],
    service: Annotated[HypothesisService, Depends()],
) -> TransitionResponse:
    """
    Aceita hipótese como validada.

    Transição: COMPLETED -> ACCEPTED
    """
    hypothesis, transition = await service.accept(
        hypothesis_id,
        accepted_by=accepted_by,
        reason=request.reason,
    )

    if not hypothesis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hypothesis {hypothesis_id} not found",
        )

    return TransitionResponse(hypothesis=hypothesis, transition=transition)


@router.post("/{hypothesis_id}/archive", response_model=TransitionResponse)
async def archive_hypothesis(
    hypothesis_id: str,
    request: TransitionRequest,
    archived_by: Annotated[str, Query(description="Usuário que está arquivando")],
    service: Annotated[HypothesisService, Depends()],
) -> TransitionResponse:
    """
    Arquiva hipótese.

    Transição: ACCEPTED/REJECTED/DRAFT -> ARCHIVED
    """
    hypothesis, transition = await service.archive(
        hypothesis_id,
        archived_by=archived_by,
        reason=request.reason,
    )

    if not hypothesis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hypothesis {hypothesis_id} not found",
        )

    return TransitionResponse(hypothesis=hypothesis, transition=transition)


@router.get("/{hypothesis_id}/transitions", response_model=list[WorkflowTransition])
async def get_transition_history(
    hypothesis_id: str,
    service: Annotated[HypothesisService, Depends()],
) -> list[WorkflowTransition]:
    """
    Retorna histórico de transições de estado.

    - **hypothesis_id**: ID da hipótese
    """
    return await service.get_transition_history(hypothesis_id)


# ============================================================================
# Versionamento
# ============================================================================

@router.get("/{hypothesis_id}/versions", response_model=VersionResponse)
async def get_version_history(
    hypothesis_id: str,
    service: Annotated[HypothesisService, Depends()],
) -> VersionResponse:
    """
    Retorna histórico de versões de uma hipótese.

    - **hypothesis_id**: ID da hipótese
    """
    versions = await service.get_version_history(hypothesis_id)

    version_dicts = []
    for v in versions:
        vd = v.model_dump()
        vd.pop("snapshot", None)  # Não retornar snapshot completo na lista
        version_dicts.append(vd)

    return VersionResponse(versions=version_dicts)


@router.get("/{hypothesis_id}/versions/compare")
async def compare_versions(
    hypothesis_id: str,
    from_version: Annotated[int, Query(description="Versão de origem")],
    to_version: Annotated[int, Query(description="Versão de destino")],
    service: Annotated[HypothesisService, Depends()],
) -> VersionDiff | None:
    """
    Compara duas versões de uma hipótese.

    - **hypothesis_id**: ID da hipótese
    - **from_version**: Versão de origem
    - **to_version**: Versão de destino
    """
    diff = await service.compare_versions(hypothesis_id, from_version, to_version)

    if not diff:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cannot compare versions {from_version} -> {to_version}",
        )

    return diff


# ============================================================================
# Metadata
# ============================================================================

@router.get("/{hypothesis_id}/allowed-transitions")
async def get_allowed_transitions(
    hypothesis_id: str,
    service: Annotated[HypothesisService, Depends()],
    role: str = Query("author", description="Papel do usuário"),
) -> list[HypothesisStatus]:
    """
    Retorna transições permitidas para uma hipótese.

    - **hypothesis_id**: ID da hipótese
    - **role**: Papel do usuário (author, reviewer, system)
    """
    return await service.get_allowed_transitions(hypothesis_id, role)
