"""
Testes adicionais para RetrainingTrigger.

Cobertura extra para feedback/retraining_trigger.py
"""

import pytest
from unittest.mock import Mock, MagicMock, AsyncMock, patch
from typing import Dict, Any
from datetime import datetime, timedelta


class TestRetrainingTriggerRecord:
    """Testes para RetrainingTriggerRecord."""

    def test_init_with_defaults(self):
        """Testa inicialização com valores padrão."""
        from neural_hive_specialists.feedback.retraining_trigger import RetrainingTriggerRecord

        record = RetrainingTriggerRecord(
            specialist_type="technical",
            feedback_count=100,
            feedback_window_days=7,
        )

        assert record.specialist_type == "technical"
        assert record.feedback_count == 100
        assert record.feedback_window_days == 7
        assert record.status == "pending"
        assert record.mlflow_run_id is None
        assert record.trigger_id.startswith("trigger-")
        assert isinstance(record.triggered_at, datetime)

    def test_init_with_all_fields(self):
        """Testa inicialização com todos os campos."""
        from neural_hive_specialists.feedback.retraining_trigger import RetrainingTriggerRecord

        now = datetime.utcnow()
        record = RetrainingTriggerRecord(
            specialist_type="business",
            feedback_count=50,
            feedback_window_days=14,
            mlflow_run_id="run-123",
            mlflow_experiment_id="exp-456",
            status="completed",
            error_message=None,
            completed_at=now,
            metadata={"model_version": "1.0"},
        )

        assert record.specialist_type == "business"
        assert record.mlflow_run_id == "run-123"
        assert record.completed_at == now
        assert record.metadata["model_version"] == "1.0"

    def test_model_config_json_encoding(self):
        """Testa encoding JSON de datetime."""
        from neural_hive_specialists.feedback.retraining_trigger import RetrainingTriggerRecord

        record = RetrainingTriggerRecord(
            specialist_type="technical",
            feedback_count=100,
            feedback_window_days=7,
        )

        # model_dump deve serializar datetime
        data = record.model_dump()

        assert "triggered_at" in data
        assert isinstance(data["triggered_at"], str)


class TestRetrainingTriggerExtended:
    """Testes estendidos para RetrainingTrigger."""

    @pytest.fixture
    def config(self):
        """Configuração de teste."""
        return {
            "retraining_feedback_threshold": 100,
            "retraining_feedback_window_days": 7,
            "mlflow_tracking_uri": "http://mlflow:5000",
            "mlflow_experiment_name": "test_experiment",
            "mongodb_uri": "mongodb://localhost:27017",
            "mongodb_database": "test_db",
        }

    @pytest.fixture
    def mock_dependencies(self):
        """Mock de dependências."""
        return {
            "feedback_collector": Mock(),
            "mlflow_client": Mock(),
            "metrics": Mock(),
        }

    def test_init_with_config(self, config, mock_dependencies):
        """Testa inicialização com configuração."""
        from neural_hive_specialists.feedback.retraining_trigger import RetrainingTrigger

        trigger = RetrainingTrigger(
            config,
            "technical",
            mock_dependencies["feedback_collector"],
            mock_dependencies["mlflow_client"],
            mock_dependencies["metrics"],
        )

        assert trigger.specialist_type == "technical"
        assert trigger.threshold == 100
        assert trigger.window_days == 7

    def test_init_default_threshold(self, mock_dependencies):
        """Testa inicialização com threshold padrão."""
        config = {}  # Config vazia

        from neural_hive_specialists.feedback.retraining_trigger import RetrainingTrigger

        trigger = RetrainingTrigger(
            config,
            "technical",
            mock_dependencies["feedback_collector"],
            mock_dependencies["mlflow_client"],
            mock_dependencies["metrics"],
        )

        # Deve usar valor padrão (50 por padrão)
        assert trigger.threshold == 50

    def test_calculate_feedback_count(self, config, mock_dependencies):
        """Testa cálculo de contagem de feedback."""
        mock_feedback_collector = mock_dependencies["feedback_collector"]
        mock_feedback_collector.count_feedback_since.return_value = 75

        from neural_hive_specialists.feedback.retraining_trigger import RetrainingTrigger

        trigger = RetrainingTrigger(
            config,
            "technical",
            mock_feedback_collector,
            mock_dependencies["mlflow_client"],
            mock_dependencies["metrics"],
        )

        count = trigger.get_feedback_count()

        assert count == 75
        mock_feedback_collector.count_feedback_since.assert_called_once()

    def test_should_trigger_true(self, config, mock_dependencies):
        """Testa que trigger deve ser disparado quando threshold atingido."""
        mock_feedback_collector = mock_dependencies["feedback_collector"]
        mock_feedback_collector.count_feedback_since.return_value = 100

        from neural_hive_specialists.feedback.retraining_trigger import RetrainingTrigger

        trigger = RetrainingTrigger(
            config,
            "technical",
            mock_feedback_collector,
            mock_dependencies["mlflow_client"],
            mock_dependencies["metrics"],
        )

        should_trigger = trigger.should_trigger()

        assert should_trigger is True

    def test_should_trigger_false(self, config, mock_dependencies):
        """Testa que trigger não deve ser disparado abaixo do threshold."""
        mock_feedback_collector = mock_dependencies["feedback_collector"]
        mock_feedback_collector.count_feedback_since.return_value = 50

        from neural_hive_specialists.feedback.retraining_trigger import RetrainingTrigger

        trigger = RetrainingTrigger(
            config,
            "technical",
            mock_feedback_collector,
            mock_dependencies["mlflow_client"],
            mock_dependencies["metrics"],
        )

        should_trigger = trigger.should_trigger()

        assert should_trigger is False

    def test_create_trigger_record(self, config, mock_dependencies):
        """Testa criação de registro de trigger."""
        from neural_hive_specialists.feedback.retraining_trigger import RetrainingTrigger

        trigger = RetrainingTrigger(
            config,
            "technical",
            mock_dependencies["feedback_collector"],
            mock_dependencies["mlflow_client"],
            mock_dependencies["metrics"],
        )

        record = trigger.create_trigger_record(100)

        assert record.specialist_type == "technical"
        assert record.feedback_count == 100
        assert record.status == "pending"

    def test_update_trigger_status(self, config, mock_dependencies):
        """Testa atualização de status de trigger."""
        from neural_hive_specialists.feedback.retraining_trigger import RetrainingTrigger

        trigger = RetrainingTrigger(
            config,
            "technical",
            mock_dependencies["feedback_collector"],
            mock_dependencies["mlflow_client"],
            mock_dependencies["metrics"],
        )

        record = trigger.create_trigger_record(100)

        # Atualizar para completed
        trigger.update_trigger_status(record, "completed", mlflow_run_id="run-123")

        assert record.status == "completed"
        assert record.mlflow_run_id == "run-123"
        assert record.completed_at is not None

    def test_update_trigger_status_failed(self, config, mock_dependencies):
        """Testa atualização de status para failed."""
        from neural_hive_specialists.feedback.retraining_trigger import RetrainingTrigger

        trigger = RetrainingTrigger(
            config,
            "technical",
            mock_dependencies["feedback_collector"],
            mock_dependencies["mlflow_client"],
            mock_dependencies["metrics"],
        )

        record = trigger.create_trigger_record(100)

        # Atualizar para failed
        trigger.update_trigger_status(
            record, "failed", error_message="Training failed"
        )

        assert record.status == "failed"
        assert record.error_message == "Training failed"

    def test_get_time_window(self, config, mock_dependencies):
        """Testa obtenção de janela de tempo."""
        from neural_hive_specialists.feedback.retraining_trigger import RetrainingTrigger

        trigger = RetrainingTrigger(
            config,
            "technical",
            mock_dependencies["feedback_collector"],
            mock_dependencies["mlflow_client"],
            mock_dependencies["metrics"],
        )

        start, end = trigger.get_time_window()

        assert isinstance(start, datetime)
        assert isinstance(end, datetime)
        assert (end - start).days == 7

    def test_get_feedback_statistics(self, config, mock_dependencies):
        """Testa obtenção de estatísticas de feedback."""
        mock_feedback_collector = mock_dependencies["feedback_collector"]
        mock_feedback_collector.get_feedback_statistics.return_value = {
            "total": 100,
            "approve": 60,
            "reject": 40,
        }

        from neural_hive_specialists.feedback.retraining_trigger import RetrainingTrigger

        trigger = RetrainingTrigger(
            config,
            "technical",
            mock_feedback_collector,
            mock_dependencies["mlflow_client"],
            mock_dependencies["metrics"],
        )

        stats = trigger.get_feedback_statistics()

        assert stats["total"] == 100
        assert stats["approve"] == 60
        assert stats["reject"] == 40
