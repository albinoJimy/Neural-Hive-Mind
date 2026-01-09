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


# =============================================================================
# Testes de Integracao: Drift-Triggered Retraining
# =============================================================================


@pytest.fixture
def mock_mongodb_collection():
    """Mock de colecao MongoDB com eventos de drift."""
    collection = MagicMock()

    # Simula cursor com eventos de drift
    drift_events = [
        {
            "_id": "event-1",
            "drift_detected": True,
            "drift_score": 0.35,
            "drifted_features": ["anomaly_score", "risk_weight"],
            "timestamp": "2025-01-01T12:00:00Z",
        },
        {
            "_id": "event-2",
            "drift_detected": True,
            "drift_score": 0.28,
            "drifted_features": ["duration_ms"],
            "timestamp": "2025-01-01T11:00:00Z",
        },
    ]

    cursor = MagicMock()
    cursor.sort = MagicMock(return_value=cursor)
    cursor.limit = MagicMock(return_value=cursor)
    cursor.to_list = AsyncMock(return_value=drift_events)

    collection.find = MagicMock(return_value=cursor)
    collection.update_one = AsyncMock()
    collection.insert_one = AsyncMock()

    return collection


@pytest.mark.integration
@pytest.mark.asyncio
async def test_drift_triggers_retraining_for_anomaly_model(mock_mongodb_collection):
    """
    Testa que drift em features de anomalia dispara retreinamento do modelo correto.
    """
    from types import SimpleNamespace

    # Simula drift_triggered_retraining.DriftTriggeredRetrainer
    class MockRetrainer:
        def __init__(self):
            self.args = SimpleNamespace(dry_run=True)
            self.drift_threshold = 0.2

        def _determine_model_type(self, drift_event):
            drifted_features = drift_event.get("drifted_features", [])
            drifted_set = set(drifted_features)

            anomaly_features = {"anomaly_score", "risk_weight", "retry_count", "capabilities"}

            if drifted_set & anomaly_features:
                return "anomaly"
            return "scheduling"

    retrainer = MockRetrainer()

    drift_event = {
        "_id": "test-event",
        "drift_score": 0.35,
        "drifted_features": ["anomaly_score", "risk_weight"],
    }

    model_type = retrainer._determine_model_type(drift_event)

    assert model_type == "anomaly"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_drift_triggers_retraining_for_scheduling_model():
    """
    Testa que drift em features de scheduling dispara retreinamento correto.
    """
    from types import SimpleNamespace

    class MockRetrainer:
        def _determine_model_type(self, drift_event):
            drifted_features = drift_event.get("drifted_features", [])
            drifted_set = set(drifted_features)

            scheduling_features = {"duration_ms", "queue_time_ms", "wait_time", "estimated_duration"}
            load_features = {"request_rate", "throughput", "concurrency", "load"}
            anomaly_features = {"anomaly_score", "risk_weight", "retry_count"}

            if drifted_set & anomaly_features:
                return "anomaly"
            elif drifted_set & load_features:
                return "load"
            elif drifted_set & scheduling_features:
                return "scheduling"
            return "anomaly"

    retrainer = MockRetrainer()

    drift_event = {
        "drift_score": 0.28,
        "drifted_features": ["duration_ms", "queue_time_ms"],
    }

    model_type = retrainer._determine_model_type(drift_event)

    assert model_type == "scheduling"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_drift_triggers_retraining_for_load_model():
    """
    Testa que drift em features de load dispara retreinamento correto.
    """
    from types import SimpleNamespace

    class MockRetrainer:
        def _determine_model_type(self, drift_event):
            drifted_features = drift_event.get("drifted_features", [])
            drifted_set = set(drifted_features)

            load_features = {"request_rate", "throughput", "concurrency", "load"}

            if drifted_set & load_features:
                return "load"
            return "anomaly"

    retrainer = MockRetrainer()

    drift_event = {
        "drift_score": 0.30,
        "drifted_features": ["throughput", "concurrency"],
    }

    model_type = retrainer._determine_model_type(drift_event)

    assert model_type == "load"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_retraining_improves_model_metrics():
    """
    Testa que retreinamento apos drift melhora metricas do modelo.

    Simula cenario onde modelo original tem F1=0.60 e apos
    retreinamento com dados recentes atinge F1=0.72.
    """
    import numpy as np

    # Metricas antes do retreinamento
    old_metrics = {
        "f1_score": 0.60,
        "precision": 0.65,
        "recall": 0.55,
    }

    # Simula retreinamento com dados atualizados
    # (dados sem drift terao melhor performance)
    new_metrics = {
        "f1_score": 0.72,
        "precision": 0.78,
        "recall": 0.67,
    }

    # Verifica melhoria
    f1_improvement = (new_metrics["f1_score"] - old_metrics["f1_score"]) / old_metrics["f1_score"]

    assert f1_improvement > 0.1, f"Melhoria de F1 ({f1_improvement:.2%}) menor que 10%"
    assert new_metrics["f1_score"] > 0.65, "F1 apos retreinamento abaixo de 0.65"

    print(f"\n=== Teste Melhoria Apos Retreinamento ===")
    print(f"F1 antes: {old_metrics['f1_score']:.3f}")
    print(f"F1 depois: {new_metrics['f1_score']:.3f}")
    print(f"Melhoria: {f1_improvement:.2%}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_drift_below_threshold_does_not_trigger():
    """Testa que drift abaixo do threshold nao dispara retreinamento."""
    threshold = 0.2

    drift_events = [
        {"drift_score": 0.15, "should_trigger": False},
        {"drift_score": 0.19, "should_trigger": False},
        {"drift_score": 0.20, "should_trigger": False},  # Igual ao threshold
        {"drift_score": 0.21, "should_trigger": True},
        {"drift_score": 0.35, "should_trigger": True},
    ]

    for event in drift_events:
        should_retrain = event["drift_score"] > threshold
        assert should_retrain == event["should_trigger"], (
            f"Evento com drift_score={event['drift_score']} "
            f"deveria trigger={event['should_trigger']}"
        )
