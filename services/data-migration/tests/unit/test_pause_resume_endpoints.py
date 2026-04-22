"""Testes unitários para endpoints pause/resume de migrações."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.api.routers.migrations import pause_migration, resume_migration


@pytest.fixture
def mock_mongodb_client():
    """Mock do MongoDB client."""
    client = MagicMock()
    client.find_migration_job_by_id = AsyncMock()
    client.update_migration_job_status = AsyncMock()
    return client


@pytest.fixture
def mock_orchestrator():
    """Mock do MigrationOrchestrator."""
    orchestrator = MagicMock()
    orchestrator.pause_migration = AsyncMock(return_value=True)
    orchestrator.resume_migration = AsyncMock(return_value=True)
    return orchestrator


class TestPauseMigrationEndpoint:
    """Testes para endpoint POST /migrations/{id}/pause."""

    @pytest.mark.asyncio
    async def test_pause_migration_success(self, mock_mongodb_client, mock_orchestrator):
        """Testa pausar migração com sucesso."""
        job_id = "test-job-1"
        mock_mongodb_client.find_migration_job_by_id.return_value = {
            "job_id": job_id,
            "schema_mapping_id": "schema-1",
            "status": "batch_migrating",
        }

        with patch(
            "src.api.routers.migrations.get_migration_orchestrator",
            return_value=mock_orchestrator,
        ):
            response = await pause_migration(job_id, mock_mongodb_client)

        assert response.success is True
        assert response.action == "pause"
        assert "paused" in response.message.lower()

    @pytest.mark.asyncio
    async def test_pause_migration_not_found(self, mock_mongodb_client):
        """Testa erro quando job não existe."""
        job_id = "nonexistent-job"
        mock_mongodb_client.find_migration_job_by_id.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await pause_migration(job_id, mock_mongodb_client)

        assert exc_info.value.status_code == 404
        assert "not found" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_pause_migration_invalid_status(self, mock_mongodb_client, mock_orchestrator):
        """Testa erro quando status não permite pausa."""
        job_id = "test-job-1"
        mock_mongodb_client.find_migration_job_by_id.return_value = {
            "job_id": job_id,
            "schema_mapping_id": "schema-1",
            "status": "completed",  # Status que não pode ser pausado
        }

        with pytest.raises(HTTPException) as exc_info:
            await pause_migration(job_id, mock_mongodb_client)

        assert exc_info.value.status_code == 400
        assert "cannot pause" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_pause_migration_valid_statuses(self, mock_mongodb_client, mock_orchestrator):
        """Testa que todos os status válidos podem ser pausados."""
        valid_statuses = ["batch_migrating", "cdc_running", "validating"]

        for status in valid_statuses:
            job_id = f"test-job-{status}"
            mock_mongodb_client.find_migration_job_by_id.return_value = {
                "job_id": job_id,
                "schema_mapping_id": "schema-1",
                "status": status,
            }

            with patch(
                "src.api.routers.migrations.get_migration_orchestrator",
                return_value=mock_orchestrator,
            ):
                response = await pause_migration(job_id, mock_mongodb_client)

            assert response.success is True


class TestResumeMigrationEndpoint:
    """Testes para endpoint POST /migrations/{id}/resume."""

    @pytest.mark.asyncio
    async def test_resume_migration_success(self, mock_mongodb_client, mock_orchestrator):
        """Testa retomar migração com sucesso."""
        job_id = "test-job-1"
        mock_mongodb_client.find_migration_job_by_id.return_value = {
            "job_id": job_id,
            "schema_mapping_id": "schema-1",
            "status": "batch_migrating",
        }

        with patch(
            "src.api.routers.migrations.get_migration_orchestrator",
            return_value=mock_orchestrator,
        ):
            response = await resume_migration(job_id, mock_mongodb_client)

        assert response.success is True
        assert response.action == "resume"
        assert "resumed" in response.message.lower() or "retomada" in response.message.lower()

    @pytest.mark.asyncio
    async def test_resume_migration_not_found(self, mock_mongodb_client):
        """Testa erro quando job não existe."""
        job_id = "nonexistent-job"
        mock_mongodb_client.find_migration_job_by_id.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await resume_migration(job_id, mock_mongodb_client)

        assert exc_info.value.status_code == 404
        assert "not found" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_resume_migration_not_paused(self, mock_mongodb_client, mock_orchestrator):
        """Testa erro quando tentar retomar migração não pausada."""
        job_id = "test-job-1"
        mock_mongodb_client.find_migration_job_by_id.return_value = {
            "job_id": job_id,
            "schema_mapping_id": "schema-1",
            "status": "batch_migrating",
        }

        # Simular erro "não está pausado"
        from src.services.migration_orchestrator import PhaseTransitionError

        mock_orchestrator.resume_migration.side_effect = PhaseTransitionError(
            "Migração não está pausada"
        )

        with patch(
            "src.api.routers.migrations.get_migration_orchestrator",
            return_value=mock_orchestrator,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await resume_migration(job_id, mock_mongodb_client)

        assert exc_info.value.status_code == 400
