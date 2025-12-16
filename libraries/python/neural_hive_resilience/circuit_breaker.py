from typing import Optional

from pybreaker import CircuitBreaker, CircuitBreakerError
from prometheus_client import Counter, Gauge
import structlog

# Metrics
circuit_breaker_state = Gauge(
    "circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=open, 2=half_open)",
    ["service", "circuit"],
)
circuit_breaker_failures = Counter(
    "circuit_breaker_failures_total",
    "Circuit breaker failures",
    ["service", "circuit"],
)
circuit_breaker_trips = Counter(
    "circuit_breaker_trips_total",
    "Circuit breaker trips",
    ["service", "circuit"],
)


class MonitoredCircuitBreaker(CircuitBreaker):
    """Circuit breaker with Prometheus metrics and structured logging."""

    def __init__(
        self,
        service_name: str,
        circuit_name: str,
        timeout_duration: Optional[int] = None,
        recovery_timeout: Optional[int] = None,
        **kwargs,
    ):
        if timeout_duration is not None:
            kwargs["reset_timeout"] = timeout_duration
        self.recovery_timeout = recovery_timeout or kwargs.get("reset_timeout")
        super().__init__(**kwargs)
        self.service_name = service_name
        self.circuit_name = circuit_name
        self.logger = structlog.get_logger()

    def call(self, func, *args, **kwargs):
        try:
            result = super().call(func, *args, **kwargs)
            circuit_breaker_state.labels(
                service=self.service_name, circuit=self.circuit_name
            ).set(0)
            return result
        except CircuitBreakerError:
            circuit_breaker_trips.labels(
                service=self.service_name, circuit=self.circuit_name
            ).inc()
            circuit_breaker_state.labels(
                service=self.service_name, circuit=self.circuit_name
            ).set(1)
            self.logger.warning(
                "circuit_breaker_open",
                service=self.service_name,
                circuit=self.circuit_name,
            )
            raise
        except Exception:
            circuit_breaker_failures.labels(
                service=self.service_name, circuit=self.circuit_name
            ).inc()
            raise

    async def call_async(self, func, *args, **kwargs):
        """
        Async-friendly wrapper that preserves circuit breaker semantics and metrics.
        """
        try:
            self._state.before_call(self)
        except CircuitBreakerError:
            circuit_breaker_trips.labels(
                service=self.service_name, circuit=self.circuit_name
            ).inc()
            circuit_breaker_state.labels(
                service=self.service_name, circuit=self.circuit_name
            ).set(1)
            self.logger.warning(
                "circuit_breaker_open",
                service=self.service_name,
                circuit=self.circuit_name,
            )
            raise

        try:
            result = await func(*args, **kwargs)
        except Exception as exc:
            self._state.failure(self, exc)
            circuit_breaker_failures.labels(
                service=self.service_name, circuit=self.circuit_name
            ).inc()
            raise
        else:
            self._state.success(self)
            circuit_breaker_state.labels(
                service=self.service_name, circuit=self.circuit_name
            ).set(0)
            return result
