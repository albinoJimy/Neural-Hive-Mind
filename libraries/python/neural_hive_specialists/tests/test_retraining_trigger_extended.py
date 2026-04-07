"""
Testes para RetrainingTrigger.

Cobertura para feedback/retraining_trigger.py com base na API implementada.
"""

import pytest
from unittest.mock import Mock
from datetime import datetime


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

        now = datetime.now()
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


class TestRetrainingTrigger:
    """Testes para RetrainingTrigger."""

    @pytest.fixture
    def config(self):
        """Configuração de teste."""
        from neural_hive_specialists.config import SpecialistConfig

        return SpecialistConfig(
            specialist_type="technical",
            service_name="test_service",
            environment="test",
            mlflow_tracking_uri="http://mlflow:5000",
            mlflow_experiment_name="test_experiment",
            mlflow_model_name="test_model",
            mongodb_uri="mongodb://localhost:27017",
            mongodb_database="test_db",
            redis_cluster_nodes="localhost:6379",
            neo4j_uri="bolt://localhost:7687",
            neo4j_password="test_password",
            enable_jwt_auth=False,
            enable_retraining_trigger=True,
            retraining_feedback_threshold=100,
            retraining_feedback_window_days=7,
            retraining_mlflow_project_uri="/fake/path",
            training_model_types=["random_forest"],
            training_hyperparameter_tuning=False,
            retraining_min_feedback_quality=0.5,
        )

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
            mock_dependencies["feedback_collector"],
            mock_dependencies["mlflow_client"],
            mock_dependencies["metrics"],
        )

        assert trigger.config is config
        assert trigger.feedback_collector is mock_dependencies["feedback_collector"]

    def test_should_trigger_true(self, config, mock_dependencies):
        """Testa que trigger deve ser disparado quando threshold atingido."""
        mock_feedback_collector = mock_dependencies["feedback_collector"]
        mock_feedback_collector.count_recent_feedback.return_value = 100

        from neural_hive_specialists.feedback.retraining_trigger import RetrainingTrigger

        trigger = RetrainingTrigger(
            config,
            mock_feedback_collector,
            mock_dependencies["mlflow_client"],
            mock_dependencies["metrics"],
        )

        should_trigger, count = trigger._should_trigger("technical")

        assert should_trigger is True
        assert count == 100
        mock_feedback_collector.count_recent_feedback.assert_called_once_with(
            specialist_type="technical",
            window_days=7,
        )

    def test_should_trigger_false(self, config, mock_dependencies):
        """Testa que trigger não deve ser disparado abaixo do threshold."""
        mock_feedback_collector = mock_dependencies["feedback_collector"]
        mock_feedback_collector.count_recent_feedback.return_value = 50

        from neural_hive_specialists.feedback.retraining_trigger import RetrainingTrigger

        trigger = RetrainingTrigger(
            config,
            mock_feedback_collector,
            mock_dependencies["mlflow_client"],
            mock_dependencies["metrics"],
        )

        should_trigger, count = trigger._should_trigger("technical")

        assert should_trigger is False
        assert count == 50

    def test_check_cooldown_no_recent_triggers(self, config, mock_dependencies):
        """Testa cooldown quando não há triggers recentes."""
        from neural_hive_specialists.feedback.retraining_trigger import RetrainingTrigger

        trigger = RetrainingTrigger(
            config,
            mock_dependencies["feedback_collector"],
            mock_dependencies["mlflow_client"],
            mock_dependencies["metrics"],
        )

        # Sem triggers recentes deve retornar False (sem cooldown)
        in_cooldown = trigger._check_cooldown("technical")

        assert in_cooldown is False

    def test_get_recent_triggers(self, config, mock_dependencies):
        """Testa obtenção de triggers recentes."""
        from neural_hive_specialists.feedback.retraining_trigger import RetrainingTrigger

        trigger = RetrainingTrigger(
            config,
            mock_dependencies["feedback_collector"],
            mock_dependencies["mlflow_client"],
            mock_dependencies["metrics"],
        )

        triggers = trigger.get_recent_triggers("technical", limit=5)

        assert isinstance(triggers, list)

    def test_close(self, config, mock_dependencies):
        """Testa fechamento de conexões."""
        from neural_hive_specialists.feedback.retraining_trigger import RetrainingTrigger

        trigger = RetrainingTrigger(
            config,
            mock_dependencies["feedback_collector"],
            mock_dependencies["mlflow_client"],
            mock_dependencies["metrics"],
        )

        # Não deve lançar exceção
        trigger.close()
