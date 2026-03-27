from enum import Enum
from pydantic import BaseModel, Field
from typing import Literal
from datetime import datetime, timezone


class PipelineProvider(str, Enum):
    GITHUB_ACTIONS = 'github_actions'
    GITLAB_CI = 'gitlab_ci'
    JENKINS = 'jenkins'
    TEKTON = 'tekton'


class GitOpsProvider(str, Enum):
    ARGOCD = 'argocd'
    FLUX_CD = 'flux_cd'
    KUBECTL = 'kubectl'


class PipelineStatus(str, Enum):
    PENDING = 'pending'
    RUNNING = 'running'
    SUCCESS = 'success'
    FAILED = 'failed'
    CANCELLED = 'cancelled'
    ROLLED_BACK = 'rolled_back'


class PipelineStage(str, Enum):
    PRE_FLIGHT = 'pre_flight'
    BUILD = 'build'
    TEST = 'test'
    SECURITY = 'security'
    STAGING = 'staging'
    APPROVAL = 'approval'
    PRODUCTION = 'production'


class Severity(str, Enum):
    LOW = 'low'
    MEDIUM = 'medium'
    HIGH = 'high'
    CRITICAL = 'critical'


class ProjectStack(BaseModel):
    language: str
    framework: str | None = None
    package_manager: str
    has_dockerfile: bool = False
    has_docker_compose: bool = False
    has_helm_chart: bool = False
    kubernetes_manifests: bool = False


class Component(BaseModel):
    name: str
    image: str
    replicas: int = 1
    port: int | None = None
    env_vars: dict[str, str] = Field(default_factory=dict)


class AnomalyType(str, Enum):
    FLAKY_TEST = 'flaky_test'
    DEPENDENCY_ISSUE = 'dependency_issue'
    PERFORMANCE_DEGRADATION = 'performance_degradation'
    SECURITY_VULNERABILITY = 'security_vulnerability'
    CONFIGURATION_DRIFT = 'configuration_drift'
