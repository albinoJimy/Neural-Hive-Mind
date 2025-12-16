"""
DigitalSigner: Assinatura digital de documentos do ledger.

Implementa assinatura RSA-SHA256 para garantir autenticidade e
integridade dos documentos, além do hash SHA-256 existente.
"""

import json
import hashlib
from typing import Dict, Any, Optional, Tuple
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.backends import default_backend
import base64
import structlog

logger = structlog.get_logger(__name__)


class DigitalSigner:
    """Gerencia assinatura digital de documentos do ledger."""

    def __init__(self, config: Dict[str, Any]):
        """
        Inicializa assinador digital.

        Args:
            config: Configuração com private_key_path, public_key_path
        """
        self.config = config
        self.private_key: Optional[rsa.RSAPrivateKey] = None
        self.public_key: Optional[rsa.RSAPublicKey] = None

        self._load_keys()

        logger.info(
            "DigitalSigner initialized",
            has_private_key=self.private_key is not None,
            has_public_key=self.public_key is not None
        )

    def _load_keys(self):
        """Carrega chaves privada e pública."""
        private_key_path = self.config.get('private_key_path')
        public_key_path = self.config.get('public_key_path')

        # Carregar chave privada
        if private_key_path:
            try:
                with open(private_key_path, 'rb') as key_file:
                    self.private_key = serialization.load_pem_private_key(
                        key_file.read(),
                        password=None,
                        backend=default_backend()
                    )
                logger.info("Private key loaded", path=private_key_path)
            except Exception as e:
                logger.error("Failed to load private key", path=private_key_path, error=str(e))
                self.private_key = None

        # Carregar chave pública
        if public_key_path:
            try:
                with open(public_key_path, 'rb') as key_file:
                    self.public_key = serialization.load_pem_public_key(
                        key_file.read(),
                        backend=default_backend()
                    )
                logger.info("Public key loaded", path=public_key_path)
            except Exception as e:
                logger.error("Failed to load public key", path=public_key_path, error=str(e))
                self.public_key = None

    def generate_keys(self, key_size: int = 2048) -> Tuple[bytes, bytes]:
        """
        Gera par de chaves RSA.

        Args:
            key_size: Tamanho da chave em bits (2048 ou 4096)

        Returns:
            Tupla (private_key_pem, public_key_pem)
        """
        logger.info("Generating RSA key pair", key_size=key_size)

        # Gerar chave privada
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=key_size,
            backend=default_backend()
        )

        # Serializar chave privada
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )

        # Obter chave pública
        public_key = private_key.public_key()

        # Serializar chave pública
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

        self.private_key = private_key
        self.public_key = public_key

        logger.info("RSA key pair generated successfully")

        return private_pem, public_pem

    def compute_content_hash(self, document: Dict[str, Any]) -> str:
        """
        Computa hash SHA-256 do conteúdo do documento.

        Args:
            document: Documento a hashear

        Returns:
            Hash SHA-256 em hexadecimal
        """
        # Criar string determinística do documento (sem campos de segurança)
        content = {k: v for k, v in document.items()
                   if k not in ['content_hash', 'digital_signature', 'signature_algorithm', '_id']}

        content_str = json.dumps(content, sort_keys=True, default=str)
        content_hash = hashlib.sha256(content_str.encode('utf-8')).hexdigest()

        return content_hash

    def sign_document(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """
        Assina documento digitalmente.

        Args:
            document: Documento a assinar

        Returns:
            Documento com assinatura digital adicionada
        """
        if self.private_key is None:
            logger.warning("No private key available for signing")
            return document

        try:
            # Computar hash do conteúdo
            content_hash = self.compute_content_hash(document)
            document['content_hash'] = content_hash

            # Assinar hash
            signature = self.private_key.sign(
                content_hash.encode('utf-8'),
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )

            # Converter para base64
            signature_b64 = base64.b64encode(signature).decode('utf-8')

            # Adicionar assinatura ao documento
            document['digital_signature'] = signature_b64
            document['signature_algorithm'] = 'RSA-SHA256-PSS'

            logger.debug(
                "Document signed",
                opinion_id=document.get('opinion_id'),
                hash=content_hash[:16] + "..."
            )

            return document

        except Exception as e:
            logger.error("Failed to sign document", error=str(e), exc_info=True)
            return document

    def verify_signature(self, document: Dict[str, Any]) -> bool:
        """
        Verifica assinatura digital do documento.

        Args:
            document: Documento a verificar

        Returns:
            True se assinatura válida, False caso contrário
        """
        if self.public_key is None:
            logger.warning("No public key available for verification")
            return False

        if 'digital_signature' not in document:
            logger.warning("Document has no digital signature")
            return False

        try:
            # Recomputar hash
            expected_hash = self.compute_content_hash(document)

            # Obter assinatura
            signature_b64 = document['digital_signature']
            signature = base64.b64decode(signature_b64)

            # Verificar assinatura
            self.public_key.verify(
                signature,
                expected_hash.encode('utf-8'),
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )

            logger.debug(
                "Signature verified successfully",
                opinion_id=document.get('opinion_id')
            )

            return True

        except Exception as e:
            logger.error(
                "Signature verification failed",
                opinion_id=document.get('opinion_id'),
                error=str(e)
            )
            return False

    def detect_tampering(self, document: Dict[str, Any]) -> bool:
        """
        Detecta se documento foi adulterado.

        Args:
            document: Documento a verificar

        Returns:
            True se adulteração detectada, False se íntegro
        """
        if 'content_hash' not in document:
            logger.warning("Document has no content hash")
            return True

        # Recomputar hash
        current_hash = self.compute_content_hash(document)
        stored_hash = document['content_hash']

        if current_hash != stored_hash:
            logger.warning(
                "Tampering detected: hash mismatch",
                opinion_id=document.get('opinion_id'),
                expected=stored_hash[:16],
                actual=current_hash[:16]
            )
            return True

        # Verificar assinatura se presente
        if 'digital_signature' in document:
            if not self.verify_signature(document):
                logger.warning(
                    "Tampering detected: invalid signature",
                    opinion_id=document.get('opinion_id')
                )
                return True

        return False
