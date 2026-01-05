"""
Testes de integracao para operacoes de remediacao Kubernetes

Testa operacoes de restart de pods, scaling, rollback e NetworkPolicies
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from kubernetes.client.rest import ApiException
from kubernetes import client

from src.clients.kubernetes_client import KubernetesClient


@pytest.fixture
def mock_core_v1_api():
    """Mock do CoreV1Api"""
    return MagicMock(spec=client.CoreV1Api)


@pytest.fixture
def mock_apps_v1_api():
    """Mock do AppsV1Api"""
    return MagicMock(spec=client.AppsV1Api)


@pytest.fixture
def mock_networking_v1_api():
    """Mock do NetworkingV1Api"""
    return MagicMock(spec=client.NetworkingV1Api)


@pytest.fixture
def k8s_client(mock_core_v1_api, mock_apps_v1_api, mock_networking_v1_api):
    """Fixture do KubernetesClient com mocks"""
    k8s = KubernetesClient(in_cluster=False, namespace="test-namespace")
    k8s.core_v1 = mock_core_v1_api
    k8s.apps_v1 = mock_apps_v1_api
    k8s.networking_v1 = mock_networking_v1_api
    return k8s


class TestPodOperations:
    """Testes de operacoes com pods"""

    @pytest.mark.asyncio
    async def test_get_pod_success(self, k8s_client, mock_core_v1_api):
        """Testa obtencao bem-sucedida de pod"""
        mock_pod = MagicMock()
        mock_pod.to_dict.return_value = {
            "metadata": {"name": "test-pod"},
            "status": {"phase": "Running"}
        }
        mock_core_v1_api.read_namespaced_pod.return_value = mock_pod

        result = await k8s_client.get_pod("test-pod")

        assert result is not None
        assert result["metadata"]["name"] == "test-pod"
        mock_core_v1_api.read_namespaced_pod.assert_called_once_with(
            "test-pod", "test-namespace"
        )

    @pytest.mark.asyncio
    async def test_get_pod_not_found(self, k8s_client, mock_core_v1_api):
        """Testa obtencao de pod nao existente"""
        mock_core_v1_api.read_namespaced_pod.side_effect = ApiException(status=404)

        result = await k8s_client.get_pod("nonexistent-pod")

        assert result is None

    @pytest.mark.asyncio
    async def test_delete_pod_success(self, k8s_client, mock_core_v1_api):
        """Testa restart bem-sucedido de pod (delete)"""
        mock_core_v1_api.delete_namespaced_pod.return_value = MagicMock()

        result = await k8s_client.delete_pod("test-pod")

        assert result is True
        mock_core_v1_api.delete_namespaced_pod.assert_called_once_with(
            "test-pod", "test-namespace"
        )

    @pytest.mark.asyncio
    async def test_delete_pod_failure(self, k8s_client, mock_core_v1_api):
        """Testa falha ao deletar pod"""
        mock_core_v1_api.delete_namespaced_pod.side_effect = ApiException(status=500)

        result = await k8s_client.delete_pod("test-pod")

        assert result is False

    @pytest.mark.asyncio
    async def test_patch_pod_labels_success(self, k8s_client, mock_core_v1_api):
        """Testa patch de labels em pod"""
        mock_core_v1_api.patch_namespaced_pod.return_value = MagicMock()

        result = await k8s_client.patch_pod_labels(
            "test-pod",
            {"quarantine": "true", "incident-id": "INC-001"}
        )

        assert result is True
        mock_core_v1_api.patch_namespaced_pod.assert_called_once()


class TestDeploymentOperations:
    """Testes de operacoes com deployments"""

    @pytest.mark.asyncio
    async def test_scale_deployment_success(self, k8s_client, mock_apps_v1_api):
        """Testa scaling bem-sucedido de deployment"""
        mock_apps_v1_api.patch_namespaced_deployment_scale.return_value = MagicMock()

        result = await k8s_client.scale_deployment("test-deployment", 5)

        assert result is True
        mock_apps_v1_api.patch_namespaced_deployment_scale.assert_called_once()

    @pytest.mark.asyncio
    async def test_scale_deployment_invalid_replicas(self, k8s_client):
        """Testa validacao de replicas invalidas"""
        # Replicas negativas
        result = await k8s_client.scale_deployment("test-deployment", -1)
        assert result is False

        # Replicas acima do limite
        result = await k8s_client.scale_deployment("test-deployment", 100)
        assert result is False

    @pytest.mark.asyncio
    async def test_scale_deployment_failure(self, k8s_client, mock_apps_v1_api):
        """Testa falha ao escalar deployment"""
        mock_apps_v1_api.patch_namespaced_deployment_scale.side_effect = ApiException(status=500)

        result = await k8s_client.scale_deployment("test-deployment", 5)

        assert result is False

    @pytest.mark.asyncio
    async def test_rollback_deployment_success(self, k8s_client, mock_apps_v1_api):
        """Testa rollback bem-sucedido de deployment"""
        mock_deployment = MagicMock()
        mock_deployment.metadata.annotations = {
            "deployment.kubernetes.io/revision": "5"
        }
        mock_apps_v1_api.read_namespaced_deployment.return_value = mock_deployment
        mock_apps_v1_api.patch_namespaced_deployment.return_value = MagicMock()

        result = await k8s_client.rollback_deployment("test-deployment")

        assert result["success"] is True
        assert result["previous_revision"] == "5"
        mock_apps_v1_api.patch_namespaced_deployment.assert_called_once()

    @pytest.mark.asyncio
    async def test_rollback_deployment_to_specific_revision(self, k8s_client, mock_apps_v1_api):
        """Testa rollback para revisao especifica"""
        mock_deployment = MagicMock()
        mock_deployment.metadata.annotations = {
            "deployment.kubernetes.io/revision": "5"
        }
        mock_apps_v1_api.read_namespaced_deployment.return_value = mock_deployment
        mock_apps_v1_api.patch_namespaced_deployment.return_value = MagicMock()

        result = await k8s_client.rollback_deployment("test-deployment", revision=3)

        assert result["success"] is True
        assert result["target_revision"] == 3

    @pytest.mark.asyncio
    async def test_rollback_deployment_failure(self, k8s_client, mock_apps_v1_api):
        """Testa falha no rollback de deployment"""
        mock_apps_v1_api.read_namespaced_deployment.side_effect = ApiException(status=404)

        result = await k8s_client.rollback_deployment("nonexistent-deployment")

        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_get_deployment_revision_history(self, k8s_client, mock_apps_v1_api):
        """Testa listagem de historico de revisoes"""
        mock_rs_list = MagicMock()
        mock_rs1 = MagicMock()
        mock_rs1.metadata.name = "test-deployment-abc123"
        mock_rs1.metadata.annotations = {"deployment.kubernetes.io/revision": "3"}
        mock_rs1.spec.replicas = 3
        mock_rs1.status.available_replicas = 3
        mock_rs1.metadata.creation_timestamp = MagicMock()
        mock_rs1.metadata.creation_timestamp.isoformat.return_value = "2024-01-01T00:00:00Z"

        mock_rs2 = MagicMock()
        mock_rs2.metadata.name = "test-deployment-def456"
        mock_rs2.metadata.annotations = {"deployment.kubernetes.io/revision": "2"}
        mock_rs2.spec.replicas = 0
        mock_rs2.status.available_replicas = 0
        mock_rs2.metadata.creation_timestamp = MagicMock()
        mock_rs2.metadata.creation_timestamp.isoformat.return_value = "2023-12-01T00:00:00Z"

        mock_rs_list.items = [mock_rs1, mock_rs2]
        mock_apps_v1_api.list_namespaced_replica_set.return_value = mock_rs_list

        result = await k8s_client.get_deployment_revision_history("test-deployment")

        assert len(result) == 2
        assert result[0]["revision"] == 3
        assert result[1]["revision"] == 2


class TestNetworkPolicyOperations:
    """Testes de operacoes com NetworkPolicies"""

    @pytest.mark.asyncio
    async def test_apply_network_policy_create(self, k8s_client, mock_networking_v1_api):
        """Testa criacao de NetworkPolicy"""
        mock_networking_v1_api.create_namespaced_network_policy.return_value = MagicMock()

        policy_spec = {
            "target": "isolate",
            "pod_selector": {"app": "suspicious-app"}
        }

        result = await k8s_client.apply_network_policy("quarantine-policy", policy_spec)

        assert result["success"] is True
        assert result["action"] == "created"
        mock_networking_v1_api.create_namespaced_network_policy.assert_called_once()

    @pytest.mark.asyncio
    async def test_apply_network_policy_update(self, k8s_client, mock_networking_v1_api):
        """Testa atualizacao de NetworkPolicy existente"""
        # Primeira chamada lanca 409 Conflict
        mock_networking_v1_api.create_namespaced_network_policy.side_effect = ApiException(status=409)
        mock_networking_v1_api.patch_namespaced_network_policy.return_value = MagicMock()

        policy_spec = {
            "target": "rate_limit",
            "pod_selector": {"app": "api"}
        }

        result = await k8s_client.apply_network_policy("rate-limit-policy", policy_spec)

        assert result["success"] is True
        assert result["action"] == "updated"
        mock_networking_v1_api.patch_namespaced_network_policy.assert_called_once()

    @pytest.mark.asyncio
    async def test_apply_network_policy_isolate(self, k8s_client, mock_networking_v1_api):
        """Testa criacao de policy de isolamento"""
        mock_networking_v1_api.create_namespaced_network_policy.return_value = MagicMock()

        policy_spec = {
            "target": "isolate",
            "pod_selector": {"app": "compromised"}
        }

        result = await k8s_client.apply_network_policy("isolate-policy", policy_spec)

        assert result["success"] is True
        # Verificar que a policy foi criada com ingress/egress vazios
        call_args = mock_networking_v1_api.create_namespaced_network_policy.call_args
        network_policy = call_args[0][1]
        assert network_policy.spec.ingress == []
        assert network_policy.spec.egress == []

    @pytest.mark.asyncio
    async def test_apply_network_policy_restore(self, k8s_client, mock_networking_v1_api):
        """Testa criacao de policy permissiva (restore)"""
        mock_networking_v1_api.create_namespaced_network_policy.return_value = MagicMock()

        policy_spec = {
            "target": "restore",
            "pod_selector": {"app": "healthy"}
        }

        result = await k8s_client.apply_network_policy("restore-policy", policy_spec)

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_apply_network_policy_failure(self, k8s_client, mock_networking_v1_api):
        """Testa falha ao aplicar NetworkPolicy"""
        mock_networking_v1_api.create_namespaced_network_policy.side_effect = ApiException(status=500)

        policy_spec = {"target": "isolate", "pod_selector": {}}

        result = await k8s_client.apply_network_policy("failing-policy", policy_spec)

        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_delete_network_policy_success(self, k8s_client, mock_networking_v1_api):
        """Testa remocao de NetworkPolicy"""
        mock_networking_v1_api.delete_namespaced_network_policy.return_value = MagicMock()

        result = await k8s_client.delete_network_policy("test-policy")

        assert result is True
        mock_networking_v1_api.delete_namespaced_network_policy.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_network_policy_not_found(self, k8s_client, mock_networking_v1_api):
        """Testa remocao de policy nao existente (deve ser sucesso)"""
        mock_networking_v1_api.delete_namespaced_network_policy.side_effect = ApiException(status=404)

        result = await k8s_client.delete_network_policy("nonexistent-policy")

        assert result is True

    @pytest.mark.asyncio
    async def test_delete_network_policy_failure(self, k8s_client, mock_networking_v1_api):
        """Testa falha ao remover NetworkPolicy"""
        mock_networking_v1_api.delete_namespaced_network_policy.side_effect = ApiException(status=500)

        result = await k8s_client.delete_network_policy("test-policy")

        assert result is False


class TestHealthCheck:
    """Testes de health check do cliente"""

    def test_is_healthy_true(self, k8s_client):
        """Testa que cliente esta saudavel quando APIs estao inicializadas"""
        assert k8s_client.is_healthy() is True

    def test_is_healthy_false_no_core(self):
        """Testa que cliente nao esta saudavel sem CoreV1Api"""
        k8s = KubernetesClient(in_cluster=False, namespace="test")
        k8s.core_v1 = None
        k8s.apps_v1 = MagicMock()

        assert k8s.is_healthy() is False

    def test_is_healthy_false_no_apps(self):
        """Testa que cliente nao esta saudavel sem AppsV1Api"""
        k8s = KubernetesClient(in_cluster=False, namespace="test")
        k8s.core_v1 = MagicMock()
        k8s.apps_v1 = None

        assert k8s.is_healthy() is False


class TestNamespaceHandling:
    """Testes de manipulacao de namespace"""

    @pytest.mark.asyncio
    async def test_operations_use_custom_namespace(self, k8s_client, mock_core_v1_api):
        """Testa que operacoes podem usar namespace customizado"""
        mock_core_v1_api.delete_namespaced_pod.return_value = MagicMock()

        await k8s_client.delete_pod("test-pod", namespace="custom-namespace")

        mock_core_v1_api.delete_namespaced_pod.assert_called_once_with(
            "test-pod", "custom-namespace"
        )

    @pytest.mark.asyncio
    async def test_operations_use_default_namespace(self, k8s_client, mock_core_v1_api):
        """Testa que operacoes usam namespace padrao quando nao especificado"""
        mock_core_v1_api.delete_namespaced_pod.return_value = MagicMock()

        await k8s_client.delete_pod("test-pod")

        mock_core_v1_api.delete_namespaced_pod.assert_called_once_with(
            "test-pod", "test-namespace"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
