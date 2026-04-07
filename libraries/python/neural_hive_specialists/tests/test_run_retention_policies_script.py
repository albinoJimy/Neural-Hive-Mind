"""Testes simplificados para o script run_retention_policies.py."""

import os
import sys
import pytest
from unittest.mock import patch, Mock

# Adicionar diretório de scripts ao path
sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "scripts"),
)

try:
    import run_retention_policies

    SCRIPT_AVAILABLE = True
except ImportError:
    SCRIPT_AVAILABLE = False


@pytest.mark.skipif(not SCRIPT_AVAILABLE, reason="Script não disponível")
class TestLoadConfig:
    """Testes para load_config()."""

    @patch.dict(
        os.environ,
        {
            "MONGODB_URI": "mongodb://localhost:27017",
            "MONGODB_DATABASE": "test_db",
            "ENABLE_PII_DETECTION": "true",
            "DEFAULT_RETENTION_DAYS": "730",
        },
    )
    def test_load_config_from_env(self):
        """Testa carregamento de config das variáveis de ambiente."""
        config = run_retention_policies.load_config()

        assert config.mongodb_uri == "mongodb://localhost:27017"
        assert config.mongodb_database == "test_db"
        assert config.enable_pii_detection is True
        assert config.default_retention_days == 730

    @patch.dict(os.environ, {}, clear=True)
    def test_load_config_missing_mongodb_uri(self):
        """Testa erro quando MONGODB_URI não está definido."""
        with pytest.raises(SystemExit):
            run_retention_policies.load_config()


@pytest.mark.skipif(not SCRIPT_AVAILABLE, reason="Script não disponível")
class TestSimpleConfig:
    """Testes para a classe SimpleConfig."""

    @patch.dict(
        os.environ,
        {
            "MONGODB_URI": "mongodb://localhost:27017",
            "MONGODB_DATABASE": "neural_hive",
            "AUDIT_LOG_RETENTION_DAYS": "365",
        },
    )
    def test_simple_config_defaults(self):
        """Testa valores padrão do SimpleConfig."""
        config = run_retention_policies.load_config()

        assert config.mongodb_database == "neural_hive"
        assert config.audit_log_retention_days == 365
        assert config.enable_pii_detection is True
        assert config.enable_field_encryption is True

    def test_simple_config_pii_entities(self):
        """Testa entidades PII padrão."""
        with patch.dict(os.environ, {"MONGODB_URI": "mongodb://localhost:27017"}):
            config = run_retention_policies.load_config()

            expected_entities = [
                "PERSON",
                "EMAIL_ADDRESS",
                "PHONE_NUMBER",
                "CREDIT_CARD",
                "IBAN_CODE",
                "IP_ADDRESS",
                "US_SSN",
                "CPF",
            ]
            assert config.pii_entities_to_detect == expected_entities


@pytest.mark.skipif(not SCRIPT_AVAILABLE, reason="Script não disponível")
class TestMainFunction:
    """Testes para main()."""

    @patch("run_retention_policies.apply_retention_policies")
    @patch("run_retention_policies.load_config")
    @patch("sys.argv", ["run_retention_policies.py"])
    def test_main_success(self, mock_load_config, mock_apply):
        """Testa execução bem-sucedida."""
        mock_config = Mock()
        mock_load_config.return_value = mock_config
        mock_apply.return_value = {"errors": 0}

        with pytest.raises(SystemExit) as exc_info:
            run_retention_policies.main()

        assert exc_info.value.code == 0

    @patch("run_retention_policies.apply_retention_policies")
    @patch("run_retention_policies.load_config")
    @patch("sys.argv", ["run_retention_policies.py"])
    def test_main_with_errors(self, mock_load_config, mock_apply):
        """Testa execução com erros."""
        mock_config = Mock()
        mock_load_config.return_value = mock_config
        mock_apply.return_value = {"errors": 5}

        with pytest.raises(SystemExit) as exc_info:
            run_retention_policies.main()

        assert exc_info.value.code == 1

    @patch("run_retention_policies.apply_retention_policies")
    @patch("run_retention_policies.load_config")
    @patch("sys.argv", ["run_retention_policies.py", "--dry-run"])
    def test_main_dry_run(self, mock_load_config, mock_apply):
        """Testa main em modo dry-run."""
        mock_config = Mock()
        mock_load_config.return_value = mock_config
        mock_apply.return_value = {"errors": 0}

        with pytest.raises(SystemExit) as exc_info:
            run_retention_policies.main()

        # Verificar que dry_run foi passado
        call_kwargs = mock_apply.call_args[1]
        assert call_kwargs["dry_run"] is True

    @patch("run_retention_policies.apply_retention_policies")
    @patch("run_retention_policies.load_config")
    @patch("sys.argv", ["run_retention_policies.py", "--policy-name", "high_risk_extended"])
    def test_main_with_policy_name(self, mock_load_config, mock_apply):
        """Testa main com nome de política específico."""
        mock_config = Mock()
        mock_load_config.return_value = mock_config
        mock_apply.return_value = {"errors": 0}

        with pytest.raises(SystemExit):
            run_retention_policies.main()

        # Verificar que policy_name foi passado
        call_kwargs = mock_apply.call_args[1]
        assert call_kwargs["policy_name"] == "high_risk_extended"
