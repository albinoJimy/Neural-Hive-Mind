"""Exceções customizadas para neural_hive_resilience.

Este módulo define exceções específicas para padrões de resiliência:
- Circuit breaker
- Retry
- Rate limiting
- Timeout
- Fallback
- Bulkhead
"""

from typing import Optional


class ResilienceError(Exception):
    """Classe base para todas as exceções de resiliência."""

    def __init__(self, message: str, service: str = "unknown", **kwargs):
        self.message = message
        self.service = service
        self.context = kwargs
        super().__init__(message)


# ==================== Circuit Breaker Exceptions ====================


class CircuitBreakerError(ResilienceError):
    """Exceção base para erros de circuit breaker."""



class CircuitBreakerOpenError(CircuitBreakerError):
    """Levantada quando o circuit breaker está em estado OPEN.

    O circuito está aberto e não permite chamadas até o timeout expirar.
    """

    def __init__(
        self,
        message: str,
        service: str,
        circuit: str,
        opened_at: float,
        remaining_timeout: float,
        **kwargs,
    ):
        super().__init__(message, service=service, **kwargs)
        self.circuit = circuit
        self.opened_at = opened_at
        self.remaining_timeout = remaining_timeout


class CircuitBreakerHalfOpenError(CircuitBreakerError):
    """Levantada quando o circuit breaker está em HALF_OPEN.

    Estado de transição onde algumas chamadas são permitidas para teste.
    """

    def __init__(self, message: str, service: str, circuit: str, **kwargs):
        super().__init__(message, service=service, **kwargs)
        self.circuit = circuit


# ==================== Retry Exceptions ====================


class RetryError(ResilienceError):
    """Exceção base para erros de retry."""



class RetryableError(RetryError):
    """Exceção que indica que a operação pode ser retriada.

    Usada para marcar exceções que devem ser retriadas automaticamente.
    Pode incluir max_retry_count para limitar tentativas.
    """

    def __init__(
        self,
        message: str,
        service: str = "unknown",
        max_retry_count: int = 3,
        **kwargs,
    ):
        super().__init__(message, service=service, **kwargs)
        self.max_retry_count = max_retry_count


class NonRetryableError(RetryError):
    """Exceção que indica que a operação NÃO deve ser retriada.

    Usada para marcar exceções que devem falhar imediatamente.
    """



class MaxRetriesExceededError(RetryError):
    """Levantada quando o número máximo de tentativas é excedido.

    Contém a última exceção que causou a falha.
    """

    def __init__(
        self,
        message: str,
        operation: str = "unknown",
        attempts: int = 0,
        last_exception: Optional[Exception] = None,
        **kwargs,
    ):
        super().__init__(message, **kwargs)
        self.operation = operation
        self.attempts = attempts
        self.last_exception = last_exception


# ==================== Rate Limiting Exceptions ====================


class RateLimitError(ResilienceError):
    """Exceção base para erros de rate limiting."""



class RateLimitExceededError(RateLimitError):
    """Levantada quando o limite de taxa é excedido.

    Inclui informações sobre quando a próxima tentativa é permitida.
    """

    def __init__(
        self,
        message: str,
        service: str,
        limit: int,
        window_seconds: float,
        retry_after: float,
        **kwargs,
    ):
        super().__init__(message, service=service, **kwargs)
        self.limit = limit
        self.window_seconds = window_seconds
        self.retry_after = retry_after


class ConcurrencyLimitExceededError(RateLimitError):
    """Levantada quando o limite de concorrência é excedido (bulkhead)."""

    def __init__(
        self,
        message: str,
        service: str,
        current_concurrent: int,
        max_concurrent: int,
        **kwargs,
    ):
        super().__init__(message, service=service, **kwargs)
        self.current_concurrent = current_concurrent
        self.max_concurrent = max_concurrent


# ==================== Timeout Exceptions ====================


class TimeoutError(ResilienceError):
    """Exceção base para erros de timeout."""

    def __init__(
        self,
        message: str,
        service: str,
        timeout_seconds: float,
        **kwargs,
    ):
        super().__init__(message, service=service, **kwargs)
        self.timeout_seconds = timeout_seconds


# ==================== Fallback Exceptions ====================


class FallbackError(ResilienceError):
    """Exceção base para erros de fallback."""



class AllFallbacksFailedError(FallbackError):
    """Levantada quando todas as opções de fallback falham.

    Contém a lista de exceções que causaram as falhas.
    """

    def __init__(
        self,
        message: str,
        service: str,
        fallback_chain: list,
        exceptions: list,
        **kwargs,
    ):
        super().__init__(message, service=service, **kwargs)
        self.fallback_chain = fallback_chain
        self.exceptions = exceptions


# ==================== Bulkhead Exceptions ====================


class BulkheadError(ResilienceError):
    """Exceção base para erros de bulkhead."""



class BulkheadRejectedError(BulkheadError):
    """Levantada quando uma operação é rejeitada pelo bulkhead.

    O bulkhead está cheio e a operação não pode ser executada.
    """

    def __init__(
        self,
        message: str,
        service: str,
        max_concurrent: int,
        current_active: int,
        queue_size: int = 0,
        **kwargs,
    ):
        super().__init__(message, service=service, **kwargs)
        self.max_concurrent = max_concurrent
        self.current_active = current_active
        self.queue_size = queue_size


# ==================== Resilience Registry Exceptions ====================


class RegistryError(ResilienceError):
    """Exceção base para erros do registro de resiliência."""



class PolicyNotFoundError(RegistryError):
    """Levantada quando uma política não é encontrada no registro."""

    def __init__(self, message: str, policy_name: str, policy_type: str, **kwargs):
        super().__init__(message, **kwargs)
        self.policy_name = policy_name
        self.policy_type = policy_type


class PolicyAlreadyExistsError(RegistryError):
    """Levantada quando tenta registrar uma política que já existe."""

    def __init__(self, message: str, policy_name: str, policy_type: str, **kwargs):
        super().__init__(message, **kwargs)
        self.policy_name = policy_name
        self.policy_type = policy_type
