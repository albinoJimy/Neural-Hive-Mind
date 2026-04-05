"""
JWT Verification Module - SEC-008

Este módulo fornece componentes para validação segura de tokens JWT-SVID
no contexto do SPIFFE/SPIRE, incluindo:

- JWKValidator: Validação de estrutura JWK (RFC 7517)
- JWTVerifier: Verificação de assinatura e claims JWT
- KeyCache: Cache de chaves públicas com TTL
- Métricas Prometheus para observabilidade

Feature Flag: ENABLE_JWT_VERIFICATION
"""

from .jwk_validator import JWKValidationError, JWKValidator
from .jwt_verifier import JWTVerificationError, JWTVerifier, VerificationResult
from .key_cache import KeyCache
from .metrics import (
    JWKValidationMetrics,
    JWTVerificationMetrics,
    get_jwk_validation_metrics,
    get_jwt_verification_metrics,
)

__all__ = [
    "JWKValidationError",
    "JWKValidationMetrics",
    "JWKValidator",
    "JWTVerificationError",
    "JWTVerificationMetrics",
    "JWTVerifier",
    "KeyCache",
    "VerificationResult",
    "get_jwk_validation_metrics",
    "get_jwt_verification_metrics",
]
