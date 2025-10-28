"""
Router FastAPI para endpoints de error budgets.
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from ..models.error_budget import ErrorBudget
from ..services.budget_calculator import BudgetCalculator
from ..clients.postgresql_client import PostgreSQLClient
from ..clients.prometheus_client import PrometheusClient


router = APIRouter(prefix="/api/v1/budgets", tags=["Error Budgets"])


# Response models
class BudgetListResponse(BaseModel):
    budgets: List[ErrorBudget]
    total: int


class BudgetSummaryResponse(BaseModel):
    total_slos: int
    healthy: int
    warning: int
    critical: int
    exhausted: int
    average_remaining: float


class BurnRateResponse(BaseModel):
    burn_rate: float
    level: str
    estimated_exhaustion_hours: Optional[float] = None


# Dependency injection
def get_budget_calculator() -> BudgetCalculator:
    raise NotImplementedError


def get_postgresql_client() -> PostgreSQLClient:
    raise NotImplementedError


def get_prometheus_client() -> PrometheusClient:
    raise NotImplementedError


@router.get("/{slo_id}", response_model=ErrorBudget)
async def get_budget(
    slo_id: str,
    use_cache: bool = Query(True),
    calculator: BudgetCalculator = Depends(get_budget_calculator)
):
    """Busca budget de um SLO."""
    budget = await calculator.get_budget(slo_id, use_cache=use_cache)
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")
    return budget


@router.get("", response_model=BudgetListResponse)
async def list_budgets(
    service_name: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    pg_client: PostgreSQLClient = Depends(get_postgresql_client)
):
    """Lista budgets mais recentes."""
    # Buscar todos os SLOs
    slos = await pg_client.list_slos(
        service_name=service_name,
        enabled_only=True
    )

    budgets = []
    for slo in slos:
        budget = await pg_client.get_latest_budget(slo.slo_id)
        if budget:
            # Filtrar por status se especificado
            if status and budget.status.value != status:
                continue
            budgets.append(budget)

    return BudgetListResponse(budgets=budgets, total=len(budgets))


@router.post("/{slo_id}/recalculate", response_model=ErrorBudget)
async def recalculate_budget(
    slo_id: str,
    calculator: BudgetCalculator = Depends(get_budget_calculator)
):
    """Força recálculo do budget."""
    try:
        budget = await calculator.recalculate_budget(slo_id)
        return budget
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Calculation failed: {str(e)}")


@router.get("/{slo_id}/history", response_model=BudgetListResponse)
async def get_budget_history(
    slo_id: str,
    days: int = Query(7, ge=1, le=90),
    pg_client: PostgreSQLClient = Depends(get_postgresql_client)
):
    """Retorna histórico de budgets."""
    # TODO: Implementar get_budget_history no PostgreSQLClient
    # Por enquanto, retornar apenas o budget mais recente
    budget = await pg_client.get_latest_budget(slo_id)
    budgets = [budget] if budget else []
    return BudgetListResponse(budgets=budgets, total=len(budgets))


@router.get("/summary", response_model=BudgetSummaryResponse)
async def get_budgets_summary(
    pg_client: PostgreSQLClient = Depends(get_postgresql_client)
):
    """Retorna resumo agregado de todos os budgets."""
    slos = await pg_client.list_slos(enabled_only=True)

    total_slos = len(slos)
    healthy = 0
    warning = 0
    critical = 0
    exhausted = 0
    total_remaining = 0.0

    for slo in slos:
        budget = await pg_client.get_latest_budget(slo.slo_id)
        if budget:
            total_remaining += budget.error_budget_remaining

            status = budget.status.value
            if status == "HEALTHY":
                healthy += 1
            elif status == "WARNING":
                warning += 1
            elif status == "CRITICAL":
                critical += 1
            elif status == "EXHAUSTED":
                exhausted += 1

    average_remaining = total_remaining / total_slos if total_slos > 0 else 0

    return BudgetSummaryResponse(
        total_slos=total_slos,
        healthy=healthy,
        warning=warning,
        critical=critical,
        exhausted=exhausted,
        average_remaining=average_remaining
    )


@router.get("/{slo_id}/burn-rate", response_model=BurnRateResponse)
async def get_burn_rate(
    slo_id: str,
    window_hours: int = Query(1, ge=1, le=168),
    pg_client: PostgreSQLClient = Depends(get_postgresql_client),
    prom_client: PrometheusClient = Depends(get_prometheus_client)
):
    """Calcula burn rate para janela específica."""
    # Buscar SLO para obter service_name
    slo = await pg_client.get_slo(slo_id)
    if not slo:
        raise HTTPException(status_code=404, detail="SLO not found")

    # Calcular burn rate
    burn_rate = await prom_client.calculate_burn_rate(
        slo.service_name,
        window_hours,
        baseline_days=30
    )

    # Classificar nível
    from ..models.error_budget import BurnRateLevel
    if burn_rate >= 14.4:
        level = BurnRateLevel.CRITICAL
    elif burn_rate >= 6:
        level = BurnRateLevel.FAST
    elif burn_rate >= 2:
        level = BurnRateLevel.ELEVATED
    else:
        level = BurnRateLevel.NORMAL

    # Estimar tempo até esgotar (simplificado)
    estimated_exhaustion = None
    if burn_rate > 0:
        budget = await pg_client.get_latest_budget(slo_id)
        if budget:
            estimated_exhaustion = (budget.error_budget_remaining / burn_rate) * window_hours

    return BurnRateResponse(
        burn_rate=burn_rate,
        level=level.value,
        estimated_exhaustion_hours=estimated_exhaustion
    )
