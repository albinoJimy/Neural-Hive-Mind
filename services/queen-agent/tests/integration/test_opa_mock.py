"""
Testes de integração OPA com mocks (sem servidor real)

Estes testes simulam as respostas do OPA para validar a lógica
de integração sem depender de um servidor externo.
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock

from src.clients.opa_client import OPAClient


@pytest_asyncio.fixture
async def mock_opa_http():
    """Mock do cliente HTTP que simula respostas OPA"""
    # Criar mock response - json() é síncrono em httpx.Response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(
        return_value={"result": {"allow": True, "violations": [], "warnings": []}}
    )

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.aclose = AsyncMock()

    return mock_client


@pytest.mark.asyncio
async def test_opa_client_evaluate_policy_success(mock_opa_http):
    """Testa avaliação de política com sucesso"""
    # Criar cliente e injetar mock HTTP
    client = OPAClient(base_url="http://mock-opa:8181", timeout=5.0)
    client._client = mock_opa_http

    result = await client.evaluate_policy(
        policy_path="neuralhive/queen/ethical_guardrails",
        input_data={
            "decision": {
                "decision_type": "PRIORITIZATION",
                "confidence_score": 0.85,
                "risk_assessment": {"risk_score": 0.3, "risk_factors": [], "mitigations": []},
                "decision": {"action": "adjust_priorities", "parameters": {}},
                "context": {
                    "resource_saturation": 0.5,
                    "critical_incidents": [],
                    "sla_violations": [],
                    "active_plans": [],
                },
                "analysis": {"metrics_snapshot": {"bias_score": 0.1}, "conflict_domains": []},
                "reasoning_summary": "Test decision",
            }
        },
    )

    assert result["allow"] is True
    assert result["violations"] == []
    mock_opa_http.post.assert_called_once()


@pytest.mark.asyncio
async def test_opa_client_evaluate_policy_deny_excessive_risk(mock_opa_http):
    """Testa avaliação que nega por risco excessivo"""
    # Configurar mock para retornar negação
    mock_opa_http.post.return_value.json = MagicMock(
        return_value={
            "result": {
                "allow": False,
                "violations": [
                    {
                        "policy": "ethical_guardrails",
                        "rule": "excessive_risk",
                        "severity": "critical",
                        "msg": "Risk score muito alto: 0.95",
                    }
                ],
                "warnings": [],
            }
        }
    )

    client = OPAClient(base_url="http://mock-opa:8181", timeout=5.0)
    client._client = mock_opa_http

    result = await client.evaluate_policy(
        policy_path="neuralhive/queen/ethical_guardrails",
        input_data={
            "decision": {
                "decision_type": "REPLANNING",
                "confidence_score": 0.8,
                "risk_assessment": {"risk_score": 0.95, "risk_factors": [], "mitigations": []},
                "decision": {"action": "trigger_replanning", "parameters": {}},
                "context": {
                    "resource_saturation": 0.5,
                    "critical_incidents": [],
                    "sla_violations": [],
                    "active_plans": [],
                },
                "analysis": {"metrics_snapshot": {}, "conflict_domains": []},
                "reasoning_summary": "Replanning",
            }
        },
    )

    assert result["allow"] is False
    assert len(result["violations"]) > 0


@pytest.mark.asyncio
async def test_opa_client_not_connected():
    """Testa erro quando cliente não está conectado"""
    client = OPAClient(base_url="http://mock-opa:8181", timeout=5.0)
    # Não chamar connect()

    with pytest.raises(RuntimeError, match="Client not connected"):
        await client.evaluate_policy(policy_path="test", input_data={})


@pytest.mark.asyncio
async def test_opa_client_http_error_handling(mock_opa_http):
    """Testa tratamento de erros HTTP"""
    # Configurar mock para simular erro HTTP
    from httpx import HTTPStatusError

    mock_response = MagicMock()
    mock_response.status_code = 500
    error_response = MagicMock()
    error_response.status_code = 500

    # Criar HTTPStatusError
    http_error = HTTPStatusError("Server error", request=MagicMock(), response=error_response)
    mock_opa_http.post.return_value.raise_for_status.side_effect = http_error

    client = OPAClient(base_url="http://mock-opa:8181", timeout=5.0)
    client._client = mock_opa_http

    result = await client.evaluate_policy(policy_path="test", input_data={})

    # Deve retornar allow=False em caso de erro
    assert result["allow"] is False
    assert "error" in result
