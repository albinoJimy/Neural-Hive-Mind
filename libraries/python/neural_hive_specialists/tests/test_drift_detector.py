import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from neural_hive_specialists.drift_monitoring.drift_detector import DriftDetector


@pytest.fixture
def drift_detector():
    evidently_monitor = MagicMock()
    evidently_monitor.detect_drift.return_value = {
        "drift_detected": True,
        "drift_score": 0.4,
        "drifted_features": ["f1", "f2"],
        "report": {"summary": "ok"},
    }
    evidently_monitor.clear_current_data = MagicMock()

    alerter = AsyncMock()
    alerter.send_alert = AsyncMock()

    collection = MagicMock()
    collection.insert_one = AsyncMock()
    ledger_client = SimpleNamespace(db={"drift_monitoring": collection})

    detector = DriftDetector(
        {"drift_threshold_psi": 0.2, "drift_detection_window_hours": 12},
        evidently_monitor,
        alerter,
        ledger_client,
    )
    return detector


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_drift_triggers_alert_and_persist(drift_detector):
    result = await drift_detector.check_drift()

    assert result["drift_detected"] is True
    assert result["drift_score"] == 0.4
    drift_detector.drift_alerter.send_alert.assert_awaited_once()
    collection = drift_detector.ledger_client.db["drift_monitoring"]
    collection.insert_one.assert_awaited_once()
    drift_detector.evidently_monitor.clear_current_data.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_drift_respects_threshold(monkeypatch, drift_detector):
    drift_detector.evidently_monitor.detect_drift.return_value = {
        "drift_detected": True,
        "drift_score": 0.1,
        "drifted_features": ["f1"],
        "report": {"summary": "low"},
    }

    await drift_detector.check_drift()

    drift_detector.drift_alerter.send_alert.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_drift_handles_exception(drift_detector):
    drift_detector.evidently_monitor.detect_drift.side_effect = RuntimeError("boom")

    result = await drift_detector.check_drift()

    assert result["drift_detected"] is False
    assert result["drift_score"] == 0.0
    assert "error" in result
    drift_detector.drift_alerter.send_alert.assert_not_awaited()
