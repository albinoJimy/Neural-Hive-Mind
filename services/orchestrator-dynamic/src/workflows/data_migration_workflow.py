"""
Workflow Temporal para Data Migration System.

Implementa o fluxo de migração de dados orquestrado via Temporal:
1. Analyze Legacy Schema
2. Generate Schema Mapping
3. Approve Mapping (gate humano)
4. Create Snapshot
5. Run Batch Migration
6. Start CDC
7. Validate Data
8. Cleanup Snapshot

Suporta rollback automático em caso de falha e sinais externos
para aprovação, pausa e rollback manual.
"""

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from src.models.migration import MigrationStatus


@workflow.defn
class DataMigrationWorkflow:
    """
    Workflow de Migração de Dados.

    Gerencia o ciclo de vida completo de uma migração de dados do sistema
    legado para o NHM, com gates de aprovação humana e rollback automático.
    """

    def __init__(self):
        self._status = "initializing"
        self._current_phase = MigrationStatus.PENDING
        self._job_id: str | None = None
        self._config: dict | None = None
        self._snapshot_id: str | None = None
        self._rollback_triggered = False
        self._pause_requested = False
        self._mapping_approved = False
        self._progress = {
            "rows_migrated": 0,
            "total_rows": 0,
            "progress_percentage": 0.0,
        }

    @workflow.run
    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """
        Executa o workflow de migração de dados.

        Args:
            input_data: Dicionário contendo:
                - migration_config: Configuração da migração
                - job_id: ID existente (opcional, para retomada)
                - initial_phase: Fase inicial (opcional)

        Returns:
            Dicionário com resultado da migração
        """
        config_data = input_data.get("migration_config", {})
        self._job_id = input_data.get("job_id")
        initial_phase = input_data.get(
            "initial_phase", MigrationStatus.PENDING.value
        )

        workflow_id = workflow.info().workflow_id

        workflow.logger.info(
            f"Iniciando workflow de migração: workflow_id={workflow_id}, "
            f"job_id={self._job_id}, initial_phase={initial_phase}"
        )

        try:
            # === Fase 1: Analyze Legacy Schema ===
            self._status = "analyzing"
            self._current_phase = MigrationStatus.ANALYZING

            analyze_result = await self._analyze_legacy_schema(config_data)

            if not analyze_result["success"]:
                return self._build_error_result(
                    workflow_id, "analyzing", analyze_result.get("error")
                )

            workflow.logger.info("Schema analisado com sucesso")

            # === Fase 2: Generate Schema Mapping ===
            self._status = "mapping"
            self._current_phase = MigrationStatus.MAPPING

            mapping_result = await self._generate_schema_mapping(
                analyze_result["schema_analysis"], config_data
            )

            if not mapping_result["success"]:
                return self._build_error_result(
                    workflow_id, "mapping", mapping_result.get("error")
                )

            workflow.logger.info("Mapeamento de schema gerado com sucesso")

            # === Fase 3: Approve Mapping (gate humano) ===
            self._status = "approving"
            self._current_phase = MigrationStatus.MAPPING

            # Verificar se aprovação automática está habilitada
            auto_approve = config_data.get("auto_approve", True)

            if not auto_approve:
                # Aguardar aprovação humana
                workflow.logger.info(
                    "Aguardando aprovação humana do mapeamento"
                )

                # Esperar sinal de aprovação (com timeout de 24h)
                await workflow.wait_condition(
                    lambda: self._mapping_approved or self._rollback_triggered,
                    timeout=timedelta(hours=24),
                )

                if self._rollback_triggered:
                    return await self._handle_rollback(
                        workflow_id, "mapping", "Rollback durante aprovação"
                    )

            else:
                # Aprovação automática
                self._mapping_approved = True
                workflow.logger.info("Aprovação automática realizada")

            # === Fase 4: Create Snapshot ===
            self._status = "creating_snapshot"
            self._current_phase = MigrationStatus.SNAPSHOT_CREATED

            snapshot_result = await self._create_snapshot(
                mapping_result["schema_mapping"], config_data
            )

            if not snapshot_result["success"]:
                return self._build_error_result(
                    workflow_id, "snapshot", snapshot_result.get("error")
                )

            self._snapshot_id = snapshot_result["snapshot_id"]
            workflow.logger.info(
                f"Snapshot criado: snapshot_id={self._snapshot_id}"
            )

            # === Fase 5: Batch Migration ===
            self._status = "batch_migrating"
            self._current_phase = MigrationStatus.BATCH_MIGRATING

            batch_result = await self._run_batch_migration(
                mapping_result["schema_mapping"], config_data
            )

            if not batch_result["success"]:
                # Rollback em caso de falha
                return await self._handle_rollback(
                    workflow_id, "batch_migration", batch_result.get("error")
                )

            # Atualizar progresso
            self._progress["rows_migrated"] = batch_result.get("rows_migrated", 0)
            self._progress["total_rows"] = batch_result.get("total_rows", 0)
            self._progress["progress_percentage"] = batch_result.get(
                "progress_percentage", 0.0
            )

            workflow.logger.info(
                f"Migração batch concluída: "
                f"{self._progress['rows_migrated']} linhas migradas"
            )

            # === Fase 6: Start CDC ===
            self._status = "starting_cdc"
            self._current_phase = MigrationStatus.CDC_RUNNING

            cdc_result = await self._start_cdc(
                mapping_result["schema_mapping"], config_data
            )

            if not cdc_result["success"]:
                return await self._handle_rollback(
                    workflow_id, "cdc", cdc_result.get("error")
                )

            workflow.logger.info("CDC iniciado com sucesso")

            # === Fase 7: Validate Data ===
            self._status = "validating"
            self._current_phase = MigrationStatus.VALIDATING

            validation_result = await self._validate_data(
                mapping_result["schema_mapping"], config_data
            )

            if not validation_result["success"]:
                validation_report = validation_result.get("validation_report", {})
                if not validation_report.get("overall_passed", False):
                    return await self._handle_rollback(
                        workflow_id,
                        "validation",
                        validation_report.get("reason", "Validação falhou"),
                    )

            workflow.logger.info("Validação de dados concluída com sucesso")

            # === Fase 8: Cleanup Snapshot ===
            self._status = "cleaning_up"
            self._current_phase = MigrationStatus.COMPLETED

            if self._snapshot_id:
                await self._cleanup_snapshot()

            # Workflow concluído
            self._status = "completed"

            return {
                "workflow_id": workflow_id,
                "job_id": self._job_id,
                "status": "success",
                "final_phase": "completed",
                "rows_migrated": self._progress["rows_migrated"],
                "total_rows": self._progress["total_rows"],
                "cdc_connector_id": cdc_result.get("connector_id"),
                "validation_report": validation_result.get("validation_report"),
            }

        except Exception as e:
            self._status = "failed"
            workflow.logger.error(f"Erro no workflow de migração: {e}", exc_info=True)
            raise

    async def _analyze_legacy_schema(
        self, config: dict
    ) -> dict[str, Any]:
        """
        Executa análise de schema legado.

        Args:
            config: Configuração da migração

        Returns:
            Dict com resultado da análise
        """
        from src.activities.data_migration import analyze_legacy_schema

        legacy_connection_id = config.get("legacy_connection_id")
        schema = config.get("schema", "public")
        tables = config.get("tables")  # None = todas as tabelas

        workflow.logger.info(
            f"Analisando schema legado: connection={legacy_connection_id}, "
            f"schema={schema}"
        )

        result = await workflow.execute_activity(
            analyze_legacy_schema,
            args=[legacy_connection_id, schema, tables],
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        return result

    async def _generate_schema_mapping(
        self, schema_analysis: dict, config: dict
    ) -> dict[str, Any]:
        """
        Gera mapeamento de schema.

        Args:
            schema_analysis: Análise do schema legado
            config: Configuração da migração

        Returns:
            Dict com mapeamento gerado
        """
        from src.activities.data_migration import generate_schema_mapping

        target_service = config.get("target_service")

        workflow.logger.info(f"Gerando mapeamento de schema: target={target_service}")

        result = await workflow.execute_activity(
            generate_schema_mapping,
            args=[schema_analysis, target_service],
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )

        return result

    async def _create_snapshot(
        self, schema_mapping: dict, config: dict
    ) -> dict[str, Any]:
        """
        Cria snapshot para rollback.

        Args:
            schema_mapping: Mapeamento de schema
            config: Configuração da migração

        Returns:
            Dict com snapshot criado
        """
        from src.activities.data_migration import create_snapshot

        strategy = config.get("snapshot_strategy", "s3")

        workflow.logger.info(
            f"Criando snapshot: strategy={strategy}, "
            f"tables={len(schema_mapping.get('tables', []))}"
        )

        result = await workflow.execute_activity(
            create_snapshot,
            args=[self._job_id, schema_mapping.get("tables", []), strategy],
            start_to_close_timeout=timedelta(hours=2),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )

        return result

    async def _run_batch_migration(
        self, schema_mapping: dict, config: dict
    ) -> dict[str, Any]:
        """
        Executa migração batch.

        Args:
            schema_mapping: Mapeamento de schema
            config: Configuração da migração

        Returns:
            Dict com resultado da migração
        """
        from src.activities.data_migration import run_batch_migration

        batch_size = config.get("batch_size", 1000)
        max_parallel = config.get("max_parallel_migrations", 5)

        workflow.logger.info(
            f"Iniciando migração batch: batch_size={batch_size}, "
            f"max_parallel={max_parallel}"
        )

        # Calcular timeout baseado no tamanho estimado
        timeout_minutes = min(60, len(schema_mapping.get("tables", [])) * 10)

        result = await workflow.execute_activity(
            run_batch_migration,
            args=[self._job_id, schema_mapping, batch_size, max_parallel],
            start_to_close_timeout=timedelta(minutes=timeout_minutes),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )

        return result

    async def _start_cdc(self, schema_mapping: dict, config: dict) -> dict[str, Any]:
        """
        Inicia pipeline CDC.

        Args:
            schema_mapping: Mapeamento de schema
            config: Configuração da migração

        Returns:
            Dict com resultado do início do CDC
        """
        from src.activities.data_migration import start_cdc

        database_config = config.get("database_config", {})

        workflow.logger.info("Iniciando pipeline CDC")

        result = await workflow.execute_activity(
            start_cdc,
            args=[self._job_id, schema_mapping, database_config],
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        return result

    async def _validate_data(
        self, schema_mapping: dict, config: dict
    ) -> dict[str, Any]:
        """
        Valida dados migrados.

        Args:
            schema_mapping: Mapeamento de schema
            config: Configuração da migração

        Returns:
            Dict com resultado da validação
        """
        from src.activities.data_migration import validate_data

        workflow.logger.info("Validando dados migrados")

        result = await workflow.execute_activity(
            validate_data,
            args=[self._job_id, schema_mapping],
            start_to_close_timeout=timedelta(minutes=30),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )

        return result

    async def _cleanup_snapshot(self) -> dict[str, Any]:
        """
        Limpa snapshot após migração bem-sucedida.

        Returns:
            Dict com resultado da limpeza
        """
        from src.activities.data_migration import cleanup_snapshot

        workflow.logger.info(
            f"Limpando snapshot: snapshot_id={self._snapshot_id}"
        )

        try:
            result = await workflow.execute_activity(
                cleanup_snapshot,
                args=[self._snapshot_id],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )
            return result
        except Exception as e:
            workflow.logger.warning(f"Falha ao limpar snapshot (não-crítica): {e}")
            return {"success": False, "error": str(e)}

    async def _handle_rollback(
        self, workflow_id: str, phase: str, error: str | None = None
    ) -> dict[str, Any]:
        """
        Trata rollback da migração.

        Args:
            workflow_id: ID do workflow
            phase: Fase onde ocorreu o erro
            error: Erro que causou o rollback

        Returns:
            Dict com resultado do rollback
        """
        from src.activities.data_migration import execute_rollback

        self._rollback_triggered = True
        self._status = "rolling_back"
        self._current_phase = MigrationStatus.FAILED

        workflow.logger.error(f"Rollback acionado: phase={phase}, error={error}")

        rollback_result = await workflow.execute_activity(
            execute_rollback,
            args=[self._job_id, self._snapshot_id, phase, error],
            start_to_close_timeout=timedelta(minutes=30),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        return {
            "workflow_id": workflow_id,
            "job_id": self._job_id,
            "status": "rolled_back",
            "phase": phase,
            "error": error,
            "rollback_successful": rollback_result.get("success", False),
        }

    def _build_error_result(
        self, workflow_id: str, phase: str, error: str | None = None
    ) -> dict[str, Any]:
        """Constroi resultado de erro."""
        return {
            "workflow_id": workflow_id,
            "job_id": self._job_id,
            "status": "failed",
            "phase": phase,
            "error": error,
        }

    # ========== Signals ==========

    @workflow.signal
    async def approve_mapping(self, approved_by: str = "unknown"):
        """
        Signal para aprovar mapeamento de schema (gate humano).

        Args:
            approved_by: Usuário ou serviço aprovando
        """
        workflow.logger.info(f"Sinal de aprovação recebido: approved_by={approved_by}")
        self._mapping_approved = True

    @workflow.signal
    async def pause_migration(self):
        """Signal para pausar a migração."""
        workflow.logger.info("Sinal de pausa recebido")
        self._pause_requested = True

    @workflow.signal
    async def resume_migration(self):
        """Signal para retomar a migração."""
        workflow.logger.info("Sinal de retomada recebido")
        self._pause_requested = False

    @workflow.signal
    async def trigger_rollback(self, reason: str = "manual"):
        """
        Signal para acionar rollback manual.

        Args:
            reason: Motivo do rollback
        """
        workflow.logger.warning(f"Sinal de rollback recebido: reason={reason}")
        self._rollback_triggered = True

    @workflow.signal
    async def update_progress(self, rows_migrated: int, total_rows: int):
        """
        Signal para atualizar progresso da migração.

        Args:
            rows_migrated: Linhas migradas
            total_rows: Total de linhas
        """
        self._progress["rows_migrated"] = rows_migrated
        self._progress["total_rows"] = total_rows
        if total_rows > 0:
            self._progress["progress_percentage"] = (
                rows_migrated / total_rows
            ) * 100.0
        workflow.logger.info(
            f"Progresso atualizado: {self._progress['progress_percentage']:.1f}%"
        )

    # ========== Queries ==========

    @workflow.query
    def get_status(self) -> dict[str, Any]:
        """Query para consultar status atual."""
        return {
            "status": self._status,
            "current_phase": self._current_phase.value
            if isinstance(self._current_phase, MigrationStatus)
            else self._current_phase,
            "job_id": self._job_id,
            "snapshot_id": self._snapshot_id,
            "mapping_approved": self._mapping_approved,
            "rollback_triggered": self._rollback_triggered,
            "pause_requested": self._pause_requested,
            "progress": self._progress,
        }

    @workflow.query
    def get_progress(self) -> dict[str, Any]:
        """Query para consultar progresso da migração."""
        return self._progress


def validate_migration_workflow_input(
    input_data: dict[str, Any]
) -> dict[str, Any]:
    """
    Valida entrada do workflow de migração.

    Args:
        input_data: Dados de entrada do workflow

    Returns:
        Dict com valid e error se inválido
    """
    required_fields = ["job_id", "schema_mapping_id", "legacy_connection_id"]

    config = input_data.get("migration_config", {})
    missing_fields = [f for f in required_fields if f not in config]

    if missing_fields:
        return {
            "valid": False,
            "missing_fields": missing_fields,
            "error": f"Campos obrigatórios faltando: {', '.join(missing_fields)}",
        }

    return {"valid": True}
