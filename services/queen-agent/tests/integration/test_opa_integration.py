"""
Testes de integração com OPA real

Nota: Estes testes requerem um servidor OPA rodando em localhost:8181
Para executar:
    docker run -p 8181:8181 openpolicyagent/opa:latest run --server
    curl -X PUT http://localhost:8181/v1/policies/ethical_guardrails \
        --data-binary @policies/rego/queen/ethical_guardrails.rego
    pytest services/queen-agent/tests/integration/test_opa_integration.py -v
"""
import pytest
import httpx

from src.clients.opa_client import OPAClient


@pytest.fixture
async def opa_client():
    """Cria cliente OPA conectado ao servidor de teste"""
    client = OPAClient(base_url="http://localhost:8181", timeout=5.0)
    try:
        await client.connect()
        yield client
    except Exception:
        pytest.skip("Servidor OPA não disponível em localhost:8181")
    finally:
        await client.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_opa_ethical_guardrails_allow(opa_client):
    """Testa se política OPA permite decisão segura"""
    input_data = {
        "decision": {
            "decision_type": "PRIORITIZATION",
            "confidence_score": 0.85,
            "risk_assessment": {"risk_score": 0.3, "risk_factors": [], "mitigations": []},
            "decision": {"action": "adjust_priorities", "parameters": {}},
            "context": {
                "resource_saturation": 0.5,
                "critical_incidents": [],
                "sla_violations": [],
                "active_plans": []
            },
            "analysis": {"metrics_snapshot": {"bias_score": 0.1}, "conflict_domains": []},
            "reasoning_summary": "Ajuste de prioridades baseado em contexto"
        }
    }

    result = await opa_client.evaluate_policy(
        policy_path="neuralhive/queen/ethical_guardrails",
        input_data=input_data
    )

    assert result.get("allow") is True
    assert len(result.get("violations", [])) == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_opa_ethical_guardrails_deny_excessive_risk(opa_client):
    """Testa se política OPA nega risco excessivo"""
    input_data = {
        "decision": {
            "decision_type": "REPLANNING",
            "confidence_score": 0.8,
            "risk_assessment": {"risk_score": 0.95, "risk_factors": [], "mitigations": []},
            "decision": {"action": "trigger_replanning", "parameters": {}},
            "context": {
                "resource_saturation": 0.5,
                "critical_incidents": [],
                "sla_violations": [],
                "active_plans": []
            },
            "analysis": {"metrics_snapshot": {}, "conflict_domains": []},
            "reasoning_summary": "Replanning"
        }
    }

    result = await opa_client.evaluate_policy(
        policy_path="neuralhive/queen/ethical_guardrails",
        input_data=input_data
    )

    assert result.get("allow") is False
    violations = result.get("violations", [])
    assert len(violations) > 0
    assert any(v.get("rule") == "excessive_risk" for v in violations)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_opa_ethical_guardrails_deny_low_confidence_critical(opa_client):
    """Testa se política OPA nega decisão crítica com baixa confiança"""
    input_data = {
        "decision": {
            "decision_type": "REPLANNING",
            "confidence_score": 0.5,  # Abaixo de 0.7
            "risk_assessment": {"risk_score": 0.3, "risk_factors": [], "mitigations": []},
            "decision": {"action": "trigger_replanning", "parameters": {}},
            "context": {
                "resource_saturation": 0.5,
                "critical_incidents": [],
                "sla_violations": [],
                "active_plans": []
            },
            "analysis": {"metrics_snapshot": {}, "conflict_domains": []},
            "reasoning_summary": "Test"
        }
    }

    result = await opa_client.evaluate_policy(
        policy_path="neuralhive/queen/ethical_guardrails",
        input_data=input_data
    )

    violations = result.get("violations", [])
    assert any(v.get("rule") == "low_confidence_critical_decision" for v in violations)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_opa_ethical_guardrails_high_risk_warning(opa_client):
    """Testa se política OPA gera warning para risco alto (mas aceitável)"""
    input_data = {
        "decision": {
            "decision_type": "PRIORITIZATION",
            "confidence_score": 0.85,
            "risk_assessment": {"risk_score": 0.75, "risk_factors": [], "mitigations": []},
            "decision": {"action": "adjust_priorities", "parameters": {}},
            "context": {
                "resource_saturation": 0.5,
                "critical_incidents": [],
                "sla_violations": [],
                "active_plans": []
            },
            "analysis": {"metrics_snapshot": {"bias_score": 0.1}, "conflict_domains": []},
            "reasoning_summary": "Ajuste"
        }
    }

    result = await opa_client.evaluate_policy(
        policy_path="neuralhive/queen/ethical_guardrails",
        input_data=input_data
    )

    assert result.get("allow") is True
    warnings = result.get("warnings", [])
    assert any(w.get("rule") == "high_risk_warning" for w in warnings)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_opa_ethical_guardrails_resource_saturation_critical(opa_client):
    """Testa se política OPA detecta saturação crítica de recursos"""
    input_data = {
        "decision": {
            "decision_type": "PRIORITIZATION",
            "confidence_score": 0.85,
            "risk_assessment": {"risk_score": 0.3, "risk_factors": [], "mitigations": []},
            "decision": {"action": "adjust_priorities", "parameters": {}},  # Não é reallocate
            "context": {
                "resource_saturation": 0.97,  # > 95%
                "critical_incidents": [],
                "sla_violations": [],
                "active_plans": []
            },
            "analysis": {"metrics_snapshot": {}, "conflict_domains": []},
            "reasoning_summary": "Test"
        }
    }

    result = await opa_client.evaluate_policy(
        policy_path="neuralhive/queen/ethical_guardrails",
        input_data=input_data
    )

    assert result.get("allow") is False
    violations = result.get("violations", [])
    assert any(v.get("rule") == "resource_saturation_critical" for v in violations)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_opa_ethical_guardrails_resource_saturation_ok_with_reallocation(opa_client):
    """Testa se política OPA permite saturação crítica quando ação é realocação"""
    input_data = {
        "decision": {
            "decision_type": "RESOURCE_REALLOCATION",
            "confidence_score": 0.85,
            "risk_assessment": {"risk_score": 0.3, "risk_factors": [], "mitigations": []},
            "decision": {"action": "reallocate_resources", "parameters": {}},  # É reallocate
            "context": {
                "resource_saturation": 0.97,  # > 95%
                "critical_incidents": [],
                "sla_violations": [],
                "active_plans": []
            },
            "analysis": {"metrics_snapshot": {"bias_score": 0.1}, "conflict_domains": []},
            "reasoning_summary": "Realocação necessária"
        }
    }

    result = await opa_client.evaluate_policy(
        policy_path="neuralhive/queen/ethical_guardrails",
        input_data=input_data
    )

    # Não deve ter violação de resource_saturation_critical
    violations = result.get("violations", [])
    assert not any(v.get("rule") == "resource_saturation_critical" for v in violations)
