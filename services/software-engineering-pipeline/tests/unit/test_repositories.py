from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.models.pipeline import PipelineRun
from src.models.schemas import AnomalyType, PipelineStatus
from src.repositories.pipeline_repository import (
    AnomalyRepository,
    PipelineRunRepository,
)


@pytest.mark.asyncio()
async def test_create_and_find_run():
    """Test creating and finding a pipeline run."""
    repo = PipelineRunRepository()

    run = PipelineRun(
        run_id="test-run-1",
        manifest_id="manifest-1",
        repo_url="https://github.com/org/repo",
        git_sha="abc123",
        status=PipelineStatus.RUNNING,
    )

    # Mock the collection methods
    repo.collection.insert_one = AsyncMock(return_value=MagicMock(inserted_id="mock-id"))
    repo.collection.find_one = AsyncMock(
        return_value={
            "_id": "mock-id",
            "run_id": "test-run-1",
            "status": PipelineStatus.RUNNING.value,
        }
    )

    run_id = await repo.create(run)
    assert run_id is not None

    found = await repo.find_by_id(run_id)
    assert found is not None
    assert found["run_id"] == "test-run-1"


@pytest.mark.asyncio()
async def test_update_run_status():
    """Test updating pipeline run status."""
    repo = PipelineRunRepository()

    run = PipelineRun(
        run_id="test-run-2",
        manifest_id="manifest-1",
        repo_url="https://github.com/org/repo",
        git_sha="abc123",
        status=PipelineStatus.RUNNING,
    )

    # Mock the collection methods
    repo.collection.insert_one = AsyncMock(return_value=MagicMock(inserted_id="mock-id-2"))
    repo.collection.update_one = AsyncMock(return_value=MagicMock(modified_count=1))

    run_id = await repo.create(run)

    updated = await repo.update_status(
        run_id,
        PipelineStatus.SUCCESS,
        finished_at=datetime.now(UTC),
        duration_seconds=120,
    )

    assert updated is True


@pytest.mark.asyncio()
async def test_find_unresolved_anomalies():
    """Test finding unresolved anomalies."""
    repo = AnomalyRepository()

    # Mock the find method - need to properly chain the cursor methods
    async_mock_cursor = AsyncMock()
    async_mock_cursor.sort = MagicMock(return_value=async_mock_cursor)
    async_mock_cursor.limit = MagicMock(return_value=async_mock_cursor)
    async_mock_cursor.to_list = AsyncMock(
        return_value=[
            {
                "_id": "anom-1",
                "anomaly_id": "anom-1",
                "repo_url": "https://github.com/org/repo",
                "type": AnomalyType.FLAKY_TEST.value,
                "severity": "medium",
                "description": "Test is flaky",
                "resolved": False,
            },
        ]
    )

    repo.collection.find = MagicMock(return_value=async_mock_cursor)

    unresolved = await repo.find_unresolved("https://github.com/org/repo")

    assert len(unresolved) == 1
    assert unresolved[0]["anomaly_id"] == "anom-1"
    assert unresolved[0]["resolved"] is False


@pytest.mark.asyncio()
async def test_mark_anomaly_resolved():
    """Test marking an anomaly as resolved."""
    repo = AnomalyRepository()

    # Mock the update method
    repo.collection.update_one = AsyncMock(return_value=MagicMock(modified_count=1))

    resolved = await repo.mark_resolved("anom-3")

    assert resolved is True


@pytest.mark.asyncio()
async def test_find_many_with_filter():
    """Test finding multiple documents with filter."""
    repo = PipelineRunRepository()

    # Mock the find method
    mock_cursor = MagicMock()
    mock_cursor.skip = MagicMock(return_value=mock_cursor)
    mock_cursor.limit = MagicMock(return_value=mock_cursor)
    mock_cursor.sort = MagicMock(return_value=mock_cursor)
    mock_cursor.to_list = AsyncMock(
        return_value=[
            {"run_id": "run-1", "status": "success"},
            {"run_id": "run-2", "status": "success"},
        ]
    )

    repo.collection.find = MagicMock(return_value=mock_cursor)

    results = await repo.find_many(
        filter_dict={"status": "success"},
        skip=0,
        limit=10,
        sort=[("started_at", -1)],
    )

    assert len(results) == 2
    assert results[0]["run_id"] == "run-1"


@pytest.mark.asyncio()
async def test_count_documents():
    """Test counting documents."""
    repo = PipelineRunRepository()

    # Mock the count_documents method
    repo.collection.count_documents = AsyncMock(return_value=42)

    count = await repo.count({"status": "success"})

    assert count == 42


@pytest.mark.asyncio()
async def test_aggregate_pipeline():
    """Test aggregation pipeline."""
    repo = PipelineRunRepository()

    # Mock the aggregate method
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(
        return_value=[
            {"_id": "success", "count": 30},
            {"_id": "failed", "count": 12},
        ]
    )

    repo.collection.aggregate = MagicMock(return_value=mock_cursor)

    pipeline = [
        {"$match": {"repo_url": "https://github.com/org/repo"}},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]

    results = await repo.aggregate(pipeline)

    assert len(results) == 2
    assert results[0]["count"] == 30


@pytest.mark.asyncio()
async def test_delete_document():
    """Test deleting a document."""
    repo = PipelineRunRepository()

    # Mock the delete_one method
    repo.collection.delete_one = AsyncMock(return_value=MagicMock(deleted_count=1))

    deleted = await repo.delete("some-id")

    assert deleted is True


@pytest.mark.asyncio()
async def test_delete_not_found():
    """Test deleting a non-existent document."""
    repo = PipelineRunRepository()

    # Mock the delete_one method to return 0 deleted
    repo.collection.delete_one = AsyncMock(return_value=MagicMock(deleted_count=0))

    deleted = await repo.delete("non-existent-id")

    assert deleted is False


@pytest.mark.asyncio()
async def test_find_by_date_range():
    """Test finding runs by date range."""
    repo = PipelineRunRepository()

    # Mock the find method - need to properly chain the cursor methods
    async_mock_cursor = AsyncMock()
    async_mock_cursor.sort = MagicMock(return_value=async_mock_cursor)
    async_mock_cursor.limit = MagicMock(return_value=async_mock_cursor)
    async_mock_cursor.to_list = AsyncMock(
        return_value=[
            {"run_id": "run-1", "started_at": datetime.now(UTC)},
        ]
    )

    repo.collection.find = MagicMock(return_value=async_mock_cursor)

    end_date = datetime.now(UTC)
    start_date = end_date - timedelta(days=7)

    results = await repo.find_by_date_range(
        "https://github.com/org/repo",
        start_date,
        end_date,
    )

    assert len(results) == 1


@pytest.mark.asyncio()
async def test_find_by_status():
    """Test finding runs by status."""
    repo = PipelineRunRepository()

    # Mock the find method
    mock_cursor = MagicMock()
    mock_cursor.sort = MagicMock(return_value=mock_cursor)
    mock_cursor.limit = MagicMock(return_value=mock_cursor)
    mock_cursor.to_list = AsyncMock(
        return_value=[
            {"run_id": "run-1", "status": "running"},
        ]
    )

    repo.collection.find = MagicMock(return_value=mock_cursor)

    results = await repo.find_by_status(PipelineStatus.RUNNING, limit=100)

    assert len(results) == 1
    assert results[0]["status"] == "running"


@pytest.mark.asyncio()
async def test_find_recent_by_repo():
    """Test finding recent runs for a repo."""
    repo = PipelineRunRepository()

    # Mock the find method
    mock_cursor = MagicMock()
    mock_cursor.sort = MagicMock(return_value=mock_cursor)
    mock_cursor.limit = MagicMock(return_value=mock_cursor)
    mock_cursor.to_list = AsyncMock(
        return_value=[
            {"run_id": "run-1", "repo_url": "https://github.com/org/repo"},
            {"run_id": "run-2", "repo_url": "https://github.com/org/repo"},
        ]
    )

    repo.collection.find = MagicMock(return_value=mock_cursor)

    results = await repo.find_recent_by_repo("https://github.com/org/repo", limit=10)

    assert len(results) == 2
