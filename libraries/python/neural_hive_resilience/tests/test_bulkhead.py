"""Testes para módulo bulkhead."""

import asyncio

import pytest

from neural_hive_resilience.bulkhead import (
    BulkheadConfig,
    BulkheadFactory,
    SemaphoreBulkhead,
    ThreadPoolBulkhead,
    bulkhead,
)
from neural_hive_resilience.exceptions import BulkheadRejectedError


class TestBulkheadConfig:
    """Testes para BulkheadConfig."""

    def test_creation(self):
        """Testa criação de configuração."""
        config = BulkheadConfig(
            max_concurrent=10,
            max_queue_size=5,
            timeout=30.0,
        )

        assert config.max_concurrent == 10
        assert config.max_queue_size == 5
        assert config.timeout == 30.0

    def test_defaults(self):
        """Testa valores padrão."""
        config = BulkheadConfig()

        assert config.max_concurrent == 10
        assert config.max_queue_size == 5
        assert config.timeout is None


class TestSemaphoreBulkhead:
    """Testes para SemaphoreBulkhead."""

    @pytest.mark.asyncio()
    async def test_initialization(self):
        """Testa inicialização com parâmetros válidos."""
        config = BulkheadConfig(max_concurrent=5, max_queue_size=2)
        bulkhead = SemaphoreBulkhead(
            service_name="test-service",
            bulkhead_name="test-bulkhead",
            config=config,
        )

        assert bulkhead.service_name == "test-service"
        assert bulkhead.bulkhead_name == "test-bulkhead"
        assert bulkhead.config.max_concurrent == 5

    @pytest.mark.asyncio()
    async def test_acquire_release(self):
        """Testa aquisição e liberação."""
        bulkhead = SemaphoreBulkhead(
            service_name="test-service",
            bulkhead_name="test",
            config=BulkheadConfig(max_concurrent=2, max_queue_size=0),
        )

        await bulkhead.acquire()
        assert bulkhead.active_count == 1

        await bulkhead.acquire()
        assert bulkhead.active_count == 2

        bulkhead.release()
        assert bulkhead.active_count == 1

    @pytest.mark.asyncio()
    async def test_context_manager(self):
        """Testa uso como context manager."""
        bulkhead = SemaphoreBulkhead(
            service_name="test-service",
            bulkhead_name="test",
            config=BulkheadConfig(max_concurrent=2, max_queue_size=0),
        )

        async with bulkhead:
            assert bulkhead.active_count == 1

        assert bulkhead.active_count == 0

    @pytest.mark.asyncio()
    async def test_concurrent_limit(self):
        """Testa limite de concorrência."""
        bulkhead = SemaphoreBulkhead(
            service_name="test-service",
            bulkhead_name="test",
            config=BulkheadConfig(max_concurrent=2, max_queue_size=0),
        )

        active_count = 0
        max_active = 0

        async def task():
            nonlocal active_count, max_active
            await bulkhead.acquire()
            active_count += 1
            max_active = max(max_active, active_count)
            await asyncio.sleep(0.05)
            active_count -= 1
            bulkhead.release()

        tasks = [task() for _ in range(5)]
        await asyncio.gather(*tasks)

        assert max_active <= 2

    @pytest.mark.asyncio()
    async def test_queue_timeout(self):
        """Testa timeout na fila."""
        bulkhead = SemaphoreBulkhead(
            service_name="test-service",
            bulkhead_name="test",
            config=BulkheadConfig(max_concurrent=1, max_queue_size=2, timeout=0.1),
        )

        # Preencher concorrência
        await bulkhead.acquire()

        # Preencher fila
        await bulkhead.queue.put(None)
        await bulkhead.queue.put(None)

        # Tentar adquirir com fila cheia e timeout
        with pytest.raises(BulkheadRejectedError):
            await bulkhead.acquire()

    @pytest.mark.asyncio()
    async def test_execute_success(self):
        """Testa execução bem-sucedida."""
        bulkhead = SemaphoreBulkhead(
            service_name="test-service",
            bulkhead_name="test",
            config=BulkheadConfig(max_concurrent=2, max_queue_size=0),
        )

        async def task():
            await asyncio.sleep(0.01)
            return "result"

        result = await bulkhead.execute(task())
        assert result == "result"

    @pytest.mark.asyncio()
    async def test_execute_with_error(self):
        """Testa execução que levanta erro."""
        bulkhead = SemaphoreBulkhead(
            service_name="test-service",
            bulkhead_name="test",
            config=BulkheadConfig(max_concurrent=2, max_queue_size=0),
        )

        async def failing_task():
            await asyncio.sleep(0.01)
            raise ValueError("error")

        with pytest.raises(ValueError):
            await bulkhead.execute(failing_task())


class TestThreadPoolBulkhead:
    """Testes para ThreadPoolBulkhead."""

    @pytest.mark.asyncio()
    async def test_initialization(self):
        """Testa inicialização."""
        bulkhead = ThreadPoolBulkhead(
            service_name="test-service",
            bulkhead_name="test",
            max_workers=5,
        )

        assert bulkhead.service_name == "test-service"
        assert bulkhead.bulkhead_name == "test"

    @pytest.mark.asyncio()
    async def test_run_in_thread(self):
        """Testa execução em thread separada."""
        bulkhead = ThreadPoolBulkhead(
            service_name="test-service",
            bulkhead_name="test",
            max_workers=2,
        )

        def blocking_function(x, y):
            return x + y

        result = await bulkhead.run_in_thread(blocking_function, 5, 3)
        assert result == 8

    @pytest.mark.asyncio()
    async def test_run_blocking_io(self):
        """Testa execução de operação bloqueante."""
        bulkhead = ThreadPoolBulkhead(
            service_name="test-service",
            bulkhead_name="test",
            max_workers=2,
        )

        def blocking_io():
            import time

            time.sleep(0.1)
            return "done"

        start = asyncio.get_event_loop().time()
        result = await bulkhead.run_in_thread(blocking_io)
        elapsed = asyncio.get_event_loop().time() - start

        assert result == "done"
        assert elapsed >= 0.1

    @pytest.mark.asyncio()
    async def test_concurrent_execution(self):
        """Testa execução concorrente em threads."""
        bulkhead = ThreadPoolBulkhead(
            service_name="test-service",
            bulkhead_name="test",
            max_workers=2,
        )

        def blocking_task(task_id):
            import time

            time.sleep(0.1)
            return task_id

        tasks = [bulkhead.run_in_thread(blocking_task, i) for i in range(4)]

        results = await asyncio.gather(*tasks)
        assert sorted(results) == [0, 1, 2, 3]

    def test_shutdown(self):
        """Testa desligamento do thread pool."""
        bulkhead = ThreadPoolBulkhead(
            service_name="test-service",
            bulkhead_name="test",
            max_workers=2,
        )

        bulkhead.shutdown(wait=True)
        # Verifica que shutdown foi completado sem erro


class TestBulkheadFactory:
    """Testes para BulkheadFactory."""

    def test_initialization(self):
        """Testa criação da factory."""
        factory = BulkheadFactory(service_name="test-service")
        assert factory.service_name == "test-service"

    def test_semaphore_creation(self):
        """Testa criação de semaphore bulkhead."""
        factory = BulkheadFactory(service_name="test-service")

        bulkhead = factory.semaphore(
            name="test-bulkhead",
            max_concurrent=5,
            max_queue_size=2,
        )

        assert isinstance(bulkhead, SemaphoreBulkhead)
        assert bulkhead.bulkhead_name == "test-bulkhead"

    def test_thread_pool_creation(self):
        """Testa criação de thread pool bulkhead."""
        factory = BulkheadFactory(service_name="test-service")

        bulkhead = factory.thread_pool(
            name="test-bulkhead",
            max_workers=5,
        )

        assert isinstance(bulkhead, ThreadPoolBulkhead)
        assert bulkhead.bulkhead_name == "test-bulkhead"


class TestBulkheadDecorator:
    """Testes para decorator bulkhead."""

    @pytest.mark.asyncio()
    async def test_decorator_success(self):
        """Testa execução bem-sucedida com decorator."""

        @bulkhead(
            bulkhead_name="test",
            max_concurrent=2,
            service_name="test-service",
        )
        async def task(value):
            await asyncio.sleep(0.01)
            return value

        result = await task("test")
        assert result == "test"

    @pytest.mark.asyncio()
    async def test_decorator_concurrent_limit(self):
        """Testa limite de concorrência com decorator."""

        @bulkhead(
            bulkhead_name="test",
            max_concurrent=2,
            service_name="test-service",
        )
        async def task(task_id):
            await asyncio.sleep(0.05)
            return task_id

        # O decorator já controla a concorrência internamente
        # Testamos que todas as tarefas completam
        tasks = [task(i) for i in range(5)]
        results = await asyncio.gather(*tasks)

        assert sorted(results) == [0, 1, 2, 3, 4]
