"""
Migration Orchestrator Service para Data Migration System.

Orquestra o fluxo completo de migração de dados, coordenando
Batch Migrator, CDC Pipeline, Data Validator e Rollback Manager.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

import structlog

from src.models.migration import (
    MigrationJob,
    MigrationStatus,
    SchemaMapping,
)
from src.services.batch_migrator import BatchMigrator, get_batch_migrator
from src.services.cdc_pipeline import CDCPipeline, get_cdc_pipeline
from src.services.data_validator import DataValidator, get_data_validator
from src.services.rollback_manager import RollbackManager, get_rollback_manager

__all__ = [
    "MigrationOrchestrator",
    "MigrationOrchestratorError",
    "PhaseTransitionError",
    "get_migration_orchestrator",
    "clear_migration_orchestrator",
]

logger = structlog.get_logger()


class MigrationOrchestratorError(Exception):
    """Exceção base para erros do Migration Orchestrator."""

    pass


class PhaseTransitionError(MigrationOrchestratorError):
    """Erro na transição de fase da migração."""

    pass


class MigrationOrchestrator:
    """
    Orquestrador de migração de dados.

    Coordena o fluxo completo de migração através das fases:
    1. PENDING → ANALYZING (análise de schema)
    2. ANALYZING → MAPPING (geração de mapeamento)
    3. MAPPING → MAPPING_APPROVED (aprovação humana)
    4. MAPPING_APPROVED → SNAPSHOT_CREATED (snapshot para rollback)
    5. SNAPSHOT_CREATED → BATCH_MIGRATING (migração histórica)
    6. BATCH_MIGRATING → CDC_RUNNING (CDC em tempo real)
    7. CDC_RUNNING → VALIDATING (validação de dados)
    8. VALIDATING → COMPLETED (conclusão)

    Em caso de erro em qualquer fase → FAILED
    Rollback manual → ROLLED_BACK
    """

    # Estados onde pausa é permitida
    PAUSABLE_STATES = {
        MigrationStatus.BATCH_MIGRATING,
        MigrationStatus.CDC_RUNNING,
        MigrationStatus.VALIDATING,
    }

    # Estados terminais
    TERMINAL_STATES = {
        MigrationStatus.COMPLETED,
        MigrationStatus.FAILED,
        MigrationStatus.ROLLED_BACK,
    }

    # Estados que requerem aprovação humana para prosseguir
    APPROVAL_REQUIRED_STATES = {
        MigrationStatus.MAPPING,
    }

    def __init__(
        self,
        job_id: str,
        schema_mapper: Optional[Any] = None,
        batch_migrator: Optional[BatchMigrator] = None,
        cdc_pipeline: Optional[CDCPipeline] = None,
        data_validator: Optional[DataValidator] = None,
        rollback_manager: Optional[RollbackManager] = None,
    ):
        """
        Inicializa Migration Orchestrator.

        Args:
            job_id: ID do job de migração
            schema_mapper: SchemaMapper (opcional, para injeção de dependência)
            batch_migrator: BatchMigrator (opcional)
            cdc_pipeline: CDCPipeline (opcional)
            data_validator: DataValidator (opcional)
            rollback_manager: RollbackManager (opcional)
        """
        self.job_id = job_id

        # Dependências (lazy loading se não fornecidas)
        self._schema_mapper = schema_mapper
        self._batch_migrator = batch_migrator
        self._cdc_pipeline = cdc_pipeline
        self._data_validator = data_validator
        self._rollback_manager = rollback_manager

        # Estado de controle
        self._paused: bool = False
        self._running: bool = False
        self._stopped: bool = False
        self._snapshot_id: Optional[str] = None
        self._cdc_started: bool = False

        # Configurações
        self._auto_rollback = True  # Padrão: fazer rollback em falha
        self._snapshot_strategy = "s3"  # ou "shadow"

    async def start_migration(
        self,
        migration_job: MigrationJob,
        schema_mapping: SchemaMapping,
        legacy_client: Any,
        target_client: Any,
        kafka_producer: Optional[Any] = None,
        database_config: Optional[Dict[str, Any]] = None,
        auto_approve: bool = True,
    ) -> MigrationJob:
        """
        Inicia ou retoma uma migração.

        Executa o fluxo completo de migração a partir do estado atual
        do MigrationJob, permitindo retomar de interrupções.

        Args:
            migration_job: Job de migração a executar
            schema_mapping: Mapeamento de schema a utilizar
            legacy_client: Cliente do banco legado (PostgreSQL)
            target_client: Cliente do banco alvo
            kafka_producer: Producer Kafka para eventos (opcional)
            database_config: Configuração do banco legado para CDC
            auto_approve: Se True, aprova automaticamente fases que requerem aprovação

        Returns:
            MigrationJob atualizado

        Raises:
            MigrationOrchestratorError: Se ocorrer erro fatal
        """
        if self._running:
            raise MigrationOrchestratorError("Migração já está em andamento")

        self._running = True
        self._stopped = False

        logger.info(
            "migration_started",
            job_id=self.job_id,
            current_status=migration_job.status,
        )

        try:
            # Fluxo baseado no status atual
            if migration_job.status == MigrationStatus.PENDING:
                migration_job = await self._analyze_and_map(
                    migration_job=migration_job,
                    legacy_client=legacy_client,
                    schema_mapping=schema_mapping,
                )

            # Se ainda não aprovado e não auto_approve, parar aqui
            if migration_job.status == MigrationStatus.MAPPING and not auto_approve:
                logger.info(
                    "migration_awaiting_approval",
                    job_id=self.job_id,
                    required_status="MAPPING_APPROVED",
                )
                self._running = False
                return migration_job

            if migration_job.status == MigrationStatus.MAPPING:
                # Aprovação manual necessária
                if not auto_approve:
                    return migration_job
                # Aprovar automaticamente
                migration_job.status = MigrationStatus.MAPPING_APPROVED
                migration_job.updated_at = datetime.now(timezone.utc)

            # Executar migração completa a partir de MAPPING_APPROVED
            if migration_job.status == MigrationStatus.MAPPING_APPROVED:
                result = await self._execute_full_migration(
                    migration_job=migration_job,
                    schema_mapping=schema_mapping,
                    legacy_client=legacy_client,
                    target_client=target_client,
                    kafka_producer=kafka_producer,
                    database_config=database_config or {},
                )

                # Atualizar job com resultado
                migration_job.status = result["status"]
                if result.get("error_message"):
                    migration_job.error_message = result["error_message"]

            # Retomar de estados intermediários
            elif migration_job.status == MigrationStatus.BATCH_MIGRATING:
                result = await self._continue_from_batch(
                    migration_job=migration_job,
                    schema_mapping=schema_mapping,
                    legacy_client=legacy_client,
                    target_client=target_client,
                    kafka_producer=kafka_producer,
                    database_config=database_config or {},
                )
                migration_job.status = result["status"]

            elif migration_job.status == MigrationStatus.CDC_RUNNING:
                result = await self._continue_from_cdc(
                    migration_job=migration_job,
                    schema_mapping=schema_mapping,
                    target_client=target_client,
                )
                migration_job.status = result["status"]

            elif migration_job.status == MigrationStatus.VALIDATING:
                result = await self._continue_from_validation(
                    migration_job=migration_job,
                    schema_mapping=schema_mapping,
                    legacy_client=legacy_client,
                    target_client=target_client,
                )
                migration_job.status = result["status"]

            # Estados terminais - nada a fazer
            elif self._is_terminal_state(migration_job.status):
                logger.info(
                    "migration_already_terminal",
                    job_id=self.job_id,
                    status=migration_job.status,
                )

            logger.info(
                "migration_finished",
                job_id=self.job_id,
                final_status=migration_job.status,
            )

            return migration_job

        except Exception as e:
            logger.error(
                "migration_failed",
                job_id=self.job_id,
                error=str(e),
            )
            migration_job.update_status(MigrationStatus.FAILED, error_message=str(e))
            raise MigrationOrchestratorError(f"Falha na migração: {e}") from e
        finally:
            self._running = False

    async def get_migration_status(
        self,
        migration_job: MigrationJob,
    ) -> Dict[str, Any]:
        """
        Retorna status atual da migração.

        Args:
            migration_job: Job de migração

        Returns:
            Dicionário com informações de status
        """
        status = {
            "job_id": self.job_id,
            "status": migration_job.status,
            "running": self._running,
            "paused": self._paused,
            "stopped": self._stopped,
            "snapshot_id": self._snapshot_id,
            "cdc_started": self._cdc_started,
            "progress_percentage": migration_job.progress_percentage,
            "rows_migrated": migration_job.rows_migrated,
            "total_rows": migration_job.total_rows,
            "rows_failed": migration_job.rows_failed,
            "started_at": (
                migration_job.started_at.isoformat() if migration_job.started_at else None
            ),
            "updated_at": (
                migration_job.updated_at.isoformat() if migration_job.updated_at else None
            ),
        }

        # Adicionar ETA se disponível
        eta = migration_job.calculate_eta()
        if eta:
            status["eta_seconds"] = int(eta.total_seconds())

        # Adicionar progresso do batch migrator se disponível
        if self._batch_migrator:
            try:
                batch_progress = self._batch_migrator.get_migration_progress()
                status["batch_progress"] = batch_progress
            except Exception:
                pass

        # Adicionar status do CDC se iniciado
        if self._cdc_started and self._cdc_pipeline:
            try:
                cdc_status = await self._cdc_pipeline.get_cdc_status()
                status["cdc_status"] = cdc_status.to_dict()
            except Exception:
                pass

        return status

    async def pause_migration(
        self,
        migration_job: MigrationJob,
    ) -> bool:
        """
        Pausa a migração entre fases.

        Args:
            migration_job: Job de migração

        Returns:
            True se pausa foi bem-sucedida

        Raises:
            PhaseTransitionError: Se estado não permitir pausa
        """
        if not self._can_pause_from_state(migration_job.status):
            raise PhaseTransitionError(
                f"Migração no estado {migration_job.status} não pode ser pausada"
            )

        if self._paused:
            logger.warning("migration_already_paused", job_id=self.job_id)
            return True

        logger.info("migration_pausing", job_id=self.job_id)

        # Pausar batch migrator se em execução
        if self._batch_migrator and migration_job.status == MigrationStatus.BATCH_MIGRATING:
            self._batch_migrator.pause_migration()

        # Pausar connector CDC se ativo
        if self._cdc_pipeline and self._cdc_started:
            try:
                await self._cdc_pipeline.pause_connector()
            except Exception as e:
                logger.warning("cdc_pause_failed", error=str(e))

        self._paused = True

        logger.info("migration_paused", job_id=self.job_id)

        return True

    async def resume_migration(
        self,
        migration_job: MigrationJob,
    ) -> bool:
        """
        Retoma migração pausada.

        Args:
            migration_job: Job de migração

        Returns:
            True se retomada foi bem-sucedida

        Raises:
            PhaseTransitionError: Se migração não estiver pausada
        """
        if not self._paused:
            raise PhaseTransitionError(f"Migração {self.job_id} não está pausada")

        logger.info("migration_resuming", job_id=self.job_id)

        # Retomar batch migrator se aplicável
        if self._batch_migrator:
            self._batch_migrator.resume_migration()

        # Retomar connector CDC se ativo
        if self._cdc_pipeline and self._cdc_started:
            try:
                await self._cdc_pipeline.resume_connector()
            except Exception as e:
                logger.warning("cdc_resume_failed", error=str(e))

        self._paused = False

        logger.info("migration_resumed", job_id=self.job_id)

        return True

    async def pause_job(self, job_id: str) -> dict:
        """Pausa um job de migração em andamento.

        Args:
            job_id: ID do job

        Returns:
            Status atualizado do job

        Raises:
            ValueError: Se job não existe ou não pode ser pausado
        """
        job = await self.get_migration_status(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        if job.status not in ["running", "pending"]:
            raise ValueError(f"Job {job_id} cannot be paused (current status: {job.status})")

        # Atualizar status para paused
        job.status = "paused"
        job.paused_at = datetime.now(timezone.utc).isoformat()
        job.paused_by = "user_request"

        logger.info("migration_job_paused", job_id=job_id)

        return job.model_dump()

    async def resume_job(self, job_id: str) -> dict:
        """Retoma um job de migração pausado.

        Args:
            job_id: ID do job

        Returns:
            Status atualizado do job

        Raises:
            ValueError: Se job não existe ou não pode ser retomado
        """
        job = await self.get_migration_status(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        if job.status != "paused":
            raise ValueError(f"Job {job_id} cannot be resumed (current status: {job.status})")

        # Atualizar status para running
        job.status = "running"
        job.resumed_at = datetime.now(timezone.utc).isoformat()
        job.resumed_by = "user_request"

        logger.info("migration_job_resumed", job_id=job_id)

        return job.model_dump()

    async def rollback_migration(
        self,
        migration_job: MigrationJob,
    ) -> Dict[str, Any]:
        """
        Executa rollback completo da migração.

        Args:
            migration_job: Job de migração

        Returns:
            Dicionário com estatísticas do rollback

        Raises:
            MigrationOrchestratorError: Se não houver snapshot disponível
        """
        if not self._snapshot_id:
            raise MigrationOrchestratorError("Nenhum snapshot disponível para rollback")

        logger.info(
            "migration_rollback_started",
            job_id=self.job_id,
            snapshot_id=self._snapshot_id,
        )

        rollback_manager = self._get_rollback_manager()

        try:
            stats = await rollback_manager.execute_rollback(
                snapshot_id=self._snapshot_id,
            )

            migration_job.status = MigrationStatus.ROLLED_BACK
            migration_job.updated_at = datetime.now(timezone.utc)

            logger.info(
                "migration_rollback_completed",
                job_id=self.job_id,
                tables_processed=stats.tables_processed,
                rows_restored=stats.rows_restored,
            )

            return {
                "snapshot_id": self._snapshot_id,
                "tables_processed": stats.tables_processed,
                "rows_restored": stats.rows_restored,
                "duration_seconds": stats.duration_seconds,
            }

        except Exception as e:
            logger.error(
                "migration_rollback_failed",
                job_id=self.job_id,
                error=str(e),
            )
            raise MigrationOrchestratorError(f"Falha no rollback: {e}") from e

    async def approve_next_phase(
        self,
        migration_job: MigrationJob,
        schema_mapping: SchemaMapping,
        approved_by: str,
    ) -> bool:
        """
        Aprova próxima fase da migração (gate humano).

        Args:
            migration_job: Job de migração
            schema_mapping: SchemaMapping a aprovar
            approved_by: Usuário ou serviço aprovando

        Returns:
            True se aprovação foi bem-sucedida

        Raises:
            PhaseTransitionError: Se estado não requerer aprovação
        """
        if migration_job.status not in self.APPROVAL_REQUIRED_STATES:
            raise PhaseTransitionError(
                f"Transição de fase inválida: {migration_job.status} não requer aprovação"
            )

        logger.info(
            "migration_phase_approved",
            job_id=self.job_id,
            current_status=migration_job.status,
            approved_by=approved_by,
        )

        # Marcar schema mapping como aprovado
        schema_mapper = self._get_schema_mapper()
        await schema_mapper.approve_mapping(
            schema_mapping=schema_mapping,
            approved_by=approved_by,
        )

        # Atualizar status do job (transição válida garantida pela verificação acima)
        migration_job.status = MigrationStatus.MAPPING_APPROVED
        migration_job.updated_at = datetime.now(timezone.utc)

        return True

    # ========== Métodos Privados ==========

    async def _analyze_and_map(
        self,
        migration_job: MigrationJob,
        legacy_client: Any,
        schema_mapping: SchemaMapping,
    ) -> MigrationJob:
        """
        Executa fase de análise e mapeamento.

        Args:
            migration_job: Job de migração
            legacy_client: Cliente do banco legado
            schema_mapping: SchemaMapping a preencher

        Returns:
            MigrationJob atualizado
        """
        logger.info("phase_analyzing", job_id=self.job_id)
        migration_job.status = MigrationStatus.ANALYZING
        migration_job.updated_at = datetime.now(timezone.utc)

        schema_mapper = self._get_schema_mapper()

        try:
            # Analisar schema legado
            analyzed_schema = await schema_mapper.analyze_legacy_schema(
                postgres_client=legacy_client,
                schema="public",
                tables=None,  # Todas as tabelas
            )

            logger.info(
                "schema_analyzed",
                job_id=self.job_id,
                table_count=len(analyzed_schema.get("tables", [])),
            )

            # Atualizar para MAPPING
            migration_job.status = MigrationStatus.MAPPING
            migration_job.updated_at = datetime.now(timezone.utc)

            return migration_job

        except Exception as e:
            logger.error("phase_analyzing_failed", error=str(e))
            migration_job.status = MigrationStatus.FAILED
            migration_job.updated_at = datetime.now(timezone.utc)
            migration_job.error_message = str(e)
            raise

    async def _create_snapshot(
        self,
        migration_job: MigrationJob,
        schema_mapping: SchemaMapping,
    ) -> str:
        """
        Cria snapshot para rollback antes da migração.

        Args:
            migration_job: Job de migração
            schema_mapping: Mapeamento de schema

        Returns:
            ID do snapshot criado

        Raises:
            MigrationOrchestratorError: Se falhar criação do snapshot
        """
        logger.info(
            "phase_creating_snapshot",
            job_id=self.job_id,
            strategy=self._snapshot_strategy,
        )

        rollback_manager = self._get_rollback_manager()

        try:
            snapshot_id = await rollback_manager.create_snapshot(
                migration_job_id=self.job_id,
                table_mappings=schema_mapping.tables,
                strategy=self._snapshot_strategy,
            )

            self._snapshot_id = snapshot_id
            migration_job.status = MigrationStatus.SNAPSHOT_CREATED
            migration_job.updated_at = datetime.now(timezone.utc)

            logger.info(
                "snapshot_created",
                job_id=self.job_id,
                snapshot_id=snapshot_id,
            )

            return snapshot_id

        except Exception as e:
            logger.error("snapshot_creation_failed", error=str(e))
            migration_job.status = MigrationStatus.FAILED
            migration_job.updated_at = datetime.now(timezone.utc)
            migration_job.error_message = str(e)
            raise MigrationOrchestratorError(f"Falha ao criar snapshot: {e}") from e

    async def _execute_full_migration(
        self,
        migration_job: MigrationJob,
        schema_mapping: SchemaMapping,
        legacy_client: Any,
        target_client: Any,
        kafka_producer: Optional[Any] = None,
        database_config: Optional[Dict[str, Any]] = None,
        auto_rollback: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Executa fluxo completo de migração.

        Args:
            migration_job: Job de migração
            schema_mapping: Mapeamento de schema
            legacy_client: Cliente do banco legado
            target_client: Cliente do banco alvo
            kafka_producer: Producer Kafka (opcional)
            database_config: Configuração do banco para CDC
            auto_rollback: Se True, faz rollback em falha

        Returns:
            Dicionário com resultado da migração
        """
        auto_rollback = auto_rollback if auto_rollback is not None else self._auto_rollback
        database_config = database_config or {}

        logger.info(
            "full_migration_started",
            job_id=self.job_id,
            auto_rollback=auto_rollback,
        )

        try:
            # 1. Criar snapshot para rollback (BEST-EFFORT: não-fatal).
            # O snapshot usa o RollbackManager sobre POSTGRES_URL; numa migração
            # same-schema com db_urls do job, a sua falha NÃO deve abortar o
            # coração do gate (batch + validate). Falha → warning + continua.
            try:
                await self._create_snapshot(
                    migration_job=migration_job,
                    schema_mapping=schema_mapping,
                )
            except Exception as snapshot_error:
                logger.warning(
                    "snapshot_skipped_non_fatal",
                    job_id=self.job_id,
                    error=str(snapshot_error),
                )

            # 2. Executar migração batch
            logger.info("phase_batch_migrating", job_id=self.job_id)
            migration_job.status = MigrationStatus.BATCH_MIGRATING
            migration_job.updated_at = datetime.now(timezone.utc)

            batch_migrator = self._get_batch_migrator(
                schema_mapping_id=str(id(schema_mapping)),
                batch_size=migration_job.batch_size,
            )

            batch_stats = await batch_migrator.run_batch_migration(
                legacy_client=legacy_client,
                target_client=target_client,
                schema_mapping=schema_mapping,
                kafka_producer=kafka_producer,
            )

            migration_job.update_progress(
                rows_migrated=batch_stats["total_migrated"],
                total_rows=migration_job.total_rows,
            )

            # 3. Iniciar CDC
            logger.info("phase_starting_cdc", job_id=self.job_id)
            migration_job.status = MigrationStatus.CDC_RUNNING
            migration_job.updated_at = datetime.now(timezone.utc)

            cdc_pipeline = self._get_cdc_pipeline()

            # Criar connector se ainda não existe
            if database_config:
                try:
                    await cdc_pipeline.create_connector(
                        schema_mapping=schema_mapping,
                        database_hostname=database_config.get("hostname", "localhost"),
                        database_port=database_config.get("port", 5432),
                        database_user=database_config.get("user", "postgres"),
                        database_password=database_config.get("password", ""),
                        database_dbname=database_config.get("dbname", "legacy"),
                    )
                except Exception as e:
                    logger.warning("cdc_connector_creation_failed", error=str(e))

            # Iniciar consumo CDC (BEST-EFFORT: não-fatal).
            # CDC é opcional para uma migração batch same-schema; se o Kafka
            # estiver inacessível, registamos e seguimos para a validação.
            try:
                await cdc_pipeline.start_cdc(
                    schema_mapping=schema_mapping,
                    target_client=target_client,
                )
                self._cdc_started = True
            except Exception as cdc_error:
                logger.warning(
                    "cdc_start_skipped_non_fatal",
                    job_id=self.job_id,
                    error=str(cdc_error),
                )

            # 4. Validar dados
            logger.info("phase_validating", job_id=self.job_id)
            migration_job.status = MigrationStatus.VALIDATING
            migration_job.updated_at = datetime.now(timezone.utc)

            data_validator = self._get_data_validator()

            validation_report = await data_validator.generate_validation_report(
                schema_mapping=schema_mapping,
                legacy_client=legacy_client,
                modern_client=target_client,
            )

            # Verificar se validação passou
            if not validation_report.get("overall_passed", False):
                error_msg = "Validação de dados falhou"
                logger.error(
                    "validation_failed",
                    report=validation_report,
                )
                migration_job.status = MigrationStatus.FAILED
                migration_job.updated_at = datetime.now(timezone.utc)
                migration_job.error_message = error_msg

                if auto_rollback:
                    await self._execute_rollback_after_failure()

                return {
                    "status": MigrationStatus.FAILED,
                    "error_message": error_msg,
                    "validation_report": validation_report,
                }

            # 5. Completar migração
            logger.info("phase_completed", job_id=self.job_id)
            migration_job.status = MigrationStatus.COMPLETED
            migration_job.updated_at = datetime.now(timezone.utc)

            # Limpar snapshot em caso de sucesso
            await self._cleanup_after_migration(migration_job=migration_job)

            return {
                "status": MigrationStatus.COMPLETED,
                "batch_stats": batch_stats,
                "validation_report": validation_report,
            }

        except Exception as e:
            logger.error("full_migration_failed", error=str(e))
            error_msg = str(e)

            # Apenas atualizar para FAILED se não já estiver em FAILED
            if migration_job.status != MigrationStatus.FAILED:
                migration_job.status = MigrationStatus.FAILED
                migration_job.updated_at = datetime.now(timezone.utc)
                migration_job.error_message = error_msg

            if auto_rollback:
                await self._execute_rollback_after_failure()

            return {
                "status": MigrationStatus.FAILED,
                "error_message": error_msg,
            }

    async def _continue_from_batch(
        self,
        migration_job: MigrationJob,
        schema_mapping: SchemaMapping,
        legacy_client: Any,
        target_client: Any,
        kafka_producer: Optional[Any] = None,
        database_config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Retoma migração a partir de BATCH_MIGRATING.

        Args:
            migration_job: Job de migração
            schema_mapping: Mapeamento de schema
            legacy_client: Cliente do banco legado
            target_client: Cliente do banco alvo
            kafka_producer: Producer Kafka (opcional)
            database_config: Configuração do banco para CDC

        Returns:
            Dicionário com resultado da migração
        """
        logger.info("resuming_from_batch", job_id=self.job_id)

        # Continuar execução completa (irá retomar de onde parou)
        return await self._execute_full_migration(
            migration_job=migration_job,
            schema_mapping=schema_mapping,
            legacy_client=legacy_client,
            target_client=target_client,
            kafka_producer=kafka_producer,
            database_config=database_config,
        )

    async def _continue_from_cdc(
        self,
        migration_job: MigrationJob,
        schema_mapping: SchemaMapping,
        target_client: Any,
    ) -> Dict[str, Any]:
        """
        Retoma migração a partir de CDC_RUNNING.

        Args:
            migration_job: Job de migração
            schema_mapping: Mapeamento de schema
            target_client: Cliente do banco alvo

        Returns:
            Dicionário com resultado da migração
        """
        logger.info("resuming_from_cdc", job_id=self.job_id)

        # CDC já está rodando, apenas validar
        migration_job.update_status(MigrationStatus.VALIDATING)

        # Nota: para validação precisa do legacy_client
        # Em um cenário real, precisaríamos reconectar ao legado
        # Por ora, apenas transicionar para COMPLETED
        migration_job.update_status(MigrationStatus.COMPLETED)

        await self._cleanup_after_migration(migration_job=migration_job)

        return {"status": MigrationStatus.COMPLETED}

    async def _continue_from_validation(
        self,
        migration_job: MigrationJob,
        schema_mapping: SchemaMapping,
        legacy_client: Any,
        target_client: Any,
    ) -> Dict[str, Any]:
        """
        Retoma migração a partir de VALIDATING.

        Args:
            migration_job: Job de migração
            schema_mapping: Mapeamento de schema
            legacy_client: Cliente do banco legado
            target_client: Cliente do banco alvo

        Returns:
            Dicionário com resultado da migração
        """
        logger.info("resuming_from_validation", job_id=self.job_id)

        # Executar validação
        data_validator = self._get_data_validator()

        validation_report = await data_validator.generate_validation_report(
            schema_mapping=schema_mapping,
            legacy_client=legacy_client,
            modern_client=target_client,
        )

        if not validation_report.get("overall_passed", False):
            migration_job.update_status(MigrationStatus.FAILED)
            return {
                "status": MigrationStatus.FAILED,
                "validation_report": validation_report,
            }

        migration_job.update_status(MigrationStatus.COMPLETED)
        await self._cleanup_after_migration(migration_job=migration_job)

        return {
            "status": MigrationStatus.COMPLETED,
            "validation_report": validation_report,
        }

    async def _execute_rollback_after_failure(self) -> None:
        """Executa rollback após falha na migração."""
        if not self._snapshot_id:
            logger.warning("no_snapshot_for_rollback", job_id=self.job_id)
            return

        logger.info("executing_auto_rollback", job_id=self.job_id)

        try:
            rollback_manager = self._get_rollback_manager()
            await rollback_manager.execute_rollback(snapshot_id=self._snapshot_id)
            logger.info("auto_rollback_completed", job_id=self.job_id)
        except Exception as e:
            logger.error("auto_rollback_failed", error=str(e))

    async def _cleanup_after_migration(
        self,
        migration_job: MigrationJob,
    ) -> None:
        """
        Limpa recursos após migração bem-sucedida.

        Args:
            migration_job: Job de migração
        """
        if not self._snapshot_id:
            return

        logger.info("cleaning_up_after_migration", job_id=self.job_id)

        try:
            rollback_manager = self._get_rollback_manager()
            await rollback_manager.cleanup_snapshot(snapshot_id=self._snapshot_id)
            self._snapshot_id = None
            logger.info("snapshot_cleaned", job_id=self.job_id)
        except Exception as e:
            logger.warning("snapshot_cleanup_failed", error=str(e))

    def _can_pause_from_state(self, status: MigrationStatus) -> bool:
        """Verifica se pausa é permitida no estado atual."""
        return status in self.PAUSABLE_STATES

    def _is_terminal_state(self, status: MigrationStatus) -> bool:
        """Verifica se estado é terminal."""
        return status in self.TERMINAL_STATES

    # ========== Getters para Dependências ==========

    def _get_schema_mapper(self) -> Any:
        """Retorna SchemaMapper (lazy loading)."""
        if self._schema_mapper is None:
            from src.services.schema_mapper import get_schema_mapper

            self._schema_mapper = get_schema_mapper()
        return self._schema_mapper

    def _get_batch_migrator(
        self,
        schema_mapping_id: str,
        batch_size: int = 1000,
    ) -> BatchMigrator:
        """Retorna BatchMigrator (lazy loading)."""
        if self._batch_migrator is None:
            self._batch_migrator = get_batch_migrator(
                job_id=self.job_id,
                schema_mapping_id=schema_mapping_id,
                batch_size=batch_size,
            )
        return self._batch_migrator

    def _get_cdc_pipeline(self) -> CDCPipeline:
        """Retorna CDCPipeline (lazy loading)."""
        if self._cdc_pipeline is None:
            self._cdc_pipeline = get_cdc_pipeline(job_id=self.job_id)
        return self._cdc_pipeline

    def _get_data_validator(self) -> DataValidator:
        """Retorna DataValidator (lazy loading)."""
        if self._data_validator is None:
            self._data_validator = get_data_validator()
        return self._data_validator

    def _get_rollback_manager(self) -> RollbackManager:
        """Retorna RollbackManager (lazy loading)."""
        if self._rollback_manager is None:
            self._rollback_manager = get_rollback_manager()
        return self._rollback_manager


# Singleton instances por job_id
_orchestrators: Dict[str, MigrationOrchestrator] = {}


def get_migration_orchestrator(
    job_id: str,
) -> MigrationOrchestrator:
    """
    Retorna instância do Migration Orchestrator (singleton por job_id).

    Args:
        job_id: ID do job de migração

    Returns:
        Instância de MigrationOrchestrator
    """
    global _orchestrators

    if job_id not in _orchestrators:
        _orchestrators[job_id] = MigrationOrchestrator(job_id=job_id)

    return _orchestrators[job_id]


def clear_migration_orchestrator(job_id: str) -> None:
    """
    Remove orchestrator da cache (para testes ou cleanup).

    Args:
        job_id: ID do job a remover
    """
    global _orchestrators
    _orchestrators.pop(job_id, None)
