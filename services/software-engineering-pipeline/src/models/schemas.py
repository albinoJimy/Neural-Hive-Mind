from enum import Enum
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from datetime import datetime, timezone


class PipelineProvider(str, Enum):
    GITHUB_ACTIONS = "github_actions"
    GITLAB_CI = "gitlab_ci"
    JENKINS = "jenkins"
    TEKTON = "tekton"


class GitOpsProvider(str, Enum):
    ARGOCD = "argocd"
    FLUX_CD = "flux_cd"
    KUBECTL = "kubectl"


class PipelineStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ROLLED_BACK = "rolled_back"


class PipelineStage(str, Enum):
    PRE_FLIGHT = "pre_flight"
    BUILD = "build"
    TEST = "test"
    SECURITY = "security"
    STAGING = "staging"
    APPROVAL = "approval"
    PRODUCTION = "production"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ProjectStack(BaseModel):
    """Informações sobre a stack tecnológica de um projeto."""

    model_config = ConfigDict(extra="forbid")

    language: str = Field(description="Linguagem de programação principal")
    framework: str | None = Field(default=None, description="Framework web utilizado")
    package_manager: str = Field(description="Gerenciador de pacotes")
    has_dockerfile: bool = Field(default=False, description="Se existe Dockerfile")
    has_docker_compose: bool = Field(
        default=False, description="Se existe docker-compose.yml"
    )
    has_helm_chart: bool = Field(default=False, description="Se existe chart Helm")
    kubernetes_manifests: bool = Field(
        default=False, description="Se existem manifests K8s"
    )


class Component(BaseModel):
    """Componente de uma aplicação para deploy."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Nome do componente")
    image: str = Field(description="Imagem Docker do componente")
    replicas: int = Field(default=1, ge=0, description="Número de réplicas")
    port: int | None = Field(default=None, description="Porta exposta pelo componente")
    env_vars: dict[str, str] = Field(
        default_factory=dict, description="Variáveis de ambiente do componente"
    )


class AnomalyType(str, Enum):
    FLAKY_TEST = "flaky_test"
    DEPENDENCY_ISSUE = "dependency_issue"
    PERFORMANCE_DEGRADATION = "performance_degradation"
    SECURITY_VULNERABILITY = "security_vulnerability"
    CONFIGURATION_DRIFT = "configuration_drift"


class InsightType(str, Enum):
    FLAKY_TEST = "flaky_test"
    SLOW_TEST = "slow_test"
    DEPENDENCY_ISSUE = "dependency_issue"
    CACHE_OPPORTUNITY = "cache_opportunity"
    PARALLELIZATION_OPPORTUNITY = "parallelization_opportunity"
    SECURITY_ISSUE = "security_issue"
