"""Workflow Temporal composto para a jornada J4_MIGRATE.

Compõe, com durabilidade Temporal e via **child-workflows**, a jornada de
modernização de legado:

    GENERATE (condicional) -> MIGRATE

- **GENERATE** (``FluxoGWorkflow``) é **condicional**: só corre quando o plano
  exige código novo (sinal ``generate_target`` no Cognitive Plan). O serviço
  moderno gerado/deployado é o **destino** (``modern_connection``) da migração.
- **MIGRATE** (``DataMigrationWorkflow``) corre sempre (a jornada J4 é, por
  definição, de migração) — depois do GENERATE quando este existe.

FAIL-CLOSED: se o GENERATE falhar/ficar incompleto, a migração **NÃO** é
executada (não se migra dados para um destino que não está de pé) e a jornada
devolve ``status="failed"``. Migração falhada → ``status="failed"``.

Determinismo (Temporal): este workflow não usa relógio/aleatoriedade; toda a
lógica de decisão/derivação está em **funções puras** testáveis
(``_journey_needs_generation``, ``build_generate_child_input``,
``build_migrate_child_input``). Os child-workflows são importados sob
``workflow.unsafe.imports_passed_through()``.

NOTA (honestidade de escopo, Fase 3): este módulo prova a **orquestração
durável em bloco** (sequência condicional + fail-closed) por testes de bloco. A
prova E2E real (intenção J4 → software gerado a correr + DB migrado +
``/validate`` OK no cluster) é a **Fase 4**.
"""

from __future__ import annotations

from typing import Any

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from src.workflows.data_migration_workflow import DataMigrationWorkflow
    from src.workflows.fluxo_g_workflow import FluxoGWorkflow


# =============================================================================
# Funções puras (decisão / derivação) — testáveis sem Temporal
# =============================================================================


def _journey_needs_generation(cognitive_plan: dict[str, Any]) -> bool:
    """A jornada precisa gerar código novo antes de migrar?

    A decisão deriva da SEMÂNTICA do plano: a presença de um ``generate_target``
    não-vazio sinaliza que o destino moderno tem de ser gerado/deployado antes da
    migração. Ausente/vazio → migração sobre um destino já existente (salta
    GENERATE). Sem defaults silenciosos: sem sinal, sem geração.
    """
    return bool(cognitive_plan.get("generate_target"))


def build_generate_child_input(cognitive_plan: dict[str, Any]) -> dict[str, Any]:
    """Constrói o input do child ``FluxoGWorkflow`` (GENERATE).

    O ``FluxoGWorkflow`` espera ``{cognitive_plan, original_intent?,
    skip_approvals?}``. A composição é automatizada (``skip_approvals`` default
    ``True``); o plano pode sobrepor explicitamente.
    """
    return {
        "cognitive_plan": cognitive_plan,
        "original_intent": cognitive_plan.get("original_intent"),
        "skip_approvals": cognitive_plan.get("skip_approvals", True),
    }


def _derive_modern_connection(generate_result: dict[str, Any] | None) -> str | None:
    """Deriva o destino (modern_connection) do resultado do GENERATE.

    Dependência de dados da modernização: o serviço/destino que o GENERATE
    deploya é o ``modern_connection`` que o MIGRATE usa. Lê o ``service_url`` do
    deployment do ``FluxoGWorkflow``. Ausente → ``None`` (o caller mantém o
    destino do plano).
    """
    if not isinstance(generate_result, dict):
        return None
    deployment = generate_result.get("deployment") or {}
    service_url = deployment.get("service_url")
    return service_url if service_url else None


def build_migrate_child_input(
    cognitive_plan: dict[str, Any], generate_result: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Constrói o input do child ``DataMigrationWorkflow`` (MIGRATE).

    Deriva o ``migration_config`` do plano e, quando houve GENERATE, sobrepõe o
    ``modern_connection_id`` pelo destino realmente deployado (dependência de
    dados GENERATE→destino). Quando não há GENERATE (ou sem destino derivável),
    usa o ``modern_connection`` do plano.
    """
    raw_config = cognitive_plan.get("migration_config") or {}
    migration_config = dict(raw_config)

    derived_modern = _derive_modern_connection(generate_result)
    if derived_modern:
        migration_config["modern_connection_id"] = derived_modern

    return {
        "migration_config": migration_config,
        "job_id": None,
        "initial_phase": "pending",
    }


def _generate_succeeded(generate_result: dict[str, Any] | None) -> bool:
    """O GENERATE concluiu com sucesso? (``FluxoGWorkflow`` -> status=completed)."""
    return (
        isinstance(generate_result, dict)
        and generate_result.get("status") == "completed"
    )


def _migration_succeeded(migration_result: dict[str, Any] | None) -> bool:
    """A migração concluiu com sucesso? (``DataMigrationWorkflow`` -> status=success)."""
    return (
        isinstance(migration_result, dict)
        and migration_result.get("status") == "success"
    )


# =============================================================================
# Workflow composto (orquestra child-workflows)
# =============================================================================


@workflow.defn
class MigrateJourneyWorkflow:
    """Sequencia GENERATE (condicional) → MIGRATE via child-workflows (J4_MIGRATE)."""

    def __init__(self) -> None:
        self._status = "initializing"
        self._generate_result: dict[str, Any] | None = None
        self._migration_result: dict[str, Any] | None = None

    @workflow.run
    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Executa a jornada composta J4_MIGRATE.

        Args:
            input_data: o Cognitive Plan (com ``migration_config`` e, opcional,
                ``generate_target`` sinalizando geração).

        Returns:
            Resultado composto ``{journey, status, generate_result?,
            migration_result, failure_reason?}``.
        """
        cognitive_plan = input_data
        info = workflow.info()
        workflow_id = info.workflow_id
        task_queue = info.task_queue

        workflow.logger.info(
            f"Iniciando MigrateJourneyWorkflow: workflow_id={workflow_id}"
        )

        generate_result: dict[str, Any] | None = None

        # === GENERATE (condicional) ===
        if _journey_needs_generation(cognitive_plan):
            self._status = "generating"
            workflow.logger.info(
                "J4/GENERATE: gerando destino moderno (FluxoGWorkflow child)"
            )

            generate_result = await workflow.execute_child_workflow(
                FluxoGWorkflow.run,
                build_generate_child_input(cognitive_plan),
                id=f"{workflow_id}-generate",
                task_queue=task_queue,
            )
            self._generate_result = generate_result

            # FAIL-CLOSED: sem destino de pé não há migração.
            if not _generate_succeeded(generate_result):
                self._status = "failed"
                workflow.logger.error(
                    "J4/GENERATE falhou — migração NÃO executada (fail-closed)"
                )
                return {
                    "journey": "J4_MIGRATE",
                    "status": "failed",
                    "failure_reason": "generate_failed",
                    "generate_result": generate_result,
                    "migration_result": None,
                }

        # === MIGRATE ===
        self._status = "migrating"
        workflow.logger.info("J4/MIGRATE: migrando dados (DataMigrationWorkflow child)")

        migration_result = await workflow.execute_child_workflow(
            DataMigrationWorkflow.run,
            build_migrate_child_input(cognitive_plan, generate_result),
            id=f"{workflow_id}-migrate",
            task_queue=task_queue,
        )
        self._migration_result = migration_result

        status = "completed" if _migration_succeeded(migration_result) else "failed"
        self._status = status

        result: dict[str, Any] = {
            "journey": "J4_MIGRATE",
            "status": status,
            "migration_result": migration_result,
        }
        if generate_result is not None:
            result["generate_result"] = generate_result
        if status == "failed":
            result["failure_reason"] = "migration_failed"

        workflow.logger.info(f"MigrateJourneyWorkflow concluído: status={status}")
        return result

    @workflow.query
    def get_status(self) -> dict[str, Any]:
        """Query do estado atual da jornada composta."""
        return {
            "status": self._status,
            "generate_done": self._generate_result is not None,
            "migration_done": self._migration_result is not None,
        }
