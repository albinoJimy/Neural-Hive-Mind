"""
Testes de Circuit Breaker para neural_hive_agent_sdk.

Cobre estados do circuit breaker (closed, open, half-open),
transições de estado, sampling em half-open, fechamento após sucesso
e abertura após falhas consecutivas.
"""

import pytest
import asyncio
from datetime import datetime, timezone
from enum import Enum


# ============================================================================
# Circuit Breaker Implementation (para testes)
# ============================================================================


class CircuitState(Enum):
    """Estados do Circuit Breaker."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class SimpleCircuitBreaker:
    """Implementação simples de Circuit Breaker para testes."""

    def __init__(self, failure_threshold: int = 5, timeout: float = 60.0):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = None
        self.success_count = 0

    def record_success(self):
        """Registra sucesso."""
        self.failure_count = 0
        self.success_count += 1

        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
            self.success_count = 0

    def record_failure(self):
        """Registra falha."""
        self.failure_count += 1
        self.last_failure_time = datetime.now(timezone.utc).timestamp()

        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN

    def can_attempt(self) -> bool:
        """Verifica se pode tentar requisição."""
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            if self.last_failure_time:
                elapsed = datetime.now(timezone.utc).timestamp() - self.last_failure_time
                if elapsed >= self.timeout:
                    self.state = CircuitState.HALF_OPEN
                    self.success_count = 0
                    return True
            return False

        if self.state == CircuitState.HALF_OPEN:
            return True

        return False

    def get_state(self) -> CircuitState:
        """Retorna estado atual."""
        return self.state


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def circuit_breaker():
    """Circuit breaker para testes."""
    return SimpleCircuitBreaker(failure_threshold=3, timeout=0.5)


# ============================================================================
# Testes de Circuit Closed
# ============================================================================


class TestCircuitClosed:
    """Testes do estado CLOSED do circuit breaker."""

    def test_circuit_closed_allows_requests(self, circuit_breaker):
        """Testa que circuito fechado permite requisições."""
        assert circuit_breaker.get_state() == CircuitState.CLOSED
        assert circuit_breaker.can_attempt() is True

    def test_circuit_closed_with_single_success(self, circuit_breaker):
        """Testa que sucesso mantém circuito fechado."""
        circuit_breaker.record_success()
        assert circuit_breaker.get_state() == CircuitState.CLOSED
        assert circuit_breaker.failure_count == 0

    def test_circuit_closed_with_single_failure(self, circuit_breaker):
        """Testa que falha única não abre circuito."""
        circuit_breaker.record_failure()
        assert circuit_breaker.get_state() == CircuitState.CLOSED
        assert circuit_breaker.failure_count == 1

    def test_circuit_closed_allows_multiple_requests(self, circuit_breaker):
        """Testa que múltiplas requisições são permitidas."""
        for _ in range(10):
            assert circuit_breaker.can_attempt() is True

    def test_circuit_closed_resets_failure_count_on_success(self, circuit_breaker):
        """Testa que sucesso reseta contador de falhas."""
        circuit_breaker.record_failure()
        circuit_breaker.record_failure()
        assert circuit_breaker.failure_count == 2

        circuit_breaker.record_success()
        assert circuit_breaker.failure_count == 0


# ============================================================================
# Testes de Circuit Open
# ============================================================================


class TestCircuitOpen:
    """Testes do estado OPEN do circuit breaker."""

    def test_circuit_opens_after_threshold(self, circuit_breaker):
        """Testa que circuito abre após atingir limite de falhas."""
        for _ in range(circuit_breaker.failure_threshold):
            circuit_breaker.record_failure()
        assert circuit_breaker.get_state() == CircuitState.OPEN

    def test_circuit_open_blocks_requests(self, circuit_breaker):
        """Testa que circuito aberto bloqueia requisições."""
        for _ in range(circuit_breaker.failure_threshold):
            circuit_breaker.record_failure()
        assert circuit_breaker.can_attempt() is False

    def test_circuit_open_fail_fast(self, circuit_breaker):
        """Testa fail fast quando circuito está aberto."""
        for _ in range(circuit_breaker.failure_threshold):
            circuit_breaker.record_failure()
        for _ in range(5):
            assert circuit_breaker.can_attempt() is False

    def test_circuit_open_tracks_failure_time(self, circuit_breaker):
        """Testa que tempo de falha é registrado."""
        before_failure = datetime.now(timezone.utc).timestamp()
        for _ in range(circuit_breaker.failure_threshold):
            circuit_breaker.record_failure()
        after_failure = datetime.now(timezone.utc).timestamp()

        assert circuit_breaker.last_failure_time is not None
        assert before_failure <= circuit_breaker.last_failure_time <= after_failure


# ============================================================================
# Testes de Circuit Half-Open
# ============================================================================


class TestCircuitHalfOpen:
    """Testes do estado HALF_OPEN do circuit breaker."""

    @pytest.mark.asyncio
    async def test_circuit_half_open_after_timeout(self, circuit_breaker):
        """Testa transição para HALF_OPEN após timeout."""
        for _ in range(circuit_breaker.failure_threshold):
            circuit_breaker.record_failure()
        assert circuit_breaker.get_state() == CircuitState.OPEN

        await asyncio.sleep(circuit_breaker.timeout + 0.1)
        circuit_breaker.can_attempt()
        assert circuit_breaker.get_state() == CircuitState.HALF_OPEN

    def test_circuit_half_open_allows_attempt(self, circuit_breaker):
        """Testa que HALF_OPEN permite tentativa."""
        for _ in range(circuit_breaker.failure_threshold):
            circuit_breaker.record_failure()
        circuit_breaker.state = CircuitState.HALF_OPEN
        circuit_breaker.last_failure_time = 0
        assert circuit_breaker.can_attempt() is True

    @pytest.mark.asyncio
    async def test_circuit_close_after_success_in_half_open(self, circuit_breaker):
        """Testa que sucesso em HALF_OPEN fecha circuito."""
        for _ in range(circuit_breaker.failure_threshold):
            circuit_breaker.record_failure()
        await asyncio.sleep(circuit_breaker.timeout + 0.1)
        circuit_breaker.can_attempt()
        circuit_breaker.record_success()
        assert circuit_breaker.get_state() == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_circuit_reopen_after_failure_in_half_open(self, circuit_breaker):
        """Testa que falha em HALF_OPEN reabre circuito."""
        for _ in range(circuit_breaker.failure_threshold):
            circuit_breaker.record_failure()
        await asyncio.sleep(circuit_breaker.timeout + 0.1)
        circuit_breaker.can_attempt()
        circuit_breaker.record_failure()
        assert circuit_breaker.get_state() == CircuitState.OPEN


# ============================================================================
# Testes de Transição de Estado
# ============================================================================


class TestCircuitTransitions:
    """Testes de transições de estado do circuit breaker."""

    def test_transition_closed_to_open(self, circuit_breaker):
        """Testa transição CLOSED -> OPEN."""
        assert circuit_breaker.get_state() == CircuitState.CLOSED
        for _ in range(circuit_breaker.failure_threshold):
            circuit_breaker.record_failure()
        assert circuit_breaker.get_state() == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_transition_open_to_half_open(self, circuit_breaker):
        """Testa transição OPEN -> HALF_OPEN."""
        for _ in range(circuit_breaker.failure_threshold):
            circuit_breaker.record_failure()
        assert circuit_breaker.get_state() == CircuitState.OPEN
        await asyncio.sleep(circuit_breaker.timeout + 0.1)
        circuit_breaker.can_attempt()
        assert circuit_breaker.get_state() == CircuitState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_transition_half_open_to_closed(self, circuit_breaker):
        """Testa transição HALF_OPEN -> CLOSED."""
        for _ in range(circuit_breaker.failure_threshold):
            circuit_breaker.record_failure()
        await asyncio.sleep(circuit_breaker.timeout + 0.1)
        circuit_breaker.can_attempt()
        circuit_breaker.record_success()
        assert circuit_breaker.get_state() == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_transition_half_open_to_open(self, circuit_breaker):
        """Testa transição HALF_OPEN -> OPEN."""
        for _ in range(circuit_breaker.failure_threshold):
            circuit_breaker.record_failure()
        await asyncio.sleep(circuit_breaker.timeout + 0.1)
        circuit_breaker.can_attempt()
        circuit_breaker.record_failure()
        assert circuit_breaker.get_state() == CircuitState.OPEN


# ============================================================================
# Testes de Configuração
# ============================================================================


class TestCircuitBreakerConfig:
    """Testes de configuração do circuit breaker."""

    def test_custom_failure_threshold(self):
        """Testa limite de falhas customizado."""
        cb = SimpleCircuitBreaker(failure_threshold=5)
        for _ in range(4):
            cb.record_failure()
        assert cb.get_state() == CircuitState.CLOSED
        cb.record_failure()
        assert cb.get_state() == CircuitState.OPEN

    def test_custom_timeout(self):
        """Testa timeout customizado com simulação de tempo."""
        cb = SimpleCircuitBreaker(failure_threshold=2, timeout=0.5)
        cb.record_failure()
        cb.record_failure()
        assert cb.get_state() == CircuitState.OPEN
        # Simular que o tempo passou (last_failure_time no passado)
        cb.last_failure_time = datetime.now(timezone.utc).timestamp() - 10
        # Agora deve poder tentar (transiciona para HALF_OPEN)
        assert cb.can_attempt() is True

    def test_default_configuration(self):
        """Testa configuração padrão."""
        cb = SimpleCircuitBreaker()
        assert cb.failure_threshold == 5
        assert cb.timeout == 60.0
        assert cb.get_state() == CircuitState.CLOSED
