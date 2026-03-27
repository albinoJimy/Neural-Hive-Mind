"""Testes unitários para repositórios."""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timezone

from src.repositories.base import BaseRepository
from src.repositories.architecture_repository import ArchitectureRepository
from src.repositories.validation_repository import ValidationRepository
from src.repositories.evolution_repository import EvolutionRepository
from src.models.architecture import (
    ArchitecturePlan,
    ArchitectureType,
    Component,
    Pattern,
)
from src.models.validation import (
    ValidationReport,
    Violation,
    Severity,
    ViolationType,
    Trend,
)
from src.models.evolution import EvolutionHistory


@pytest.fixture
def mock_mongo_client():
    with patch("motor.motor_asyncio.AsyncIOMotorClient") as mock:
        client = Mock()
        mock.return_value = client
        yield client


@pytest.fixture
def mock_settings():
    with patch("src.repositories.base.get_settings") as mock:
        settings = Mock()
        settings.mongodb.url = "mongodb://localhost:27017"
        settings.mongodb.database = "test_db"
        settings.mongodb.collection_architecture = "test_arch"
        settings.mongodb.collection_validation = "test_validation"
        settings.mongodb.collection_evolution = "test_evolution"
        mock.return_value = settings
        yield mock


# BaseRepository Tests
@pytest.mark.asyncio
async def test_base_repository_initializes():
    with patch("src.repositories.architecture_repository.AsyncIOMotorClient"):
        from src.repositories.architecture_repository import ArchitectureRepository

        repo = ArchitectureRepository()
        assert repo.collection is not None


# ArchitectureRepository Tests
@pytest.mark.asyncio
async def test_architecture_repo_create():
    with patch("src.repositories.architecture_repository.AsyncIOMotorClient"):
        repo = ArchitectureRepository()
        repo.collection = Mock()
        repo.collection.insert_one = AsyncMock(return_value=Mock(inserted_id="test-id"))

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
async def test_architecture_repo_get_by_plan_id():
    with patch("src.repositories.architecture_repository.AsyncIOMotorClient"):
        repo = ArchitectureRepository()
        repo.collection = Mock()
        repo.collection.find_one = AsyncMock(
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
                "created_at": datetime.now(timezone.utc),
            }
        )

        result = await repo.get_by_plan_id("test-plan")
        assert result is not None
        assert result.plan_id == "test-plan"


@pytest.mark.asyncio
async def test_architecture_repo_get_by_plan_id_not_found():
    with patch("src.repositories.architecture_repository.AsyncIOMotorClient"):
        repo = ArchitectureRepository()
        repo.collection = Mock()
        repo.collection.find_one = AsyncMock(return_value=None)

        result = await repo.get_by_plan_id("nonexistent")
        assert result is None


@pytest.mark.asyncio
async def test_architecture_repo_get_by_cognitive_plan_id():
    with patch("src.repositories.architecture_repository.AsyncIOMotorClient"):
        repo = ArchitectureRepository()
        repo.collection = Mock()
        repo.collection.find = Mock()
        cursor = Mock()
        cursor.to_list = AsyncMock(
            return_value=[
                {
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
                    "created_at": datetime.now(timezone.utc),
                }
            ]
        )
        repo.collection.find.return_value = cursor

        results = await repo.get_by_cognitive_plan_id("cp-123")
        assert len(results) == 1
        assert results[0].plan_id == "test-plan"


@pytest.mark.asyncio
async def test_architecture_repo_list_by_type():
    with patch("src.repositories.architecture_repository.AsyncIOMotorClient"):
        repo = ArchitectureRepository()
        repo.collection = Mock()
        repo.collection.find = Mock()
        cursor = Mock()
        cursor.limit = Mock(return_value=cursor)
        cursor.to_list = AsyncMock(
            return_value=[
                {
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
                    "created_at": datetime.now(timezone.utc),
                }
            ]
        )
        repo.collection.find.return_value = cursor

        results = await repo.list_by_type(ArchitectureType.MICROSERVICES)
        assert len(results) == 1
        assert results[0].architecture_type == ArchitectureType.MICROSERVICES


@pytest.mark.asyncio
async def test_architecture_repo_update_rationale():
    with patch("src.repositories.architecture_repository.AsyncIOMotorClient"):
        repo = ArchitectureRepository()
        repo.collection = Mock()
        repo.collection.update_one = AsyncMock(return_value=Mock(modified_count=1))

        result = await repo.update_rationale("test-plan", "Updated rationale")
        assert result is True


@pytest.mark.asyncio
async def test_architecture_repo_create_duplicate_raises_error():
    with patch("src.repositories.architecture_repository.AsyncIOMotorClient"):
        repo = ArchitectureRepository()
        repo.collection = Mock()
        repo.collection.insert_one = AsyncMock(side_effect=Exception("Duplicate key"))

        plan = ArchitecturePlan(
            plan_id="test-plan",
            cognitive_plan_id=None,
            architecture_type=ArchitectureType.MICROSERVICES,
            components=[Component(name="api", stack="python/fastapi")],
            patterns=[Pattern.REPOSITORY],
            rationale="Test",
        )

        with pytest.raises(ValueError, match="já existe"):
            await repo.create(plan)


# ValidationRepository Tests
@pytest.mark.asyncio
async def test_validation_repo_create():
    with patch("src.repositories.validation_repository.AsyncIOMotorClient"):
        repo = ValidationRepository()
        repo.collection = Mock()
        repo.collection.insert_one = AsyncMock(return_value=Mock(inserted_id="test-id"))

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
async def test_validation_repo_get_by_report_id():
    with patch("src.repositories.validation_repository.AsyncIOMotorClient"):
        repo = ValidationRepository()
        repo.collection = Mock()
        repo.collection.find_one = AsyncMock(
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
                "created_at": datetime.now(timezone.utc),
            }
        )

        result = await repo.get_by_report_id("val-123")
        assert result is not None
        assert result.report_id == "val-123"


@pytest.mark.asyncio
async def test_validation_repo_get_by_report_id_not_found():
    with patch("src.repositories.validation_repository.AsyncIOMotorClient"):
        repo = ValidationRepository()
        repo.collection = Mock()
        repo.collection.find_one = AsyncMock(return_value=None)

        result = await repo.get_by_report_id("nonexistent")
        assert result is None


@pytest.mark.asyncio
async def test_validation_repo_get_by_repo_url():
    with patch("src.repositories.validation_repository.AsyncIOMotorClient"):
        repo = ValidationRepository()
        repo.collection = Mock()
        repo.collection.find = Mock()
        cursor = Mock()
        cursor.sort = Mock(return_value=cursor)
        cursor.limit = Mock(return_value=cursor)
        cursor.to_list = AsyncMock(
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
                    "created_at": datetime.now(timezone.utc),
                }
            ]
        )
        repo.collection.find.return_value = cursor

        results = await repo.get_by_repo_url("github.com/test/repo")
        assert len(results) == 1
        assert results[0].repo_url == "github.com/test/repo"


@pytest.mark.asyncio
async def test_validation_repo_get_latest_by_repo():
    with patch("src.repositories.validation_repository.AsyncIOMotorClient"):
        repo = ValidationRepository()
        repo.collection = Mock()
        repo.collection.find_one = AsyncMock(
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
                "created_at": datetime.now(timezone.utc),
            }
        )

        result = await repo.get_latest_by_repo("github.com/test/repo")
        assert result is not None
        assert result.repo_url == "github.com/test/repo"


@pytest.mark.asyncio
async def test_validation_repo_get_latest_by_repo_not_found():
    with patch("src.repositories.validation_repository.AsyncIOMotorClient"):
        repo = ValidationRepository()
        repo.collection = Mock()
        repo.collection.find_one = AsyncMock(return_value=None)

        result = await repo.get_latest_by_repo("nonexistent")
        assert result is None


@pytest.mark.asyncio
async def test_validation_repo_get_low_health_scores():
    with patch("src.repositories.validation_repository.AsyncIOMotorClient"):
        repo = ValidationRepository()
        repo.collection = Mock()
        repo.collection.find = Mock()
        cursor = Mock()
        cursor.sort = Mock(return_value=cursor)
        cursor.limit = Mock(return_value=cursor)
        cursor.to_list = AsyncMock(
            return_value=[
                {
                    "_id": "val-123",
                    "report_id": "val-123",
                    "repo_url": "github.com/test/repo",
                    "branch": "main",
                    "health_score": 30,
                    "trend": "down",
                    "violations": [],
                    "suggestions": [],
                    "metrics": {},
                    "created_at": datetime.now(timezone.utc),
                }
            ]
        )
        repo.collection.find.return_value = cursor

        results = await repo.get_low_health_scores(threshold=50)
        assert len(results) == 1
        assert results[0].health_score == 30


@pytest.mark.asyncio
async def test_validation_repo_get_average_health_score():
    with patch("src.repositories.validation_repository.AsyncIOMotorClient"):
        repo = ValidationRepository()
        repo.collection = Mock()
        repo.collection.aggregate = Mock()
        cursor = Mock()
        cursor.to_list = AsyncMock(return_value=[{"_id": None, "avg_score": 72.5}])
        repo.collection.aggregate.return_value = cursor

        result = await repo.get_average_health_score()
        assert result == 72.5


@pytest.mark.asyncio
async def test_validation_repo_get_average_health_score_no_data():
    with patch("src.repositories.validation_repository.AsyncIOMotorClient"):
        repo = ValidationRepository()
        repo.collection = Mock()
        repo.collection.aggregate = Mock()
        cursor = Mock()
        cursor.to_list = AsyncMock(return_value=[])
        repo.collection.aggregate.return_value = cursor

        result = await repo.get_average_health_score()
        assert result == 0.0


@pytest.mark.asyncio
async def test_validation_repo_get_average_health_score_with_repo_filter():
    with patch("src.repositories.validation_repository.AsyncIOMotorClient"):
        repo = ValidationRepository()
        repo.collection = Mock()
        repo.collection.aggregate = Mock()
        cursor = Mock()
        cursor.to_list = AsyncMock(return_value=[{"_id": None, "avg_score": 80.0}])
        repo.collection.aggregate.return_value = cursor

        result = await repo.get_average_health_score(repo_url="github.com/test/repo")
        assert result == 80.0


# EvolutionRepository Tests
@pytest.mark.asyncio
async def test_evolution_repo_create():
    with patch("src.repositories.evolution_repository.AsyncIOMotorClient"):
        repo = EvolutionRepository()
        repo.collection = Mock()
        repo.collection.insert_one = AsyncMock(return_value=Mock(inserted_id="test-id"))

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
async def test_evolution_repo_get_by_plan_id():
    with patch("src.repositories.evolution_repository.AsyncIOMotorClient"):
        repo = EvolutionRepository()
        repo.collection = Mock()
        repo.collection.find = Mock()
        cursor = Mock()
        cursor.sort = Mock(return_value=cursor)
        cursor.limit = Mock(return_value=cursor)
        cursor.to_list = AsyncMock(
            return_value=[
                {
                    "_id": "evo-123",
                    "history_id": "evo-123",
                    "plan_id": "arch-123",
                    "version": 1,
                    "changes": ["Initial"],
                    "drifts": [],
                    "created_at": datetime.now(timezone.utc),
                    "created_by": "architect-agent",
                }
            ]
        )
        repo.collection.find.return_value = cursor

        results = await repo.get_by_plan_id("arch-123")
        assert len(results) == 1
        assert results[0].plan_id == "arch-123"


@pytest.mark.asyncio
async def test_evolution_repo_get_recent():
    with patch("src.repositories.evolution_repository.AsyncIOMotorClient"):
        repo = EvolutionRepository()
        repo.collection = Mock()
        repo.collection.find = Mock()
        cursor = Mock()
        cursor.sort = Mock(return_value=cursor)
        cursor.limit = Mock(return_value=cursor)
        cursor.to_list = AsyncMock(
            return_value=[
                {
                    "_id": "evo-123",
                    "history_id": "evo-123",
                    "plan_id": "arch-123",
                    "version": 1,
                    "changes": ["Initial"],
                    "drifts": [],
                    "created_at": datetime.now(timezone.utc),
                    "created_by": "architect-agent",
                }
            ]
        )
        repo.collection.find.return_value = cursor

        results = await repo.get_recent()
        assert len(results) == 1


@pytest.mark.asyncio
async def test_evolution_repo_count_drifts_by_plan():
    with patch("src.repositories.evolution_repository.AsyncIOMotorClient"):
        repo = EvolutionRepository()
        repo.collection = Mock()
        repo.collection.aggregate = Mock()
        cursor = Mock()
        cursor.to_list = AsyncMock(return_value=[{"total": 3}])
        repo.collection.aggregate.return_value = cursor

        result = await repo.count_drifts_by_plan("arch-123")
        assert result == 3


@pytest.mark.asyncio
async def test_evolution_repo_count_drifts_by_plan_no_drifts():
    with patch("src.repositories.evolution_repository.AsyncIOMotorClient"):
        repo = EvolutionRepository()
        repo.collection = Mock()
        repo.collection.aggregate = Mock()
        cursor = Mock()
        cursor.to_list = AsyncMock(return_value=[])
        repo.collection.aggregate.return_value = cursor

        result = await repo.count_drifts_by_plan("arch-123")
        assert result == 0


@pytest.mark.asyncio
async def test_evolution_repo_count_drifts_by_plan_empty_drifts_list():
    with patch("src.repositories.evolution_repository.AsyncIOMotorClient"):
        repo = EvolutionRepository()
        repo.collection = Mock()
        repo.collection.aggregate = Mock()
        # When $unwind is applied to an empty array, no documents are produced
        cursor = Mock()
        cursor.to_list = AsyncMock(return_value=[])
        repo.collection.aggregate.return_value = cursor

        result = await repo.count_drifts_by_plan("arch-123")
        assert result == 0
