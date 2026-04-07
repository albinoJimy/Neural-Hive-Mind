"""Testes para o playbook de detecção de memory leak - TDD Approach."""

import pytest
import yaml
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


class TestMemoryLeakDetectionPlaybook:
    """Testes para verificar a existência e schema do playbook memory_leak_detection.yaml."""

    def test_memory_leak_detection_playbook_exists(self):
        """Verifica que o ficheiro do playbook existe."""
        playbook_path = (
            Path(__file__).parent.parent.parent.parent / "playbooks" / "memory_leak_detection.yaml"
        )
        assert playbook_path.exists(), "Playbook file does not exist"

    def test_memory_leak_detection_playbook_valid_schema(self):
        """Verifica que o playbook tem o schema válido."""
        playbook_path = (
            Path(__file__).parent.parent.parent.parent / "playbooks" / "memory_leak_detection.yaml"
        )
        with open(playbook_path) as f:
            playbook = yaml.safe_load(f)

        assert playbook["playbook_id"] == "memory-leak-detection-v1"
        assert "actions" in playbook
        assert len(playbook["actions"]) >= 2

        # Verificar que as ações esperadas existem
        action_names = [action["name"] for action in playbook["actions"]]
        assert "get_pod_metrics" in action_names
        assert "analyze_memory_usage" in action_names

    def test_memory_leak_detection_playbook_trigger(self):
        """Verifica que o playbook tem o trigger correto."""
        playbook_path = (
            Path(__file__).parent.parent.parent.parent / "playbooks" / "memory_leak_detection.yaml"
        )
        with open(playbook_path) as f:
            playbook = yaml.safe_load(f)

        assert "trigger" in playbook
        assert playbook["trigger"]["pattern"] == "memory_leak_detected"
        assert playbook["trigger"]["severity"] == "warning"


class TestPodMetricsAction:
    """Testes para a ação get_pod_metrics no PlaybookExecutor."""

    @pytest.fixture
    def mock_clients(self):
        """Mock clients para Kubernetes."""
        return {
            "core_v1": MagicMock(),
            "custom_api": MagicMock(),
        }

    @pytest.fixture
    def executor(self, mock_clients):
        """Cria executor com mocks."""
        from src.services.playbook_executor import PlaybookExecutor

        executor = PlaybookExecutor(
            playbooks_dir="/tmp/playbooks",
            k8s_in_cluster=False,
            opa_enabled=False,
        )
        executor.core_v1 = mock_clients["core_v1"]
        return executor

    @pytest.mark.asyncio
    async def test_get_pod_metrics_success(self, executor):
        """Testa sucesso ao obter métricas do pod."""
        # Arrange
        from kubernetes.client.rest import ApiException

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.data = """
        {
            "containers": [
                {
                    "name": "app",
                    "usage": {"memory": "128Mi", "cpu": "100m"}
                },
                {
                    "name": "sidecar",
                    "usage": {"memory": "64Mi", "cpu": "50m"}
                }
            ]
        }
        """

        with patch.object(executor.core_v1.api_client, "call_api", return_value=mock_response):
            # Act
            result = await executor._get_pod_metrics(
                {"pod_name": "test-pod", "namespace": "default"}, {}
            )

            # Assert
            assert result["success"] is True
            assert "containers" in result
            assert len(result["containers"]) == 2
            assert result["containers"][0]["name"] == "app"
            assert result["containers"][0]["usage"]["memory"] == "128Mi"

    @pytest.mark.asyncio
    async def test_get_pod_metrics_pod_not_found(self, executor):
        """Testa erro quando pod não existe."""
        # Arrange
        from kubernetes.client.rest import ApiException

        mock_error = ApiException(status=404, reason="Pod not found")

        with patch.object(executor.core_v1.api_client, "call_api", side_effect=mock_error):
            # Act
            result = await executor._get_pod_metrics(
                {"pod_name": "nonexistent-pod", "namespace": "default"}, {}
            )

            # Assert
            assert result["success"] is False
            assert "error" in result
            assert "404" in result["error"]

    @pytest.mark.asyncio
    async def test_get_pod_metrics_memory_threshold_check(self, executor):
        """Testa detecção de memory leak baseado em threshold."""
        # Arrange
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.data = """
        {
            "containers": [
                {
                    "name": "app",
                    "usage": {"memory": "512Mi"}
                }
            ]
        }
        """

        with patch.object(executor.core_v1.api_client, "call_api", return_value=mock_response):
            # Act
            result = await executor._get_pod_metrics(
                {"pod_name": "test-pod", "namespace": "default", "memory_threshold_mb": 256}, {}
            )

            # Assert
            assert result["success"] is True
            assert result["memory_threshold_exceeded"] is True
            assert result["memory_mb"] == 512


class TestAnalyzeMemoryUsageAction:
    """Testes para a ação analyze_memory_usage no PlaybookExecutor."""

    @pytest.fixture
    def executor(self):
        """Cria executor."""
        from src.services.playbook_executor import PlaybookExecutor

        return PlaybookExecutor(
            playbooks_dir="/tmp/playbooks",
            k8s_in_cluster=False,
            opa_enabled=False,
        )

    @pytest.mark.asyncio
    async def test_analyze_memory_usage_increasing_trend(self, executor):
        """Testa detecção de tendência crescente de uso de memória."""
        # Arrange
        metrics_history = [
            {"timestamp": "T-10m", "memory_mb": 100},
            {"timestamp": "T-8m", "memory_mb": 150},
            {"timestamp": "T-6m", "memory_mb": 200},
            {"timestamp": "T-4m", "memory_mb": 300},
            {"timestamp": "T-2m", "memory_mb": 450},
        ]

        # Act
        result = await executor._analyze_memory_usage(
            {"pod_name": "test-pod", "metrics_history": metrics_history}, {}
        )

        # Assert
        assert result["success"] is True
        assert result["memory_leak_detected"] is True
        assert result["trend"] == "increasing"

    @pytest.mark.asyncio
    async def test_analyze_memory_usage_stable(self, executor):
        """Testa detecção de uso de memória estável."""
        # Arrange
        metrics_history = [
            {"timestamp": "T-10m", "memory_mb": 100},
            {"timestamp": "T-8m", "memory_mb": 105},
            {"timestamp": "T-6m", "memory_mb": 98},
            {"timestamp": "T-4m", "memory_mb": 102},
            {"timestamp": "T-2m", "memory_mb": 100},
        ]

        # Act
        result = await executor._analyze_memory_usage(
            {"pod_name": "test-pod", "metrics_history": metrics_history}, {}
        )

        # Assert
        assert result["success"] is True
        assert result["memory_leak_detected"] is False
        assert result["trend"] == "stable"
