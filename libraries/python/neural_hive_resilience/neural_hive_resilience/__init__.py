"""
Neural Hive-Mind Resilience Library

Biblioteca padronizada para padrões de resiliência em serviços Neural Hive-Mind.
Fornece circuit breakers, retry, rate limiting, timeout, fallback e bulkhead.

Funcionalidades:
- Circuit Breaker com métricas Prometheus
- Retry com exponential backoff e jitter
- Rate limiting (token bucket, sliding window)
- Timeout para operações assíncronas
- Fallback chains para degradação graciosa
- Bulkhead para isolamento de recursos
- Registro central de políticas

Exemplo de uso:
```python
from neural_hive_resilience import (
    ResilienceRegistry,
    retry,
    timeout,
    CircuitBreakerOpenError,
)

# Criar registro de políticas
registry = ResilienceRegistry(service_name="consensus-engine")

# Registrar circuit breaker
cb = registry.register_circuit_breaker(
    name="specialist_calls",
    failure_threshold=5,
    recovery_timeout=60,
)

# Usar decorator de retry
@retry(
    policy=registry.get_retry_policy("default"),
    service_name="consensus-engine",
    operation_name="call_specialist",
)
async def call_specialist(specialist_id: str):
    return await specialist.analyze(...)
```
"""

__version__ = "2.0.0"

# Circuit Breaker
from .circuit_breaker import MonitoredCircuitBreaker

# Fallback
from .fallback import (
    ConditionalFallback,
    FallbackChain,
    FallbackConfig,
    FallbackResult,
    FallbackStrategy,
    with_fallback,
)

# Rate Limiting
from .rate_limiter import (
    ConcurrencyLimiter,
    RateLimitAlgorithm,
    RateLimiterFactory,
    RateLimitResult,
    SlidingWindowLogRateLimiter,
    TokenBucketRateLimiter,
)

# Retry
from .retry import (
    BackoffStrategy,
    RetryConfigError,
    RetryContext,
    RetryPolicy,
    retry,
)

# Timeout
from .timeout import (
    TimeoutContext,
    TimeoutWithFallback,
    timeout,
    timeout_with_fallback,
)

# Alias para compatibilidade
fallback = with_fallback

# Bulkhead
from .bulkhead import (
    BulkheadConfig,
    BulkheadFactory,
    BulkheadStrategy,
    SemaphoreBulkhead,
    ThreadPoolBulkhead,
    bulkhead,
)

# Exceptions
from .exceptions import (
    AllFallbacksFailedError,
    # Bulkhead
    BulkheadError,
    BulkheadRejectedError,
    # Circuit Breaker
    CircuitBreakerError,
    CircuitBreakerHalfOpenError,
    CircuitBreakerOpenError,
    ConcurrencyLimitExceededError,
    # Fallback
    FallbackError,
    MaxRetriesExceededError,
    NonRetryableError,
    PolicyAlreadyExistsError,
    PolicyNotFoundError,
    # Rate Limiting
    RateLimitError,
    RateLimitExceededError,
    # Registry
    RegistryError,
    # Base
    ResilienceError,
    RetryableError,
    # Retry
    RetryError,
    # Timeout
    TimeoutError as ResilienceTimeoutError,
)

# Registry
from .registry import (
    PolicyMetadata,
    PolicyType,
    ResilienceRegistry,
    get_global_registry,
    init_global_registry,
)

# Re-exportar CircuitBreakerError do pybreaker para compatibilidade
try:
    from pybreaker import CircuitBreakerError as PyBreakerCircuitBreakerError

    CircuitBreakerError = PyBreakerCircuitBreakerError
except ImportError:
    pass

__all__ = [
    # Version
    "__version__",
    # Circuit Breaker
    "MonitoredCircuitBreaker",
    "CircuitBreakerError",
    "CircuitBreakerOpenError",
    "CircuitBreakerHalfOpenError",
    # Retry
    "RetryPolicy",
    "BackoffStrategy",
    "retry",
    "RetryContext",
    "RetryConfigError",
    "RetryableError",
    "NonRetryableError",
    "MaxRetriesExceededError",
    # Rate Limiting
    "TokenBucketRateLimiter",
    "SlidingWindowLogRateLimiter",
    "ConcurrencyLimiter",
    "RateLimiterFactory",
    "RateLimitAlgorithm",
    "RateLimitResult",
    "RateLimitError",
    "RateLimitExceededError",
    "ConcurrencyLimitExceededError",
    # Timeout
    "timeout",
    "timeout_with_fallback",
    "TimeoutContext",
    "TimeoutWithFallback",
    "ResilienceTimeoutError",
    # Fallback
    "FallbackChain",
    "FallbackConfig",
    "FallbackResult",
    "FallbackStrategy",
    "ConditionalFallback",
    "with_fallback",
    "fallback",
    "AllFallbacksFailedError",
    # Bulkhead
    "SemaphoreBulkhead",
    "ThreadPoolBulkhead",
    "BulkheadFactory",
    "BulkheadConfig",
    "BulkheadStrategy",
    "bulkhead",
    "BulkheadRejectedError",
    # Registry
    "ResilienceRegistry",
    "PolicyType",
    "PolicyMetadata",
    "get_global_registry",
    "init_global_registry",
    "PolicyNotFoundError",
    "PolicyAlreadyExistsError",
    # Base
    "ResilienceError",
    "FallbackError",
    "BulkheadError",
    "RetryError",
    "RegistryError",
]
