"""
Testes unitários para Migration Orchestrator.

Cobre orquestração completa de migração, coordenação de componentes
e gerenciamento de transições de estado.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.migration import (
    FieldMapping,
    MigrationJob,
    MigrationStatus,
    SchemaMapping,
    TableMapping,
)
from src.services.migration_orchestrator import (
    MigrationOrchestrator,
    MigrationOrchestratorError,
    PhaseTransitionError,
)


@pytest.fixture
def sample_table_mapping():
    """Retorna mapeamento de tabela para testes."""
    return TableMapping(
        source_schema="public",
        source_table="users",
        target_table="users",
        target_schema="public",
        fields=[
            FieldMapping(
                source_field="id",
                target_field="id",
                data_type="uuid",
                nullable=False,
                is_primary_key=True,
            ),
            FieldMapping(
                source_field="name",
                target_field="name",
                data_type="text",
                nullable=True,
            ),
            FieldMapping(
                source_field="email",
                target_field="email",
                data_type="text",
                nullable=False,
            ),
        ],
        estimated_rows=1000,
    )


@pytest.fixture
def sample_schema_mapping(sample_table_mapping):
    """Retorna schema mapping para testes."""
    return SchemaMapping(
        legacy_connection_id="legacy-conn-1",
        nhm_target="feature-store",
        tables=[sample_table_mapping],
    )


@pytest.fixture
def sample_migration_job(sample_schema_mapping):
    """Retorna migration job para testes."""
    return MigrationJob(
        job_id="test-job-1",
        schema_mapping_id="mapping-1",
        status=MigrationStatus.PENDING,
        batch_size=100,
        total_rows=1000,
    )


@pytest.fixture
def mock_legacy_client():
    """Mock do cliente PostgreSQL legado."""
    client = MagicMock()
    client.fetch_batch = AsyncMock()
    client.get_table_count = AsyncMock(return_value=1000)
    client.get_table_schema = AsyncMock(return_value=[])
    client.get_primary_keys = AsyncMock(return_value=[])
    client.get_foreign_keys = AsyncMock(return_value=[])
    client.get_indexes = AsyncMock(return_value=[])
    client.get_tables = AsyncMock(return_value=["users"])
    client.execute_query = AsyncMock()
    client.is_connected = AsyncMock(return_value=True)
    client.connect = AsyncMock()
    return client


@pytest.fixture
def mock_target_client():
    """Mock do cliente alvo."""
    client = MagicMock()
    client.insert_batch = AsyncMock()
    client.insert = AsyncMock()
    client.update = AsyncMock()
    client.delete = AsyncMock()
    client.insert_many = AsyncMock()
    client.execute = AsyncMock()
    client.is_connected = AsyncMock(return_value=True)
    client.connect = AsyncMock()
    return client


@pytest.fixture
def mock_kafka_producer():
    """Mock do Kafka producer."""
    producer = MagicMock()
    producer.produce = AsyncMock()
    producer.send_and_wait = AsyncMock()
    producer.flush = AsyncMock()
    return producer


@pytest.fixture
def mock_rollback_manager():
    """Mock do RollbackManager."""
    manager = MagicMock()
    manager.create_snapshot = AsyncMock(return_value="snap-123")
    manager.execute_rollback = AsyncMock(
        return_value=MagicMock(
            tables_processed=1,
            rows_restored=1000,
            tables_failed=0,
            duration_seconds=5.0,
        )
    )
    manager.cleanup_snapshot = AsyncMock(return_value=True)
    return manager


@pytest.fixture
def mock_data_validator():
    """Mock do DataValidator."""
    validator = MagicMock()
    validator.generate_validation_report = AsyncMock(
        return_value={
            "overall_passed": True,
            "total_validations": 3,
            "passed_validations": 3,
            "failed_validations": 0,
            "results": [],
        }
    )
    return validator


@pytest.fixture
def mock_batch_migrator():
    """Mock do BatchMigrator."""
    migrator = MagicMock()
    migrator.run_batch_migration = AsyncMock(
        return_value={
            "job_id": "test-job-1",
            "total_migrated": 1000,
            "total_failed": 0,
            "batches_processed": 10,
            "tables_processed": 1,
        }
    )
    migrator.pause_migration = MagicMock()
    migrator.resume_migration = MagicMock()
    migrator.stop_migration = MagicMock()
    migrator.get_migration_progress = MagicMock(
        return_value={
            "job_id": "test-job-1",
            "total_migrated": 500,
            "total_failed": 0,
            "running": True,
            "paused": False,
        }
    )
    return migrator


@pytest.fixture
def mock_cdc_pipeline():
    """Mock do CDCPipeline."""
    pipeline = MagicMock()
    pipeline.create_connector = AsyncMock(return_value="connector-123")
    pipeline.start_cdc = AsyncMock()
    pipeline.stop_cdc = AsyncMock()
    pipeline.get_cdc_status = AsyncMock(
        return_value=MagicMock(
            connector_id="connector-123",
            connector_state="RUNNING",
            running=True,
            lag_ms=0,
        )
    )
    return pipeline


@pytest.fixture
def mock_schema_mapper():
    """Mock do SchemaMapper."""
    mapper = MagicMock()
    mapper.analyze_legacy_schema = AsyncMock(
        return_value={
            "schema": "public",
            "tables": [
                {
                    "name": "users",
                    "columns": [
                        {
                            "column_name": "id",
                            "data_type": "uuid",
                            "is_nullable": "NO",
                        }
                    ],
                    "primary_keys": ["id"],
                    "foreign_keys": [],
                    "row_count": 1000,
                }
            ],
            "relationships": [],
        }
    )
    mapper.generate_schema_mapping = AsyncMock(return_value=sample_schema_mapping)
    mapper.approve_mapping = AsyncMock(return_value=sample_schema_mapping)
    return mapper


class TestMigrationOrchestrator:
    """Testes para MigrationOrchestrator."""

    def test_initialization(self, sample_migration_job):
        """Verifica inicialização do MigrationOrchestrator."""
        orchestrator = MigrationOrchestrator(job_id=sample_migration_job.job_id)

        assert orchestrator.job_id == sample_migration_job.job_id
        assert orchestrator._paused is False
        assert orchestrator._running is False
        assert orchestrator._snapshot_id is None

    @pytest.mark.asyncio
    async def test_start_migration_from_pending(
        self,
        sample_migration_job,
        sample_schema_mapping,
        mock_legacy_client,
        mock_target_client,
        mock_kafka_producer,
        mock_rollback_manager,
        mock_data_validator,
        mock_batch_migrator,
        mock_cdc_pipeline,
        mock_schema_mapper,
    ):
        """Verifica início de migração do estado PENDING."""
        orchestrator = MigrationOrchestrator(
            job_id=sample_migration_job.job_id,
            schema_mapper=mock_schema_mapper,
            batch_migrator=mock_batch_migrator,
            cdc_pipeline=mock_cdc_pipeline,
            data_validator=mock_data_validator,
            rollback_manager=mock_rollback_manager,
        )

        job = await orchestrator.start_migration(
            migration_job=sample_migration_job,
            schema_mapping=sample_schema_mapping,
            legacy_client=mock_legacy_client,
            target_client=mock_target_client,
            kafka_producer=mock_kafka_producer,
            database_config={
                "hostname": "localhost",
                "port": 5432,
                "user": "test",
                "password": "test",
                "dbname": "legacy_db",
            },
        )

        # Verificar transições de estado
        assert job.status == MigrationStatus.COMPLETED
        assert mock_rollback_manager.create_snapshot.called
        assert mock_batch_migrator.run_batch_migration.called
        assert mock_cdc_pipeline.start_cdc.called
        assert mock_data_validator.generate_validation_report.called

    @pytest.mark.asyncio
    async def test_start_migration_with_approval_required(
        self,
        sample_migration_job,
        sample_schema_mapping,
        mock_legacy_client,
        mock_target_client,
        mock_kafka_producer,
        mock_rollback_manager,
        mock_data_validator,
        mock_batch_migrator,
        mock_cdc_pipeline,
        mock_schema_mapper,
    ):
        """Verifica que migração para em MAPPING aguardando aprovação."""
        orchestrator = MigrationOrchestrator(
            job_id=sample_migration_job.job_id,
            schema_mapper=mock_schema_mapper,
            batch_migrator=mock_batch_migrator,
            cdc_pipeline=mock_cdc_pipeline,
            data_validator=mock_data_validator,
            rollback_manager=mock_rollback_manager,
        )

        # Iniciar sem aprovação prévia
        sample_schema_mapping.metadata = {"approved": False}

        with patch.object(orchestrator, "_execute_full_migration", AsyncMock()):
            job = await orchestrator.start_migration(
                migration_job=sample_migration_job,
                schema_mapping=sample_schema_mapping,
                legacy_client=mock_legacy_client,
                target_client=mock_target_client,
                kafka_producer=mock_kafka_producer,
                database_config={
                    "hostname": "localhost",
                    "port": 5432,
                    "user": "test",
                    "password": "test",
                    "dbname": "legacy_db",
                },
                auto_approve=False,
            )

        # Deve parar em MAPPING (aguardando aprovação humana)
        assert job.status == MigrationStatus.MAPPING

    @pytest.mark.asyncio
    async def test_approve_next_phase_from_mapping(
        self,
        sample_migration_job,
        sample_schema_mapping,
    ):
        """Verifica aprovação de próxima fase a partir de MAPPING."""
        orchestrator = MigrationOrchestrator(
            job_id=sample_migration_job.job_id,
        )

        sample_migration_job.status = MigrationStatus.MAPPING

        approved = await orchestrator.approve_next_phase(
            migration_job=sample_migration_job,
            schema_mapping=sample_schema_mapping,
            approved_by="test-user",
        )

        assert approved is True
        assert sample_migration_job.status == MigrationStatus.MAPPING_APPROVED
        assert sample_schema_mapping.metadata.get("approved") is True
        assert sample_schema_mapping.metadata.get("approved_by") == "test-user"

    @pytest.mark.asyncio
    async def test_approve_next_phase_invalid_transition(
        self,
        sample_migration_job,
        sample_schema_mapping,
    ):
        """Verifica erro ao aprovar fase inválida."""
        orchestrator = MigrationOrchestrator(
            job_id=sample_migration_job.job_id,
        )

        sample_migration_job.status = MigrationStatus.PENDING

        with pytest.raises(PhaseTransitionError, match="Transição de fase inválida"):
            await orchestrator.approve_next_phase(
                migration_job=sample_migration_job,
                schema_mapping=sample_schema_mapping,
                approved_by="test-user",
            )

    @pytest.mark.asyncio
    async def test_pause_migration(
        self,
        sample_migration_job,
        mock_batch_migrator,
        mock_cdc_pipeline,
    ):
        """Verifica pausa de migração em andamento."""
        orchestrator = MigrationOrchestrator(
            job_id=sample_migration_job.job_id,
            batch_migrator=mock_batch_migrator,
            cdc_pipeline=mock_cdc_pipeline,
        )

        sample_migration_job.status = MigrationStatus.BATCH_MIGRATING

        paused = await orchestrator.pause_migration(migration_job=sample_migration_job)

        assert paused is True
        assert mock_batch_migrator.pause_migration.called
        assert orchestrator._paused is True

    @pytest.mark.asyncio
    async def test_pause_migration_invalid_state(
        self,
        sample_migration_job,
        mock_batch_migrator,
    ):
        """Verifica erro ao pausar em estado inválido."""
        orchestrator = MigrationOrchestrator(
            job_id=sample_migration_job.job_id,
            batch_migrator=mock_batch_migrator,
        )

        sample_migration_job.status = MigrationStatus.PENDING

        with pytest.raises(PhaseTransitionError, match="não pode ser pausada"):
            await orchestrator.pause_migration(migration_job=sample_migration_job)

    @pytest.mark.asyncio
    async def test_resume_migration(
        self,
        sample_migration_job,
        mock_batch_migrator,
        mock_cdc_pipeline,
    ):
        """Verifica retomada de migração pausada."""
        orchestrator = MigrationOrchestrator(
            job_id=sample_migration_job.job_id,
            batch_migrator=mock_batch_migrator,
            cdc_pipeline=mock_cdc_pipeline,
        )

        sample_migration_job.status = MigrationStatus.BATCH_MIGRATING
        orchestrator._paused = True

        resumed = await orchestrator.resume_migration(migration_job=sample_migration_job)

        assert resumed is True
        assert mock_batch_migrator.resume_migration.called
        assert orchestrator._paused is False

    @pytest.mark.asyncio
    async def test_resume_migration_not_paused(
        self,
        sample_migration_job,
        mock_batch_migrator,
    ):
        """Verifica erro ao retomar migração não pausada."""
        orchestrator = MigrationOrchestrator(
            job_id=sample_migration_job.job_id,
            batch_migrator=mock_batch_migrator,
        )

        sample_migration_job.status = MigrationStatus.BATCH_MIGRATING
        orchestrator._paused = False

        with pytest.raises(PhaseTransitionError, match="não está pausada"):
            await orchestrator.resume_migration(migration_job=sample_migration_job)

    @pytest.mark.asyncio
    async def test_rollback_migration(
        self,
        sample_migration_job,
        mock_rollback_manager,
        mock_cdc_pipeline,
    ):
        """Verifica rollback de migração."""
        orchestrator = MigrationOrchestrator(
            job_id=sample_migration_job.job_id,
            rollback_manager=mock_rollback_manager,
            cdc_pipeline=mock_cdc_pipeline,
        )

        orchestrator._snapshot_id = "snap-123"
        sample_migration_job.status = MigrationStatus.VALIDATING

        result = await orchestrator.rollback_migration(
            migration_job=sample_migration_job,
        )

        assert result["snapshot_id"] == "snap-123"
        assert result["tables_processed"] == 1
        assert sample_migration_job.status == MigrationStatus.ROLLED_BACK

    @pytest.mark.asyncio
    async def test_rollback_migration_no_snapshot(
        self,
        sample_migration_job,
        mock_rollback_manager,
    ):
        """Verifica erro ao rollback sem snapshot."""
        orchestrator = MigrationOrchestrator(
            job_id=sample_migration_job.job_id,
            rollback_manager=mock_rollback_manager,
        )

        sample_migration_job.status = MigrationStatus.VALIDATING

        with pytest.raises(MigrationOrchestratorError, match="Nenhum snapshot disponível"):
            await orchestrator.rollback_migration(migration_job=sample_migration_job)

    @pytest.mark.asyncio
    async def test_get_migration_status(
        self,
        sample_migration_job,
        mock_batch_migrator,
    ):
        """Verifica obtenção de status de migração."""
        orchestrator = MigrationOrchestrator(
            job_id=sample_migration_job.job_id,
            batch_migrator=mock_batch_migrator,
        )

        sample_migration_job.status = MigrationStatus.BATCH_MIGRATING
        orchestrator._running = True

        status = await orchestrator.get_migration_status(migration_job=sample_migration_job)

        assert status["job_id"] == sample_migration_job.job_id
        assert status["status"] == MigrationStatus.BATCH_MIGRATING
        assert status["running"] is True

    @pytest.mark.asyncio
    async def test_execute_full_migration_flow(
        self,
        sample_migration_job,
        sample_schema_mapping,
        mock_legacy_client,
        mock_target_client,
        mock_kafka_producer,
        mock_rollback_manager,
        mock_data_validator,
        mock_batch_migrator,
        mock_cdc_pipeline,
    ):
        """Verifica fluxo completo de migração."""
        orchestrator = MigrationOrchestrator(
            job_id=sample_migration_job.job_id,
            batch_migrator=mock_batch_migrator,
            cdc_pipeline=mock_cdc_pipeline,
            data_validator=mock_data_validator,
            rollback_manager=mock_rollback_manager,
        )

        # Schema mapping já aprovado
        sample_schema_mapping.metadata["approved"] = True
        sample_migration_job.status = MigrationStatus.MAPPING_APPROVED

        result = await orchestrator._execute_full_migration(
            migration_job=sample_migration_job,
            schema_mapping=sample_schema_mapping,
            legacy_client=mock_legacy_client,
            target_client=mock_target_client,
            kafka_producer=mock_kafka_producer,
            database_config={
                "hostname": "localhost",
                "port": 5432,
                "user": "test",
                "password": "test",
                "dbname": "legacy_db",
            },
        )

        assert result["status"] == MigrationStatus.COMPLETED
        assert mock_rollback_manager.create_snapshot.called
        assert mock_batch_migrator.run_batch_migration.called
        assert mock_cdc_pipeline.start_cdc.called
        assert mock_data_validator.generate_validation_report.called

    @pytest.mark.asyncio
    async def test_migration_failure_triggers_rollback(
        self,
        sample_migration_job,
        sample_schema_mapping,
        mock_legacy_client,
        mock_target_client,
        mock_kafka_producer,
        mock_rollback_manager,
        mock_data_validator,
        mock_batch_migrator,
        mock_cdc_pipeline,
    ):
        """Verifica que falha na migração aciona rollback."""
        orchestrator = MigrationOrchestrator(
            job_id=sample_migration_job.job_id,
            batch_migrator=mock_batch_migrator,
            cdc_pipeline=mock_cdc_pipeline,
            data_validator=mock_data_validator,
            rollback_manager=mock_rollback_manager,
        )

        sample_schema_mapping.metadata["approved"] = True
        sample_migration_job.status = MigrationStatus.MAPPING_APPROVED
        orchestrator._snapshot_id = "snap-123"

        # Simular falha no batch migrator
        mock_batch_migrator.run_batch_migration.side_effect = Exception("Migration failed")

        result = await orchestrator._execute_full_migration(
            migration_job=sample_migration_job,
            schema_mapping=sample_schema_mapping,
            legacy_client=mock_legacy_client,
            target_client=mock_target_client,
            kafka_producer=mock_kafka_producer,
            database_config={
                "hostname": "localhost",
                "port": 5432,
                "user": "test",
                "password": "test",
                "dbname": "legacy_db",
            },
            auto_rollback=True,
        )

        assert result["status"] == MigrationStatus.FAILED
        assert mock_rollback_manager.execute_rollback.called

    @pytest.mark.asyncio
    async def test_cleanup_after_successful_migration(
        self,
        sample_migration_job,
        mock_rollback_manager,
    ):
        """Verifica limpeza de snapshot após migração bem-sucedida."""
        orchestrator = MigrationOrchestrator(
            job_id=sample_migration_job.job_id,
            rollback_manager=mock_rollback_manager,
        )

        orchestrator._snapshot_id = "snap-123"
        sample_migration_job.status = MigrationStatus.COMPLETED

        await orchestrator._cleanup_after_migration(migration_job=sample_migration_job)

        assert mock_rollback_manager.cleanup_snapshot.called
        # Verificar que o snapshot_id correto foi passado como keyword argument
        assert (
            mock_rollback_manager.cleanup_snapshot.call_args.kwargs.get("snapshot_id") == "snap-123"
        )

    @pytest.mark.asyncio
    async def test_validation_failure_prevents_completion(
        self,
        sample_migration_job,
        sample_schema_mapping,
        mock_legacy_client,
        mock_target_client,
        mock_kafka_producer,
        mock_rollback_manager,
        mock_data_validator,
        mock_batch_migrator,
        mock_cdc_pipeline,
    ):
        """Verifica que falha na validação impede conclusão."""
        orchestrator = MigrationOrchestrator(
            job_id=sample_migration_job.job_id,
            batch_migrator=mock_batch_migrator,
            cdc_pipeline=mock_cdc_pipeline,
            data_validator=mock_data_validator,
            rollback_manager=mock_rollback_manager,
        )

        sample_schema_mapping.metadata["approved"] = True
        sample_migration_job.status = MigrationStatus.MAPPING_APPROVED
        orchestrator._snapshot_id = "snap-123"

        # Simular falha na validação
        mock_data_validator.generate_validation_report.return_value = {
            "overall_passed": False,
            "total_validations": 3,
            "passed_validations": 2,
            "failed_validations": 1,
            "results": [],
        }

        result = await orchestrator._execute_full_migration(
            migration_job=sample_migration_job,
            schema_mapping=sample_schema_mapping,
            legacy_client=mock_legacy_client,
            target_client=mock_target_client,
            kafka_producer=mock_kafka_producer,
            database_config={
                "hostname": "localhost",
                "port": 5432,
                "user": "test",
                "password": "test",
                "dbname": "legacy_db",
            },
        )

        assert result["status"] == MigrationStatus.FAILED

    @pytest.mark.asyncio
    async def test_resume_from_batch_migrating_state(
        self,
        sample_migration_job,
        sample_schema_mapping,
        mock_legacy_client,
        mock_target_client,
        mock_kafka_producer,
        mock_rollback_manager,
        mock_data_validator,
        mock_batch_migrator,
        mock_cdc_pipeline,
    ):
        """Verifica retomada de migração do estado BATCH_MIGRATING."""
        orchestrator = MigrationOrchestrator(
            job_id=sample_migration_job.job_id,
            batch_migrator=mock_batch_migrator,
            cdc_pipeline=mock_cdc_pipeline,
            data_validator=mock_data_validator,
            rollback_manager=mock_rollback_manager,
        )

        sample_schema_mapping.metadata["approved"] = True
        sample_migration_job.status = MigrationStatus.BATCH_MIGRATING
        orchestrator._snapshot_id = "snap-123"

        with patch.object(orchestrator, "_continue_from_batch", AsyncMock()):
            await orchestrator._execute_full_migration(
                migration_job=sample_migration_job,
                schema_mapping=sample_schema_mapping,
                legacy_client=mock_legacy_client,
                target_client=mock_target_client,
                kafka_producer=mock_kafka_producer,
                database_config={
                    "hostname": "localhost",
                    "port": 5432,
                    "user": "test",
                    "password": "test",
                    "dbname": "legacy_db",
                },
            )

    @pytest.mark.asyncio
    async def test_continue_from_cdc_running_state(
        self,
        sample_migration_job,
        sample_schema_mapping,
        mock_legacy_client,
        mock_target_client,
        mock_kafka_producer,
        mock_data_validator,
        mock_cdc_pipeline,
    ):
        """Verifica continuação a partir do estado CDC_RUNNING."""
        orchestrator = MigrationOrchestrator(
            job_id=sample_migration_job.job_id,
            cdc_pipeline=mock_cdc_pipeline,
            data_validator=mock_data_validator,
        )

        sample_migration_job.status = MigrationStatus.CDC_RUNNING

        result = await orchestrator._continue_from_cdc(
            migration_job=sample_migration_job,
            schema_mapping=sample_schema_mapping,
            target_client=mock_target_client,
        )

        assert result["status"] in (MigrationStatus.COMPLETED, MigrationStatus.FAILED)

    def test_can_pause_from_state(self):
        """Verifica estados onde pausa é permitida."""
        orchestrator = MigrationOrchestrator(job_id="test-job")

        assert orchestrator._can_pause_from_state(MigrationStatus.BATCH_MIGRATING) is True
        assert orchestrator._can_pause_from_state(MigrationStatus.CDC_RUNNING) is True
        assert orchestrator._can_pause_from_state(MigrationStatus.VALIDATING) is True
        assert orchestrator._can_pause_from_state(MigrationStatus.PENDING) is False
        assert orchestrator._can_pause_from_state(MigrationStatus.COMPLETED) is False

    def test_is_terminal_state(self):
        """Verifica detecção de estados terminais."""
        orchestrator = MigrationOrchestrator(job_id="test-job")

        assert orchestrator._is_terminal_state(MigrationStatus.COMPLETED) is True
        assert orchestrator._is_terminal_state(MigrationStatus.FAILED) is True
        assert orchestrator._is_terminal_state(MigrationStatus.ROLLED_BACK) is True
        assert orchestrator._is_terminal_state(MigrationStatus.BATCH_MIGRATING) is False


class TestMigrationOrchestratorErrorHandling:
    """Testes para tratamento de erros no MigrationOrchestrator."""

    @pytest.mark.asyncio
    async def test_snapshot_failure_propagates(
        self,
        sample_migration_job,
        sample_schema_mapping,
        mock_legacy_client,
        mock_target_client,
        mock_kafka_producer,
        mock_rollback_manager,
    ):
        """Verifica que falha na criação de snapshot propaga."""
        orchestrator = MigrationOrchestrator(
            job_id=sample_migration_job.job_id,
            rollback_manager=mock_rollback_manager,
        )

        mock_rollback_manager.create_snapshot.side_effect = Exception("S3 connection failed")

        with pytest.raises(MigrationOrchestratorError, match="Falha ao criar snapshot"):
            await orchestrator._create_snapshot(
                migration_job=sample_migration_job,
                schema_mapping=sample_schema_mapping,
            )

    @pytest.mark.asyncio
    async def test_invalid_status_transition_raises_error(
        self,
        sample_migration_job,
    ):
        """Verifica que transição de status inválida levanta erro."""
        MigrationOrchestrator(job_id=sample_migration_job.job_id)

        sample_migration_job.status = MigrationStatus.COMPLETED

        with pytest.raises(ValueError):
            sample_migration_job.update_status(MigrationStatus.ANALYZING)


class TestMigrationOrchestratorSingletons:
    """Testes para funções singleton do MigrationOrchestrator."""

    def test_get_migration_orchestrator_returns_singleton(self):
        """Verifica que get_migration_orchestrator retorna singleton."""
        from src.services.migration_orchestrator import (
            clear_migration_orchestrator,
            get_migration_orchestrator,
        )

        # Limpar singleton primeiro
        clear_migration_orchestrator("test-job")

        orchestrator1 = get_migration_orchestrator(job_id="test-job")
        orchestrator2 = get_migration_orchestrator(job_id="test-job")

        assert orchestrator1 is orchestrator2

    def test_clear_migration_orchestrator(self):
        """Verifica limpeza de singleton do orchestrator."""
        from src.services.migration_orchestrator import (
            clear_migration_orchestrator,
            get_migration_orchestrator,
        )

        orchestrator1 = get_migration_orchestrator(job_id="test-job-2")
        clear_migration_orchestrator("test-job-2")

        orchestrator2 = get_migration_orchestrator(job_id="test-job-2")

        # Não deve ser a mesma instância
        assert orchestrator1 is not orchestrator2
