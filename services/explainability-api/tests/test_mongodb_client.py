"""
Testes unitários para MongoDBClient do Explainability API.

EPIC-204-01: Modelo ML para SHAP
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest
from src.database.mongodb_client import MongoDBClient


@pytest.fixture()
def mock_motor_client():
    """Mock para AsyncIOMotorClient."""
    with patch("src.database.mongodb_client.AsyncIOMotorClient") as mock:
        yield mock


@pytest.fixture()
def mongo_client():
    """Fixture para MongoDBClient."""
    client = MongoDBClient(
        uri="mongodb://localhost:27017", database="test_db", consensus_collection="test_decisions"
    )
    return client


@pytest.mark.asyncio()
class TestMongoDBClient:
    """Testes para MongoDBClient."""

    async def test_init(self, mongo_client):
        """Testa inicialização."""
        assert mongo_client.uri == "mongodb://localhost:27017"
        assert mongo_client.database_name == "test_db"
        assert mongo_client.consensus_collection_name == "test_decisions"
        assert mongo_client.client is None

    async def test_connect(self, mongo_client, mock_motor_client):
        """Testa conexão ao MongoDB."""
        mock_instance = AsyncMock()
        mock_motor_client.return_value = mock_instance

        # Mock ping command
        mock_instance.admin.command = AsyncMock(return_value={"ok": 1})

        await mongo_client.connect()

        assert mongo_client.client is not None
        mock_motor_client.assert_called_once()
        mock_instance.admin.command.assert_called_once_with("ping")

    async def test_get_recent_decisions(self, mongo_client):
        """Testa coleta de decisões recentes."""
        # Dados mock
        mock_decisions = [
            {
                "decision_id": "decision_1",
                "final_decision": "approve",
                "aggregated_confidence": 0.8,
                "aggregated_risk": 0.2,
                "created_at": datetime.now(UTC),
            },
            {
                "decision_id": "decision_2",
                "final_decision": "reject",
                "aggregated_confidence": 0.3,
                "aggregated_risk": 0.7,
                "created_at": datetime.now(UTC),
            },
        ]

        # Criar mock cursor que retorna lista async
        mock_cursor = AsyncMock()
        mock_cursor.sort = Mock(return_value=mock_cursor)
        mock_cursor.skip = Mock(return_value=mock_cursor)
        mock_cursor.limit = Mock(return_value=mock_cursor)

        # Criar classe para o cursor que suporta async iteration
        class MockCursor:
            def __init__(self, decisions):
                self.decisions = decisions

            def sort(self, *args, **kwargs):
                return self

            def skip(self, *args, **kwargs):
                return self

            def limit(self, *args, **kwargs):
                return self

            def __aiter__(self):
                return self

            async def __anext__(self):
                if not self.decisions:
                    raise StopAsyncIteration
                return self.decisions.pop(0)

        mock_cursor_instance = MockCursor(mock_decisions[:])

        # Mock database
        mongo_client.consensus_collection = AsyncMock()
        mongo_client.consensus_collection.find = Mock(return_value=mock_cursor_instance)

        decisions = await mongo_client.get_recent_decisions(limit=100)

        assert len(decisions) == 2
        assert decisions[0]["decision_id"] == "decision_1"
        assert "_id" not in decisions[0]

    async def test_get_recent_decisions_empty(self, mongo_client):
        """Testa coleta quando não há decisões."""

        # Criar classe para o cursor vazio
        class EmptyCursor:
            def sort(self, *args, **kwargs):
                return self

            def skip(self, *args, **kwargs):
                return self

            def limit(self, *args, **kwargs):
                return self

            def __aiter__(self):
                return self

            async def __anext__(self):
                raise StopAsyncIteration

        mock_cursor_instance = EmptyCursor()

        mongo_client.consensus_collection = AsyncMock()
        mongo_client.consensus_collection.find = Mock(return_value=mock_cursor_instance)

        decisions = await mongo_client.get_recent_decisions()

        assert len(decisions) == 0

    async def test_get_decision_by_id(self, mongo_client):
        """Testa busca de decisão por ID."""
        mock_doc = {"_id": "object_id", "decision_id": "decision_1", "final_decision": "approve"}

        mongo_client.consensus_collection = AsyncMock()
        mongo_client.consensus_collection.find_one = AsyncMock(return_value=mock_doc)

        decision = await mongo_client.get_decision_by_id("decision_1")

        assert decision is not None
        assert decision["decision_id"] == "decision_1"
        assert "_id" not in decision

    async def test_get_decision_by_id_not_found(self, mongo_client):
        """Testa busca de decisão inexistente."""
        mongo_client.consensus_collection = AsyncMock()
        mongo_client.consensus_collection.find_one = AsyncMock(return_value=None)

        decision = await mongo_client.get_decision_by_id("nonexistent")

        assert decision is None

    async def test_count_decisions(self, mongo_client):
        """Testa contagem de decisões."""
        mongo_client.consensus_collection = AsyncMock()
        mongo_client.consensus_collection.count_documents = AsyncMock(return_value=42)

        count = await mongo_client.count_decisions()

        assert count == 42

    async def test_get_decision_stats(self, mongo_client):
        """Testa obtenção de estatísticas."""
        # Mock aggregate pipeline result
        mock_result = [
            {
                "decision_counts": [
                    {"_id": "approve", "count": 30},
                    {"_id": "reject", "count": 12},
                ],
                "consensus_method_counts": [
                    {"_id": "bayesian", "count": 25},
                    {"_id": "voting", "count": 17},
                ],
                "date_range": [{"oldest": datetime(2026, 1, 1), "newest": datetime(2026, 3, 31)}],
                "confidence_ranges": [{"avg_confidence": 0.65, "avg_risk": 0.35}],
            }
        ]

        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=mock_result)

        mongo_client.consensus_collection = AsyncMock()
        mongo_client.consensus_collection.aggregate = Mock(return_value=mock_cursor)
        mongo_client.consensus_collection.count_documents = AsyncMock(return_value=42)

        stats = await mongo_client.get_decision_stats()

        assert stats["total_decisions"] == 42
        assert stats["decision_distribution"]["approve"] == 30
        assert stats["decision_distribution"]["reject"] == 12
        assert stats["consensus_method_distribution"]["bayesian"] == 25
        assert stats["date_range"]["oldest"] == "2026-01-01T00:00:00"
        assert stats["averages"]["confidence"] == 0.65

    async def test_get_decision_stats_empty(self, mongo_client):
        """Testa estatísticas quando não há decisões."""
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=[])

        mongo_client.consensus_collection = AsyncMock()
        mongo_client.consensus_collection.aggregate = Mock(return_value=mock_cursor)
        mongo_client.consensus_collection.count_documents = AsyncMock(return_value=0)

        stats = await mongo_client.get_decision_stats()

        assert stats["total_decisions"] == 0
        assert stats["decision_distribution"] == {}

    async def test_close(self, mongo_client):
        """Testa fechamento de conexão."""
        mock_client = AsyncMock()
        mongo_client.client = mock_client

        await mongo_client.close()

        mock_client.close.assert_called_once()

    async def test_context_manager(self, mongo_client, mock_motor_client):
        """Testa uso como context manager."""
        mock_instance = AsyncMock()
        mock_motor_client.return_value = mock_instance
        mock_instance.admin.command = AsyncMock(return_value={"ok": 1})

        async with mongo_client as client:
            assert client is mongo_client
            assert mongo_client.client is not None

        # Verificar que close foi chamado
        mock_instance.close.assert_called_once()

    async def test_get_decisions_by_date_range(self, mongo_client):
        """Testa busca por intervalo de datas."""
        start_date = datetime(2026, 1, 1)
        end_date = datetime(2026, 1, 31)

        mock_decisions = [{"decision_id": "decision_1", "created_at": datetime(2026, 1, 15)}]

        # Criar classe para o cursor
        class MockCursor:
            def __init__(self, decisions):
                self.decisions = decisions

            def sort(self, *args, **kwargs):
                return self

            def limit(self, *args, **kwargs):
                return self

            def __aiter__(self):
                return self

            async def __anext__(self):
                if not self.decisions:
                    raise StopAsyncIteration
                return self.decisions.pop(0)

        mock_cursor_instance = MockCursor(mock_decisions[:])

        mongo_client.consensus_collection = AsyncMock()
        mongo_client.consensus_collection.find = Mock(return_value=mock_cursor_instance)

        decisions = await mongo_client.get_decisions_by_date_range(start_date, end_date, limit=100)

        mongo_client.consensus_collection.find.assert_called_once()
        call_args = mongo_client.consensus_collection.find.call_args[0][0]
        assert "created_at" in call_args
        assert "$gte" in call_args["created_at"]
        assert "$lte" in call_args["created_at"]
