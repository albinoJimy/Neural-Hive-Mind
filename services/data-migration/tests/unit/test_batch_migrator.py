"""
Testes unitários para Batch Migrator.

Corre migração de dados históricos em batches, aplicando transformações
e reportando progresso via Kafka events.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models.migration import (
    FieldMapping,
    MigrationJob,
    MigrationStatus,
    SchemaMapping,
    TableMapping,
)
from src.services.batch_migrator import (
    BatchMigrator,
    BatchMigratorError,
    MigrationProgress,
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
            FieldMapping(
                source_field="created_at",
                target_field="created_at",
                data_type="timestamp",
                nullable=True,
                transform="CAST_TIMESTAMP_UTC",
            ),
        ],
        estimated_rows=10000,
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
        status=MigrationStatus.MAPPING,
        batch_size=100,
        total_rows=10000,
    )


@pytest.fixture
def mock_legacy_client():
    """Mock do cliente PostgreSQL legado."""
    client = MagicMock()
    client.fetch_batch = AsyncMock()
    client.get_table_count = AsyncMock(return_value=10000)
    client.is_connected = AsyncMock(return_value=True)
    return client


@pytest.fixture
def mock_target_client():
    """Mock do cliente alvo (MongoDB ou moderno)."""
    client = MagicMock()
    client.insert_batch = AsyncMock()
    client.is_connected = AsyncMock(return_value=True)
    return client


@pytest.fixture
def mock_kafka_producer():
    """Mock do Kafka producer."""
    producer = MagicMock()
    producer.produce = AsyncMock()
    producer.flush = AsyncMock()
    return producer


class TestMigrationProgress:
    """Testes para MigrationProgress."""

    def test_initialization(self):
        """Verifica inicialização do MigrationProgress."""
        progress = MigrationProgress(
            job_id="job-1",
            table="users",
            total_rows=10000,
        )

        assert progress.job_id == "job-1"
        assert progress.table == "users"
        assert progress.total_rows == 10000
        assert progress.rows_migrated == 0
        assert progress.rows_failed == 0
        assert progress.batches_processed == 0
        assert progress.status == "pending"

    def test_update_migrated(self):
        """Verifica atualização de linhas migradas."""
        progress = MigrationProgress(
            job_id="job-1",
            table="users",
            total_rows=10000,
        )

        progress.update_migrated(1000)
        assert progress.rows_migrated == 1000
        assert progress.batches_processed == 1
        assert progress.progress_percentage == 10.0

        progress.update_migrated(500)
        assert progress.rows_migrated == 1500
        assert progress.progress_percentage == 15.0

    def test_update_failed(self):
        """Verifica atualização de linhas falhadas."""
        progress = MigrationProgress(
            job_id="job-1",
            table="users",
            total_rows=10000,
        )

        progress.update_failed(5)
        assert progress.rows_failed == 5

    def test_to_dict(self):
        """Verifica conversão para dicionário."""
        progress = MigrationProgress(
            job_id="job-1",
            table="users",
            total_rows=10000,
            rows_migrated=5000,
            rows_failed=10,
        )
        progress.update_migrated(0)  # Para calcular percentage

        data = progress.to_dict()

        assert data["job_id"] == "job-1"
        assert data["table"] == "users"
        assert data["total_rows"] == 10000
        assert data["rows_migrated"] == 5000
        assert data["rows_failed"] == 10
        assert data["progress_percentage"] == 50.0


class TestBatchMigrator:
    """Testes para BatchMigrator."""

    def test_initialization(self, sample_migration_job):
        """Verifica inicialização do BatchMigrator."""
        migrator = BatchMigrator(
            job_id=sample_migration_job.job_id,
            schema_mapping_id=sample_migration_job.schema_mapping_id,
            batch_size=sample_migration_job.batch_size,
        )

        assert migrator.job_id == sample_migration_job.job_id
        assert migrator.schema_mapping_id == sample_migration_job.schema_mapping_id
        assert migrator.batch_size == sample_migration_job.batch_size
        assert migrator._paused is False
        assert migrator._running is False

    @pytest.mark.asyncio
    async def test_run_batch_migration_success(
        self,
        sample_migration_job,
        sample_schema_mapping,
        mock_legacy_client,
        mock_target_client,
        mock_kafka_producer,
    ):
        """Verifica execução de migração batch com sucesso."""
        migrator = BatchMigrator(
            job_id=sample_migration_job.job_id,
            schema_mapping_id=sample_migration_job.schema_mapping_id,
            batch_size=100,
        )

        # Simular batches
        batch1 = [
            {"id": f"id-{i}", "name": f"User {i}", "email": f"user{i}@test.com"} for i in range(100)
        ]
        batch2 = [
            {"id": f"id-{i}", "name": f"User {i}", "email": f"user{i}@test.com"}
            for i in range(100, 200)
        ]

        mock_legacy_client.fetch_batch.side_effect = [
            batch1,
            batch2,
            [],
        ]  # Ultimo vazio sinaliza fim

        stats = await migrator.run_batch_migration(
            legacy_client=mock_legacy_client,
            target_client=mock_target_client,
            schema_mapping=sample_schema_mapping,
            kafka_producer=mock_kafka_producer,
        )

        assert stats["total_migrated"] == 200
        assert stats["total_failed"] == 0
        assert stats["batches_processed"] == 2
        assert stats["tables_processed"] == 1

        # Verificar que insert_batch foi chamado
        assert mock_target_client.insert_batch.call_count == 2

        # Verificar que eventos Kafka foram enviados
        assert mock_kafka_producer.produce.call_count >= 2  # started + progress

    @pytest.mark.asyncio
    async def test_run_batch_migration_with_filters(
        self,
        sample_migration_job,
        sample_schema_mapping,
        mock_legacy_client,
        mock_target_client,
        mock_kafka_producer,
    ):
        """Verifica execução de migração com filtro WHERE."""
        # Adicionar filtro à tabela
        sample_schema_mapping.tables[0].source_filter = "deleted_at IS NULL"

        migrator = BatchMigrator(
            job_id=sample_migration_job.job_id,
            schema_mapping_id=sample_migration_job.schema_mapping_id,
            batch_size=100,
        )

        batch = [{"id": "id-1", "name": "User 1", "email": "user1@test.com"}]
        mock_legacy_client.fetch_batch.side_effect = [batch, []]

        await migrator.run_batch_migration(
            legacy_client=mock_legacy_client,
            target_client=mock_target_client,
            schema_mapping=sample_schema_mapping,
            kafka_producer=mock_kafka_producer,
        )

        # Verificar que fetch_batch foi chamado com o filtro
        call_args = mock_legacy_client.fetch_batch.call_args_list
        assert "where" in call_args[0].kwargs
        assert call_args[0].kwargs["where"] == "deleted_at IS NULL"

    @pytest.mark.asyncio
    async def test_run_batch_migration_multiple_tables(
        self,
        sample_migration_job,
        sample_schema_mapping,
        mock_legacy_client,
        mock_target_client,
        mock_kafka_producer,
    ):
        """Verifica migração de múltiplas tabelas."""
        # Adicionar segunda tabela
        table2 = TableMapping(
            source_schema="public",
            source_table="orders",
            target_table="orders",
            fields=[
                FieldMapping(
                    source_field="id",
                    target_field="id",
                    data_type="uuid",
                    nullable=False,
                    is_primary_key=True,
                ),
            ],
            estimated_rows=5000,
        )
        sample_schema_mapping.tables.append(table2)

        migrator = BatchMigrator(
            job_id=sample_migration_job.job_id,
            schema_mapping_id=sample_migration_job.schema_mapping_id,
            batch_size=100,
        )

        # Simular batches para cada tabela
        users_batch = [{"id": "user-1", "name": "User 1"}]
        orders_batch = [{"id": "order-1"}]

        mock_legacy_client.fetch_batch.side_effect = [
            users_batch,  # users batch 1
            [],  # users done
            orders_batch,  # orders batch 1
            [],  # orders done
        ]

        stats = await migrator.run_batch_migration(
            legacy_client=mock_legacy_client,
            target_client=mock_target_client,
            schema_mapping=sample_schema_mapping,
            kafka_producer=mock_kafka_producer,
        )

        assert stats["tables_processed"] == 2
        assert stats["total_migrated"] == 2

    @pytest.mark.asyncio
    async def test_pause_during_migration(
        self,
        sample_migration_job,
        sample_schema_mapping,
        mock_legacy_client,
        mock_target_client,
        mock_kafka_producer,
    ):
        """Verifica pausa durante migração."""
        migrator = BatchMigrator(
            job_id=sample_migration_job.job_id,
            schema_mapping_id=sample_migration_job.schema_mapping_id,
            batch_size=100,
        )

        # Adicionar segunda tabela para pausar entre tabelas
        table2 = TableMapping(
            source_schema="public",
            source_table="orders",
            target_table="orders",
            fields=[
                FieldMapping(
                    source_field="id",
                    target_field="id",
                    data_type="uuid",
                    nullable=False,
                    is_primary_key=True,
                ),
            ],
            estimated_rows=5000,
        )
        sample_schema_mapping.tables.append(table2)

        # Pausar após processar primeira tabela
        original_migrate_table = migrator._migrate_table

        async def migrate_with_pause(*args, **kwargs):
            result = await original_migrate_table(*args, **kwargs)
            # Pausar após primeira tabela
            if not migrator.is_paused():
                migrator.pause_migration()
            return result

        migrator._migrate_table = migrate_with_pause

        # Batches: users completa, orders não inicia porque pausou
        users_batch = [{"id": "id-1"}]
        mock_legacy_client.fetch_batch.side_effect = [
            users_batch,  # users batch 1
            [],  # users done
        ]

        stats = await migrator.run_batch_migration(
            legacy_client=mock_legacy_client,
            target_client=mock_target_client,
            schema_mapping=sample_schema_mapping,
            kafka_producer=mock_kafka_producer,
        )

        # Migração foi interrompida pela pausa
        assert migrator.is_paused() is True
        # Apenas uma tabela foi processada
        assert stats["tables_processed"] == 1

    @pytest.mark.asyncio
    async def test_get_migration_progress(
        self,
        sample_migration_job,
        sample_schema_mapping,
        mock_legacy_client,
        mock_target_client,
        mock_kafka_producer,
    ):
        """Verifica obtenção de progresso da migração."""
        migrator = BatchMigrator(
            job_id=sample_migration_job.job_id,
            schema_mapping_id=sample_migration_job.schema_mapping_id,
            batch_size=100,
        )

        # Iniciar migração e pausar após primeiro batch
        call_count = [0]

        async def mock_fetch(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # Pausar após primeiro batch para verificar progresso
                await asyncio.sleep(0.01)
                migrator.pause_migration()
            return [{"id": f"id-{call_count[0]}"}]

        mock_legacy_client.fetch_batch.side_effect = mock_fetch

        # Executar em background
        task = asyncio.create_task(
            migrator.run_batch_migration(
                legacy_client=mock_legacy_client,
                target_client=mock_target_client,
                schema_mapping=sample_schema_mapping,
                kafka_producer=mock_kafka_producer,
            )
        )

        # Esperar um pouco e verificar progresso durante execução
        await asyncio.sleep(0.05)

        progress = migrator.get_migration_progress()

        assert progress["job_id"] == sample_migration_job.job_id
        assert "total_migrated" in progress
        assert "status" in progress
        # Status deve ser running ou paused
        assert progress["status"] in ("running", "paused")

        # Aguardar task completar (com pausa)
        await asyncio.wait_for(task, timeout=1.0)

        # Verificar progresso final após pausa
        final_progress = migrator.get_migration_progress()
        assert final_progress["job_id"] == sample_migration_job.job_id
        assert "total_migrated" in final_progress

    def test_pause_migration(self, sample_migration_job):
        """Verifica pausa de migração."""
        migrator = BatchMigrator(
            job_id=sample_migration_job.job_id,
            schema_mapping_id=sample_migration_job.schema_mapping_id,
        )

        assert migrator.is_paused() is False

        migrator.pause_migration()

        assert migrator.is_paused() is True

    def test_resume_migration(self, sample_migration_job):
        """Verifica retomada de migração."""
        migrator = BatchMigrator(
            job_id=sample_migration_job.job_id,
            schema_mapping_id=sample_migration_job.schema_mapping_id,
        )

        migrator.pause_migration()
        assert migrator.is_paused() is True

        migrator.resume_migration()
        assert migrator.is_paused() is False

    @pytest.mark.asyncio
    async def test_apply_transformations(self, sample_migration_job, sample_schema_mapping):
        """Verifica aplicação de transformações de dados."""
        migrator = BatchMigrator(
            job_id=sample_migration_job.job_id,
            schema_mapping_id=sample_migration_job.schema_mapping_id,
        )

        source_data = [
            {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "name": "John Doe",
                "email": "john@example.com",
                "created_at": "2024-01-01 12:00:00",
            }
        ]

        transformed = await migrator._apply_transformations(
            source_data=source_data,
            table_mapping=sample_schema_mapping.tables[0],
        )

        assert len(transformed) == 1
        assert transformed[0]["id"] == "123e4567-e89b-12d3-a456-426614174000"
        assert transformed[0]["name"] == "John Doe"
        assert transformed[0]["email"] == "john@example.com"
        # created_at deve ter sido transformado
        assert "created_at" in transformed[0]

    @pytest.mark.asyncio
    async def test_apply_transformations_with_default_values(self, sample_migration_job):
        """Verifica aplicação de valores default."""
        migrator = BatchMigrator(
            job_id=sample_migration_job.job_id,
            schema_mapping_id=sample_migration_job.schema_mapping_id,
        )

        # Campo com default_value
        table_mapping = TableMapping(
            source_schema="public",
            source_table="users",
            target_table="users",
            fields=[
                FieldMapping(
                    source_field="id",
                    target_field="id",
                    data_type="uuid",
                    nullable=False,
                    is_primary_key=True,
                ),
                FieldMapping(
                    source_field="status",
                    target_field="status",
                    data_type="text",
                    nullable=True,
                    default_value="active",
                ),
            ],
        )

        source_data = [{"id": "id-1"}]  # status ausente

        transformed = await migrator._apply_transformations(
            source_data=source_data,
            table_mapping=table_mapping,
        )

        assert transformed[0]["status"] == "active"

    @pytest.mark.asyncio
    async def test_emit_progress_events(
        self,
        sample_migration_job,
        mock_kafka_producer,
    ):
        """Verifica emissão de eventos de progresso."""
        migrator = BatchMigrator(
            job_id=sample_migration_job.job_id,
            schema_mapping_id=sample_migration_job.schema_mapping_id,
        )

        progress = MigrationProgress(
            job_id=sample_migration_job.job_id,
            table="users",
            total_rows=10000,
            rows_migrated=5000,
        )
        progress.update_migrated(0)  # Recalcular percentage

        await migrator._emit_progress_event(
            kafka_producer=mock_kafka_producer,
            event_type="migration.batch_progress",
            progress=progress,
        )

        # Verificar chamada ao Kafka
        mock_kafka_producer.produce.assert_called_once()

        call_args = mock_kafka_producer.produce.call_args
        event_data = call_args.kwargs.get("value", {})

        assert event_data["job_id"] == sample_migration_job.job_id
        assert event_data["table"] == "users"
        assert event_data["rows_migrated"] == 5000

    @pytest.mark.asyncio
    async def test_run_batch_migration_error_handling(
        self,
        sample_migration_job,
        sample_schema_mapping,
        mock_legacy_client,
        mock_target_client,
        mock_kafka_producer,
    ):
        """Verifica tratamento de erros durante migração."""
        migrator = BatchMigrator(
            job_id=sample_migration_job.job_id,
            schema_mapping_id=sample_migration_job.schema_mapping_id,
            batch_size=100,
        )

        # Simular erro no fetch
        mock_legacy_client.fetch_batch.side_effect = Exception("Database error")

        with pytest.raises(BatchMigratorError, match="Erro durante migração"):
            await migrator.run_batch_migration(
                legacy_client=mock_legacy_client,
                target_client=mock_target_client,
                schema_mapping=sample_schema_mapping,
                kafka_producer=mock_kafka_producer,
            )

    @pytest.mark.asyncio
    async def test_run_batch_migration_kafka_error_is_tolerated(
        self,
        sample_migration_job,
        sample_schema_mapping,
        mock_legacy_client,
        mock_target_client,
        mock_kafka_producer,
    ):
        """Verifica que erro no Kafka não interrompe migração."""
        migrator = BatchMigrator(
            job_id=sample_migration_job.job_id,
            schema_mapping_id=sample_migration_job.schema_mapping_id,
            batch_size=100,
        )

        batch = [{"id": "id-1"}]
        mock_legacy_client.fetch_batch.side_effect = [batch, []]
        mock_kafka_producer.produce.side_effect = Exception("Kafka error")

        # Migração deve completar mesmo com erro no Kafka
        stats = await migrator.run_batch_migration(
            legacy_client=mock_legacy_client,
            target_client=mock_target_client,
            schema_mapping=sample_schema_mapping,
            kafka_producer=mock_kafka_producer,
        )

        assert stats["total_migrated"] == 1
        # Verificar que insert foi chamado
        mock_target_client.insert_batch.assert_called_once()
