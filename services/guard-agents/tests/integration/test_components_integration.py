"""
Testes de integração dos componentes do fluxo de resiliência.
Valida que componentes individuais funcionam integrados.
"""
import pytest
from unittest.mock import Mock, AsyncMock
from datetime import datetime, timezone


@pytest.mark.asyncio
async def test_producer_publishes_to_kafka():
    """Testa que RemediationProducer publica eventos no Kafka"""
    from src.producers.remediation_producer import RemediationProducer

    # Mock do producer Kafka
    mock_kafka_producer = AsyncMock()
    mock_kafka_producer.send_and_wait = AsyncMock(return_value=Mock(partition=0, offset=123))

    producer = RemediationProducer(
        bootstrap_servers="localhost:9092",
        topic="remediation-actions"
    )
    producer.producer = mock_kafka_producer
    producer._connected = True

    # Publicar evento
    success = await producer.publish_remediation_action(
        remediation_id="REM-001",
        incident_id="INC-001",
        action_type="restart_pod",
        status="completed",
        details={"pod": "api-gateway-123"}
    )

    assert success is True
    assert mock_kafka_producer.send_and_wait.called
    print("✅ RemediationProducer: Publica eventos corretamente")


@pytest.mark.asyncio
async def test_self_healing_client_triggers_remediation():
    """Testa que SelfHealingClient comunica com engine"""
    from src.clients.self_healing_client import SelfHealingClient

    # Mock do HTTP client
    mock_http_client = AsyncMock()
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json = Mock(return_value={
        "remediation_id": "REM-001",
        "status": "pending"
    })
    mock_response.raise_for_status = Mock()
    mock_http_client.post = AsyncMock(return_value=mock_response)

    client = SelfHealingClient(base_url="http://localhost:8080")
    client._client = mock_http_client

    # Acionar remediação
    result = await client.trigger_remediation(
        remediation_id="REM-001",
        incident_id="INC-001",
        playbook_id="RB-SEC-001",
        parameters={}
    )

    assert result["remediation_id"] == "REM-001"
    assert result["status"] == "pending"
    assert mock_http_client.post.called
    print("✅ SelfHealingClient: Dispara remediações corretamente")


@pytest.mark.asyncio
async def test_opa_client_evaluates_policy():
    """Testa que OPAClient valida políticas"""
    from src.clients.opa_client import OPAClient

    # Mock do HTTP client
    mock_http_client = AsyncMock()
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json = Mock(return_value={
        "result": {
            "allowed": True,
            "reason": "Policy evaluation passed"
        }
    })
    mock_response.raise_for_status = Mock()
    mock_http_client.post = AsyncMock(return_value=mock_response)

    client = OPAClient(base_url="http://opa:8181")
    client._client = mock_http_client

    # Avaliar política
    result = await client.evaluate_policy(
        policy_path="security/unauthorized_access",
        input_data={"incident": {"severity": "critical"}}
    )

    assert result["allowed"] is True
    assert mock_http_client.post.called
    print("✅ OPAClient: Avalia políticas corretamente")


@pytest.mark.asyncio
async def test_prometheus_client_validates_sla():
    """Testa que PrometheusClient valida SLA"""
    from src.clients.prometheus_client import PrometheusClient

    # Mock do HTTP client
    mock_http_client = AsyncMock()

    # Mock de queries Prometheus
    def mock_get(url, **kwargs):
        response = Mock()
        response.status_code = 200

        if "query=" in str(kwargs.get("params", {})):
            response.json = Mock(return_value={
                "status": "success",
                "data": {
                    "result": [
                        {"value": [1234567890, "0.99"]}
                    ]
                }
            })

        response.raise_for_status = Mock()
        return response

    mock_http_client.get = AsyncMock(side_effect=mock_get)

    client = PrometheusClient(base_url="http://prometheus:9090")
    client._client = mock_http_client

    # Validar SLA
    result = await client.validate_sla_restoration(
        service="api-gateway",
        sla_targets={
            "min_success_rate": 99.9,
            "max_latency_p99": 0.5,
            "max_error_rate": 0.1
        }
    )

    assert "sla_restored" in result
    assert "metrics" in result
    print(f"✅ PrometheusClient: Valida SLA - Restaurado: {result['sla_restored']}")


@pytest.mark.asyncio
async def test_policy_enforcer_with_opa_istio():
    """Testa PolicyEnforcer com OPA e Istio integrados"""
    from src.services.policy_enforcer import PolicyEnforcer

    # Mocks
    mock_k8s = Mock()
    mock_redis = Mock()
    mock_redis.set = AsyncMock()

    mock_opa_client = AsyncMock()
    mock_opa_client.evaluate_policy = AsyncMock(return_value={
        "allowed": True,
        "reason": "Policy passed"
    })

    mock_istio_client = AsyncMock()
    mock_istio_client.block_ip = AsyncMock(return_value={
        "success": True,
        "name": "block-ip-10-0-0-100"
    })

    # Criar enforcer
    enforcer = PolicyEnforcer(
        k8s_client=mock_k8s,
        redis_client=mock_redis,
        opa_client=mock_opa_client,
        istio_client=mock_istio_client,
        opa_enabled=True,
        istio_enabled=True
    )

    # Enforçar política
    incident = {
        "incident_id": "INC-001",
        "threat_type": "dos_attack",
        "severity": "critical",
        "affected_resources": ["api-gateway"],
        "anomaly": {
            "details": {
                "source_ip": "10.0.0.100"
            }
        }
    }

    result = await enforcer.enforce_policy(incident)

    assert result["success"] is True
    assert mock_opa_client.evaluate_policy.called
    assert mock_istio_client.block_ip.called
    print("✅ PolicyEnforcer: Integra OPA e Istio corretamente")


@pytest.mark.asyncio
async def test_remediation_coordinator_with_engine():
    """Testa RemediationCoordinator delegando para Self-Healing Engine"""
    from src.services.remediation_coordinator import RemediationCoordinator

    # Mocks
    mock_k8s = Mock()
    mock_mongodb = Mock()
    mock_mongodb.remediation_collection = Mock()
    mock_mongodb.remediation_collection.insert_one = AsyncMock()

    mock_kafka_producer = AsyncMock()
    mock_kafka_producer.publish_remediation_result = AsyncMock(return_value=True)

    mock_sh_client = AsyncMock()
    mock_sh_client.trigger_remediation = AsyncMock(return_value={
        "remediation_id": "REM-001",
        "status": "pending"
    })
    mock_sh_client.wait_for_completion = AsyncMock(return_value={
        "remediation_id": "REM-001",
        "status": "completed"
    })

    # Criar coordinator
    coordinator = RemediationCoordinator(
        k8s_client=mock_k8s,
        mongodb_client=mock_mongodb,
        kafka_producer=mock_kafka_producer,
        self_healing_client=mock_sh_client,
        use_self_healing_engine=True
    )

    # Coordenar remediação
    incident = {
        "incident_id": "INC-001",
        "runbook_id": "RB-SEC-001-CRITICAL",
        "severity": "critical"
    }

    enforcement_result = {"success": True}

    result = await coordinator.coordinate_remediation(incident, enforcement_result)

    assert result["status"] == "completed"
    assert mock_sh_client.trigger_remediation.called
    assert mock_sh_client.wait_for_completion.called
    assert mock_kafka_producer.publish_remediation_result.called
    print("✅ RemediationCoordinator: Delega para Self-Healing Engine corretamente")


@pytest.mark.asyncio
async def test_full_pipeline_integration():
    """
    Testa integração completa dos componentes principais:
    PolicyEnforcer -> RemediationCoordinator -> Kafka -> Self-Healing
    """
    from src.services.policy_enforcer import PolicyEnforcer
    from src.services.remediation_coordinator import RemediationCoordinator

    # Setup completo
    mock_k8s = Mock()
    mock_redis = Mock()
    mock_redis.set = AsyncMock()
    mock_mongodb = Mock()
    mock_mongodb.remediation_collection = Mock()
    mock_mongodb.remediation_collection.insert_one = AsyncMock()

    mock_opa = AsyncMock()
    mock_opa.evaluate_policy = AsyncMock(return_value={"allowed": True})

    mock_istio = AsyncMock()
    mock_istio.apply_rate_limit = AsyncMock(return_value={"success": True})

    mock_kafka = AsyncMock()
    mock_kafka.publish_remediation_result = AsyncMock(return_value=True)

    mock_sh = AsyncMock()
    mock_sh.trigger_remediation = AsyncMock(return_value={"remediation_id": "REM-001", "status": "pending"})
    mock_sh.wait_for_completion = AsyncMock(return_value={"status": "completed"})

    # Criar componentes
    enforcer = PolicyEnforcer(
        k8s_client=mock_k8s,
        redis_client=mock_redis,
        opa_client=mock_opa,
        istio_client=mock_istio,
        opa_enabled=True,
        istio_enabled=True
    )

    coordinator = RemediationCoordinator(
        k8s_client=mock_k8s,
        mongodb_client=mock_mongodb,
        kafka_producer=mock_kafka,
        self_healing_client=mock_sh,
        use_self_healing_engine=True
    )

    # Simular incidente
    incident = {
        "incident_id": "INC-001",
        "threat_type": "dos_attack",
        "severity": "critical",
        "runbook_id": "RB-AVAIL-001-CRITICAL",
        "affected_resources": ["api-gateway"],
        "anomaly": {"details": {"source_ip": "10.0.0.100"}}
    }

    # Executar pipeline
    # 1. Enforçar políticas
    enforcement = await enforcer.enforce_policy(incident)
    assert enforcement["success"] is True

    # 2. Coordenar remediação
    remediation = await coordinator.coordinate_remediation(incident, enforcement)
    assert remediation["status"] == "completed"

    # Verificações
    assert mock_opa.evaluate_policy.called
    assert mock_istio.apply_rate_limit.called
    assert mock_sh.trigger_remediation.called
    assert mock_kafka.publish_remediation_result.called

    print("✅ Pipeline completo: E3 -> E4 -> Kafka -> Self-Healing funcionando!")
    print(f"   - OPA validou: {mock_opa.evaluate_policy.called}")
    print(f"   - Istio enforçou: {mock_istio.apply_rate_limit.called}")
    print(f"   - Engine executou: {mock_sh.trigger_remediation.called}")
    print(f"   - Kafka publicou: {mock_kafka.publish_remediation_result.called}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
