"""
Testes unitários para a normalização de `priority` numérica legada antes do OPA.

Cobre o bug confirmado por runtime E2E: planos cognitivos com `priority` em
formato numérico legado (ex.: 5) eram enviados crus ao OPA, gerando falso-positivo
de violação `priority_mismatch_risk_band` (o Rego compara contra prioridades
NOMEADAS: medium -> ["CRITICAL", "HIGH", "NORMAL"]).

A correção normaliza `priority` numérico->nomeado (1-2 LOW, 3-5 NORMAL,
6-8 HIGH, 9-10 CRITICAL) ANTES de construir o input OPA, reutilizando o helper
canónico `normalize_priority` (DRY, partilhado com o field_validator de Priority).
"""

from unittest.mock import AsyncMock, Mock

import pytest
from src.models.execution_ticket import Priority, normalize_priority
from src.policies.policy_validator import PolicyValidator


# ---------------------------------------------------------------------------
# Testes do helper canónico normalize_priority
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        (1, Priority.LOW),
        (2, Priority.LOW),
        (3, Priority.NORMAL),
        (5, Priority.NORMAL),  # caso central do bug
        (6, Priority.HIGH),
        (8, Priority.HIGH),
        (9, Priority.CRITICAL),
        (10, Priority.CRITICAL),
    ],
)
def test_normalize_priority_numerico_mapeia_para_nomeado(value, expected):
    assert normalize_priority(value) == expected


def test_normalize_priority_caso_bug_5_para_normal():
    """O caso exato do bug: priority=5 -> NORMAL (permitido para risk_band=medium)."""
    result = normalize_priority(5)
    assert result == Priority.NORMAL
    assert result.value == "NORMAL"


@pytest.mark.parametrize(
    "value,expected",
    [
        (0, Priority.LOW),  # clamp inferior (<1)
        (-3, Priority.LOW),  # clamp inferior
        (11, Priority.CRITICAL),  # clamp superior (>10)
        (999, Priority.CRITICAL),  # clamp superior
    ],
)
def test_normalize_priority_fora_de_intervalo_sofre_clamp(value, expected):
    assert normalize_priority(value) == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        ("LOW", Priority.LOW),
        ("NORMAL", Priority.NORMAL),
        ("HIGH", Priority.HIGH),
        ("CRITICAL", Priority.CRITICAL),
        ("normal", Priority.NORMAL),  # case-insensitive passthrough
        ("high", Priority.HIGH),
    ],
)
def test_normalize_priority_string_nomeada_passthrough(value, expected):
    assert normalize_priority(value) == expected


def test_normalize_priority_string_invalida_levanta_valueerror():
    with pytest.raises(ValueError):
        normalize_priority("URGENTISSIMO")


def test_normalize_priority_enum_passthrough():
    assert normalize_priority(Priority.HIGH) == Priority.HIGH


# ---------------------------------------------------------------------------
# Fixtures para PolicyValidator
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_config():
    cfg = Mock()
    cfg.opa_fail_open = False
    cfg.opa_max_concurrent_tickets = 100
    cfg.opa_allowed_capabilities = ["code_generation"]
    cfg.opa_resource_limits = {"max_cpu": "4000m", "max_memory": "8Gi"}
    cfg.opa_policy_resource_limits = "neuralhive/orchestrator/resource_limits"
    cfg.opa_policy_sla_enforcement = "neuralhive/orchestrator/sla_enforcement"
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
# Testes de integração leve (validate_cognitive_plan + opa_client mockado)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_cognitive_plan_normaliza_priority_no_input_opa(
    mock_config, mock_opa_client
):
    """O input OPA construído deve conter priority NOMEADA (não o int legado)."""
    validator = PolicyValidator(opa_client=mock_opa_client, config=mock_config)

    plan = {
        "plan_id": "plan-bug",
        "priority": 5,  # formato numérico legado
        "risk_band": "medium",
        "tasks": [],
    }

    await validator.validate_cognitive_plan(plan)

    # Pelo menos um input deve ter sido enviado ao OPA
    assert mock_opa_client._captured["inputs"]
    for _policy_path, opa_input in mock_opa_client._captured["inputs"]:
        resource = opa_input["input"]["resource"]
        assert resource["priority"] == "NORMAL"
        # tipo string (forma nomeada), nunca o int cru
        assert isinstance(resource["priority"], str)


@pytest.mark.asyncio
async def test_validate_cognitive_plan_nao_muta_plano_original(
    mock_config, mock_opa_client
):
    """A normalização não deve mutar o dict original recebido."""
    validator = PolicyValidator(opa_client=mock_opa_client, config=mock_config)

    plan = {
        "plan_id": "plan-immutable",
        "priority": 5,
        "risk_band": "medium",
        "tasks": [],
    }

    await validator.validate_cognitive_plan(plan)

    # O original mantém o valor numérico intacto
    assert plan["priority"] == 5


@pytest.mark.asyncio
async def test_validate_cognitive_plan_priority_string_passa_inalterada(
    mock_config, mock_opa_client
):
    """Priority já nomeada faz passthrough sem alteração indevida."""
    validator = PolicyValidator(opa_client=mock_opa_client, config=mock_config)

    plan = {
        "plan_id": "plan-named",
        "priority": "HIGH",
        "risk_band": "high",
        "tasks": [],
    }

    await validator.validate_cognitive_plan(plan)

    for _policy_path, opa_input in mock_opa_client._captured["inputs"]:
        assert opa_input["input"]["resource"]["priority"] == "HIGH"


@pytest.mark.asyncio
async def test_validate_cognitive_plan_priority_ausente_nao_falha(
    mock_config, mock_opa_client
):
    """Plano sem priority não deve falhar nem inventar campo."""
    validator = PolicyValidator(opa_client=mock_opa_client, config=mock_config)

    plan = {
        "plan_id": "plan-no-priority",
        "risk_band": "low",
        "tasks": [],
    }

    result = await validator.validate_cognitive_plan(plan)

    assert result.valid is True
    for _policy_path, opa_input in mock_opa_client._captured["inputs"]:
        assert "priority" not in opa_input["input"]["resource"]


def test_normalize_resource_priority_helper_clamp(mock_config, mock_opa_client):
    """O helper _normalize_resource_priority faz clamp e devolve cópia (não muta)."""
    validator = PolicyValidator(opa_client=mock_opa_client, config=mock_config)

    original = {"priority": 999, "risk_band": "critical"}
    normalized = validator._normalize_resource_priority(original)

    assert normalized["priority"] == "CRITICAL"
    # original preservado
    assert original["priority"] == 999
    assert normalized is not original
