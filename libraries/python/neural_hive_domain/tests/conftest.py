"""Shared test fixtures for neural_hive_domain tests."""

from unittest.mock import MagicMock

import pytest
import structlog


@pytest.fixture(autouse=True)
def mock_structlog(monkeypatch):
    """Mock structlog to capture log calls without side effects."""
    mock_logger = MagicMock()
    monkeypatch.setattr(structlog, 'get_logger', lambda *args, **kwargs: mock_logger)
    return mock_logger


@pytest.fixture
def all_domains():
    """Return all valid UnifiedDomain values."""
    from neural_hive_domain import UnifiedDomain

    return list(UnifiedDomain)


@pytest.fixture
def valid_sources():
    """Return all valid source values for normalization."""
    return ['intent_envelope', 'scout_signal', 'risk_scoring', 'ontology']


@pytest.fixture
def valid_layers():
    """Return all valid pheromone layers."""
    return ['strategic', 'exploration', 'consensus', 'specialist']


@pytest.fixture
def valid_pheromone_types():
    """Return all valid pheromone types."""
    return [
        'SUCCESS',
        'FAILURE',
        'WARNING',
        'ANOMALY_POSITIVE',
        'ANOMALY_NEGATIVE',
        'CONFIDENCE',
        'RISK',
    ]
