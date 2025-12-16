import numpy as np
import pytest

from neural_hive_specialists.observability.anomaly_detector import AnomalyDetector


def _base_config(tmp_path):
    return {
        "enable_anomaly_detection": True,
        "anomaly_contamination": 0.1,
        "anomaly_n_estimators": 10,
        "anomaly_model_path": str(tmp_path / "anomaly_{specialist_type}.pkl"),
        "anomaly_alert_threshold": -0.3,
    }


@pytest.mark.unit
def test_detect_anomalies_disabled(tmp_path):
    detector = AnomalyDetector({**_base_config(tmp_path), "enable_anomaly_detection": False})

    result = detector.detect_anomalies({"consensus_agreement_rate": 0.9})

    assert result["is_anomaly"] is False
    assert result["severity"] == "info"


@pytest.mark.unit
def test_detect_anomalies_untrained_model(tmp_path):
    detector = AnomalyDetector(_base_config(tmp_path))

    result = detector.detect_anomalies({"consensus_agreement_rate": 0.9})

    assert result["is_anomaly"] is False
    assert result.get("error") == "model_not_trained"
