"""
Métricas Prometheus para JWT/JWK Verification

Fornece métricas para observabilidade da verificação JWT:
- Contadores de tentativas de verificação (sucesso/falha)
- Histogramas de duração da verificação
- Contadores de validação JWK

Integração com SEC-008: Observabilidade da validação de trust bundle.
"""

from functools import lru_cache

try:
    from prometheus_client import Counter, Gauge, Histogram

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    Counter = None
    Histogram = None
    Gauge = None

import structlog

logger = structlog.get_logger(__name__)


# =============================================================================
# Métricas de Verificação JWT
# =============================================================================

if PROMETHEUS_AVAILABLE:
    # Contador de tentativas de verificação
    jwt_verification_attempts_total = Counter(
        "jwt_verification_attempts_total",
        "Total de tentativas de verificação JWT",
        ["status"],  # success, failed, expired, signature_error, etc.
    )

    # Contador de falhas por motivo
    jwt_verification_failures_total = Counter(
        "jwt_verification_failures_total",
        "Total de falhas de verificação JWT",
        ["reason"],  # expired, invalid_signature, missing_claim, etc.
    )

    # Histograma de duração da verificação
    jwt_verification_duration_seconds = Histogram(
        "jwt_verification_duration_seconds",
        "Duração da verificação JWT em segundos",
        buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
    )

    # Gauge de chaves de verificação carregadas
    jwt_verification_keys_loaded = Gauge(
        "jwt_verification_keys_loaded", "Número de chaves de verificação JWT carregadas"
    )

else:
    logger.warning(
        "prometheus_unavailable", message="Prometheus client not installed, metrics disabled"
    )


class JWTVerificationMetrics:
    """
    Wrapper para métricas de verificação JWT.

    Exemplo de uso:
        metrics = get_jwt_verification_metrics()
        metrics.record_attempt("success")
        metrics.record_duration(0.123)
        metrics.record_failure("invalid_signature")
    """

    def __init__(self):
        """Inicializa wrapper de métricas."""
        self._enabled = PROMETHEUS_AVAILABLE

    def record_attempt(self, status: str) -> None:
        """
        Registra tentativa de verificação.

        Args:
            status: Status da verificação (success, failed, etc.)
        """
        if not self._enabled:
            return
        jwt_verification_attempts_total.labels(status=status).inc()

    def record_failure(self, reason: str) -> None:
        """
        Registra falha de verificação.

        Args:
            reason: Motivo da falha (expired, invalid_signature, etc.)
        """
        if not self._enabled:
            return
        jwt_verification_failures_total.labels(reason=reason).inc()
        # Também incrementar attempts com status=failed
        jwt_verification_attempts_total.labels(status="failed").inc()

    def record_success(self) -> None:
        """Registra verificação bem-sucedida."""
        if not self._enabled:
            return
        jwt_verification_attempts_total.labels(status="success").inc()

    def record_duration(self, duration_seconds: float) -> None:
        """
        Registra duração da verificação.

        Args:
            duration_seconds: Duração em segundos
        """
        if not self._enabled:
            return
        jwt_verification_duration_seconds.observe(duration_seconds)

    def set_keys_loaded(self, count: int) -> None:
        """
        Define número de chaves carregadas.

        Args:
            count: Número de chaves
        """
        if not self._enabled:
            return
        jwt_verification_keys_loaded.set(count)

    def time_verification(self):
        """
        Context manager para medir duração da verificação.

        Exemplo:
            with metrics.time_verification():
                result = await verifier.verify(token)
        """
        if not self._enabled:

            class NullTimer:
                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    pass

            return NullTimer()

        return jwt_verification_duration_seconds.time()


# =============================================================================
# Métricas de Validação JWK
# =============================================================================

if PROMETHEUS_AVAILABLE:
    # Contador de validações JWK
    jwk_validation_attempts_total = Counter(
        "jwk_validation_attempts_total",
        "Total de tentativas de validação JWK",
        ["status"],  # success, failed
    )

    # Contador de erros de validação por campo
    jwk_validation_errors_total = Counter(
        "jwk_validation_errors_total",
        "Total de erros de validação JWK",
        ["field"],  # kty, kid, alg, n, e, etc.
    )

    # Gauge de chaves no cache
    jwk_cache_size = Gauge("jwk_cache_size", "Número de chaves JWK em cache")

    # Contador de operações de cache
    jwk_cache_operations_total = Counter(
        "jwk_cache_operations_total",
        "Total de operações de cache JWK",
        ["operation"],  # hit, miss, evict, clear
    )


class JWKValidationMetrics:
    """
    Wrapper para métricas de validação JWK.

    Exemplo de uso:
        metrics = get_jwk_validation_metrics()
        metrics.record_validation("success")
        metrics.record_cache_hit()
    """

    def __init__(self):
        """Inicializa wrapper de métricas."""
        self._enabled = PROMETHEUS_AVAILABLE

    def record_validation(self, status: str) -> None:
        """
        Registra validação JWK.

        Args:
            status: Status da validação (success, failed)
        """
        if not self._enabled:
            return
        jwk_validation_attempts_total.labels(status=status).inc()

    def record_field_error(self, field: str) -> None:
        """
        Registra erro de campo específico.

        Args:
            field: Nome do campo com erro (kty, kid, alg, etc.)
        """
        if not self._enabled:
            return
        jwk_validation_errors_total.labels(field=field).inc()

    def set_cache_size(self, size: int) -> None:
        """
        Define tamanho do cache.

        Args:
            size: Número de chaves em cache
        """
        if not self._enabled:
            return
        jwk_cache_size.set(size)

    def record_cache_hit(self) -> None:
        """Registra cache hit."""
        if not self._enabled:
            return
        jwk_cache_operations_total.labels(operation="hit").inc()

    def record_cache_miss(self) -> None:
        """Registra cache miss."""
        if not self._enabled:
            return
        jwk_cache_operations_total.labels(operation="miss").inc()

    def record_cache_evict(self) -> None:
        """Registra evicção de cache."""
        if not self._enabled:
            return
        jwk_cache_operations_total.labels(operation="evict").inc()

    def record_cache_clear(self) -> None:
        """Registra limpeza de cache."""
        if not self._enabled:
            return
        jwk_cache_operations_total.labels(operation="clear").inc()


# =============================================================================
# Funções auxiliares
# =============================================================================


@lru_cache(maxsize=1)
def get_jwt_verification_metrics() -> JWTVerificationMetrics:
    """
    Retorna singleton de métricas de verificação JWT.

    Returns:
        Instância de JWTVerificationMetrics
    """
    return JWTVerificationMetrics()


@lru_cache(maxsize=1)
def get_jwk_validation_metrics() -> JWKValidationMetrics:
    """
    Retorna singleton de métricas de validação JWK.

    Returns:
        Instância de JWKValidationMetrics
    """
    return JWKValidationMetrics()


# =============================================================================
# Métricas de SPIFFE Trust Bundle (específico para SEC-008)
# =============================================================================
#
# NOTA: spiffe_trust_bundle_updates_total é importada de spiffe_manager.py
# para evitar duplicação no CollectorRegistry do Prometheus.
# As métricas abaixo são específicas para validação de trust bundle no
# contexto de JWT/JWK verification.

if PROMETHEUS_AVAILABLE:
    # Importar métrica compartilhada de spiffe_manager para evitar duplicação
    try:
        from neural_hive_security.spiffe_manager import spiffe_trust_bundle_updates_total
    except ImportError:
        # Fallback se a importação falhar (ex: testes isolados)
        spiffe_trust_bundle_updates_total = None

    # Contador de chaves validadas do trust bundle
    spiffe_trust_bundle_keys_validated_total = Counter(
        "spiffe_trust_bundle_keys_validated_total",
        "Total de chaves validadas do trust bundle",
        ["validation_status"],  # valid, invalid
    )

    # Histograma de tempo de validação de trust bundle
    spiffe_trust_bundle_validation_duration_seconds = Histogram(
        "spiffe_trust_bundle_validation_duration_seconds",
        "Duração da validação de trust bundle em segundos",
        buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    )


class SPIFFETrustBundleMetrics:
    """
    Métricas específicas para trust bundle SPIFFE (SEC-008).

    Exemplo de uso:
        metrics = SPIFFETrustBundleMetrics()
        metrics.record_update("success", keys_validated=5, keys_invalid=0)
    """

    def __init__(self):
        """Inicializa métricas de trust bundle."""
        self._enabled = PROMETHEUS_AVAILABLE

    def record_update(self, status: str, keys_validated: int = 0, keys_invalid: int = 0) -> None:
        """
        Registra atualização de trust bundle.

        Args:
            status: Status da atualização (success, failed)
            keys_validated: Número de chaves validadas
            keys_invalid: Número de chaves inválidas
        """
        if not self._enabled:
            return

        # Usar métrica importada de spiffe_manager.py se disponível
        if spiffe_trust_bundle_updates_total is not None:
            spiffe_trust_bundle_updates_total.labels(status=status).inc()

        if keys_validated > 0:
            spiffe_trust_bundle_keys_validated_total.labels(validation_status="valid").inc(
                keys_validated
            )

        if keys_invalid > 0:
            spiffe_trust_bundle_keys_validated_total.labels(validation_status="invalid").inc(
                keys_invalid
            )

    def time_validation(self):
        """
        Context manager para medir duração da validação.

        Exemplo:
            with metrics.time_validation():
                results = validator.validate_jwks(jwks)
        """
        if not self._enabled:

            class NullTimer:
                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    pass

            return NullTimer()

        return spiffe_trust_bundle_validation_duration_seconds.time()
