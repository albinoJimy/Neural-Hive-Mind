"""Unit tests for RemediationCoordinator"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.services.remediation_coordinator import RemediationCoordinator, RemediationType


@pytest.fixture
def mock_k8s_client():
    """Mock Kubernetes client"""
    client = MagicMock()
    client.namespace = "neural-hive"
    client.delete_pod = AsyncMock(return_value=True)
    client.get_pod = AsyncMock(return_value=None)  # Pod deleted
    client.list_pods = AsyncMock(return_value=[{
        "metadata": {"name": "test-pod-abc123"},
        "status": {"phase": "Running", "containerStatuses": [{"ready": True}]}
    }])
    client.scale_deployment = AsyncMock(return_value=True)
    client.rollback_deployment = AsyncMock(return_value={"success": True})
    client.apply_network_policy = AsyncMock(return_value={"success": True})
    return client


@pytest.fixture
def mock_redis_client():
    """Mock Redis client"""
    client = MagicMock()
    client.client = MagicMock()
    client.client.flushdb = AsyncMock()
    client.client.scan = AsyncMock(return_value=(0, ["key1", "key2"]))
    client.client.delete = AsyncMock()
    return client


@pytest.fixture
def mock_chaosmesh_client():
    """Mock ChaosMesh client"""
    client = MagicMock()
    client.is_healthy = MagicMock(return_value=True)
    client.create_pod_chaos = AsyncMock(return_value={
        "success": True,
        "experiment_name": "test-chaos",
        "experiment_type": "PodChaos"
    })
    client.create_network_chaos = AsyncMock(return_value={
        "success": True,
        "experiment_name": "test-chaos",
        "experiment_type": "NetworkChaos"
    })
    return client


@pytest.fixture
def mock_script_executor():
    """Mock Script executor"""
    executor = MagicMock()
    executor.is_healthy = MagicMock(return_value=True)
    executor.execute_script = AsyncMock(return_value={
        "success": True,
        "job_name": "guard-script-test",
        "exit_code": 0,
        "duration_seconds": 2.5,
        "logs": "Script executed successfully"
    })
    return executor


@pytest.fixture
def remediation_coordinator(mock_k8s_client, mock_redis_client):
    """RemediationCoordinator with mocked dependencies"""
    coordinator = RemediationCoordinator(
        k8s_client=mock_k8s_client,
        use_self_healing_engine=False
    )
    coordinator.redis_client = mock_redis_client
    return coordinator


class TestClearCache:
    """Tests for _clear_cache method"""

    @pytest.mark.asyncio
    async def test_clear_cache_redis_flush(self, remediation_coordinator, mock_redis_client):
        """Test clearing entire Redis cache"""
        action = {"cache": "redis"}
        incident = {"incident_id": "INC-001"}

        result = await remediation_coordinator._clear_cache(action, incident)

        assert result["success"] is True
        assert result["action_type"] == RemediationType.CLEAR_CACHE
        assert result["details"]["action"] == "flushdb"
        mock_redis_client.client.flushdb.assert_called_once()

    @pytest.mark.asyncio
    async def test_clear_cache_redis_pattern(self, remediation_coordinator, mock_redis_client):
        """Test clearing Redis cache by pattern"""
        action = {"cache": "redis", "pattern": "session:*"}
        incident = {"incident_id": "INC-001"}

        result = await remediation_coordinator._clear_cache(action, incident)

        assert result["success"] is True
        assert result["details"]["pattern"] == "session:*"
        assert result["details"]["keys_deleted"] == 2

    @pytest.mark.asyncio
    async def test_clear_cache_redis_not_available(self, remediation_coordinator):
        """Test cache clearing when Redis is not available"""
        remediation_coordinator.redis_client = None
        action = {"cache": "redis"}
        incident = {"incident_id": "INC-001"}

        result = await remediation_coordinator._clear_cache(action, incident)

        assert result["success"] is True  # Graceful degradation
        assert "warning" in result["details"]

    @pytest.mark.asyncio
    async def test_clear_cache_memcached(self, remediation_coordinator):
        """Test Memcached clearing (not implemented)"""
        action = {"cache": "memcached"}
        incident = {"incident_id": "INC-001"}

        result = await remediation_coordinator._clear_cache(action, incident)

        assert result["success"] is True
        assert "warning" in result["details"]
        assert "not implemented" in result["details"]["warning"].lower()


class TestTriggerChaos:
    """Tests for _trigger_chaos method"""

    @pytest.mark.asyncio
    async def test_trigger_chaos_pod_failure(self, remediation_coordinator, mock_chaosmesh_client):
        """Test triggering pod failure chaos"""
        remediation_coordinator.chaosmesh_client = mock_chaosmesh_client
        action = {"chaos_type": "pod_failure", "duration": "30s"}
        incident = {"incident_id": "INC-001"}

        result = await remediation_coordinator._trigger_chaos(action, incident)

        assert result["success"] is True
        assert result["action_type"] == RemediationType.TRIGGER_CHAOS
        assert result["details"]["experiment_created"] is True
        mock_chaosmesh_client.create_pod_chaos.assert_called_once()

    @pytest.mark.asyncio
    async def test_trigger_chaos_network_delay(self, remediation_coordinator, mock_chaosmesh_client):
        """Test triggering network delay chaos"""
        remediation_coordinator.chaosmesh_client = mock_chaosmesh_client
        action = {"chaos_type": "network_delay", "latency": "100ms"}
        incident = {"incident_id": "INC-001"}

        result = await remediation_coordinator._trigger_chaos(action, incident)

        assert result["success"] is True
        assert result["details"]["latency"] == "100ms"
        mock_chaosmesh_client.create_network_chaos.assert_called_once()

    @pytest.mark.asyncio
    async def test_trigger_chaos_not_available(self, remediation_coordinator):
        """Test chaos triggering when ChaosMesh is not available"""
        action = {"chaos_type": "pod_kill"}
        incident = {"incident_id": "INC-001"}

        result = await remediation_coordinator._trigger_chaos(action, incident)

        assert result["success"] is True  # Graceful degradation
        assert result["details"]["simulated"] is True


class TestExecScript:
    """Tests for _exec_script method"""

    @pytest.mark.asyncio
    async def test_exec_script_predefined(self, remediation_coordinator, mock_script_executor):
        """Test executing predefined script"""
        remediation_coordinator.script_executor = mock_script_executor
        action = {"script": "revoke_tokens.sh"}
        incident = {"incident_id": "INC-001"}

        result = await remediation_coordinator._exec_script(action, incident)

        assert result["success"] is True
        assert result["action_type"] == RemediationType.EXEC_SCRIPT
        assert result["details"]["job_name"] is not None
        mock_script_executor.execute_script.assert_called_once()

    @pytest.mark.asyncio
    async def test_exec_script_inline(self, remediation_coordinator, mock_script_executor):
        """Test executing inline script content"""
        remediation_coordinator.script_executor = mock_script_executor
        action = {
            "script": "custom-script",
            "script_content": "#!/bin/sh\necho 'Hello World'"
        }
        incident = {"incident_id": "INC-001"}

        result = await remediation_coordinator._exec_script(action, incident)

        assert result["success"] is True
        mock_script_executor.execute_script.assert_called_once()

    @pytest.mark.asyncio
    async def test_exec_script_not_available(self, remediation_coordinator):
        """Test script execution when executor is not available"""
        action = {"script": "test.sh"}
        incident = {"incident_id": "INC-001"}

        result = await remediation_coordinator._exec_script(action, incident)

        assert result["success"] is True  # Graceful degradation
        assert result["details"]["simulated"] is True

    @pytest.mark.asyncio
    async def test_exec_script_no_script_specified(self, remediation_coordinator, mock_script_executor):
        """Test execution without script specified"""
        remediation_coordinator.script_executor = mock_script_executor
        action = {}
        incident = {"incident_id": "INC-001"}

        result = await remediation_coordinator._exec_script(action, incident)

        assert result["success"] is False
        assert "error" in result["details"]


class TestGetPredefinedScript:
    """Tests for _get_predefined_script method"""

    def test_get_predefined_script_revoke_tokens(self, remediation_coordinator):
        """Test getting revoke_tokens.sh script"""
        script = remediation_coordinator._get_predefined_script(
            "revoke_tokens.sh",
            {"incident_id": "INC-001"}
        )

        assert "#!/bin/sh" in script
        assert "INC-001" in script
        assert "Revoking tokens" in script

    def test_get_predefined_script_unknown(self, remediation_coordinator):
        """Test getting unknown script"""
        script = remediation_coordinator._get_predefined_script(
            "unknown_script.sh",
            {"incident_id": "INC-001"}
        )

        assert "Unknown script" in script
        assert "INC-001" in script


class TestRestartPod:
    """Tests for _restart_pod method"""

    @pytest.mark.asyncio
    async def test_restart_pod_success(self, remediation_coordinator, mock_k8s_client):
        """Test successful pod restart"""
        action = {"selector": "app"}
        incident = {
            "incident_id": "INC-001",
            "affected_resources": ["neural-hive/pod/test-pod-abc123"]
        }

        result = await remediation_coordinator._restart_pod(action, incident)

        assert result["success"] is True
        assert result["details"]["pod_deleted"] == "test-pod-abc123"
        mock_k8s_client.delete_pod.assert_called_once()

    @pytest.mark.asyncio
    async def test_restart_pod_no_resources(self, remediation_coordinator):
        """Test pod restart with no resources"""
        action = {"selector": "app"}
        incident = {
            "incident_id": "INC-001",
            "affected_resources": []
        }

        result = await remediation_coordinator._restart_pod(action, incident)

        # Should succeed with warning (graceful degradation)
        assert result["success"] is True
        assert "warning" in result["details"]
