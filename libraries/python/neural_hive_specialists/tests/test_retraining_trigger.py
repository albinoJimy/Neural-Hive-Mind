"""
Testes unitários para RetrainingTrigger.
"""

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, Mock, patch

import pytest

from neural_hive_specialists.config import SpecialistConfig
from neural_hive_specialists.feedback import RetrainingTrigger


@pytest.fixture()
def mock_config():
    """Configuração mock para testes."""
    return SpecialistConfig(
        specialist_type="technical",
        service_name="test-retraining-specialist",
        environment="test",  # Ambiente de teste
        mongodb_uri="mongodb://localhost:27017",
        mongodb_database="neural_hive_test",
        enable_jwt_auth=False,  # Desabilitar JWT em testes
        enable_retraining_trigger=True,
        retraining_feedback_threshold=100,
        retraining_feedback_window_days=7,
        retraining_mlflow_project_uri="./ml_pipelines/training",
        mlflow_tracking_uri="http://localhost:5000",
        mlflow_experiment_name="test-experiment",
        mlflow_model_name="test-model",
        redis_cluster_nodes="localhost:6379",
        neo4j_uri="bolt://localhost:7687",
        neo4j_password="test",
    )


@pytest.fixture()
def mock_feedback_collector():
    """FeedbackCollector mock."""
    collector = Mock()
    collector.count_recent_feedback = Mock(return_value=150)
    return collector


@pytest.fixture()
def mock_mlflow_client():
    """MLflowClient mock."""
    return Mock()


@pytest.fixture()
def retraining_trigger(mock_config, mock_feedback_collector, mock_mlflow_client):
    """Instância de RetrainingTrigger com mocks."""
    with patch("neural_hive_specialists.feedback.retraining_trigger.MongoClient"):
        trigger = RetrainingTrigger(mock_config, mock_feedback_collector, mock_mlflow_client)
        trigger._triggers_collection = MagicMock()
        return trigger


class TestRetrainingTrigger:
    """Testes do RetrainingTrigger."""

    def test_should_trigger_when_threshold_met(self, retraining_trigger, mock_feedback_collector):
        """Teste quando threshold é atingido."""
        mock_feedback_collector.count_recent_feedback.return_value = 150

        should_trigger, count = retraining_trigger._should_trigger("technical")

        assert should_trigger is True
        assert count == 150

    def test_should_not_trigger_when_below_threshold(
        self, retraining_trigger, mock_feedback_collector
    ):
        """Teste quando abaixo do threshold."""
        mock_feedback_collector.count_recent_feedback.return_value = 50

        should_trigger, count = retraining_trigger._should_trigger("technical")

        assert should_trigger is False
        assert count == 50

    def test_check_cooldown_active(self, retraining_trigger):
        """Teste de cooldown ativo."""
        # Simular trigger recente (1 hora atrás)
        recent_trigger = {
            "specialist_type": "technical",
            "triggered_at": datetime.now(timezone.utc) - timedelta(hours=1),
            "trigger_id": "test-trigger",
            "status": "completed",
        }

        retraining_trigger._triggers_collection.find_one.return_value = recent_trigger

        is_cooldown = retraining_trigger._check_cooldown("technical")

        assert is_cooldown is True

    def test_cooldown_expired(self, retraining_trigger):
        """Teste de cooldown expirado."""
        from datetime import timedelta

        # Simular trigger antigo (48 horas atrás) - fora do período de cooldown de 24h
        old_trigger = {
            "specialist_type": "technical",
            "triggered_at": datetime.now(timezone.utc) - timedelta(hours=48),
            "trigger_id": "test-trigger",
            "status": "completed",
        }

        # Configurar mock para retornar None quando a consulta filtra por data recente
        # (trigger de 48h não está no período de 24h)
        def mock_find_one_filter(query, sort=None):
            # A query busca triggers com triggered_at >= cutoff_time (últimas 24h)
            # Como o trigger antigo é de 48h, ele não deve ser retornado
            if "triggered_at" in query:
                triggered_at_filter = query["triggered_at"]
                if isinstance(triggered_at_filter, dict) and "$gte" in triggered_at_filter:
                    # Query filtrando por data recente - trigger antigo não corresponde
                    return None
            return old_trigger

        retraining_trigger._triggers_collection.find_one = Mock(side_effect=mock_find_one_filter)

        is_cooldown = retraining_trigger._check_cooldown("technical")

        assert is_cooldown is False

    def test_cooldown_no_previous_trigger(self, retraining_trigger):
        """Teste sem trigger anterior."""
        retraining_trigger._triggers_collection.find_one.return_value = None

        is_cooldown = retraining_trigger._check_cooldown("technical")

        assert is_cooldown is False

    @patch("neural_hive_specialists.feedback.retraining_trigger.mlflow")
    def test_start_mlflow_run_success(self, mock_mlflow, retraining_trigger):
        """Teste de inicialização bem-sucedida de run MLflow."""
        mock_run = Mock()
        mock_run.run_id = "test-run-id"
        mock_mlflow.projects.run.return_value = mock_run
        mock_mlflow.get_experiment_by_name.return_value = Mock(experiment_id="exp-123")

        run_id, exp_id = retraining_trigger._start_mlflow_run("technical", 150)

        assert run_id == "test-run-id"
        assert exp_id == "exp-123"

        # Verificar que mlflow.set_experiment foi chamado
        mock_mlflow.set_experiment.assert_called_once_with("specialist-retraining-technical")

        # Verificar que mlflow.projects.run foi chamado SEM experiment_id
        call_args = mock_mlflow.projects.run.call_args
        assert "experiment_id" not in call_args.kwargs
        mock_mlflow.projects.run.assert_called_once()

    def test_trigger_retraining_success(self, retraining_trigger):
        """Teste de trigger bem-sucedido."""
        retraining_trigger._start_mlflow_run = Mock(return_value=("run-123", "exp-456"))
        retraining_trigger._triggers_collection.insert_one = Mock()
        retraining_trigger._triggers_collection.update_one = Mock()

        trigger_id = retraining_trigger.trigger_retraining("technical", 150)

        assert trigger_id.startswith("trigger-")
        retraining_trigger._triggers_collection.insert_one.assert_called_once()
        retraining_trigger._start_mlflow_run.assert_called_once_with(
            specialist_type="technical", feedback_count=150
        )

    def test_trigger_retraining_mlflow_error(self, retraining_trigger):
        """Teste de erro no MLflow."""
        retraining_trigger._start_mlflow_run = Mock(side_effect=Exception("MLflow error"))
        retraining_trigger._triggers_collection.insert_one = Mock()
        retraining_trigger._triggers_collection.update_one = Mock()

        with pytest.raises(Exception, match="MLflow error"):
            retraining_trigger.trigger_retraining("technical", 150)

        # Verificar que status foi atualizado para 'failed'
        retraining_trigger._triggers_collection.update_one.assert_called_once()

    def test_update_trigger_status(self, retraining_trigger):
        """Teste de atualização de status."""
        metadata = {"run_id": "test-run", "status": "completed"}

        retraining_trigger.update_trigger_status("trigger-123", "completed", metadata)

        retraining_trigger._triggers_collection.update_one.assert_called_once()

    def test_check_and_trigger_threshold_not_met(self, retraining_trigger, mock_feedback_collector):
        """Teste quando threshold não é atingido."""
        mock_feedback_collector.count_recent_feedback.return_value = 50

        trigger_id = retraining_trigger.check_and_trigger("technical")

        assert trigger_id is None

    def test_check_and_trigger_cooldown_active(self, retraining_trigger, mock_feedback_collector):
        """Teste quando cooldown está ativo."""
        mock_feedback_collector.count_recent_feedback.return_value = 150
        retraining_trigger._check_cooldown = Mock(return_value=True)

        trigger_id = retraining_trigger.check_and_trigger("technical", force=False)

        assert trigger_id is None

    def test_check_and_trigger_force_ignores_cooldown(
        self, retraining_trigger, mock_feedback_collector
    ):
        """Teste que force ignora cooldown."""
        mock_feedback_collector.count_recent_feedback.return_value = 150
        retraining_trigger._check_cooldown = Mock(return_value=True)
        retraining_trigger.trigger_retraining = Mock(return_value="trigger-123")

        trigger_id = retraining_trigger.check_and_trigger("technical", force=True)

        assert trigger_id == "trigger-123"
        retraining_trigger.trigger_retraining.assert_called_once()

    def test_check_and_trigger_success(self, retraining_trigger, mock_feedback_collector):
        """Teste de check and trigger bem-sucedido."""
        mock_feedback_collector.count_recent_feedback.return_value = 150
        retraining_trigger._check_cooldown = Mock(return_value=False)
        retraining_trigger.trigger_retraining = Mock(return_value="trigger-123")

        trigger_id = retraining_trigger.check_and_trigger("technical")

        assert trigger_id == "trigger-123"
        retraining_trigger.trigger_retraining.assert_called_once_with(
            specialist_type="technical", feedback_count=150
        )

    def test_get_recent_triggers(self, retraining_trigger):
        """Teste de consulta de triggers recentes."""
        mock_triggers = [
            {
                "trigger_id": "trigger-1",
                "specialist_type": "technical",
                "triggered_at": datetime.now(timezone.utc),
                "feedback_count": 150,
                "feedback_window_days": 7,
                "status": "completed",
                "metadata": {},
            }
        ]

        retraining_trigger._triggers_collection.find.return_value.sort.return_value.limit.return_value = (
            mock_triggers
        )

        triggers = retraining_trigger.get_recent_triggers("technical", limit=10)

        assert len(triggers) == 1
        assert triggers[0].trigger_id == "trigger-1"
