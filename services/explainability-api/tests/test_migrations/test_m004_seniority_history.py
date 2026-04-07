"""
Testes para Migration 004 - Seniority History.

Verifica que a migration cria corretamente a colecao e indices.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestM004SeniorityHistory:
    """Testes unitarios para migration m004_seniority_history."""

    @pytest.mark.asyncio
    async def test_m004_creates_collection(self):
        """Verifica que migration cria colecao seniority_history."""
        from src.database.migrations.m004_seniority_history import upgrade

        # Mock MongoDB client
        mongo_client = self._create_mock_mongo_client()

        # Run migration
        await upgrade(mongo_client, "neural_hive")

        # Verify create_collection was called
        db = mongo_client["neural_hive"]
        db.create_collection.assert_called_once_with("seniority_history")

    @pytest.mark.asyncio
    async def test_m004_creates_indexes(self):
        """Verifica indices criados."""
        from src.database.migrations.m004_seniority_history import upgrade

        # Mock MongoDB client
        mongo_client = self._create_mock_mongo_client()

        # Run migration
        await upgrade(mongo_client, "neural_hive")

        # Verify indexes were created
        db = mongo_client["neural_hive"]
        collection = db["seniority_history"]

        assert collection.create_index.call_count == 3

        # Verify index specifications
        calls = collection.create_index.call_args_list

        # First index: specialist_id + changed_at
        assert calls[0][0][0] == [("specialist_id", 1), ("changed_at", -1)]
        assert calls[0][1]["name"] == "specialist_id_1_changed_at_-1"

        # Second index: domain + changed_at
        assert calls[1][0][0] == [("domain", 1), ("changed_at", -1)]
        assert calls[1][1]["name"] == "domain_1_changed_at_-1"

        # Third index: changed_at
        assert calls[2][0][0] == [("changed_at", 1)]
        assert calls[2][1]["name"] == "changed_at_1"

    @pytest.mark.asyncio
    async def test_m004_downgrade_drops_collection(self):
        """Verifica que downgrade remove a colecao."""
        from src.database.migrations.m004_seniority_history import downgrade

        # Mock MongoDB client
        mongo_client = self._create_mock_mongo_client()

        # Run downgrade
        await downgrade(mongo_client, "neural_hive")

        # Verify drop_collection was called
        db = mongo_client["neural_hive"]
        db.drop_collection.assert_called_once_with("seniority_history")

    @pytest.mark.asyncio
    async def test_verify_schema(self):
        """Verifica verificação de schema."""
        from src.database.migrations.m004_seniority_history import verify_schema

        # Mock MongoDB client
        mongo_client = self._create_mock_mongo_client()

        # Run verification
        result = await verify_schema(mongo_client, "neural_hive")

        # Verify result structure
        assert "timestamp" in result
        assert "collection_exists" in result
        assert "indexes" in result

    def _create_mock_mongo_client(self):
        """Cria mock do MongoDB client para testes."""
        # Mock database
        db = MagicMock()

        # Mock collection
        collection = MagicMock()

        # Setup async mocks using AsyncMock
        db.create_collection = AsyncMock(return_value=None)
        db.drop_collection = AsyncMock(return_value=None)
        db.list_collection_names = AsyncMock(return_value=["seniority_history"])
        collection.create_index = AsyncMock(return_value="index_name")
        collection.list_indexes = AsyncMock(
            return_value=[
                {"name": "_id_"},
                {"name": "specialist_id_1_changed_at_-1"},
                {"name": "domain_1_changed_at_-1"},
                {"name": "changed_at_1"},
            ]
        )

        # Setup __getitem__ on db to return collection
        db.__getitem__.return_value = collection

        # Create client mock with db as __getitem__ return
        client = MagicMock()
        client.__getitem__.return_value = db

        return client
