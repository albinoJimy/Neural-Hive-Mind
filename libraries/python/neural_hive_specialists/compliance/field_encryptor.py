"""
Criptografia de campos sensíveis usando Fernet (AES-128).
"""
import os
import structlog
from typing import Dict, Any, Optional
from cryptography.fernet import Fernet, InvalidToken

logger = structlog.get_logger(__name__)


class FieldEncryptor:
    """
    Criptografa e descriptografa campos sensíveis usando Fernet (AES-128).

    Fernet é uma implementação de criptografia simétrica autenticada que usa:
    - AES em modo CBC com chave de 128 bits
    - HMAC SHA256 para autenticação
    - Timestamping automático

    Uso:
        encryptor = FieldEncryptor(config)
        encrypted = encryptor.encrypt_field("sensitive_data")
        decrypted = encryptor.decrypt_field(encrypted)
    """

    def __init__(self, config):
        """
        Inicializa FieldEncryptor com configuração.

        Args:
            config: SpecialistConfig com configurações de criptografia
        """
        self.config = config
        self.enabled = config.enable_field_encryption
        self.cipher = None

        if not self.enabled:
            logger.info("FieldEncryptor desabilitado por configuração")
            return

        try:
            # Carregar ou gerar chave
            key = self._load_or_generate_key()
            self.cipher = Fernet(key)

            logger.info(
                "FieldEncryptor inicializado com sucesso",
                algorithm=config.encryption_algorithm,
                key_path=config.encryption_key_path if config.encryption_key_path else "auto-generated"
            )

        except Exception as e:
            logger.error(
                "Falha ao inicializar FieldEncryptor - criptografia desabilitada",
                error=str(e)
            )
            self.enabled = False

    def encrypt_field(self, value: str) -> str:
        """
        Criptografa valor de campo.

        Args:
            value: Valor a criptografar

        Returns:
            Valor criptografado em base64 com prefixo 'enc:'
        """
        if not self.enabled or not value:
            return value

        try:
            # Converter para bytes se necessário
            if isinstance(value, str):
                value_bytes = value.encode('utf-8')
            else:
                value_bytes = str(value).encode('utf-8')

            # Criptografar
            encrypted_bytes = self.cipher.encrypt(value_bytes)

            # Retornar como string base64 com prefixo
            encrypted_str = encrypted_bytes.decode('utf-8')
            return f"enc:{encrypted_str}"

        except Exception as e:
            logger.error(
                "Erro ao criptografar campo - retornando valor original",
                error=str(e),
                value_length=len(str(value))
            )
            return value

    def decrypt_field(self, encrypted_value: str) -> str:
        """
        Descriptografa valor de campo.

        Args:
            encrypted_value: Valor criptografado (com prefixo 'enc:')

        Returns:
            Valor original descriptografado
        """
        if not self.enabled or not encrypted_value:
            return encrypted_value

        try:
            # Remover prefixo se presente
            if encrypted_value.startswith('enc:'):
                encrypted_value = encrypted_value[4:]

            # Descriptografar
            encrypted_bytes = encrypted_value.encode('utf-8')
            decrypted_bytes = self.cipher.decrypt(encrypted_bytes)

            return decrypted_bytes.decode('utf-8')

        except InvalidToken:
            logger.error(
                "Token de criptografia inválido - valor corrompido ou chave errada"
            )
            return encrypted_value

        except Exception as e:
            logger.error(
                "Erro ao descriptografar campo - retornando valor criptografado",
                error=str(e)
            )
            return encrypted_value

    def encrypt_dict(
        self,
        data: Dict[str, Any],
        fields_to_encrypt: Optional[list] = None
    ) -> Dict[str, Any]:
        """
        Criptografa campos específicos em dicionário.

        Args:
            data: Dicionário para processar
            fields_to_encrypt: Lista de campos a criptografar (usa config se None)

        Returns:
            Dicionário com campos criptografados
        """
        if not self.enabled:
            return data

        if fields_to_encrypt is None:
            fields_to_encrypt = self.config.fields_to_encrypt

        encrypted_data = data.copy()

        for field in fields_to_encrypt:
            if field in encrypted_data and encrypted_data[field]:
                value = encrypted_data[field]

                # Não criptografar se já está criptografado
                if isinstance(value, str) and value.startswith('enc:'):
                    continue

                encrypted_data[field] = self.encrypt_field(str(value))

        return encrypted_data

    def decrypt_dict(
        self,
        data: Dict[str, Any],
        fields_to_decrypt: Optional[list] = None
    ) -> Dict[str, Any]:
        """
        Descriptografa campos específicos em dicionário.

        Args:
            data: Dicionário para processar
            fields_to_decrypt: Lista de campos a descriptografar (usa config se None)

        Returns:
            Dicionário com campos descriptografados
        """
        if not self.enabled:
            return data

        if fields_to_decrypt is None:
            fields_to_decrypt = self.config.fields_to_encrypt

        decrypted_data = data.copy()

        for field in fields_to_decrypt:
            if field in decrypted_data and decrypted_data[field]:
                value = decrypted_data[field]

                # Descriptografar apenas se tem prefixo
                if isinstance(value, str) and value.startswith('enc:'):
                    decrypted_data[field] = self.decrypt_field(value)

        return decrypted_data

    def _load_or_generate_key(self) -> bytes:
        """
        Carrega chave de arquivo ou gera nova.

        Returns:
            Chave Fernet (32 bytes base64)
        """
        key_path = self.config.encryption_key_path

        # Se path configurado, carregar de arquivo
        if key_path and os.path.exists(key_path):
            try:
                with open(key_path, 'rb') as f:
                    key = f.read()

                # Validar formato
                Fernet(key)  # Lança exceção se inválida

                logger.info("Chave de criptografia carregada de arquivo", path=key_path)
                return key

            except Exception as e:
                logger.error(
                    "Erro ao carregar chave de arquivo - gerando nova",
                    path=key_path,
                    error=str(e)
                )

        # Gerar chave nova
        key = Fernet.generate_key()

        # Salvar chave se path configurado
        if key_path:
            try:
                self._save_key(key, key_path)
            except Exception as e:
                logger.warning(
                    "Falha ao salvar chave gerada - continuando com chave em memória",
                    path=key_path,
                    error=str(e)
                )
        else:
            # Path padrão para desenvolvimento
            default_path = '/tmp/neural_hive_encryption.key'
            try:
                self._save_key(key, default_path)
                logger.warning(
                    "Chave gerada automaticamente e salva em path temporário",
                    path=default_path,
                    warning="NÃO recomendado para produção - configure ENCRYPTION_KEY_PATH"
                )
            except Exception as e:
                logger.warning(
                    "Falha ao salvar chave em path temporário - continuando com chave em memória",
                    error=str(e)
                )

        return key

    @staticmethod
    def _save_key(key: bytes, path: str) -> None:
        """
        Salva chave em arquivo com permissões restritas.

        Args:
            key: Chave Fernet
            path: Caminho do arquivo
        """
        # Criar diretório se não existe
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)

        # Salvar chave
        with open(path, 'wb') as f:
            f.write(key)

        # Definir permissões 0600 (apenas owner pode ler/escrever)
        try:
            os.chmod(path, 0o600)
        except Exception as e:
            logger.warning(
                "Falha ao definir permissões do arquivo de chave",
                path=path,
                error=str(e)
            )

        logger.info("Chave de criptografia salva", path=path)
