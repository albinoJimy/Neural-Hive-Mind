"""
Testes para o Circuit Breaker Pattern.

Implementa o pattern de Circuit Breaker para prevenir chamadas
a serviços que estão falhando repetidamente.

Estados:
- CLOSED: Operação normal, chamadas passam
- OPEN: Serviço está falhando, chamadas falham imediatamente
- HALF_OPEN: Testando se serviço recuperou
"""

import pytest
from src.services.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitBreakerState,
)


class TestCircuitBreaker:
    """Testes para o CircuitBreaker."""

    def test_initial_state(self):
        """Testa estado inicial do circuit breaker."""
        cb = CircuitBreaker(service_name="test-service", failure_threshold=3, timeout_seconds=60)
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.failure_count == 0
        assert cb.last_failure_time is None

    def test_record_failure_increments_count(self):
        """Testa que falhas incrementam o contador."""
        cb = CircuitBreaker("test-service", failure_threshold=3)

        cb.record_failure("Connection timeout")

        assert cb.failure_count == 1
        assert cb.state == CircuitBreakerState.CLOSED

    def test_opens_after_threshold(self):
        """Testa que circuit breaker abre após threshold de falhas."""
        cb = CircuitBreaker("test-service", failure_threshold=3)

        cb.record_failure("Error 1")
        cb.record_failure("Error 2")
        assert cb.state == CircuitBreakerState.CLOSED

        cb.record_failure("Error 3")
        assert cb.state == CircuitBreakerState.OPEN

    def test_record_success_resets_failures(self):
        """Testa que sucesso reseta o contador de falhas."""
        cb = CircuitBreaker("test-service", failure_threshold=3)

        cb.record_failure("Error")
        cb.record_failure("Error")
        assert cb.failure_count == 2

        cb.record_success()
        assert cb.failure_count == 0
        assert cb.state == CircuitBreakerState.CLOSED

    def test_call_fails_when_open(self):
        """Testa que chamadas falham quando circuit breaker está OPEN."""
        cb = CircuitBreaker("test-service", failure_threshold=2)

        cb.record_failure("Error 1")
        cb.record_failure("Error 2")
        assert cb.state == CircuitBreakerState.OPEN

        with pytest.raises(CircuitBreakerOpenError):
            cb.call(lambda: "result")

    def test_transition_to_half_open_after_timeout(self):
        """Testa transição para HALF_OPEN após timeout."""
        cb = CircuitBreaker("test-service", failure_threshold=2, timeout_seconds=1)

        # Abrir o circuit breaker
        cb.record_failure("Error 1")
        cb.record_failure("Error 2")
        assert cb.state == CircuitBreakerState.OPEN

        # Aguardar timeout
        import time

        time.sleep(1.5)

        # Tentar chamar deve transicionar para HALF_OPEN
        result = cb.call(lambda: "success")
        assert result == "success"
        # Estado deve estar HALF_OPEN ou CLOSED dependendo da implementação
        assert cb.state in [CircuitBreakerState.HALF_OPEN, CircuitBreakerState.CLOSED]

    def test_half_open_to_closed_on_success(self):
        """Testa transição HALF_OPEN → CLOSED após sucesso."""
        cb = CircuitBreaker(
            "test-service", failure_threshold=2, timeout_seconds=1, half_open_max_calls=1
        )

        cb.record_failure("Error 1")
        cb.record_failure("Error 2")
        assert cb.state == CircuitBreakerState.OPEN

        # Aguardar timeout fora do teste assíncrono
        import time

        time.sleep(1.5)

        # Primeira chamada após sucesso deve fechar o circuito (half_open_max_calls=1)
        result = cb.call(lambda: "success")
        assert result == "success"

        # Verificar que fechou (meia chamada já fecha com half_open_max_calls=1)
        assert cb.state == CircuitBreakerState.CLOSED

    def test_half_open_to_open_on_failure(self):
        """Testa transição HALF_OPEN → OPEN após falha."""
        cb = CircuitBreaker(
            "test-service", failure_threshold=2, timeout_seconds=1, half_open_max_calls=1
        )

        cb.record_failure("Error 1")
        cb.record_failure("Error 2")
        assert cb.state == CircuitBreakerState.OPEN

        import time

        time.sleep(1.5)

        # Falha em HALF_OPEN deve reabrir
        def failing_func():
            raise Exception("Still failing")

        with pytest.raises(Exception):
            cb.call(failing_func)

        # Deve ter registrado a falha e reaberto
        assert cb.state == CircuitBreakerState.OPEN

    def test_get_state_info(self):
        """Testa obtenção de informações do estado."""
        cb = CircuitBreaker("test-service", failure_threshold=5)

        info = cb.get_state_info()
        assert info["service_name"] == "test-service"
        assert info["state"] == "CLOSED"
        assert info["failure_count"] == 0
        assert "last_state_change" in info

    def test_reset(self):
        """Testa reset manual do circuit breaker."""
        cb = CircuitBreaker("test-service", failure_threshold=3)

        cb.record_failure("Error 1")
        cb.record_failure("Error 2")
        cb.record_failure("Error 3")
        assert cb.state == CircuitBreakerState.OPEN

        cb.reset()
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.failure_count == 0


class TestCircuitBreakerState:
    """Testes para o enum CircuitBreakerState."""

    def test_state_values(self):
        """Testa valores do estado."""
        assert CircuitBreakerState.CLOSED.value == "CLOSED"
        assert CircuitBreakerState.OPEN.value == "OPEN"
        assert CircuitBreakerState.HALF_OPEN.value == "HALF_OPEN"


class TestCircuitBreakerOpenError:
    """Testes para a exceção CircuitBreakerOpenError."""

    def test_error_message(self):
        """Testa mensagem de erro."""
        error = CircuitBreakerOpenError("test-service")
        assert "test-service" in str(error)
        assert "OPEN" in str(error)
