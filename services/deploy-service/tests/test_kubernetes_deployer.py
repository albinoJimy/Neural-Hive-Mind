"""Tests para KubernetesDeployer."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.deployment import (
    DeploymentRequest,
    DeploymentResponse,
    DeploymentStatus,
    HealthCheckSpec,
    IngressSpec,
    ResourceSpec,
)
from src.services.kubernetes_deployer import KubernetesDeployer


@pytest.fixture()
def mock_kubectl():
    """Mock para comandos kubectl."""

    async def mock_create_process(*args, **kwargs):
        """Cria um mock de processo."""
        process = MagicMock()

        # Determina qual comando está sendo executado
        cmd_str = " ".join(str(a) for a in args)

        async def mock_communicate(input_data=None, **kwargs):
            # Retornar dados diferentes baseado no comando
            if "get pods" in cmd_str:
                return (
                    b'{"items":[{"status":{"conditions":[{"type":"Ready","status":"True"}]}}]}',
                    b"",
                )
            elif "get deployment/" in cmd_str:
                return (
                    b'{"spec":{"replicas":2},"status":{"availableReplicas":2,"updatedReplicas":2,"readyReplicas":2}}',
                    b"",
                )
            elif "rollout status" in cmd_str:
                return (b"deployment successfully rolled out", b"")
            # Para todos os outros comandos (apply, create, etc.)
            return (b"", b"")

        process.communicate = mock_communicate
        process.returncode = 0
        return process

    with patch("asyncio.create_subprocess_exec", side_effect=mock_create_process):
        yield


@pytest.fixture()
def deployer():
    """Fixture para KubernetesDeployer."""
    return KubernetesDeployer()


@pytest.fixture()
def sample_deployment_request():
    """DeploymentRequest de exemplo."""
    return DeploymentRequest(
        service_name="test-service",
        version="v1.0.0",
        container_image="service:v1.0.0",
        namespace="nhm",
        replicas=2,
        resources=ResourceSpec(cpu="500m", memory="512Mi"),
        health_checks=HealthCheckSpec(),
        ingress=IngressSpec(host="test-service.nhm.local"),
    )


class TestKubernetesDeployer:
    """Testes para KubernetesDeployer."""

    def test_initialization(self):
        """Testa inicialização."""
        deployer = KubernetesDeployer()

        assert deployer.namespace is not None
        assert deployer.kubeconfig is not None

    @pytest.mark.asyncio()
    async def test_deploy_success(self, deployer, mock_kubectl, sample_deployment_request):
        """Testa deployment bem-sucedido."""
        result = await deployer.deploy(sample_deployment_request)

        assert isinstance(result, DeploymentResponse)
        assert result.service_name == "test-service"
        assert result.status == DeploymentStatus.DEPLOYED
        assert result.kubernetes.replicas == 2
        assert result.kubernetes.ready_replicas == 2

    @pytest.mark.asyncio()
    async def test_deploy_failure(self, deployer, sample_deployment_request):
        """Testa deployment com falha."""

        async def mock_create_process_fail(*args, **kwargs):
            """Cria um mock de processo que falha."""
            process = MagicMock()
            process.communicate = AsyncMock(return_value=(b"", b"Error applying manifest"))
            process.returncode = 1
            return process

        with patch("asyncio.create_subprocess_exec", side_effect=mock_create_process_fail):
            result = await deployer.deploy(sample_deployment_request)

            assert result.status == DeploymentStatus.FAILED
            assert result.error is not None

    @pytest.mark.asyncio()
    async def test_rollback(self, deployer, mock_kubectl):
        """Testa rollback de deployment."""
        result = await deployer.rollback("test-service-v1.0.0", "nhm")

        assert result["deployment_name"] == "test-service-v1.0.0"
        assert result["rollback_status"] == "completed"

    @pytest.mark.asyncio()
    async def test_rollback_failure(self, deployer):
        """Testa rollback com falha."""

        async def mock_create_process_fail(*args, **kwargs):
            """Cria um mock de processo que falha."""
            process = MagicMock()
            process.communicate = AsyncMock(return_value=(b"", b"Rollback failed"))
            process.returncode = 1
            return process

        with patch("asyncio.create_subprocess_exec", side_effect=mock_create_process_fail):
            with pytest.raises(RuntimeError, match="Rollback failed"):
                await deployer.rollback("test-service-v1.0.0", "nhm")

    @pytest.mark.asyncio()
    async def test_deploy_without_ingress(self, deployer, mock_kubectl, sample_deployment_request):
        """Testa deployment sem ingress."""
        sample_deployment_request.ingress = None

        result = await deployer.deploy(sample_deployment_request)

        assert result.status == DeploymentStatus.DEPLOYED
        assert result.service.ingress_url == ""

    @pytest.mark.asyncio()
    async def test_deploy_with_custom_resources(
        self, deployer, mock_kubectl, sample_deployment_request
    ):
        """Testa deployment com recursos customizados."""
        sample_deployment_request.resources = ResourceSpec(
            cpu="1000m", memory="1Gi", limits={"cpu": "2000m", "memory": "2Gi"}
        )

        result = await deployer.deploy(sample_deployment_request)

        assert result.status == DeploymentStatus.DEPLOYED

    @pytest.mark.asyncio()
    async def test_deploy_with_tls_ingress(self, deployer, mock_kubectl, sample_deployment_request):
        """Testa deployment com ingress TLS."""
        sample_deployment_request.ingress.tls_enabled = True

        result = await deployer.deploy(sample_deployment_request)

        assert result.status == DeploymentStatus.DEPLOYED
        assert "https://" in result.service.ingress_url
