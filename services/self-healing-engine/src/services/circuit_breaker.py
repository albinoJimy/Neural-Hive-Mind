"""
Circuit Breaker Pattern para Self-Healing Engine.

Previne chamadas a serviços que estão falhando repetidamente,
permitindo que o sistema recupere sem sobrecarga.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Optional, TypeVar

import structlog

logger = structlog.get_logger()

T = TypeVar("T")


class CircuitBreakerState(Enum):
    """Estados do Circuit Breaker."""

    CLOSED = "CLOSED"  # Operação normal
    OPEN = "OPEN"  # Serviço falhando, chamadas bloqueadas
    HALF_OPEN = "HALF_OPEN"  # Testando recuperação


class CircuitBreakerOpenError(Exception):
    """Exceção levantada quando tentativa de chamada com circuit breaker OPEN."""

    def __init__(self, service_name: str):
        self.service_name = service_name
        super().__init__(f"Circuit breaker is OPEN for service: {service_name}")


@dataclass
class CircuitBreakerInfo:
    """Informações sobre o estado do Circuit Breaker."""

    service_name: str
    state: CircuitBreakerState
    failure_count: int
    last_failure_time: Optional[datetime]
    last_state_change: datetime
    threshold: int
    timeout_seconds: int


class CircuitBreaker:
    """
    Implementação do Circuit Breaker Pattern.

    O circuit breaker bloqueia chamadas a um serviço após um número
    de falhas consecutivas, permitindo que o serviço recupere.
    """

    def __init__(
        self,
        service_name: str,
        failure_threshold: int = 5,
        timeout_seconds: int = 60,
        half_open_max_calls: int = 3,
    ):
        """
        Inicializa o Circuit Breaker.

        Args:
            service_name: Nome do serviço sendo monitorado
            failure_threshold: Número de falhas consecutivas para abrir
            timeout_seconds: Tempo antes de tentar recuperar (OPEN → HALF_OPEN)
            half_open_max_calls: Máximo de chamadas em HALF_OPEN antes de decidir
        """
        self.service_name = service_name
        self._failure_threshold = failure_threshold
        self._timeout_seconds = timeout_seconds
        self._half_open_max_calls = half_open_max_calls

        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._last_failure_time: Optional[datetime] = None
        self._last_state_change = datetime.now(timezone.utc)
        self._half_open_call_count = 0

        logger.info(
            "circuit_breaker.created",
            service=service_name,
            threshold=failure_threshold,
            timeout_seconds=timeout_seconds,
        )

    @property
    def state(self) -> CircuitBreakerState:
        """Estado atual do circuit breaker."""
        return self._state

    @property
    def failure_count(self) -> int:
        """Número de falhas consecutivas atuais."""
        return self._failure_count

    @property
    def last_failure_time(self) -> Optional[datetime]:
        """Timestamp da última falha."""
        return self._last_failure_time

    @property
    def is_open(self) -> bool:
        """Retorna True se o circuit breaker está aberto (OPEN)."""
        return self._state == CircuitBreakerState.OPEN

    def record_success(self):
        """
        Registra uma chamada bem-sucedida.

        Reseta o contador de falhas e, se em HALF_OPEN, fecha o circuito.
        """
        if self._state == CircuitBreakerState.HALF_OPEN:
            self._state = CircuitBreakerState.CLOSED
            logger.info(
                "circuit_breaker.closed_after_half_open",
                service=self.service_name,
                calls_in_half_open=self._half_open_call_count,
            )
            self._half_open_call_count = 0

        self._failure_count = 0
        self._last_state_change = datetime.now(timezone.utc)

    def record_failure(self, error_message: Optional[str] = None):
        """
        Registra uma falha.

        Args:
            error_message: Mensagem de erro opcional para logging
        """
        self._failure_count += 1
        self._last_failure_time = datetime.now(timezone.utc)

        logger.warning(
            "circuit_breaker.failure_recorded",
            service=self.service_name,
            failure_count=self._failure_count,
            threshold=self._failure_threshold,
            error=error_message,
        )

        if self._failure_count >= self._failure_threshold:
            self._open()

    def _open(self):
        """Abre o circuit breaker."""
        if self._state != CircuitBreakerState.OPEN:
            self._state = CircuitBreakerState.OPEN
            self._last_state_change = datetime.now(timezone.utc)
            logger.error(
                "circuit_breaker.opened",
                service=self.service_name,
                failure_count=self._failure_count,
            )

    def _half_open(self):
        """Transiciona para HALF_OPEN."""
        if self._state != CircuitBreakerState.HALF_OPEN:
            self._state = CircuitBreakerState.HALF_OPEN
            self._last_state_change = datetime.now(timezone.utc)
            self._half_open_call_count = 0
            logger.info("circuit_breaker.half_open", service=self.service_name)

    def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """
        Executa função com proteção do circuit breaker.

        Args:
            func: Função a executar
            *args: Argumentos posicionais
            **kwargs: Argumentos nomeados

        Returns:
            Resultado da função

        Raises:
            CircuitBreakerOpenError: Se circuit breaker está OPEN
        """
        if self._state == CircuitBreakerState.OPEN:
            # Verificar se expirou o timeout
            if self._last_state_change:
                elapsed = (datetime.now(timezone.utc) - self._last_state_change).total_seconds()
                if elapsed >= self._timeout_seconds:
                    self._half_open()
                else:
                    raise CircuitBreakerOpenError(self.service_name)
            else:
                raise CircuitBreakerOpenError(self.service_name)

        try:
            result = func(*args, **kwargs)

            if self._state == CircuitBreakerState.HALF_OPEN:
                self._half_open_call_count += 1
                # Após N chamadas bem-sucedidas em HALF_OPEN, fecha o circuito
                if self._half_open_call_count >= self._half_open_max_calls:
                    self.record_success()

            return result

        except Exception as e:
            self.record_failure(str(e))
            raise

    async def call_async(self, func: Callable[..., T], *args, **kwargs) -> T:
        """
        Executa função assíncrona com proteção do circuit breaker.

        Args:
            func: Função assíncrona a executar
            *args: Argumentos posicionais
            **kwargs: Argumentos nomeados

        Returns:
            Resultado da função

        Raises:
            CircuitBreakerOpenError: Se circuit breaker está OPEN
        """
        if self._state == CircuitBreakerState.OPEN:
            # Verificar se expirou o timeout
            if self._last_state_change:
                elapsed = (datetime.now(timezone.utc) - self._last_state_change).total_seconds()
                if elapsed >= self._timeout_seconds:
                    self._half_open()
                else:
                    raise CircuitBreakerOpenError(self.service_name)
            else:
                raise CircuitBreakerOpenError(self.service_name)

        try:
            result = await func(*args, **kwargs)

            if self._state == CircuitBreakerState.HALF_OPEN:
                self._half_open_call_count += 1
                if self._half_open_call_count >= self._half_open_max_calls:
                    self.record_success()

            return result

        except Exception as e:
            self.record_failure(str(e))
            raise

    def reset(self):
        """Reseta o circuit breaker para estado CLOSED."""
        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._last_failure_time = None
        self._last_state_change = datetime.now(timezone.utc)
        self._half_open_call_count = 0
        logger.info("circuit_breaker.reset", service=self.service_name)

    def get_state_info(self) -> dict:
        """Retorna informações sobre o estado atual."""
        return {
            "service_name": self.service_name,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "last_failure_time": (
                self._last_failure_time.isoformat() if self._last_failure_time else None
            ),
            "last_state_change": self._last_state_change.isoformat(),
            "threshold": self._failure_threshold,
            "timeout_seconds": self._timeout_seconds,
        }
