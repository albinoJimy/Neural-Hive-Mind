"""Router para insights e relatórios."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field

from src.repositories.pipeline_repository import (
    AnomalyRepository,
    PipelineRunRepository,
)

router = APIRouter(prefix="/insights", tags=["insights"])
run_repo = PipelineRunRepository()
anomaly_repo = AnomalyRepository()


class GenerateInsightsRequest(BaseModel):
    """Request para gerar insights."""

    model_config = ConfigDict(extra="forbid")

    repo_url: str = Field(..., description="URL do repositório")
    days: int = Field(default=7, ge=1, le=90, description="Dias de análise")


class InsightsReportResponse(BaseModel):
    """Response de relatório de insights."""

    model_config = ConfigDict(extra="forbid")

    repo_url: str
    timeframe_start: str
    timeframe_end: str
    total_runs: int
    success_rate: float
    average_duration_seconds: float


@router.post("/generate", response_model=InsightsReportResponse)
async def generate_insights(request: GenerateInsightsRequest) -> InsightsReportResponse:
    """Gera insights para um repositório."""
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=request.days)

    runs = await run_repo.find_by_date_range(request.repo_url, start_date, end_date)

    # Calcula métricas
    total = len(runs)
    successful = sum(1 for r in runs if r.get("status") == "success")
    success_rate = successful / total if total > 0 else 0.0

    durations = [r.get("duration_seconds", 0) for r in runs if r.get("duration_seconds")]
    avg_duration = sum(durations) / len(durations) if durations else 0.0

    return InsightsReportResponse(
        repo_url=request.repo_url,
        timeframe_start=start_date.isoformat(),
        timeframe_end=end_date.isoformat(),
        total_runs=total,
        success_rate=success_rate,
        average_duration_seconds=avg_duration,
    )


@router.get("/repositories/{repo_url:path}/health", response_model=dict)
async def get_repository_health(
    repo_url: str,
    days: int = Query(30, ge=1, le=365, description="Dias de análise"),
) -> dict:
    """Obtém um resumo de saúde de um repositório."""
    full_repo_url = f"https://{repo_url}" if not repo_url.startswith("http") else repo_url

    success_rate = await run_repo.get_success_rate(full_repo_url, days=days)

    # Buscar anomalias não resolvidas
    unresolved_anomalies = await anomaly_repo.find_unresolved(full_repo_url)

    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)

    recent_runs = await run_repo.find_by_date_range(full_repo_url, start_date, end_date)

    # Calcula duração média
    durations = [r.get("duration_seconds", 0) for r in recent_runs if r.get("duration_seconds")]
    avg_duration = sum(durations) / len(durations) if durations else 0

    # Classifica saúde
    if success_rate >= 0.95 and len(unresolved_anomalies) == 0:
        health_status = "excellent"
    elif success_rate >= 0.85 and len(unresolved_anomalies) <= 2:
        health_status = "good"
    elif success_rate >= 0.70:
        health_status = "warning"
    else:
        health_status = "critical"

    return {
        "repository": full_repo_url,
        "health_status": health_status,
        "period_days": days,
        "success_rate": round(success_rate * 100, 2),
        "total_runs": len(recent_runs),
        "unresolved_anomalies": len(unresolved_anomalies),
        "average_duration_seconds": round(avg_duration, 2),
        "last_run_at": recent_runs[0].get("started_at") if recent_runs else None,
    }
