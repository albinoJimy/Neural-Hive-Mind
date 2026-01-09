"""Unit tests for IncidentOrchestrator"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from src.services.incident_orchestrator import IncidentOrchestrator


@pytest.fixture
def mock_threat_detector():
    """Mock ThreatDetector"""
    detector = MagicMock()
    detector.detect_anomaly = AsyncMock(return_value={
        "threat_type": "unauthorized_access",
        "severity": "high",
        "confidence": 0.95
    })
    return detector


@pytest.fixture
def mock_incident_classifier():
    """Mock IncidentClassifier"""
    classifier = MagicMock()
    classifier.classify_incident = AsyncMock(return_value={
        "incident_id": "INC-001",
        "severity": "high",
        "runbook_id": "RB-SEC-001",
        "priority": 1
    })
    return classifier


@pytest.fixture
def mock_policy_enforcer():
    """Mock PolicyEnforcer"""
    enforcer = MagicMock()
    enforcer.enforce_policy = AsyncMock(return_value={
        "success": True,
        "actions": [{"action": "revoke_access"}]
    })
    return enforcer


@pytest.fixture
def mock_remediation_coordinator():
    """Mock RemediationCoordinator"""
    coordinator = MagicMock()
    coordinator.coordinate_remediation = AsyncMock(return_value={
        "remediation_id": "REM-001",
        "status": "completed",
        "actions": [{"action_type": "restart_pod"}]
    })
    return coordinator


@pytest.fixture
def mock_mongodb_client():
    """Mock MongoDB client"""
    client = MagicMock()
    client.incidents_collection = MagicMock()
    client.incidents_collection.update_one = AsyncMock()
    client.postmortems_collection = MagicMock()
    client.postmortems_collection.insert_one = AsyncMock()
    client.critical_incidents_collection = MagicMock()
    client.critical_incidents_collection.insert_one = AsyncMock()
    return client


@pytest.fixture
def mock_kafka_producer():
    """Mock Kafka producer"""
    producer = MagicMock()
    producer.publish_remediation_result = AsyncMock(return_value=True)
    producer.publish_critical_incident = AsyncMock()
    return producer


@pytest.fixture
def mock_itsm_client():
    """Mock ITSM client"""
    client = MagicMock()
    client.is_healthy = MagicMock(return_value=True)
    client.create_incident = AsyncMock(return_value={
        "success": True,
        "ticket_id": "SNOW-12345",
        "itsm_type": "servicenow"
    })
    return client


@pytest.fixture
def incident_orchestrator(
    mock_threat_detector,
    mock_incident_classifier,
    mock_policy_enforcer,
    mock_remediation_coordinator,
    mock_mongodb_client,
    mock_kafka_producer
):
    """IncidentOrchestrator with mocked dependencies"""
    return IncidentOrchestrator(
        threat_detector=mock_threat_detector,
        incident_classifier=mock_incident_classifier,
        policy_enforcer=mock_policy_enforcer,
        remediation_coordinator=mock_remediation_coordinator,
        mongodb_client=mock_mongodb_client,
        kafka_producer=mock_kafka_producer
    )


class TestOpenCriticalIncident:
    """Tests for _open_critical_incident method"""

    @pytest.mark.asyncio
    async def test_open_critical_incident_with_itsm(
        self, incident_orchestrator, mock_itsm_client, mock_mongodb_client
    ):
        """Test opening critical incident with ITSM integration"""
        incident_orchestrator.itsm_client = mock_itsm_client

        incident = {
            "incident_id": "INC-001",
            "severity": "critical",
            "threat_type": "data_exfiltration"
        }
        issues = ["MTTR exceeded", "Remediation failed"]

        await incident_orchestrator._open_critical_incident(incident, issues)

        mock_itsm_client.create_incident.assert_called_once()
        call_kwargs = mock_itsm_client.create_incident.call_args.kwargs
        assert "Critical SLA Breach" in call_kwargs["title"]
        assert call_kwargs["priority"] == "critical"
        assert call_kwargs["original_incident_id"] == "INC-001"

    @pytest.mark.asyncio
    async def test_open_critical_incident_itsm_not_available(
        self, incident_orchestrator, mock_mongodb_client
    ):
        """Test opening critical incident when ITSM is not available"""
        incident = {
            "incident_id": "INC-001",
            "severity": "critical",
            "threat_type": "unauthorized_access"
        }
        issues = ["SLA not restored"]

        # Should not raise error
        await incident_orchestrator._open_critical_incident(incident, issues)

        # Should still try to persist
        mock_mongodb_client.critical_incidents_collection.insert_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_open_critical_incident_itsm_failure(
        self, incident_orchestrator, mock_itsm_client
    ):
        """Test handling ITSM creation failure"""
        mock_itsm_client.create_incident = AsyncMock(return_value={
            "success": False,
            "error": "Connection refused"
        })
        incident_orchestrator.itsm_client = mock_itsm_client

        incident = {
            "incident_id": "INC-001",
            "severity": "high",
            "threat_type": "dos_attack"
        }
        issues = ["Attack ongoing"]

        # Should not raise error
        await incident_orchestrator._open_critical_incident(incident, issues)


class TestPublishIncidentOutcome:
    """Tests for _publish_incident_outcome method"""

    @pytest.mark.asyncio
    async def test_publish_incident_outcome_success(
        self, incident_orchestrator, mock_kafka_producer
    ):
        """Test successful outcome publishing"""
        result = {
            "incident_id": "INC-001",
            "flow": "E1-E6_complete",
            "e5_sla_validation": {"sla_met": True}
        }

        await incident_orchestrator._publish_incident_outcome(result)

        mock_kafka_producer.publish_remediation_result.assert_called_once_with(
            remediation_id="INC-001",
            result=result
        )

    @pytest.mark.asyncio
    async def test_publish_incident_outcome_no_producer(self, incident_orchestrator):
        """Test outcome publishing when Kafka producer is not available"""
        incident_orchestrator.kafka_producer = None

        result = {"incident_id": "INC-001"}

        # Should not raise error
        await incident_orchestrator._publish_incident_outcome(result)

    @pytest.mark.asyncio
    async def test_publish_incident_outcome_failure(
        self, incident_orchestrator, mock_kafka_producer
    ):
        """Test handling publishing failure"""
        mock_kafka_producer.publish_remediation_result = AsyncMock(return_value=False)

        result = {"incident_id": "INC-001"}

        # Should not raise error
        await incident_orchestrator._publish_incident_outcome(result)


class TestE5ValidateSLARestoration:
    """Tests for _e5_validate_sla_restoration method"""

    @pytest.mark.asyncio
    async def test_validate_sla_met(self, incident_orchestrator):
        """Test SLA validation when all targets are met"""
        incident = {"incident_id": "INC-001", "affected_resources": []}
        remediation_result = {"status": "completed"}
        flow_start_time = datetime.now(timezone.utc)

        result = await incident_orchestrator._e5_validate_sla_restoration(
            incident, remediation_result, flow_start_time
        )

        assert result["sla_met"] is True
        assert len(result["issues"]) == 0

    @pytest.mark.asyncio
    async def test_validate_sla_not_met_mttr_exceeded(self, incident_orchestrator):
        """Test SLA validation when MTTR is exceeded"""
        incident = {"incident_id": "INC-001", "affected_resources": []}
        remediation_result = {"status": "completed"}
        # Set start time to simulate long running remediation
        from datetime import timedelta
        flow_start_time = datetime.now(timezone.utc) - timedelta(seconds=100)

        result = await incident_orchestrator._e5_validate_sla_restoration(
            incident, remediation_result, flow_start_time
        )

        assert result["sla_met"] is False
        assert any("MTTR exceeded" in issue for issue in result["issues"])

    @pytest.mark.asyncio
    async def test_validate_sla_not_met_remediation_failed(self, incident_orchestrator):
        """Test SLA validation when remediation failed"""
        incident = {"incident_id": "INC-001", "affected_resources": []}
        remediation_result = {"status": "failed"}
        flow_start_time = datetime.now(timezone.utc)

        result = await incident_orchestrator._e5_validate_sla_restoration(
            incident, remediation_result, flow_start_time
        )

        assert result["sla_met"] is False
        assert any("not completed" in issue for issue in result["issues"])


class TestE6DocumentLessons:
    """Tests for _e6_document_lessons method"""

    @pytest.mark.asyncio
    async def test_document_lessons_success(
        self, incident_orchestrator, mock_mongodb_client
    ):
        """Test successful lessons documentation"""
        incident = {
            "incident_id": "INC-001",
            "threat_type": "unauthorized_access",
            "severity": "high",
            "runbook_id": "RB-SEC-001"
        }
        enforcement_result = {"success": True, "actions": []}
        remediation_result = {"status": "completed", "actions": []}
        sla_validation = {"sla_met": True, "recovery_time_s": 45.0}

        result = await incident_orchestrator._e6_document_lessons(
            incident, enforcement_result, remediation_result, sla_validation
        )

        assert result["incident_id"] == "INC-001"
        assert result["threat_type"] == "unauthorized_access"
        assert "summary" in result
        mock_mongodb_client.postmortems_collection.insert_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_document_lessons_mongodb_failure(
        self, incident_orchestrator, mock_mongodb_client
    ):
        """Test handling MongoDB failure during documentation"""
        mock_mongodb_client.postmortems_collection.insert_one = AsyncMock(
            side_effect=Exception("Connection failed")
        )

        incident = {
            "incident_id": "INC-001",
            "threat_type": "dos_attack",
            "severity": "critical",
            "runbook_id": "RB-AVAIL-001"
        }
        enforcement_result = {"success": True, "actions": []}
        remediation_result = {"status": "completed", "actions": []}
        sla_validation = {"sla_met": False, "recovery_time_s": 120.0}

        # Should not raise error
        result = await incident_orchestrator._e6_document_lessons(
            incident, enforcement_result, remediation_result, sla_validation
        )

        assert result is not None


class TestProcessIncidentFlow:
    """Tests for process_incident_flow method"""

    @pytest.mark.asyncio
    async def test_full_flow_success(self, incident_orchestrator):
        """Test successful complete E1-E6 flow"""
        event = {
            "type": "security_event",
            "event_id": "EVT-001"
        }

        result = await incident_orchestrator.process_incident_flow(event)

        assert result["incident_id"] == "INC-001"
        assert result["flow"] == "E1-E6_complete"
        assert "e1_anomaly" in result
        assert "e2_classification" in result
        assert "e3_enforcement" in result
        assert "e4_remediation" in result
        assert "e5_sla_validation" in result
        assert "e6_lessons_learned" in result

    @pytest.mark.asyncio
    async def test_flow_no_anomaly_detected(
        self, incident_orchestrator, mock_threat_detector
    ):
        """Test flow when no anomaly is detected"""
        mock_threat_detector.detect_anomaly = AsyncMock(return_value=None)

        event = {
            "type": "normal_event",
            "event_id": "EVT-002"
        }

        result = await incident_orchestrator.process_incident_flow(event)

        assert result["incident_detected"] is False
        assert result["event_id"] == "EVT-002"
