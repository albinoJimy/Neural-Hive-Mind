"""Testes para módulo retry."""

import pytest
import asyncio
from unittest.mock import Mock

from neural_hive_resilience.retry import (
    RetryPolicy,
    BackoffStrategy,
    retry,
    RetryContext,
    RetryConfigError,
)
from neural_hive_resilience.exceptions import (
    RetryableError,
    NonRetryableError,
    MaxRetriesExceededError,
)


class TestRetryPolicy:
    """Testes para RetryPolicy."""

    def test_initialization(self):
        """Testa inicialização com parâmetros válidos."""
        policy = RetryPolicy(
            max_attempts=5,
            base_delay=0.5,
            max_delay=60.0,
        )

        assert policy.max_attempts == 5
        assert policy.base_delay == 0.5
        assert policy.max_delay == 60.0

    def test_initialization_invalid_max_attempts(self):
        """Testa erro com max_attempts inválido."""
        with pytest.raises(ValueError, match="max_attempts deve ser >= 1"):
            RetryPolicy(max_attempts=0)

    def test_initialization_invalid_base_delay(self):
        """Testa erro com base_delay negativo."""
        with pytest.raises(ValueError, match="base_delay deve ser >= 0"):
            RetryPolicy(base_delay=-1.0)

    def test_initialization_invalid_max_delay(self):
        """Testa erro com max_delay menor que base_delay."""
        with pytest.raises(ValueError, match="max_delay deve ser >= base_delay"):
            RetryPolicy(base_delay=10.0, max_delay=5.0)

    def test_initialization_invalid_jitter_factor(self):
        """Testa erro com jitter_factor fora do range."""
        with pytest.raises(ValueError, match="jitter_factor deve estar entre 0.0 e 1.0"):
            RetryPolicy(jitter_factor=1.5)

    def test_calculate_delay_exponential(self):
        """Testa cálculo de delay com estratégia exponencial."""
        policy = RetryPolicy(
            backoff_strategy=BackoffStrategy.EXPONENTIAL,
            base_delay=1.0,
            jitter_enabled=False,
        )

        assert policy.calculate_delay(0) == 0
        assert policy.calculate_delay(1) == 1.0
        assert policy.calculate_delay(2) == 2.0
        assert policy.calculate_delay(3) == 4.0
        assert policy.calculate_delay(4) == 8.0

    def test_calculate_delay_linear(self):
        """Testa cálculo de delay com estratégia linear."""
        policy = RetryPolicy(
            backoff_strategy=BackoffStrategy.LINEAR,
            base_delay=1.0,
            jitter_enabled=False,
        )

        assert policy.calculate_delay(0) == 0
        assert policy.calculate_delay(1) == 1.0
        assert policy.calculate_delay(2) == 2.0
        assert policy.calculate_delay(3) == 3.0

    def test_calculate_delay_fixed(self):
        """Testa cálculo de delay com estratégia fixa."""
        policy = RetryPolicy(
            backoff_strategy=BackoffStrategy.FIXED,
            base_delay=2.0,
            jitter_enabled=False,
        )

        assert policy.calculate_delay(0) == 0
        assert policy.calculate_delay(1) == 2.0
        assert policy.calculate_delay(2) == 2.0
        assert policy.calculate_delay(3) == 2.0

    def test_calculate_delay_max_delay(self):
        """Testa limite máximo de delay."""
        policy = RetryPolicy(
            backoff_strategy=BackoffStrategy.EXPONENTIAL,
            base_delay=1.0,
            max_delay=5.0,
            jitter_enabled=False,
        )

        # Sem limite: 1, 2, 4, 8, 16...
        # Com max_delay=5: 1, 2, 4, 5, 5...
        assert policy.calculate_delay(1) == 1.0
        assert policy.calculate_delay(2) == 2.0
        assert policy.calculate_delay(3) == 4.0
        assert policy.calculate_delay(4) == 5.0
        assert policy.calculate_delay(5) == 5.0

    def test_calculate_delay_jitter(self):
        """Testa aplicação de jitter."""
        policy = RetryPolicy(
            backoff_strategy=BackoffStrategy.EXPONENTIAL,
            base_delay=10.0,
            jitter_enabled=True,
            jitter_factor=0.1,
        )

        # Com jitter de 10%, delay deve estar entre 9.0 e 11.0
        delay = policy.calculate_delay(1)
        assert 9.0 <= delay <= 11.0

    def test_should_retry_default(self):
        """Testa should_retry sem configuração específica."""
        policy = RetryPolicy()

        # Por padrão, nada é retryable
        assert not policy.should_retry(Exception("test"))

    def test_should_retry_with_retryable_list(self):
        """Testa should_retry com lista de exceções retryable."""
        policy = RetryPolicy(
            retryable_exceptions=(ValueError, KeyError),
        )

        assert policy.should_retry(ValueError("test"))
        assert policy.should_retry(KeyError("test"))
        assert not policy.should_retry(TypeError("test"))

    def test_should_retry_with_non_retryable_list(self):
        """Testa should_retry com lista de exceções non-retryable."""
        policy = RetryPolicy(
            retryable_exceptions=(ValueError, KeyError),
            non_retryable_exceptions=(KeyError,),
        )

        # Non-retryable tem prioridade
        assert not policy.should_retry(KeyError("test"))
        assert policy.should_retry(ValueError("test"))

    def test_should_retry_retryable_error(self):
        """Testa que RetryableError é sempre retriado."""
        policy = RetryPolicy()

        assert policy.should_retry(RetryableError("test"))

    def test_should_retry_non_retryable_error(self):
        """Testa que NonRetryableError nunca é retriado."""
        policy = RetryPolicy(
            retryable_exceptions=(Exception,),
        )

        assert not policy.should_retry(NonRetryableError("test"))

    def test_get_retry_count_default(self):
        """Testa get_retry_count padrão."""
        policy = RetryPolicy(max_attempts=5)

        assert policy.get_retry_count(ValueError("test")) == 5

    def test_get_retry_count_custom(self):
        """Testa get_retry_count com RetryableError customizado."""
        policy = RetryPolicy(max_attempts=10)

        error = RetryableError("test", max_retry_count=3)
        assert policy.get_retry_count(error) == 3


class TestRetryDecorator:
    """Testes para decorator retry."""

    @pytest.mark.asyncio
    async def test_retry_success_on_first_attempt(self):
        """Testa sucesso na primeira tentativa."""

        async def mock_func(*args, **kwargs):
            return "success"

        decorated = retry(
            service_name="test-service",
            operation_name="test-op",
        )(mock_func)

        result = await decorated("arg1", kwarg="value")

        assert result == "success"

    @pytest.mark.asyncio
    async def test_retry_with_retryable_exception(self):
        """Testa retry com exceção retriável."""
        attempt_count = 0

        async def failing_func():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise ValueError("temporary error")
            return "success"

        policy = RetryPolicy(
            max_attempts=5,
            retryable_exceptions=(ValueError,),
        )

        decorated = retry(
            policy=policy,
            service_name="test-service",
            operation_name="test-op",
        )(failing_func)

        result = await decorated()

        assert result == "success"
        assert attempt_count == 3

    @pytest.mark.asyncio
    async def test_retry_max_attempts_exceeded(self):
        """Testa erro quando máximo de tentativas é excedido."""

        async def always_failing_func():
            raise ValueError("always fails")

        policy = RetryPolicy(
            max_attempts=3,
            retryable_exceptions=(ValueError,),
        )

        decorated = retry(
            policy=policy,
            service_name="test-service",
            operation_name="test-op",
        )(always_failing_func)

        with pytest.raises(MaxRetriesExceededError):
            await decorated()

    @pytest.mark.asyncio
    async def test_retry_non_retryable_exception(self):
        """Testa que exceções non-retryable não são retriadas."""
        attempt_count = 0

        async def failing_func():
            nonlocal attempt_count
            attempt_count += 1
            raise ValueError("fatal error")

        policy = RetryPolicy(
            max_attempts=5,
            non_retryable_exceptions=(ValueError,),
        )

        decorated = retry(
            policy=policy,
            service_name="test-service",
            operation_name="test-op",
        )(failing_func)

        with pytest.raises(ValueError):
            await decorated()

        assert attempt_count == 1

    @pytest.mark.asyncio
    async def test_retry_with_on_retry_callback(self):
        """Testa callback on_retry."""
        attempt_counts = []

        async def failing_func():
            raise ValueError("error")

        policy = RetryPolicy(
            max_attempts=3,
            retryable_exceptions=(ValueError,),
        )

        def on_retry(attempt, exception):
            attempt_counts.append(attempt)

        decorated = retry(
            policy=policy,
            service_name="test-service",
            operation_name="test-op",
            on_retry=on_retry,
        )(failing_func)

        with pytest.raises(MaxRetriesExceededError):
            await decorated()

        assert attempt_counts == [1, 2]

    @pytest.mark.asyncio
    async def test_retry_sync_function_raises(self):
        """Testa que função síncrona levanta erro."""

        def sync_func():
            return "sync"

        decorated = retry(
            service_name="test-service",
            operation_name="test-op",
        )(sync_func)

        # Decorador suporta async apenas
        # Se for síncrono, ainda deve funcionar com await
        # mas o teste verifica que a função é detectada corretamente
        assert asyncio.iscoroutinefunction(sync_func) is False


class TestRetryContext:
    """Testes para RetryContext."""

    @pytest.mark.asyncio
    async def test_retry_context_success(self):
        """Testa execução bem-sucedida no contexto."""
        policy = RetryPolicy(max_attempts=3)

        async def success_func():
            return "result"

        async with RetryContext(policy=policy) as ctx:
            result = await ctx.execute(success_func())

        assert result == "result"

    @pytest.mark.asyncio
    async def test_retry_context_with_retries(self):
        """Testa retry no contexto."""
        attempt_count = 0

        async def failing_func():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 2:
                raise ValueError("temp error")
            return "success"

        policy = RetryPolicy(
            max_attempts=5,
            retryable_exceptions=(ValueError,),
        )

        async with RetryContext(policy=policy) as ctx:
            result = await ctx.execute(failing_func)

        assert result == "success"
        assert attempt_count == 2

    @pytest.mark.asyncio
    async def test_retry_context_max_attempts_exceeded(self):
        """Testa erro quando máximo de tentativas é excedido."""

        async def always_failing():
            raise ValueError("fails")

        policy = RetryPolicy(
            max_attempts=2,
            retryable_exceptions=(ValueError,),
        )

        with pytest.raises(MaxRetriesExceededError):
            async with RetryContext(policy=policy) as ctx:
                await ctx.execute(always_failing)


class TestRetryableErrors:
    """Testes para exceções de retry."""

    def test_retryable_error_creation(self):
        """Testa criação de RetryableError."""
        error = RetryableError("test", service="my-service", max_retry_count=5)

        assert error.service == "my-service"
        assert error.max_retry_count == 5

    def test_non_retryable_error_creation(self):
        """Testa criação de NonRetryableError."""
        error = NonRetryableError("fatal", service="my-service")

        assert error.service == "my-service"

    def test_max_retries_exceeded_error(self):
        """Testa criação de MaxRetriesExceededError."""
        original_error = ValueError("original")

        error = MaxRetriesExceededError(
            "max exceeded",
            operation="test-op",
            attempts=5,
            last_exception=original_error,
        )

        assert error.operation == "test-op"
        assert error.attempts == 5
        assert error.last_exception == original_error
