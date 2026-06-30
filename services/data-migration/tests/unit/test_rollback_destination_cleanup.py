"""
Testes unitários para o fallback idempotente do /rollback (limpeza do destino).

Quando NÃO há snapshot disponível (instância de orchestrator recriada após o
/start, com _snapshot_id=None), o handler ``rollback_migration`` deixa de
devolver HTTP 400 e passa a truncar as tabelas-alvo no destino (modern),
desfazendo o efeito da migração de forma idempotente.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.api.routers.migrations import rollback_migration
from src.services.migration_orchestrator import MigrationOrchestratorError


@pytest.fixture
def mock_mongodb_client():
    """Mock do MongoDB client."""
    client = MagicMock()
    client.find_migration_job_by_id = AsyncMock()
    client.find_schema_mapping_by_id = AsyncMock()
    client.update_migration_job_status = AsyncMock()
    return client


@pytest.fixture
def mock_orchestrator_no_snapshot():
    """Orchestrator cujo rollback_migration levanta (sem snapshot)."""
    orchestrator = MagicMock()
    orchestrator.rollback_migration = AsyncMock(
        side_effect=MigrationOrchestratorError("Nenhum snapshot disponível para rollback")
    )
    return orchestrator


def _job_dict_with_metadata(job_id: str, modern_url: str = "postgresql://u:p@modern:5432/db"):
    """Job válido com modern_db_url em metadata."""
    return {
        "job_id": job_id,
        "schema_mapping_id": f"mapping-{job_id}",
        "status": "failed",
        "metadata": {
            "legacy_db_url": "postgresql://u:p@legacy:5432/db",
            "modern_db_url": modern_url,
        },
    }


def _schema_mapping_with_targets(n: int):
    """Schema mapping com n tabelas-alvo."""
    return {
        "_id": "mapping-x",
        "legacy_connection_id": "conn-1",
        "nhm_target": "feature-store",
        "tables": [
            {
                "source_schema": "public",
                "source_table": f"src_{i}",
                "target_table": f"tgt_{i}",
                "target_schema": "public",
                "fields": [],
            }
            for i in range(n)
        ],
    }


class TestRollbackDestinationCleanup:
    """Testes para o fallback de limpeza do destino no /rollback."""

    @pytest.mark.asyncio
    async def test_rollback_truncates_target_tables(
        self, mock_mongodb_client, mock_orchestrator_no_snapshot
    ):
        """Sem snapshot → trunca as 4 tabelas-alvo e devolve sucesso (HTTP 2xx)."""
        job_id = "job-rb-1"
        mock_mongodb_client.find_migration_job_by_id.return_value = _job_dict_with_metadata(job_id)
        mock_mongodb_client.find_schema_mapping_by_id.return_value = _schema_mapping_with_targets(4)

        mock_pg = MagicMock()
        mock_pg.connect = AsyncMock()
        mock_pg.disconnect = AsyncMock()
        mock_pg.truncate_table = AsyncMock()

        with patch(
            "src.api.routers.migrations.get_migration_orchestrator",
            return_value=mock_orchestrator_no_snapshot,
        ), patch(
            "src.api.routers.migrations.PostgreSQLClient",
            return_value=mock_pg,
        ):
            response = await rollback_migration(job_id, mock_mongodb_client)

        assert response.success is True
        assert response.action == "rollback"
        assert "4 tables truncated" in response.message

        # 4 tabelas-alvo truncadas
        assert mock_pg.truncate_table.await_count == 4
        truncated = {c.args[0] for c in mock_pg.truncate_table.call_args_list}
        assert truncated == {f"tgt_{i}" for i in range(4)}

        # Status atualizado para rolled_back
        mock_mongodb_client.update_migration_job_status.assert_awaited_once_with(
            job_id=job_id, status="rolled_back"
        )

        # Cliente desligado no finally
        mock_pg.disconnect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_rollback_without_modern_url_fails_honestly(
        self, mock_mongodb_client, mock_orchestrator_no_snapshot
    ):
        """Sem snapshot E sem modern_db_url → 400 honesto (não finge sucesso)."""
        job_id = "job-rb-2"
        job_dict = _job_dict_with_metadata(job_id)
        job_dict["metadata"].pop("modern_db_url")
        mock_mongodb_client.find_migration_job_by_id.return_value = job_dict

        mock_pg = MagicMock()
        mock_pg.connect = AsyncMock()
        mock_pg.disconnect = AsyncMock()
        mock_pg.truncate_table = AsyncMock()

        with patch(
            "src.api.routers.migrations.get_migration_orchestrator",
            return_value=mock_orchestrator_no_snapshot,
        ), patch(
            "src.api.routers.migrations.PostgreSQLClient",
            return_value=mock_pg,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await rollback_migration(job_id, mock_mongodb_client)

        assert exc_info.value.status_code == 400
        assert "modern_db_url" in str(exc_info.value.detail)

        # Não tocou no destino nem fingiu rollback
        mock_pg.truncate_table.assert_not_called()
        mock_mongodb_client.update_migration_job_status.assert_not_called()
