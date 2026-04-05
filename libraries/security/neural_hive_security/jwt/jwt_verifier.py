"""
JWTVerifier - Verificação de Assinatura e Claims JWT

Implementa verificação segura de tokens JWT-SVID SPIFFE com:
- Validação de assinatura usando PyJWT/python-jose
- Validação de claims padrão (iss, exp, nbf, aud)
- Extração de SPIFFE ID do claim sub
- Proteção contra ataques (algorithm confusion, token substitution)

Componente crítico para SEC-008: Validar trust bundle JWT.
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

# Tentar importar PyJWT
try:
    import jwt

    JWT_AVAILABLE = True
except ImportError:
    JWT_AVAILABLE = False
    jwt = None

# Tentar importar python-jose para JWK
try:
    from jose import jwk as jose_jwk
    from jose.exceptions import JWKError, JWTError as JoseJWTError

    JOSE_AVAILABLE = True
except ImportError:
    JOSE_AVAILABLE = False
    jose_jwk = None
    JoseJWTError = None


logger = structlog.get_logger(__name__)


class JWTVerificationError(Exception):
    """Erro na verificação JWT."""

    def __init__(self, message: str, errors: list[str] | None = None):
        super().__init__(message)
        self.errors = errors or []


class VerificationStatus(Enum):
    """Status da verificação JWT."""

    VALID = "valid"
    INVALID = "invalid"
    EXPIRED = "expired"
    NOT_YET_VALID = "not_yet_valid"
    SIGNATURE_ERROR = "signature_error"
    MISSING_CLAIM = "missing_claim"
    INVALID_SPIFFE_ID = "invalid_spiffe_id"
    TRUST_DOMAIN_MISMATCH = "trust_domain_mismatch"


@dataclass
class VerificationResult:
    """Resultado da verificação JWT."""

    is_valid: bool
    status: VerificationStatus
    spiffe_id: str | None = None
    claims: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    verification_duration_ms: float = 0.0

    def __bool__(self) -> bool:
        """Retorna True se verificação foi bem-sucedida."""
        return self.is_valid


class JWTVerifier:
    """
    Verificador de tokens JWT-SVID SPIFFE.

    Funcionalidades:
    - Verificação de assinatura com chaves públicas (JWK)
    - Validação de claims: iss, sub, exp, nbf, aud
    - Extração e validação de SPIFFE ID
    - Proteção contra algorithm confusion attacks
    - Proteção contra token substitution attacks

    Exemplo de uso:
        verifier = JWTVerifier(
            trust_domain="neural-hive.local",
            verification_keys={"key-1": jwk_data},
            enable_verification=True
        )

        result = await verifier.verify(token)
        if result.is_valid:
            spiffe_id = result.spiffe_id
    """

    # Algoritmos permitidos (exclui "none")
    DEFAULT_ALLOWED_ALGORITHMS: set[str] = {
        "RS256",
        "RS384",
        "RS512",
        "ES256",
        "ES384",
        "ES512",
        "PS256",
        "PS384",
        "PS512",
        "EdDSA",
    }

    # Clock skew permitido para exp/nbf (segundos)
    DEFAULT_CLOCK_SKEW_SECONDS = 30

    def __init__(
        self,
        trust_domain: str,
        verification_keys: dict[str, Any],
        enable_verification: bool = True,
        allowed_algorithms: set[str] | None = None,
        clock_skew_seconds: int = DEFAULT_CLOCK_SKEW_SECONDS,
        require_audience: bool = False,
        expected_audience: str | None = None,
    ):
        """
        Inicializa verificador JWT.

        Args:
            trust_domain: Trust domain SPIFFE esperado
            verification_keys: Dict de kid -> JWK key data
            enable_verification: Se True, verifica assinatura; se False, apenas decodifica
            allowed_algorithms: Conjunto de algoritmos permitidos
            clock_skew_seconds: Skew de relógio permitido (padrão: 30s)
            require_audience: Se True, requer claim aud
            expected_audience: Audience esperada no claim aud
        """
        self.trust_domain = trust_domain
        self.verification_keys = verification_keys
        self.enable_verification = enable_verification
        self.allowed_algorithms = allowed_algorithms or self.DEFAULT_ALLOWED_ALGORITHMS
        self.clock_skew_seconds = clock_skew_seconds
        self.require_audience = require_audience
        self.expected_audience = expected_audience

        # Converter JWKs para chaves PyJWT se disponível
        self._public_keys: dict[str, Any] = {}
        if JWT_AVAILABLE:
            self._convert_jwks_to_public_keys()

        logger.info(
            "jwt_verifier_initialized",
            trust_domain=trust_domain,
            keys_count=len(verification_keys),
            enable_verification=enable_verification,
            allowed_algorithms=list(self.allowed_algorithms),
        )

    def _convert_jwks_to_public_keys(self):
        """Converte JWKs para chaves públicas PyJWT."""
        if not JOSE_AVAILABLE:
            logger.warning(
                "jose_unavailable", message="python-jose not available, JWK conversion limited"
            )
            return

        for kid, jwk_data in self.verification_keys.items():
            try:
                # Usar python-jose para converter JWK para chave pública
                if isinstance(jwk_data, dict):
                    key = jose_jwk.construct(jwk_data)
                    self._public_keys[kid] = key
                    logger.debug("jwk_converted", kid=kid)
            except (JWKError, Exception) as e:
                logger.warning("jwk_conversion_failed", kid=kid, error=str(e))

    async def verify(self, token: str) -> VerificationResult:
        """
        Verifica um token JWT-SVID.

        Args:
            token: Token JWT string

        Returns:
            VerificationResult com resultado da verificação
        """
        start_time = time.time()
        errors = []

        # Verificar disponibilidade do PyJWT
        if not JWT_AVAILABLE:
            return VerificationResult(
                is_valid=False, status=VerificationStatus.INVALID, errors=["PyJWT not available"]
            )

        try:
            # Passo 1: Extrair header sem verificação para obter kid e alg
            try:
                header = jwt.get_unverified_header(token)
                kid = header.get("kid")
                alg = header.get("alg")

                if not kid:
                    errors.append("Missing kid in JWT header")
                    return VerificationResult(
                        is_valid=False, status=VerificationStatus.INVALID, errors=errors
                    )

                # Verificar algoritmo permitido
                if alg not in self.allowed_algorithms:
                    errors.append(f"Algorithm not allowed: {alg}")
                    logger.warning(
                        "algorithm_not_allowed",
                        algorithm=alg,
                        allowed=list(self.allowed_algorithms),
                        kid=kid,
                    )
                    return VerificationResult(
                        is_valid=False, status=VerificationStatus.INVALID, errors=errors
                    )

            except Exception as e:
                errors.append(f"Invalid JWT header: {e!s}")
                return VerificationResult(
                    is_valid=False, status=VerificationStatus.INVALID, errors=errors
                )

            # Passo 2: Obter chave pública para verificação
            public_key = None
            if self.enable_verification:
                # Tentar obter chave convertida
                public_key = self._public_keys.get(kid)

                # Se não encontrada, tentar usar dados JWK brutos
                if not public_key and kid in self.verification_keys:
                    jwk_data = self.verification_keys[kid]
                    if isinstance(jwk_data, str):
                        # Assume que já é chave em formato PEM/der
                        public_key = jwk_data
                    elif isinstance(jwk_data, dict):
                        # Tentar converter em tempo de execução
                        try:
                            public_key = jwt.algorithms.RSAAlgorithm.from_jwk(jwk_data)
                        except Exception as e:
                            logger.warning("runtime_jwk_conversion_failed", kid=kid, error=str(e))

                if not public_key:
                    errors.append(f"Public key not found for kid: {kid}")
                    logger.warning("public_key_not_found", kid=kid)
                    return VerificationResult(
                        is_valid=False, status=VerificationStatus.INVALID, errors=errors
                    )

            # Passo 3: Decodificar e verificar token
            decode_options = {
                "verify_signature": self.enable_verification,
                "verify_exp": True,
                "verify_nbf": True,
                "verify_iat": False,  # iat não é crítico para segurança
                "require": ["sub"],  # sub é obrigatório (SPIFFE ID)
            }

            # Adicionar verify_iss se iss estiver presente no token
            # (verificamos iss após decodificação)

            # Preparar kwargs para decode
            decode_kwargs = {
                "options": decode_options,
                "leeway": self.clock_skew_seconds,
                "algorithms": list(self.allowed_algorithms),
            }

            if self.enable_verification and public_key:
                decode_kwargs["key"] = public_key
            else:
                # Decode sem verificação (modo inseguro - apenas para dev)
                decode_kwargs["options"]["verify_signature"] = False

            if self.require_audience and self.expected_audience:
                decode_kwargs["audience"] = self.expected_audience

            # Decodificar token
            payload = jwt.decode(token, **decode_kwargs)

            # Passo 4: Validar claims padrão
            validation_errors = self._validate_claims(payload, kid)
            if validation_errors:
                errors.extend(validation_errors)
                return VerificationResult(
                    is_valid=False,
                    status=VerificationStatus.MISSING_CLAIM,
                    errors=errors,
                    claims=payload,
                )

            # Passo 5: Validar SPIFFE ID
            spiffe_id = payload.get("sub")
            spiffe_validation = self._validate_spiffe_id(spiffe_id, payload)
            if not spiffe_validation["is_valid"]:
                errors.extend(spiffe_validation["errors"])
                return VerificationResult(
                    is_valid=False,
                    status=spiffe_validation.get("status", VerificationStatus.INVALID_SPIFFE_ID),
                    errors=errors,
                    claims=payload,
                )

            # Sucesso!
            duration_ms = (time.time() - start_time) * 1000
            logger.info("jwt_verified", spiffe_id=spiffe_id, kid=kid, duration_ms=duration_ms)

            return VerificationResult(
                is_valid=True,
                status=VerificationStatus.VALID,
                spiffe_id=spiffe_id,
                claims=payload,
                verification_duration_ms=duration_ms,
            )

        except jwt.ExpiredSignatureError:
            logger.warning("jwt_expired", token_preview=token[:20])
            return VerificationResult(
                is_valid=False,
                status=VerificationStatus.EXPIRED,
                errors=["Token has expired"],
                verification_duration_ms=(time.time() - start_time) * 1000,
            )

        except jwt.ImmatureSignatureError:
            logger.warning("jwt_not_yet_valid", token_preview=token[:20])
            return VerificationResult(
                is_valid=False,
                status=VerificationStatus.NOT_YET_VALID,
                errors=["Token not yet valid (nbf claim in future)"],
                verification_duration_ms=(time.time() - start_time) * 1000,
            )

        except jwt.InvalidSignatureError:
            logger.warning("jwt_invalid_signature", token_preview=token[:20])
            return VerificationResult(
                is_valid=False,
                status=VerificationStatus.SIGNATURE_ERROR,
                errors=["Invalid signature"],
                verification_duration_ms=(time.time() - start_time) * 1000,
            )

        except jwt.InvalidTokenError as e:
            logger.warning("jwt_invalid", error=str(e), token_preview=token[:20])
            return VerificationResult(
                is_valid=False,
                status=VerificationStatus.INVALID,
                errors=[f"Invalid token: {e!s}"],
                verification_duration_ms=(time.time() - start_time) * 1000,
            )

        except Exception as e:
            logger.error("jwt_verification_error", error=str(e))
            return VerificationResult(
                is_valid=False,
                status=VerificationStatus.INVALID,
                errors=[f"Verification error: {e!s}"],
                verification_duration_ms=(time.time() - start_time) * 1000,
            )

    def _validate_claims(self, payload: dict, kid: str) -> list[str]:
        """
        Valida claims padrão do JWT.

        Args:
            payload: Payload decodificado do JWT
            kid: Key ID do token

        Returns:
            Lista de erros (vazia se válido)
        """
        errors = []

        # Validar iss (issuer) se presente
        iss = payload.get("iss")
        if iss:
            # Issuer deve começar com https://<trust_domain>
            expected_iss = f"https://{self.trust_domain}"
            if not iss.startswith(expected_iss):
                errors.append(f"Invalid issuer: {iss}. Expected: {expected_iss}")

        # Validar aud (audience) se requerido
        if self.require_audience:
            aud = payload.get("aud")
            if not aud:
                errors.append("Missing required claim: aud (audience)")
            elif self.expected_audience:
                if isinstance(aud, list):
                    if self.expected_audience not in aud:
                        errors.append(
                            f"Invalid audience: {aud}. Expected: {self.expected_audience}"
                        )
                elif aud != self.expected_audience:
                    errors.append(f"Invalid audience: {aud}. Expected: {self.expected_audience}")

        # Validar exp (já verificado pelo PyJWT, mas podemos adicionar verificação extra)
        # Validar nbf (já verificado pelo PyJWT)

        return errors

    def _validate_spiffe_id(self, spiffe_id: str | None, payload: dict) -> dict[str, Any]:
        """
        Valida SPIFFE ID do claim sub.

        Args:
            spiffe_id: Valor do claim sub
            payload: Payload completo do JWT

        Returns:
            Dict com is_valid (bool) e errors (list)
        """
        result = {"is_valid": True, "errors": []}

        if not spiffe_id:
            result["is_valid"] = False
            result["errors"].append("Missing required claim: sub (SPIFFE ID)")
            result["status"] = VerificationStatus.MISSING_CLAIM
            return result

        # Verificar formato spiffe://
        if not spiffe_id.startswith("spiffe://"):
            result["is_valid"] = False
            result["errors"].append(
                f"Invalid SPIFFE ID format: {spiffe_id}. Must start with 'spiffe://'"
            )
            result["status"] = VerificationStatus.INVALID_SPIFFE_ID
            return result

        # Verificar trust domain
        expected_prefix = f"spiffe://{self.trust_domain}"
        if not spiffe_id.startswith(expected_prefix):
            result["is_valid"] = False
            result["errors"].append(
                f"Trust domain mismatch. Expected: {expected_prefix}, Got: {spiffe_id}"
            )
            result["status"] = VerificationStatus.TRUST_DOMAIN_MISMATCH
            return result

        # SPIFFE ID válido
        return result

    def update_keys(self, new_keys: dict[str, Any]) -> None:
        """
        Atualiza chaves de verificação.

        Args:
            new_keys: Novo dict de kid -> JWK data
        """
        self.verification_keys = new_keys
        self._public_keys = {}
        if JWT_AVAILABLE:
            self._convert_jwks_to_public_keys()

        logger.info("jwt_verifier_keys_updated", keys_count=len(new_keys))

    def add_key(self, kid: str, jwk_data: Any) -> None:
        """
        Adiciona uma chave individual.

        Args:
            kid: Key ID
            jwk_data: Dados JWK
        """
        self.verification_keys[kid] = jwk_data

        # Tentar converter para chave pública
        if JWT_AVAILABLE and JOSE_AVAILABLE and isinstance(jwk_data, dict):
            try:
                key = jose_jwk.construct(jwk_data)
                self._public_keys[kid] = key
                logger.debug("key_added", kid=kid)
            except (JWKError, Exception) as e:
                logger.warning("key_addition_conversion_failed", kid=kid, error=str(e))

    def remove_key(self, kid: str) -> bool:
        """
        Remove uma chave de verificação.

        Args:
            kid: Key ID a remover

        Returns:
            True se a chave foi removida
        """
        removed = kid in self.verification_keys
        if removed:
            del self.verification_keys[kid]
            if kid in self._public_keys:
                del self._public_keys[kid]
            logger.debug("key_removed", kid=kid)
        return removed
