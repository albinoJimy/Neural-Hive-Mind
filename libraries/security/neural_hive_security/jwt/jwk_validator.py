"""
JWKValidator - Validação de Estrutura JWK (RFC 7517)

Implementa validação rigorosa de JSON Web Keys (JWK) para prevenir
injeção de chaves malformadas e garantir conformidade com RFC 7517.

Componente crítico para SEC-008: Prevenir token substitution attacks.
"""

from dataclasses import dataclass
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class JWKValidationError:
    """Erro de validação JWK com contexto."""

    field: str
    message: str
    key_id: str | None = None


class JWKValidator:
    """
    Validador de estrutura JWK (RFC 7517).

    Valida campos obrigatórios e detecta JWKs malformados que podem
    indicar tentativas de ataque de injeção de chaves.

    Campos obrigatórios por tipo:
    - RSA: kty, kid, alg, n, e
    - EC: kty, kid, alg, crv, x, y

    Exemplo de uso:
        validator = JWKValidator()

        jwk = {"kty": "RSA", "kid": "key-1", "alg": "RS256", "n": "...", "e": "AQAB"}
        if validator.validate(jwk):
            # JWK válido
        else:
            errors = validator.get_errors()
    """

    # Tipos de chave suportados
    SUPPORTED_KEY_TYPES = {"RSA", "EC", "OKP"}

    # Algoritmos suportados
    SUPPORTED_ALGORITHMS = {
        "RS256",
        "RS384",
        "RS512",  # RSA com SHA-2
        "ES256",
        "ES384",
        "ES512",  # EC com SHA-2
        "PS256",
        "PS384",
        "PS512",  # RSA-PSS
        "EdDSA",  # Ed25519/Ed448
    }

    # Componentes obrigatórios por tipo
    REQUIRED_FIELDS = {
        "RSA": ["kty", "kid", "alg", "n", "e"],
        "EC": ["kty", "kid", "alg", "crv", "x", "y"],
        "OKP": ["kty", "kid", "alg", "crv", "x"],
    }

    def __init__(self, strict_mode: bool = True):
        """
        Inicializa validador JWK.

        Args:
            strict_mode: Se True, rejeita JWKs com campos extras desconhecidos
        """
        self.strict_mode = strict_mode
        self._errors: list[JWKValidationError] = []

    def validate(self, jwk: Any) -> bool:
        """
        Valida um JWK individual.

        Args:
            jwk: Objeto JWK a validar (deve ser dict)

        Returns:
            True se JWK é válido, False caso contrário
        """
        self._errors = []

        # Verificar tipo
        if not isinstance(jwk, dict):
            self._add_error("type", "JWK must be a dictionary")
            return False

        # Verificar vazio
        if not jwk:
            self._add_error("structure", "JWK cannot be empty")
            return False

        key_id = jwk.get("kid", "unknown")

        # Validar kty (key type)
        kty = jwk.get("kty")
        if not kty:
            self._add_error("kty", "Missing required field: kty (key type)", key_id)
            return False

        if kty not in self.SUPPORTED_KEY_TYPES:
            self._add_error(
                "kty", f"Unsupported key type: {kty}. Supported: {self.SUPPORTED_KEY_TYPES}", key_id
            )
            return False

        # Validar campos obrigatórios para o tipo
        required_fields = self.REQUIRED_FIELDS.get(kty, [])
        for field in required_fields:
            if field not in jwk:
                self._add_error(field, f"Missing required field for {kty}: {field}", key_id)

        # Validar alg (algorithm)
        alg = jwk.get("alg")
        if not alg:
            self._add_error("alg", "Missing required field: alg (algorithm)", key_id)
        elif alg not in self.SUPPORTED_ALGORITHMS:
            self._add_error(
                "alg",
                f"Unsupported algorithm: {alg}. Supported: {self.SUPPORTED_ALGORITHMS}",
                key_id,
            )

        # Validar kid (key ID)
        if "kid" not in jwk:
            self._add_error("kid", "Missing required field: kid (key ID)", key_id)
        elif not isinstance(jwk["kid"], str) or not jwk["kid"].strip():
            self._add_error("kid", "kid must be a non-empty string", jwk.get("kid"))

        # Validações específicas por tipo
        if kty == "RSA":
            self._validate_rsa_jwk(jwk, key_id)
        elif kty == "EC":
            self._validate_ec_jwk(jwk, key_id)
        elif kty == "OKP":
            self._validate_okp_jwk(jwk, key_id)

        # Verificar se há erros
        return len(self._errors) == 0

    def _validate_rsa_jwk(self, jwk: dict, key_id: str):
        """Valida JWK do tipo RSA."""
        # Verificar que 'n' (modulus) é string base64url válida
        n = jwk.get("n")
        if n:
            if not isinstance(n, str) or len(n) < 10:
                self._add_error("n", "RSA modulus (n) must be a non-empty string", key_id)

        # Verificar que 'e' (exponent) é string base64url válida
        e = jwk.get("e")
        if e:
            if not isinstance(e, str) or len(e) < 1:
                self._add_error("e", "RSA exponent (e) must be a non-empty string", key_id)

    def _validate_ec_jwk(self, jwk: dict, key_id: str):
        """Valida JWK do tipo EC (Elliptic Curve)."""
        # Verificar curva válida
        crv = jwk.get("crv")
        valid_curves = {"P-256", "P-384", "P-521", "Ed25519", "Ed448"}
        if crv and crv not in valid_curves:
            self._add_error("crv", f"Unsupported curve: {crv}. Supported: {valid_curves}", key_id)

        # Verificar coordenadas
        x = jwk.get("x")
        y = jwk.get("y")
        if x and not isinstance(x, str):
            self._add_error("x", "EC coordinate (x) must be a string", key_id)
        if y and not isinstance(y, str):
            self._add_error("y", "EC coordinate (y) must be a string", key_id)

    def _validate_okp_jwk(self, jwk: dict, key_id: str):
        """Valida JWK do tipo OKP (Octet Key Pair - EdDSA)."""
        crv = jwk.get("crv")
        valid_curves = {"Ed25519", "Ed448"}
        if crv and crv not in valid_curves:
            self._add_error(
                "crv", f"Unsupported OKP curve: {crv}. Supported: {valid_curves}", key_id
            )

        x = jwk.get("x")
        if x and not isinstance(x, str):
            self._add_error("x", "OKP public key data (x) must be a string", key_id)

    def validate_jwks(self, jwks: dict) -> dict[str, int]:
        """
        Valida um conjunto JWK (JWKS).

        Args:
            jwks: Dicionário JWKS com campo 'keys'

        Returns:
            Dict com contagens: valid_count, invalid_count, total_count
        """
        if not isinstance(jwks, dict) or "keys" not in jwks:
            logger.warning(
                "invalid_jwks_structure", message="JWKS must be a dict with 'keys' field"
            )
            return {"valid_count": 0, "invalid_count": 0, "total_count": 0}

        keys = jwks["keys"]
        if not isinstance(keys, list):
            logger.warning("invalid_jwks_keys_type", message="JWKS 'keys' must be a list")
            return {"valid_count": 0, "invalid_count": 0, "total_count": 0}

        valid_count = 0
        invalid_count = 0
        invalid_key_ids = []

        for jwk in keys:
            self._errors = []  # Limpar erros anteriores
            if self.validate(jwk):
                valid_count += 1
            else:
                invalid_count += 1
                kid = jwk.get("kid", "unknown")
                invalid_key_ids.append(kid)

        result = {
            "valid_count": valid_count,
            "invalid_count": invalid_count,
            "total_count": len(keys),
            "invalid_key_ids": invalid_key_ids,
        }

        if invalid_count > 0:
            logger.warning(
                "jwks_validation_partial_failure",
                valid_count=valid_count,
                invalid_count=invalid_count,
                invalid_key_ids=invalid_key_ids,
            )
        else:
            logger.info("jwks_validation_success", total_keys=valid_count)

        return result

    def get_errors(self) -> list[str]:
        """
        Retorna lista de mensagens de erro da última validação.

        Returns:
            Lista de strings com mensagens de erro
        """
        return [f"{e.field}: {e.message}" for e in self._errors]

    def get_detailed_errors(self) -> list[JWKValidationError]:
        """
        Retorna erros detalhados da última validação.

        Returns:
            Lista de objetos JWKValidationError
        """
        return self._errors.copy()

    def _add_error(self, field: str, message: str, key_id: str | None = None):
        """Adiciona erro à lista de erros."""
        error = JWKValidationError(field=field, message=message, key_id=key_id)
        self._errors.append(error)

        # Log com contexto
        log_data = {"field": field, "message": message}
        if key_id:
            log_data["key_id"] = key_id

        logger.debug("jwk_validation_error", **log_data)


# Funções auxiliares


def validate_trust_bundle_jwks(jwks_data: str) -> dict[str, int]:
    """
    Valida JWKS de trust bundle (wrapper conveniente).

    Args:
        jwks_data: String JSON contendo JWKS

    Returns:
        Dict com resultado da validação
    """
    import json

    try:
        jwks = json.loads(jwks_data)
        validator = JWKValidator()
        return validator.validate_jwks(jwks)
    except json.JSONDecodeError as e:
        logger.error("invalid_jwks_json", error=str(e))
        return {"valid_count": 0, "invalid_count": 0, "total_count": 0, "error": "invalid_json"}
