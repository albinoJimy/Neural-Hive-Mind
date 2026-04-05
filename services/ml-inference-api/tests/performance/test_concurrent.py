"""
Testes de concorrência - ML-001-08.3

Objetivo: Verificar comportamento sob carga concorrente:
- Múltiplos requests simultâneos
- Estabilidade sob stress
- Race conditions não ocorrem
"""
import asyncio
import time

import pytest
from httpx import AsyncClient

# ============================================================================
# Testes de concorrência básica
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.performance
async def test_concurrent_requests_10(
    performance_client: AsyncClient,
    sample_request_data: dict,
) -> None:
    """
    Testa 10 requests concorrentes.

    Todos devem completar com sucesso.
    """
    num_concurrent = 10

    async def single_request() -> tuple[bool, float]:
        """Executa request e retorna (sucesso, latência)."""
        start = time.perf_counter()
        try:
            response = await performance_client.post(
                "/api/v1/inference/predict",
                json=sample_request_data,
            )
            end = time.perf_counter()
            success = response.status_code == 200
            return success, (end - start) * 1000
        except Exception:
            end = time.perf_counter()
            return False, (end - start) * 1000

    start_time = time.time()
    results = await asyncio.gather(*[single_request() for _ in range(num_concurrent)])
    total_time = time.time() - start_time

    successful = sum(1 for success, _ in results if success)
    latencies = [lat for _, lat in results if lat > 0]

    assert successful == num_concurrent, f"Apenas {successful}/{num_concurrent} requests foram bem-sucedidos"

    p50 = sorted(latencies)[len(latencies) // 2]
    p99_idx = int(len(latencies) * 0.99)
    p99 = sorted(latencies)[min(p99_idx, len(latencies) - 1)]

    print(f"\nConcurrent Requests ({num_concurrent}):")
    print("  Todos bem-sucedidos: ✓")
    print(f"  Tempo total: {total_time:.2f}s")
    print(f"  p50 latência: {p50:.2f}ms")
    print(f"  p99 latência: {p99:.2f}ms")


@pytest.mark.asyncio
@pytest.mark.performance
async def test_concurrent_requests_50(
    performance_client: AsyncClient,
    sample_request_data: dict,
) -> None:
    """
    Testa 50 requests concorrentes.

    Verifica estabilidade sob carga moderada.
    """
    num_concurrent = 50

    async def single_request() -> tuple[bool, float]:
        """Executa request e retorna (sucesso, latência)."""
        start = time.perf_counter()
        try:
            response = await performance_client.post(
                "/api/v1/inference/predict",
                json=sample_request_data,
            )
            end = time.perf_counter()
            success = response.status_code == 200
            return success, (end - start) * 1000
        except Exception:
            end = time.perf_counter()
            return False, (end - start) * 1000

    start_time = time.time()
    results = await asyncio.gather(*[single_request() for _ in range(num_concurrent)])
    total_time = time.time() - start_time

    successful = sum(1 for success, _ in results if success)
    latencies = [lat for _, lat in results if lat > 0]

    assert successful == num_concurrent, f"Apenas {successful}/{num_concurrent} requests foram bem-sucedidos"

    p50 = sorted(latencies)[len(latencies) // 2]
    p99 = sorted(latencies)[min(int(len(latencies) * 0.99), len(latencies) - 1)]
    avg = sum(latencies) / len(latencies)

    throughput = num_concurrent / total_time

    print(f"\nConcurrent Requests ({num_concurrent}):")
    print("  Todos bem-sucedidos: ✓")
    print(f"  Tempo total: {total_time:.2f}s")
    print(f"  Throughput: {throughput:.2f} req/s")
    print(f"  p50 latência: {p50:.2f}ms")
    print(f"  p99 latência: {p99:.2f}ms")
    print(f"  avg latência: {avg:.2f}ms")

    # Verificar que latência não degradou demais
    assert p99 < 500, f"Latência p99 ({p99:.2f}ms) degradou sob concorrência"


@pytest.mark.asyncio
@pytest.mark.performance
async def test_concurrent_requests_100(
    performance_client: AsyncClient,
    sample_request_data: dict,
) -> None:
    """
    Testa 100 requests concorrentes.

    Verifica estabilidade sob carga alta.
    """
    num_concurrent = 100

    async def single_request() -> tuple[bool, float]:
        """Executa request e retorna (sucesso, latência)."""
        start = time.perf_counter()
        try:
            response = await performance_client.post(
                "/api/v1/inference/predict",
                json=sample_request_data,
            )
            end = time.perf_counter()
            success = response.status_code == 200
            return success, (end - start) * 1000
        except Exception:
            end = time.perf_counter()
            return False, (end - start) * 1000

    start_time = time.time()
    results = await asyncio.gather(*[single_request() for _ in range(num_concurrent)])
    total_time = time.time() - start_time

    successful = sum(1 for success, _ in results if success)
    latencies = [lat for _, lat in results if lat > 0]

    assert successful == num_concurrent, f"Apenas {successful}/{num_concurrent} requests foram bem-sucedidos"

    p50 = sorted(latencies)[len(latencies) // 2]
    p99 = sorted(latencies)[min(int(len(latencies) * 0.99), len(latencies) - 1)]

    throughput = num_concurrent / total_time

    print(f"\nConcurrent Requests ({num_concurrent}):")
    print("  Todos bem-sucedidos: ✓")
    print(f"  Tempo total: {total_time:.2f}s")
    print(f"  Throughput: {throughput:.2f} req/s")
    print(f"  p50 latência: {p50:.2f}ms")
    print(f"  p99 latência: {p99:.2f}ms")


# ============================================================================
# Testes de batch concorrente
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.performance
async def test_concurrent_batches(
    performance_client: AsyncClient,
    batch_request_factory: callable,
) -> None:
    """
    Testa múltiplos batches concorrentes.

    Simula múltiplos clientes enviando batches simultâneos.
    """
    num_batches = 10
    batch_size = 20

    async def process_batch(batch_id: int) -> dict:
        """Processa um batch e retorna estatísticas."""
        batch_data = batch_request_factory(batch_size)

        start = time.perf_counter()
        response = await performance_client.post(
            "/api/v1/inference/predict-batch",
            json={"requests": batch_data, "options": {"parallel": True}},
        )
        end = time.perf_counter()

        duration_ms = (end - start) * 1000

        if response.status_code == 200:
            result = response.json()
            return {
                "batch_id": batch_id,
                "success": True,
                "duration_ms": duration_ms,
                "successful": result["successful"],
                "total": result["total_processed"],
            }
        else:
            return {
                "batch_id": batch_id,
                "success": False,
                "duration_ms": duration_ms,
            }

    start_time = time.time()
    results = await asyncio.gather(*[process_batch(i) for i in range(num_batches)])
    total_time = time.time() - start_time

    successful = sum(1 for r in results if r["success"])
    total_items = sum(r.get("total", 0) for r in results if r["success"])
    durations = [r["duration_ms"] for r in results if r["success"]]

    assert successful == num_batches, f"Apenas {successful}/{num_batches} batches foram bem-sucedidos"

    avg_duration = sum(durations) / len(durations)

    print(f"\nConcurrent Batches ({num_batches} batches de {batch_size}):")
    print("  Todos bem-sucedidos: ✓")
    print(f"  Tempo total: {total_time:.2f}s")
    print(f"  Total items: {total_items}")
    print(f"  Avg batch duration: {avg_duration:.2f}ms")


@pytest.mark.asyncio
@pytest.mark.performance
async def test_mixed_concurrent_workload(
    performance_client: AsyncClient,
    sample_request_data: dict,
    batch_request_factory: callable,
) -> None:
    """
    Testa workload misto: requests individuais + batches.

    Simula cenário real de produção com diferentes tipos de clients.
    """
    async def single_request_task() -> tuple[bool, float]:
        """Executa request individual."""
        start = time.perf_counter()
        try:
            response = await performance_client.post(
                "/api/v1/inference/predict",
                json=sample_request_data,
            )
            end = time.perf_counter()
            return response.status_code == 200, (end - start) * 1000
        except Exception:
            end = time.perf_counter()
            return False, (end - start) * 1000

    async def batch_request_task(batch_id: int) -> tuple[bool, float]:
        """Executa request em batch."""
        batch_data = batch_request_factory(20)
        start = time.perf_counter()
        try:
            response = await performance_client.post(
                "/api/v1/inference/predict-batch",
                json={"requests": batch_data, "options": {"parallel": True}},
            )
            end = time.perf_counter()
            return response.status_code == 200, (end - start) * 1000
        except Exception:
            end = time.perf_counter()
            return False, (end - start) * 1000

    # Criar workload misto
    tasks = []
    # 20 requests individuais
    tasks.extend([single_request_task() for _ in range(20)])
    # 10 batch requests
    tasks.extend([batch_request_task(i) for i in range(10)])

    start_time = time.time()
    results = await asyncio.gather(*tasks)
    total_time = time.time() - start_time

    successful = sum(1 for success, _ in results if success)
    latencies = [lat for _, lat in results if lat > 0]

    assert successful == len(tasks), f"Apenas {successful}/{len(tasks)} requests foram bem-sucedidos"

    avg_latency = sum(latencies) / len(latencies)

    print("\nMixed Concurrent Workload:")
    print(f"  Total tasks: {len(tasks)}")
    print("  Single: 20")
    print("  Batch: 10")
    print("  Todos bem-sucedidos: ✓")
    print(f"  Tempo total: {total_time:.2f}s")
    print(f"  Avg latência: {avg_latency:.2f}ms")


# ============================================================================
# Testes de stress
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.performance
async def test_sustained_load(
    performance_client: AsyncClient,
    sample_request_data: dict,
) -> None:
    """
    Testa carga sustentada por período prolongado.

    Verifica que não há degradação ao longo do tempo.
    """
    duration_sec = 3
    concurrency = 20
    measurements = []

    start_time = time.time()
    end_time = start_time + duration_sec

    while time.time() < end_time:
        batch_start = time.time()

        # Executar lote de requests concorrentes
        tasks = []
        for _ in range(concurrency):
            async def single_req():
                try:
                    response = await performance_client.post(
                        "/api/v1/inference/predict",
                        json=sample_request_data,
                    )
                    return response.status_code == 200
                except Exception:
                    return False

            tasks.append(single_req())

        results = await asyncio.gather(*tasks)
        batch_end = time.time()

        successful = sum(results)
        batch_duration = batch_end - batch_start

        measurements.append({
            "time": batch_end - start_time,
            "successful": successful,
            "total": len(tasks),
            "duration": batch_duration,
        })

        # Pequena pausa entre batches
        await asyncio.sleep(0.01)

    # Analisar degradação
    first_half = measurements[:len(measurements)//2] if len(measurements) > 1 else measurements
    second_half = measurements[len(measurements)//2:] if len(measurements) > 1 else measurements

    first_success_rate = sum(m["successful"] for m in first_half) / sum(m["total"] for m in first_half)
    second_success_rate = sum(m["successful"] for m in second_half) / sum(m["total"] for m in second_half)

    degradation = (first_success_rate - second_success_rate) / first_success_rate if first_success_rate > 0 else 0

    print(f"\nSustained Load ({duration_sec}s, {concurrency} concurrent):")
    print(f"  Measurements: {len(measurements)}")
    print(f"  Success rate (1ª metade): {first_success_rate:.1%}")
    print(f"  Success rate (2ª metade): {second_success_rate:.1%}")
    print(f"  Degradation: {degradation:.1%}")

    # Success rate deve permanecer alto
    assert second_success_rate > 0.95, f"Success rate degradou para {second_success_rate:.1%}"
    assert degradation < 0.1, f"Degradation excessiva ({degradation:.1%})"


@pytest.mark.asyncio
@pytest.mark.performance
async def test_ramp_up_load(
    performance_client: AsyncClient,
    sample_request_data: dict,
) -> None:
    """
    Testa aumento gradual de concorrência (ramp-up).

    Verifica comportamento com carga crescente.
    """
    max_concurrency = 100
    ramp_steps = 5
    step_duration = 0.5

    results_by_concurrency = {}

    for step in range(1, ramp_steps + 1):
        concurrency = (max_concurrency // ramp_steps) * step
        step_results = []

        step_start = time.time()
        step_end = step_start + step_duration

        while time.time() < step_end:
            async def single_req():
                start = time.perf_counter()
                try:
                    response = await performance_client.post(
                        "/api/v1/inference/predict",
                        json=sample_request_data,
                    )
                    end = time.perf_counter()
                    return response.status_code == 200, (end - start) * 1000
                except Exception:
                    end = time.perf_counter()
                    return False, (end - start) * 1000

            tasks = [single_req() for _ in range(concurrency)]
            results = await asyncio.gather(*tasks)
            step_results.extend(results)

        # Calcular estatísticas do step
        successful = sum(1 for s, _ in step_results if s)
        latencies = [lat for s, lat in step_results if s and lat > 0]

        results_by_concurrency[concurrency] = {
            "total": len(step_results),
            "successful": successful,
            "success_rate": successful / len(step_results) if step_results else 0,
            "avg_latency": sum(latencies) / len(latencies) if latencies else 0,
            "p99_latency": sorted(latencies)[min(int(len(latencies) * 0.99), len(latencies) - 1)] if latencies else 0,
        }

        await asyncio.sleep(0.1)  # Pausa entre steps

    # Verificar resultados
    print("\nRamp-up Load Test:")
    for concurrency, stats in results_by_concurrency.items():
        print(f"  {concurrency:3d} concurrent: {stats['success_rate']:.1%} success, "
              f"avg {stats['avg_latency']:.2f}ms, p99 {stats['p99_latency']:.2f}ms")

    # Success rate deve permanecer alto mesmo em alta concorrência
    for concurrency, stats in results_by_concurrency.items():
        assert stats["success_rate"] > 0.95, f"Success rate caiu para {stats['success_rate']:.1%} em {concurrency} concurrent"
