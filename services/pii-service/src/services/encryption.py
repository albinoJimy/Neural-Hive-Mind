"""Serviço de criptografia para unmask reversível (INV-14: AES-256-GCM)."""

import json
import os
from datetime import datetime, timedelta, timezone

import structlog
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

from src.config.settings import get_settings

logger = structlog.get_logger(__name__)


class ReversibleMaskService:
    """
    Serviço para mascaramento reversível de PII usando AES-256-GCM (INV-14).

    Implementa:
    - Criptografia AES-256-GCM para tokens de unmask
    - TTL para tokens (configurável, padrão 7 dias)
    - Limite de tentativas de unmask
    - Integração com Vault ou arquivo de chave
    """

    def __init__(self):
        """Inicializa serviço de mascaramento reversível."""
        settings = get_settings()
        self.enabled = settings.UNMASK_ENABLED
        self.token_ttl_hours = settings.UNMASK_TOKEN_TTL_HOURS
        self.max_attempts = settings.UNMASK_MAX_ATTEMPTS

        # Carregar ou gerar chave de criptografia
        self._encryption_key = self._load_or_generate_key()

        # Cache de tokens em memória (para produção, usar Redis)
        self._token_cache: dict[str, dict] = {}

        logger.info(
            "reversible_mask_service_initialized",
            enabled=self.enabled,
            token_ttl_hours=self.token_ttl_hours,
        )

    def create_mask_token(
        self, original_value: str, pii_type: str, requestor_id: str
    ) -> tuple[str, datetime]:
        """
        Cria token de mascaramento reversível (INV-14).

        Args:
            original_value: Valor original do PII
            pii_type: Tipo de PII
            requestor_id: ID do solicitante

        Returns:
            Tupla (mask_id, expires_at)
        """
        if not self.enabled:
            raise RuntimeError("Reversible masking is disabled")

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=self.token_ttl_hours)

        # Criar payload
        payload = {
            "original_value": original_value,
            "pii_type": pii_type,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "requestor_id": requestor_id,
            "attempt_count": 0,
        }

        # Serializar e criptografar
        payload_json = json.dumps(payload)
        encrypted = self._encrypt(payload_json)

        # Criar mask_id (token)
        mask_id = encrypted.decode("utf-8")

        # Armazenar no cache (para validação de tentativas)
        self._token_cache[mask_id] = payload

        # Remover tokens expirados do cache periodicamente
        self._cleanup_expired_tokens()

        logger.info(
            "mask_token_created",
            pii_type=pii_type,
            requestor_id=requestor_id,
            expires_at=expires_at.isoformat(),
        )

        return mask_id, expires_at

    def unmask(self, mask_id: str, requestor_id: str) -> tuple[str, str]:
        """
        Remove máscara de PII (INV-14).

        Args:
            mask_id: Token criptografado
            requestor_id: ID do solicitante

        Returns:
            Tupla (original_value, pii_type)

        Raises:
            PIIUnmaskError: Se token inválido, expirado ou tentativas excedidas
        """
        if not self.enabled:
            raise PIIUnmaskError("Reversible masking is disabled")

        # Tentar descriptografar
        try:
            decrypted_bytes = self._decrypt(mask_id.encode("utf-8"))
            payload = json.loads(decrypted_bytes.decode("utf-8"))
        except Exception as e:
            logger.warning("unmask_failed_invalid_token", error=str(e))
            raise PIIUnmaskError("Invalid mask token")

        # Verificar expiração
        expires_at = datetime.fromisoformat(payload["expires_at"])
        if datetime.now(timezone.utc) > expires_at:
            logger.warning("unmask_failed_token_expired")
            raise PIIUnmaskError("Mask token has expired")

        # Verificar tentativas
        attempt_count = payload.get("attempt_count", 0)
        if attempt_count >= self.max_attempts:
            logger.warning("unmask_failed_max_attempts", attempts=attempt_count)
            raise PIIUnmaskError("Maximum unmask attempts exceeded")

        # Incrementar tentativas
        payload["attempt_count"] = attempt_count + 1

        # Atualizar cache
        if mask_id in self._token_cache:
            self._token_cache[mask_id] = payload

        original_value = payload["original_value"]
        pii_type = payload["pii_type"]

        logger.info(
            "unmask_successful",
            pii_type=pii_type,
            requestor_id=requestor_id,
            attempt_count=attempt_count + 1,
        )

        return original_value, pii_type

    def validate_token(self, mask_id: str) -> dict:
        """
        Valida token de mascaramento sem fazer unmask.

        Args:
            mask_id: Token criptografado

        Returns:
            Dict com valid, expires_at, pii_types
        """
        try:
            decrypted_bytes = self._decrypt(mask_id.encode("utf-8"))
            payload = json.loads(decrypted_bytes.decode("utf-8"))

            expires_at = datetime.fromisoformat(payload["expires_at"])
            is_valid = datetime.now(timezone.utc) <= expires_at

            return {
                "valid": is_valid,
                "expires_at": expires_at,
                "pii_types": [payload.get("pii_type")],
            }
        except Exception as e:
            logger.warning("token_validation_failed", error=str(e))
            return {"valid": False, "error_message": str(e)}

    def _encrypt(self, plaintext: str) -> bytes:
        """Criptografa usando AES-256-GCM."""
        # Gerar nonce único
        nonce = os.urandom(12)

        # Criptografar
        aesgcm = AESGCM(self._encryption_key)
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)

        # Retornar nonce + ciphertext
        return nonce + ciphertext

    def _decrypt(self, ciphertext: bytes) -> bytes:
        """Descriptografa usando AES-256-GCM."""
        # Extrair nonce e ciphertext
        nonce = ciphertext[:12]
        actual_ciphertext = ciphertext[12:]

        # Descriptografar
        aesgcm = AESGCM(self._encryption_key)
        plaintext = aesgcm.decrypt(nonce, actual_ciphertext, None)

        return plaintext

    def _load_or_generate_key(self) -> bytes:
        """Carrega ou gera chave de criptografia de 32 bytes (AES-256)."""
        settings = get_settings()

        # Tentar carregar do Vault
        if settings.VAULT_ADDR and settings.VAULT_TOKEN:
            try:
                return self._load_from_vault(settings)
            except Exception as e:
                logger.warning("vault_load_failed", error=str(e))

        # Tentar carregar de arquivo
        if settings.ENCRYPTION_KEY_PATH:
            try:
                return self._load_from_file(settings.ENCRYPTION_KEY_PATH)
            except Exception as e:
                logger.warning("file_key_load_failed", error=str(e))

        # Gerar chave temporária (não recomendado para produção)
        logger.warning("using_temporary_encryption_key_not_recommended_for_production")
        return os.urandom(32)

    def _load_from_vault(self, settings) -> bytes:
        """Carrega chave do HashiCorp Vault."""
        try:
            import hvac

            client = hvac.Client(url=settings.VAULT_ADDR, token=settings.VAULT_TOKEN)

            response = client.secrets.kv.v2.read_secret_version(
                path=settings.VAULT_SECRET_PATH
            )

            key_b64 = response["data"]["data"]["key"]
            import base64

            return base64.b64decode(key_b64)
        except ImportError:
            logger.warning("hvac_not_installed")
            raise
        except Exception as e:
            logger.error("vault_key_load_error", error=str(e))
            raise

    def _load_from_file(self, path: str) -> bytes:
        """Carrega chave de arquivo."""
        if not os.path.exists(path):
            raise FileNotFoundError(f"Encryption key file not found: {path}")

        with open(path, "rb") as f:
            key = f.read()

        # Validar tamanho (32 bytes para AES-256)
        if len(key) != 32:
            # Derivar chave de 32 bytes usando PBKDF2
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=b"pii-service-salt",
                iterations=100000,
                backend=default_backend(),
            )
            key = kdf.derive(key)

        return key

    def _cleanup_expired_tokens(self):
        """Remove tokens expirados do cache."""
        now = datetime.now(timezone.utc)
        expired_keys = []

        for mask_id, payload in self._token_cache.items():
            expires_at = datetime.fromisoformat(payload["expires_at"])
            if now > expires_at:
                expired_keys.append(mask_id)

        for key in expired_keys:
            del self._token_cache[key]

        if expired_keys:
            logger.debug("cleaned_up_expired_tokens", count=len(expired_keys))


# Importar exceção no topo
from src.models.pii import PIIUnmaskError


# Singleton
_reversible_mask_service: ReversibleMaskService | None = None


def get_reversible_mask_service() -> ReversibleMaskService:
    """Retorna instância singleton do serviço."""
    global _reversible_mask_service
    if _reversible_mask_service is None:
        _reversible_mask_service = ReversibleMaskService()
    return _reversible_mask_service
