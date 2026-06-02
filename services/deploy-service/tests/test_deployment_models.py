"""Tests para Deployment models."""

from src.models.deployment import (
    DeploymentRequest,
    DeploymentResponse,
    DeploymentStatus,
    HealthCheckSpec,
    HealthCheckStatus,
    IngressSpec,
    ResourceSpec,
)


class TestDeploymentRequest:
    """Testes para DeploymentRequest."""

    def test_creation_minimal(self):
        """Testa criação mínima de DeploymentRequest."""
        request = DeploymentRequest(
            service_name="test-service",
            version="v1.0.0",
            container_image="service:latest",
        )

        assert request.service_name == "test-service"
        assert request.version == "v1.0.0"
        assert request.container_image == "service:latest"
        assert request.namespace == "default"
        assert request.replicas == 2

    def test_creation_with_all_fields(self):
        """Testa criação com todos os campos."""
        request = DeploymentRequest(
            service_name="test-service",
            version="v1.0.0",
            container_image="service:latest",
            namespace="nhm",
            replicas=3,
            resources=ResourceSpec(cpu="1000m", memory="1Gi"),
            environment="staging",
            plan_id="plan-123",
        )

        assert request.namespace == "nhm"
        assert request.replicas == 3
        assert request.resources.cpu == "1000m"
        assert request.environment == "staging"


class TestDeploymentResponse:
    """Testes para DeploymentResponse."""

    def test_creation_success(self):
        """Testa criação de resposta com sucesso."""
        response = DeploymentResponse(
            deployment_id="test-service-v1.0.0",
            service_name="test-service",
            version="v1.0.0",
            status=DeploymentStatus.DEPLOYED,
        )

        assert response.deployment_id == "test-service-v1.0.0"
        assert response.service_name == "test-service"
        assert response.status == DeploymentStatus.DEPLOYED

    def test_creation_failure(self):
        """Testa criação de resposta com falha."""
        response = DeploymentResponse(
            deployment_id="test-service-v1.0.0",
            service_name="test-service",
            version="v1.0.0",
            status=DeploymentStatus.FAILED,
            error="Deployment failed",
        )

        assert response.status == DeploymentStatus.FAILED
        assert response.error == "Deployment failed"


class TestDeploymentStatus:
    """Testes para DeploymentStatus enum."""

    def test_all_statuses(self):
        """Testa todos os status disponíveis."""
        assert DeploymentStatus.PENDING.value == "pending"
        assert DeploymentStatus.PROVISIONING.value == "provisioning"
        assert DeploymentStatus.DEPLOYING.value == "deploying"
        assert DeploymentStatus.HEALTH_CHECKING.value == "health_checking"
        assert DeploymentStatus.DEPLOYED.value == "deployed"
        assert DeploymentStatus.FAILED.value == "failed"
        assert DeploymentStatus.ROLLING_BACK.value == "rolling_back"
        assert DeploymentStatus.ROLLBACK_COMPLETE.value == "rollback_complete"


class TestHealthCheckStatus:
    """Testes para HealthCheckStatus enum."""

    def test_all_statuses(self):
        """Testa todos os status."""
        assert HealthCheckStatus.HEALTHY.value == "healthy"
        assert HealthCheckStatus.UNHEALTHY.value == "unhealthy"
        assert HealthCheckStatus.UNKNOWN.value == "unknown"
        assert HealthCheckStatus.PENDING.value == "pending"


class TestResourceSpec:
    """Testes para ResourceSpec."""

    def test_defaults(self):
        """Testa valores padrão."""
        spec = ResourceSpec()

        assert spec.cpu == "500m"
        assert spec.memory == "512Mi"
        assert spec.limits is None

    def test_custom(self):
        """Testa valores customizados."""
        spec = ResourceSpec(
            cpu="1000m",
            memory="1Gi",
            limits={"cpu": "2000m", "memory": "2Gi"},
        )

        assert spec.cpu == "1000m"
        assert spec.memory == "1Gi"
        assert spec.limits["cpu"] == "2000m"


class TestHealthCheckSpec:
    """Testes para HealthCheckSpec."""

    def test_defaults(self):
        """Testa valores padrão."""
        spec = HealthCheckSpec()

        assert spec.liveness_path == "/health/live"
        assert spec.readiness_path == "/health/ready"
        assert spec.initial_delay == 10
        assert spec.period == 10
        assert spec.timeout == 5
        assert spec.failure_threshold == 3


class TestIngressSpec:
    """Testes para IngressSpec."""

    def test_defaults(self):
        """Testa valores padrão."""
        spec = IngressSpec(host="example.com")

        assert spec.enabled is True
        assert spec.host == "example.com"
        assert spec.path == "/"
        assert spec.tls_enabled is False
        assert spec.annotations is None
