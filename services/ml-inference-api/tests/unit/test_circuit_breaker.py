"""
Unit Tests para Circuit Breaker - ML Inference API

Testes unitários para o padrão Circuit Breaker de proteção contra falhas.
"""
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Dict, Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import uuid4
import asyncio
import time

import pytest

from src.services.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    CircuitBreakerOpenError
)


# ===== FIXTURES =====


@pytest.fixture
def mock_settings():
    """Configurações mockadas para testes."""
    return SimpleNamespace(
        circuit_breaker_threshold=5,
        circuit_breaker_timeout_seconds=60000,  # 1 minuto
        circuit_breaker_half_open_max_calls=3,
    )


@pytest.fixture
def circuit_breaker(mock_settings):
    """Instância do CircuitBreaker para testes."""
    with patch('src.services.circuit_breaker.get_settings', return_value=mock_settings):
        breaker = CircuitBreaker(
            name='test_breaker',
            threshold=5,
            timeout_seconds=1000  # 1 segundo para testes
        )
    return breaker


# ===== TESTES: Initialization =====


class TestCircuitBreakerInit:
    """Testes de inicialização do CircuitBreaker."""

    def test_init_creates_breaker(self, mock_settings):
        """
        DADO: Configurações válidas
        QUANDO: Crio CircuitBreaker
        ENTÃO: Deve inicializar em estado CLOSED
        """
        with patch('src.services.circuit_breaker.get_settings', return_value=mock_settings):
            breaker = CircuitBreaker(
                name='test_breaker',
                threshold=5,
                timeout_seconds=60000
            )

        assert breaker.name == 'test_breaker'
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0
        assert breaker.threshold == 5

    def test_init_with_custom_parameters(self, mock_settings):
        """
        DADO: Parâmetros customizados
        QUANDO: Crio CircuitBreaker
        ENTÃO: Deve usar os parâmetros fornecidos
        """
        with patch('src.services.circuit_breaker.get_settings', return_value=mock_settings):
            breaker = CircuitBreaker(
                name='custom_breaker',
                threshold=10,
                timeout_seconds=30
            )

        assert breaker.name == 'custom_breaker'
        assert breaker.threshold == 10
        assert breaker.timeout_seconds == 30


# ===== TESTES: State Transitions =====


class TestCircuitStateTransitions:
    """Testes de transições de estado do Circuit Breaker."""

    def test_closed_to_open_after_threshold(self):
        """
        DADO: Circuit breaker em estado CLOSED
        QUANDO: Ocorrem falhas acima do threshold
        ENTÃO: Deve transicionar para OPEN
        """
        breaker = CircuitBreaker(
            name='test_breaker',
            threshold=3,
            timeout_seconds=1000
        )

        assert breaker.state == CircuitState.CLOSED

        # Registrar falhas até o threshold
        breaker.record_failure()
        breaker.record_failure()
        breaker.record_failure()

        # Após o threshold, deve estar OPEN
        assert breaker.state == CircuitState.OPEN

    def test_closed_remains_closed_below_threshold(self):
        """
        DADO: Circuit breaker em estado CLOSED
        QUANDO: Ocorrem falhas abaixo do threshold
        ENTÃO: Deve permanecer CLOSED
        """
        breaker = CircuitBreaker(
            name='test_breaker',
            threshold=5,
            timeout_seconds=1000
        )

        # Registrar apenas 2 falhas (threshold é 5)
        breaker.record_failure()
        breaker.record_failure()

        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 2

    def test_closed_to_open_with_success_resets(self):
        """
        DADO: Circuit breaker com algumas falhas
        QUANDO: Ocorre um sucesso
        ENTÃO: Deve resetar o contador de falhas
        """
        breaker = CircuitBreaker(
            name='test_breaker',
            threshold=5,
            timeout_seconds=1000
        )

        # Registrar 3 falhas
        breaker.record_failure()
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.failure_count == 3

        # Registrar sucesso
        breaker.record_success()
        assert breaker.failure_count == 0
        assert breaker.state == CircuitState.CLOSED


# ===== TESTES: OPEN State =====


class TestCircuitBreakerOpenState:
    """Testes do estado OPEN do Circuit Breaker."""

    def test_open_blocks_calls(self):
        """
        DADO: Circuit breaker em estado OPEN
        QUANDO: Tentar fazer uma chamada
        ENTÃO: Deve levantar CircuitBreakerOpenError
        """
        breaker = CircuitBreaker(
            name='test_breaker',
            threshold=3,
            timeout_seconds=1000
        )

        # Forçar para OPEN
        breaker.record_failure()
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

        # Tentar chamar - deve levantar erro
        with pytest.raises(CircuitBreakerOpenError):
            breaker.call(lambda: 'result')

    def test_open_to_half_open_after_timeout(self):
        """
        DADO: Circuit breaker em estado OPEN
        QUANDO: O tempo de timeout expira
        ENTÃO: Deve transicionar para HALF_OPEN
        """
        breaker = CircuitBreaker(
            name='test_breaker',
            threshold=3,
            timeout_seconds=1  # 1 segundo para testes
        )

        # Forçar para OPEN
        breaker.record_failure()
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

        # Esperar timeout (um pouco mais para garantir)
        time.sleep(1.1)

        # Tentar uma chamada - deve transicionar para HALF_OPEN
        try:
            breaker.call(lambda: 'result')
        except CircuitBreakerOpenError:
            pass

        # Após timeout, deve estar HALF_OPEN
        assert breaker.state == CircuitState.HALF_OPEN


# ===== TESTES: HALF_OPEN State =====


class TestCircuitBreakerHalfOpenState:
    """Testes do estado HALF_OPEN do Circuit Breaker."""

    def test_half_open_to_closed_after_success(self):
        """
        DADO: Circuit breaker em estado HALF_OPEN
        QUANDO: Chamadas succeeds
        ENTÃO: Deve transicionar para CLOSED após 2 sucessos consecutivos
        """
        breaker = CircuitBreaker(
            name='test_breaker',
            threshold=3,
            timeout_seconds=1
        )

        # Forçar para OPEN
        breaker.record_failure()
        breaker.record_failure()
        breaker.record_failure()

        # Esperar timeout para HALF_OPEN
        time.sleep(1.1)

        # Fazer chamadas de sucesso
        result1 = breaker.call(lambda: 'result1')
        assert result1 == 'result1'
        assert breaker.state == CircuitState.HALF_OPEN

        result2 = breaker.call(lambda: 'result2')
        assert result2 == 'result2'

        # Após 2 sucessos consecutivos, deve estar CLOSED
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0

    def test_half_open_to_open_after_failure(self):
        """
        DADO: Circuit breaker em estado HALF_OPEN
        QUANDO: Uma chamada falha
        ENTÃO: Deve transicionar de volta para OPEN
        """
        breaker = CircuitBreaker(
            name='test_breaker',
            threshold=3,
            timeout_seconds=1
        )

        # Forçar para OPEN
        breaker.record_failure()
        breaker.record_failure()
        breaker.record_failure()

        # Esperar timeout para HALF_OPEN
        time.sleep(1.1)

        # Fazer uma chamada com sucesso para confirmar HALF_OPEN
        breaker.call(lambda: 'result')
        assert breaker.state == CircuitState.HALF_OPEN

        # Fazer uma chamada que falha
        with pytest.raises(ValueError):
            breaker.call(lambda: (_ for _ in ()).throw(ValueError('Test error')))

        # Deve voltar para OPEN
        assert breaker.state == CircuitState.OPEN


# ===== TESTES: Call Method =====


class TestCircuitBreakerCall:
    """Testes do método call do Circuit Breaker."""

    def test_call_success_in_closed_state(self):
        """
        DADO: Circuit breaker em estado CLOSED
        QUANDO: Chamar uma função que succeeds
        ENTÃO: Deve executar e registrar sucesso
        """
        breaker = CircuitBreaker(
            name='test_breaker',
            threshold=3,
            timeout_seconds=1000
        )

        result = breaker.call(lambda x: x * 2, 5)

        assert result == 10
        assert breaker.failure_count == 0
        assert breaker.state == CircuitState.CLOSED

    def test_call_failure_in_closed_state(self):
        """
        DADO: Circuit breaker em estado CLOSED
        QUANDO: Chamar uma função que falha
        ENTÃO: Deve propagar exceção e registrar falha
        """
        breaker = CircuitBreaker(
            name='test_breaker',
            threshold=3,
            timeout_seconds=1000
        )

        with pytest.raises(ValueError, match='Test error'):
            breaker.call(lambda: (_ for _ in ()).throw(ValueError('Test error')))

        assert breaker.failure_count == 1
        assert breaker.state == CircuitState.CLOSED

    def test_call_with_fallback(self):
        """
        DADO: Circuit breaker em estado OPEN
        QUANDO: Chamar uma função
        ENTÃO: Deve levantar CircuitBreakerOpenError (sem suporte a fallback)
        """
        breaker = CircuitBreaker(
            name='test_breaker',
            threshold=3,
            timeout_seconds=1000
        )

        # Forçar para OPEN
        breaker.record_failure()
        breaker.record_failure()
        breaker.record_failure()

        # Chamar - deve levantar erro (não existe fallback na API)
        with pytest.raises(CircuitBreakerOpenError):
            breaker.call(lambda: 'original')


# ===== TESTES: Async Call Method =====


class TestCircuitBreakerAsyncCall:
    """Testes do método call_async do Circuit Breaker."""

    @pytest.mark.asyncio
    async def test_call_async_success(self):
        """
        DADO: Circuit breaker em estado CLOSED
        QUANDO: Chamar uma função async que succeeds
        ENTÃO: Deve executar e registrar sucesso
        """
        breaker = CircuitBreaker(
            name='test_breaker',
            threshold=3,
            timeout_seconds=1000
        )

        async def async_func(x):
            return x * 2

        result = await breaker.call_async(async_func, 5)

        assert result == 10
        assert breaker.failure_count == 0

    @pytest.mark.asyncio
    async def test_call_async_failure(self):
        """
        DADO: Circuit breaker em estado CLOSED
        QUANDO: Chamar uma função async que falha
        ENTÃO: Deve propagar exceção e registrar falha
        """
        breaker = CircuitBreaker(
            name='test_breaker',
            threshold=3,
            timeout_seconds=1000
        )

        async def async_failing_func():
            raise ValueError('Async error')

        with pytest.raises(ValueError, match='Async error'):
            await breaker.call_async(async_failing_func)

        assert breaker.failure_count == 1

    @pytest.mark.asyncio
    async def test_call_async_when_open(self):
        """
        DADO: Circuit breaker em estado OPEN
        QUANDO: Chamar call_async
        ENTÃO: Deve levantar CircuitBreakerOpenError
        """
        breaker = CircuitBreaker(
            name='test_breaker',
            threshold=3,
            timeout_seconds=1000
        )

        # Forçar para OPEN
        breaker.record_failure()
        breaker.record_failure()
        breaker.record_failure()

        async def async_func():
            return 'result'

        with pytest.raises(CircuitBreakerOpenError):
            await breaker.call_async(async_func)


# ===== TESTES: Metrics =====


class TestCircuitBreakerMetrics:
    """Testes de métricas do Circuit Breaker."""

    def test_get_metrics(self):
        """
        DADO: Um circuit breaker com histórico
        QUANDO: Chamo get_metrics
        ENTÃO: Deve retornar métricas completas
        """
        breaker = CircuitBreaker(
            name='test_breaker',
            threshold=5,
            timeout_seconds=1000
        )

        # Registrar algumas falhas
        breaker.record_failure()
        breaker.record_failure()
        # Em estado CLOSED, record_success reseta o contador
        breaker.record_success()
        # Mais uma falha após o reset
        breaker.record_failure()

        metrics = breaker.get_metrics()

        assert metrics['name'] == 'test_breaker'
        assert metrics['state'] == CircuitState.CLOSED.value
        # Após record_success em CLOSED, o contador é resetado para 0
        # Depois temos mais 1 falha, então o contador é 1
        assert metrics['failure_count'] == 1
        assert metrics['threshold'] == 5
        assert 'last_failure_time' in metrics
        assert 'last_state_change' in metrics

    def test_get_metrics_in_open_state(self):
        """
        DADO: Um circuit breaker em estado OPEN
        QUANDO: Chamo get_metrics
        ENTÃO: Deve incluir opened_at
        """
        breaker = CircuitBreaker(
            name='test_breaker',
            threshold=3,
            timeout_seconds=1000
        )

        # Forçar para OPEN
        breaker.record_failure()
        breaker.record_failure()
        breaker.record_failure()

        metrics = breaker.get_metrics()

        assert metrics['state'] == CircuitState.OPEN.value
        assert 'opened_at' in metrics


# ===== TESTES: Reset =====


class TestCircuitBreakerReset:
    """Testes de reset do Circuit Breaker."""

    def test_reset_returns_to_closed(self):
        """
        DADO: Um circuit breaker em estado OPEN
        QUANDO: Chamo reset
        ENTÃO: Deve voltar para CLOSED com contador zerado
        """
        breaker = CircuitBreaker(
            name='test_breaker',
            threshold=3,
            timeout_seconds=1000
        )

        # Forçar para OPEN
        breaker.record_failure()
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

        # Reset
        breaker.reset()

        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0
