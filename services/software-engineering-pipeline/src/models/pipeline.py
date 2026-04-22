from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .schemas import (
    AnomalyType,
    GitOpsProvider,
    InsightType,
    PipelineProvider,
    PipelineStage,
    PipelineStatus,
    Severity,
)


class PipelineManifest(BaseModel):
    """Manifesto de pipeline CI/CD gerado."""

    model_config = ConfigDict(extra="forbid")

    manifest_id: str = Field(description="Identificador único do manifesto")
    repo_url: str = Field(description="URL do repositório")
    branch: str = Field(description="Branch do repositório")
    provider: PipelineProvider = Field(description="Provider de CI/CD")
    content: str = Field(description="Conteúdo YAML do pipeline")
    stack: dict[str, str] = Field(default_factory=dict, description="Informações da stack")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp de criação",
    )


class PipelineRun(BaseModel):
    """Execução de um pipeline CI/CD."""

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(description="Identificador único da execução")
    manifest_id: str = Field(description="ID do manifesto utilizado")
    repo_url: str = Field(description="URL do repositório")
    git_sha: str = Field(description="SHA do commit")
    status: PipelineStatus = Field(
        default=PipelineStatus.PENDING, description="Status atual da execução"
    )
    current_stage: PipelineStage | None = Field(
        default=None, description="Estágio atual em execução"
    )
    stages_completed: list[PipelineStage] = Field(
        default_factory=list, description="Estágios concluídos"
    )
    stages_failed: list[PipelineStage] = Field(
        default_factory=list, description="Estágios que falharam"
    )
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp de início",
    )
    finished_at: datetime | None = Field(default=None, description="Timestamp de conclusão")
    duration_seconds: int | None = Field(default=None, ge=0, description="Duração em segundos")
    logs_url: str | None = Field(default=None, description="URL dos logs da execução")
    rollback_reason: str | None = Field(default=None, description="Motivo do rollback")
    rollback_run_id: str | None = Field(default=None, description="ID da execução de rollback")


class DeployRequest(BaseModel):
    """Requisição de deploy de uma aplicação."""

    model_config = ConfigDict(extra="forbid")

    repo_url: str = Field(description="URL do repositório")
    git_sha: str = Field(description="SHA do commit para deploy")
    branch: str = Field(default="main", description="Branch do repositório")
    environment: Literal["staging", "production"] = Field(description="Ambiente de destino")
    provider: PipelineProvider = Field(
        default=PipelineProvider.GITHUB_ACTIONS, description="Provider de CI/CD"
    )
    gitops_provider: GitOpsProvider | None = Field(default=None, description="Provider de GitOps")
    timeout_minutes: int = Field(
        default=60, ge=1, le=720, description="Timeout em minutos (max 12h)"
    )


class DeployResponse(BaseModel):
    """Resposta de uma requisição de deploy."""

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(description="Identificador da execução criada")
    status: PipelineStatus = Field(description="Status inicial da execução")
    message: str = Field(description="Mensagem descritiva")


class RollbackRequest(BaseModel):
    """Requisição de rollback de um deploy."""

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(description="ID da execução para rollback")
    reason: str = Field(description="Motivo do rollback")
    force: bool = Field(
        default=False, description="Forçar rollback mesmo com health checks pendentes"
    )


class Anomaly(BaseModel):
    """Anomalia detectada em um pipeline ou execução."""

    model_config = ConfigDict(extra="forbid")

    anomaly_id: str = Field(description="Identificador único da anomalia")
    repo_url: str = Field(description="URL do repositório afetado")
    run_id: str | None = Field(default=None, description="ID da execução relacionada")
    type: AnomalyType = Field(description="Tipo da anomalia")
    severity: Severity = Field(description="Severidade da anomalia")
    description: str = Field(description="Descrição detalhada")
    affected_component: str | None = Field(default=None, description="Componente afetado")
    detected_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp de detecção",
    )
    resolved: bool = Field(default=False, description="Se foi resolvida")
    resolved_at: datetime | None = Field(default=None, description="Timestamp de resolução")
    suggested_action: str | None = Field(default=None, description="Ação sugerida para correção")


class Insight(BaseModel):
    """Insight sobre otimizações ou issues em um pipeline."""

    model_config = ConfigDict(extra="forbid")

    insight_id: str = Field(description="Identificador único do insight")
    repo_url: str = Field(description="URL do repositório analisado")
    insight_type: InsightType = Field(description="Tipo do insight")
    title: str = Field(description="Título descritivo do insight")
    description: str = Field(description="Descrição detalhada")
    impact: Severity = Field(description="Impacto da issue ou oportunidade")
    effort: Literal["S", "M", "L"] = Field(description="Esforço estimado para implementação")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp de criação",
    )


class InsightsReport(BaseModel):
    """Relatório consolidado de insights de um repositório."""

    model_config = ConfigDict(extra="forbid")

    repo_url: str = Field(description="URL do repositório analisado")
    timeframe_start: datetime = Field(description="Início do período analisado")
    timeframe_end: datetime = Field(description="Fim do período analisado")
    total_runs: int = Field(ge=0, description="Total de execuções no período")
    success_rate: float = Field(ge=0.0, le=1.0, description="Taxa de sucesso (0.0 a 1.0)")
    average_duration_seconds: float = Field(ge=0.0, description="Duração média em segundos")
    flaky_tests: list[Insight] = Field(
        default_factory=list, description="Testes flaky identificados"
    )
    slow_tests: list[Insight] = Field(
        default_factory=list, description="Testes lentos identificados"
    )
    optimization_opportunities: list[Insight] = Field(
        default_factory=list, description="Oportunidades de otimização"
    )
    security_issues: list[Insight] = Field(
        default_factory=list, description="Issues de segurança encontradas"
    )
