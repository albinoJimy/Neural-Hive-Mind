"""
Testes unitários para CircuitBreaker do cliente Redis.
"""
import pytest
import time
from unittest.mock import patch

from src.clients.redis_client import CircuitBreaker


class TestCircuitBreakerStates:
    """Testes de transições de estado do circuit breaker."""

    def test_initial_state_is_closed(self):
        """Testa que estado inicial é CLOSED."""
        cb = CircuitBreaker()
        assert cb.state == "CLOSED"
        assert cb.failure_count == 0
        assert cb.last_failure_time is None

    def test_allows_requests_when_closed(self):
        """Testa que requisições são permitidas quando CLOSED."""
        cb = CircuitBreaker()
        assert cb.should_allow_request() is True

    def test_remains_closed_under_threshold(self):
        """Testa que permanece CLOSED abaixo do threshold."""
        cb = CircuitBreaker(failure_threshold=5)

        for _ in range(4):
            cb.record_failure()

        assert cb.state == "CLOSED"
        assert cb.failure_count == 4
        assert cb.should_allow_request() is True

    def test_opens_after_threshold(self):
        """Testa que abre após atingir threshold de falhas."""
        cb = CircuitBreaker(failure_threshold=5)

        for _ in range(5):
            cb.record_failure()

        assert cb.state == "OPEN"
        assert cb.failure_count == 5
        assert cb.last_failure_time is not None

    def test_blocks_requests_when_open(self):
        """Testa que requisições são bloqueadas quando OPEN."""
        cb = CircuitBreaker(failure_threshold=5, recovery_timeout=60)

        for _ in range(5):
            cb.record_failure()

        assert cb.state == "OPEN"
        assert cb.should_allow_request() is False


class TestCircuitBreakerRecovery:
    """Testes de recuperação do circuit breaker."""

    def test_transitions_to_half_open_after_timeout(self):
        """Testa transição para HALF_OPEN após recovery timeout."""
        cb = CircuitBreaker(failure_threshold=5, recovery_timeout=1)

        for _ in range(5):
            cb.record_failure()

        assert cb.state == "OPEN"

        # Simular passagem do tempo
        with patch('src.clients.redis_client.time.time', return_value=time.time() + 2):
            assert cb.should_allow_request() is True
            assert cb.state == "HALF_OPEN"

    def test_resets_to_closed_on_success_in_half_open(self):
        """Testa reset para CLOSED em sucesso no estado HALF_OPEN."""
        cb = CircuitBreaker(failure_threshold=5, recovery_timeout=1)

        for _ in range(5):
            cb.record_failure()

        cb.state = "HALF_OPEN"
        cb.record_success()

        assert cb.state == "CLOSED"
        assert cb.failure_count == 0
        assert cb.last_failure_time is None

    def test_remains_closed_on_success(self):
        """Testa que sucesso em CLOSED não altera estado."""
        cb = CircuitBreaker()

        cb.record_failure()
        cb.record_failure()
        cb.record_success()

        # Deve permanecer CLOSED (não reseta contador abaixo do threshold)
        assert cb.state == "CLOSED"

    def test_allows_test_request_in_half_open(self):
        """Testa que permite requisição de teste em HALF_OPEN."""
        cb = CircuitBreaker()
        cb.state = "HALF_OPEN"

        assert cb.should_allow_request() is True


class TestCircuitBreakerReset:
    """Testes de reset do circuit breaker."""

    def test_reset_clears_all_state(self):
        """Testa que reset limpa todo o estado."""
        cb = CircuitBreaker(failure_threshold=3)

        for _ in range(3):
            cb.record_failure()

        assert cb.state == "OPEN"

        cb.reset()

        assert cb.state == "CLOSED"
        assert cb.failure_count == 0
        assert cb.last_failure_time is None

    def test_reset_from_half_open(self):
        """Testa reset a partir de HALF_OPEN."""
        cb = CircuitBreaker()
        cb.state = "HALF_OPEN"
        cb.failure_count = 5

        cb.reset()

        assert cb.state == "CLOSED"
        assert cb.failure_count == 0


class TestCircuitBreakerConfiguration:
    """Testes de configuração do circuit breaker."""

    def test_default_configuration(self):
        """Testa configuração padrão."""
        cb = CircuitBreaker()

        assert cb.failure_threshold == 5
        assert cb.recovery_timeout == 60

    def test_custom_configuration(self):
        """Testa configuração customizada."""
        cb = CircuitBreaker(failure_threshold=10, recovery_timeout=120)

        assert cb.failure_threshold == 10
        assert cb.recovery_timeout == 120

    def test_respects_custom_threshold(self):
        """Testa que respeita threshold customizado."""
        cb = CircuitBreaker(failure_threshold=3)

        for _ in range(2):
            cb.record_failure()

        assert cb.state == "CLOSED"

        cb.record_failure()

        assert cb.state == "OPEN"
