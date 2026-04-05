"""
Circuit Breaker Pattern para proteção de chamadas ao modelo ML.

Previne cascading failures quando o serviço de ML está indisponível
ou respondendo lentamente.
"""
import time
import asyncio
from enum import Enum, auto
from typing import Callable, TypeVar, Optional, Any
from functools import wraps
import structlog

from ..config import get_settings


logger = structlog.get_logger()
settings = get_settings()


class CircuitState(Enum):
    """Estados do Circuit Breaker."""
    CLOSED = auto()  # Funcionando normalmente
    OPEN = auto()  # Circuito aberto, rejeita chamadas
    HALF_OPEN = auto()  # Testando recuperação


class CircuitBreakerOpenError(Exception):
    """Exceção levantada quando circuit breaker está aberto."""
    def __init__(self, message: str = "Circuit breaker is OPEN") -> None:
        self.message = message
        super().__init__(self.message)


T = TypeVar("T")


class CircuitBreaker:
    """
    Implementação do Circuit Breaker Pattern.

    Protege serviços externos de serem sobrecarregados quando estão
    com problemas, abrindo o circuito após um threshold de falhas.
    """

    def __init__(
        self,
        threshold: int | None = None,
        timeout_seconds: int | None = None,
        recovery_timeout_seconds: int | None = None,
        name: str = "default",
    ):
        """
        Inicializa Circuit Breaker.

        Args:
            threshold: Número de falhas consecutivas para abrir circuito
            timeout_seconds: Tempo para manter circuito aberto
            recovery_timeout_seconds: Tempo para tentar recuperação em half-open
            name: Nome do circuit breaker (para logging)
        """
        self.threshold = threshold or settings.circuit_breaker_threshold
        self.timeout_seconds = timeout_seconds or settings.circuit_breaker_timeout_seconds
        self.recovery_timeout_seconds = (
            recovery_timeout_seconds or settings.circuit_breaker_recovery_timeout_seconds
        )
        self.name = name

        # Estado interno
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._success_count = 0  # Para half-open state
        self._last_state_change: float = time.time()
        self._opened_at: Optional[float] = None  # Quando foi aberto

    @property
    def state(self) -> CircuitState:
        """Retorna estado atual do circuit breaker."""
        return self._state

    @property
    def failure_count(self) -> int:
        """Retorna contador de falhas."""
        return self._failure_count

    def _should_allow_request(self) -> bool:
        """Verifica se request deve ser permitido."""
        if self._state == CircuitState.CLOSED:
            return True

        if self._state == CircuitState.OPEN:
            # Verifica se timeout expirou para tentar half-open
            if (
                self._last_failure_time
                and (time.time() - self._last_failure_time) >= self.timeout_seconds
            ):
                logger.info(
                    "circuit_breaker_transitioning_to_half_open",
                    name=self.name,
                    open_duration_seconds=time.time() - (self._last_failure_time or 0),
                )
                self._state = CircuitState.HALF_OPEN
                self._last_state_change = time.time()
                self._success_count = 0
                return True
            return False

        # HALF_OPEN - permite request para testar recuperação
        return True

    def _on_success(self) -> None:
        """Callback para chamada bem-sucedida."""
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= 2:  # 2 sucessos consecutivos
                logger.info(
                    "circuit_breaker_closed_after_recovery",
                    name=self.name,
                    success_count=self._success_count,
                )
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._last_state_change = time.time()
        elif self._state == CircuitState.CLOSED:
            self._failure_count = 0  # Reset em sucesso

    def _on_failure(self) -> None:
        """Callback para chamada falhada."""
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._state == CircuitState.HALF_OPEN:
            # Falha em half-open -> voltar para open
            logger.warning(
                "circuit_breaker_reopen_from_half_open",
                name=self.name,
                failure_count=self._failure_count,
            )
            self._state = CircuitState.OPEN
            self._opened_at = time.time()
            self._last_state_change = time.time()
        elif self._failure_count >= self.threshold:
            # Threshold atingido -> abrir circuito
            logger.warning(
                "circuit_breaker_opened",
                name=self.name,
                failure_count=self._failure_count,
                threshold=self.threshold,
            )
            self._state = CircuitState.OPEN
            self._opened_at = time.time()
            self._last_state_change = time.time()

    def call(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """
        Executa função protegida pelo circuit breaker.

        Args:
            func: Função a executar
            *args: Argumentos posicionais
            **kwargs: Argumentos nomeados

        Returns:
            Resultado da função

        Raises:
            CircuitBreakerOpenError: Se circuito está aberto
            Exception: Exceção original da função (se circuito fechado)
        """
        if not self._should_allow_request():
            logger.warning(
                "circuit_breaker_rejecting_request",
                name=self.name,
                state=self._state.name,
                failure_count=self._failure_count,
            )
            raise CircuitBreakerOpenError(
                f"Circuit breaker '{self.name}' is OPEN - rejecting request"
            )

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            logger.error(
                "circuit_breaker_function_failed",
                name=self.name,
                error=str(e),
                state=self._state.name,
                failure_count=self._failure_count,
            )
            raise

    async def call_async(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """
        Executa função assíncrona protegida pelo circuit breaker.

        Args:
            func: Função assíncrona a executar
            *args: Argumentos posicionais
            **kwargs: Argumentos nomeados

        Returns:
            Resultado da função

        Raises:
            CircuitBreakerOpenError: Se circuito está aberto
            Exception: Exceção original da função (se circuito fechado)
        """
        if not self._should_allow_request():
            logger.warning(
                "circuit_breaker_rejecting_async_request",
                name=self.name,
                state=self._state.name,
                failure_count=self._failure_count,
            )
            raise CircuitBreakerOpenError(
                f"Circuit breaker '{self.name}' is OPEN - rejecting request"
            )

        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            logger.error(
                "circuit_breaker_async_function_failed",
                name=self.name,
                error=str(e),
                state=self._state.name,
                failure_count=self._failure_count,
            )
            raise

    async def acall(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """
        Executa função assíncrona protegida pelo circuit breaker.

        Args:
            func: Função assíncrona a executar
            *args: Argumentos posicionais
            **kwargs: Argumentos nomeados

        Returns:
            Resultado da função

        Raises:
            CircuitBreakerOpenError: Se circuito está aberto
            Exception: Exceção original da função (se circuito fechado)
        """
        if not self._should_allow_request():
            logger.warning(
                "circuit_breaker_rejecting_async_request",
                name=self.name,
                state=self._state.name,
                failure_count=self._failure_count,
            )
            raise CircuitBreakerOpenError(
                f"Circuit breaker '{self.name}' is OPEN - rejecting request"
            )

        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            logger.error(
                "circuit_breaker_async_function_failed",
                name=self.name,
                error=str(e),
                state=self._state.name,
                failure_count=self._failure_count,
            )
            raise

    def record_failure(self) -> None:
        """Registra uma falha manualmente."""
        self._on_failure()

    def record_success(self) -> None:
        """Registra um sucesso manualmente."""
        self._on_success()

    def reset(self) -> None:
        """Reseta circuit breaker para estado fechado."""
        logger.info(
            "circuit_breaker_manually_reset",
            name=self.name,
            previous_state=self._state.name,
        )
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = None
        self._success_count = 0
        self._last_state_change = time.time()
        self._opened_at = None

    def get_state_info(self) -> dict[str, Any]:
        """Retorna informações sobre estado atual."""
        return {
            "name": self.name,
            "state": self._state.name,
            "failure_count": self._failure_count,
            "threshold": self.threshold,
            "last_failure_time": self._last_failure_time,
        }

    def get_metrics(self) -> dict[str, Any]:
        """Retorna métricas completas do circuit breaker."""
        metrics = {
            "name": self.name,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "threshold": self.threshold,
            "last_failure_time": self._last_failure_time,
            "last_state_change": self._last_state_change,
        }
        if self._state == CircuitState.OPEN and self._opened_at:
            metrics["opened_at"] = self._opened_at
        return metrics


def circuit_breaker(
    threshold: int | None = None,
    timeout_seconds: int | None = None,
    recovery_timeout_seconds: int | None = None,
    name: str = "default",
) -> Callable:
    """
    Decorator para aplicar circuit breaker em funções.

    Args:
        threshold: Número de falhas consecutivas para abrir circuito
        timeout_seconds: Tempo para manter circuito aberto
        recovery_timeout_seconds: Tempo para tentar recuperação em half-open
        name: Nome do circuit breaker

    Returns:
        Decorator function

    Example:
        @circuit_breaker(threshold=3, name="ml_model")
        def predict(text: str) -> dict:
            return model.predict(text)
    """
    cb = CircuitBreaker(threshold, timeout_seconds, recovery_timeout_seconds, name)

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> T:
            return cb.call(func, *args, **kwargs)

        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> T:
            return await cb.acall(func, *args, **kwargs)

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if asyncio.iscoroutinefunction(func):
                return async_wrapper(*args, **kwargs)
            return sync_wrapper(*args, **kwargs)

        return wrapper  # type: ignore

    return decorator
