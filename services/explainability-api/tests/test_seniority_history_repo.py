"""
Testes para SeniorityHistoryRepository.

Verifica operacoes CRUD de historico de mudancas de senioridade.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class AsyncIteratorMock:
    """Mock iterator for async for loops."""

    def __init__(self, items):
        self.items = iter(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self.items)
        except StopIteration:
            raise StopAsyncIteration


def _create_mock_mongo_client(test_data=None):
    """Cria mock do MongoDB client para testes."""
    if test_data is None:
        test_data = []

    # Mock collection
    collection = MagicMock()

    # Mock async methods - must be AsyncMock!
    collection.insert_one = AsyncMock(return_value=MagicMock(inserted_id="doc_123"))

    # Create a cursor mock for find operations
    def create_find_cursor(*args, **kwargs):
        mock_cursor = MagicMock()
        # Chain sort() and limit() which return the cursor
        mock_cursor.sort = MagicMock(return_value=mock_cursor)
        mock_cursor.limit = MagicMock(return_value=AsyncIteratorMock(test_data))
        return mock_cursor

    collection.find = MagicMock(side_effect=create_find_cursor)

    # Mock database - need to set both attribute and __getitem__
    db = MagicMock()
    db.seniority_history = collection  # Attribute access
    db.__getitem__.return_value = collection  # Dictionary access

    # Mock client
    client = MagicMock()
    client.__getitem__.return_value = db
    client.neural_hive = db  # Also support attribute access

    return client


@pytest.fixture
def mongo_client():
    """Mock MongoDB client."""
    return _create_mock_mongo_client()


@pytest.fixture
def repo(mongo_client):
    """Repository instance."""
    from src.repositories.seniority_history_repo import SeniorityHistoryRepository
    return SeniorityHistoryRepository(mongo_client)


class TestSeniorityHistoryRepository:
    """Testes unitarios para SeniorityHistoryRepository."""

    @pytest.mark.asyncio
    async def test_save_seniority_change(self, repo):
        """Salvar mudanca de senioridade."""
        doc_id = await repo.save_change(
            specialist_id="business_analyst",
            specialist_name="Business Analyst",
            domain="BUSINESS",
            previous_level="mid_level",
            previous_multiplier=1.0,
            new_level="senior",
            new_multiplier=1.5,
            changed_by="admin",
            change_reason="promocao",
            decision_id="decision_123"
        )

        assert doc_id == "doc_123"

        repo.collection.insert_one.assert_called_once()

        # Verify document structure
        call_args = repo.collection.insert_one.call_args[0][0]
        assert call_args["specialist_id"] == "business_analyst"
        assert call_args["new_level"] == "senior"
        assert call_args["previous_level"] == "mid_level"
        assert call_args["changed_by"] == "admin"
        assert call_args["change_reason"] == "promocao"
        assert call_args["decision_id"] == "decision_123"

    @pytest.mark.asyncio
    async def test_save_change_with_all_optional_params(self, repo):
        """Salvar mudanca com todos os parametros opcionais."""
        await repo.save_change(
            specialist_id="tech_lead",
            specialist_name="Tech Lead",
            domain="TECHNICAL",
            previous_level="senior",
            previous_multiplier=1.5,
            new_level="expert",
            new_multiplier=2.0,
            changed_by="system",
            change_reason="auto_promotion",
            decision_id="decision_456",
            plan_id="plan_789"
        )

        call_args = repo.collection.insert_one.call_args[0][0]
        assert call_args["decision_id"] == "decision_456"
        assert call_args["plan_id"] == "plan_789"

    @pytest.mark.asyncio
    async def test_save_change_without_optional_params(self, repo):
        """Salvar mudanca sem parametros opcionais."""
        doc_id = await repo.save_change(
            specialist_id="business_analyst",
            specialist_name="Business Analyst",
            domain="BUSINESS",
            previous_level="mid_level",
            previous_multiplier=1.0,
            new_level="senior",
            new_multiplier=1.5,
            changed_by="admin",
            change_reason="promocao"
        )

        assert doc_id == "doc_123"

        call_args = repo.collection.insert_one.call_args[0][0]
        assert call_args["decision_id"] is None
        assert call_args["plan_id"] is None

    @pytest.mark.asyncio
    async def test_get_history(self):
        """Buscar historico de um especialista."""
        # Setup test data
        test_data = [
            {
                "_id": "doc_1",
                "specialist_id": "business_analyst",
                "new_level": "senior",
                "changed_at": datetime.utcnow()
            },
            {
                "_id": "doc_2",
                "specialist_id": "business_analyst",
                "new_level": "expert",
                "changed_at": datetime.utcnow()
            }
        ]

        mongo_client = _create_mock_mongo_client(test_data)
        from src.repositories.seniority_history_repo import SeniorityHistoryRepository
        repo_instance = SeniorityHistoryRepository(mongo_client)

        changes = await repo_instance.get_history("business_analyst")

        assert len(changes) == 2
        assert changes[0]["new_level"] == "senior"
        assert changes[1]["new_level"] == "expert"
        # Verify _id was removed
        assert "_id" not in changes[0]
        assert "_id" not in changes[1]

        # Verify query
        repo_instance.collection.find.assert_called()
        call_args = repo_instance.collection.find.call_args[0][0]
        assert call_args["specialist_id"] == "business_analyst"

    @pytest.mark.asyncio
    async def test_get_history_empty(self):
        """Buscar historico vazio."""
        mongo_client = _create_mock_mongo_client([])
        from src.repositories.seniority_history_repo import SeniorityHistoryRepository
        repo_instance = SeniorityHistoryRepository(mongo_client)

        changes = await repo_instance.get_history("nonexistent_specialist")

        assert len(changes) == 0

    @pytest.mark.asyncio
    async def test_get_history_limit(self):
        """Buscar historico com limite customizado."""
        test_data = [
            {
                "_id": "doc_1",
                "specialist_id": "spec_1",
                "new_level": "senior",
                "changed_at": datetime.utcnow()
            }
        ]

        mongo_client = _create_mock_mongo_client(test_data)
        from src.repositories.seniority_history_repo import SeniorityHistoryRepository
        repo_instance = SeniorityHistoryRepository(mongo_client)

        changes = await repo_instance.get_history("spec_1", limit=50)

        assert len(changes) == 1
        # Verify the query was made with the specialist_id
        call_args = repo_instance.collection.find.call_args[0][0]
        assert call_args["specialist_id"] == "spec_1"

    @pytest.mark.asyncio
    async def test_get_recent_changes_multiple_specialists(self):
        """Buscar mudancas recentes de varios especialistas."""
        # Setup test data
        test_data = [
            {
                "_id": "doc_1",
                "specialist_id": "spec_1",
                "new_level": "senior",
                "changed_at": datetime.utcnow()
            },
            {
                "_id": "doc_2",
                "specialist_id": "spec_2",
                "new_level": "expert",
                "changed_at": datetime.utcnow()
            }
        ]

        mongo_client = _create_mock_mongo_client(test_data)
        from src.repositories.seniority_history_repo import SeniorityHistoryRepository
        repo_instance = SeniorityHistoryRepository(mongo_client)

        since = datetime.now() - timedelta(days=1)
        changes = await repo_instance.get_recent_changes(
            specialists=["spec_1", "spec_2"],
            since=since
        )

        # Verify query structure
        call_args = repo_instance.collection.find.call_args[0][0]
        assert "specialist_id" in call_args
        assert "$in" in call_args["specialist_id"]
        assert "spec_1" in call_args["specialist_id"]["$in"]
        assert "spec_2" in call_args["specialist_id"]["$in"]
        assert "changed_at" in call_args
        assert "$gte" in call_args["changed_at"]

    @pytest.mark.asyncio
    async def test_get_by_domain(self):
        """Buscar mudancas por dominio."""
        test_data = [
            {
                "_id": "doc_1",
                "domain": "BUSINESS",
                "specialist_id": "spec_1",
                "new_level": "senior",
                "changed_at": datetime.utcnow()
            }
        ]

        mongo_client = _create_mock_mongo_client(test_data)
        from src.repositories.seniority_history_repo import SeniorityHistoryRepository
        repo_instance = SeniorityHistoryRepository(mongo_client)

        since = datetime.now() - timedelta(days=7)
        changes = await repo_instance.get_by_domain("BUSINESS", since=since, limit=50)

        # Verify query
        call_args = repo_instance.collection.find.call_args[0][0]
        assert call_args["domain"] == "BUSINESS"
        assert "changed_at" in call_args
        assert "$gte" in call_args["changed_at"]

    @pytest.mark.asyncio
    async def test_get_by_domain_without_since(self):
        """Buscar mudancas por dominio sem filtro temporal."""
        mongo_client = _create_mock_mongo_client([])
        from src.repositories.seniority_history_repo import SeniorityHistoryRepository
        repo_instance = SeniorityHistoryRepository(mongo_client)

        changes = await repo_instance.get_by_domain("TECHNICAL")

        # Verify query
        call_args = repo_instance.collection.find.call_args[0][0]
        assert call_args["domain"] == "TECHNICAL"
        assert "changed_at" not in call_args  # No temporal filter

    @pytest.mark.asyncio
    async def test_parse_cursor_removes_id(self):
        """Verifica que _id eh removido dos resultados."""
        test_data = [
            {
                "_id": "doc_123",
                "specialist_id": "test_spec",
                "new_level": "senior"
            }
        ]

        cursor = AsyncIteratorMock(test_data)

        mongo_client = _create_mock_mongo_client()
        from src.repositories.seniority_history_repo import SeniorityHistoryRepository
        repo_instance = SeniorityHistoryRepository(mongo_client)

        results = await repo_instance._parse_cursor(cursor)

        assert len(results) == 1
        assert "_id" not in results[0]
        assert results[0]["specialist_id"] == "test_spec"
