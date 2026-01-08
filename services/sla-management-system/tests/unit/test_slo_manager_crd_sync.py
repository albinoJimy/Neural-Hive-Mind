"""Testes unitarios para sincronizacao de CRDs no SLOManager."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from kubernetes.client.rest import ApiException

from src.services.slo_manager import SLOManager
from src.models.slo_definition import SLODefinition, SLOType, SLIQuery


@pytest.fixture
def mock_crd_spec():
    """Fixture com spec de CRD valido."""
    return {
        "name": "test-slo",
        "sloType": "LATENCY",
        "serviceName": "test-service",
        "layer": "orquestracao",
        "target": 0.999,
        "windowDays": 30,
        "description": "Test SLO description",
        "sliQuery": {
            "metricName": "http_request_duration_seconds",
            "query": "histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))",
            "aggregation": "avg",
            "labels": {}
        },
        "enabled": True
    }


@pytest.fixture
def mock_crd(mock_crd_spec):
    """Fixture com CRD completo."""
    return {
        "apiVersion": "neural-hive.io/v1",
        "kind": "SLODefinition",
        "metadata": {
            "name": "gateway-latency-p99",
            "namespace": "neural-hive",
            "uid": "12345"
        },
        "spec": mock_crd_spec
    }


@pytest.fixture
def mock_postgresql_client():
    """Fixture com mock do PostgreSQL client."""
    client = MagicMock()
    client.create_slo = AsyncMock(return_value="slo-uuid-123")
    client.get_slo = AsyncMock(return_value=None)
    client.list_slos = AsyncMock(return_value=[])
    client.update_slo = AsyncMock(return_value=True)
    return client


@pytest.fixture
def mock_prometheus_client():
    """Fixture com mock do Prometheus client."""
    client = MagicMock()
    client.query = AsyncMock(return_value={"resultType": "vector", "result": []})
    return client


@pytest.fixture
def mock_kubernetes_client():
    """Fixture com mock do Kubernetes client."""
    client = MagicMock()
    client.is_healthy = MagicMock(return_value=True)
    client.list_slo_definitions = AsyncMock(return_value=[])
    client.get_slo_definition = AsyncMock(return_value=None)
    client.update_slo_status = AsyncMock(return_value=True)
    return client


class TestSyncFromCrdsCreateNewSlos:
    """Testes para criacao de novos SLOs."""

    @pytest.mark.asyncio
    async def test_sync_from_crds_creates_new_slos(
        self,
        mock_postgresql_client,
        mock_prometheus_client,
        mock_kubernetes_client,
        mock_crd
    ):
        """Verifica que sync_from_crds cria novos SLOs quando nao existem."""
        # Configurar mock para retornar 2 CRDs
        crd2 = mock_crd.copy()
        crd2["metadata"] = {"name": "error-rate-slo", "namespace": "neural-hive"}
        crd2["spec"] = mock_crd["spec"].copy()
        crd2["spec"]["name"] = "Error Rate SLO"
        crd2["spec"]["sloType"] = "ERROR_RATE"

        mock_kubernetes_client.list_slo_definitions.return_value = [mock_crd, crd2]

        # PostgreSQL retorna lista vazia (nenhum SLO existente)
        mock_postgresql_client.list_slos.return_value = []

        # Criar SLOManager
        manager = SLOManager(
            postgresql_client=mock_postgresql_client,
            prometheus_client=mock_prometheus_client,
            kubernetes_client=mock_kubernetes_client
        )

        # Executar sincronizacao
        synced_ids = await manager.sync_from_crds()

        # Verificar que create_slo foi chamado 2 vezes
        assert mock_postgresql_client.create_slo.call_count == 2
        assert len(synced_ids) == 2

        # Verificar que update_slo_status foi chamado 2 vezes
        assert mock_kubernetes_client.update_slo_status.call_count == 2


class TestSyncFromCrdsUpdateExisting:
    """Testes para atualizacao de SLOs existentes."""

    @pytest.mark.asyncio
    async def test_sync_from_crds_updates_existing_slos(
        self,
        mock_postgresql_client,
        mock_prometheus_client,
        mock_kubernetes_client,
        mock_crd
    ):
        """Verifica que sync_from_crds atualiza SLOs com valores diferentes."""
        # CRD com target=0.999
        mock_kubernetes_client.list_slo_definitions.return_value = [mock_crd]

        # SLO existente com target=0.99 (diferente)
        existing_slo = SLODefinition(
            slo_id="existing-slo-id",
            name="test-slo",
            slo_type=SLOType.LATENCY,
            service_name="test-service",
            layer="orquestracao",
            target=0.99,  # Diferente do CRD
            window_days=30,
            sli_query=SLIQuery(
                metric_name="http_request_duration_seconds",
                query="histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))",
                aggregation="avg"
            ),
            metadata={
                "crd_name": "gateway-latency-p99",
                "crd_namespace": "neural-hive"
            }
        )
        mock_postgresql_client.list_slos.return_value = [existing_slo]

        manager = SLOManager(
            postgresql_client=mock_postgresql_client,
            prometheus_client=mock_prometheus_client,
            kubernetes_client=mock_kubernetes_client
        )

        synced_ids = await manager.sync_from_crds()

        # Verificar que update_slo foi chamado (nao create_slo)
        mock_postgresql_client.update_slo.assert_called_once()
        mock_postgresql_client.create_slo.assert_not_called()
        assert synced_ids == ["existing-slo-id"]


class TestSyncFromCrdsSkipUnchanged:
    """Testes para skip de SLOs sem mudancas."""

    @pytest.mark.asyncio
    async def test_sync_from_crds_skips_unchanged_slos(
        self,
        mock_postgresql_client,
        mock_prometheus_client,
        mock_kubernetes_client,
        mock_crd
    ):
        """Verifica que sync_from_crds nao atualiza SLOs identicos."""
        mock_kubernetes_client.list_slo_definitions.return_value = [mock_crd]

        # SLO existente com valores identicos ao CRD
        existing_slo = SLODefinition(
            slo_id="existing-slo-id",
            name="test-slo",
            description="Test SLO description",
            slo_type=SLOType.LATENCY,
            service_name="test-service",
            layer="orquestracao",
            target=0.999,  # Igual ao CRD
            window_days=30,
            sli_query=SLIQuery(
                metric_name="http_request_duration_seconds",
                query="histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))",
                aggregation="avg"
            ),
            enabled=True,
            metadata={
                "crd_name": "gateway-latency-p99",
                "crd_namespace": "neural-hive"
            }
        )
        mock_postgresql_client.list_slos.return_value = [existing_slo]

        manager = SLOManager(
            postgresql_client=mock_postgresql_client,
            prometheus_client=mock_prometheus_client,
            kubernetes_client=mock_kubernetes_client
        )

        synced_ids = await manager.sync_from_crds()

        # Verificar que update_slo NAO foi chamado
        mock_postgresql_client.update_slo.assert_not_called()
        mock_postgresql_client.create_slo.assert_not_called()
        assert synced_ids == ["existing-slo-id"]


class TestSyncFromCrdsErrorHandling:
    """Testes para tratamento de erros."""

    @pytest.mark.asyncio
    async def test_sync_from_crds_handles_kubernetes_errors(
        self,
        mock_postgresql_client,
        mock_prometheus_client,
        mock_kubernetes_client
    ):
        """Verifica que sync_from_crds trata erros do Kubernetes."""
        # Simular erro na listagem
        mock_kubernetes_client.list_slo_definitions.side_effect = Exception("API Error")

        manager = SLOManager(
            postgresql_client=mock_postgresql_client,
            prometheus_client=mock_prometheus_client,
            kubernetes_client=mock_kubernetes_client
        )

        synced_ids = await manager.sync_from_crds()

        # Deve retornar lista vazia e nao lancar excecao
        assert synced_ids == []

    @pytest.mark.asyncio
    async def test_sync_from_crds_without_kubernetes_client(
        self,
        mock_postgresql_client,
        mock_prometheus_client
    ):
        """Verifica que sync_from_crds retorna vazio sem kubernetes_client."""
        manager = SLOManager(
            postgresql_client=mock_postgresql_client,
            prometheus_client=mock_prometheus_client,
            kubernetes_client=None
        )

        synced_ids = await manager.sync_from_crds()

        # Deve retornar lista vazia
        assert synced_ids == []

    @pytest.mark.asyncio
    async def test_sync_from_crds_with_unhealthy_client(
        self,
        mock_postgresql_client,
        mock_prometheus_client,
        mock_kubernetes_client
    ):
        """Verifica que sync_from_crds retorna vazio com cliente nao saudavel."""
        mock_kubernetes_client.is_healthy.return_value = False

        manager = SLOManager(
            postgresql_client=mock_postgresql_client,
            prometheus_client=mock_prometheus_client,
            kubernetes_client=mock_kubernetes_client
        )

        synced_ids = await manager.sync_from_crds()

        # Deve retornar lista vazia
        assert synced_ids == []
        mock_kubernetes_client.list_slo_definitions.assert_not_called()


class TestSloNeedsUpdate:
    """Testes para _slo_needs_update."""

    def test_slo_needs_update_different_target(
        self,
        mock_postgresql_client,
        mock_prometheus_client
    ):
        """Verifica deteccao de mudanca no target."""
        manager = SLOManager(
            postgresql_client=mock_postgresql_client,
            prometheus_client=mock_prometheus_client
        )

        existing = SLODefinition(
            name="test",
            slo_type=SLOType.LATENCY,
            service_name="svc",
            layer="layer",
            target=0.99,
            sli_query=SLIQuery(metric_name="m", query="q", aggregation="avg")
        )

        new_data = SLODefinition(
            name="test",
            slo_type=SLOType.LATENCY,
            service_name="svc",
            layer="layer",
            target=0.999,  # Diferente
            sli_query=SLIQuery(metric_name="m", query="q", aggregation="avg")
        )

        assert manager._slo_needs_update(existing, new_data) is True

    def test_slo_needs_update_same_values(
        self,
        mock_postgresql_client,
        mock_prometheus_client
    ):
        """Verifica que valores identicos nao precisam de update."""
        manager = SLOManager(
            postgresql_client=mock_postgresql_client,
            prometheus_client=mock_prometheus_client
        )

        existing = SLODefinition(
            name="test",
            slo_type=SLOType.LATENCY,
            service_name="svc",
            layer="layer",
            target=0.999,
            sli_query=SLIQuery(metric_name="m", query="q", aggregation="avg")
        )

        new_data = SLODefinition(
            name="test",
            slo_type=SLOType.LATENCY,
            service_name="svc",
            layer="layer",
            target=0.999,
            sli_query=SLIQuery(metric_name="m", query="q", aggregation="avg")
        )

        assert manager._slo_needs_update(existing, new_data) is False
