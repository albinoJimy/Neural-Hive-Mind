"""Testes para migrations MongoDB."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.database.migrations.m001_optimization_recommendations import (
    upgrade,
    downgrade,
    validate,
    run_migration,
)


@pytest.mark.asyncio
class TestMigration001:
    """Testes para migration m001."""

    async def test_upgrade_creates_collection_and_indexes(self):
        """Testa que upgrade cria coleção e índices."""
        mock_client = AsyncMock()
        mock_db = MagicMock()

        # Mock list_collection_names para retornar vazio (coleção não existe)
        mock_db.list_collection_names = AsyncMock(return_value=[])
        mock_db.create_collection = AsyncMock()
        mock_db.optimization_recommendations = MagicMock()
        mock_db.optimization_recommendations.create_index = AsyncMock()

        mock_client.__getitem__ = lambda self, name: mock_db

        result = await upgrade(mock_client, "neural_hive")

        assert result["status"] == "success"
        assert result["collection"] == "optimization_recommendations"
        assert len(result["indexes_created"]) == 6
        mock_db.create_collection.assert_called_once_with("optimization_recommendations")

    async def test_upgrade_skips_if_collection_exists(self):
        """Testa que upgrade é skipado se coleção já existe."""
        mock_client = AsyncMock()
        mock_db = MagicMock()

        # Mock list_collection_names para retornar coleção existente
        mock_db.list_collection_names = AsyncMock(
            return_value=["optimization_recommendations", "other_collection"]
        )

        mock_client.__getitem__ = lambda self, name: mock_db

        result = await upgrade(mock_client, "neural_hive")

        assert result["status"] == "skipped"
        assert "already exists" in result["reason"]

    async def test_downgrade_drops_collection(self):
        """Testa que downgrade remove coleção."""
        mock_client = AsyncMock()
        mock_db = MagicMock()

        # Mock list_collection_names para retornar coleção existente
        mock_db.list_collection_names = AsyncMock(return_value=["optimization_recommendations"])
        mock_db.optimization_recommendations = MagicMock()
        mock_db.optimization_recommendations.drop = AsyncMock()

        mock_client.__getitem__ = lambda self, name: mock_db

        result = await downgrade(mock_client, "neural_hive")

        assert result["status"] == "success"
        assert result["collection"] == "optimization_recommendations"
        mock_db.optimization_recommendations.drop.assert_called_once()

    async def test_downgrade_skips_if_collection_not_exists(self):
        """Testa que downgrade é skipado se coleção não existe."""
        mock_client = AsyncMock()
        mock_db = MagicMock()

        # Mock list_collection_names para retornar vazio
        mock_db.list_collection_names = AsyncMock(return_value=[])

        mock_client.__getitem__ = lambda self, name: mock_db

        result = await downgrade(mock_client, "neural_hive")

        assert result["status"] == "skipped"
        assert "does not exist" in result["reason"]

    async def test_validate_returns_valid_when_migration_applied(self):
        """Testa validação quando migration foi aplicada."""
        mock_client = AsyncMock()
        mock_db = MagicMock()

        # Mock list_collection_names
        mock_db.list_collection_names = AsyncMock(return_value=["optimization_recommendations"])

        # Mock index_information para retornar índices esperados
        mock_db.optimization_recommendations = MagicMock()
        mock_db.optimization_recommendations.index_information = AsyncMock(
            return_value={
                "_id_": [("key", 1)],
                "idx_ticket_id": [("ticket_id", 1)],
                "idx_workflow_id_created_at": [("workflow_id", 1), ("created_at", -1)],
                "idx_status_created_at": [("status", 1), ("created_at", -1)],
                "idx_pending_auto_apply": [("recommendations.status", 1)],
                "idx_bottleneck_issues": [("performance_analysis.bottlenecks.issue", 1)],
                "idx_target_type_status": [("recommendations.target_type", 1)],
            }
        )

        mock_client.__getitem__ = lambda self, name: mock_db

        result = await validate(mock_client, "neural_hive")

        assert result["valid"] is True
        assert result["collection_exists"] is True
        assert len(result["missing_indexes"]) == 0

    async def test_validate_returns_invalid_when_collection_missing(self):
        """Testa validação quando coleção não existe."""
        mock_client = AsyncMock()
        mock_db = MagicMock()

        mock_db.list_collection_names = AsyncMock(return_value=[])
        mock_client.__getitem__ = lambda self, name: mock_db

        result = await validate(mock_client, "neural_hive")

        assert result["valid"] is False
        assert "does not exist" in result["reason"]

    async def test_validate_returns_missing_indexes(self):
        """Testa validação retorna índices faltando."""
        mock_client = AsyncMock()
        mock_db = MagicMock()

        mock_db.list_collection_names = AsyncMock(return_value=["optimization_recommendations"])

        # Retornar apenas alguns índices
        mock_db.optimization_recommendations = MagicMock()
        mock_db.optimization_recommendations.index_information = AsyncMock(
            return_value={
                "_id_": [("key", 1)],
                "idx_ticket_id": [("ticket_id", 1)],
            }
        )

        mock_client.__getitem__ = lambda self, name: mock_db

        result = await validate(mock_client, "neural_hive")

        assert result["valid"] is False
        assert len(result["missing_indexes"]) > 0

    async def test_run_migration_with_upgrade_action(self):
        """Testa run_migration com action=upgrade."""
        mock_client = AsyncMock()
        mock_db = MagicMock()

        mock_db.list_collection_names = AsyncMock(return_value=[])
        mock_db.create_collection = AsyncMock()
        mock_db.optimization_recommendations = MagicMock()
        mock_db.optimization_recommendations.create_index = AsyncMock()

        mock_client.__getitem__ = lambda self, name: mock_db

        result = await run_migration(mock_client, "neural_hive", "upgrade")

        assert result["status"] == "success"

    async def test_run_migration_with_downgrade_action(self):
        """Testa run_migration com action=downgrade."""
        mock_client = AsyncMock()
        mock_db = MagicMock()

        mock_db.list_collection_names = AsyncMock(return_value=["optimization_recommendations"])
        mock_db.optimization_recommendations = MagicMock()
        mock_db.optimization_recommendations.drop = AsyncMock()

        mock_client.__getitem__ = lambda self, name: mock_db

        result = await run_migration(mock_client, "neural_hive", "downgrade")

        assert result["status"] == "success"

    async def test_run_migration_with_validate_action(self):
        """Testa run_migration com action=validate."""
        mock_client = AsyncMock()
        mock_db = MagicMock()

        mock_db.list_collection_names = AsyncMock(return_value=["optimization_recommendations"])

        mock_db.optimization_recommendations = MagicMock()
        mock_db.optimization_recommendations.index_information = AsyncMock(
            return_value={
                "_id_": [("key", 1)],
                "idx_ticket_id": [("ticket_id", 1)],
            }
        )

        mock_client.__getitem__ = lambda self, name: mock_db

        result = await run_migration(mock_client, "neural_hive", "validate")

        assert result["collection_exists"] is True

    async def test_run_migration_with_unknown_action(self):
        """Testa run_migration com action desconhecido."""
        mock_client = AsyncMock()

        result = await run_migration(mock_client, "neural_hive", "unknown")

        assert result["status"] == "error"
        assert "Unknown action" in result["reason"]
