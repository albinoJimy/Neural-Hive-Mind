"""Testes simplificados para o script run_disaster_recovery_restore.py."""

import os
import sys
import pytest
from unittest.mock import patch, Mock
from datetime import datetime

# Adicionar diretório de scripts ao path
sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "scripts"),
)

try:
    import run_disaster_recovery_restore

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

        with pytest.raises(ValueError, match="não suportado"):
            run_disaster_recovery_restore.create_storage_client(mock_config)


@pytest.mark.skipif(not SCRIPT_AVAILABLE, reason="Script não disponível")
class TestListBackups:
    """Testes para list_backups()."""

    def test_list_backups_with_files(self, capsys):
        """Testa listagem de backups com arquivos."""
        mock_dr_manager = Mock()
        mock_dr_manager.list_available_backups.return_value = [
            {"key": "backup1.tar.gz", "size": 1024000, "timestamp": datetime(2026, 1, 1, 12, 0)},
        ]

        result = run_disaster_recovery_restore.list_backups(mock_dr_manager)

        assert result == 0

        captured = capsys.readouterr()
        assert "Total de backups: 1" in captured.out

    def test_list_backups_empty(self, capsys):
        """Testa listagem quando não há backups."""
        mock_dr_manager = Mock()
        mock_dr_manager.list_available_backups.return_value = []

        result = run_disaster_recovery_restore.list_backups(mock_dr_manager)

        assert result == 0

        captured = capsys.readouterr()
        assert "Nenhum backup encontrado" in captured.out


@pytest.mark.skipif(not SCRIPT_AVAILABLE, reason="Script não disponível")
class TestConfirmRestore:
    """Testes para confirm_restore()."""

    @patch("builtins.input", return_value="yes")
    def test_confirm_restore_yes(self, mock_input):
        """Testa confirmação com resposta 'yes'."""
        result = run_disaster_recovery_restore.confirm_restore("backup-123")
        assert result is True

    @patch("builtins.input", return_value="no")
    def test_confirm_restore_no(self, mock_input):
        """Testa confirmação com resposta 'no'."""
        result = run_disaster_recovery_restore.confirm_restore("backup-123")
        assert result is False
