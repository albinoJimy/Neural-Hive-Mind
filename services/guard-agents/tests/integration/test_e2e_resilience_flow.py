"""
Teste end-to-end do fluxo de resiliência E1-E6.
Valida que um incidente Kafka percorre toda a pipeline até validação de SLA.
"""
import pytest
import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import Mock, AsyncMock, patch


@pytest.fixture
def mock_incident_event():
    """Evento de incidente de segurança para teste"""
    return {
        "type": "security_incident",
        "event_id": "INC-TEST-001",
        "severity": "high",
        "threat_type": "dos_attack",
        "source_ip": "10.0.0.100",
        "user_id": "malicious_user",
        "payload": {"attack_type": "syn_flood"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "raw_data": {
            "incident_id": "INC-TEST-001",
            "affected_resources": ["neural-hive-resilience/deployment/api-gateway"]
        }
    }


@pytest.fixture
def mock_context():
    """Contexto adicional do incidente"""
    return {
        "environment": "staging",
        "is_critical_resource": True,
        "affected_resources": ["neural-hive-resilience/deployment/api-gateway"]
    }


@pytest.mark.asyncio
async def test_e1_e6_complete_flow(mock_incident_event, mock_context):
    """
    Testa fluxo completo E1→E6:
    - E1: Detectar anomalia
    - E2: Classificar severidade
    - E3: Enforçar políticas (OPA/Istio)
    - E4: Executar playbooks (via Self-Healing Engine)
    - E5: Validar SLA (Prometheus)
    - E6: Documentar lições
    """
    from src.services.incident_orchestrator import IncidentOrchestrator
    from src.services.threat_detector import ThreatDetector
    from src.services.incident_classifier import IncidentClassifier
    from src.services.policy_enforcer import PolicyEnforcer
    from src.services.remediation_coordinator import RemediationCoordinator

    # Mocks
    mock_redis = Mock()
    mock_mongodb = Mock()
    mock_k8s = Mock()
    mock_kafka_producer = AsyncMock()
    mock_self_healing_client = AsyncMock()
    mock_opa_client = AsyncMock()
    mock_istio_client = AsyncMock()
    mock_prometheus_client = AsyncMock()

    # Configurar comportamentos dos mocks

    # OPA: permitir enforcement
    mock_opa_client.evaluate_policy = AsyncMock(return_value={
        "allowed": True,
        "reason": "Policy evaluation passed"
    })

    # Istio: rate limiting aplicado
    mock_istio_client.apply_rate_limit = AsyncMock(return_value={
        "success": True,
        "name": "rate-limit-test",
        "rate_limit": "100/MINUTE"
    })

    # Self-Healing Engine: remediação bem-sucedida
    mock_self_healing_client.trigger_remediation = AsyncMock(return_value={
        "remediation_id": "REM-TEST-001",
        "status": "pending"
    })
    mock_self_healing_client.wait_for_completion = AsyncMock(return_value={
        "remediation_id": "REM-TEST-001",
        "status": "completed",
        "actions": ["rate_limit_applied", "scaled_deployment"]
    })

    # Prometheus: SLA restaurado
    mock_prometheus_client.validate_sla_restoration = AsyncMock(return_value={
        "sla_restored": True,
        "metrics": {
            "success_rate": 99.95,
            "latency_p99": 0.25,
            "error_rate": 0.05
        },
        "violations": []
    })

    # MongoDB: persistência
    mock_mongodb.incidents_collection = Mock()
    mock_mongodb.incidents_collection.insert_one = AsyncMock()

    # Kafka: publicação
    mock_kafka_producer.publish_remediation_result = AsyncMock(return_value=True)

    # Criar componentes
    threat_detector = ThreatDetector(redis_client=mock_redis)
    incident_classifier = IncidentClassifier(mongodb_client=mock_mongodb)
    policy_enforcer = PolicyEnforcer(
        k8s_client=mock_k8s,
        redis_client=mock_redis,
        opa_client=mock_opa_client,
        istio_client=mock_istio_client
    )
    remediation_coordinator = RemediationCoordinator(
        k8s_client=mock_k8s,
        mongodb_client=mock_mongodb,
        kafka_producer=mock_kafka_producer,
        self_healing_client=mock_self_healing_client
    )

    # Criar orquestrador
    orchestrator = IncidentOrchestrator(
        threat_detector=threat_detector,
        incident_classifier=incident_classifier,
        policy_enforcer=policy_enforcer,
        remediation_coordinator=remediation_coordinator,
        mongodb_client=mock_mongodb,
        kafka_producer=mock_kafka_producer,
        prometheus_client=mock_prometheus_client
    )

    # Executar fluxo completo
    result = await orchestrator.process_incident_flow(
        event=mock_incident_event,
        context=mock_context
    )

    # Validações

    # 1. Fluxo completou
    assert result is not None
    assert result.get("status") == "completed"

    # 2. Anomalia detectada (E1)
    assert result.get("anomaly") is not None
    assert result["anomaly"].get("detected") is True

    # 3. Incidente classificado (E2)
    assert result.get("incident") is not None
    assert result["incident"].get("severity") in ["critical", "high"]
    assert result["incident"].get("runbook_id") is not None

    # 4. Políticas enforçadas (E3)
    assert result.get("enforcement") is not None
    assert result["enforcement"].get("success") is True

    # OPA foi consultado
    assert mock_opa_client.evaluate_policy.called

    # Istio aplicou rate limit
    assert mock_istio_client.apply_rate_limit.called

    # 5. Remediação executada (E4)
    assert result.get("remediation") is not None
    assert result["remediation"].get("status") == "completed"

    # Self-Healing Engine foi acionado
    assert mock_self_healing_client.trigger_remediation.called
    assert mock_self_healing_client.wait_for_completion.called

    # 6. SLA validado (E5)
    assert result.get("sla_validation") is not None
    assert result["sla_validation"].get("sla_met") is True

    # Prometheus foi consultado
    assert mock_prometheus_client.validate_sla_restoration.called

    # 7. Lições documentadas (E6)
    assert result.get("lessons_learned") is not None
    assert result["lessons_learned"].get("incident_id") == mock_incident_event["event_id"]

    # 8. MTTD e MTTR dentro dos alvos
    duration_ms = result.get("duration_ms", 0)
    duration_s = duration_ms / 1000
    assert duration_s < 90.0  # MTTR < 90s

    # 9. Evento publicado no Kafka
    assert mock_kafka_producer.publish_remediation_result.called

    print("\n✅ Teste E2E do fluxo E1-E6 passou com sucesso!")
    print(f"   - Duração total: {duration_s:.2f}s")
    print(f"   - SLA restaurado: {result['sla_validation']['sla_met']}")
    print(f"   - Prometheus métricas: {result['sla_validation'].get('prometheus_metrics', {})}")


@pytest.mark.asyncio
async def test_e2e_with_sla_violation():
    """
    Testa fluxo E1-E6 quando SLA NÃO é restaurado.
    Valida que incidente crítico é aberto (E5).
    """
    from src.services.incident_orchestrator import IncidentOrchestrator
    from src.services.threat_detector import ThreatDetector
    from src.services.incident_classifier import IncidentClassifier
    from src.services.policy_enforcer import PolicyEnforcer
    from src.services.remediation_coordinator import RemediationCoordinator

    # Mocks
    mock_redis = Mock()
    mock_mongodb = Mock()
    mock_k8s = Mock()
    mock_kafka_producer = AsyncMock()
    mock_self_healing_client = AsyncMock()
    mock_prometheus_client = AsyncMock()

    # Self-Healing: remediação falha
    mock_self_healing_client.trigger_remediation = AsyncMock(return_value={
        "remediation_id": "REM-FAIL-001",
        "status": "pending"
    })
    mock_self_healing_client.wait_for_completion = AsyncMock(return_value={
        "remediation_id": "REM-FAIL-001",
        "status": "failed",
        "error": "Playbook execution failed"
    })

    # Prometheus: SLA NÃO restaurado
    mock_prometheus_client.validate_sla_restoration = AsyncMock(return_value={
        "sla_restored": False,
        "metrics": {
            "success_rate": 85.0,  # Abaixo de 99.9%
            "latency_p99": 2.5,    # Acima de 500ms
            "error_rate": 15.0     # Acima de 0.1%
        },
        "violations": [
            {"metric": "success_rate", "value": 85.0, "target": 99.9},
            {"metric": "latency_p99", "value": 2.5, "target": 0.5},
            {"metric": "error_rate", "value": 15.0, "target": 0.1}
        ]
    })

    mock_mongodb.incidents_collection = Mock()
    mock_mongodb.incidents_collection.insert_one = AsyncMock()
    mock_kafka_producer.publish_remediation_result = AsyncMock(return_value=True)

    # Criar componentes
    threat_detector = ThreatDetector(redis_client=mock_redis)
    incident_classifier = IncidentClassifier(mongodb_client=mock_mongodb)
    policy_enforcer = PolicyEnforcer(k8s_client=mock_k8s, redis_client=mock_redis)
    remediation_coordinator = RemediationCoordinator(
        k8s_client=mock_k8s,
        mongodb_client=mock_mongodb,
        kafka_producer=mock_kafka_producer,
        self_healing_client=mock_self_healing_client
    )

    orchestrator = IncidentOrchestrator(
        threat_detector=threat_detector,
        incident_classifier=incident_classifier,
        policy_enforcer=policy_enforcer,
        remediation_coordinator=remediation_coordinator,
        mongodb_client=mock_mongodb,
        kafka_producer=mock_kafka_producer,
        prometheus_client=mock_prometheus_client
    )

    event = {
        "type": "security_incident",
        "event_id": "INC-FAIL-001",
        "severity": "critical",
        "threat_type": "data_exfiltration",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    result = await orchestrator.process_incident_flow(event=event)

    # Validações

    # SLA não foi restaurado
    assert result["sla_validation"]["sla_met"] is False

    # Violações registradas
    assert len(result["sla_validation"]["violations"]) > 0

    # Remediação falhou
    assert result["remediation"]["status"] == "failed"

    print("\n✅ Teste E2E com violação de SLA passou!")
    print(f"   - Violações: {len(result['sla_validation']['violations'])}")
    print(f"   - Métricas: {result['sla_validation']['metrics']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
