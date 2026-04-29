"""Test configuration and fixtures."""

import asyncio
from collections.abc import AsyncGenerator, Generator
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from src.clients.mongodb_client import MongoDBClient
from src.config.settings import Settings
from src.services.impact_analyzer import ImpactAnalyzer

UTC = timezone.utc


@pytest.fixture()
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture()
def settings() -> Settings:
    """Get test settings."""
    return Settings(
        environment="test",
        debug=True,
        log_level="DEBUG",
        service_name="experiment-impact-analyzer-test",
        service_version="1.0.0-test",
        mongodb_uri="mongodb://localhost:27017",
        mongodb_database="neural_hive_test",
        mongodb_impacts_collection="test_impacts",
        mongodb_experiments_collection="test_experiments",
        mongodb_hypotheses_collection="test_hypotheses",
        api_port=8013,
        prometheus_port=9093,
    )


@pytest.fixture()
async def mock_mongodb_client() -> AsyncGenerator[MongoDBClient, None]:
    """Create mock MongoDB client."""
    client = MongoDBClient(
        Settings(
            mongodb_uri="mongodb://localhost:27017",
            mongodb_database="test_db",
        )
    )

    # Mock the connection
    client._client = MagicMock(spec=AsyncIOMotorClient)
    client._database = MagicMock()
    client._connected = True

    yield client

    client._connected = False


@pytest.fixture()
def sample_experiment() -> dict:
    """Sample experiment data."""
    return {
        "experiment_id": "test-exp-001",
        "hypothesis_id": "test-hyp-001",
        "experiment_type": "A_B_TEST",
        "target_component": "consensus-engine",
        "baseline_configuration": {
            "error_rate": 0.05,
            "latency_p95": 100.0,
            "throughput": 1000.0,
        },
        "experimental_configuration": {
            "weight_adjustment": 0.1,
        },
        "control_metrics": {
            "error_rate": [0.048, 0.052, 0.049, 0.051, 0.050],
            "latency_p95": [95.0, 105.0, 98.0, 102.0, 100.0],
            "throughput": [1020.0, 980.0, 1010.0, 990.0, 1000.0],
        },
        "treatment_metrics": {
            "error_rate": [0.045, 0.048, 0.046, 0.047, 0.046],
            "latency_p95": [92.0, 98.0, 95.0, 97.0, 94.0],
            "throughput": [1050.0, 1020.0, 1040.0, 1030.0, 1045.0],
        },
        "sample_size": 1000,
        "created_at": int(datetime.now(timezone.utc).timestamp() * 1000),
        "status": "COMPLETED",
    }


@pytest.fixture()
def sample_hypothesis() -> dict:
    """Sample hypothesis data."""
    return {
        "hypothesis_id": "test-hyp-001",
        "title": "Test hypothesis",
        "description": "A test hypothesis for impact analysis",
        "expected_outcome": "Improved performance",
        "baseline_metrics": {
            "error_rate": 0.05,
            "latency_p95": 100.0,
        },
        "target_metrics": {
            "error_rate": 0.045,
            "latency_p95": 95.0,
        },
        "status": "COMPLETED",
    }


@pytest.fixture()
def sample_impact() -> dict:
    """Sample impact analysis data."""
    return {
        "impact_id": "test-impact-001",
        "experiment_id": "test-exp-001",
        "hypothesis_id": "test-hyp-001",
        "overall_direction": "positive",
        "overall_magnitude": "medium",
        "categories": ["performance", "reliability"],
        "recommendation": "ACCEPT: Positive impact observed.",
        "confidence_level": 0.85,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "analysis_version": 1,
    }


@pytest.fixture()
def impact_analyzer(settings: Settings, mock_mongodb_client: MongoDBClient) -> ImpactAnalyzer:
    """Create impact analyzer with mocked dependencies."""
    return ImpactAnalyzer(
        settings=settings,
        mongodb_client=mock_mongodb_client,
    )


@pytest.fixture()
def mock_experiment_data(sample_experiment: dict) -> MagicMock:
    """Create mock experiment data accessor."""
    mock = MagicMock()
    mock.get_experiment = AsyncMock(return_value=sample_experiment)
    mock.get_hypothesis = AsyncMock(return_value=None)
    mock.get_impact_by_experiment = AsyncMock(return_value=None)
    mock.save_impact = AsyncMock(return_value="mock-id")
    mock.get_metrics_history = AsyncMock(return_value=[])
    mock.find_correlated_experiments = AsyncMock(return_value=[])
    return mock
