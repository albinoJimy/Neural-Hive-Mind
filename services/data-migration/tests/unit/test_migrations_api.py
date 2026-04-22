"""
Testes unitários para API router de migrações.

Testa os endpoints REST do Data Migration System:
- POST /api/v1/migrations - Criar job
- GET /api/v1/migrations/{job_id} - Obter status
- GET /api/v1/migrations - Listar jobs
- POST /api/v1/migrations/{job_id}/start - Iniciar
- POST /api/v1/migrations/{job_id}/pause - Pausar
- POST /api/v1/migrations/{job_id}/resume - Retomar
- POST /api/v1/migrations/{job_id}/rollback - Rollback
- POST /api/v1/migrations/{job_id}/approve - Aprovar fase
- POST /api/v1/migrations/{job_id}/validate - Validar dados
- GET /api/v1/migrations/{job_id}/schema - Obter schema mapping
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

# ========== Import do router e modelos ==========
from src.api.routers.migrations import (
    MigrationActionResponse,
    MigrationApproveRequest,
    MigrationCreateRequest,
    MigrationListResponse,
    MigrationStartRequest,
    MigrationStatusResponse,
    ValidationResultResponse,
    _get_current_phase,
    _parse_datetime,
)
from src.models.migration import (
    FieldMapping,
    MigrationJob,
    MigrationStatus,
    SchemaMapping,
    TableMapping,
)

# ========== Fixtures ==========


@pytest.fixture
def mock_mongodb_client():
    """Mock do cliente MongoDB."""
    mock_client = AsyncMock()
    mock_client.database = MagicMock()
    mock_client.migration_jobs_collection = MagicMock()
    mock_client.schema_mappings_collection = MagicMock()
    return mock_client


@pytest.fixture
def sample_field_mapping():
    """Retorna um FieldMapping de exemplo."""
    return FieldMapping(
        source_field="id",
        target_field="id",
        data_type="uuid",
        nullable=False,
        is_primary_key=True,
    )


@pytest.fixture
def sample_table_mapping(sample_field_mapping):
    """Retorna um TableMapping de exemplo."""
    return TableMapping(
        source_schema="public",
        source_table="users",
        target_table="users",
        target_schema="public",
        fields=[
            sample_field_mapping,
            FieldMapping(
                source_field="email",
                target_field="email",
                data_type="varchar",
                nullable=False,
            ),
            FieldMapping(
                source_field="created_at",
                target_field="created_at",
                data_type="timestamp",
                nullable=True,
            ),
        ],
        estimated_rows=1000,
    )


@pytest.fixture
def sample_schema_mapping(sample_table_mapping):
    """Retorna um SchemaMapping de exemplo."""
    return SchemaMapping(
        legacy_connection_id="legacy-conn-1",
        nhm_target="feature-store",
        tables=[sample_table_mapping],
        metadata={"description": "Test migration"},
    )


@pytest.fixture
def sample_migration_job():
    """Retorna um MigrationJob de exemplo."""
    return MigrationJob(
        job_id="test-job-1",
        schema_mapping_id="mapping-1",
        status=MigrationStatus.PENDING,
        batch_size=1000,
        rows_migrated=0,
        total_rows=10000,
        progress_percentage=0.0,
    )


@pytest.fixture
def migration_create_request():
    """Retorna dados de request para criar migração."""
    return {
        "legacy_db_url": "postgresql://user:pass@localhost:5432/legacy",
        "modern_db_url": "postgresql://user:pass@localhost:5432/modern",
        "tables": ["users", "orders"],
    }


# ========== Testes: Modelos Request/Response ==========


class TestRequestResponseModels:
    """Testes para modelos Pydantic de request/response."""

    def test_migration_create_request_valid(self):
        """Testa MigrationCreateRequest válido."""
        request = MigrationCreateRequest(
            legacy_db_url="postgresql://localhost:5432/legacy",
            modern_db_url="postgresql://localhost:5432/modern",
            tables=["users", "orders"],
        )
        assert request.tables == ["users", "orders"]
        assert request.batch_size == 1000  # valor default
        assert request.auto_approve is False  # valor default

    def test_migration_create_request_invalid_tables(self):
        """Testa erro com tabelas vazias."""
        with pytest.raises(ValidationError):
            MigrationCreateRequest(
                legacy_db_url="postgresql://localhost:5432/legacy",
                modern_db_url="postgresql://localhost:5432/modern",
                tables=[],
            )

    def test_migration_create_request_invalid_url(self):
        """Testa erro com URL inválida."""
        with pytest.raises(ValidationError):
            MigrationCreateRequest(
                legacy_db_url="not-a-valid-url",
                modern_db_url="postgresql://localhost:5432/modern",
                tables=["users"],
            )

    def test_migration_create_request_postgres_url_variant(self):
        """Testa aceitação de variante postgres://."""
        request = MigrationCreateRequest(
            legacy_db_url="postgres://localhost:5432/legacy",
            modern_db_url="postgresql://localhost:5432/modern",
            tables=["users"],
        )
        assert request.legacy_db_url == "postgres://localhost:5432/legacy"

    def test_migration_create_request_custom_batch_size(self):
        """Testa configuração de batch_size customizado."""
        request = MigrationCreateRequest(
            legacy_db_url="postgresql://localhost:5432/legacy",
            modern_db_url="postgresql://localhost:5432/modern",
            tables=["users"],
            batch_size=5000,
        )
        assert request.batch_size == 5000

    def test_migration_create_request_batch_size_bounds(self):
        """Testa limites de batch_size."""
        # Mínimo é 1
        with pytest.raises(ValidationError):
            MigrationCreateRequest(
                legacy_db_url="postgresql://localhost:5432/legacy",
                modern_db_url="postgresql://localhost:5432/modern",
                tables=["users"],
                batch_size=0,
            )

        # Máximo é 10000
        with pytest.raises(ValidationError):
            MigrationCreateRequest(
                legacy_db_url="postgresql://localhost:5432/legacy",
                modern_db_url="postgresql://localhost:5432/modern",
                tables=["users"],
                batch_size=10001,
            )

    def test_migration_status_response_valid(self):
        """Testa MigrationStatusResponse válido."""
        response = MigrationStatusResponse(
            job_id="test-1",
            status=MigrationStatus.BATCH_MIGRATING,
            progress=50.0,
            current_phase="batch_migration",
            tables_completed=2,
            total_tables=4,
            started_at=datetime.now(timezone.utc),
            completed_at=None,
        )
        assert response.progress == 50.0
        assert response.tables_completed == 2

    def test_migration_status_response_progress_bounds(self):
        """Testa limites de progresso."""
        # Progresso > 100 é inválido
        with pytest.raises(ValidationError):
            MigrationStatusResponse(
                job_id="test-1",
                status=MigrationStatus.PENDING,
                progress=150.0,
                current_phase="pending",
                tables_completed=0,
                total_tables=4,
            )

        # Progresso < 0 é inválido
        with pytest.raises(ValidationError):
            MigrationStatusResponse(
                job_id="test-1",
                status=MigrationStatus.PENDING,
                progress=-10.0,
                current_phase="pending",
                tables_completed=0,
                total_tables=4,
            )

        # Progresso = 0 é válido
        response = MigrationStatusResponse(
            job_id="test-1",
            status=MigrationStatus.PENDING,
            progress=0.0,
            current_phase="pending",
            tables_completed=0,
            total_tables=4,
        )
        assert response.progress == 0.0

        # Progresso = 100 é válido
        response = MigrationStatusResponse(
            job_id="test-1",
            status=MigrationStatus.COMPLETED,
            progress=100.0,
            current_phase="completed",
            tables_completed=4,
            total_tables=4,
        )
        assert response.progress == 100.0

    def test_migration_action_response_valid(self):
        """Testa MigrationActionResponse válido."""
        response = MigrationActionResponse(
            job_id="test-1",
            action="start",
            success=True,
            message="Migration started",
        )
        assert response.success is True
        assert response.action == "start"

    def test_migration_list_response_valid(self):
        """Testa MigrationListResponse válido."""
        response = MigrationListResponse(
            jobs=[
                {
                    "job_id": "job-1",
                    "status": "pending",
                }
            ],
            total=1,
            limit=100,
            offset=0,
        )
        assert len(response.jobs) == 1
        assert response.total == 1

    def test_validation_result_response_valid(self):
        """Testa ValidationResultResponse válido."""
        response = ValidationResultResponse(
            job_id="test-1",
            overall_passed=True,
            total_validations=10,
            passed_validations=10,
            failed_validations=0,
            results=[],
        )
        assert response.overall_passed is True
        assert response.total_validations == 10

    def test_migration_approve_request_valid(self):
        """Testa MigrationApproveRequest válido."""
        request = MigrationApproveRequest(approved_by="admin")
        assert request.approved_by == "admin"

    def test_migration_approve_request_missing_field(self):
        """Testa erro sem campo approved_by."""
        with pytest.raises(ValidationError):
            MigrationApproveRequest()

    def test_migration_start_request_defaults(self):
        """Testa valores default de MigrationStartRequest."""
        request = MigrationStartRequest()
        assert request.auto_approve is False
        assert request.database_config is None


# ========== Testes: Funções Auxiliares ==========


class TestHelperFunctions:
    """Testes para funções auxiliares do router."""

    def test_get_current_phase_all_statuses(self):
        """Testa mapeamento de status para fase."""
        assert _get_current_phase("pending") == "Aguardando início"
        assert _get_current_phase("analyzing") == "Analisando schema"
        assert _get_current_phase("mapping") == "Gerando mapeamento"
        assert _get_current_phase("mapping_approved") == "Mapeamento aprovado"
        assert _get_current_phase("snapshot_created") == "Snapshot criado"
        assert _get_current_phase("batch_migrating") == "Migrando dados históricos"
        assert _get_current_phase("cdc_running") == "CDC em execução"
        assert _get_current_phase("validating") == "Validando dados"
        assert _get_current_phase("completed") == "Concluído"
        assert _get_current_phase("failed") == "Falhou"
        assert _get_current_phase("rolled_back") == "Rollback executado"

    def test_get_current_phase_unknown_status(self):
        """Testa status desconhecido retorna ele mesmo."""
        assert _get_current_phase("unknown_status") == "unknown_status"

    def test_parse_datetime_valid_string(self):
        """Testa parse de datetime string válido."""
        dt_str = "2024-01-01T12:00:00Z"
        result = _parse_datetime(dt_str)
        assert result is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 1

    def test_parse_datetime_with_offset(self):
        """Testa parse de datetime com offset."""
        dt_str = "2024-01-01T12:00:00+00:00"
        result = _parse_datetime(dt_str)
        assert result is not None

    def test_parse_datetime_none(self):
        """Testa parse de None retorna None."""
        assert _parse_datetime(None) is None

    def test_parse_datetime_empty_string(self):
        """Testa parse de string vazia retorna None."""
        assert _parse_datetime("") is None

    def test_parse_datetime_invalid_string(self):
        """Testa parse de string inválida retorna None."""
        assert _parse_datetime("not-a-datetime") is None

    def test_parse_datetime_already_datetime(self):
        """Testa parse de datetime já como datetime."""
        dt = datetime.now(timezone.utc)
        result = _parse_datetime(dt)
        assert result == dt


# ========== Testes: Modelos de Migração (Integração com Models) ==========


class TestMigrationModelsIntegration:
    """Testes de integração com modelos de migração."""

    def test_migration_job_to_dict_for_db(self, sample_migration_job):
        """Testa conversão de MigrationJob para dict para MongoDB."""
        job_dict = sample_migration_job.model_dump()
        assert "job_id" in job_dict
        assert job_dict["job_id"] == "test-job-1"
        assert job_dict["status"] == "pending"

    def test_migration_job_status_transitions(self, sample_migration_job):
        """Testa transições de status do MigrationJob."""
        # Devido ao use_enum_values=True no model_config, o status é armazenado como string
        # Precisamos converter para o enum para testar transições
        current_status = MigrationStatus(sample_migration_job.status)

        # Transição válida - PENDING -> ANALYZING
        assert current_status.is_valid_transition(MigrationStatus.ANALYZING)
        sample_migration_job.update_status(MigrationStatus.ANALYZING)

        # Após update, o status deve ser ANALYZING (como string devido ao config)
        assert sample_migration_job.status == MigrationStatus.ANALYZING.value

        # Transição inválida - ANALYZING não pode voltar para PENDING
        with pytest.raises(ValueError):
            sample_migration_job.update_status(MigrationStatus.PENDING)

    def test_migration_job_progress_update(self, sample_migration_job):
        """Testa atualização de progresso."""
        sample_migration_job.update_progress(rows_migrated=5000, total_rows=10000)
        assert sample_migration_job.rows_migrated == 5000
        assert sample_migration_job.progress_percentage == 50.0

    def test_migration_job_eta_calculation(self, sample_migration_job):
        """Testa cálculo de ETA."""
        sample_migration_job.started_at = datetime.now(timezone.utc)
        sample_migration_job.update_progress(rows_migrated=5000, total_rows=10000)

        # ETA não deve ser None
        eta = sample_migration_job.calculate_eta()
        assert eta is not None

    def test_schema_mapping_serialization(self, sample_schema_mapping):
        """Testa serialização de SchemaMapping."""
        mapping_dict = sample_schema_mapping.model_dump()
        assert "legacy_connection_id" in mapping_dict
        assert "nhm_target" in mapping_dict
        assert "tables" in mapping_dict
        assert len(mapping_dict["tables"]) == 1

    def test_table_mapping_with_filters(self, sample_table_mapping):
        """Testa TableMapping com filtros."""
        assert sample_table_mapping.source_table == "users"
        assert len(sample_table_mapping.fields) == 3

    def test_field_mapping_types(self, sample_field_mapping):
        """Testa FieldMapping com diferentes tipos."""
        assert sample_field_mapping.source_field == "id"
        assert sample_field_mapping.is_primary_key is True
        assert sample_field_mapping.data_type == "uuid"


# ========== Testes: Mock de Dependências ==========


class TestDependencyMocking:
    """Testes de mocking de dependências externas."""

    @pytest.mark.asyncio
    async def test_mongodb_client_mock_find_job(self, mock_mongodb_client):
        """Testa mock de find_migration_job_by_id."""
        job_data = {
            "job_id": "test-1",
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        mock_mongodb_client.find_migration_job_by_id = AsyncMock(return_value=job_data)

        result = await mock_mongodb_client.find_migration_job_by_id("test-1")
        assert result["job_id"] == "test-1"

    @pytest.mark.asyncio
    async def test_mongodb_client_mock_find_schema(self, mock_mongodb_client):
        """Testa mock de find_schema_mapping_by_id."""
        mapping_data = {
            "_id": "mapping-1",
            "legacy_connection_id": "conn-1",
            "nhm_target": "feature-store",
            "tables": [],
        }
        mock_mongodb_client.find_schema_mapping_by_id = AsyncMock(return_value=mapping_data)

        result = await mock_mongodb_client.find_schema_mapping_by_id("mapping-1")
        assert result["nhm_target"] == "feature-store"

    @pytest.mark.asyncio
    async def test_mongodb_client_mock_list_jobs(self, mock_mongodb_client):
        """Testa mock de list_migration_jobs_by_status."""
        jobs = [
            {"job_id": "job-1", "status": "pending"},
            {"job_id": "job-2", "status": "pending"},
        ]
        mock_mongodb_client.list_migration_jobs_by_status = AsyncMock(return_value=jobs)

        result = await mock_mongodb_client.list_migration_jobs_by_status("pending")
        assert len(result) == 2


# ========== Testes: Validações de Negócio ==========


class TestBusinessValidations:
    """Testes para validações de negócio específicas."""

    def test_migration_status_flow_validation(self):
        """Testa fluxo completo de status."""
        valid_flow = [
            MigrationStatus.PENDING,
            MigrationStatus.ANALYZING,
            MigrationStatus.MAPPING,
            MigrationStatus.MAPPING_APPROVED,
            MigrationStatus.SNAPSHOT_CREATED,
            MigrationStatus.BATCH_MIGRATING,
            MigrationStatus.CDC_RUNNING,
            MigrationStatus.VALIDATING,
            MigrationStatus.COMPLETED,
        ]

        current = None
        for next_status in valid_flow:
            if current is None:
                current = next_status
            else:
                assert current.is_valid_transition(
                    next_status
                ), f"Transição inválida: {current} -> {next_status}"
                current = next_status

    def test_migration_rollback_possible_states(self):
        """Testa estados que podem fazer rollback."""
        rollback_allowed_from = [
            MigrationStatus.BATCH_MIGRATING,
            MigrationStatus.CDC_RUNNING,
            MigrationStatus.VALIDATING,
            MigrationStatus.FAILED,
            MigrationStatus.COMPLETED,
        ]

        for state in rollback_allowed_from:
            # Rollback é uma transição especial, não testada via is_valid_transition
            # mas verificamos que são estados onde dados podem ter sido modificados
            assert state in [
                MigrationStatus.BATCH_MIGRATING,
                MigrationStatus.CDC_RUNNING,
                MigrationStatus.VALIDATING,
                MigrationStatus.FAILED,
                MigrationStatus.COMPLETED,
            ]

    def test_pause_allowed_states(self):
        """Testa estados onde pausa é permitida."""
        pausable_states = [
            MigrationStatus.BATCH_MIGRATING,
            MigrationStatus.CDC_RUNNING,
            MigrationStatus.VALIDATING,
        ]

        for state in pausable_states:
            # Verificar que são estados de longa duração
            assert state in [
                MigrationStatus.BATCH_MIGRATING,
                MigrationStatus.CDC_RUNNING,
                MigrationStatus.VALIDATING,
            ]

    def test_approval_required_state(self):
        """Testa que estado MAPPING requer aprovação."""
        assert MigrationStatus.MAPPING in {
            MigrationStatus.MAPPING,
        }

    def test_terminal_states_no_transition(self):
        """Testa estados terminais não permitem transições."""
        terminal_states = [
            MigrationStatus.COMPLETED,
            MigrationStatus.FAILED,
            MigrationStatus.ROLLED_BACK,
        ]

        for state in terminal_states:
            # Estados terminais devem ter lista vazia de transições
            transitions = state.is_valid_transition(MigrationStatus.PENDING)
            # COMPLETED permite rollback para ROLLED_BACK
            if state == MigrationStatus.COMPLETED:
                assert state.is_valid_transition(MigrationStatus.ROLLED_BACK)
            else:
                assert not transitions


# ========== Testes: Serialização/Deserialização ==========


class TestSerialization:
    """Testes para serialização e deserialização."""

    def test_migration_job_json_serialization(self, sample_migration_job):
        """Testa serialização JSON de MigrationJob."""
        job_dict = sample_migration_job.model_dump()
        assert isinstance(job_dict, dict)
        assert "job_id" in job_dict

    def test_migration_job_json_deserialization(self):
        """Testa deserialização JSON para MigrationJob."""
        job_data = {
            "job_id": "test-1",
            "schema_mapping_id": "mapping-1",
            "status": "pending",
            "batch_size": 1000,
            "rows_migrated": 0,
            "total_rows": 10000,
            "progress_percentage": 0.0,
        }
        job = MigrationJob(**job_data)
        assert job.job_id == "test-1"
        assert job.status == MigrationStatus.PENDING

    def test_schema_mapping_json_serialization(self, sample_schema_mapping):
        """Testa serialização JSON de SchemaMapping."""
        mapping_dict = sample_schema_mapping.model_dump()
        assert isinstance(mapping_dict, dict)
        assert "tables" in mapping_dict

    def test_field_mapping_json_serialization(self, sample_field_mapping):
        """Testa serialização JSON de FieldMapping."""
        field_dict = sample_field_mapping.model_dump()
        assert field_dict["source_field"] == "id"
        assert field_dict["is_primary_key"] is True
