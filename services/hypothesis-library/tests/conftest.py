"""Configuration file for pytest."""

import sys
from pathlib import Path

# Add parent directory to sys.path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from src.models.hypothesis import (
    Hypothesis,
    HypothesisCreate,
    HypothesisPriority,
    HypothesisStatus,
)


@pytest.fixture()
def mock_settings():
    """Mock settings for testing."""
    settings = Mock()
    settings.environment = "test"
    settings.debug = True
    settings.log_level = "DEBUG"
    settings.service_name = "hypothesis-library-test"
    settings.service_version = "1.0.0-test"

    settings.api_host = "127.0.0.1"
    settings.api_port = 8010
    settings.api_prefix = "/api/v1"
    settings.cors_origins = ["*"]

    settings.mongodb_uri = "mongodb://localhost:27017"
    settings.mongodb_database = "test_neural_hive"
    settings.mongodb_hypotheses_collection = "test_hypotheses"
    settings.mongodb_versions_collection = "test_hypothesis_versions"
    settings.mongodb_max_pool_size = 10
    settings.mongodb_min_pool_size = 1

    settings.max_versions_per_hypothesis = 50
    settings.auto_archive_days = 180
    settings.require_approval_for_testing = True
    settings.enable_versioning = True

    return settings


@pytest.fixture()
def mock_mongodb_client():
    """Mock MongoDB client for testing."""
    client = AsyncMock()
    return client


@pytest.fixture()
def sample_hypothesis_create():
    """Sample hypothesis creation data."""
    return HypothesisCreate(
        title="Reduce latency via weight recalibration",
        description="Adjust consensus weights to reduce P95 latency",
        background="Current latency is above SLO target",
        expected_outcome="P95 latency reduced from 200ms to 150ms",
        metrics=["latency_p95", "throughput", "error_rate"],
        baseline_metrics={"latency_p95": 200.0, "throughput": 1000.0},
        target_metrics={"latency_p95": 150.0},
        priority=HypothesisPriority.HIGH,
        author="test-user",
        tags=["performance", "latency", "consensus"],
    )


@pytest.fixture()
def sample_hypothesis(sample_hypothesis_create):
    """Sample hypothesis for testing."""
    return Hypothesis(
        **sample_hypothesis_create.model_dump(),
        hypothesis_id=str(uuid4()),
        status=HypothesisStatus.DRAFT,
    )


@pytest.fixture()
def sample_hypothesis_proposed(sample_hypothesis_create):
    """Sample hypothesis in PROPOSED status."""
    return Hypothesis(
        **sample_hypothesis_create.model_dump(),
        hypothesis_id=str(uuid4()),
        status=HypothesisStatus.PROPOSED,
        proposed_at=Mock(),
    )


@pytest.fixture()
def sample_hypothesis_approved(sample_hypothesis_create):
    """Sample hypothesis in APPROVED status."""
    return Hypothesis(
        **sample_hypothesis_create.model_dump(),
        hypothesis_id=str(uuid4()),
        status=HypothesisStatus.APPROVED,
        proposed_at=Mock(),
        approved_at=Mock(),
        approved_by="reviewer-1",
    )
