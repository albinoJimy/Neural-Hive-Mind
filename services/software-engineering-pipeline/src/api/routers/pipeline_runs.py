"""Router para execuções de pipeline."""

import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from src.models.pipeline import PipelineRun
from src.models.schemas import PipelineStatus
from src.repositories.pipeline_repository import PipelineRunRepository

router = APIRouter(prefix="/pipelines", tags=["pipelines"])
repo = PipelineRunRepository()


class CreatePipelineRunRequest(BaseModel):
    """Request para criar execução de pipeline."""

    model_config = ConfigDict(extra="forbid")

    manifest_id: str = Field(..., description="ID do manifesto de pipeline")
    repo_url: str = Field(..., description="URL do repositório")
    git_sha: str = Field(..., description="SHA do commit")


class PipelineRunResponse(BaseModel):
    """Response de execução de pipeline."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    manifest_id: str
    repo_url: str
    git_sha: str
    status: str
    current_stage: str | None = None
    stages_completed: list[str] = Field(default_factory=list)
    stages_failed: list[str] = Field(default_factory=list)
    started_at: str | None = None
    finished_at: str | None = None
    duration_seconds: int | None = None
    logs_url: str | None = None


class PipelineRunListResponse(BaseModel):
    """Response de lista de execuções."""

    model_config = ConfigDict(extra="forbid")

    total: int
    items: list[PipelineRunResponse]
    page: int
    per_page: int


@router.post("/runs", response_model=PipelineRunResponse, status_code=201)
async def create_run(request: CreatePipelineRunRequest) -> PipelineRunResponse:
    """Cria uma nova execução de pipeline."""
    # Gera um ID único
    run_id = str(uuid.uuid4())

    run = PipelineRun(
        run_id=run_id,
        manifest_id=request.manifest_id,
        repo_url=request.repo_url,
        git_sha=request.git_sha,
        status=PipelineStatus.PENDING,
    )

    await repo.create(run)

    return _run_to_response(run)


@router.get("/runs", response_model=PipelineRunListResponse)
async def list_runs(
    repo_url: str | None = Query(None, description="Filtrar por URL do repositório"),
    status_filter: PipelineStatus | None = Query(None, alias="status"),
    page: int = Query(1, ge=1, description="Número da página"),
    per_page: int = Query(10, ge=1, le=100, description="Itens por página"),
) -> PipelineRunListResponse:
    """Lista execuções de pipeline com paginação e filtros."""
    filter_dict: dict[str, Any] = {}
    if repo_url:
        filter_dict["repo_url"] = repo_url
    if status_filter:
        filter_dict["status"] = status_filter.value

    skip = (page - 1) * per_page

    total = await repo.count(filter_dict)
    runs = await repo.find_many(
        filter_dict=filter_dict,
        skip=skip,
        limit=per_page,
        sort=[("started_at", -1)],
    )

    return PipelineRunListResponse(
        total=total,
        items=[_run_to_response_from_dict(r) for r in runs],
        page=page,
        per_page=per_page,
    )


@router.get("/runs/{run_id}", response_model=PipelineRunResponse)
async def get_run(run_id: str) -> PipelineRunResponse:
    """Obtém detalhes de uma execução específica."""
    run = await repo.find_by_id(run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pipeline run {run_id} not found",
        )

    return _run_to_response_from_dict(run)


@router.delete("/runs/{run_id}", status_code=204)
async def delete_run(run_id: str) -> None:
    """Deleta uma execução de pipeline."""
    deleted = await repo.delete(run_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pipeline run {run_id} not found",
        )


@router.get("/repositories/{repo_url:path}/stats", response_model=dict)
async def get_repository_stats(
    repo_url: str,
    days: int = Query(30, ge=1, le=365, description="Dias de histórico"),
) -> dict:
    """Obtém estatísticas de um repositório."""
    full_repo_url = f"https://{repo_url}" if not repo_url.startswith("http") else repo_url

    success_rate = await repo.get_success_rate(full_repo_url, days=days)

    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)

    pipeline = [
        {
            "$match": {
                "repo_url": full_repo_url,
                "started_at": {"$gte": start_date, "$lte": end_date},
            }
        },
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]

    status_counts = await repo.aggregate(pipeline)

    count_by_status = {item.get("_id"): item.get("count", 0) for item in status_counts}

    total = sum(count_by_status.values())

    return {
        "repository": full_repo_url,
        "period_days": days,
        "total_runs": total,
        "success_rate": round(success_rate * 100, 2),
        "count_by_status": count_by_status,
    }


def _run_to_response(run: PipelineRun) -> PipelineRunResponse:
    """Converte um PipelineRun para PipelineRunResponse."""
    return PipelineRunResponse(
        run_id=run.run_id,
        manifest_id=run.manifest_id,
        repo_url=run.repo_url,
        git_sha=run.git_sha,
        status=run.status.value,
        current_stage=run.current_stage.value if run.current_stage else None,
        stages_completed=[s.value for s in run.stages_completed],
        stages_failed=[s.value for s in run.stages_failed],
        started_at=run.started_at.isoformat(),
        finished_at=run.finished_at.isoformat() if run.finished_at else None,
        duration_seconds=run.duration_seconds,
        logs_url=run.logs_url,
    )


def _run_to_response_from_dict(run: dict) -> PipelineRunResponse:
    """Converte um dict para PipelineRunResponse."""
    return PipelineRunResponse(
        run_id=run.get("run_id", run.get("_id", "")),
        manifest_id=run.get("manifest_id", ""),
        repo_url=run.get("repo_url", ""),
        git_sha=run.get("git_sha", ""),
        status=run.get("status", "unknown"),
        current_stage=run.get("current_stage"),
        stages_completed=run.get("stages_completed", []),
        stages_failed=run.get("stages_failed", []),
        started_at=run.get("started_at"),
        finished_at=run.get("finished_at"),
        duration_seconds=run.get("duration_seconds"),
        logs_url=run.get("logs_url"),
    )
