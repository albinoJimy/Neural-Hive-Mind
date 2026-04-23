"""
Deployment models for Deploy Service.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DeploymentStatus(str, Enum):
    """Status de um deployment."""

    PENDING = "pending"
    PROVISIONING = "provisioning"
    DEPLOYING = "deploying"
    HEALTH_CHECKING = "health_checking"
    DEPLOYED = "deployed"
    FAILED = "failed"
    ROLLING_BACK = "rolling_back"
    ROLLBACK_COMPLETE = "rollback_complete"


class HealthCheckStatus(str, Enum):
    """Status de health check."""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"
    PENDING = "pending"


class ResourceSpec(BaseModel):
    """Especificação de recursos."""

    cpu: str = "500m"
    memory: str = "512Mi"
    limits: dict[str, str] | None = None


class HealthCheckSpec(BaseModel):
    """Especificação de health checks."""

    liveness_path: str = "/health/live"
    readiness_path: str = "/health/ready"
    initial_delay: int = 10
    period: int = 10
    timeout: int = 5
    failure_threshold: int = 3


class IngressSpec(BaseModel):
    """Especificação de ingress."""

    enabled: bool = True
    host: str
    path: str = "/"
    tls_enabled: bool = False
    annotations: dict[str, str] | None = None


class DeploymentRequest(BaseModel):
    """Request para criar um deployment."""

    service_name: str
    version: str
    container_image: str
    namespace: str = "default"
    replicas: int = 2
    resources: ResourceSpec | None = None
    environment: str = "production"
    ingress: IngressSpec | None = None
    health_checks: HealthCheckSpec | None = None
    config_maps: dict[str, str] | None = None
    secrets_ref: str = ""
    plan_id: str = ""


class HealthCheckResult(BaseModel):
    """Resultado de health check."""

    liveness: HealthCheckStatus = HealthCheckStatus.UNKNOWN
    readiness: HealthCheckStatus = HealthCheckStatus.UNKNOWN
    custom: dict[str, Any] = Field(default_factory=dict)


class KubernetesInfo(BaseModel):
    """Informações do Kubernetes."""

    deployment_name: str
    namespace: str
    replicas: int = 0
    available_replicas: int = 0
    updated_replicas: int = 0
    ready_replicas: int = 0


class ServiceInfo(BaseModel):
    """Informações do Service."""

    name: str
    namespace: str
    port: int = 80
    target_port: int = 8080
    url: str = ""
    ingress_url: str = ""


class DeploymentResponse(BaseModel):
    """Response de um deployment."""

    deployment_id: str
    plan_id: str = ""
    service_name: str
    version: str
    status: DeploymentStatus = DeploymentStatus.PENDING
    kubernetes: KubernetesInfo | None = None
    service: ServiceInfo | None = None
    health_checks: HealthCheckResult | None = None
    rollback_enabled: bool = True
    previous_version: str | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    duration_ms: int = 0


class RollbackRequest(BaseModel):
    """Request para rollback."""

    reason: str = "manual"


class RollbackResponse(BaseModel):
    """Response de rollback."""

    deployment_id: str
    rollback_status: str
    previous_version: str | None = None
    reason: str
