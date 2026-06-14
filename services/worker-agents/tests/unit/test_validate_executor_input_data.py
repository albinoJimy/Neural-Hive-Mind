"""Teste do fix do input_data=None no ValidateExecutor.

O STE deixa input_data=None no template (a popular pelo executor). Antes,
parameters.get("input_data", {}) devolvia None (chave presente com None), e
construir PolicyEvaluationRequest(input_data=None) crashava (Pydantic exige
dict) -> fallback conservador -> task VALIDATE FAILED -> cascata de dependentes.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from clients.opa_client import PolicyEvaluationResponse, ViolationSeverity
from executors.validate_executor import ValidateExecutor


def _config():
    config = MagicMock()
    config.opa_enabled = True
    config.opa_url = "http://opa.neural-hive.svc.cluster.local:8181"
    config.trivy_enabled = False
    config.sonarqube_enabled = False
    config.snyk_enabled = False
    config.checkov_enabled = False
    return config


def _opa_client(allow=True):
    client = MagicMock()
    client.evaluate_policy = AsyncMock(
        return_value=PolicyEvaluationResponse(allow=allow, violations=[], metadata={})
    )
    client.count_violations_by_severity = MagicMock(
        return_value={
            ViolationSeverity.CRITICAL: 0,
            ViolationSeverity.HIGH: 0,
            ViolationSeverity.MEDIUM: 0,
            ViolationSeverity.LOW: 0,
            ViolationSeverity.INFO: 0,
        }
    )
    return client


def _ticket_with_none_input_data():
    _tid = str(uuid.uuid4())
    return {
        "ticket_id": _tid,
        "task_id": f"task-{_tid[:8]}",
        "task_type": "VALIDATE",
        "security_level": "confidential",
        "is_destructive": False,
        "risk_band": "medium",
        "parameters": {
            "validation_type": "policy",
            "policy_path": "/neural_hive/security/validation",
            "input_data": None,  # o caso do bug
            "target": "OAuth2 com MFA",
            "subject": "migração técnica",
            "entities": ["OAuth2", "MFA"],
        },
    }


@pytest.mark.asyncio()
async def test_input_data_none_coerced_to_dict_and_passes():
    """input_data=None não deve crashar; é coergido para dict e a validação passa."""
    opa = _opa_client(allow=True)
    executor = ValidateExecutor(config=_config(), metrics=MagicMock(), opa_client=opa)

    result = await executor._execute_internal(_ticket_with_none_input_data(), span=MagicMock())

    # Não caiu no fallback conservador (que daria success=False)
    assert result["success"] is True
    # O PolicyEvaluationRequest recebeu input_data como dict (não None)
    request = opa.evaluate_policy.call_args.args[0]
    assert isinstance(request.input_data, dict)
    # Enriquecido com o contexto de segurança do ticket
    assert request.input_data.get("target") == "OAuth2 com MFA"
    assert request.input_data.get("security_level") == "confidential"


@pytest.mark.asyncio()
async def test_input_data_none_does_not_trigger_pydantic_fallback_failure():
    """Sem o fix, input_data=None crashava e devolvia success=False (conservador)."""
    opa = _opa_client(allow=True)
    executor = ValidateExecutor(config=_config(), metrics=MagicMock(), opa_client=opa)

    result = await executor._execute_internal(_ticket_with_none_input_data(), span=MagicMock())

    # evaluate_policy foi de facto chamado (não houve crash antes do OPA)
    opa.evaluate_policy.assert_awaited_once()
    assert result["success"] is True
