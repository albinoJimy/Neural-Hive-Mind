"""Testes simplificados para o script run_disaster_recovery_test.py."""

import os
import sys
from unittest.mock import Mock, patch

import pytest

# Adicionar diretório de scripts ao path
sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "scripts"),
)

try:
    import run_disaster_recovery_test

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
            run_disaster_recovery_test.create_storage_client(mock_config)

    @patch("run_disaster_recovery_test.GCSStorageClient")
    def test_create_gcs_client_missing_config(self, mock_gcs_class):
        """Testa erro quando configuração GCS está incompleta."""
        mock_config = Mock()
        mock_config.backup_storage_provider = "gcs"
        mock_config.backup_gcs_bucket = None
        mock_config.backup_gcs_project = None

        with pytest.raises(ValueError, match="obrigatório"):
            run_disaster_recovery_test.create_storage_client(mock_config)


@pytest.mark.skipif(not SCRIPT_AVAILABLE, reason="Script não disponível")
class TestSendAlert:
    """Testes para send_alert()."""

    @patch("run_disaster_recovery_test.asyncio.run")
    @patch.dict(os.environ, {"DR_ALERTMANAGER_URL": "http://alertmanager:9093"})
    def test_send_alert_with_env_urls(self, mock_asyncio_run):
        """Testa envio de alerta com URLs de variáveis de ambiente."""
        mock_asyncio_run.return_value = None

        # Não deve lançar erro
        run_disaster_recovery_test.send_alert(
            message="Teste de alerta",
            specialist_type="technical",
        )


@pytest.mark.skipif(not SCRIPT_AVAILABLE, reason="Script não disponível")
class TestPrintTestResults:
    """Testes para print_test_results()."""

    def test_print_results_success(self, capsys):
        """Testa impressão de resultados de sucesso."""
        result = {
            "status": "success",
            "backup_id": "backup-123",
            "duration_seconds": 30.5,
            "test_results": {
                "download": {"status": "success"},
                "restore": {"status": "success"},
            },
        }

        run_disaster_recovery_test.print_test_results(result, verbose=False)

        captured = capsys.readouterr()
        assert "SUCCESS" in captured.out
        assert "backup-123" in captured.out

    def test_print_results_failure(self, capsys):
        """Testa impressão de resultados de falha."""
        result = {
            "status": "failed",
            "backup_id": "backup-456",
            "error": "Restore failed",
        }

        run_disaster_recovery_test.print_test_results(result, verbose=False)

        captured = capsys.readouterr()
        assert "FAILED" in captured.out
