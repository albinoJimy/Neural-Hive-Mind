"""Testes da validação real por domínio (OPA) — Task 6 caminho-real-first-class.

Cobre 4 caminhos:
1. Caminho real por domínio: opa_client devolve result={allow,violations}.
2. policy_undefined fail-closed para domínio EXIGIDO; fail-open marcado para
   path NÃO-exigido.
3. SAST timeout → FAILED (simulated=False).
4. Sem fallback simulado: validation_type desconhecido / sem ferramenta →
   FAILED (nunca success=True + simulated=True).
"""

import subprocess
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from clients.opa_client import (
    OPAClient,
    PolicyEvaluationRequest,
    PolicyEvaluationResponse,
    Violation,
    ViolationSeverity,
)
from executors.validate_executor import ValidateExecutor


def _config(trivy_enabled=False):
    config = MagicMock()
    config.opa_enabled = True
    config.opa_url = "http://opa.neural-hive.svc.cluster.local:8181"
    config.trivy_enabled = trivy_enabled
    config.trivy_timeout_seconds = 5
    config.sonarqube_enabled = False
    config.snyk_enabled = False
    config.checkov_enabled = False
    return config


def _opa_client(response=None):
    client = MagicMock()
    client.evaluate_policy = AsyncMock(
        return_value=response or PolicyEvaluationResponse(allow=True, violations=[], metadata={})
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


def _domain_ticket(policy_path, validation_type="policy"):
    tid = str(uuid.uuid4())
    return {
        "ticket_id": tid,
        "task_id": f"task-{tid[:8]}",
        "task_type": "VALIDATE",
        "security_level": "internal",
        "is_destructive": False,
        "risk_band": "medium",
        "parameters": {
            "validation_type": validation_type,
            "policy_path": policy_path,
            "subject": "componente alvo",
        },
    }


class TestRealDomainPath:
    """Caminho real: a política de domínio avalia e devolve allow/violations."""

    @pytest.mark.asyncio()
    async def test_architecture_allow(self):
        opa = _opa_client(PolicyEvaluationResponse(allow=True, violations=[], metadata={}))
        executor = ValidateExecutor(config=_config(), metrics=MagicMock(), opa_client=opa)

        result = await executor._execute_internal(
            _domain_ticket("/neural_hive/architecture/compliance"), span=MagicMock()
        )

        assert result["success"] is True
        assert result["output"]["validation_passed"] is True
        # Decisão real (não policy_undefined): client_type dedicated, sem simulação
        assert result["metadata"]["client_type"] == "dedicated"
        assert result["metadata"]["simulated"] is False

    @pytest.mark.asyncio()
    async def test_quality_deny_with_violations(self):
        violations = [
            Violation(
                rule_id="quality_score_below_threshold",
                message="score baixo",
                severity=ViolationSeverity.HIGH,
            )
        ]
        opa = _opa_client(PolicyEvaluationResponse(allow=False, violations=violations, metadata={}))
        opa.count_violations_by_severity.return_value = {
            ViolationSeverity.CRITICAL: 0,
            ViolationSeverity.HIGH: 1,
            ViolationSeverity.MEDIUM: 0,
            ViolationSeverity.LOW: 0,
            ViolationSeverity.INFO: 0,
        }
        executor = ValidateExecutor(config=_config(), metrics=MagicMock(), opa_client=opa)

        result = await executor._execute_internal(
            _domain_ticket("/neural_hive/quality/standards"), span=MagicMock()
        )

        assert result["success"] is False
        assert result["output"]["validation_passed"] is False
        assert len(result["output"]["violations"]) == 1
        assert result["output"]["violations"][0]["rule_id"] == "quality_score_below_threshold"


class TestPolicyUndefinedFailClosed:
    """policy_undefined: fail-closed p/ domínio exigido; fail-open p/ não-exigido."""

    @pytest.mark.asyncio()
    async def test_required_domain_undefined_is_fail_closed(self):
        # opa_client REAL com prefixos exigidos; OPA responde sem "result".
        client = OPAClient(
            base_url="http://opa.test:8181",
            required_policy_prefixes=["neural_hive/architecture"],
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"decision_id": "abc-123"}  # sem result
        mock_response.raise_for_status = MagicMock()

        with patch.object(client.client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            resp = await client.evaluate_policy(
                PolicyEvaluationRequest(
                    policy_path="/neural_hive/architecture/compliance", input_data={}
                )
            )

        # Domínio exigido + undefined -> fail-closed
        assert resp.allow is False
        assert resp.metadata.get("policy_required") is True
        assert any(v.rule_id == "policy_required_but_undefined" for v in resp.violations)

    @pytest.mark.asyncio()
    async def test_non_required_domain_undefined_is_fail_open_marked(self):
        client = OPAClient(
            base_url="http://opa.test:8181",
            required_policy_prefixes=["neural_hive/architecture"],
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"decision_id": "abc-123"}  # sem result
        mock_response.raise_for_status = MagicMock()

        with patch.object(client.client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            resp = await client.evaluate_policy(
                PolicyEvaluationRequest(policy_path="policy/allow", input_data={})
            )

        # Domínio NÃO exigido + undefined -> fail-open marcado (degradação)
        assert resp.allow is True
        assert resp.metadata.get("policy_undefined") is True
        assert resp.metadata.get("degraded") is True
        assert resp.metadata.get("policy_required") is None

    @pytest.mark.asyncio()
    async def test_required_domain_undefined_propagates_to_executor_failed(self):
        """Integração: undefined de domínio exigido -> executor devolve FAILED."""
        client = OPAClient(
            base_url="http://opa.test:8181",
            required_policy_prefixes=["neural_hive/operational"],
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"decision_id": "abc-123"}
        mock_response.raise_for_status = MagicMock()

        executor = ValidateExecutor(config=_config(), metrics=MagicMock(), opa_client=client)

        with patch.object(client.client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            result = await executor._execute_internal(
                _domain_ticket("/neural_hive/operational/procedures"), span=MagicMock()
            )

        assert result["success"] is False
        assert result["output"]["validation_passed"] is False
        assert result["metadata"]["simulated"] is False


class TestSastTimeoutFailed:
    """SAST timeout/error -> FAILED, nunca success simulado."""

    @pytest.mark.asyncio()
    async def test_sast_timeout_is_failed(self):
        executor = ValidateExecutor(
            config=_config(trivy_enabled=True), metrics=MagicMock(), opa_client=None
        )
        tid = str(uuid.uuid4())
        ticket = {
            "ticket_id": tid,
            "task_id": f"task-{tid[:8]}",
            "task_type": "VALIDATE",
            "parameters": {"validation_type": "sast", "working_dir": "."},
        }

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="trivy", timeout=5)):
            result = await executor._execute_internal(ticket, span=MagicMock())

        assert result["success"] is False
        assert result["output"]["validation_passed"] is False
        assert result["metadata"]["simulated"] is False
        assert result["metadata"]["failure_reason"] == "sast_timeout"

    @pytest.mark.asyncio()
    async def test_sast_error_is_failed(self):
        executor = ValidateExecutor(
            config=_config(trivy_enabled=True), metrics=MagicMock(), opa_client=None
        )
        tid = str(uuid.uuid4())
        ticket = {
            "ticket_id": tid,
            "task_id": f"task-{tid[:8]}",
            "task_type": "VALIDATE",
            "parameters": {"validation_type": "sast", "working_dir": "."},
        }

        with patch("subprocess.run", side_effect=OSError("trivy not found")):
            result = await executor._execute_internal(ticket, span=MagicMock())

        assert result["success"] is False
        assert result["output"]["validation_passed"] is False
        assert result["metadata"]["simulated"] is False
        assert result["metadata"]["failure_reason"] == "sast_error"


class TestNoSimulatedFallback:
    """validation_type desconhecido / sem ferramenta -> FAILED, nunca simulado."""

    @pytest.mark.asyncio()
    async def test_unknown_validation_type_is_failed_not_simulated(self):
        # opa desabilitado e sem ferramentas -> sem caminho real disponível
        config = _config()
        config.opa_enabled = False
        executor = ValidateExecutor(config=config, metrics=MagicMock(), opa_client=None)
        tid = str(uuid.uuid4())
        ticket = {
            "ticket_id": tid,
            "task_id": f"task-{tid[:8]}",
            "task_type": "VALIDATE",
            "parameters": {"validation_type": "desconhecido"},
        }

        result = await executor._execute_internal(ticket, span=MagicMock())

        # NUNCA success simulado
        assert result["success"] is False
        assert result["output"]["validation_passed"] is False
        assert result["metadata"]["simulated"] is False
        assert result["metadata"]["failure_reason"] == "no_validation_path_available"

    @pytest.mark.asyncio()
    async def test_no_path_never_returns_passed_and_simulated(self):
        """Garante que nenhum caminho devolve validation_passed=True + simulated=True."""
        config = _config()
        config.opa_enabled = False
        executor = ValidateExecutor(config=config, metrics=MagicMock(), opa_client=None)
        tid = str(uuid.uuid4())
        ticket = {
            "ticket_id": tid,
            "task_id": f"task-{tid[:8]}",
            "task_type": "VALIDATE",
            "parameters": {"validation_type": "policy"},
        }

        result = await executor._execute_internal(ticket, span=MagicMock())

        passed = result["output"]["validation_passed"]
        simulated = result["metadata"].get("simulated")
        assert not (passed is True and simulated is True)
