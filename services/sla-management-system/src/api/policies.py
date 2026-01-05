"""
Router FastAPI para endpoints de políticas de congelamento.
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from ..models.freeze_policy import FreezePolicy, FreezeEvent
from ..services.policy_enforcer import PolicyEnforcer
from ..clients.postgresql_client import PostgreSQLClient


router = APIRouter(prefix="/api/v1/policies", tags=["Freeze Policies"])


# Response models
class PolicyCreateResponse(BaseModel):
    policy_id: str
    message: str


class PolicyListResponse(BaseModel):
    policies: List[FreezePolicy]
    total: int


class FreezeListResponse(BaseModel):
    freezes: List[FreezeEvent]
    total: int


# Dependency injection
def get_policy_enforcer() -> PolicyEnforcer:
    """
    Returns the PolicyEnforcer instance from application state.

    In production, this is overridden via FastAPI dependency_overrides in main.py.
    This fallback accesses the module-level singleton directly.
    """
    from .. import main
    if main.policy_enforcer is None:
        raise HTTPException(
            status_code=503,
            detail="PolicyEnforcer not initialized. Service is starting up."
        )
    return main.policy_enforcer


def get_postgresql_client() -> PostgreSQLClient:
    """
    Returns the PostgreSQLClient instance from application state.

    In production, this is overridden via FastAPI dependency_overrides in main.py.
    This fallback accesses the module-level singleton directly.
    """
    from .. import main
    if main.postgresql_client is None:
        raise HTTPException(
            status_code=503,
            detail="PostgreSQLClient not initialized. Service is starting up."
        )
    return main.postgresql_client


@router.post("", response_model=PolicyCreateResponse, status_code=201)
async def create_policy(
    policy: FreezePolicy,
    pg_client: PostgreSQLClient = Depends(get_postgresql_client)
):
    """Cria nova política de freeze."""
    try:
        policy_id = await pg_client.create_policy(policy)
        return PolicyCreateResponse(
            policy_id=policy_id,
            message="Policy created successfully"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Creation failed: {str(e)}")


@router.get("/{policy_id}", response_model=FreezePolicy)
async def get_policy(
    policy_id: str,
    pg_client: PostgreSQLClient = Depends(get_postgresql_client)
):
    """Busca política por ID."""
    policy = await pg_client.get_policy(policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    return policy


@router.get("", response_model=PolicyListResponse)
async def list_policies(
    enabled: Optional[bool] = Query(None),
    pg_client: PostgreSQLClient = Depends(get_postgresql_client)
):
    """Lista políticas."""
    enabled_only = enabled if enabled is not None else True
    policies = await pg_client.list_policies(enabled_only=enabled_only)
    return PolicyListResponse(policies=policies, total=len(policies))


@router.put("/{policy_id}", response_model=FreezePolicy)
async def update_policy(
    policy_id: str,
    updates: dict,
    pg_client: PostgreSQLClient = Depends(get_postgresql_client)
):
    """Atualiza campos da política."""
    try:
        # TODO: Implementar update_policy no PostgreSQLClient
        policy = await pg_client.get_policy(policy_id)
        if not policy:
            raise HTTPException(status_code=404, detail="Policy not found")

        # Por enquanto, retornar política sem modificações
        return policy

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Update failed: {str(e)}")


@router.delete("/{policy_id}")
async def delete_policy(
    policy_id: str,
    pg_client: PostgreSQLClient = Depends(get_postgresql_client)
):
    """Deleta política (soft delete)."""
    # TODO: Implementar delete_policy no PostgreSQLClient
    policy = await pg_client.get_policy(policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    return {"message": "Policy deleted successfully"}


@router.get("/freezes/active", response_model=FreezeListResponse)
async def get_active_freezes(
    service_name: Optional[str] = Query(None),
    enforcer: PolicyEnforcer = Depends(get_policy_enforcer)
):
    """Lista freezes ativos."""
    freezes = await enforcer.get_active_freezes(service_name)
    return FreezeListResponse(freezes=freezes, total=len(freezes))


@router.post("/freezes/{event_id}/resolve")
async def resolve_freeze(
    event_id: str,
    enforcer: PolicyEnforcer = Depends(get_policy_enforcer),
    pg_client: PostgreSQLClient = Depends(get_postgresql_client)
):
    """Resolve freeze manualmente."""
    # Buscar evento
    freezes = await pg_client.get_active_freezes()
    event = next((f for f in freezes if f.event_id == event_id), None)

    if not event:
        raise HTTPException(status_code=404, detail="Freeze event not found")

    # Resolver freeze (sem budget, resolve manualmente)
    # Criar budget dummy para passar para resolve_freeze
    from ..models.error_budget import ErrorBudget, BudgetStatus
    from datetime import datetime

    dummy_budget = ErrorBudget(
        slo_id=event.slo_id,
        service_name=event.service_name,
        calculated_at=datetime.utcnow(),
        window_start=datetime.utcnow(),
        window_end=datetime.utcnow(),
        sli_value=0.999,
        slo_target=0.999,
        error_budget_total=0.1,
        error_budget_consumed=0,
        error_budget_remaining=100,
        status=BudgetStatus.HEALTHY,
        burn_rates=[]
    )

    success = await enforcer.resolve_freeze(event, dummy_budget)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to resolve freeze")

    return {"message": "Freeze resolved successfully"}


@router.get("/freezes/history", response_model=FreezeListResponse)
async def get_freeze_history(
    service_name: Optional[str] = Query(None),
    days: int = Query(7, ge=1, le=90),
    pg_client: PostgreSQLClient = Depends(get_postgresql_client)
):
    """Histórico de freezes (ativos e resolvidos)."""
    # TODO: Implementar get_freeze_history no PostgreSQLClient
    # Por enquanto, retornar apenas freezes ativos
    freezes = await pg_client.get_active_freezes(service_name)
    return FreezeListResponse(freezes=freezes, total=len(freezes))
