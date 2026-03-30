"""Testes simplificados para o script run_disaster_recovery_backup.py."""

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
    import run_disaster_recovery_backup
    SCRIPT_AVAILABLE = True
except ImportError:
    SCRIPT_AVAILABLE = False


@pytest.mark.skipif(not SCRIPT_AVAILABLE, reason="Script não disponível")
class TestCreateStorageClient:
    """Testes para create_storage_client()."""

    def test_create_storage_client_unsupported(self):
        """Testa erro para provider não suportado."""
        mock_config = Mock()
        mock_config.backup_storage_provider = "unsupported"

        with pytest.raises(ValueError):
            run_disaster_recovery_backup.create_storage_client(mock_config)


@pytest.mark.skipif(not SCRIPT_AVAILABLE, reason="Script não disponível")
class TestMainFunction:
    """Testes para main()."""

    @patch("run_disaster_recovery_backup.run_backup")
    @patch("sys.argv", ["run_disaster_recovery_backup.py"])
    def test_main_default(self, mock_run_backup):
        """Testa main com parâmetros padrão."""
        mock_run_backup.return_value = 0

        with pytest.raises(SystemExit) as exc_info:
            run_disaster_recovery_backup.main()

        assert exc_info.value.code == 0

    @patch("run_disaster_recovery_backup.run_backup")
    @patch("sys.argv", ["run_disaster_recovery_backup.py", "--specialist-type", "business"])
    def test_main_with_specialist_type(self, mock_run_backup):
        """Testa main com tipo de especialista específico."""
        mock_run_backup.return_value = 0

        with pytest.raises(SystemExit):
            run_disaster_recovery_backup.main()

        # Verificar argumento passado
        call_kwargs = mock_run_backup.call_args[1]
        assert call_kwargs["specialist_type"] == "business"

    @patch("run_disaster_recovery_backup.run_backup")
    @patch("sys.argv", ["run_disaster_recovery_backup.py", "--dry-run"])
    def test_main_dry_run(self, mock_run_backup):
        """Testa main em modo dry-run."""
        mock_run_backup.return_value = 0

        with pytest.raises(SystemExit):
            run_disaster_recovery_backup.main()

        call_kwargs = mock_run_backup.call_args[1]
        assert call_kwargs["dry_run"] is True

    @patch("run_disaster_recovery_backup.run_backup")
    @patch("sys.argv", ["run_disaster_recovery_backup.py", "--verbose"])
    def test_main_verbose(self, mock_run_backup):
        """Testa main em modo verbose."""
        mock_run_backup.return_value = 0

        with pytest.raises(SystemExit):
            run_disaster_recovery_backup.main()

        call_kwargs = mock_run_backup.call_args[1]
        assert call_kwargs["verbose"] is True

    @patch("run_disaster_recovery_backup.run_backup")
    @patch("sys.argv", ["run_disaster_recovery_backup.py", "--cleanup"])
    def test_main_with_cleanup(self, mock_run_backup):
        """Testa main com flag de cleanup."""
        mock_run_backup.return_value = 0

        with pytest.raises(SystemExit):
            run_disaster_recovery_backup.main()

        call_kwargs = mock_run_backup.call_args[1]
        assert call_kwargs["cleanup"] is True
