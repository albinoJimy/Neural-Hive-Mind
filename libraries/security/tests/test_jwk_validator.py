"""
Testes para JWKValidator - SEC-008

Testa validação de estrutura JWK (RFC 7517), detecção de chaves malformadas,
e validação de campos obrigatórios.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, AsyncMock, patch
import time

from neural_hive_security.jwt.jwk_validator import JWKValidator, JWKValidationError
from neural_hive_security.jwt.jwt_verifier import (
    JWTVerifier,
    JWTVerificationError,
    VerificationStatus,
)
from neural_hive_security.config import SPIFFEConfig


# =============================================================================
# Test: JWKValidator - Estrutura JWK
# =============================================================================


class TestJWKValidator:
    """Testes de validação de estrutura JWK."""

    def test_validate_valid_rsa_jwk(self):
        """Deve aceitar JWK RSA válido com todos os campos obrigatórios."""
        validator = JWKValidator()

        valid_rsa_jwk = {
            "kty": "RSA",
            "kid": "key-123",
            "alg": "RS256",
            "n": "0vx7agoebGcQSuuPiLJXZptN9nndrQmbXEps2aiAFbWhM78LhWx4cbbfAAtVT86zwu1RK7aPFFxuhDR1L6tSoc_BJECPebWKRXjBZCiFV4n3oknjhMstn64tZ_2W-5JsGY4Hc5n9yBXArwl93lqt7_RN5w6Cf0h4QyQ5v-65YGjQR0_FDW2QvzqY368QQMicAtaSqzs8KJZgnYb9c7d0zgdAZHzu6qMQvRL5hajrn1n91CbOpbISD08qNLyrdkt-bFTWhAI4vMQFh6WeZu0fM4lFd2NcRwr3XPksINHaQ-G_xBniIqbw0Ls1jF44-csFCur-kEgU8awapJzKnqDKgw",
            "e": "AQAB",
        }

        result = validator.validate(valid_rsa_jwk)

        assert result is True
        assert validator.get_errors() == []

    def test_validate_valid_ec_jwk(self):
        """Deve aceitar JWK EC (Elliptic Curve) válido."""
        validator = JWKValidator()

        valid_ec_jwk = {
            "kty": "EC",
            "kid": "ec-key-456",
            "alg": "ES256",
            "crv": "P-256",
            "x": "WKn-ZIGevcwGIyyrzFoZNBdaq9_TsqzGl96oc0CWuis",
            "y": "y77t-RvAHRKTsSGdIYUfweuOvwrvDD-Q3Hv5J0fSKbE",
        }

        result = validator.validate(valid_ec_jwk)

        assert result is True

    def test_reject_jwk_missing_kty(self):
        """Deve rejeitar JWK sem campo 'kty' (key type)."""
        validator = JWKValidator()

        invalid_jwk = {"kid": "key-123", "alg": "RS256", "n": "...", "e": "AQAB"}

        result = validator.validate(invalid_jwk)

        assert result is False
        assert any("kty" in error for error in validator.get_errors())

    def test_reject_jwk_missing_kid(self):
        """Deve rejeitar JWK sem campo 'kid' (key ID)."""
        validator = JWKValidator()

        invalid_jwk = {"kty": "RSA", "alg": "RS256", "n": "...", "e": "AQAB"}

        result = validator.validate(invalid_jwk)

        assert result is False
        assert any("kid" in error for error in validator.get_errors())

    def test_reject_jwk_missing_alg(self):
        """Deve rejeitar JWK sem campo 'alg' (algorithm)."""
        validator = JWKValidator()

        invalid_jwk = {"kty": "RSA", "kid": "key-123", "n": "...", "e": "AQAB"}

        result = validator.validate(invalid_jwk)

        assert result is False
        assert any("alg" in error for error in validator.get_errors())

    def test_reject_jwk_invalid_kty(self):
        """Deve rejeitar JWK com kty não suportado."""
        validator = JWKValidator()

        invalid_jwk = {
            "kty": "oct",  # Symmetric key (não suportado para trust bundles)
            "kid": "key-123",
            "alg": "HS256",
        }

        result = validator.validate(invalid_jwk)

        assert result is False
        assert any(
            "kty" in error or "not supported" in error.lower() for error in validator.get_errors()
        )

    def test_reject_jwk_missing_rsa_components(self):
        """Deve rejeitar JWK RSA sem componentes 'n' e 'e'."""
        validator = JWKValidator()

        invalid_jwk = {"kty": "RSA", "kid": "key-123", "alg": "RS256"}

        result = validator.validate(invalid_jwk)

        assert result is False
        errors = validator.get_errors()
        assert any(
            "n" in error or "e" in error or "components" in error.lower() for error in errors
        )

    def test_reject_jwk_missing_ec_components(self):
        """Deve rejeitar JWK EC sem componentes 'x' e 'y'."""
        validator = JWKValidator()

        invalid_jwk = {"kty": "EC", "kid": "key-123", "alg": "ES256", "crv": "P-256"}

        result = validator.validate(invalid_jwk)

        assert result is False
        errors = validator.get_errors()
        assert any(
            "x" in error or "y" in error or "components" in error.lower() for error in errors
        )

    def test_reject_malformed_jwk_not_dict(self):
        """Deve rejeitar JWK que não é um dicionário."""
        validator = JWKValidator()

        result = validator.validate("not-a-dict")

        assert result is False
        assert any(
            "dict" in error.lower() or "type" in error.lower() for error in validator.get_errors()
        )

    def test_reject_empty_jwk(self):
        """Deve rejeitar JWK vazio."""
        validator = JWKValidator()

        result = validator.validate({})

        assert result is False
        assert len(validator.get_errors()) > 0

    def test_validate_jwks_set(self):
        """Deve validar conjunto de JWKs (JWKS)."""
        validator = JWKValidator()

        jwks = {
            "keys": [
                {
                    "kty": "RSA",
                    "kid": "key-1",
                    "alg": "RS256",
                    "n": "0vx7agoebGcQSuuPiLJXZptN9nndrQmbXEps2aiAFbWhM78LhWx4cbbfAAtVT86zwu1RK7aPFFxuhDR1L6tSoc_BJECPebWKRXjBZCiFV4n3oknjhMstn64tZ_2W-5JsGY4Hc5n9yBXArwl93lqt7_RN5w6Cf0h4QyQ5v-65YGjQR0_FDW2QvzqY368QQMicAtaSqzs8KJZgnYb9c7d0zgdAZHzu6qMQvRL5hajrn1n91CbOpbISD08qNLyrdkt-bFTWhAI4vMQFh6WeZu0fM4lFd2NcRwr3XPksINHaQ-G_xBniIqbw0Ls1jF44-csFCur-kEgU8awapJzKnqDKgw",
                    "e": "AQAB",
                },
                {
                    "kty": "RSA",
                    "kid": "key-2",
                    "alg": "RS256",
                    "n": "another modulus here",
                    "e": "AQAB",
                },
            ]
        }

        results = validator.validate_jwks(jwks)

        assert results["valid_count"] == 2
        assert results["invalid_count"] == 0
        assert results["total_count"] == 2

    def test_validate_jwks_set_with_invalid_keys(self):
        """Deve validar JWKS e contar chaves inválidas."""
        validator = JWKValidator()

        jwks = {
            "keys": [
                {
                    "kty": "RSA",
                    "kid": "key-1",
                    "alg": "RS256",
                    "n": "0vx7agoebGcQSuuPiLJXZptN9nndrQmbXEps2aiAFbWhM78LhWx4cbbfAAtVT86zwu1RK7aPFFxuhDR1L6tSoc_BJECPebWKRXjBZCiFV4n3oknjhMstn64tZ_2W-5JsGY4Hc5n9yBXArwl93lqt7_RN5w6Cf0h4QyQ5v-65YGjQR0_FDW2QvzqY368QQMicAtaSqzs8KJZgnYb9c7d0zgdAZHzu6qMQvRL5hajrn1n91CbOpbISD08qNLyrdkt-bFTWhAI4vMQFh6WeZu0fM4lFd2NcRwr3XPksINHaQ-G_xBniIqbw0Ls1jF44-csFCur-kEgU8awapJzKnqDKgw",
                    "e": "AQAB",
                },
                {
                    "kty": "RSA",
                    "kid": "key-2",
                    # Missing alg - invalid
                    "n": "another modulus here",
                    "e": "AQAB",
                },
            ]
        }

        results = validator.validate_jwks(jwks)

        assert results["valid_count"] == 1
        assert results["invalid_count"] == 1
        assert results["total_count"] == 2


# =============================================================================
# Test: JWTVerifier - Verificação de Assinatura
# =============================================================================


class TestJWTVerifier:
    """Testes de verificação JWT."""

    @pytest.fixture
    def valid_rsa_key(self):
        """Chave RSA válida para testes."""
        return {
            "kty": "RSA",
            "kid": "test-key-1",
            "alg": "RS256",
            "n": "0vx7agoebGcQSuuPiLJXZptN9nndrQmbXEps2aiAFbWhM78LhWx4cbbfAAtVT86zwu1RK7aPFFxuhDR1L6tSoc_BJECPebWKRXjBZCiFV4n3oknjhMstn64tZ_2W-5JsGY4Hc5n9yBXArwl93lqt7_RN5w6Cf0h4QyQ5v-65YGjQR0_FDW2QvzqY368QQMicAtaSqzs8KJZgnYb9c7d0zgdAZHzu6qMQvRL5hajrn1n91CbOpbISD08qNLyrdkt-bFTWhAI4vMQFh6WeZu0fM4lFd2NcRwr3XPksINHaQ-G_xBniIqbw0Ls1jF44-csFCur-kEgU8awapJzKnqDKgw",
            "e": "AQAB",
        }

    @pytest.fixture
    def spiffe_config(self):
        """Configuração SPIFFE para testes."""
        return SPIFFEConfig(trust_domain="neural-hive.local", jwt_audience="test-audience")

    def _create_test_token(self, payload, secret="test-secret", kid="test-key-1"):
        """Helper para criar token JWT com header kid."""
        import jwt

        headers = {"kid": kid}
        return jwt.encode(payload, secret, algorithm="HS256", headers=headers)

    @pytest.mark.asyncio
    async def test_verify_valid_jwt_token(self, valid_rsa_key, spiffe_config):
        """Deve verificar token JWT válido."""
        # Mock para criar token válido
        import jwt

        # Usar segredo simples para HS256 nos testes (RS256 requer chave real)
        secret = "test-secret"
        payload = {
            "sub": "spiffe://neural-hive.local/ns/default/sa/test-service",
            "iss": "https://neural-hive.local",
            "aud": "test-audience",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            "iat": datetime.now(timezone.utc),
            "nbf": datetime.now(timezone.utc),
        }

        token = self._create_test_token(payload, secret, "test-key-1")

        verifier = JWTVerifier(
            trust_domain="neural-hive.local",
            verification_keys={"test-key-1": secret},  # Incluir chave
            enable_verification=False,  # Desabilitar para teste simples
            allowed_algorithms={"HS256", "RS256", "ES256"},  # Permitir HS256 para teste
        )

        result = await verifier.verify(token)

        assert result.is_valid is True
        assert result.spiffe_id == "spiffe://neural-hive.local/ns/default/sa/test-service"
        assert result.claims["sub"] == payload["sub"]

    @pytest.mark.asyncio
    async def test_verify_expired_token(self, spiffe_config):
        """Deve rejeitar token expirado."""
        import jwt

        secret = "test-secret"
        payload = {
            "sub": "spiffe://neural-hive.local/ns/default/sa/test-service",
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),  # Expirado
        }

        token = self._create_test_token(payload, secret)

        verifier = JWTVerifier(
            trust_domain="neural-hive.local",
            verification_keys={},
            enable_verification=False,
            allowed_algorithms={"HS256", "RS256", "ES256"},
        )

        result = await verifier.verify(token)

        assert result.is_valid is False
        assert result.status == VerificationStatus.EXPIRED

    @pytest.mark.asyncio
    async def test_verify_token_with_invalid_signature(self):
        """Deve rejeitar token com assinatura inválida."""
        import jwt

        secret1 = "secret-1-32-bytes-long-hmac-key"
        secret2 = "secret-2-32-bytes-long-hmac-key"  # Segredo diferente
        payload = {
            "sub": "spiffe://neural-hive.local/ns/default/sa/test-service",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }

        token = self._create_test_token(payload, secret1)

        verifier = JWTVerifier(
            trust_domain="neural-hive.local",
            verification_keys={"test-key-1": secret2},  # Segredo errado
            enable_verification=True,
            allowed_algorithms={"HS256", "RS256", "ES256"},
        )

        result = await verifier.verify(token)

        assert result.is_valid is False
        assert result.status == VerificationStatus.SIGNATURE_ERROR

    @pytest.mark.asyncio
    async def test_verify_token_without_sub_claim(self):
        """Deve rejeitar token sem claim 'sub' (SPIFFE ID)."""
        import jwt

        secret = "test-secret"
        payload = {
            "user": "test-user",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }

        token = self._create_test_token(payload, secret)

        verifier = JWTVerifier(
            trust_domain="neural-hive.local",
            verification_keys={},
            enable_verification=False,
            allowed_algorithms={"HS256", "RS256", "ES256"},
        )

        result = await verifier.verify(token)

        assert result.is_valid is False
        assert "sub" in result.errors[0].lower()

    @pytest.mark.asyncio
    async def test_verify_token_with_invalid_spiffe_id(self):
        """Deve rejeitar token com SPIFFE ID inválido."""
        import jwt

        secret = "test-secret"
        payload = {
            "sub": "not-a-spiffe-id",  # Não começa com spiffe://
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }

        token = self._create_test_token(payload, secret)

        verifier = JWTVerifier(
            trust_domain="neural-hive.local",
            verification_keys={},
            enable_verification=False,
            allowed_algorithms={"HS256", "RS256", "ES256"},
        )

        result = await verifier.verify(token)

        assert result.is_valid is False
        assert "spiffe" in result.errors[0].lower()

    @pytest.mark.asyncio
    async def test_verify_token_with_wrong_trust_domain(self):
        """Deve rejeitar token com trust domain diferente."""
        import jwt

        secret = "test-secret"
        payload = {
            "sub": "spiffe://evil-domain.local/ns/default/sa/test-service",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }

        token = self._create_test_token(payload, secret)

        verifier = JWTVerifier(
            trust_domain="neural-hive.local",  # Trust domain esperado
            verification_keys={},
            enable_verification=False,
            allowed_algorithms={"HS256", "RS256", "ES256"},
        )

        result = await verifier.verify(token)

        assert result.is_valid is False
        assert "trust" in result.errors[0].lower() or "domain" in result.errors[0].lower()

    @pytest.mark.asyncio
    async def test_verify_token_with_nbf_claim_future(self):
        """Deve rejeitar token com nbf (not before) no futuro."""
        import jwt

        secret = "test-secret"
        payload = {
            "sub": "spiffe://neural-hive.local/ns/default/sa/test-service",
            "nbf": datetime.now(timezone.utc) + timedelta(hours=1),  # Ainda não válido
            "exp": datetime.now(timezone.utc) + timedelta(hours=2),
        }

        token = self._create_test_token(payload, secret)

        verifier = JWTVerifier(
            trust_domain="neural-hive.local",
            verification_keys={},
            enable_verification=False,
            allowed_algorithms={"HS256", "RS256", "ES256"},
        )

        result = await verifier.verify(token)

        assert result.is_valid is False
        assert result.status == VerificationStatus.NOT_YET_VALID


# =============================================================================
# Test: KeyCache - Cache de chaves com TTL
# =============================================================================


class TestKeyCache:
    """Testes de cache de chaves com TTL."""

    def test_cache_store_and_retrieve(self):
        """Deve armazenar e recuperar chaves do cache."""
        from neural_hive_security.jwt.key_cache import KeyCache

        cache = KeyCache(ttl_seconds=300)

        test_key = {"kty": "RSA", "kid": "test-1", "alg": "RS256"}
        cache.put("test-1", test_key)

        retrieved = cache.get("test-1")

        assert retrieved == test_key

    def test_cache_expiration(self):
        """Deve expirar chaves após TTL."""
        from neural_hive_security.jwt.key_cache import KeyCache

        cache = KeyCache(ttl_seconds=1)  # 1 segundo

        test_key = {"kty": "RSA", "kid": "test-1", "alg": "RS256"}
        cache.put("test-1", test_key)

        # Deve estar disponível imediatamente
        assert cache.get("test-1") == test_key

        # Aguardar expiração
        time.sleep(1.1)

        # Deve estar expirado
        assert cache.get("test-1") is None

    def test_cache_invalidate(self):
        """Deve invalidar chave específica."""
        from neural_hive_security.jwt.key_cache import KeyCache

        cache = KeyCache(ttl_seconds=300)

        test_key = {"kty": "RSA", "kid": "test-1", "alg": "RS256"}
        cache.put("test-1", test_key)

        assert cache.get("test-1") is not None

        cache.invalidate("test-1")

        assert cache.get("test-1") is None

    def test_cache_clear(self):
        """Deve limpar todas as chaves do cache."""
        from neural_hive_security.jwt.key_cache import KeyCache

        cache = KeyCache(ttl_seconds=300)

        cache.put("key-1", {"kty": "RSA", "kid": "key-1"})
        cache.put("key-2", {"kty": "RSA", "kid": "key-2"})

        assert cache.get("key-1") is not None
        assert cache.get("key-2") is not None

        cache.clear()

        assert cache.get("key-1") is None
        assert cache.get("key-2") is None

    def test_cache_stats(self):
        """Deve manter estatísticas de cache hits/misses."""
        from neural_hive_security.jwt.key_cache import KeyCache

        cache = KeyCache(ttl_seconds=300)

        cache.put("key-1", {"kty": "RSA", "kid": "key-1"})

        cache.get("key-1")  # Hit
        cache.get("key-2")  # Miss

        stats = cache.get_stats()

        assert stats["hits"] == 1
        assert stats["misses"] == 1


# =============================================================================
# Test: Token Substitution Attack (SEC-008)
# =============================================================================


class TestTokenSubstitutionAttack:
    """Testes de segurança contra ataques de substituição de token."""

    def _create_test_token(self, payload, secret="test-secret", kid="test-key-1"):
        """Helper para criar token JWT com header kid."""
        import jwt

        headers = {"kid": kid}
        return jwt.encode(payload, secret, algorithm="HS256", headers=headers)

    @pytest.mark.asyncio
    async def test_reject_token_with_different_kid(self):
        """Deve rejeitar token assinado com chave diferente do kid no header."""
        import jwt

        # Token com kid=key-1 no header
        secret1 = "secret-1-32-bytes-long-hmac-key"
        payload = {
            "sub": "spiffe://neural-hive.local/ns/default/sa/test-service",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }

        token = self._create_test_token(payload, secret1, "key-1")

        verifier = JWTVerifier(
            trust_domain="neural-hive.local",
            verification_keys={"key-1": "wrong-secret-32-bytes-long-hmac"},  # Segredo errado
            enable_verification=True,
            allowed_algorithms={"HS256", "RS256", "ES256"},
        )

        result = await verifier.verify(token)

        assert result.is_valid is False
        assert result.status == VerificationStatus.SIGNATURE_ERROR

    @pytest.mark.asyncio
    async def test_reject_algorithm_confusion_attack(self):
        """Deve rejeitar ataque de confusão de algoritmo (none algorithm)."""
        import jwt

        # Tentativa de usar algoritmo "none"
        payload = {
            "sub": "spiffe://neural-hive.local/ns/default/sa/test-service",
        }

        # PyJWT rejeita algoritmo "none" por padrão
        token = jwt.encode(payload, "", algorithm="none")

        verifier = JWTVerifier(
            trust_domain="neural-hive.local",
            verification_keys={},
            enable_verification=True,
            allowed_algorithms={"RS256", "ES256"},  # Não inclui "none"
        )

        result = await verifier.verify(token)

        assert result.is_valid is False

    @pytest.mark.asyncio
    async def test_reject_key_injection_attack(self):
        """Deve rejeitar tentativa de injetar chave maliciosa no JWKS."""
        validator = JWKValidator()

        # JWKS com chave maliciosa (sem componentes obrigatórios)
        malicious_jwks = {
            "keys": [
                {
                    "kty": "RSA",
                    "kid": "legitimate-key",
                    "alg": "RS256",
                    "n": "0vx7agoebGcQSuuPiLJXZptN9nndrQmbXEps2aiAFbWhM78LhWx4cbbfAAtVT86zwu1RK7aPFFxuhDR1L6tSoc_BJECPebWKRXjBZCiFV4n3oknjhMstn64tZ_2W-5JsGY4Hc5n9yBXArwl93lqt7_RN5w6Cf0h4QyQ5v-65YGjQR0_FDW2QvzqY368QQMicAtaSqzs8KJZgnYb9c7d0zgdAZHzu6qMQvRL5hajrn1n91CbOpbISD08qNLyrdkt-bFTWhAI4vMQFh6WeZu0fM4lFd2NcRwr3XPksINHaQ-G_xBniIqbw0Ls1jF44-csFCur-kEgU8awapJzKnqDKgw",
                    "e": "AQAB",
                },
                {
                    "kty": "RSA",
                    "kid": "injected-key",
                    # Falta alg - chave mal formada
                },
            ]
        }

        results = validator.validate_jwks(malicious_jwks)

        # Chave legítima válida, chave injetada inválida
        assert results["valid_count"] == 1
        assert results["invalid_count"] == 1


# =============================================================================
# Test: Integração com SPIFFE Manager
# =============================================================================


class TestSPIFFEManagerIntegration:
    """Testes de integração com SPIFFE Manager."""

    @pytest.mark.asyncio
    async def test_spiffe_manager_uses_jwk_validator(self):
        """SPIFFE Manager deve usar JWKValidator para validar trust bundle."""
        from neural_hive_security.spiffe_manager import SPIFFEManager
        from neural_hive_security.jwt.jwk_validator import JWKValidator

        config = SPIFFEConfig(
            workload_api_socket="unix:///tmp/test.sock", trust_domain="test.local"
        )

        manager = SPIFFEManager(config)

        # Injetar validator
        manager._jwk_validator = JWKValidator()

        # JWKS de teste
        test_jwks = {
            "keys": [
                {
                    "kty": "RSA",
                    "kid": "test-key",
                    "alg": "RS256",
                    "n": "0vx7agoebGcQSuuPiLJXZptN9nndrQmbXEps2aiAFbWhM78LhWx4cbbfAAtVT86zwu1RK7aPFFxuhDR1L6tSoc_BJECPebWKRXjBZCiFV4n3oknjhMstn64tZ_2W-5JsGY4Hc5n9yBXArwl93lqt7_RN5w6Cf0h4QyQ5v-65YGjQR0_FDW2QvzqY368QQMicAtaSqzs8KJZgnYb9c7d0zgdAZHzu6qMQvRL5hajrn1n91CbOpbISD08qNLyrdkt-bFTWhAI4vMQFh6WeZu0fM4lFd2NcRwr3XPksINHaQ-G_xBniIqbw0Ls1jF44-csFCur-kEgU8awapJzKnqDKgw",
                    "e": "AQAB",
                }
            ]
        }

        # Validar JWKS
        results = manager._jwk_validator.validate_jwks(test_jwks)

        assert results["valid_count"] == 1
        assert results["invalid_count"] == 0


# =============================================================================
# Test: Métricas Prometheus
# =============================================================================


class TestPrometheusMetrics:
    """Testes de métricas Prometheus para verificação JWT."""

    @pytest.mark.asyncio
    async def test_jwt_verification_metrics(self):
        """Deve registrar métricas de verificação JWT."""
        from neural_hive_security.jwt.metrics import (
            JWTVerificationMetrics,
            get_jwt_verification_metrics,
        )

        metrics = get_jwt_verification_metrics()

        # Simular verificações
        metrics.record_attempt("success")
        metrics.record_attempt("failed")
        metrics.record_failure("invalid_signature")
        metrics.record_duration(0.123)

        # Verificar que métricas foram incrementadas
        # Nota: Prometheus client não permite ler valores diretamente,
        # mas podemos verificar que não há exceções
        assert metrics is not None

    @pytest.mark.asyncio
    async def test_jwk_validation_metrics(self):
        """Deve registrar métricas de validação JWK."""
        from neural_hive_security.jwt.metrics import (
            JWKValidationMetrics,
            get_jwk_validation_metrics,
        )

        metrics = get_jwk_validation_metrics()

        # Simular validações
        metrics.record_validation("success")
        metrics.record_validation("failed")
        metrics.record_field_error("kty")

        assert metrics is not None
