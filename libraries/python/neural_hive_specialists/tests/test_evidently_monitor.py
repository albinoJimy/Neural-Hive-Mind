import sys
from pathlib import Path

import pandas as pd
import pytest

from neural_hive_specialists.drift_monitoring.evidently_monitor import EvidentlyMonitor


def _mock_evidently(monkeypatch, drift_result=True, drift_share=0.35):
    class FakeReport:
        def __init__(self, metrics):
            self.metrics = metrics
            self.ran = False

        def run(self, reference_data, current_data, column_mapping=None):
            self.ran = True

        def as_dict(self):
            return {
                "metrics": [
                    {
                        "metric": "DatasetDriftMetric",
                        "result": {
                            "dataset_drift": drift_result,
                            "drift_share": drift_share,
                            "drift_by_columns": {"feature_a": {"drift_detected": drift_result}},
                        },
                    }
                ]
            }

        def save_html(self, path):
            Path(path).write_text("<html>report</html>")

    class FakeReportModule:
        Report = FakeReport

    class FakePresetModule:
        @staticmethod
        def DataDriftPreset():
            return "drift"

        @staticmethod
        def DataQualityPreset():
            return "quality"

    monkeypatch.setitem(sys.modules, "evidently.report", FakeReportModule())
    monkeypatch.setitem(sys.modules, "evidently.metric_preset", FakePresetModule())


@pytest.mark.unit
def test_detect_drift_with_mocked_evidently(monkeypatch):
    _mock_evidently(monkeypatch)
    monitor = EvidentlyMonitor({"drift_reference_dataset_path": None})
    monitor.reference_data = pd.DataFrame({"feature_a": [1, 2, 3], "timestamp": [1, 2, 3]})
    monitor.log_features({"feature_a": 10})

    result = monitor.detect_drift()

    assert result["drift_detected"] is True
    assert result["drift_score"] == 0.35
    assert "feature_a" in result["drifted_features"]


@pytest.mark.unit
def test_generate_html_report(monkeypatch, tmp_path):
    _mock_evidently(monkeypatch)
    monitor = EvidentlyMonitor({"drift_reference_dataset_path": None})
    monitor.reference_data = pd.DataFrame({"feature_a": [1, 2, 3], "timestamp": [1, 2, 3]})
    monitor.log_features({"feature_a": 5})

    output_path = tmp_path / "report.html"
    monitor.generate_html_report(str(output_path))

    assert output_path.exists()
    assert output_path.read_text() != ""


@pytest.mark.unit
def test_detect_drift_without_reference_data(monkeypatch):
    monitor = EvidentlyMonitor({"drift_reference_dataset_path": None})
    monitor.current_data = [{"feature_a": 1}]

    result = monitor.detect_drift()

    assert result["drift_detected"] is False
    assert result["drift_score"] == 0.0
