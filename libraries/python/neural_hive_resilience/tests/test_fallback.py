"""Testes para módulo fallback."""

import pytest
import asyncio

from neural_hive_resilience.fallback import (
    FallbackChain,
    FallbackConfig,
    FallbackStrategy,
    ConditionalFallback,
    with_fallback,
)

# Alias para compatibilidade
fallback = with_fallback
from neural_hive_resilience.exceptions import AllFallbacksFailedError


class TestFallbackConfig:
    """Testes para FallbackConfig."""

    def test_creation(self):
        """Testa criação de configuração."""

        async def dummy_fallback():
            return "fallback"

        config = FallbackConfig(
            name="test",
            func=dummy_fallback,
        )

        assert config.name == "test"
        assert config.func == dummy_fallback
        assert config.should_execute is None
        assert config.timeout is None

    def test_creation_with_options(self):
        """Testa criação com opções."""

        async def dummy_fallback():
            return "fallback"

        def condition():
            return True

        config = FallbackConfig(
            name="test",
            func=dummy_fallback,
            should_execute=condition,
            timeout=5.0,
        )

        assert config.should_execute == condition
        assert config.timeout == 5.0


class TestFallbackChain:
    """Testes para FallbackChain."""

    @pytest.mark.asyncio
    async def test_primary_success(self):
        """Testa sucesso na função primária."""
        fallbacks = [
            FallbackConfig(name="cache", func=lambda: "cache_value"),
            FallbackConfig(name="static", func=lambda: "static_value"),
        ]

        chain = FallbackChain(
            service_name="test-service",
            operation_name="test-op",
            fallbacks=fallbacks,
        )

        async def primary():
            return "primary_value"

        result = await chain.execute(primary)

        assert result.success is True
        assert result.result == "primary_value"
        assert result.source == "primary"
        assert result.attempt == 0

    @pytest.mark.asyncio
    async def test_first_fallback_success(self):
        """Testa sucesso no primeiro fallback."""

        async def cache_fallback():
            await asyncio.sleep(0.01)
            return "cache_value"

        async def static_fallback():
            return "static_value"

        fallbacks = [
            FallbackConfig(name="cache", func=cache_fallback),
            FallbackConfig(name="static", func=static_fallback),
        ]

        chain = FallbackChain(
            service_name="test-service",
            operation_name="test-op",
            fallbacks=fallbacks,
        )

        async def primary():
            raise ValueError("primary failed")

        result = await chain.execute(primary)

        assert result.success is True
        assert result.result == "cache_value"
        assert result.source == "cache"
        assert result.attempt == 1

    @pytest.mark.asyncio
    async def test_second_fallback_success(self):
        """Testa sucesso no segundo fallback."""

        async def cache_fallback():
            raise ValueError("cache failed")

        async def static_fallback():
            await asyncio.sleep(0.01)
            return "static_value"

        fallbacks = [
            FallbackConfig(name="cache", func=cache_fallback),
            FallbackConfig(name="static", func=static_fallback),
        ]

        chain = FallbackChain(
            service_name="test-service",
            operation_name="test-op",
            fallbacks=fallbacks,
        )

        async def primary():
            raise ValueError("primary failed")

        result = await chain.execute(primary)

        assert result.success is True
        assert result.result == "static_value"
        assert result.source == "static"
        assert result.attempt == 2

    @pytest.mark.asyncio
    async def test_all_fallbacks_failed(self):
        """Testa erro quando todos os fallbacks falham."""

        async def fallback1():
            raise ValueError("failed")

        async def fallback2():
            raise ValueError("failed")

        fallbacks = [
            FallbackConfig(name="fallback1", func=fallback1),
            FallbackConfig(name="fallback2", func=fallback2),
        ]

        chain = FallbackChain(
            service_name="test-service",
            operation_name="test-op",
            fallbacks=fallbacks,
        )

        async def primary():
            raise ValueError("primary failed")

        with pytest.raises(AllFallbacksFailedError) as exc_info:
            await chain.execute(primary)

        assert exc_info.value.service == "test-service"
        assert len(exc_info.value.exceptions) == 3  # primary + 2 fallbacks

    @pytest.mark.asyncio
    async def test_fallback_with_should_execute(self):
        """Testa fallback com condição should_execute."""
        call_count = {"primary": 0, "fallback1": 0}

        async def primary():
            call_count["primary"] += 1
            raise ValueError("failed")

        async def fallback1():
            call_count["fallback1"] += 1
            return "fallback1_value"

        def should_execute_fallback1():
            return call_count["primary"] >= 1

        fallbacks = [
            FallbackConfig(
                name="fallback1",
                func=fallback1,
                should_execute=should_execute_fallback1,
            ),
        ]

        chain = FallbackChain(
            service_name="test-service",
            operation_name="test-op",
            fallbacks=fallbacks,
        )

        result = await chain.execute(primary)

        assert result.success is True
        assert result.result == "fallback1_value"
        assert call_count["fallback1"] == 1

    @pytest.mark.asyncio
    async def test_fastest_strategy(self):
        """Testa estratégia fastest."""
        execution_delays = {
            "primary": 0.2,  # Maior delay para garantir que não ganha
            "fallback1": 0.05,
            "fallback2": 0.15,
        }

        async def delayed_func(name):
            await asyncio.sleep(execution_delays[name])
            return f"{name}_result"

        async def primary_func():
            return await delayed_func("primary")

        async def fallback1_func():
            return await delayed_func("fallback1")

        async def fallback2_func():
            return await delayed_func("fallback2")

        fallbacks = [
            FallbackConfig(name="fallback1", func=fallback1_func),
            FallbackConfig(name="fallback2", func=fallback2_func),
        ]

        chain = FallbackChain(
            service_name="test-service",
            operation_name="test-op",
            fallbacks=fallbacks,
            strategy=FallbackStrategy.FASTEST,
        )

        result = await chain.execute(primary_func)

        # fallback1 deve ganhar (0.05s) - é o mais rápido
        # ou não deve ser "primary" (que tem delay maior)
        assert result.source != "primary"
        assert result.success is True
        assert result.result in ["fallback1_result", "fallback2_result"]


class TestConditionalFallback:
    """Testes para ConditionalFallback."""

    @pytest.mark.asyncio
    async def test_condition_met(self):
        """Testa execução quando condição é atendida."""

        async def fallback(*args, **kwargs):
            return "fallback_value"

        def is_timeout_error(exc):
            return isinstance(exc, asyncio.TimeoutError)

        conditional = ConditionalFallback(
            service_name="test-service",
            operation_name="test-op",
            fallback_func=fallback,
            condition=is_timeout_error,
        )

        async def primary():
            raise asyncio.TimeoutError()

        result = await conditional.execute(primary)
        assert result == "fallback_value"

    @pytest.mark.asyncio
    async def test_condition_not_met(self):
        """Testa erro quando condição não é atendida."""

        async def fallback(*args, **kwargs):
            return "fallback_value"

        def is_timeout_error(exc):
            return isinstance(exc, asyncio.TimeoutError)

        conditional = ConditionalFallback(
            service_name="test-service",
            operation_name="test-op",
            fallback_func=fallback,
            condition=is_timeout_error,
        )

        async def primary():
            raise ValueError("other error")

        with pytest.raises(ValueError):
            await conditional.execute(primary)


class TestFallbackDecorator:
    """Testes para decorator fallback."""

    @pytest.mark.asyncio
    async def test_decorator_success(self):
        """Testa que decorator não interfere em sucesso."""

        async def fallback_fn(*args, **kwargs):
            return "fallback"

        @with_fallback(
            fallback_func=fallback_fn,
            service_name="test-service",
        )
        async def primary_func():
            return "primary"

        result = await primary_func()
        assert result == "primary"

    @pytest.mark.asyncio
    async def test_decorator_fallback_triggered(self):
        """Testa que fallback é executado em falha."""

        async def fallback_fn(*args, **kwargs):
            return "fallback_value"

        @with_fallback(
            fallback_func=fallback_fn,
            service_name="test-service",
        )
        async def failing_func():
            raise ValueError("error")

        result = await failing_func()
        assert result == "fallback_value"

    @pytest.mark.asyncio
    async def test_decorator_with_args(self):
        """Testa que fallback recebe argumentos corretamente."""
        received_args = None

        async def fallback_fn(*args, **kwargs):
            nonlocal received_args
            received_args = (args, kwargs)
            return "fallback"

        @with_fallback(fallback_func=fallback_fn)
        async def failing_func(arg1, arg2, kwarg=None):
            raise ValueError("error")

        result = await failing_func("a", "b", kwarg="c")
        assert result == "fallback"
        assert received_args == (("a", "b"), {"kwarg": "c"})

    def test_decorator_sync_function_raises(self):
        """Testa erro ao aplicar decorator a função síncrona."""

        async def fallback_fn(*args, **kwargs):
            return "fallback"

        with pytest.raises(TypeError, match="só suporta funções assíncronas"):

            @with_fallback(fallback_func=fallback_fn)
            def sync_func():
                return "sync"
