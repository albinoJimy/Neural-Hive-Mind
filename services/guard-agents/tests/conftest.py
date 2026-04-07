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


@pytest.fixture
def mock_redis_client():
    """Mock Redis client for testing."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.keys = AsyncMock(return_value=[])
    redis.lrange = AsyncMock(return_value=[])
    redis.lock_component = AsyncMock(return_value=True)
    redis.unlock_component = AsyncMock(return_value=True)
    return redis


@pytest.fixture
def mock_anomaly_detector():
    """Mock anomaly detector for testing."""
    detector = MagicMock()
    detector.model = MagicMock()
    detector.detect_anomaly = AsyncMock(
        return_value={
            "is_anomaly": False,
            "anomaly_score": 0.3,
            "anomaly_type": "none",
            "explanation": "Normal behavior",
            "model_type": "isolation_forest",
        }
    )
    return detector


@pytest.fixture
def sample_auth_event():
    """Sample authentication event for testing."""
    return {
        "event_id": "auth-event-001",
        "type": "authentication",
        "user_id": "user-123",
        "failed_attempts": 3,
        "source_ip": "192.168.1.100",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@pytest.fixture
def sample_failed_auth_event():
    """Sample failed authentication event for testing."""
    return {
        "event_id": "auth-event-002",
        "type": "authentication",
        "user_id": "user-456",
        "failed_attempts": 7,
        "source_ip": "10.0.0.50",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@pytest.fixture
def sample_request_metrics_event():
    """Sample request metrics event for testing."""
    return {
        "event_id": "metrics-event-001",
        "type": "request_metrics",
        "requests_per_minute": 500,
        "source": "api-gateway",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@pytest.fixture
def sample_dos_attack_event():
    """Sample DoS attack event for testing."""
    return {
        "event_id": "dos-event-001",
        "type": "request_metrics",
        "requests_per_minute": 1500,
        "source": "api-gateway",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@pytest.fixture
def sample_payload_event():
    """Sample payload event for testing."""
    return {
        "event_id": "payload-event-001",
        "type": "http_request",
        "payload": "normal request payload",  # Safe payload that doesn't match patterns
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@pytest.fixture
def sample_malicious_payload_event():
    """Sample malicious payload event for testing."""
    return {
        "event_id": "malicious-event-001",
        "type": "http_request",
        "payload": "1' OR '1'='1'; DROP TABLE users--",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@pytest.fixture
def sample_resource_metrics_event():
    """Sample resource metrics event for testing."""
    return {
        "event_id": "resource-event-001",
        "type": "resource_metrics",
        "resource_name": "worker-node-1",
        "metrics": {"cpu_usage": 0.65, "memory_usage": 0.70, "disk_usage": 0.50},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@pytest.fixture
def sample_high_resource_event():
    """Sample high resource usage event for testing."""
    return {
        "event_id": "resource-event-002",
        "type": "resource_metrics",
        "resource_name": "worker-node-2",
        "metrics": {"cpu_usage": 0.90, "memory_usage": 0.95, "disk_usage": 0.80},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@pytest.fixture
def sample_behavioral_event():
    """Sample behavioral event for testing."""
    return {
        "event_id": "behavior-event-001",
        "type": "user_behavior",
        "user_id": "user-789",
        "anomaly_score": 0.4,
        "features": {"login_frequency": 5, "action_diversity": 0.6, "time_pattern": "normal"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@pytest.fixture
def sample_anomalous_behavior_event():
    """Sample anomalous behavior event for testing."""
    return {
        "event_id": "anomaly-event-001",
        "type": "user_behavior",
        "user_id": "user-999",
        "anomaly_score": 0.85,
        "features": {"login_frequency": 50, "action_diversity": 0.1, "time_pattern": "unusual"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
