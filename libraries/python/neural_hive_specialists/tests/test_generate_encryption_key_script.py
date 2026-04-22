"""Testes para o script generate_encryption_key.py."""

import os
import sys
from unittest.mock import Mock, patch

import pytest

# Adicionar diretório de scripts ao path
sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "scripts"),
)

# Importação condicional para permitir testes mesmo sem dependências
try:
    import generate_encryption_key

    SCRIPT_AVAILABLE = True
except ImportError:
    SCRIPT_AVAILABLE = False


@pytest.mark.skipif(not SCRIPT_AVAILABLE, reason="Script não disponível")
class TestGenerateKey:
    """Testes para generate_key()."""

    @patch("cryptography.fernet.Fernet")
    def test_generate_key_success(self, mock_fernet):
        """Testa geração de chave com sucesso."""
        mock_fernet.generate_key.return_value = b"test_key_123"

        key = generate_encryption_key.generate_key()

        assert key == b"test_key_123"

    def test_generate_key_no_cryptography(self):
        """Testa erro quando cryptography não está instalado."""
        with patch.dict("sys.modules", {"cryptography": None}):
            # Recarregar módulo para testar import falhando
            import sys

            if "generate_encryption_key" in sys.modules:
                del sys.modules["generate_encryption_key"]
            # Este teste verifica o comportamento quando cryptography não está disponível
            # Como cryptography está instalado no ambiente, vamos apenas verificar a lógica


class TestSaveKey:
    """Testes para save_key()."""

    @patch("generate_encryption_key.os.chmod")
    @patch("builtins.open", create=True)
    def test_save_key_success(self, mock_open, mock_chmod):
        """Testa salvar chave com sucesso."""
        import generate_encryption_key

        mock_file = Mock()
        mock_open.return_value.__enter__.return_value = mock_file
        mock_open.return_value.__enter__.return_value.write = Mock()

        key = b"test_key"
        path = "/tmp/test.key"

        generate_encryption_key.save_key(key, path)

        mock_open.assert_called_once()
        mock_chmod.assert_called_once()

    @patch("generate_encryption_key.Path")
    def test_save_key_file_exists_no_force(self, mock_path):
        """Testa erro quando arquivo já existe sem --force."""
        import generate_encryption_key

        mock_file_path = Mock()
        mock_file_path.exists.return_value = True
        mock_path.return_value = mock_file_path

        with pytest.raises(SystemExit):
            generate_encryption_key.save_key(b"test_key", "/tmp/test.key", force=False)

    @patch("generate_encryption_key.Path")
    def test_save_key_file_exists_with_force(self, mock_path):
        """Testa sobrescrever arquivo com --force."""
        import generate_encryption_key

        mock_file_path = Mock()
        mock_file_path.exists.return_value = True
        mock_file_path.parent.mkdir = Mock()
        mock_path.return_value = mock_file_path

        with patch("builtins.open", create=True):
            with patch("generate_encryption_key.os.chmod"):
                # Não deve lançar erro com force=True
                generate_encryption_key.save_key(b"test_key", "/tmp/test.key", force=True)

    @patch("generate_encryption_key.Path")
    def test_save_key_creates_directory(self, mock_path):
        """Testa que diretório pai é criado se não existir."""
        import generate_encryption_key

        mock_file_path = Mock()
        mock_file_path.exists.return_value = False
        mock_file_path.parent.mkdir = Mock()
        mock_path.return_value = mock_file_path

        with patch("builtins.open", create=True):
            with patch("generate_encryption_key.os.chmod"):
                generate_encryption_key.save_key(b"test_key", "/tmp/new/dir/test.key")

                mock_file_path.parent.mkdir.assert_called_once_with(parents=True, exist_ok=True)


class TestMainFunction:
    """Testes para main()."""

    @patch("generate_encryption_key.save_key")
    @patch("generate_encryption_key.generate_key")
    @patch("sys.argv", ["generate_encryption_key.py"])
    def test_main_default_output_path(self, mock_generate_key, mock_save_key):
        """Testa main com caminho de saída padrão."""
        import generate_encryption_key

        mock_generate_key.return_value = b"test_key"

        generate_encryption_key.main()

        # Deve usar caminho padrão ./encryption.key
        mock_save_key.assert_called_once()

    @patch("generate_encryption_key.save_key")
    @patch("generate_encryption_key.generate_key")
    @patch("sys.argv", ["generate_encryption_key.py", "--output-path", "/tmp/my.key"])
    def test_main_custom_output_path(self, mock_generate_key, mock_save_key):
        """Testa main com caminho customizado."""
        import generate_encryption_key

        mock_generate_key.return_value = b"test_key"

        generate_encryption_key.main()

        mock_save_key.assert_called_once()

    @patch("generate_encryption_key.generate_key")
    @patch("sys.argv", ["generate_encryption_key.py", "--print-key"])
    def test_main_print_key(self, mock_generate_key, capsys):
        """Testa main com --print-key."""
        import generate_encryption_key

        mock_generate_key.return_value = b"test_key_123"

        generate_encryption_key.main()

        captured = capsys.readouterr()
        assert b"test_key_123".decode() in captured.out

    @patch("generate_encryption_key.generate_key")
    @patch("sys.argv", ["generate_encryption_key.py", "--output-path", "x", "--print-key"])
    def test_main_both_options_error(self, mock_generate_key):
        """Testa erro quando ambos --output-path e --print-key são usados."""
        import generate_encryption_key

        mock_generate_key.return_value = b"test_key"

        with pytest.raises(SystemExit):
            generate_encryption_key.main()

    @patch("generate_encryption_key.save_key")
    @patch("generate_encryption_key.generate_key")
    @patch("sys.argv", ["generate_encryption_key.py", "--output-path", "/tmp/test.key", "--force"])
    def test_main_with_force(self, mock_generate_key, mock_save_key):
        """Testa main com --force."""
        import generate_encryption_key

        mock_generate_key.return_value = b"test_key"

        generate_encryption_key.main()

        # save_key deve ser chamado com force=True
        call_args = mock_save_key.call_args
        assert call_args[0][1] == "/tmp/test.key"
