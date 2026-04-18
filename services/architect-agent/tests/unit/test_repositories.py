"""Testes unitários para repositórios."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from src.models.architecture import (
    ArchitecturePlan,
    ArchitectureType,
    Component,
    Pattern,
)
from src.models.evolution import EvolutionHistory
from src.models.validation import (
    Trend,
    ValidationReport,
)
from src.repositories.architecture_repository import ArchitectureRepository
from src.repositories.evolution_repository import EvolutionRepository
from src.repositories.validation_repository import ValidationRepository


@pytest.fixture
def mock_mongo_client():
    """Mock MongoDB client singleton."""
    client = MagicMock()
    db = MagicMock()
    collection = MagicMock()
    client.__getitem__ = Mock(return_value=db)
    db.__getitem__ = Mock(return_value=collection)
    return client


@pytest.fixture
def mock_settings():
    """Mock settings."""
    with patch("src.repositories.base.get_settings") as mock:
        settings = Mock()
        settings.mongodb.url = "mongodb://localhost:27017"
        settings.mongodb.database = "test_db"
        settings.mongodb.collection_architecture = "test_arch"
        settings.mongodb.collection_validation = "test_validation"
        settings.mongodb.collection_evolution = "test_evolution"
        mock.return_value = settings
        yield mock


@pytest.fixture(autouse=True)
def reset_mongo_singleton():
    """Reseta o singleton do MongoDB entre testes."""
    import src.repositories.base as base_module

    original_client = base_module._mongo_client
    base_module._mongo_client = None
    yield
    base_module._mongo_client = original_client


# BaseRepository Tests
@pytest.mark.asyncio
async def test_base_repository_initializes(mock_settings, mock_mongo_client):
    with patch("src.repositories.base.get_mongo_client", return_value=mock_mongo_client):
        repo = ArchitectureRepository()
        assert repo.collection is not None


# ArchitectureRepository Tests
@pytest.mark.asyncio
async def test_architecture_repo_create(mock_settings):
    mock_client = MagicMock()
    mock_db = MagicMock()
    mock_collection = MagicMock()
    mock_collection.insert_one = AsyncMock(return_value=Mock(inserted_id="test-id"))
    mock_db.__getitem__ = Mock(return_value=mock_collection)
    mock_client.__getitem__ = Mock(return_value=mock_db)

    with patch("src.repositories.base.get_mongo_client", return_value=mock_client):
        repo = ArchitectureRepository()

        plan = ArchitecturePlan(
            plan_id="test-plan",
            cognitive_plan_id=None,
            architecture_type=ArchitectureType.MICROSERVICES,
            components=[Component(name="api", stack="python/fastapi")],
            patterns=[Pattern.REPOSITORY],
            rationale="Test",
        )

        result = await repo.create(plan)
        assert result == "test-plan"


@pytest.mark.asyncio
async def test_architecture_repo_get_by_plan_id(mock_settings):
    mock_client = MagicMock()
    mock_db = MagicMock()
    mock_collection = MagicMock()
    mock_collection.find_one = AsyncMock(
        return_value={
            "_id": "test-plan",
            "plan_id": "test-plan",
            "architecture_type": "microservices",
            "components": [
                {
                    "name": "api",
                    "stack": "python/fastapi",
                    "replicas": 1,
                    "ha": False,
                    "resources": {},
                }
            ],
            "patterns": ["repository"],
            "rationale": "Test",
            "requirements": {},
        }
    )
    mock_db.__getitem__ = Mock(return_value=mock_collection)
    mock_client.__getitem__ = Mock(return_value=mock_db)

    with patch("src.repositories.base.get_mongo_client", return_value=mock_client):
        repo = ArchitectureRepository()
        result = await repo.get_by_plan_id("test-plan")
        assert result is not None
        assert result.plan_id == "test-plan"


@pytest.mark.asyncio
async def test_architecture_repo_get_by_plan_id_not_found(mock_settings):
    mock_client = MagicMock()
    mock_db = MagicMock()
    mock_collection = MagicMock()
    mock_collection.find_one = AsyncMock(return_value=None)
    mock_db.__getitem__ = Mock(return_value=mock_collection)
    mock_client.__getitem__ = Mock(return_value=mock_db)

    with patch("src.repositories.base.get_mongo_client", return_value=mock_client):
        repo = ArchitectureRepository()
        result = await repo.get_by_plan_id("nonexistent")
        assert result is None


@pytest.mark.asyncio
async def test_architecture_repo_get_by_cognitive_plan_id(mock_settings):
    mock_client = MagicMock()
    mock_db = MagicMock()
    mock_collection = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(
        return_value=[
            {
                "_id": "arch-1",
                "plan_id": "arch-1",
                "cognitive_plan_id": "cog-1",
                "architecture_type": "microservices",
                "components": [],
                "patterns": [],
                "rationale": "Test",
                "requirements": {},
            }
        ]
    )
    mock_collection.find = Mock(return_value=mock_cursor)
    mock_db.__getitem__ = Mock(return_value=mock_collection)
    mock_client.__getitem__ = Mock(return_value=mock_db)

    with patch("src.repositories.base.get_mongo_client", return_value=mock_client):
        repo = ArchitectureRepository()
        results = await repo.get_by_cognitive_plan_id("cog-1")
        assert len(results) == 1
        assert results[0].cognitive_plan_id == "cog-1"


@pytest.mark.asyncio
async def test_architecture_repo_list_by_type(mock_settings):
    mock_client = MagicMock()
    mock_db = MagicMock()
    mock_collection = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=[])
    mock_cursor.limit = Mock(return_value=mock_cursor)
    mock_collection.find = Mock(return_value=mock_cursor)
    mock_db.__getitem__ = Mock(return_value=mock_collection)
    mock_client.__getitem__ = Mock(return_value=mock_db)

    with patch("src.repositories.base.get_mongo_client", return_value=mock_client):
        repo = ArchitectureRepository()
        results = await repo.list_by_type(ArchitectureType.MICROSERVICES)
        assert isinstance(results, list)


@pytest.mark.asyncio
async def test_architecture_repo_update_rationale(mock_settings):
    mock_client = MagicMock()
    mock_db = MagicMock()
    mock_collection = MagicMock()
    mock_result = Mock()
    mock_result.modified_count = 1
    mock_collection.update_one = AsyncMock(return_value=mock_result)
    mock_db.__getitem__ = Mock(return_value=mock_collection)
    mock_client.__getitem__ = Mock(return_value=mock_db)

    with patch("src.repositories.base.get_mongo_client", return_value=mock_client):
        repo = ArchitectureRepository()
        result = await repo.update_rationale("test-plan", "New rationale")
        assert result is True


@pytest.mark.asyncio
async def test_architecture_repo_create_duplicate_raises_error(mock_settings):
    from pymongo.errors import DuplicateKeyError

    mock_client = MagicMock()
    mock_db = MagicMock()
    mock_collection = MagicMock()
    mock_collection.insert_one = AsyncMock(side_effect=DuplicateKeyError("E11000"))
    mock_db.__getitem__ = Mock(return_value=mock_collection)
    mock_client.__getitem__ = Mock(return_value=mock_db)

    with patch("src.repositories.base.get_mongo_client", return_value=mock_client):
        repo = ArchitectureRepository()
        plan = ArchitecturePlan(
            plan_id="test-plan",
            cognitive_plan_id=None,
            architecture_type=ArchitectureType.MICROSERVICES,
            components=[],
            patterns=[],
            rationale="Test",
        )

        with pytest.raises(ValueError, match="já existe"):
            await repo.create(plan)


# ValidationRepository Tests
@pytest.mark.asyncio
async def test_validation_repo_create(mock_settings):
    mock_client = MagicMock()
    mock_db = MagicMock()
    mock_collection = MagicMock()
    mock_collection.insert_one = AsyncMock(return_value=Mock(inserted_id="val-123"))
    mock_db.__getitem__ = Mock(return_value=mock_collection)
    mock_client.__getitem__ = Mock(return_value=mock_db)

    with patch("src.repositories.base.get_mongo_client", return_value=mock_client):
        repo = ValidationRepository()

        report = ValidationReport(
            report_id="val-123",
            repo_url="github.com/test/repo",
            branch="main",
            health_score=75,
            trend=Trend.STABLE,
            violations=[],
            suggestions=[],
        )

        result = await repo.create(report)
        assert result == "val-123"


@pytest.mark.asyncio
async def test_validation_repo_get_by_report_id(mock_settings):
    mock_client = MagicMock()
    mock_db = MagicMock()
    mock_collection = MagicMock()
    mock_collection.find_one = AsyncMock(
        return_value={
            "_id": "val-123",
            "report_id": "val-123",
            "repo_url": "github.com/test/repo",
            "branch": "main",
            "health_score": 75,
            "trend": "stable",
            "violations": [],
            "suggestions": [],
            "metrics": {},
            "created_at": datetime.now(UTC),
        }
    )
    mock_db.__getitem__ = Mock(return_value=mock_collection)
    mock_client.__getitem__ = Mock(return_value=mock_db)

    with patch("src.repositories.base.get_mongo_client", return_value=mock_client):
        repo = ValidationRepository()
        result = await repo.get_by_report_id("val-123")
        assert result is not None
        assert result.report_id == "val-123"


@pytest.mark.asyncio
async def test_validation_repo_get_by_report_id_not_found(mock_settings):
    mock_client = MagicMock()
    mock_db = MagicMock()
    mock_collection = MagicMock()
    mock_collection.find_one = AsyncMock(return_value=None)
    mock_db.__getitem__ = Mock(return_value=mock_collection)
    mock_client.__getitem__ = Mock(return_value=mock_db)

    with patch("src.repositories.base.get_mongo_client", return_value=mock_client):
        repo = ValidationRepository()
        result = await repo.get_by_report_id("nonexistent")
        assert result is None


@pytest.mark.asyncio
async def test_validation_repo_get_by_repo_url(mock_settings):
    mock_client = MagicMock()
    mock_db = MagicMock()
    mock_collection = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.limit = Mock(return_value=mock_cursor)
    mock_cursor.sort = Mock(return_value=mock_cursor)
    mock_cursor.to_list = AsyncMock(
        return_value=[
            {
                "_id": "val-123",
                "report_id": "val-123",
                "repo_url": "github.com/test/repo",
                "branch": "main",
                "health_score": 75,
                "trend": "stable",
                "violations": [],
                "suggestions": [],
                "metrics": {},
                "created_at": datetime.now(UTC),
            }
        ]
    )
    mock_collection.find = Mock(return_value=mock_cursor)
    mock_db.__getitem__ = Mock(return_value=mock_collection)
    mock_client.__getitem__ = Mock(return_value=mock_db)

    with patch("src.repositories.base.get_mongo_client", return_value=mock_client):
        repo = ValidationRepository()
        results = await repo.get_by_repo_url("github.com/test/repo")
        assert len(results) == 1
        assert results[0].repo_url == "github.com/test/repo"


@pytest.mark.asyncio
async def test_validation_repo_get_latest_by_repo(mock_settings):
    mock_client = MagicMock()
    mock_db = MagicMock()
    mock_collection = MagicMock()
    mock_collection.find_one = AsyncMock(
        return_value={
            "_id": "val-123",
            "report_id": "val-123",
            "repo_url": "github.com/test/repo",
            "branch": "main",
            "health_score": 75,
            "trend": "stable",
            "violations": [],
            "suggestions": [],
            "metrics": {},
            "created_at": datetime.now(UTC),
        }
    )
    mock_db.__getitem__ = Mock(return_value=mock_collection)
    mock_client.__getitem__ = Mock(return_value=mock_db)

    with patch("src.repositories.base.get_mongo_client", return_value=mock_client):
        repo = ValidationRepository()
        result = await repo.get_latest_by_repo("github.com/test/repo")
        assert result is not None
        assert result.repo_url == "github.com/test/repo"


@pytest.mark.asyncio
async def test_validation_repo_get_latest_by_repo_not_found(mock_settings):
    mock_client = MagicMock()
    mock_db = MagicMock()
    mock_collection = MagicMock()
    mock_collection.find_one = AsyncMock(return_value=None)
    mock_db.__getitem__ = Mock(return_value=mock_collection)
    mock_client.__getitem__ = Mock(return_value=mock_db)

    with patch("src.repositories.base.get_mongo_client", return_value=mock_client):
        repo = ValidationRepository()
        result = await repo.get_latest_by_repo("github.com/test/repo")
        assert result is None


@pytest.mark.asyncio
async def test_validation_repo_get_low_health_scores(mock_settings):
    mock_client = MagicMock()
    mock_db = MagicMock()
    mock_collection = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.limit = Mock(return_value=mock_cursor)
    mock_cursor.sort = Mock(return_value=mock_cursor)
    mock_cursor.to_list = AsyncMock(return_value=[])
    mock_collection.find = Mock(return_value=mock_cursor)
    mock_db.__getitem__ = Mock(return_value=mock_collection)
    mock_client.__getitem__ = Mock(return_value=mock_db)

    with patch("src.repositories.base.get_mongo_client", return_value=mock_client):
        repo = ValidationRepository()
        results = await repo.get_low_health_scores(threshold=50)
        assert isinstance(results, list)


@pytest.mark.asyncio
async def test_validation_repo_get_average_health_score(mock_settings):
    mock_client = MagicMock()
    mock_db = MagicMock()
    mock_collection = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=[{"_id": None, "avg_score": 72.5}])
    mock_collection.aggregate = Mock(return_value=mock_cursor)
    mock_db.__getitem__ = Mock(return_value=mock_collection)
    mock_client.__getitem__ = Mock(return_value=mock_db)

    with patch("src.repositories.base.get_mongo_client", return_value=mock_client):
        repo = ValidationRepository()
        result = await repo.get_average_health_score()
        assert result == 72.5


@pytest.mark.asyncio
async def test_validation_repo_get_average_health_score_no_data(mock_settings):
    mock_client = MagicMock()
    mock_db = MagicMock()
    mock_collection = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=[])
    mock_collection.aggregate = Mock(return_value=mock_cursor)
    mock_db.__getitem__ = Mock(return_value=mock_collection)
    mock_client.__getitem__ = Mock(return_value=mock_db)

    with patch("src.repositories.base.get_mongo_client", return_value=mock_client):
        repo = ValidationRepository()
        result = await repo.get_average_health_score()
        assert result == 0.0


@pytest.mark.asyncio
async def test_validation_repo_get_average_health_score_with_repo_filter(mock_settings):
    mock_client = MagicMock()
    mock_db = MagicMock()
    mock_collection = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=[{"_id": None, "avg_score": 68.0}])
    mock_collection.aggregate = Mock(return_value=mock_cursor)
    mock_db.__getitem__ = Mock(return_value=mock_collection)
    mock_client.__getitem__ = Mock(return_value=mock_db)

    with patch("src.repositories.base.get_mongo_client", return_value=mock_client):
        repo = ValidationRepository()
        result = await repo.get_average_health_score(repo_url="github.com/test/repo")
        assert result == 68.0


# EvolutionRepository Tests
@pytest.mark.asyncio
async def test_evolution_repo_create(mock_settings):
    mock_client = MagicMock()
    mock_db = MagicMock()
    mock_collection = MagicMock()
    mock_collection.insert_one = AsyncMock(return_value=Mock(inserted_id="evo-123"))
    mock_db.__getitem__ = Mock(return_value=mock_collection)
    mock_client.__getitem__ = Mock(return_value=mock_db)

    with patch("src.repositories.base.get_mongo_client", return_value=mock_client):
        repo = EvolutionRepository()

        history = EvolutionHistory(
            history_id="evo-123",
            plan_id="arch-123",
            version=1,
            changes=["Initial version"],
            drifts=[],
        )

        result = await repo.create(history)
        assert result == "evo-123"


@pytest.mark.asyncio
async def test_evolution_repo_get_by_plan_id(mock_settings):
    mock_client = MagicMock()
    mock_db = MagicMock()
    mock_collection = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.limit = Mock(return_value=mock_cursor)
    mock_cursor.sort = Mock(return_value=mock_cursor)
    mock_cursor.to_list = AsyncMock(
        return_value=[
            {
                "_id": "evo-123",
                "history_id": "evo-123",
                "plan_id": "arch-123",
                "version": 1,
                "changes": ["Initial"],
                "drifts": [],
                "created_at": datetime.now(UTC),
                "created_by": "architect-agent",
            }
        ]
    )
    mock_collection.find = Mock(return_value=mock_cursor)
    mock_db.__getitem__ = Mock(return_value=mock_collection)
    mock_client.__getitem__ = Mock(return_value=mock_db)

    with patch("src.repositories.base.get_mongo_client", return_value=mock_client):
        repo = EvolutionRepository()
        results = await repo.get_by_plan_id("arch-123")
        assert len(results) == 1
        assert results[0].plan_id == "arch-123"


@pytest.mark.asyncio
async def test_evolution_repo_get_recent(mock_settings):
    mock_client = MagicMock()
    mock_db = MagicMock()
    mock_collection = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.limit = Mock(return_value=mock_cursor)
    mock_cursor.sort = Mock(return_value=mock_cursor)
    mock_cursor.to_list = AsyncMock(return_value=[])
    mock_collection.find = Mock(return_value=mock_cursor)
    mock_db.__getitem__ = Mock(return_value=mock_collection)
    mock_client.__getitem__ = Mock(return_value=mock_db)

    with patch("src.repositories.base.get_mongo_client", return_value=mock_client):
        repo = EvolutionRepository()
        results = await repo.get_recent()
        assert isinstance(results, list)


@pytest.mark.asyncio
async def test_evolution_repo_count_drifts_by_plan(mock_settings):
    mock_client = MagicMock()
    mock_db = MagicMock()
    mock_collection = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=[{"total": 3}])
    mock_collection.aggregate = Mock(return_value=mock_cursor)
    mock_db.__getitem__ = Mock(return_value=mock_collection)
    mock_client.__getitem__ = Mock(return_value=mock_db)

    with patch("src.repositories.base.get_mongo_client", return_value=mock_client):
        repo = EvolutionRepository()
        result = await repo.count_drifts_by_plan("arch-123")
        assert result == 3


@pytest.mark.asyncio
async def test_evolution_repo_count_drifts_by_plan_no_drifts(mock_settings):
    mock_client = MagicMock()
    mock_db = MagicMock()
    mock_collection = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=[])
    mock_collection.aggregate = Mock(return_value=mock_cursor)
    mock_db.__getitem__ = Mock(return_value=mock_collection)
    mock_client.__getitem__ = Mock(return_value=mock_db)

    with patch("src.repositories.base.get_mongo_client", return_value=mock_client):
        repo = EvolutionRepository()
        result = await repo.count_drifts_by_plan("arch-123")
        assert result == 0


@pytest.mark.asyncio
async def test_evolution_repo_count_drifts_by_plan_empty_drifts_list(mock_settings):
    mock_client = MagicMock()
    mock_db = MagicMock()
    mock_collection = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=[{"total": 0}])
    mock_collection.aggregate = Mock(return_value=mock_cursor)
    mock_db.__getitem__ = Mock(return_value=mock_collection)
    mock_client.__getitem__ = Mock(return_value=mock_db)

    with patch("src.repositories.base.get_mongo_client", return_value=mock_client):
        repo = EvolutionRepository()
        result = await repo.count_drifts_by_plan("arch-456")
        assert result == 0
