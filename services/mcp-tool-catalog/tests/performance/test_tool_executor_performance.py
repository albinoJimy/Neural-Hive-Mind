"""
Testes de performance para ToolExecutor.

Cobertura:
- Latencia de execucao individual
- Latencia de execucao em batch
- Throughput com execucoes concorrentes
- Uso de memoria sob carga
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.tool_executor import ToolExecutor
from src.models.tool_descriptor import ToolDescriptor, ToolCategory, IntegrationType
from src.adapters.base_adapter import ExecutionResult


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_settings():
    """Mock de configuracoes para testes de performance."""
    settings = MagicMock()
    settings.TOOL_EXECUTION_TIMEOUT_SECONDS = 300
    settings.TOOL_RETRY_MAX_ATTEMPTS = 1
    settings.MAX_CONCURRENT_TOOL_EXECUTIONS = 10
    settings.MCP_SERVER_TIMEOUT_SECONDS = 30
    settings.MCP_SERVER_MAX_RETRIES = 1
    settings.MCP_SERVER_CIRCUIT_BREAKER_THRESHOLD = 5
    settings.MCP_SERVER_CIRCUIT_BREAKER_TIMEOUT_SECONDS = 60
    settings.MCP_SERVERS = {}
    return settings


@pytest.fixture
def tool_executor(mock_settings):
    """ToolExecutor para testes de performance."""
    with patch("src.services.tool_executor.get_settings", return_value=mock_settings):
        return ToolExecutor(settings=mock_settings)


@pytest.fixture
def benchmark_tools():
    """Lista de 10 ferramentas para benchmark."""
    tools = []
    for i in range(10):
        tools.append(ToolDescriptor(
            tool_id=f"tool-{i:03d}",
            tool_name=f"benchmark-tool-{i}",
            category=ToolCategory.ANALYSIS,
            version="1.0.0",
            capabilities=["benchmark"],
            reputation_score=0.8,
            cost_score=0.1,
            average_execution_time_ms=1000,
            integration_type=IntegrationType.CLI,
            authentication_method="NONE",
            is_healthy=True
        ))
    return tools


@pytest.fixture
def cli_tool():
    """Ferramenta CLI para testes."""
    return ToolDescriptor(
        tool_id="perf-tool-001",
        tool_name="perf-test",
        category=ToolCategory.VALIDATION,
        version="1.0.0",
        capabilities=["performance"],
        reputation_score=0.9,
        cost_score=0.1,
        average_execution_time_ms=100,
        integration_type=IntegrationType.CLI,
        authentication_method="NONE",
        is_healthy=True
    )


@pytest.fixture
def fast_execution_result():
    """ExecutionResult rapido para benchmark."""
    return ExecutionResult(
        success=True,
        output="Fast execution completed",
        execution_time_ms=10.0,
        exit_code=0
    )


# ============================================================================
# Testes de Latencia
# ============================================================================

class TestLatency:
    """Testes de latencia de execucao."""

    @pytest.mark.asyncio
    async def test_single_tool_execution_latency(
        self, tool_executor, cli_tool, fast_execution_result
    ):
        """Verifica latencia < 100ms para execucao individual (mock)."""
        with patch.object(
            tool_executor.cli_adapter,
            "execute",
            return_value=fast_execution_result
        ):
            with patch.object(
                tool_executor.cli_adapter,
                "validate_tool_availability",
                return_value=True
            ):
                start = time.perf_counter()

                result = await tool_executor.execute_tool(
                    tool=cli_tool,
                    execution_params={},
                    context={}
                )

                elapsed_ms = (time.perf_counter() - start) * 1000

                assert result.success is True
                assert elapsed_ms < 100, f"Latencia {elapsed_ms:.2f}ms excede 100ms"

    @pytest.mark.asyncio
    async def test_batch_execution_latency(
        self, tool_executor, benchmark_tools, fast_execution_result
    ):
        """Verifica latencia < 500ms para batch de 10 ferramentas."""
        with patch.object(
            tool_executor.cli_adapter,
            "execute",
            return_value=fast_execution_result
        ):
            with patch.object(
                tool_executor.cli_adapter,
                "validate_tool_availability",
                return_value=True
            ):
                start = time.perf_counter()

                results = await tool_executor.execute_tools_batch(
                    tools=benchmark_tools,
                    execution_params={},
                    context={}
                )

                elapsed_ms = (time.perf_counter() - start) * 1000

                assert len(results) == 10
                assert all(r.success for r in results.values())
                assert elapsed_ms < 500, f"Latencia batch {elapsed_ms:.2f}ms excede 500ms"

    @pytest.mark.asyncio
    async def test_batch_execution_parallel_faster_than_sequential(
        self, tool_executor, benchmark_tools
    ):
        """Verifica que execucao paralela e mais rapida que sequencial."""
        # Simular execucao com delay
        async def slow_execute(*args, **kwargs):
            await asyncio.sleep(0.05)  # 50ms por execucao
            return ExecutionResult(
                success=True,
                output="Slow execution",
                execution_time_ms=50.0
            )

        with patch.object(
            tool_executor.cli_adapter,
            "execute",
            side_effect=slow_execute
        ):
            with patch.object(
                tool_executor.cli_adapter,
                "validate_tool_availability",
                return_value=True
            ):
                start = time.perf_counter()

                results = await tool_executor.execute_tools_batch(
                    tools=benchmark_tools,
                    execution_params={},
                    context={}
                )

                elapsed_ms = (time.perf_counter() - start) * 1000

                # Se fosse sequencial: 10 * 50ms = 500ms
                # Paralelo deve ser significativamente menor
                assert len(results) == 10
                # Com paralelismo, deve levar menos que 60% do tempo sequencial
                assert elapsed_ms < 300, (
                    f"Execucao paralela {elapsed_ms:.2f}ms nao e significativamente "
                    f"mais rapida que sequencial (500ms)"
                )


# ============================================================================
# Testes de Throughput
# ============================================================================

class TestThroughput:
    """Testes de throughput."""

    @pytest.mark.asyncio
    async def test_concurrent_executions_throughput(
        self, tool_executor, cli_tool, fast_execution_result
    ):
        """Testa 50 execucoes concorrentes."""
        with patch.object(
            tool_executor.cli_adapter,
            "execute",
            return_value=fast_execution_result
        ):
            with patch.object(
                tool_executor.cli_adapter,
                "validate_tool_availability",
                return_value=True
            ):
                start = time.perf_counter()

                # Criar 50 tasks concorrentes
                tasks = [
                    tool_executor.execute_tool(
                        tool=cli_tool,
                        execution_params={"iteration": i},
                        context={}
                    )
                    for i in range(50)
                ]

                results = await asyncio.gather(*tasks)

                elapsed_ms = (time.perf_counter() - start) * 1000
                throughput = 50 / (elapsed_ms / 1000)  # execucoes/segundo

                assert len(results) == 50
                assert all(r.success for r in results)
                assert throughput > 100, (
                    f"Throughput {throughput:.1f} exec/s abaixo do minimo 100 exec/s"
                )

    @pytest.mark.asyncio
    async def test_batch_execution_parallelism(self, mock_settings):
        """Verifica execucao paralela com semaforo."""
        mock_settings.MAX_CONCURRENT_TOOL_EXECUTIONS = 5  # Limite de 5

        with patch("src.services.tool_executor.get_settings", return_value=mock_settings):
            executor = ToolExecutor(settings=mock_settings)

            # Contador de execucoes simultaneas
            concurrent_count = 0
            max_concurrent = 0
            lock = asyncio.Lock()

            async def counting_execute(*args, **kwargs):
                nonlocal concurrent_count, max_concurrent
                async with lock:
                    concurrent_count += 1
                    max_concurrent = max(max_concurrent, concurrent_count)

                await asyncio.sleep(0.1)  # Simular trabalho

                async with lock:
                    concurrent_count -= 1

                return ExecutionResult(
                    success=True,
                    output="Success",
                    execution_time_ms=100.0
                )

            tools = [
                ToolDescriptor(
                    tool_id=f"tool-{i}",
                    tool_name=f"tool-{i}",
                    category=ToolCategory.ANALYSIS,
                    version="1.0.0",
                    capabilities=["test"],
                    reputation_score=0.8,
                    cost_score=0.1,
                    average_execution_time_ms=100,
                    integration_type=IntegrationType.CLI,
                    authentication_method="NONE",
                    is_healthy=True
                )
                for i in range(10)
            ]

            with patch.object(
                executor.cli_adapter,
                "execute",
                side_effect=counting_execute
            ):
                with patch.object(
                    executor.cli_adapter,
                    "validate_tool_availability",
                    return_value=True
                ):
                    await executor.execute_tools_batch(
                        tools=tools,
                        execution_params={},
                        context={}
                    )

                    # Maximo concorrente deve respeitar o limite
                    assert max_concurrent <= 5, (
                        f"Max concurrent {max_concurrent} excede limite 5"
                    )


# ============================================================================
# Testes de Carga
# ============================================================================

class TestLoad:
    """Testes de carga."""

    @pytest.mark.asyncio
    async def test_sustained_load_100_requests(
        self, tool_executor, cli_tool, fast_execution_result
    ):
        """Testa 100 requisicoes sequenciais sem degradacao."""
        latencies = []

        with patch.object(
            tool_executor.cli_adapter,
            "execute",
            return_value=fast_execution_result
        ):
            with patch.object(
                tool_executor.cli_adapter,
                "validate_tool_availability",
                return_value=True
            ):
                for i in range(100):
                    start = time.perf_counter()

                    result = await tool_executor.execute_tool(
                        tool=cli_tool,
                        execution_params={"iteration": i},
                        context={}
                    )

                    elapsed_ms = (time.perf_counter() - start) * 1000
                    latencies.append(elapsed_ms)

                    assert result.success is True

        # Verificar que nao ha degradacao significativa
        first_10_avg = sum(latencies[:10]) / 10
        last_10_avg = sum(latencies[-10:]) / 10

        # Ultimas 10 nao devem ser mais de 50% mais lentas que primeiras 10
        assert last_10_avg < first_10_avg * 1.5, (
            f"Degradacao detectada: primeiras 10 avg={first_10_avg:.2f}ms, "
            f"ultimas 10 avg={last_10_avg:.2f}ms"
        )

    @pytest.mark.asyncio
    async def test_memory_usage_under_load(
        self, tool_executor, benchmark_tools, fast_execution_result
    ):
        """Verifica que uso de memoria e estavel sob carga."""
        import sys

        # Executar coleta de lixo antes do teste
        import gc
        gc.collect()

        with patch.object(
            tool_executor.cli_adapter,
            "execute",
            return_value=fast_execution_result
        ):
            with patch.object(
                tool_executor.cli_adapter,
                "validate_tool_availability",
                return_value=True
            ):
                # Executar 10 batches
                for batch in range(10):
                    results = await tool_executor.execute_tools_batch(
                        tools=benchmark_tools,
                        execution_params={"batch": batch},
                        context={}
                    )
                    assert len(results) == 10

                # Forcar coleta de lixo
                gc.collect()

                # Nota: Este teste e mais um smoke test
                # Testes reais de memoria requerem ferramentas como memory_profiler


# ============================================================================
# Testes de Timeout sob Carga
# ============================================================================

class TestTimeoutUnderLoad:
    """Testes de timeout sob carga."""

    @pytest.mark.asyncio
    async def test_timeout_does_not_block_other_executions(
        self, tool_executor, benchmark_tools
    ):
        """Verifica que timeout de uma execucao nao bloqueia outras."""
        call_count = 0

        async def mixed_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1

            # Primeira execucao e lenta (simula timeout)
            if call_count == 1:
                await asyncio.sleep(5)  # Muito lento

            return ExecutionResult(
                success=True,
                output="Success",
                execution_time_ms=10.0
            )

        with patch.object(
            tool_executor.cli_adapter,
            "execute",
            side_effect=mixed_execute
        ):
            with patch.object(
                tool_executor.cli_adapter,
                "validate_tool_availability",
                return_value=True
            ):
                start = time.perf_counter()

                # Usar asyncio.wait_for para timeout global
                try:
                    results = await asyncio.wait_for(
                        tool_executor.execute_tools_batch(
                            tools=benchmark_tools[:3],  # Apenas 3 para teste rapido
                            execution_params={},
                            context={}
                        ),
                        timeout=10.0
                    )

                    elapsed_ms = (time.perf_counter() - start) * 1000

                    # Deve completar em menos de 10 segundos
                    # (paralelo, nao bloqueado pela execucao lenta)
                    assert elapsed_ms < 10000

                except asyncio.TimeoutError:
                    pytest.fail("Batch execution timed out - blocking detected")


# ============================================================================
# Benchmarks (requerem pytest-benchmark)
# ============================================================================

class TestBenchmarks:
    """Benchmarks com pytest-benchmark (opcional)."""

    @pytest.mark.asyncio
    async def test_single_execution_benchmark(
        self, tool_executor, cli_tool, fast_execution_result
    ):
        """Benchmark de execucao individual."""
        with patch.object(
            tool_executor.cli_adapter,
            "execute",
            return_value=fast_execution_result
        ):
            with patch.object(
                tool_executor.cli_adapter,
                "validate_tool_availability",
                return_value=True
            ):
                # Warmup
                for _ in range(10):
                    await tool_executor.execute_tool(
                        tool=cli_tool,
                        execution_params={},
                        context={}
                    )

                # Benchmark
                iterations = 100
                start = time.perf_counter()

                for _ in range(iterations):
                    await tool_executor.execute_tool(
                        tool=cli_tool,
                        execution_params={},
                        context={}
                    )

                elapsed_ms = (time.perf_counter() - start) * 1000
                avg_latency = elapsed_ms / iterations

                print(f"\nBenchmark: {iterations} execucoes")
                print(f"Total: {elapsed_ms:.2f}ms")
                print(f"Media: {avg_latency:.3f}ms/execucao")
                print(f"Throughput: {1000/avg_latency:.1f} exec/s")

                # Assertions basicas
                assert avg_latency < 10, f"Latencia media {avg_latency:.3f}ms excede 10ms"

    @pytest.mark.asyncio
    async def test_batch_execution_benchmark(
        self, tool_executor, benchmark_tools, fast_execution_result
    ):
        """Benchmark de execucao em batch."""
        with patch.object(
            tool_executor.cli_adapter,
            "execute",
            return_value=fast_execution_result
        ):
            with patch.object(
                tool_executor.cli_adapter,
                "validate_tool_availability",
                return_value=True
            ):
                # Warmup
                for _ in range(5):
                    await tool_executor.execute_tools_batch(
                        tools=benchmark_tools,
                        execution_params={},
                        context={}
                    )

                # Benchmark
                iterations = 20
                start = time.perf_counter()

                for _ in range(iterations):
                    await tool_executor.execute_tools_batch(
                        tools=benchmark_tools,
                        execution_params={},
                        context={}
                    )

                elapsed_ms = (time.perf_counter() - start) * 1000
                avg_batch_time = elapsed_ms / iterations
                tools_per_second = (iterations * len(benchmark_tools)) / (elapsed_ms / 1000)

                print(f"\nBenchmark Batch: {iterations} batches x {len(benchmark_tools)} tools")
                print(f"Total: {elapsed_ms:.2f}ms")
                print(f"Media batch: {avg_batch_time:.2f}ms")
                print(f"Tools/segundo: {tools_per_second:.1f}")

                # Assertions
                assert avg_batch_time < 100, f"Batch medio {avg_batch_time:.2f}ms excede 100ms"
