"""Configurações do Fluxo G Dashboard."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações do Dashboard."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_prefix="FLUXO_G_DASHBOARD_",
    )

    # API
    api_title: str = "Fluxo G Dashboard"
    api_version: str = "0.1.0"
    host: str = "0.0.0.0"
    port: int = 8018

    # Temporal
    temporal_host: str = Field(
        default="temporal-frontend.temporal.svc.cluster.local",
        description="Host do Temporal"
    )
    temporal_port: int = Field(default=7233, description="Porta do Temporal")
    temporal_namespace: str = Field(default="default", description="Namespace")
    temporal_task_queue: str = Field(
        default="orchestration-tasks",
        description="Fila de tarefas do Fluxo G"
    )

    # Services URLs
    orchestrator_url: str = Field(
        default="http://orchestrator-dynamic:8003",
        description="URL do Orchestrator"
    )
    requirements_url: str = Field(
        default="http://requirements-engineering:8010",
        description="URL do Requirements Engineering"
    )
    documentation_url: str = Field(
        default="http://documentation-generation:8014",
        description="URL do Documentation Generation"
    )
    knowledge_graph_url: str = Field(
        default="http://knowledge-graph-rag:8016",
        description="URL do Knowledge Graph RAG"
    )
    approval_url: str = Field(
        default="http://approval-gateway:8017",
        description="URL do Approval Gateway"
    )

    # Dashboard Settings
    refresh_interval_seconds: int = Field(
        default=30,
        ge=5,
        le=300,
        description="Intervalo de refresh automático"
    )
    max_workflows_display: int = Field(
        default=50,
        ge=10,
        le=500,
        description="Máximo de workflows a exibir"
    )

    # Service Info
    service_name: str = "fluxo-g-dashboard"
    service_version: str = "0.1.0"


@lru_cache
def get_settings() -> Settings:
    """Retorna instância singleton."""
    return Settings()
