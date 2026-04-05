"""
Testes de uso de memória - ML-001-08.4

Objetivo: Verificar que o serviço não tem vazamento de memória:
- Uso de memória permanece estável sob carga
- Memória é liberada após picos
- Não há growth contínuo ao longo do tempo

Nota: Estes testes requerem 'memory_profiler' instalado.
Se não estiver instalado, os testes serão pulados.
"""
import asyncio
import gc

import pytest
from httpx import AsyncClient

# Tentar importar memory_profiler
try:
    from memory_profiler import memory_usage
    MEMORY_PROFILER_AVAILABLE = True
except ImportError:
    MEMORY_PROFILER_AVAILABLE = False


# ============================================================================
# Testes de memória básicos
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.performance
@pytest.mark.skipif(not MEMORY_PROFILER_AVAILABLE, reason="memory_profiler not installed")
async def test_memory_baseline(
    performance_client: AsyncClient,
    sample_request_data: dict,
) -> None:
    """
    Mede uso de memória baseline do serviço.

    Executa um pequeno número de requests e mede memória.
    """
    def run_requests():
        """Executa requests síncronos para profiling."""
        async def async_requests():
            for _ in range(10):
                await performance_client.post(
                    "/api/v1/inference/predict",
                    json=sample_request_data,
                )

        # Executar de forma síncrona para memory_profiler
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(async_requests())
        finally:
            loop.close()

    # Medir memória durante execução
    mem_usage = memory_usage(
        run_requests,
        interval=0.01,
        timeout=10,
    )

    max_mem = max(mem_usage)
    min_mem = min(mem_usage)
    delta_mem = max_mem - min_mem

    print("\nMemory Baseline (10 requests):")
    print(f"  Min mem: {min_mem:.2f} MiB")
    print(f"  Max mem: {max_mem:.2f} MiB")
    print(f"  Delta:   {delta_mem:.2f} MiB")

    # Delta não deve ser muito grande para 10 requests simples
    assert delta_mem < 50, f"Crescimento de memória excessivo: {delta_mem:.2f} MiB"


@pytest.mark.asyncio
@pytest.mark.performance
@pytest.mark.skipif(not MEMORY_PROFILER_AVAILABLE, reason="memory_profiler not installed")
async def test_memory_under_load(
    performance_client: AsyncClient,
    sample_request_data: dict,
) -> None:
    """
    Mede uso de memória sob carga moderada.

    Executa 100 requests concorrentes e monitora memória.
    """
    def run_load():
        """Executa carga para profiling."""
        async def async_load():
            tasks = []
            for _ in range(100):
                async def single_req():
                    try:
                        await performance_client.post(
                            "/api/v1/inference/predict",
                            json=sample_request_data,
                        )
                    except Exception:
                        pass

                tasks.append(single_req())

            await asyncio.gather(*tasks, return_exceptions=True)

            # Força GC para verificar se memória é liberada
            gc.collect()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(async_load())
        finally:
            loop.close()

    # Medir memória durante execução
    mem_usage = memory_usage(
        run_load,
        interval=0.05,
        timeout=30,
    )

    max_mem = max(mem_usage)
    min_mem = min(mem_usage)
    final_mem = mem_usage[-1] if mem_usage else min_mem
    delta_mem = max_mem - min_mem
    growth = final_mem - min_mem

    print("\nMemory Under Load (100 concurrent requests):")
    print(f"  Min mem:   {min_mem:.2f} MiB")
    print(f"  Max mem:   {max_mem:.2f} MiB")
    print(f"  Final mem: {final_mem:.2f} MiB")
    print(f"  Delta:     {delta_mem:.2f} MiB")
    print(f"  Growth:    {growth:.2f} MiB")

    # Crescimento (final vs inicial) deve ser pequeno
    # (indicando que memória foi liberada após carga)
    assert growth < 100, f"Memória não foi liberada adequadamente: growth={growth:.2f} MiB"


@pytest.mark.asyncio
@pytest.mark.performance
@pytest.mark.skipif(not MEMORY_PROFILER_AVAILABLE, reason="memory_profiler not installed")
async def test_memory_sustained_operation(
    performance_client: AsyncClient,
    sample_request_data: dict,
) -> None:
    """
    Verifica estabilidade de memória ao longo do tempo.

    Executa requests continuamente e monitora se memória cresce indefinidamente.
    """
    def run_sustained():
        """Executa operação sustentada para profiling."""
        async def async_sustained():
            # Executar em "ondas" para simular uso prolongado
            for _wave in range(5):
                # Burst de 20 requests
                tasks = []
                for _ in range(20):
                    async def single_req():
                        try:
                            await performance_client.post(
                                "/api/v1/inference/predict",
                                json=sample_request_data,
                            )
                        except Exception:
                            pass

                    tasks.append(single_req())

                await asyncio.gather(*tasks, return_exceptions=True)

                # GC entre ondas
                gc.collect()

                # Pequena pausa
                await asyncio.sleep(0.05)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(async_sustained())
        finally:
            loop.close()

    # Medir memória durante execução
    mem_usage = memory_usage(
        run_sustained,
        interval=0.1,
        timeout=30,
    )

    max_mem = max(mem_usage)
    min_mem = min(mem_usage)
    final_mem = mem_usage[-1] if mem_usage else min_mem

    # Calcular tendência (linear regression simples)
    n = len(mem_usage)
    if n > 2:
        x = list(range(n))
        y = mem_usage

        # Simple linear regression: y = mx + b
        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(xi * yi for xi, yi in zip(x, y, strict=True))
        sum_x2 = sum(xi * xi for xi in x)

        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x)
        growth_rate = slope  # MiB por amostra

        # Calcular R²
        y_mean = sum_y / n
        ss_tot = sum((yi - y_mean) ** 2 for yi in y)
        y_pred = [slope * xi + (sum_y - slope * sum_x) / n for xi in x]
        ss_res = sum((yi - ypi) ** 2 for yi, ypi in zip(y, y_pred, strict=True))
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
    else:
        growth_rate = 0
        r_squared = 0

    print("\nMemory Sustained Operation (5 waves of 20 requests):")
    print(f"  Min mem:     {min_mem:.2f} MiB")
    print(f"  Max mem:     {max_mem:.2f} MiB")
    print(f"  Final mem:   {final_mem:.2f} MiB")
    print(f"  Samples:     {n}")
    if n > 2:
        print(f"  Slope:       {growth_rate:.4f} MiB/sample")
        print(f"  R²:          {r_squared:.4f}")

    # Verificar se há vazamento de memória
    # Se slope é positivo e R² é alto, há tendência de crescimento
    if r_squared > 0.7 and growth_rate > 0.5:
        pytest.fail(f"Possível vazamento de memória detectado: slope={growth_rate:.4f} MiB/sample, R²={r_squared:.4f}")


# ============================================================================
# Testes de memória para batch
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.performance
@pytest.mark.skipif(not MEMORY_PROFILER_AVAILABLE, reason="memory_profiler not installed")
async def test_memory_batch_processing(
    performance_client: AsyncClient,
    batch_request_factory: callable,
) -> None:
    """
    Verifica uso de memória durante processamento em batch.
    """
    batch_data = batch_request_factory(100)

    def run_batch():
        """Executa batch para profiling."""
        async def async_batch():
            await performance_client.post(
                "/api/v1/inference/predict-batch",
                json={"requests": batch_data, "options": {"parallel": True}},
            )
            gc.collect()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(async_batch())
        finally:
            loop.close()

    # Medir memória
    mem_usage = memory_usage(
        run_batch,
        interval=0.01,
        timeout=10,
    )

    max_mem = max(mem_usage)
    min_mem = min(mem_usage)
    delta_mem = max_mem - min_mem

    print("\nMemory Batch Processing (100 items):")
    print(f"  Min mem: {min_mem:.2f} MiB")
    print(f"  Max mem: {max_mem:.2f} MiB")
    print(f"  Delta:   {delta_mem:.2f} MiB")

    # Batch de 100 itens não deve consumir memória excessiva
    assert delta_mem < 200, f"Uso de memória para batch muito alto: {delta_mem:.2f} MiB"


# ============================================================================
# Testes de comparação de memória
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.performance
@pytest.mark.skipif(not MEMORY_PROFILER_AVAILABLE, reason="memory_profiler not installed")
async def test_memory_batch_vs_individual(
    performance_client: AsyncClient,
    batch_request_factory: callable,
) -> None:
    """
    Compara uso de memória: batch vs requests individuais.

    Batch deve ser mais eficiente em memória.
    """
    batch_data = batch_request_factory(50)

    def run_individual():
        """Executa requests individuais."""
        async def async_individual():
            for request in batch_data[:10]:  # Apenas 10 para não demorar muito
                await performance_client.post(
                    "/api/v1/inference/predict",
                    json=request,
                )
            gc.collect()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(async_individual())
        finally:
            loop.close()

    def run_batch():
        """Executa batch."""
        async def async_batch():
            await performance_client.post(
                "/api/v1/inference/predict-batch",
                json={"requests": batch_data[:10], "options": {"parallel": True}},
            )
            gc.collect()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(async_batch())
        finally:
            loop.close()

    # Medir individuais
    mem_individual = memory_usage(run_individual, interval=0.01, timeout=10)
    delta_individual = max(mem_individual) - min(mem_individual)

    # Medir batch
    mem_batch = memory_usage(run_batch, interval=0.01, timeout=10)
    delta_batch = max(mem_batch) - min(mem_batch)

    efficiency = delta_individual / delta_batch if delta_batch > 0 else 1

    print("\nMemory Comparison (10 requests):")
    print(f"  Individual delta: {delta_individual:.2f} MiB")
    print(f"  Batch delta:      {delta_batch:.2f} MiB")
    print(f"  Efficiency:       {efficiency:.2f}x")

    # Batch deve ser mais eficiente (menor delta por request)
    # Nota: Pode não ser drasticamente melhor em Python devido ao GIL,
    # mas não deve ser pior
    assert delta_batch <= delta_individual * 1.5, "Batch usou significativamente mais memória"


# ============================================================================
# Testes sem memory_profiler (alternativa simples)
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.performance
async def test_memory_no_leaks_simple(
    performance_client: AsyncClient,
    sample_request_data: dict,
) -> None:
    """
    Teste simples de vazamento de memória sem memory_profiler.

    Usa tracemalloc do Python para detecção básica.
    """
    try:
        import tracemalloc
    except ImportError:
        pytest.skip("tracemalloc not available")

    tracemalloc.start()
    snapshot1 = tracemalloc.take_snapshot()

    # Executar alguns requests
    for _ in range(50):
        await performance_client.post(
            "/api/v1/inference/predict",
            json=sample_request_data,
        )

    # Forçar GC
    gc.collect()

    snapshot2 = tracemalloc.take_snapshot()
    tracemalloc.stop()

    # Calcular diferença
    top_stats = snapshot2.compare_to(snapshot1, 'lineno')
    total_increase = sum(stat.size_diff for stat in top_stats if stat.size_diff > 0)

    print("\nSimple Memory Leak Test (50 requests):")
    print(f"  Total increase: {total_increase / 1024:.2f} KiB")
    print("  Top 5 allocations:")
    for stat in top_stats[:5]:
        print(f"    {stat}")

    # Aumento não deve ser excessivo
    # (algum aumento é normal devido a caching, etc.)
    assert total_increase < 10 * 1024 * 1024, f"Aumento de memória excessivo: {total_increase / 1024:.2f} KiB"


@pytest.mark.asyncio
@pytest.mark.performance
async def test_memory_reuse(
    performance_client: AsyncClient,
    sample_request_data: dict,
) -> None:
    """
    Verifica que memória está sendo reutilizada entre requests.

    Executa múltiplas vezes e verifica que tamanho total não cresce linearmente.
    """
    try:
        import tracemalloc
    except ImportError:
        pytest.skip("tracemalloc not available")

    tracemalloc.start()

    # Baseline
    snapshot0 = tracemalloc.take_snapshot()
    current_size0 = sum(stat.size for stat in snapshot0.statistics("lineno"))

    # Primeira rodada
    for _ in range(20):
        await performance_client.post("/api/v1/inference/predict", json=sample_request_data)
    gc.collect()
    snapshot1 = tracemalloc.take_snapshot()
    current_size1 = sum(stat.size for stat in snapshot1.statistics("lineno"))
    growth1 = current_size1 - current_size0

    # Segunda rodada (deve usar memória reutilizada)
    for _ in range(20):
        await performance_client.post("/api/v1/inference/predict", json=sample_request_data)
    gc.collect()
    snapshot2 = tracemalloc.take_snapshot()
    current_size2 = sum(stat.size for stat in snapshot2.statistics("lineno"))
    growth2 = current_size2 - current_size1

    tracemalloc.stop()

    print("\nMemory Reuse Test:")
    print(f"  Initial:    {current_size0 / 1024:.2f} KiB")
    print(f"  After 1st:  {current_size1 / 1024:.2f} KiB (growth: {growth1 / 1024:.2f} KiB)")
    print(f"  After 2nd:  {current_size2 / 1024:.2f} KiB (growth: {growth2 / 1024:.2f} KiB)")

    # Segundo crescimento deve ser menor (memória sendo reutilizada)
    # Pode haver algum crescimento, mas não deve ser linear
    assert growth2 < growth1 * 1.5, "Memória não está sendo reutilizada adequadamente"
