"""
Testes para o fix de causa-raiz do allocate_resources quando o Intelligent
Scheduler é desativado por feature flag.

Cobre:
- FIX-1 (gating): com _intelligent_scheduler injetado mas use_intelligent_scheduler=False
  (feature flag OPA enable_intelligent_scheduler=False) e fallback stub OFF, a alocação
  deve degradar graciosamente para o round-robin F2 (em vez de falhar com
  "Intelligent Scheduler falhou ... fallback não está configurado" — o kill-switch).
- FIX-2 (namespace): _get_available_workers usa POD_NAMESPACE em vez do atributo
  inexistente _config.namespace (que levantava AttributeError).
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.activities.ticket_generation import (
    _get_available_workers,
    allocate_resources,
    set_activity_dependencies,
)


@pytest.fixture()
def mock_activity_info():
    """Mock activity.info() para contexto de workflow."""
    with patch("src.activities.ticket_generation.activity") as mock_activity:
        mock_info = MagicMock()
        mock_info.workflow_id = "test-workflow-scheduler-disabled"
        mock_activity.info.return_value = mock_info
        mock_activity.logger = MagicMock()
        yield mock_activity


def _policy_validator_with_scheduler_disabled():
    """Validator OPA que passa mas devolve enable_intelligent_scheduler=False."""
    validator = AsyncMock()
    result = MagicMock()
    result.valid = True
    result.violations = []
    result.warnings = []
    result.policy_decisions = {"feature_flags": {"enable_intelligent_scheduler": False}}
    validator.validate_execution_ticket.return_value = result
    validator.validate_resource_allocation.return_value = result
    return validator


def _registry_client_with_workers():
    """Service Registry que devolve 2 workers saudáveis."""
    registry = AsyncMock()
    registry.discover_agents.return_value = [
        {"agent_id": "worker-001", "agent_type": "WORKER", "status": "HEALTHY"},
        {"agent_id": "worker-002", "agent_type": "WORKER", "status": "HEALTHY"},
    ]
    return registry


def _config_scheduler_off_stub_off():
    """Config tipo produção/staging: stub desabilitado."""
    config = MagicMock()
    config.opa_enabled = True
    config.opa_fail_open = True
    config.environment = "staging"
    config.scheduler_fallback_stub_enabled = False
    config.MONGODB_FAIL_OPEN_EXECUTION_TICKETS = False
    return config


@pytest.mark.asyncio()
async def test_scheduler_disabled_by_flag_degrades_to_round_robin(mock_activity_info):
    """
    FIX-1: scheduler injetado + feature flag OFF + stub OFF → round-robin F2,
    NÃO deve levantar 'fallback não está configurado'.
    """
    scheduler = AsyncMock()  # injetado (truthy), mas não deve ser usado
    ticket = {
        "ticket_id": str(uuid.uuid4()),
        "risk_band": "medium",
        "status": "PENDING",
    }

    set_activity_dependencies(
        kafka_producer=None,
        mongodb_client=None,
        registry_client=_registry_client_with_workers(),
        intelligent_scheduler=scheduler,
        policy_validator=_policy_validator_with_scheduler_disabled(),
        config=_config_scheduler_off_stub_off(),
    )

    result = await allocate_resources(ticket)

    assert "allocation_metadata" in result
    assert result["allocation_metadata"]["allocation_method"] == "round_robin_fallback"
    assert result["allocation_metadata"]["agent_id"] in {"worker-001", "worker-002"}
    # O scheduler estava injetado mas desativado por flag — não deve ter sido chamado
    scheduler.schedule_ticket.assert_not_called()


@pytest.mark.asyncio()
async def test_get_available_workers_uses_pod_namespace(monkeypatch):
    """
    FIX-2: _get_available_workers usa POD_NAMESPACE (não _config.namespace inexistente).
    """
    monkeypatch.setenv("POD_NAMESPACE", "ns-de-teste")
    registry = _registry_client_with_workers()

    # _config sem atributo 'namespace' (igual ao OrchestratorSettings real):
    config = MagicMock(spec=["temporal_namespace", "environment"])

    set_activity_dependencies(
        kafka_producer=None,
        mongodb_client=None,
        registry_client=registry,
        intelligent_scheduler=None,
        policy_validator=None,
        config=config,
    )

    workers = await _get_available_workers()

    assert len(workers) == 2
    called_filters = registry.discover_agents.call_args.kwargs["filters"]
    assert called_filters["namespace"] == "ns-de-teste"
    assert called_filters["status"] == "HEALTHY"
