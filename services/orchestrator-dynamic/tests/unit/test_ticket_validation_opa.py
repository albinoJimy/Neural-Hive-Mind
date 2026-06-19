"""
Testes unitários para validate_execution_ticket (validação OPA POR-TICKET).

Cobrem dois bugs confirmados por análise + runtime E2E:

FIX-A: validate_execution_ticket enviava o ticket CRU ao OPA sem normalizar
`priority`, ao contrário de validate_cognitive_plan. Tickets com priority
numérico legado (ex.: 5) disparavam falso-positivo
`sla_enforcement/priority_mismatch_risk_band`. A correção normaliza o ticket
via `_normalize_resource_priority` ANTES de construir o input OPA.

FIX-B: o default de `opa_allowed_capabilities` usava vocabulário CI/CD
(code_generation/deployment/testing/validation) que NÃO correspondia às
capabilities reais emitidas pelo STE e declaradas pelos workers, bloqueando
100% dos planos. O conjunto canónico real deve conter read/analyze/etc.
"""

from unittest.mock import AsyncMock, Mock

import pytest
from src.config.settings import OrchestratorSettings
from src.policies.policy_validator import PolicyValidator

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_config():
    """Config mínima para validate_execution_ticket (todas as 4 políticas)."""
    cfg = Mock()
    cfg.opa_fail_open = False
    cfg.opa_max_concurrent_tickets = 100
    cfg.opa_allowed_capabilities = ["read", "analyze"]
    cfg.opa_resource_limits = {"max_cpu": "4000m", "max_memory": "8Gi"}
    cfg.opa_policy_resource_limits = "neuralhive/orchestrator/resource_limits"
    cfg.opa_policy_sla_enforcement = "neuralhive/orchestrator/sla_enforcement"
    cfg.opa_policy_feature_flags = "neuralhive/orchestrator/feature_flags"
    cfg.opa_policy_security_constraints = "neuralhive/orchestrator/security_constraints"
    # Feature flags
    cfg.opa_intelligent_scheduler_enabled = True
    cfg.opa_burst_capacity_enabled = True
    cfg.opa_burst_threshold = 0.8
    cfg.opa_predictive_allocation_enabled = False
    cfg.opa_auto_scaling_enabled = False
    cfg.opa_scheduler_namespaces = ["production"]
    cfg.opa_premium_tenants = []
    # Security
    cfg.opa_security_enabled = False
    cfg.spiffe_enabled = False
    cfg.spiffe_trust_domain = "example.com"
    cfg.opa_allowed_tenants = []
    cfg.opa_rbac_roles = {}
    cfg.opa_data_residency_regions = {}
    cfg.opa_tenant_rate_limits = {}
    cfg.opa_global_rate_limit = 0
    cfg.opa_default_tenant_rate_limit = 0
    # Redis ausente -> _get_request_count devolve 0
    cfg.redis_cluster_nodes = ""
    return cfg


@pytest.fixture()
def mock_opa_client():
    """OPA client que captura o input recebido e devolve sempre sem violações."""
    client = AsyncMock()
    captured = {"inputs": []}

    async def _batch_evaluate(evaluations):
        results = []
        for policy_path, opa_input in evaluations:
            captured["inputs"].append((policy_path, opa_input))
            results.append({"policy_path": policy_path, "result": {"violations": []}})
        return results

    client.batch_evaluate.side_effect = _batch_evaluate
    client._captured = captured
    return client


# ---------------------------------------------------------------------------
# FIX-A: normalização de priority no ticket
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_validate_execution_ticket_normaliza_priority_no_input_opa(
    mock_config, mock_opa_client
):
    """Ticket com priority=5 -> input OPA com resource.priority == 'NORMAL'."""
    validator = PolicyValidator(opa_client=mock_opa_client, config=mock_config)

    ticket = {
        "ticket_id": "ticket-bug",
        "priority": 5,  # formato numérico legado
        "risk_band": "medium",
        "namespace": "default",
        "required_capabilities": ["read"],
    }

    await validator.validate_execution_ticket(ticket)

    assert mock_opa_client._captured["inputs"]
    for _policy_path, opa_input in mock_opa_client._captured["inputs"]:
        resource = opa_input["input"]["resource"]
        assert resource["priority"] == "NORMAL"
        assert isinstance(resource["priority"], str)


@pytest.mark.asyncio()
async def test_validate_execution_ticket_nao_muta_ticket_original(
    mock_config, mock_opa_client
):
    """A normalização não deve mutar o dict original do ticket."""
    validator = PolicyValidator(opa_client=mock_opa_client, config=mock_config)

    ticket = {
        "ticket_id": "ticket-immutable",
        "priority": 5,
        "risk_band": "medium",
        "namespace": "default",
    }

    await validator.validate_execution_ticket(ticket)

    assert ticket["priority"] == 5


@pytest.mark.asyncio()
async def test_validate_execution_ticket_priority_string_passthrough(
    mock_config, mock_opa_client
):
    """Priority já nomeada faz passthrough sem alteração indevida."""
    validator = PolicyValidator(opa_client=mock_opa_client, config=mock_config)

    ticket = {
        "ticket_id": "ticket-named",
        "priority": "HIGH",
        "risk_band": "high",
        "namespace": "default",
    }

    await validator.validate_execution_ticket(ticket)

    for _policy_path, opa_input in mock_opa_client._captured["inputs"]:
        assert opa_input["input"]["resource"]["priority"] == "HIGH"


# ---------------------------------------------------------------------------
# FIX-B: conjunto canónico de capabilities permitidas
# ---------------------------------------------------------------------------


CANONICAL_CAPABILITIES = {
    "read",
    "write",
    "compute",
    "analyze",
    "transform",
    "test",
    "code",
    "security",
    "scan",
    "compliance",
    "deploy",
}

# Vocabulário CI/CD stale que NÃO deve mais ser o default
STALE_CICD_CAPABILITIES = {
    "code_generation",
    "deployment",
    "testing",
    "validation",
}


@pytest.fixture()
def orchestrator_settings(monkeypatch):
    """Instancia OrchestratorSettings com os campos obrigatórios mínimos.

    Foca apenas o default de opa_allowed_capabilities (FIX-B); os restantes
    campos são preenchidos só para satisfazer a validação pydantic.
    """
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    monkeypatch.setenv("POSTGRES_HOST", "localhost")
    monkeypatch.setenv("POSTGRES_USER", "user")
    monkeypatch.setenv("POSTGRES_PASSWORD", "pass")
    monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
    monkeypatch.setenv("REDIS_CLUSTER_NODES", "localhost:6379")
    return OrchestratorSettings()


def test_opa_allowed_capabilities_default_contem_conjunto_canonico(
    orchestrator_settings,
):
    """O default deve conter o conjunto canónico real (read, analyze, etc.)."""
    allowed = set(orchestrator_settings.opa_allowed_capabilities)

    # Casos centrais do bug
    assert "analyze" in allowed
    assert "read" in allowed

    # Conjunto canónico completo presente
    assert CANONICAL_CAPABILITIES.issubset(allowed), (
        f"Faltam capabilities canónicas: " f"{CANONICAL_CAPABILITIES - allowed}"
    )


def test_opa_allowed_capabilities_default_nao_e_so_vocabulario_cicd(
    orchestrator_settings,
):
    """O default não deve ser o vocabulário CI/CD stale (que bloqueava tudo)."""
    allowed = set(orchestrator_settings.opa_allowed_capabilities)

    # Não pode ser exatamente o conjunto antigo
    assert allowed != STALE_CICD_CAPABILITIES
