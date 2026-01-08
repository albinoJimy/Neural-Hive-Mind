"""Testes de integracao para o Kubernetes Client."""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from kubernetes.client.rest import ApiException

from src.clients.kubernetes_client import (
    KubernetesClient,
    CRD_GROUP,
    CRD_VERSION,
    CRD_PLURAL
)


@pytest.fixture
def mock_custom_objects_api():
    """Fixture com mock do CustomObjectsApi."""
    return MagicMock()


@pytest.fixture
def sample_crd():
    """Fixture com CRD de exemplo."""
    return {
        "apiVersion": f"{CRD_GROUP}/{CRD_VERSION}",
        "kind": "SLODefinition",
        "metadata": {
            "name": "gateway-latency-p99",
            "namespace": "neural-hive",
            "uid": "test-uid-123"
        },
        "spec": {
            "name": "Gateway P99 Latency",
            "description": "99th percentile latency for gateway",
            "sloType": "LATENCY",
            "serviceName": "gateway-intencoes",
            "layer": "experiencia",
            "target": 0.999,
            "windowDays": 30,
            "sliQuery": {
                "metricName": "http_request_duration_seconds",
                "query": "histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))",
                "aggregation": "avg"
            },
            "enabled": True
        },
        "status": {
            "synced": False
        }
    }


@pytest.mark.integration
@pytest.mark.k8s
class TestKubernetesClientListSloDefinitions:
    """Testes de integracao para listagem de SLODefinitions."""

    @pytest.mark.asyncio
    async def test_list_slo_definitions_returns_crds(
        self,
        mock_custom_objects_api,
        sample_crd
    ):
        """Verifica que list_slo_definitions retorna CRDs do cluster."""
        # Configurar mock
        mock_custom_objects_api.list_cluster_custom_object.return_value = {
            "items": [sample_crd]
        }

        with patch("src.clients.kubernetes_client.config"):
            with patch(
                "src.clients.kubernetes_client.client.CustomObjectsApi",
                return_value=mock_custom_objects_api
            ):
                k8s_client = KubernetesClient(in_cluster=False)
                await k8s_client.connect()

                # Executar listagem
                crds = await k8s_client.list_slo_definitions()

                # Verificar resultado
                assert len(crds) == 1
                assert crds[0]["metadata"]["name"] == "gateway-latency-p99"
                assert crds[0]["spec"]["target"] == 0.999

                # Verificar chamada correta
                mock_custom_objects_api.list_cluster_custom_object.assert_called_once_with(
                    group=CRD_GROUP,
                    version=CRD_VERSION,
                    plural=CRD_PLURAL
                )

    @pytest.mark.asyncio
    async def test_list_slo_definitions_with_namespace(
        self,
        mock_custom_objects_api,
        sample_crd
    ):
        """Verifica listagem filtrada por namespace."""
        mock_custom_objects_api.list_namespaced_custom_object.return_value = {
            "items": [sample_crd]
        }

        with patch("src.clients.kubernetes_client.config"):
            with patch(
                "src.clients.kubernetes_client.client.CustomObjectsApi",
                return_value=mock_custom_objects_api
            ):
                k8s_client = KubernetesClient(in_cluster=False)
                await k8s_client.connect()

                crds = await k8s_client.list_slo_definitions(namespace="neural-hive")

                assert len(crds) == 1
                mock_custom_objects_api.list_namespaced_custom_object.assert_called_once_with(
                    group=CRD_GROUP,
                    version=CRD_VERSION,
                    namespace="neural-hive",
                    plural=CRD_PLURAL
                )

    @pytest.mark.asyncio
    async def test_list_slo_definitions_handles_api_error(
        self,
        mock_custom_objects_api
    ):
        """Verifica tratamento de erro da API."""
        mock_custom_objects_api.list_cluster_custom_object.side_effect = ApiException(
            status=500,
            reason="Internal Server Error"
        )

        with patch("src.clients.kubernetes_client.config"):
            with patch(
                "src.clients.kubernetes_client.client.CustomObjectsApi",
                return_value=mock_custom_objects_api
            ):
                k8s_client = KubernetesClient(in_cluster=False)
                await k8s_client.connect()

                crds = await k8s_client.list_slo_definitions()

                # Deve retornar lista vazia em caso de erro
                assert crds == []


@pytest.mark.integration
@pytest.mark.k8s
class TestKubernetesClientUpdateSloStatus:
    """Testes de integracao para atualizacao de status."""

    @pytest.mark.asyncio
    async def test_update_slo_status_success(
        self,
        mock_custom_objects_api,
        sample_crd
    ):
        """Verifica atualizacao de status do CRD."""
        # get_namespaced_custom_object retorna CRD atual
        mock_custom_objects_api.get_namespaced_custom_object.return_value = sample_crd

        # patch_namespaced_custom_object_status retorna CRD atualizado
        updated_crd = sample_crd.copy()
        updated_crd["status"] = {"synced": True, "sloId": "uuid-123"}
        mock_custom_objects_api.patch_namespaced_custom_object_status.return_value = updated_crd

        with patch("src.clients.kubernetes_client.config"):
            with patch(
                "src.clients.kubernetes_client.client.CustomObjectsApi",
                return_value=mock_custom_objects_api
            ):
                k8s_client = KubernetesClient(in_cluster=False)
                await k8s_client.connect()

                result = await k8s_client.update_slo_status(
                    name="gateway-latency-p99",
                    namespace="neural-hive",
                    status={"synced": True, "sloId": "uuid-123"}
                )

                assert result is True
                mock_custom_objects_api.patch_namespaced_custom_object_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_slo_status_not_found(
        self,
        mock_custom_objects_api
    ):
        """Verifica tratamento quando CRD nao existe."""
        mock_custom_objects_api.get_namespaced_custom_object.side_effect = ApiException(
            status=404,
            reason="Not Found"
        )

        with patch("src.clients.kubernetes_client.config"):
            with patch(
                "src.clients.kubernetes_client.client.CustomObjectsApi",
                return_value=mock_custom_objects_api
            ):
                k8s_client = KubernetesClient(in_cluster=False)
                await k8s_client.connect()

                result = await k8s_client.update_slo_status(
                    name="non-existent",
                    namespace="neural-hive",
                    status={"synced": True}
                )

                assert result is False


@pytest.mark.integration
@pytest.mark.k8s
class TestKubernetesClientConnection:
    """Testes de integracao para conexao."""

    @pytest.mark.asyncio
    async def test_connect_out_of_cluster(self, mock_custom_objects_api):
        """Verifica conexao fora do cluster."""
        with patch("src.clients.kubernetes_client.config") as mock_config:
            with patch(
                "src.clients.kubernetes_client.client.CustomObjectsApi",
                return_value=mock_custom_objects_api
            ):
                k8s_client = KubernetesClient(in_cluster=False)
                await k8s_client.connect()

                mock_config.load_kube_config.assert_called_once()
                assert k8s_client.is_healthy() is True

    @pytest.mark.asyncio
    async def test_connect_in_cluster(self, mock_custom_objects_api):
        """Verifica conexao dentro do cluster."""
        with patch("src.clients.kubernetes_client.config") as mock_config:
            with patch(
                "src.clients.kubernetes_client.client.CustomObjectsApi",
                return_value=mock_custom_objects_api
            ):
                k8s_client = KubernetesClient(in_cluster=True)
                await k8s_client.connect()

                mock_config.load_incluster_config.assert_called_once()
                assert k8s_client.is_healthy() is True

    @pytest.mark.asyncio
    async def test_is_healthy_before_connect(self):
        """Verifica que is_healthy retorna False antes de conectar."""
        k8s_client = KubernetesClient(in_cluster=False)
        assert k8s_client.is_healthy() is False
