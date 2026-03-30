"""Testes simplificados para o script run_retraining_trigger.py."""

import os
import sys
import pytest
from unittest.mock import patch, Mock

# Adicionar diretório de scripts ao path
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(__file__), "..", "scripts"
    ),
)

try:
    import run_retraining_trigger
    SCRIPT_AVAILABLE = True
except ImportError:
    SCRIPT_AVAILABLE = False


@pytest.mark.skipif(not SCRIPT_AVAILABLE, reason="Script não disponível")
class TestLoadConfig:
    """Testes para load_config()."""

    @patch.dict(os.environ, {
        "MONGODB_URI": "mongodb://localhost:27017",
        "MONGODB_DATABASE": "neural_hive",
        "RETRAINING_FEEDBACK_THRESHOLD": "150",
        "RETRAINING_FEEDBACK_WINDOW_DAYS": "14",
        "MLFLOW_TRACKING_URI": "http://mlflow:5000",
    })
    def test_load_config_from_env(self):
        """Testa carregamento de config das variáveis de ambiente."""
        config = run_retraining_trigger.load_config()

        assert config["mongodb_uri"] == "mongodb://localhost:27017"
        assert config["mongodb_database"] == "neural_hive"
        assert config["retraining_feedback_threshold"] == 150
        assert config["retraining_feedback_window_days"] == 14

    @patch.dict(os.environ, {}, clear=True)
    def test_load_config_missing_mongodb_uri(self):
        """Testa erro quando MONGODB_URI não está definido."""
        with pytest.raises(SystemExit):
            run_retraining_trigger.load_config()

    @patch.dict(os.environ, {
        "MONGODB_URI": "mongodb://localhost:27017",
        "ENABLE_RETRAINING_TRIGGER": "false",
    })
    def test_load_config_retraining_disabled(self):
        """Testa configuração quando retraining está desabilitado."""
        config = run_retraining_trigger.load_config()
        assert config["enable_retraining_trigger"] is False


@pytest.mark.skipif(not SCRIPT_AVAILABLE, reason="Script não disponível")
class TestCheckAndTriggerRetraining:
    """Testes para check_and_trigger_retraining()."""

    def test_check_and_trigger_dry_run(self):
        """Testa verificação em modo dry-run."""
        with patch("run_retraining_trigger.initialize_components") as mock_init:
            mock_trigger = Mock()
            mock_trigger._should_trigger.return_value = (True, 150)
            mock_collector = Mock()
            mock_init.return_value = (mock_collector, mock_trigger)

            config = {"retraining_feedback_threshold": 100}

            result = run_retraining_trigger.check_and_trigger_retraining(
                specialist_type="technical",
                config=config,
                dry_run=True,
            )

            # Dry run deve retornar None
            assert result is None

    def test_check_and_trigger_error_handling(self):
        """Testa tratamento de erros."""
        with patch("run_retraining_trigger.initialize_components") as mock_init:
            mock_init.side_effect = Exception("Test error")

            config = {"retraining_feedback_threshold": 100}

            result = run_retraining_trigger.check_and_trigger_retraining(
                specialist_type="technical",
                config=config,
                dry_run=True,
            )

            # Deve retornar None em caso de erro
            assert result is None


@pytest.mark.skipif(not SCRIPT_AVAILABLE, reason="Script não disponível")
class TestMainFunction:
    """Testes para main()."""

    @patch("run_retraining_trigger.check_and_trigger_retraining")
    @patch("run_retraining_trigger.load_config")
    @patch("sys.argv", ["run_retraining_trigger.py"])
    def test_main_retraining_disabled(self, mock_load_config, mock_check):
        """Testa main quando retraining está desabilitado."""
        mock_load_config.return_value = {"enable_retraining_trigger": False}

        with pytest.raises(SystemExit) as exc_info:
            run_retraining_trigger.main()

        assert exc_info.value.code == 0

    @patch("run_retraining_trigger.check_and_trigger_retraining")
    @patch("run_retraining_trigger.load_config")
    @patch("sys.argv", ["run_retraining_trigger.py", "--specialist-type", "technical"])
    def test_main_single_specialist(self, mock_load_config, mock_check):
        """Testa main com único especialista."""
        mock_load_config.return_value = {
            "enable_retraining_trigger": True,
            "pushgateway_url": None,
        }
        mock_check.return_value = "trigger-123"

        with pytest.raises(SystemExit) as exc_info:
            run_retraining_trigger.main()

        assert exc_info.value.code == 0
        mock_check.assert_called_once()

    @patch("run_retraining_trigger.check_and_trigger_retraining")
    @patch("run_retraining_trigger.load_config")
    @patch("sys.argv", ["run_retraining_trigger.py"])
    def test_main_all_specialists(self, mock_load_config, mock_check):
        """Testa main processando todos os especialistas."""
        mock_load_config.return_value = {
            "enable_retraining_trigger": True,
            "pushgateway_url": None,
        }
        mock_check.return_value = None

        with pytest.raises(SystemExit) as exc_info:
            run_retraining_trigger.main()

        assert exc_info.value.code == 0
        assert mock_check.call_count == 5
