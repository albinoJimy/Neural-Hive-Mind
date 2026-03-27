from pydantic import BaseModel, Field
from typing import Literal
from datetime import datetime, timezone
from .schemas import (
    PipelineProvider,
    PipelineStatus,
    PipelineStage,
    GitOpsProvider,
    Severity,
    AnomalyType,
)


class PipelineManifest(BaseModel):
    manifest_id: str
    repo_url: str
    branch: str
    provider: PipelineProvider
    content: str
    stack: dict[str, str]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PipelineRun(BaseModel):
    run_id: str
    manifest_id: str
    repo_url: str
    git_sha: str
    status: PipelineStatus = PipelineStatus.PENDING
    current_stage: PipelineStage | None = None
    stages_completed: list[PipelineStage] = Field(default_factory=list)
    stages_failed: list[PipelineStage] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    duration_seconds: int | None = None
    logs_url: str | None = None
    rollback_reason: str | None = None
    rollback_run_id: str | None = None


class DeployRequest(BaseModel):
    repo_url: str
    git_sha: str
    branch: str = 'main'
    environment: Literal['staging', 'production']
    provider: PipelineProvider = PipelineProvider.GITHUB_ACTIONS
    gitops_provider: GitOpsProvider | None = None
    timeout_minutes: int = 60


class DeployResponse(BaseModel):
    run_id: str
    status: PipelineStatus
    message: str


class RollbackRequest(BaseModel):
    run_id: str
    reason: str
    force: bool = False


class Anomaly(BaseModel):
    anomaly_id: str
    repo_url: str
    run_id: str | None = None
    type: AnomalyType
    severity: Severity
    description: str
    affected_component: str | None = None
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resolved: bool = False
    resolved_at: datetime | None = None
    suggested_action: str | None = None


class Insight(BaseModel):
    insight_id: str
    repo_url: str
    insight_type: Literal[
        'flaky_test',
        'slow_test',
        'dependency_issue',
        'cache_opportunity',
        'parallelization_opportunity',
        'security_issue',
    ]
    title: str
    description: str
    impact: Severity
    effort: Literal['S', 'M', 'L']
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class InsightsReport(BaseModel):
    repo_url: str
    timeframe_start: datetime
    timeframe_end: datetime
    total_runs: int
    success_rate: float
    average_duration_seconds: float
    flaky_tests: list[Insight]
    slow_tests: list[Insight]
    optimization_opportunities: list[Insight]
    security_issues: list[Insight]
