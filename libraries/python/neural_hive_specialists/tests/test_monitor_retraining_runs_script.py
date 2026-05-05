"""Testes simplificados para o script monitor_retraining_runs.py."""

import os
import sys
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch

import pytest

# Adicionar diretório de scripts ao path
sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "scripts"),
)

try:
    import monitor_retraining_runs

    SCRIPT_AVAILABLE = True
except ImportError:
    SCRIPT_AVAILABLE = False


@pytest.mark.skipif(not SCRIPT_AVAILABLE, reason="Script não disponível")
class TestMonitorRunningTriggers:
    """Testes para monitor_running_triggers()."""

    @patch("monitor_retraining_runs.MongoClient")
    @patch("monitor_retraining_runs.MlflowClient")
    def test_monitor_no_running_triggers(self, mock_mlflow_class, mock_mongo_class):
        """Testa monitoramento quando não há triggers em execução."""
        mock_mongo = Mock()
        mock_db = Mock()
        mock_collection = Mock()
        mock_mongo_class.return_value = mock_mongo
        mock_mongo.__getitem__ = Mock(return_value=mock_db)
        mock_db.__getitem__ = Mock(return_value=mock_collection)
        mock_collection.find.return_value = []

        stats = monitor_retraining_runs.monitor_running_triggers(
            mongodb_uri="mongodb://localhost:27017",
            mongodb_database="neural_hive",
            mlflow_tracking_uri="http://localhost:5000",
        )

        assert stats["checked"] == 0
        assert stats["completed"] == 0
        assert stats["errors"] == 0

    @patch("monitor_retraining_runs.MongoClient")
    @patch("monitor_retraining_runs.MlflowClient")
    def test_monitor_run_finished(self, mock_mlflow_class, mock_mongo_class):
        """Testa monitoramento de run que terminou com sucesso."""
        mock_mongo = Mock()
        mock_db = Mock()
        mock_collection = Mock()
        mock_mongo_class.return_value = mock_mongo
        mock_mongo.__getitem__ = Mock(return_value=mock_db)
        mock_db.__getitem__ = Mock(return_value=mock_collection)

        trigger_doc = {
            "trigger_id": "trigger-123",
            "metadata": {"mlflow_run_id": "run-456"},
            "triggered_at": datetime.now(timezone.utc) - timedelta(minutes=30),
            "specialist_type": "technical",
        }
        mock_collection.find.return_value = [trigger_doc]

        mock_mlflow = Mock()
        mock_mlflow_class.return_value = mock_mlflow

        mock_run = Mock()
        mock_run.info.status = "FINISHED"
        mock_run.info.end_time = int((datetime.now(timezone.utc).timestamp() + 3600) * 1000)
        mock_run.info.start_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        mock_run.data.metrics = {"precision": 0.85}
        mock_mlflow.get_run.return_value = mock_run

        stats = monitor_retraining_runs.monitor_running_triggers(
            mongodb_uri="mongodb://localhost:27017",
            mongodb_database="neural_hive",
            mlflow_tracking_uri="http://localhost:5000",
        )

        assert stats["checked"] == 1
        assert stats["completed"] == 1
        assert stats["failed"] == 0

    @patch("monitor_retraining_runs.MongoClient")
    @patch("monitor_retraining_runs.MlflowClient")
    def test_monitor_run_failed(self, mock_mlflow_class, mock_mongo_class):
        """Testa monitoramento de run que falhou."""
        mock_mongo = Mock()
        mock_db = Mock()
        mock_collection = Mock()
        mock_mongo_class.return_value = mock_mongo
        mock_mongo.__getitem__ = Mock(return_value=mock_db)
        mock_db.__getitem__ = Mock(return_value=mock_collection)

        trigger_doc = {
            "trigger_id": "trigger-789",
            "metadata": {"mlflow_run_id": "run-failed"},
            "triggered_at": datetime.now(timezone.utc) - timedelta(minutes=30),
            "specialist_type": "business",
        }
        mock_collection.find.return_value = [trigger_doc]

        mock_mlflow = Mock()
        mock_mlflow_class.return_value = mock_mlflow

        mock_run = Mock()
        mock_run.info.status = "FAILED"
        mock_mlflow.get_run.return_value = mock_run

        stats = monitor_retraining_runs.monitor_running_triggers(
            mongodb_uri="mongodb://localhost:27017",
            mongodb_database="neural_hive",
            mlflow_tracking_uri="http://localhost:5000",
        )

        assert stats["checked"] == 1
        assert stats["failed"] == 1

    @patch("monitor_retraining_runs.MongoClient")
    @patch("monitor_retraining_runs.MlflowClient")
    def test_monitor_run_still_running(self, mock_mlflow_class, mock_mongo_class):
        """Testa monitoramento de run ainda em execução."""
        mock_mongo = Mock()
        mock_db = Mock()
        mock_collection = Mock()
        mock_mongo_class.return_value = mock_mongo
        mock_mongo.__getitem__ = Mock(return_value=mock_db)
        mock_db.__getitem__ = Mock(return_value=mock_collection)

        trigger_doc = {
            "trigger_id": "trigger-running",
            "metadata": {"mlflow_run_id": "run-running"},
            "triggered_at": datetime.now(timezone.utc) - timedelta(minutes=10),
            "specialist_type": "behavior",
        }
        mock_collection.find.return_value = [trigger_doc]

        mock_mlflow = Mock()
        mock_mlflow_class.return_value = mock_mlflow

        mock_run = Mock()
        mock_run.info.status = "RUNNING"
        mock_mlflow.get_run.return_value = mock_run

        stats = monitor_retraining_runs.monitor_running_triggers(
            mongodb_uri="mongodb://localhost:27017",
            mongodb_database="neural_hive",
            mlflow_tracking_uri="http://localhost:5000",
        )

        assert stats["checked"] == 1
        assert stats["still_running"] == 1

    @patch("monitor_retraining_runs.MongoClient")
    @patch("monitor_retraining_runs.MlflowClient")
    def test_monitor_run_timeout(self, mock_mlflow_class, mock_mongo_class):
        """Testa monitoramento de run que excedeu timeout."""
        mock_mongo = Mock()
        mock_db = Mock()
        mock_collection = Mock()
        mock_mongo_class.return_value = mock_mongo
        mock_mongo.__getitem__ = Mock(return_value=mock_db)
        mock_db.__getitem__ = Mock(return_value=mock_collection)

        trigger_doc = {
            "trigger_id": "trigger-timeout",
            "metadata": {"mlflow_run_id": "run-timeout"},
            "triggered_at": datetime.now(timezone.utc) - timedelta(hours=25),
            "specialist_type": "evolution",
        }
        mock_collection.find.return_value = [trigger_doc]

        mock_mlflow = Mock()
        mock_mlflow_class.return_value = mock_mlflow

        stats = monitor_retraining_runs.monitor_running_triggers(
            mongodb_uri="mongodb://localhost:27017",
            mongodb_database="neural_hive",
            mlflow_tracking_uri="http://localhost:5000",
            max_run_age_hours=24,
        )

        assert stats["checked"] == 1
        assert stats["timed_out"] == 1


@pytest.mark.skipif(not SCRIPT_AVAILABLE, reason="Script não disponível")
class TestMainFunction:
    """Testes para main()."""

    @patch("monitor_retraining_runs.monitor_running_triggers")
    @patch("sys.argv", ["monitor_retraining_runs.py"])
    def test_main_default_params(self, mock_monitor):
        """Testa main com parâmetros padrão."""
        mock_monitor.return_value = {
            "checked": 5,
            "completed": 3,
            "failed": 1,
            "timed_out": 0,
            "still_running": 1,
            "errors": 0,
        }

        with pytest.raises(SystemExit) as exc_info:
            monitor_retraining_runs.main()

        assert exc_info.value.code == 0

    @patch("monitor_retraining_runs.monitor_running_triggers")
    @patch("sys.argv", ["monitor_retraining_runs.py"])
    def test_main_with_errors(self, mock_monitor):
        """Testa main quando há erros no monitoramento."""
        mock_monitor.return_value = {
            "checked": 5,
            "completed": 0,
            "failed": 0,
            "timed_out": 0,
            "still_running": 0,
            "errors": 2,
        }

        with pytest.raises(SystemExit) as exc_info:
            monitor_retraining_runs.main()

        assert exc_info.value.code == 1
