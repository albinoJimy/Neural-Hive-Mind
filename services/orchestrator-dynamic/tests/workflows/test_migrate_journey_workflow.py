"""Testes do MigrateJourneyWorkflow (Fase 3 / Task 4).

Spec: docs/specs/2026-06-29-gate-j4-migrate-fiavel — compõe a jornada J4_MIGRATE
encadeando GENERATE (condicional) → MIGRATE via child-workflows.

Cobertura:
- Funções puras (decisão/derivação): ``_journey_needs_generation``,
  ``build_generate_child_input``, ``build_migrate_child_input`` (incl. dependência
  de dados GENERATE→destino).
- Workflow (mock de ``workflow.execute_child_workflow``, espelha o padrão de
  ``test_fluxo_g_workflow.py``):
    * requires_generation → FluxoG child ANTES de DataMigration child (ordem);
    * sem sinal → salta GENERATE, só DataMigration;
    * GENERATE falha → NÃO executa MIGRATE (fail-closed).
"""

from unittest.mock import MagicMock, patch

import pytest
from src.workflows.data_migration_workflow import DataMigrationWorkflow
from src.workflows.fluxo_g_workflow import FluxoGWorkflow
from src.workflows.migrate_journey_workflow import (
    MigrateJourneyWorkflow,
    _journey_needs_generation,
    build_generate_child_input,
    build_migrate_child_input,
)


def _plan(*, generate_target=None, modern="postgres-modern", **extra) -> dict:
    """Cognitive Plan J4 mínimo (com migration_config)."""
    plan: dict = {
        "plan_id": "p-j4",
        "journey": "J4_MIGRATE",
        "migration_config": {
            "legacy_connection_id": "postgres-legacy",
            "modern_connection_id": modern,
            "schema": "public",
            "tables": ["users", "orders"],
        },
    }
    if generate_target is not None:
        plan["generate_target"] = generate_target
    plan.update(extra)
    return plan


# =============================================================================
# Funções puras
# =============================================================================


class TestJourneyNeedsGeneration:
    """A geração é condicional: deriva do sinal ``generate_target`` no plano."""

    def test_generate_target_present_needs_generation(self):
        assert (
            _journey_needs_generation(_plan(generate_target={"language": "python"}))
            is True
        )

    def test_absent_generate_target_does_not_need_generation(self):
        assert _journey_needs_generation(_plan()) is False

    def test_empty_generate_target_does_not_need_generation(self):
        assert _journey_needs_generation(_plan(generate_target={})) is False


class TestBuildGenerateChildInput:
    """Input do child FluxoGWorkflow (contrato cognitive_plan/original_intent/skip_approvals)."""

    def test_carries_cognitive_plan_and_defaults(self):
        plan = _plan(generate_target={"language": "python"})
        child = build_generate_child_input(plan)
        assert child["cognitive_plan"] is plan
        assert child["skip_approvals"] is True
        assert child["original_intent"] is None

    def test_respects_explicit_intent_and_skip(self):
        plan = _plan(
            generate_target={"language": "go"},
            original_intent="migrar loja legada",
            skip_approvals=False,
        )
        child = build_generate_child_input(plan)
        assert child["original_intent"] == "migrar loja legada"
        assert child["skip_approvals"] is False


class TestBuildMigrateChildInput:
    """Input do child DataMigrationWorkflow + dependência GENERATE→destino."""

    def test_without_generate_uses_plan_modern_connection(self):
        plan = _plan(modern="postgres-modern")
        child = build_migrate_child_input(plan, generate_result=None)
        assert child["migration_config"]["legacy_connection_id"] == "postgres-legacy"
        assert child["migration_config"]["modern_connection_id"] == "postgres-modern"
        assert child["migration_config"]["tables"] == ["users", "orders"]
        assert child["job_id"] is None
        assert child["initial_phase"] == "pending"

    def test_generate_result_overrides_modern_connection(self):
        """O destino realmente deployado pelo GENERATE substitui o do plano."""
        plan = _plan(modern="postgres-modern")
        generate_result = {
            "status": "completed",
            "deployment": {"service_url": "http://modern-svc.nhm.local"},
        }
        child = build_migrate_child_input(plan, generate_result)
        assert (
            child["migration_config"]["modern_connection_id"]
            == "http://modern-svc.nhm.local"
        )

    def test_generate_result_without_service_url_keeps_plan_modern(self):
        plan = _plan(modern="postgres-modern")
        generate_result = {"status": "completed", "deployment": {}}
        child = build_migrate_child_input(plan, generate_result)
        assert child["migration_config"]["modern_connection_id"] == "postgres-modern"

    def test_does_not_mutate_plan_config(self):
        plan = _plan(modern="postgres-modern")
        build_migrate_child_input(
            plan, {"status": "completed", "deployment": {"service_url": "http://x"}}
        )
        # O config do plano original não é mutado (cópia defensiva).
        assert plan["migration_config"]["modern_connection_id"] == "postgres-modern"


# =============================================================================
# Workflow — orquestração durável (child-workflows mockados)
# =============================================================================


def _patched_workflow():
    """Context manager que patcha o módulo ``workflow`` do MigrateJourneyWorkflow."""
    return patch("src.workflows.migrate_journey_workflow.workflow")


async def _make_result(value):
    return value


@pytest.mark.asyncio()
class TestMigrateJourneyWorkflowRun:
    async def test_requires_generation_runs_fluxog_before_migration(self):
        """requires_generation → FluxoG child ANTES de DataMigration child (ordem)."""
        wf = MigrateJourneyWorkflow()
        plan = _plan(generate_target={"language": "python", "framework": "fastapi"})

        with _patched_workflow() as mock_workflow:
            mock_workflow.info.return_value = MagicMock(
                workflow_id="wf-j4", task_queue="q"
            )
            mock_workflow.logger = MagicMock()
            mock_workflow.execute_child_workflow = MagicMock(
                side_effect=[
                    _make_result(
                        {
                            "status": "completed",
                            "deployment": {"service_url": "http://modern-svc"},
                        }
                    ),
                    _make_result({"status": "success", "rows_migrated": 10}),
                ]
            )

            result = await wf.run(plan)

        calls = mock_workflow.execute_child_workflow.call_args_list
        assert len(calls) == 2
        # Ordem: GENERATE (FluxoG) ANTES de MIGRATE (DataMigration).
        assert calls[0].args[0] == FluxoGWorkflow.run
        assert calls[1].args[0] == DataMigrationWorkflow.run
        # Dependência de dados: destino derivado do GENERATE chega ao MIGRATE.
        migrate_input = calls[1].args[1]
        assert (
            migrate_input["migration_config"]["modern_connection_id"]
            == "http://modern-svc"
        )
        assert result["status"] == "completed"
        assert result["journey"] == "J4_MIGRATE"
        assert result["generate_result"]["status"] == "completed"
        assert result["migration_result"]["rows_migrated"] == 10

    async def test_without_signal_skips_generation_only_migration(self):
        """sem sinal → salta GENERATE, só DataMigration."""
        wf = MigrateJourneyWorkflow()
        plan = _plan()  # sem generate_target

        with _patched_workflow() as mock_workflow:
            mock_workflow.info.return_value = MagicMock(
                workflow_id="wf-j4", task_queue="q"
            )
            mock_workflow.logger = MagicMock()
            mock_workflow.execute_child_workflow = MagicMock(
                side_effect=[_make_result({"status": "success", "rows_migrated": 5})]
            )

            result = await wf.run(plan)

        calls = mock_workflow.execute_child_workflow.call_args_list
        assert len(calls) == 1
        assert calls[0].args[0] == DataMigrationWorkflow.run
        assert result["status"] == "completed"
        # Sem GENERATE: chave generate_result ausente do resultado composto.
        assert "generate_result" not in result

    async def test_generate_failure_does_not_run_migration_fail_closed(self):
        """GENERATE falha → NÃO executa MIGRATE (fail-closed)."""
        wf = MigrateJourneyWorkflow()
        plan = _plan(generate_target={"language": "python"})

        with _patched_workflow() as mock_workflow:
            mock_workflow.info.return_value = MagicMock(
                workflow_id="wf-j4", task_queue="q"
            )
            mock_workflow.logger = MagicMock()
            # Só o GENERATE é chamado; se MIGRATE fosse chamado, StopIteration.
            mock_workflow.execute_child_workflow = MagicMock(
                side_effect=[
                    _make_result({"status": "failed", "error": "build falhou"})
                ]
            )

            result = await wf.run(plan)

        # Apenas 1 child executado (GENERATE); MIGRATE NÃO foi executado.
        assert mock_workflow.execute_child_workflow.call_count == 1
        assert (
            mock_workflow.execute_child_workflow.call_args_list[0].args[0]
            == FluxoGWorkflow.run
        )
        assert result["status"] == "failed"
        assert result["failure_reason"] == "generate_failed"
        assert result["migration_result"] is None

    async def test_migration_failure_yields_failed_status(self):
        """Migração falhada → status failed (fail-closed da migração)."""
        wf = MigrateJourneyWorkflow()
        plan = _plan()  # sem geração

        with _patched_workflow() as mock_workflow:
            mock_workflow.info.return_value = MagicMock(
                workflow_id="wf-j4", task_queue="q"
            )
            mock_workflow.logger = MagicMock()
            mock_workflow.execute_child_workflow = MagicMock(
                side_effect=[
                    _make_result({"status": "rolled_back", "phase": "validation"})
                ]
            )

            result = await wf.run(plan)

        assert result["status"] == "failed"
        assert result["failure_reason"] == "migration_failed"
