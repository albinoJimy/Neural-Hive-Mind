"""Unit tests for PolicyEnforcer"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.services.policy_enforcer import PolicyEnforcer, EnforcementAction


@pytest.fixture
def mock_k8s_client():
    """Mock Kubernetes client"""
    client = MagicMock()
    client.namespace = "neural-hive"
    client.patch_pod_labels = AsyncMock(return_value=True)
    client.apply_network_policy = AsyncMock(return_value={
        "success": True,
        "action": "created",
        "policy_name": "test-policy"
    })
    return client


@pytest.fixture
def mock_keycloak_client():
    """Mock Keycloak client"""
    client = MagicMock()
    client.revoke_user_sessions = AsyncMock(return_value={
        "success": True,
        "timestamp": "2025-01-01T00:00:00Z"
    })
    client.disable_user = AsyncMock(return_value={
        "success": True,
        "timestamp": "2025-01-01T00:00:00Z"
    })
    return client


@pytest.fixture
def mock_mongodb_client():
    """Mock MongoDB client"""
    client = MagicMock()
    client.remediation_collection = MagicMock()
    client.remediation_collection.insert_one = AsyncMock()
    return client


@pytest.fixture
def policy_enforcer(mock_k8s_client, mock_keycloak_client, mock_mongodb_client):
    """PolicyEnforcer with mocked dependencies"""
    return PolicyEnforcer(
        k8s_client=mock_k8s_client,
        keycloak_client=mock_keycloak_client,
        mongodb_client=mock_mongodb_client,
        opa_enabled=False,
        istio_enabled=False
    )


class TestQuarantineResource:
    """Tests for _quarantine_resource method"""

    @pytest.mark.asyncio
    async def test_quarantine_resource_success(self, policy_enforcer, mock_k8s_client):
        """Test successful quarantine of resources"""
        incident = {
            "incident_id": "INC-001",
            "affected_resources": ["neural-hive/pod/test-pod-1", "neural-hive/pod/test-pod-2"]
        }
        plan = {"target": "isolate"}

        result = await policy_enforcer._quarantine_resource(incident, plan)

        assert result["success"] is True
        assert result["action"] == "quarantine"
        assert len(result["details"]["quarantined_pods"]) == 2
        assert result["details"]["network_policy"] is not None
        assert mock_k8s_client.patch_pod_labels.call_count == 2
        assert mock_k8s_client.apply_network_policy.call_count == 1

    @pytest.mark.asyncio
    async def test_quarantine_resource_no_resources(self, policy_enforcer):
        """Test quarantine with no resources"""
        incident = {
            "incident_id": "INC-001",
            "affected_resources": []
        }
        plan = {}

        result = await policy_enforcer._quarantine_resource(incident, plan)

        assert result["success"] is False
        assert result["reason"] == "No resources to quarantine"

    @pytest.mark.asyncio
    async def test_quarantine_resource_k8s_not_available(self, policy_enforcer):
        """Test quarantine when K8s client is not available"""
        policy_enforcer.k8s = None
        incident = {
            "incident_id": "INC-001",
            "affected_resources": ["test-pod"]
        }
        plan = {}

        result = await policy_enforcer._quarantine_resource(incident, plan)

        assert result["success"] is True  # Graceful degradation
        assert "warning" in result["details"]

    @pytest.mark.asyncio
    async def test_quarantine_resource_label_failure(self, policy_enforcer, mock_k8s_client):
        """Test quarantine when labeling fails"""
        mock_k8s_client.patch_pod_labels = AsyncMock(return_value=False)

        incident = {
            "incident_id": "INC-001",
            "affected_resources": ["neural-hive/pod/test-pod"]
        }
        plan = {}

        result = await policy_enforcer._quarantine_resource(incident, plan)

        assert result["success"] is False
        assert "errors" in result["details"]


class TestParseResource:
    """Tests for _parse_resource method"""

    def test_parse_resource_full_format(self, policy_enforcer):
        """Test parsing namespace/kind/name format"""
        namespace, name = policy_enforcer._parse_resource("neural-hive/pod/test-pod")
        assert namespace == "neural-hive"
        assert name == "test-pod"

    def test_parse_resource_kind_name(self, policy_enforcer):
        """Test parsing kind/name format"""
        namespace, name = policy_enforcer._parse_resource("pod/test-pod")
        assert namespace is None
        assert name == "test-pod"

    def test_parse_resource_name_only(self, policy_enforcer):
        """Test parsing name only format"""
        namespace, name = policy_enforcer._parse_resource("test-pod")
        assert namespace is None
        assert name == "test-pod"

    def test_parse_resource_empty(self, policy_enforcer):
        """Test parsing empty string"""
        namespace, name = policy_enforcer._parse_resource("")
        assert namespace is None
        assert name is None


class TestRevokeAccess:
    """Tests for _revoke_access method"""

    @pytest.mark.asyncio
    async def test_revoke_access_success(self, policy_enforcer, mock_keycloak_client):
        """Test successful access revocation"""
        incident = {
            "incident_id": "INC-001",
            "anomaly": {"details": {"user_id": "user-123"}}
        }
        plan = {}

        result = await policy_enforcer._revoke_access(incident, plan)

        assert result["success"] is True
        assert result["action"] == "revoke_access"
        assert result["details"]["keycloak_action"] == "sessions_revoked"
        mock_keycloak_client.revoke_user_sessions.assert_called_once_with("user-123")

    @pytest.mark.asyncio
    async def test_revoke_access_fallback_to_disable(self, policy_enforcer, mock_keycloak_client):
        """Test fallback to disabling user when session revoke fails"""
        mock_keycloak_client.revoke_user_sessions = AsyncMock(return_value={
            "success": False,
            "reason": "Session not found"
        })

        incident = {
            "incident_id": "INC-001",
            "anomaly": {"details": {"user_id": "user-123"}}
        }
        plan = {}

        result = await policy_enforcer._revoke_access(incident, plan)

        assert result["success"] is True
        assert result["details"]["keycloak_action"] == "user_disabled"
        mock_keycloak_client.disable_user.assert_called_once_with("user-123")

    @pytest.mark.asyncio
    async def test_revoke_access_no_user_id(self, policy_enforcer):
        """Test revoke access without user ID"""
        incident = {
            "incident_id": "INC-001",
            "anomaly": {"details": {}}
        }
        plan = {}

        result = await policy_enforcer._revoke_access(incident, plan)

        assert result["success"] is False
        assert result["reason"] == "No user ID"

    @pytest.mark.asyncio
    async def test_revoke_access_keycloak_not_available(self, policy_enforcer):
        """Test revoke access when Keycloak is not available"""
        policy_enforcer.keycloak_client = None

        incident = {
            "incident_id": "INC-001",
            "anomaly": {"details": {"user_id": "user-123"}}
        }
        plan = {}

        result = await policy_enforcer._revoke_access(incident, plan)

        assert result["success"] is True  # Graceful degradation
        assert result["details"]["keycloak_action"] == "bypassed"
