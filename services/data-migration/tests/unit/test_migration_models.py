"""
Testes unitários para modelos de migração.

Cobre MigrationJob, SchemaMapping e MigrationStatus.
"""

from datetime import datetime, timedelta, timezone

from src.models.migration import (
    FieldMapping,
    MigrationJob,
    MigrationStatus,
    SchemaMapping,
    TableMapping,
)


class TestMigrationStatus:
    """Testes para enum MigrationStatus."""

    def test_migration_status_values(self):
        """Verifica valores do enum MigrationStatus."""
        assert MigrationStatus.PENDING == "pending"
        assert MigrationStatus.ANALYZING == "analyzing"
        assert MigrationStatus.MAPPING == "mapping"
        assert MigrationStatus.BATCH_MIGRATING == "batch_migrating"
        assert MigrationStatus.CDC_RUNNING == "cdc_running"
        assert MigrationStatus.VALIDATING == "validating"
        assert MigrationStatus.COMPLETED == "completed"
        assert MigrationStatus.FAILED == "failed"
        assert MigrationStatus.ROLLED_BACK == "rolled_back"

    def test_migration_status_is_valid_transition(self):
        """Verifica transições válidas de status."""
        # Transições válidas (fluxo com aprovação humana)
        assert MigrationStatus.PENDING.is_valid_transition(MigrationStatus.ANALYZING)
        assert MigrationStatus.ANALYZING.is_valid_transition(MigrationStatus.MAPPING)
        assert MigrationStatus.MAPPING.is_valid_transition(MigrationStatus.MAPPING_APPROVED)
        assert MigrationStatus.MAPPING_APPROVED.is_valid_transition(
            MigrationStatus.SNAPSHOT_CREATED
        )
        assert MigrationStatus.SNAPSHOT_CREATED.is_valid_transition(MigrationStatus.BATCH_MIGRATING)
        assert MigrationStatus.BATCH_MIGRATING.is_valid_transition(MigrationStatus.CDC_RUNNING)
        assert MigrationStatus.CDC_RUNNING.is_valid_transition(MigrationStatus.VALIDATING)
        assert MigrationStatus.VALIDATING.is_valid_transition(MigrationStatus.COMPLETED)

        # Transição para FAILED sempre válida a partir de estados intermediários
        assert MigrationStatus.PENDING.is_valid_transition(MigrationStatus.FAILED)
        assert MigrationStatus.ANALYZING.is_valid_transition(MigrationStatus.FAILED)
        assert MigrationStatus.MAPPING.is_valid_transition(MigrationStatus.FAILED)
        assert MigrationStatus.BATCH_MIGRATING.is_valid_transition(MigrationStatus.FAILED)
        assert MigrationStatus.CDC_RUNNING.is_valid_transition(MigrationStatus.FAILED)
        assert MigrationStatus.VALIDATING.is_valid_transition(MigrationStatus.FAILED)

        # Transição para ROLLED_BACK
        assert MigrationStatus.COMPLETED.is_valid_transition(MigrationStatus.ROLLED_BACK)
        assert MigrationStatus.BATCH_MIGRATING.is_valid_transition(MigrationStatus.ROLLED_BACK)
        assert MigrationStatus.CDC_RUNNING.is_valid_transition(MigrationStatus.ROLLED_BACK)
        assert MigrationStatus.VALIDATING.is_valid_transition(MigrationStatus.ROLLED_BACK)

        # Transições inválidas
        assert not MigrationStatus.COMPLETED.is_valid_transition(MigrationStatus.PENDING)
        assert not MigrationStatus.FAILED.is_valid_transition(MigrationStatus.ANALYZING)
        assert not MigrationStatus.PENDING.is_valid_transition(MigrationStatus.COMPLETED)

        # MAPPING não pode ir direto para BATCH_MIGRATING (precisa de MAPPING_APPROVED)
        assert not MigrationStatus.MAPPING.is_valid_transition(MigrationStatus.BATCH_MIGRATING)


class TestFieldMapping:
    """Testes para modelo FieldMapping."""

    def test_field_mapping_creation(self):
        """Verifica criação de FieldMapping."""
        field = FieldMapping(
            source_field="user_id",
            target_field="id",
            data_type="INTEGER",
            nullable=False,
            is_primary_key=True,
        )

        assert field.source_field == "user_id"
        assert field.target_field == "id"
        assert field.data_type == "INTEGER"
        assert field.nullable is False
        assert field.is_primary_key is True
        assert field.transform is None
        assert field.default_value is None
        assert field.description is None

    def test_field_mapping_with_transform(self):
        """Verifica FieldMapping com transformação."""
        field = FieldMapping(
            source_field="created_at",
            target_field="created_at",
            data_type="TIMESTAMP",
            transform="CAST_TIMESTAMP_UTC",
            description="Converte timestamp para UTC",
        )

        assert field.transform == "CAST_TIMESTAMP_UTC"
        assert field.description == "Converte timestamp para UTC"

    def test_field_mapping_with_default(self):
        """Verifica FieldMapping com valor default."""
        field = FieldMapping(
            source_field="status",
            target_field="status",
            data_type="VARCHAR(50)",
            default_value="'active'",
            nullable=False,
        )

        assert field.default_value == "'active'"


class TestTableMapping:
    """Testes para modelo TableMapping."""

    def test_table_mapping_creation(self):
        """Verifica criação de TableMapping."""
        fields = [
            FieldMapping(
                source_field="id",
                target_field="id",
                data_type="UUID",
                is_primary_key=True,
                nullable=False,
            ),
            FieldMapping(
                source_field="name",
                target_field="full_name",
                data_type="VARCHAR(255)",
                nullable=False,
            ),
        ]

        table = TableMapping(
            source_schema="public",
            source_table="users",
            target_table="nhm_users",
            fields=fields,
        )

        assert table.source_schema == "public"
        assert table.source_table == "users"
        assert table.target_table == "nhm_users"
        assert len(table.fields) == 2
        assert table.source_filter is None
        assert table.target_pre_actions is None
        assert table.target_post_actions is None

    def test_table_mapping_with_filter(self):
        """Verifica TableMapping com filtro."""
        table = TableMapping(
            source_schema="public",
            source_table="orders",
            target_table="nhm_orders",
            fields=[],
            source_filter="deleted_at IS NULL",
        )

        assert table.source_filter == "deleted_at IS NULL"

    def test_table_mapping_with_actions(self):
        """Verifica TableMapping com ações pré/pós."""
        table = TableMapping(
            source_schema="public",
            source_table="products",
            target_table="nhm_products",
            fields=[],
            target_pre_actions=["DROP INDEX IF EXISTS idx_product_name"],
            target_post_actions=["CREATE INDEX idx_nhm_product_name ON nhm_products(name)"],
        )

        assert len(table.target_pre_actions) == 1
        assert len(table.target_post_actions) == 1
        assert "DROP INDEX" in table.target_pre_actions[0]
        assert "CREATE INDEX" in table.target_post_actions[0]


class TestSchemaMapping:
    """Testes para modelo SchemaMapping."""

    def test_schema_mapping_creation(self):
        """Verifica criação de SchemaMapping."""
        tables = [
            TableMapping(
                source_schema="public",
                source_table="users",
                target_table="nhm_users",
                fields=[],
            ),
            TableMapping(
                source_schema="public",
                source_table="orders",
                target_table="nhm_orders",
                fields=[],
            ),
        ]

        schema = SchemaMapping(
            legacy_connection_id="postgres-legacy-01",
            nhm_target="feature-store",
            tables=tables,
        )

        assert schema.legacy_connection_id == "postgres-legacy-01"
        assert schema.nhm_target == "feature-store"
        assert len(schema.tables) == 2
        assert schema.metadata == {}

    def test_schema_mapping_with_metadata(self):
        """Verifica SchemaMapping com metadata."""
        schema = SchemaMapping(
            legacy_connection_id="postgres-legacy-01",
            nhm_target="feature-store",
            tables=[],
            metadata={"estimated_rows": 1000000, "business_critical": True},
        )

        assert schema.metadata["estimated_rows"] == 1000000
        assert schema.metadata["business_critical"] is True

    def test_schema_mapping_model_dump(self):
        """Verifica serialização do SchemaMapping."""
        schema = SchemaMapping(
            legacy_connection_id="postgres-legacy-01",
            nhm_target="feature-store",
            tables=[],
            metadata={"version": 1},
        )

        data = schema.model_dump()

        assert data["legacy_connection_id"] == "postgres-legacy-01"
        assert data["nhm_target"] == "feature-store"
        assert data["metadata"]["version"] == 1


class TestMigrationJob:
    """Testes para modelo MigrationJob."""

    def test_migration_job_creation(self):
        """Verifica criação de MigrationJob."""
        job = MigrationJob(
            schema_mapping_id="schema-123",
            status=MigrationStatus.PENDING,
            batch_size=1000,
            max_parallel_migrations=5,
        )

        assert job.schema_mapping_id == "schema-123"
        assert job.status == MigrationStatus.PENDING
        assert job.batch_size == 1000
        assert job.max_parallel_migrations == 5
        assert job.progress_percentage == 0.0
        assert job.rows_migrated == 0
        assert job.rows_failed == 0
        assert job.error_message is None

    def test_migration_job_with_auto_fields(self):
        """Verifica campos auto-gerados de MigrationJob."""
        job = MigrationJob(
            schema_mapping_id="schema-123",
            status=MigrationStatus.PENDING,
        )

        assert job.job_id is not None
        assert isinstance(job.job_id, str)
        assert job.created_at is not None
        assert isinstance(job.created_at, datetime)
        assert job.updated_at is not None
        assert isinstance(job.updated_at, datetime)

    def test_migration_job_status_update(self):
        """Verifica atualização de status."""
        job = MigrationJob(
            schema_mapping_id="schema-123",
            status=MigrationStatus.PENDING,
        )

        # Atualizar status
        job.status = MigrationStatus.ANALYZING
        job.updated_at = datetime.now(timezone.utc)

        assert job.status == MigrationStatus.ANALYZING

    def test_migration_job_progress_update(self):
        """Verifica atualização de progresso."""
        job = MigrationJob(
            schema_mapping_id="schema-123",
            status=MigrationStatus.BATCH_MIGRATING,
        )

        # Atualizar progresso
        job.rows_migrated = 50000
        job.total_rows = 100000
        job.progress_percentage = 50.0
        job.updated_at = datetime.now(timezone.utc)

        assert job.rows_migrated == 50000
        assert job.total_rows == 100000
        assert job.progress_percentage == 50.0

    def test_migration_job_failure(self):
        """Verifica marcação de job como falhado."""
        job = MigrationJob(
            schema_mapping_id="schema-123",
            status=MigrationStatus.BATCH_MIGRATING,
        )

        job.status = MigrationStatus.FAILED
        job.error_message = "Connection timeout to legacy database"
        job.failed_at = datetime.now(timezone.utc)
        job.updated_at = datetime.now(timezone.utc)

        assert job.status == MigrationStatus.FAILED
        assert job.error_message == "Connection timeout to legacy database"
        assert job.failed_at is not None

    def test_migration_job_completion(self):
        """Verifica marcação de job como completo."""
        job = MigrationJob(
            schema_mapping_id="schema-123",
            status=MigrationStatus.VALIDATING,
            rows_migrated=100000,
            total_rows=100000,
        )

        job.status = MigrationStatus.COMPLETED
        job.progress_percentage = 100.0
        job.completed_at = datetime.now(timezone.utc)
        job.updated_at = datetime.now(timezone.utc)

        assert job.status == MigrationStatus.COMPLETED
        assert job.progress_percentage == 100.0
        assert job.completed_at is not None

    def test_migration_job_rollback(self):
        """Verifica marcação de job como rolled back."""
        job = MigrationJob(
            schema_mapping_id="schema-123",
            status=MigrationStatus.COMPLETED,
            completed_at=datetime.now(timezone.utc),
        )

        job.status = MigrationStatus.ROLLED_BACK
        job.rolled_back_at = datetime.now(timezone.utc)
        job.rollback_reason = "Data validation failed"
        job.updated_at = datetime.now(timezone.utc)

        assert job.status == MigrationStatus.ROLLED_BACK
        assert job.rolled_back_at is not None
        assert job.rollback_reason == "Data validation failed"

    def test_migration_job_calculate_eta(self):
        """Verifica cálculo de ETA."""
        job = MigrationJob(
            schema_mapping_id="schema-123",
            status=MigrationStatus.BATCH_MIGRATING,
            rows_migrated=5000,
            total_rows=10000,
            started_at=datetime.now(timezone.utc) - timedelta(minutes=10),
        )

        eta = job.calculate_eta()

        assert eta is not None
        assert eta > timedelta(0)  # Deve restar algum tempo

    def test_migration_job_calculate_eta_no_progress(self):
        """Verifica ETA quando não há progresso."""
        job = MigrationJob(
            schema_mapping_id="schema-123",
            status=MigrationStatus.PENDING,
            rows_migrated=0,
            total_rows=10000,
            started_at=None,
        )

        eta = job.calculate_eta()

        assert eta is None

    def test_migration_job_to_dict(self):
        """Verifica conversão para dicionário."""
        job = MigrationJob(
            schema_mapping_id="schema-123",
            status=MigrationStatus.PENDING,
            batch_size=1000,
        )

        data = job.model_dump()

        assert data["schema_mapping_id"] == "schema-123"
        assert data["status"] == "pending"
        assert data["batch_size"] == 1000
        assert "job_id" in data
        assert "created_at" in data

    def test_migration_job_from_dict(self):
        """Verifica criação a partir de dicionário."""
        data = {
            "schema_mapping_id": "schema-123",
            "status": "pending",
            "batch_size": 1000,
            "max_parallel_migrations": 5,
        }

        job = MigrationJob(**data)

        assert job.schema_mapping_id == "schema-123"
        assert job.status == MigrationStatus.PENDING
        assert job.batch_size == 1000
        assert job.max_parallel_migrations == 5
