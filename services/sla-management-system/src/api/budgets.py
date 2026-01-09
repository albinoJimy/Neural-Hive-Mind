"""
Router FastAPI para endpoints de error budgets.
"""

import json
import time
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, Query, Response
from pydantic import BaseModel

from ..models.error_budget import ErrorBudget
from ..services.budget_calculator import BudgetCalculator
from ..clients.postgresql_client import PostgreSQLClient
from ..clients.prometheus_client import PrometheusClient
from ..clients.redis_client import RedisClient
from ..observability.metrics import sla_metrics


router = APIRouter(prefix="/api/v1/budgets", tags=["Error Budgets"])


# Response models
class BudgetListResponse(BaseModel):
    budgets: List[ErrorBudget]
    total: int


class BudgetTrends(BaseModel):
    """Tendências e estatísticas de budget."""
    trend_direction: str
    average_remaining: float
    min_remaining: float
    max_consumed: float
    volatility: float
    violations_frequency: float
    burn_rate_avg: float


class BudgetHistoryResponse(BaseModel):
    """Response para histórico de budgets com suporte a tendências."""
    budgets: List[ErrorBudget]
    total: int
    period_days: int
    aggregation: Optional[str] = None
    trends: Optional[BudgetTrends] = None


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
    """
    Retorna a instância de BudgetCalculator do estado da aplicação.

    Em produção, é sobrescrito via dependency_overrides do FastAPI em main.py.
    Este fallback acessa o singleton do módulo diretamente.
    """
    from .. import main
    if main.budget_calculator is None:
        raise HTTPException(
            status_code=503,
            detail="BudgetCalculator não inicializado. Serviço iniciando."
        )
    return main.budget_calculator


def get_postgresql_client() -> PostgreSQLClient:
    """
    Retorna a instância de PostgreSQLClient do estado da aplicação.

    Em produção, é sobrescrito via dependency_overrides do FastAPI em main.py.
    Este fallback acessa o singleton do módulo diretamente.
    """
    from .. import main
    if main.postgresql_client is None:
        raise HTTPException(
            status_code=503,
            detail="PostgreSQLClient não inicializado. Serviço iniciando."
        )
    return main.postgresql_client


def get_prometheus_client() -> PrometheusClient:
    """
    Retorna a instância de PrometheusClient do estado da aplicação.

    Em produção, é sobrescrito via dependency_overrides do FastAPI em main.py.
    Este fallback acessa o singleton do módulo diretamente.
    """
    from .. import main
    if main.prometheus_client is None:
        raise HTTPException(
            status_code=503,
            detail="PrometheusClient não inicializado. Serviço iniciando."
        )
    return main.prometheus_client


def get_redis_client() -> RedisClient:
    """
    Retorna a instância de RedisClient do estado da aplicação.

    Em produção, é sobrescrito via dependency_overrides do FastAPI em main.py.
    Este fallback acessa o singleton do módulo diretamente.
    """
    from .. import main
    if main.redis_client is None:
        raise HTTPException(
            status_code=503,
            detail="RedisClient não inicializado. Serviço iniciando."
        )
    return main.redis_client


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


@router.get("/{slo_id}/history", response_model=BudgetHistoryResponse)
async def get_budget_history(
    slo_id: str,
    response: Response,
    days: int = Query(7, ge=1, le=90),
    aggregation: Optional[str] = Query(None, regex="^(hourly|daily|none)$"),
    include_trends: bool = Query(False),
    pg_client: PostgreSQLClient = Depends(get_postgresql_client),
    redis_client: RedisClient = Depends(get_redis_client)
):
    """
    Retorna histórico de budgets com suporte a agregações e tendências.

    Inclui:
    - Rate limiting: 10 requests/minuto por slo_id
    - Cache Redis: TTL 300s (5 minutos)
    - Métricas Prometheus para monitoramento

    Args:
        slo_id: ID do SLO
        days: Período em dias (1-90, default: 7)
        aggregation: Tipo de agregação (hourly, daily, none)
        include_trends: Se True, inclui análise de tendências
    """
    start_time = time.time()
    agg_key = aggregation if aggregation and aggregation != 'none' else None

    # Rate limiting: 10 req/min por slo_id
    allowed, remaining = await redis_client.check_rate_limit(
        slo_id=slo_id,
        limit=10,
        window_seconds=60
    )
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    response.headers["X-RateLimit-Limit"] = "10"

    if not allowed:
        sla_metrics.record_budget_history_query(
            aggregation=agg_key or "none",
            days=days,
            duration=time.time() - start_time,
            success=False,
            result_count=0,
            slo_id=slo_id
        )
        raise HTTPException(
            status_code=429,
            detail="Rate limit excedido. Tente novamente em 1 minuto.",
            headers={"Retry-After": "60"}
        )

    # Verificar se SLO existe
    slo = await pg_client.get_slo(slo_id)
    if not slo:
        raise HTTPException(status_code=404, detail="SLO não encontrado")

    # Tentar obter do cache (exceto quando include_trends=True, pois trends não são cacheadas)
    if not include_trends:
        cached = await redis_client.get_cached_budget_history(slo_id, days, agg_key)
        if cached:
            try:
                cached_data = json.loads(cached)
                budgets = [ErrorBudget(**b) for b in cached_data]
                duration = time.time() - start_time

                sla_metrics.record_budget_history_query(
                    aggregation=agg_key or "none",
                    days=days,
                    duration=duration,
                    success=True,
                    result_count=len(budgets),
                    slo_id=slo_id
                )

                response.headers["X-Cache"] = "HIT"
                return BudgetHistoryResponse(
                    budgets=budgets,
                    total=len(budgets),
                    period_days=days,
                    aggregation=agg_key,
                    trends=None
                )
            except Exception:
                # Cache corrompido, buscar do banco
                pass

    response.headers["X-Cache"] = "MISS"

    # Buscar histórico do banco
    try:
        budgets = await pg_client.get_budget_history(slo_id, days, agg_key)
        duration = time.time() - start_time

        # Registrar métricas
        sla_metrics.record_budget_history_query(
            aggregation=agg_key or "none",
            days=days,
            duration=duration,
            success=True,
            result_count=len(budgets),
            slo_id=slo_id
        )

        # Armazenar no cache (se não estiver pedindo trends)
        if not include_trends and budgets:
            budgets_json = json.dumps([b.model_dump(mode='json') for b in budgets])
            await redis_client.cache_budget_history(
                slo_id=slo_id,
                days=days,
                aggregation=agg_key,
                budgets_json=budgets_json,
                ttl=300  # 5 minutos
            )

    except Exception as e:
        duration = time.time() - start_time
        sla_metrics.record_budget_history_query(
            aggregation=agg_key or "none",
            days=days,
            duration=duration,
            success=False,
            result_count=0,
            slo_id=slo_id
        )
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao buscar histórico: {str(e)}"
        )

    # Buscar tendências se solicitado
    trends = None
    if include_trends:
        trends_data = await pg_client.get_budget_trends(slo_id, days)
        trends = BudgetTrends(**trends_data)

    return BudgetHistoryResponse(
        budgets=budgets,
        total=len(budgets),
        period_days=days,
        aggregation=agg_key,
        trends=trends
    )


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
