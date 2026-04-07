"""
Testes unitários para FieldEncryptor.

Cobertura: inicialização, encrypt/decrypt roundtrip, prefixo 'enc:', dict encryption,
invalid ciphertext, file permissions 0600, auto key generation.
"""

import pytest
import os
import tempfile
from unittest.mock import Mock, patch
from cryptography.fernet import Fernet

from neural_hive_specialists.compliance.field_encryptor import FieldEncryptor


@pytest.fixture
def mock_config():
    """Cria configuração mockada para testes."""
    config = Mock()
    config.enable_field_encryption = True
    config.encryption_algorithm = "fernet"
    config.encryption_key_path = None
    config.fields_to_encrypt = ["correlation_id", "trace_id", "span_id"]
    return config


@pytest.fixture
def temp_key_file():
    """Cria arquivo temporário para chave de criptografia."""
    with tempfile.NamedTemporaryFile(mode="wb", delete=False) as f:
        key = Fernet.generate_key()
        f.write(key)
        temp_path = f.name

    yield temp_path

    # Cleanup
    if os.path.exists(temp_path):
        os.remove(temp_path)


@pytest.mark.unit
class TestFieldEncryptorInitialization:
    """Testes de inicialização do FieldEncryptor."""

    def test_initialization_disabled(self):
        """Testa inicialização quando encryption está desabilitado."""
        config = Mock()
        config.enable_field_encryption = False

        encryptor = FieldEncryptor(config)

        assert encryptor.enabled is False
        assert encryptor.cipher is None

    def test_initialization_with_key_file(self, temp_key_file):
        """Testa inicialização carregando chave de arquivo."""
        config = Mock()
        config.enable_field_encryption = True
        config.encryption_algorithm = "fernet"
        config.encryption_key_path = temp_key_file
        config.fields_to_encrypt = []

        encryptor = FieldEncryptor(config)

        assert encryptor.enabled is True
        assert encryptor.cipher is not None

    def test_initialization_auto_generate_key(self, mock_config):
        """Testa geração automática de chave."""
        encryptor = FieldEncryptor(mock_config)

        assert encryptor.enabled is True
        assert encryptor.cipher is not None

    def test_initialization_handles_error(self, mock_config):
        """Testa que erro na inicialização desabilita encryption."""
        with patch(
            "neural_hive_specialists.compliance.field_encryptor.Fernet",
            side_effect=Exception("Crypto error"),
        ):
            encryptor = FieldEncryptor(mock_config)
            assert encryptor.enabled is False

    def test_initialization_saves_key_with_permissions(self, mock_config):
        """Testa que chave gerada é salva com permissões 0600."""
        with tempfile.TemporaryDirectory() as tmpdir:
            key_path = os.path.join(tmpdir, "test_key.key")
            mock_config.encryption_key_path = key_path

            encryptor = FieldEncryptor(mock_config)

            assert os.path.exists(key_path)
            # Verificar permissões (apenas em sistemas Unix-like)
            if os.name != "nt":  # Não Windows
                stat_info = os.stat(key_path)
                permissions = oct(stat_info.st_mode)[-3:]
                assert permissions == "600"

    def test_initialization_invalid_key_file_generates_new(self, mock_config):
        """Testa que chave inválida gera nova chave."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("invalid_key_data")
            invalid_key_path = f.name

        try:
            mock_config.encryption_key_path = invalid_key_path

            encryptor = FieldEncryptor(mock_config)

            # Deve gerar nova chave e funcionar
            assert encryptor.enabled is True
            assert encryptor.cipher is not None
        finally:
            if os.path.exists(invalid_key_path):
                os.remove(invalid_key_path)


@pytest.mark.unit
class TestEncryptField:
    """Testes do método encrypt_field."""

    @pytest.fixture
    def encryptor(self, mock_config):
        """Cria encryptor com chave válida."""
        return FieldEncryptor(mock_config)

    def test_encrypt_field_success(self, encryptor):
        """Testa criptografia bem-sucedida de campo."""
        value = "sensitive_data"

        encrypted = encryptor.encrypt_field(value)

        assert encrypted != value
        assert encrypted.startswith("enc:")
        assert len(encrypted) > len(value)

    def test_encrypt_field_adds_prefix(self, encryptor):
        """Verifica que prefixo 'enc:' é adicionado."""
        encrypted = encryptor.encrypt_field("test")

        assert encrypted.startswith("enc:")

    def test_encrypt_field_empty_value(self, encryptor):
        """Testa que valor vazio retorna vazio."""
        encrypted = encryptor.encrypt_field("")

        assert encrypted == ""

    def test_encrypt_field_none_value(self, encryptor):
        """Testa que None retorna None."""
        encrypted = encryptor.encrypt_field(None)

        assert encrypted is None

    def test_encrypt_field_converts_non_string(self, encryptor):
        """Testa que valores não-string são convertidos."""
        encrypted = encryptor.encrypt_field(12345)

        assert encrypted.startswith("enc:")

    def test_encrypt_field_disabled(self):
        """Testa que encryptor desabilitado retorna valor original."""
        config = Mock()
        config.enable_field_encryption = False
        encryptor = FieldEncryptor(config)

        encrypted = encryptor.encrypt_field("test")

        assert encrypted == "test"

    def test_encrypt_field_handles_error(self, encryptor):
        """Testa que erro na criptografia retorna valor original."""
        with patch.object(encryptor.cipher, "encrypt", side_effect=Exception("Crypto error")):
            value = "test"
            encrypted = encryptor.encrypt_field(value)

            assert encrypted == value


@pytest.mark.unit
class TestDecryptField:
    """Testes do método decrypt_field."""

    @pytest.fixture
    def encryptor(self, mock_config):
        """Cria encryptor com chave válida."""
        return FieldEncryptor(mock_config)

    def test_decrypt_field_success(self, encryptor):
        """Testa descriptografia bem-sucedida de campo."""
        original = "sensitive_data"
        encrypted = encryptor.encrypt_field(original)

        decrypted = encryptor.decrypt_field(encrypted)

        assert decrypted == original

    def test_decrypt_field_removes_prefix(self, encryptor):
        """Verifica que prefixo 'enc:' é removido antes de descriptografar."""
        original = "test"
        encrypted = encryptor.encrypt_field(original)

        assert encrypted.startswith("enc:")
        decrypted = encryptor.decrypt_field(encrypted)
        assert decrypted == original

    def test_decrypt_field_empty_value(self, encryptor):
        """Testa que valor vazio retorna vazio."""
        decrypted = encryptor.decrypt_field("")

        assert decrypted == ""

    def test_decrypt_field_none_value(self, encryptor):
        """Testa que None retorna None."""
        decrypted = encryptor.decrypt_field(None)

        assert decrypted is None

    def test_decrypt_field_invalid_token(self, encryptor):
        """Testa que token inválido retorna valor sem prefixo."""
        invalid_encrypted = "enc:invalid_token_data"

        decrypted = encryptor.decrypt_field(invalid_encrypted)

        # Deve retornar o valor após remover prefixo (código já removeu 'enc:')
        assert decrypted == "invalid_token_data"

    def test_decrypt_field_disabled(self):
        """Testa que encryptor desabilitado retorna valor original."""
        config = Mock()
        config.enable_field_encryption = False
        encryptor = FieldEncryptor(config)

        decrypted = encryptor.decrypt_field("enc:test")

        assert decrypted == "enc:test"

    def test_decrypt_field_handles_error(self, encryptor):
        """Testa que erro na descriptografia retorna valor sem prefixo."""
        with patch.object(encryptor.cipher, "decrypt", side_effect=Exception("Decrypt error")):
            encrypted = "enc:some_encrypted_data"
            decrypted = encryptor.decrypt_field(encrypted)

            # Retorna valor após remover prefixo
            assert decrypted == "some_encrypted_data"


@pytest.mark.unit
class TestEncryptDecryptRoundtrip:
    """Testes de roundtrip encrypt/decrypt."""

    @pytest.fixture
    def encryptor(self, mock_config):
        """Cria encryptor com chave válida."""
        return FieldEncryptor(mock_config)

    def test_roundtrip_simple_string(self, encryptor):
        """Testa roundtrip com string simples."""
        original = "test_value"

        encrypted = encryptor.encrypt_field(original)
        decrypted = encryptor.decrypt_field(encrypted)

        assert decrypted == original

    def test_roundtrip_unicode_string(self, encryptor):
        """Testa roundtrip com string unicode."""
        original = "João Silva - São Paulo 🇧🇷"

        encrypted = encryptor.encrypt_field(original)
        decrypted = encryptor.decrypt_field(encrypted)

        assert decrypted == original

    def test_roundtrip_long_string(self, encryptor):
        """Testa roundtrip com string longa."""
        original = "a" * 10000

        encrypted = encryptor.encrypt_field(original)
        decrypted = encryptor.decrypt_field(encrypted)

        assert decrypted == original

    def test_roundtrip_special_characters(self, encryptor):
        """Testa roundtrip com caracteres especiais."""
        original = "test@#$%^&*(){}[]|\\:;\"'<>,.?/~`"

        encrypted = encryptor.encrypt_field(original)
        decrypted = encryptor.decrypt_field(encrypted)

        assert decrypted == original


@pytest.mark.unit
class TestEncryptDict:
    """Testes do método encrypt_dict."""

    @pytest.fixture
    def encryptor(self, mock_config):
        """Cria encryptor com chave válida."""
        return FieldEncryptor(mock_config)

    def test_encrypt_dict_configured_fields(self, encryptor):
        """Testa criptografia de campos configurados em dicionário."""
        data = {
            "correlation_id": "corr-123",
            "trace_id": "trace-456",
            "span_id": "span-789",
            "other_field": "not_encrypted",
        }

        encrypted_data = encryptor.encrypt_dict(data)

        assert encrypted_data["correlation_id"].startswith("enc:")
        assert encrypted_data["trace_id"].startswith("enc:")
        assert encrypted_data["span_id"].startswith("enc:")
        assert encrypted_data["other_field"] == "not_encrypted"

    def test_encrypt_dict_custom_fields(self, encryptor):
        """Testa criptografia de campos customizados."""
        data = {
            "custom_field_1": "value1",
            "custom_field_2": "value2",
            "other": "unchanged",
        }

        encrypted_data = encryptor.encrypt_dict(data, fields_to_encrypt=["custom_field_1"])

        assert encrypted_data["custom_field_1"].startswith("enc:")
        assert encrypted_data["custom_field_2"] == "value2"
        assert encrypted_data["other"] == "unchanged"

    def test_encrypt_dict_already_encrypted_skip(self, encryptor):
        """Testa que campos já criptografados não são re-criptografados."""
        data = {"correlation_id": "enc:already_encrypted"}

        encrypted_data = encryptor.encrypt_dict(data)

        # Deve permanecer igual
        assert encrypted_data["correlation_id"] == "enc:already_encrypted"

    def test_encrypt_dict_missing_fields(self, encryptor):
        """Testa que campos ausentes são ignorados."""
        data = {"other_field": "value"}

        encrypted_data = encryptor.encrypt_dict(data)

        # Não deve lançar erro
        assert encrypted_data == data

    def test_encrypt_dict_empty_values_skip(self, encryptor):
        """Testa que valores vazios/None são ignorados."""
        data = {"correlation_id": None, "trace_id": "", "span_id": "valid"}

        encrypted_data = encryptor.encrypt_dict(data)

        assert encrypted_data["correlation_id"] is None
        assert encrypted_data["trace_id"] == ""
        assert encrypted_data["span_id"].startswith("enc:")

    def test_encrypt_dict_disabled(self):
        """Testa que encryptor desabilitado retorna dicionário original."""
        config = Mock()
        config.enable_field_encryption = False
        encryptor = FieldEncryptor(config)

        data = {"field": "value"}
        encrypted_data = encryptor.encrypt_dict(data)

        assert encrypted_data == data


@pytest.mark.unit
class TestDecryptDict:
    """Testes do método decrypt_dict."""

    @pytest.fixture
    def encryptor(self, mock_config):
        """Cria encryptor com chave válida."""
        return FieldEncryptor(mock_config)

    def test_decrypt_dict_configured_fields(self, encryptor):
        """Testa descriptografia de campos configurados em dicionário."""
        original_data = {
            "correlation_id": "corr-123",
            "trace_id": "trace-456",
            "span_id": "span-789",
        }

        encrypted_data = encryptor.encrypt_dict(original_data)
        decrypted_data = encryptor.decrypt_dict(encrypted_data)

        assert decrypted_data["correlation_id"] == "corr-123"
        assert decrypted_data["trace_id"] == "trace-456"
        assert decrypted_data["span_id"] == "span-789"

    def test_decrypt_dict_custom_fields(self, encryptor):
        """Testa descriptografia de campos customizados."""
        data = {"custom_field": "value"}

        encrypted_data = encryptor.encrypt_dict(data, fields_to_encrypt=["custom_field"])
        decrypted_data = encryptor.decrypt_dict(encrypted_data, fields_to_decrypt=["custom_field"])

        assert decrypted_data["custom_field"] == "value"

    def test_decrypt_dict_only_encrypted_fields(self, encryptor):
        """Testa que apenas campos com prefixo 'enc:' são descriptografados."""
        data = {"encrypted_field": "enc:some_cipher", "plain_field": "plain_value"}

        # Mock decrypt para evitar erro com cipher inválido
        with patch.object(
            encryptor,
            "decrypt_field",
            side_effect=lambda x: "decrypted" if x.startswith("enc:") else x,
        ):
            decrypted_data = encryptor.decrypt_dict(
                data, fields_to_decrypt=["encrypted_field", "plain_field"]
            )

            # plain_field não deve ser alterado
            assert decrypted_data["plain_field"] == "plain_value"

    def test_decrypt_dict_disabled(self):
        """Testa que encryptor desabilitado retorna dicionário original."""
        config = Mock()
        config.enable_field_encryption = False
        encryptor = FieldEncryptor(config)

        data = {"field": "enc:value"}
        decrypted_data = encryptor.decrypt_dict(data)

        assert decrypted_data == data


@pytest.mark.unit
class TestKeyManagement:
    """Testes de gerenciamento de chaves."""

    def test_load_key_from_file(self, temp_key_file):
        """Testa carregamento de chave de arquivo."""
        config = Mock()
        config.enable_field_encryption = True
        config.encryption_algorithm = "fernet"
        config.encryption_key_path = temp_key_file
        config.fields_to_encrypt = []

        encryptor = FieldEncryptor(config)

        assert encryptor.enabled is True
        assert encryptor.cipher is not None

    def test_generate_key_when_file_not_exists(self, mock_config):
        """Testa geração de chave quando arquivo não existe."""
        with tempfile.TemporaryDirectory() as tmpdir:
            key_path = os.path.join(tmpdir, "new_key.key")
            mock_config.encryption_key_path = key_path

            encryptor = FieldEncryptor(mock_config)

            # Chave deve ser gerada e salva
            assert os.path.exists(key_path)
            assert encryptor.enabled is True

    def test_key_file_permissions_0600(self, mock_config):
        """Testa que arquivo de chave tem permissões 0600."""
        if os.name == "nt":  # Skip em Windows
            pytest.skip("Teste de permissões Unix-only")

        with tempfile.TemporaryDirectory() as tmpdir:
            key_path = os.path.join(tmpdir, "key.key")
            mock_config.encryption_key_path = key_path

            encryptor = FieldEncryptor(mock_config)

            stat_info = os.stat(key_path)
            permissions = oct(stat_info.st_mode)[-3:]
            assert permissions == "600"

    def test_auto_key_generation_warning_path(self, mock_config):
        """Testa que chave auto-gerada usa path temporário com warning."""
        mock_config.encryption_key_path = None

        encryptor = FieldEncryptor(mock_config)

        # Chave deve ser gerada e salva em /tmp
        assert encryptor.enabled is True
        assert os.path.exists("/tmp/neural_hive_encryption.key")

        # Cleanup
        if os.path.exists("/tmp/neural_hive_encryption.key"):
            os.remove("/tmp/neural_hive_encryption.key")

    def test_save_key_creates_directory(self, mock_config):
        """Testa que diretório é criado se não existe."""
        with tempfile.TemporaryDirectory() as tmpdir:
            key_path = os.path.join(tmpdir, "subdir", "key.key")
            mock_config.encryption_key_path = key_path

            encryptor = FieldEncryptor(mock_config)

            # Diretório deve ser criado
            assert os.path.exists(os.path.dirname(key_path))
            assert os.path.exists(key_path)
