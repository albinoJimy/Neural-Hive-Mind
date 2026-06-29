"""Testes do routing via capacidade MIGRATE no Decision Consumer (Fase 1 / Task 2).

Spec: docs/specs/2026-06-29-gate-j4-migrate-fiavel — espelha EXATAMENTE o padrão
GENERATE (Task 3 da spec extrair-capacidade-generate).

A fronteira deixa de estar vazada: o consumer decide "requer migração" pela
SEMÂNTICA da jornada (J4_MIGRATE) — não por conhecer a classe do workflow — e,
quando o plano traz um ``migration_config`` explícito, inicia o
``DataMigrationWorkflow`` durável (des-orfanizando-o), em vez de cair na
``OrchestrationWorkflow`` genérica de J2. Preservado:

    - J2_ORCHESTRATE             -> OrchestrationWorkflow (caminho legado);
    - J3_BUILD                   -> GenerateCapability (inalterado);
    - sem journey (default)      -> OrchestrationWorkflow (fallback compat);
    - J4 SEM migration_config    -> OrchestrationWorkflow (compat: sem spec de
      migração não há o que migrar — a capacidade ativa-se com spec presente).

Anti-verde-falso: ``migration_config`` PRESENTE mas inválido (sem
``legacy_connection_id`` ou ``tables`` vazias) → NÃO inicia o
``DataMigrationWorkflow`` e NÃO cai na orquestração genérica; erro permanente
(commit do offset, sem retry infinito). Sem defaults silenciosos.
"""

from unittest.mock import AsyncMock, Mock

import pytest
from src.consumers.decision_consumer import (
    DecisionConsumer,
    InvalidMigrationConfigError,
    _extract_migration_config,
    _journey_requires_migration,
    _requires_migration,
)
from src.workflows.data_migration_workflow import DataMigrationWorkflow
from src.workflows.orchestration_workflow import OrchestrationWorkflow

from tests.integration.j4_migrate_fixture import (
    MIGRATION_TABLES,
    build_j4_migrate_plan_message,
)

# =============================================================================
# Helpers module-level (isolados)
# =============================================================================


class TestJourneyRequiresMigration:
    """A decisão deriva da semântica da jornada (hoje só J4_MIGRATE)."""

    def test_j4_migrate_requires_migration(self):
        assert _journey_requires_migration("J4_MIGRATE") is True

    def test_other_journeys_do_not_require_migration(self):
        for journey in ("J1_PLAN_ONLY", "J2_ORCHESTRATE", "J3_BUILD", "UNKNOWN", ""):
            assert _journey_requires_migration(journey) is False


class TestRequiresMigration:
    """Autoridade única partilhada por consumer e resume (não devem divergir)."""

    def test_j4_migrate_by_journey(self):
        # journey J4_MIGRATE requer migração independentemente do workflow_type.
        assert _requires_migration("J4_MIGRATE", "orchestration") is True

    def test_plan_only_never_requires_migration(self):
        # Espelha o guard plan-only de _requires_generate_capability.
        assert _requires_migration("J1_PLAN_ONLY", "orchestration") is False

    def test_other_journeys_are_not_migration(self):
        for journey in ("J2_ORCHESTRATE", "J3_BUILD", "UNKNOWN", ""):
            assert _requires_migration(journey, "orchestration") is False


class TestExtractMigrationConfig:
    """Extração fail-closed do migration_config (sem defaults silenciosos)."""

    def test_valid_config_from_harness_message(self):
        """Consistência harness<->consumer: a mensagem do harness é aceite."""
        plan = build_j4_migrate_plan_message()
        config = _extract_migration_config(plan)
        assert config["legacy_connection_id"] == "postgres-legacy"
        assert config["tables"] == MIGRATION_TABLES

    def test_absent_migration_config_raises(self):
        with pytest.raises(InvalidMigrationConfigError):
            _extract_migration_config({})

    def test_empty_migration_config_raises(self):
        with pytest.raises(InvalidMigrationConfigError):
            _extract_migration_config({"migration_config": {}})

    def test_missing_legacy_connection_id_raises(self):
        with pytest.raises(InvalidMigrationConfigError):
            _extract_migration_config({"migration_config": {"tables": ["users"]}})

    def test_empty_tables_raises(self):
        with pytest.raises(InvalidMigrationConfigError):
            _extract_migration_config(
                {"migration_config": {"legacy_connection_id": "x", "tables": []}}
            )

    def test_whitespace_tables_are_ignored_and_raise(self):
        """Tabelas só-com-espaços não contam: lista efetivamente vazia → erro."""
        with pytest.raises(InvalidMigrationConfigError):
            _extract_migration_config(
                {
                    "migration_config": {
                        "legacy_connection_id": "x",
                        "tables": ["  ", "\t"],
                    }
                }
            )

    def test_valid_minimal_config_returns_normalized(self):
        config = _extract_migration_config(
            {
                "migration_config": {
                    "legacy_connection_id": "  pg  ",
                    "tables": [" users "],
                }
            }
        )
        assert config["legacy_connection_id"] == "pg"
        assert config["tables"] == ["users"]
        assert config["schema"] == "public"


# =============================================================================
# Harness do handler _process_message (caminho direct-plan; bypassa Mongo)
# =============================================================================


def _make_consumer() -> DecisionConsumer:
    config = Mock()
    config.temporal_workflow_id_prefix = "workflow-"
    config.temporal_task_queue = "q"
    config.ml_drift_check_enabled = False

    consumer = DecisionConsumer(config, AsyncMock(), AsyncMock(), AsyncMock())
    consumer.consumer = AsyncMock()
    consumer._check_ml_drift = AsyncMock(return_value=None)
    consumer._is_duplicate_decision = AsyncMock(return_value=False)
    consumer._mark_decision_processed = AsyncMock()
    consumer.generate_capability = AsyncMock()
    return consumer


def _wrap(plan: dict):
    return Mock(headers=[], value=plan, topic="t", partition=0, offset=1)


def _make_simple_message(journey: str | None = None, workflow_type: str | None = None):
    """Mensagem mínima (sem migration_config) — espelha o harness de generate."""
    plan: dict = {
        "plan_id": "p1",
        "tasks": [{"task_id": "t1"}],
        "execution_order": ["t1"],
        "risk_band": "low",
    }
    if journey is not None:
        plan["journey"] = journey
    if workflow_type is not None:
        plan["workflow_type"] = workflow_type
    return _wrap(plan)


@pytest.mark.asyncio()
async def test_j4_migrate_with_config_invokes_data_migration_workflow():
    """J4 + migration_config válido -> start_workflow(DataMigrationWorkflow.run, ...)."""
    consumer = _make_consumer()
    plan = build_j4_migrate_plan_message()

    await consumer._process_message(_wrap(plan))

    consumer.generate_capability.start.assert_not_called()
    consumer.temporal_client.start_workflow.assert_awaited_once()
    args = consumer.temporal_client.start_workflow.call_args.args
    assert args[0] == DataMigrationWorkflow.run
    migration_input = args[1]
    assert migration_input["migration_config"]["tables"] == MIGRATION_TABLES
    assert (
        migration_input["migration_config"]["legacy_connection_id"] == "postgres-legacy"
    )
    consumer.consumer.commit.assert_awaited()


@pytest.mark.asyncio()
async def test_j4_migrate_invalid_config_does_not_start_migration():
    """Anti-verde-falso: migration_config presente mas inválido (tables vazias) ->
    NÃO inicia DataMigrationWorkflow nem OrchestrationWorkflow; commit feito."""
    consumer = _make_consumer()
    plan = build_j4_migrate_plan_message(tables=[])

    await consumer._process_message(_wrap(plan))

    consumer.generate_capability.start.assert_not_called()
    consumer.temporal_client.start_workflow.assert_not_called()
    consumer.consumer.commit.assert_awaited()


@pytest.mark.asyncio()
async def test_j4_migrate_missing_legacy_id_does_not_start_migration():
    """Anti-verde-falso: legacy_connection_id vazio -> fail-closed (sem start)."""
    consumer = _make_consumer()
    plan = build_j4_migrate_plan_message(legacy_connection_id="")

    await consumer._process_message(_wrap(plan))

    consumer.temporal_client.start_workflow.assert_not_called()
    consumer.consumer.commit.assert_awaited()


@pytest.mark.asyncio()
async def test_j4_migrate_without_config_falls_back_to_orchestration():
    """J4 SEM migration_config -> OrchestrationWorkflow (compat legado)."""
    consumer = _make_consumer()

    await consumer._process_message(_make_simple_message(journey="J4_MIGRATE"))

    consumer.generate_capability.start.assert_not_called()
    consumer.temporal_client.start_workflow.assert_awaited_once()
    assert (
        consumer.temporal_client.start_workflow.call_args.args[0]
        == OrchestrationWorkflow.run
    )


# =============================================================================
# Zero regressão — J2 / J3 / sem-journey inalterados
# =============================================================================


@pytest.mark.asyncio()
async def test_j2_orchestrate_still_uses_orchestration_workflow():
    """J2_ORCHESTRATE -> OrchestrationWorkflow (inalterado pela introdução de MIGRATE)."""
    consumer = _make_consumer()

    await consumer._process_message(_make_simple_message(journey="J2_ORCHESTRATE"))

    consumer.generate_capability.start.assert_not_called()
    consumer.temporal_client.start_workflow.assert_awaited_once()
    assert (
        consumer.temporal_client.start_workflow.call_args.args[0]
        == OrchestrationWorkflow.run
    )


@pytest.mark.asyncio()
async def test_j3_build_still_invokes_generate_capability():
    """J3_BUILD -> GenerateCapability (inalterado); DataMigrationWorkflow NÃO iniciado."""
    from src.capabilities.generate.capability import GenerateHandle

    consumer = _make_consumer()
    consumer.generate_capability.start = AsyncMock(
        return_value=GenerateHandle(workflow_id="workflow-p1", journey="J3_BUILD")
    )

    await consumer._process_message(_make_simple_message(journey="J3_BUILD"))

    consumer.generate_capability.start.assert_awaited_once()
    consumer.temporal_client.start_workflow.assert_not_called()


@pytest.mark.asyncio()
async def test_no_journey_still_defaults_to_orchestration():
    """sem journey (default) -> OrchestrationWorkflow.run (fallback compat)."""
    consumer = _make_consumer()

    await consumer._process_message(_make_simple_message())

    consumer.generate_capability.start.assert_not_called()
    consumer.temporal_client.start_workflow.assert_awaited_once()
    assert (
        consumer.temporal_client.start_workflow.call_args.args[0]
        == OrchestrationWorkflow.run
    )
