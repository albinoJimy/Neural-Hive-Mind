import time
from unittest.mock import MagicMock

import pytest

from neural_hive_specialists.observability.business_metrics_collector import (
    BusinessMetricsCollector,
)


def _base_config():
    return {
        "mongodb_uri": "mongodb://localhost:27017",
        "mongodb_database": "neural_hive_test",
        "mongodb_opinions_collection": "opinions_test",
        "consensus_mongodb_uri": "mongodb://localhost:27017",
        "consensus_mongodb_database": "neural_hive_test",
        "consensus_collection_name": "consensus_test",
        "consensus_timestamp_field": "timestamp",
    }


@pytest.mark.unit
def test_collect_business_metrics_disabled():
    config = {**_base_config(), "enable_business_metrics": False}
    collector = BusinessMetricsCollector(config, metrics_registry={})

    result = collector.collect_business_metrics()

    assert result["status"] == "disabled"


@pytest.mark.unit
def test_collect_business_metrics_uses_cache(monkeypatch):
    config = _base_config()
    collector = BusinessMetricsCollector(config, metrics_registry={})
    collector._cache = {"status": "cached", "metrics": 1}
    collector._cache_timestamp = time.time()

    fetch_opinions = MagicMock()
    fetch_decisions = MagicMock()
    monkeypatch.setattr(collector, "_fetch_opinions", fetch_opinions)
    monkeypatch.setattr(collector, "_fetch_consensus_decisions", fetch_decisions)

    result = collector.collect_business_metrics()

    assert result["status"] == "cached"
    fetch_opinions.assert_not_called()
    fetch_decisions.assert_not_called()
