"""Testes para módulo timeout."""

import pytest
import asyncio

from neural_hive_resilience.timeout import (
    timeout,
    timeout_with_fallback,
    TimeoutContext,
    TimeoutWithFallback,
)
from neural_hive_resilience.exceptions import TimeoutError as ResilienceTimeoutError


class TestTimeoutDecorator:
    """Testes para decorator timeout."""

    @pytest.mark.asyncio
    async def test_timeout_success_before_limit(self):
        """Testa sucesso antes do limite."""

        @timeout(timeout_seconds=1.0, service_name="test-service")
        async def quick_function():
            await asyncio.sleep(0.1)
            return "success"

        result = await quick_function()
        assert result == "success"

    @pytest.mark.asyncio
    async def test_timeout_exceeded(self):
        """Testa erro quando timeout é excedido."""

        @timeout(timeout_seconds=0.1, service_name="test-service")
        async def slow_function():
            await asyncio.sleep(1.0)
            return "never reached"

        with pytest.raises(ResilienceTimeoutError) as exc_info:
            await slow_function()

        assert exc_info.value.service == "test-service"
        assert exc_info.value.timeout_seconds == 0.1

    @pytest.mark.asyncio
    async def test_timeout_with_operation_name(self):
        """Testa timeout com nome de operação customizado."""

        @timeout(
            timeout_seconds=0.1,
            service_name="test-service",
            operation_name="custom-op",
        )
        async def slow_function():
            await asyncio.sleep(1.0)

        with pytest.raises(ResilienceTimeoutError) as exc_info:
            await slow_function()

        assert "custom-op" in str(exc_info.value)

    def test_timeout_sync_function_raises(self):
        """Testa erro ao aplicar decorator a função síncrona."""
        with pytest.raises(TypeError, match="só suporta funções assíncronas"):

            @timeout(timeout_seconds=1.0)
            def sync_function():
                return "sync"

    def test_timeout_invalid_value(self):
        """Testa erro com valor de timeout inválido."""
        with pytest.raises(ValueError, match="timeout_seconds deve ser > 0"):

            @timeout(timeout_seconds=0)
            async def func():
                pass


class TestTimeoutWithFallbackDecorator:
    """Testes para decorator timeout_with_fallback."""

    @pytest.mark.asyncio
    async def test_fallback_not_triggered_on_success(self):
        """Testa que fallback não é executado em caso de sucesso."""
        fallback_called = False

        async def fallback():
            nonlocal fallback_called
            fallback_called = True
            return "fallback"

        @timeout_with_fallback(
            timeout_seconds=1.0,
            fallback_func=fallback,
            service_name="test-service",
        )
        async def quick_function():
            return "success"

        result = await quick_function()
        assert result == "success"
        assert fallback_called is False

    @pytest.mark.asyncio
    async def test_fallback_triggered_on_timeout(self):
        """Testa que fallback é executado em timeout."""
        fallback_called = False

        async def fallback():
            nonlocal fallback_called
            fallback_called = True
            return "fallback_result"

        @timeout_with_fallback(
            timeout_seconds=0.1,
            fallback_func=fallback,
            service_name="test-service",
        )
        async def slow_function():
            await asyncio.sleep(1.0)
            return "never reached"

        result = await slow_function()
        assert result == "fallback_result"
        assert fallback_called is True

    @pytest.mark.asyncio
    async def test_fallback_with_args(self):
        """Testa que fallback recebe os mesmos argumentos."""
        received_args = None

        async def fallback(*args, **kwargs):
            nonlocal received_args
            received_args = (args, kwargs)
            return "fallback"

        @timeout_with_fallback(
            timeout_seconds=0.1,
            fallback_func=fallback,
        )
        async def slow_function(arg1, arg2, kwarg1=None):
            await asyncio.sleep(1.0)
            return "never reached"

        result = await slow_function("a", "b", kwarg1="c")
        assert result == "fallback"
        assert received_args == (("a", "b"), {"kwarg1": "c"})


class TestTimeoutContext:
    """Testes para TimeoutContext."""

    @pytest.mark.asyncio
    async def test_context_success(self):
        """Testa execução bem-sucedida no contexto."""
        context = TimeoutContext(timeout_seconds=1.0)

        async def quick_func():
            return "result"

        async with context:
            result = await context.execute(quick_func())

        assert result == "result"

    @pytest.mark.asyncio
    async def test_context_timeout_exceeded(self):
        """Testa timeout no contexto."""
        context = TimeoutContext(
            timeout_seconds=0.1,
            service_name="test-service",
        )

        async def slow_func():
            await asyncio.sleep(1.0)
            return "never reached"

        with pytest.raises(ResilienceTimeoutError):
            async with context:
                await context.execute(slow_func())

    @pytest.mark.asyncio
    async def test_context_cancel_on_timeout(self):
        """Testa que tarefa é cancelada em timeout."""
        context = TimeoutContext(timeout_seconds=0.1)

        task_running = True

        async def slow_func():
            nonlocal task_running
            try:
                await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                task_running = False
                raise

        with pytest.raises(ResilienceTimeoutError):
            async with context:
                await context.execute(slow_func())

        assert task_running is False

    def test_context_invalid_timeout(self):
        """Testa erro com timeout inválido."""
        with pytest.raises(ValueError, match="timeout_seconds deve ser > 0"):
            TimeoutContext(timeout_seconds=0)


class TestTimeoutWithFallback:
    """Testes para classe TimeoutWithFallback."""

    @pytest.mark.asyncio
    async def test_execute_success(self):
        """Testa execução bem-sucedida."""
        fallback_called = False

        async def fallback(*args, **kwargs):
            nonlocal fallback_called
            fallback_called = True
            return "fallback"

        timeout_fallback = TimeoutWithFallback(
            timeout_seconds=1.0,
            fallback_func=fallback,
            service_name="test-service",
        )

        async def main_func():
            return "main_result"

        result = await timeout_fallback.execute(main_func())
        assert result == "main_result"
        assert fallback_called is False

    @pytest.mark.asyncio
    async def test_execute_with_fallback(self):
        """Testa execução com fallback em timeout."""
        fallback_called = False

        async def fallback(*args, **kwargs):
            nonlocal fallback_called
            fallback_called = True
            return "fallback_result"

        timeout_fallback = TimeoutWithFallback(
            timeout_seconds=0.1,
            fallback_func=fallback,
            service_name="test-service",
        )

        async def slow_func():
            await asyncio.sleep(1.0)
            return "never reached"

        result = await timeout_fallback.execute(slow_func())
        assert result == "fallback_result"
        assert fallback_called is True
