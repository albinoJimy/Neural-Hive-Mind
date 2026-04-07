"""
Configuration file for pytest.

Fixes import path for the src module.
"""

import sys
from pathlib import Path

# Add the parent directory to sys.path so we can import src
# This allows tests to run with 'from src.xxx import yyy'
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone
from neural_hive_domain import UnifiedDomain


@pytest.fixture
def mock_memory_client():
    """Mock Memory Layer client for testing."""
    client = AsyncMock()
    client.start = AsyncMock(return_value=None)
    client.stop = AsyncMock(return_value=None)
    client.store_signal_redis = AsyncMock(return_value=True)
    client.get_signal_redis = AsyncMock(return_value=None)
    return client


@pytest.fixture
def mock_pheromone_client():
    """Mock Pheromone client for testing."""
    client = AsyncMock()
    client.start = AsyncMock(return_value=None)
    client.stop = AsyncMock(return_value=None)
    client.publish_pheromone = AsyncMock(return_value=True)
    return client


@pytest.fixture
def mock_kafka_producer():
    """Mock Kafka producer for testing."""
    producer = AsyncMock()
    producer.start = AsyncMock(return_value=None)
    producer.stop = AsyncMock(return_value=None)
    producer.publish_signal = AsyncMock(return_value=True)
    return producer


@pytest.fixture
def sample_raw_event():
    """Sample raw event for testing."""
    from src.models.raw_event import RawEvent

    return RawEvent(
        event_id="raw-event-001",
        source="test-source",
        event_type="user_action",
        timestamp=datetime.now(timezone.utc),
        payload={"action": "click", "element": "button", "page": "/home"},
        metadata={"trace_id": "trace-123", "span_id": "span-456", "device_id": "device-789"},
    )


@pytest.fixture
def sample_metric_raw_event():
    """Sample metric raw event for testing."""
    from src.models.raw_event import RawEvent

    return RawEvent(
        event_id="metric-event-001",
        source="prometheus",
        event_type="metric",
        timestamp=datetime.now(timezone.utc),
        payload={"cpu_usage": 0.75, "memory_usage": 0.60, "request_count": 1000},
        metadata={"trace_id": "trace-metric-123"},
    )


@pytest.fixture
def sample_anomalous_raw_event():
    """Sample anomalous raw event for testing."""
    from src.models.raw_event import RawEvent

    return RawEvent(
        event_id="anomaly-event-001",
        source="api-gateway",
        event_type="error_spike",
        timestamp=datetime.now(timezone.utc),
        payload={"error_count": 500, "error_rate": 0.45, "affected_services": ["auth", "payment"]},
        metadata={"trace_id": "trace-anomaly-123", "severity": "high"},
    )


@pytest.fixture
def sample_geolocation_metadata():
    """Sample metadata with geolocation for testing."""
    return {
        "trace_id": "trace-geo-123",
        "span_id": "span-geo-456",
        "geolocation": {"latitude": 37.7749, "longitude": -122.4194},
    }


@pytest.fixture
def sample_raw_event_with_geo():
    """Sample raw event with geolocation for testing."""
    from src.models.raw_event import RawEvent

    return RawEvent(
        event_id="geo-event-001",
        source="mobile-app",
        event_type="location_update",
        timestamp=datetime.now(timezone.utc),
        payload={"latitude": 40.7128, "longitude": -74.0060, "accuracy": 10.5},
        metadata={"trace_id": "trace-geo-789", "device_id": "mobile-device-123"},
    )


@pytest.fixture
def sample_trending_raw_event():
    """Sample trending raw event for testing."""
    from src.models.raw_event import RawEvent
    import random

    # Create a trending pattern
    values = [50 + i * 10 + random.random() * 5 for i in range(15)]

    return RawEvent(
        event_id="trend-event-001",
        source="analytics",
        event_type="usage_metric",
        timestamp=datetime.now(timezone.utc),
        payload={"daily_active_users": values[-1], "trend_values": values},
        metadata={"trace_id": "trace-trend-123"},
    )


@pytest.fixture
def sample_emerging_pattern_event():
    """Sample event with emerging pattern for testing."""
    from src.models.raw_event import RawEvent

    return RawEvent(
        event_id="pattern-event-001",
        source="behavioral_tracker",
        event_type="user_journey",
        timestamp=datetime.now(timezone.utc),
        payload={
            "steps": ["login", "dashboard", "settings", "logout"],
            "duration_ms": 5000,
            "new_feature_interaction": True,
        },
        metadata={"trace_id": "trace-pattern-123", "user_id": "user-pattern-456"},
    )


@pytest.fixture
def business_domain():
    """Business domain fixture."""
    return UnifiedDomain.BUSINESS


@pytest.fixture
def security_domain():
    """Security domain fixture."""
    return UnifiedDomain.SECURITY


@pytest.fixture
def technical_domain():
    """Technical domain fixture."""
    return UnifiedDomain.TECHNICAL


@pytest.fixture
def infrastructure_domain():
    """Infrastructure domain fixture."""
    return UnifiedDomain.INFRASTRUCTURE


@pytest.fixture
def behavior_domain():
    """Behavior domain fixture."""
    return UnifiedDomain.BEHAVIOR
