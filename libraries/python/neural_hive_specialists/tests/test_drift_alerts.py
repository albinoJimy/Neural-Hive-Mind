from unittest.mock import AsyncMock

import pytest

from neural_hive_specialists.drift_monitoring.drift_alerts import DriftAlerter


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_alert_dispatches_channels(monkeypatch):
    alerter = DriftAlerter(
        {
            "alertmanager_url": "http://alertmanager:9093",
            "slack_webhook_url": "http://slack.example.com/webhook",
        }
    )
    alertmanager_mock = AsyncMock()
    slack_mock = AsyncMock()
    monkeypatch.setattr(alerter, "_send_to_alertmanager", alertmanager_mock)
    monkeypatch.setattr(alerter, "_send_to_slack", slack_mock)

    await alerter.send_alert(0.6, ["feature_a", "feature_b"], {"dummy": True})

    alertmanager_mock.assert_awaited_once()
    slack_mock.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_alert_disabled(monkeypatch):
    alerter = DriftAlerter(
        {
            "enable_drift_alerts": False,
            "alertmanager_url": "http://alertmanager:9093",
            "slack_webhook_url": "http://slack.example.com/webhook",
        }
    )
    alertmanager_mock = AsyncMock()
    monkeypatch.setattr(alerter, "_send_to_alertmanager", alertmanager_mock)

    await alerter.send_alert(0.9, ["f1"], {"report": True})

    alertmanager_mock.assert_not_awaited()


@pytest.mark.unit
def test_calculate_severity_levels():
    alerter = DriftAlerter({})

    assert alerter._calculate_severity(0.1) == "info"
    assert alerter._calculate_severity(0.31) == "warning"
    assert alerter._calculate_severity(0.7) == "critical"
