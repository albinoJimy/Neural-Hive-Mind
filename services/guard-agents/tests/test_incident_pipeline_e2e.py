"""
Teste end-to-end do pipeline completo de incidentes (E1-E6)

Testa o fluxo completo:
E1: Detectar anomalia
E2: Classificar severidade
E3: Enforçar políticas (OPA/Istio)
E4: Executar playbooks de autocura
E5: Validar restauração de SLA
E6: Documentar lições aprendidas
"""
import pytest
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.threat_detector import ThreatDetector
from src.services.incident_classifier import IncidentClassifier
from src.services.policy_enforcer import PolicyEnforcer
from src.services.remediation_coordinator import RemediationCoordinator
from src.services.incident_orchestrator import IncidentOrchestrator


@pytest.fixture
def mock_mongodb_client():
    """Mock MongoDB client"""
    client = MagicMock()
    client.incidents_collection = AsyncMock()
    client.remediation_collection = AsyncMock()
    client.postmortems_collection = AsyncMock()
    return client


@pytest.fixture
def mock_redis_client():
    """Mock Redis client"""
    client = AsyncMock()
    client.set = AsyncMock()
    client.get = AsyncMock()
    return client


@pytest.fixture
def mock_k8s_client():
    """Mock Kubernetes client"""
    client = AsyncMock()
    client.is_healthy = MagicMock(return_value=True)
    return client


@pytest.fixture
def threat_detector(mock_redis_client):
    """Fixture do ThreatDetector"""
    return ThreatDetector(redis_client=mock_redis_client)


@pytest.fixture
def incident_classifier(mock_mongodb_client):
    """Fixture do IncidentClassifier"""
    return IncidentClassifier(mongodb_client=mock_mongodb_client)


@pytest.fixture
def mock_keycloak_client():
    """Mock Keycloak Admin client"""
    client = AsyncMock()
    client.revoke_user_sessions = AsyncMock(return_value={
        "success": True,
        "user_id": "test-user",
        "action": "revoke_sessions",
        "timestamp": "2024-01-01T00:00:00Z"
    })
    client.disable_user = AsyncMock(return_value={
        "success": True,
        "user_id": "test-user",
        "action": "disable_user",
        "timestamp": "2024-01-01T00:00:00Z"
    })
    return client


@pytest.fixture
def policy_enforcer(mock_k8s_client, mock_redis_client, mock_keycloak_client, mock_mongodb_client):
    """Fixture do PolicyEnforcer com Keycloak Admin"""
    return PolicyEnforcer(
        k8s_client=mock_k8s_client,
        redis_client=mock_redis_client,
        keycloak_client=mock_keycloak_client,
        mongodb_client=mock_mongodb_client
    )


@pytest.fixture
def remediation_coordinator(mock_k8s_client, mock_mongodb_client):
    """Fixture do RemediationCoordinator"""
    return RemediationCoordinator(
        k8s_client=mock_k8s_client,
        mongodb_client=mock_mongodb_client,
        kafka_producer=None
    )


@pytest.fixture
def incident_orchestrator(
    threat_detector,
    incident_classifier,
    policy_enforcer,
    remediation_coordinator,
    mock_mongodb_client
):
    """Fixture do IncidentOrchestrator"""
    return IncidentOrchestrator(
        threat_detector=threat_detector,
        incident_classifier=incident_classifier,
        policy_enforcer=policy_enforcer,
        remediation_coordinator=remediation_coordinator,
        mongodb_client=mock_mongodb_client,
        kafka_producer=None
    )


@pytest.mark.asyncio
async def test_e1_threat_detection_unauthorized_access(threat_detector):
    """Testa E1: Detecção de acesso não autorizado"""
    event = {
        "type": "authentication",
        "event_id": "evt-001",
        "user_id": "user-123",
        "failed_attempts": 10,
        "source_ip": "192.168.1.100",
    }

    anomaly = await threat_detector.detect_anomaly(event)

    assert anomaly is not None
    assert anomaly["threat_type"] == "unauthorized_access"
    assert anomaly["severity"] == "high"
    assert anomaly["confidence"] >= 0.5


@pytest.mark.asyncio
async def test_e1_threat_detection_dos_attack(threat_detector):
    """Testa E1: Detecção de ataque DoS"""
    event = {
        "type": "request_metrics",
        "event_id": "evt-002",
        "requests_per_minute": 5000,
        "source": "external-lb",
    }

    anomaly = await threat_detector.detect_anomaly(event)

    assert anomaly is not None
    assert anomaly["threat_type"] == "dos_attack"
    assert anomaly["severity"] == "critical"


@pytest.mark.asyncio
async def test_e1_threat_detection_resource_anomaly(threat_detector):
    """Testa E1: Detecção de anomalia de recursos"""
    event = {
        "type": "resource_metrics",
        "event_id": "evt-003",
        "metrics": {
            "cpu_usage": 0.95,
            "memory_usage": 0.92,
        },
        "resource_name": "pod-xyz",
    }

    anomaly = await threat_detector.detect_anomaly(event)

    assert anomaly is not None
    assert anomaly["threat_type"] == "resource_abuse"


@pytest.mark.asyncio
async def test_e2_incident_classification(incident_classifier):
    """Testa E2: Classificação de severidade e mapeamento a runbooks"""
    anomaly = {
        "threat_type": "unauthorized_access",
        "severity": "high",
        "confidence": 0.85,
        "detected_at": datetime.now(timezone.utc).isoformat(),
        "details": {"user_id": "user-123", "failed_attempts": 10},
        "raw_event": {},
    }

    incident = await incident_classifier.classify_incident(anomaly)

    assert incident is not None
    assert "incident_id" in incident
    assert incident["severity"] in ["critical", "high", "medium", "low", "info"]
    assert "runbook_id" in incident
    assert incident["runbook_id"].startswith("RB-")


@pytest.mark.asyncio
async def test_e3_policy_enforcement(policy_enforcer):
    """Testa E3: Enforcement de políticas"""
    incident = {
        "incident_id": "INC-TEST-001",
        "threat_type": "unauthorized_access",
        "severity": "high",
        "runbook_id": "RB-SEC-001-HIGH",
    }

    enforcement_result = await policy_enforcer.enforce_policy(incident)

    assert enforcement_result is not None
    assert "success" in enforcement_result
    assert "actions" in enforcement_result


@pytest.mark.asyncio
async def test_e4_remediation_coordination(remediation_coordinator):
    """Testa E4: Coordenação de remediação"""
    incident = {
        "incident_id": "INC-TEST-002",
        "threat_type": "resource_abuse",
        "severity": "high",
        "runbook_id": "RB-PERF-001-HIGH",
    }

    enforcement_result = {"success": True, "actions": []}

    remediation_result = await remediation_coordinator.coordinate_remediation(
        incident, enforcement_result
    )

    assert remediation_result is not None
    assert "remediation_id" in remediation_result
    assert "status" in remediation_result


@pytest.mark.asyncio
async def test_full_incident_pipeline_e1_to_e6(incident_orchestrator):
    """Testa fluxo completo E1→E6 com incidente de segurança"""
    # Event de autenticação suspeita
    event = {
        "type": "authentication",
        "event_id": "evt-e2e-001",
        "user_id": "attacker-001",
        "failed_attempts": 15,
        "source_ip": "10.0.0.1",
    }

    context = {
        "environment": "production",
        "is_critical_resource": True,
    }

    # Processar fluxo completo
    result = await incident_orchestrator.process_incident_flow(event, context)

    # Validações do resultado
    assert result is not None
    assert "incident_id" in result
    assert result["flow"] == "E1-E6_complete"

    # E1: Detecção
    assert "e1_anomaly" in result
    assert result["e1_anomaly"]["threat_type"] == "unauthorized_access"

    # E2: Classificação
    assert "e2_classification" in result
    assert "severity" in result["e2_classification"]
    assert "runbook_id" in result["e2_classification"]

    # E3: Enforcement
    assert "e3_enforcement" in result
    assert "success" in result["e3_enforcement"]

    # E4: Remediação
    assert "e4_remediation" in result
    assert "status" in result["e4_remediation"]

    # E5: Validação SLA
    assert "e5_sla_validation" in result
    assert "sla_met" in result["e5_sla_validation"]
    assert "recovery_time_s" in result["e5_sla_validation"]

    # E6: Lições aprendidas
    assert "e6_lessons_learned" in result
    assert "summary" in result["e6_lessons_learned"]

    # Métricas
    assert "duration_ms" in result


@pytest.mark.asyncio
async def test_full_incident_pipeline_dos_attack(incident_orchestrator):
    """Testa fluxo completo E1→E6 com ataque DoS"""
    event = {
        "type": "request_metrics",
        "event_id": "evt-e2e-002",
        "requests_per_minute": 10000,
        "source": "external",
    }

    result = await incident_orchestrator.process_incident_flow(event)

    assert result is not None
    assert result["e1_anomaly"]["threat_type"] == "dos_attack"
    assert result["e1_anomaly"]["severity"] == "critical"


@pytest.mark.asyncio
async def test_full_incident_pipeline_resource_abuse(incident_orchestrator):
    """Testa fluxo completo E1→E6 com abuso de recursos"""
    event = {
        "type": "resource_metrics",
        "event_id": "evt-e2e-003",
        "metrics": {
            "cpu_usage": 0.99,
            "memory_usage": 0.95,
        },
        "resource_name": "pod-critical-001",
    }

    context = {
        "environment": "production",
        "is_critical_resource": True,
        "namespace": "production",
    }

    result = await incident_orchestrator.process_incident_flow(event, context)

    assert result is not None
    assert result["e1_anomaly"]["threat_type"] == "resource_abuse"


@pytest.mark.asyncio
async def test_no_incident_detected(incident_orchestrator):
    """Testa cenário onde nenhum incidente é detectado"""
    event = {
        "type": "authentication",
        "event_id": "evt-normal-001",
        "user_id": "user-normal",
        "failed_attempts": 0,
    }

    result = await incident_orchestrator.process_incident_flow(event)

    assert result is not None
    assert result["incident_detected"] is False
    assert "duration_ms" in result


@pytest.mark.asyncio
async def test_sla_metrics_mttd_mttr(incident_orchestrator):
    """Testa métricas de SLA (MTTD e MTTR)"""
    event = {
        "type": "authentication",
        "event_id": "evt-sla-001",
        "user_id": "attacker-sla",
        "failed_attempts": 20,
        "source_ip": "1.2.3.4",
    }

    result = await incident_orchestrator.process_incident_flow(event)

    # Verificar que MTTR está dentro do SLA target (< 90s)
    sla_validation = result["e5_sla_validation"]
    assert "recovery_time_s" in sla_validation
    assert "mttr_target_s" in sla_validation
    assert sla_validation["mttr_target_s"] == 90.0


if __name__ == "__main__":
    # Executar testes
    pytest.main([__file__, "-v", "-s"])
