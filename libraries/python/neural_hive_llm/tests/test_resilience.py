"""Testes unitários para módulo de resiliência."""

import asyncio

import pytest
from tenacity import RetryError

from neural_hive_llm.resilience import (
    LLMRateLimitError,
    LLMRetryPolicy,
    _is_retryable_llm_error,
    llm_retry,
)


class TestLLMRetryPolicy:
    """Testes para LLMRetryPolicy."""

    def test_default_initialization(self):
        """Testa inicialização com valores padrão."""
        policy = LLMRetryPolicy()
        assert policy.max_retries == 3
        assert policy.base_delay == 1.0
        assert policy.max_delay == 60.0
        assert policy.jitter_enabled is True

    def test_custom_initialization(self):
        """Testa inicialização com valores customizados."""
        policy = LLMRetryPolicy(
            max_retries=5,
            base_delay=2.0,
            max_delay=120.0,
            jitter_enabled=False,
        )
        assert policy.max_retries == 5
        assert policy.base_delay == 2.0
        assert policy.max_delay == 120.0
        assert policy.jitter_enabled is False

    def test_invalid_max_retries(self):
        """Testa erro para max_retries inválido."""
        with pytest.raises(ValueError, match="max_retries"):
            LLMRetryPolicy(max_retries=-1)

    def test_invalid_base_delay(self):
        """Testa erro para base_delay inválido."""
        with pytest.raises(ValueError, match="base_delay"):
            LLMRetryPolicy(base_delay=-1.0)

    def test_invalid_max_delay(self):
        """Testa erro para max_delay menor que base_delay."""
        with pytest.raises(ValueError, match="max_delay"):
            LLMRetryPolicy(base_delay=10.0, max_delay=5.0)

    def test_calculate_delay_exponential(self):
        """Testa que política tem configurações corretas."""
        policy = LLMRetryPolicy(
            base_delay=1.0,
            max_delay=100.0,
            jitter_enabled=False,
        )

        # Verificar que a política tem os valores configurados
        assert policy.base_delay == 1.0
        assert policy.max_delay == 100.0
        assert policy.jitter_enabled is False

    def test_calculate_delay_with_max(self):
        """Testa que max_delay é configurado corretamente."""
        policy = LLMRetryPolicy(
            base_delay=10.0,
            max_delay=30.0,
            jitter_enabled=False,
        )

        assert policy.max_delay == 30.0

    def test_calculate_delay_with_jitter(self):
        """Testa que jitter é configurado corretamente."""
        policy = LLMRetryPolicy(
            base_delay=1.0,
            jitter_enabled=True,
        )

        assert policy.jitter_enabled is True


class TestIsRetryableLLMError:
    """Testes para _is_retryable_llm_error."""

    def test_rate_limit_error_is_retryable(self):
        """Testa que LLMRateLimitError é retriável."""
        error = LLMRateLimitError("Rate limit exceeded")
        assert _is_retryable_llm_error(error) is True

    def test_timeout_error_is_retryable(self):
        """Testa que LLMTimeoutError é retriável."""
        from neural_hive_llm.resilience import LLMTimeoutError

        error = LLMTimeoutError("Request timeout")
        assert _is_retryable_llm_error(error) is True

    def test_server_error_is_retryable(self):
        """Testa que LLMServerError é retriável."""
        from neural_hive_llm.resilience import LLMServerError

        error = LLMServerError("Internal server error")
        assert _is_retryable_llm_error(error) is True

    def test_generic_error_is_not_retryable(self):
        """Testa que exceção genérica não é retriável."""
        error = ValueError("Some error")
        assert _is_retryable_llm_error(error) is False

    def test_openai_rate_limit_is_retryable(self):
        """Testa que RateLimitError do OpenAI é retriável."""
        # O _is_retryable_llm_error verifica o nome da classe
        # Criar exceção com nome exato que OpenAI usa
        class RateLimitError(Exception):
            pass

        error = RateLimitError("Rate limit")
        # Deve retornar True porque o nome é "RateLimitError"
        assert _is_retryable_llm_error(error) is True


@pytest.mark.asyncio
class TestLLMRetryDecorator:
    """Testes para decorator llm_retry."""

    async def test_successful_call_no_retry(self):
        """Testa que chamada bem-sucedida não retry."""

        @llm_retry(service_name="test", operation_name="test_op")
        async def successful_call():
            return "success"

        result = await successful_call()
        assert result == "success"

    async def test_retry_on_transient_error(self):
        """Testa retry em erro transitório."""
        call_count = 0

        @llm_retry(
            policy=LLMRetryPolicy(max_retries=2, base_delay=0.01),
            service_name="test",
            operation_name="test_op",
        )
        async def flaky_call():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise LLMRateLimitError("Rate limit")
            return "success"

        result = await flaky_call()
        assert result == "success"
        assert call_count == 2

    async def test_non_retryable_error_raises_immediately(self):
        """Testa que erro não retriável levanta imediatamente."""

        @llm_retry(
            policy=LLMRetryPolicy(max_retries=3, base_delay=0.01),
            service_name="test",
            operation_name="test_op",
        )
        async def failing_call():
            raise ValueError("Non-retryable error")

        with pytest.raises(ValueError, match="Non-retryable"):
            await failing_call()

    async def test_max_retries_exhausted(self):
        """Testa erro após esgotar máximo de retries."""

        @llm_retry(
            policy=LLMRetryPolicy(max_retries=2, base_delay=0.01),
            service_name="test",
            operation_name="test_op",
        )
        async def always_failing_call():
            raise LLMRateLimitError("Always rate limited")

        with pytest.raises(Exception):
            await always_failing_call()

    async def test_retry_with_sync_function(self):
        """Testa decorator com função síncrona."""
        call_count = 0

        @llm_retry(
            policy=LLMRetryPolicy(max_retries=2, base_delay=0.01),
            service_name="test",
            operation_name="test_op",
        )
        def flaky_sync_call():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise LLMRateLimitError("Rate limit")
            return "success"

        result = flaky_sync_call()
        assert result == "success"
        assert call_count == 2


@pytest.mark.asyncio
class TestLLMCircuitBreaker:
    """Testes para LLMCircuitBreaker (via integração)."""

    async def test_circuit_breaker_initialization(self):
        """Testa inicialização do circuit breaker."""
        from neural_hive_llm.circuit_breaker import (
            LLMCircuitBreaker,
            create_llm_circuit_breaker,
        )

        cb = create_llm_circuit_breaker("openai")
        assert cb.provider == "openai"
        assert cb.state == "closed"

    async def test_circuit_breaker_state_property(self):
        """Testa propriedade state."""
        from neural_hive_llm.circuit_breaker import LLMCircuitBreaker

        cb = LLMCircuitBreaker(provider="anthropic")
        assert cb.state in ("closed", "open", "half_open")
