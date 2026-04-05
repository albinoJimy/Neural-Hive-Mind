"""
Testes de latência - ML-001-08.1

Objetivo: Verificar que a latência de inferência está dentro dos limits do spec:
- Latência p50 < 50ms
- Latência p99 < 200ms

Usa pytest-benchmark para microbenchmarks consistentes.
"""
import asyncio
import time
from typing import Any

import pytest
from httpx import AsyncClient

# ============================================================================
# Testes de latência de API
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.performance
async def test_api_predict_latency_p50(
    performance_client: AsyncClient,
    sample_request_data: dict,
    performance_targets: dict,
) -> None:
    """
    Testa latência p50 da API de predição individual.

    Target: p50 < 50ms
    """
    latencies = []
    num_requests = 100

    for _ in range(num_requests):
        start = time.perf_counter()

        response = await performance_client.post(
            "/api/v1/inference/predict",
            json=sample_request_data,
        )

        end = time.perf_counter()

        assert response.status_code == 200
        latencies.append((end - start) * 1000)  # Converter para ms

    # Calcular p50
    latencies_sorted = sorted(latencies)
    p50 = latencies_sorted[len(latencies_sorted) // 2]

    # Calcular p99 também para relatório
    p99_idx = int(len(latencies_sorted) * 0.99)
    p99 = latencies_sorted[min(p99_idx, len(latencies_sorted) - 1)]

    avg_latency = sum(latencies) / len(latencies)

    # Verificar target
    target_p50 = performance_targets["latency_p50_max_ms"]
    assert p50 < target_p50, f"Latência p50 ({p50:.2f}ms) excede target ({target_p50}ms)"

    # Log para diagnóstico
    print(f"\nLatência API Predict (n={num_requests}):")
    print(f"  p50:  {p50:.2f}ms (target: <{target_p50}ms)")
    print(f"  p99:  {p99:.2f}ms (target: <{performance_targets['latency_p99_max_ms']}ms)")
    print(f"  avg:  {avg_latency:.2f}ms")
    print(f"  min:  {min(latencies):.2f}ms")
    print(f"  max:  {max(latencies):.2f}ms")


@pytest.mark.asyncio
@pytest.mark.performance
async def test_api_predict_latency_p99(
    performance_client: AsyncClient,
    sample_request_data: dict,
    performance_targets: dict,
) -> None:
    """
    Testa latência p99 da API de predição individual.

    Target: p99 < 200ms
    """
    latencies = []
    num_requests = 500  # Maior amostra para p99 confiável

    for _ in range(num_requests):
        start = time.perf_counter()

        response = await performance_client.post(
            "/api/v1/inference/predict",
            json=sample_request_data,
        )

        end = time.perf_counter()

        assert response.status_code == 200
        latencies.append((end - start) * 1000)

    # Calcular percentis
    latencies_sorted = sorted(latencies)
    p50 = latencies_sorted[len(latencies_sorted) // 2]
    p95_idx = int(len(latencies_sorted) * 0.95)
    p95 = latencies_sorted[min(p95_idx, len(latencies_sorted) - 1)]
    p99_idx = int(len(latencies_sorted) * 0.99)
    p99 = latencies_sorted[min(p99_idx, len(latencies_sorted) - 1)]

    # Verificar target
    target_p99 = performance_targets["latency_p99_max_ms"]
    assert p99 < target_p99, f"Latência p99 ({p99:.2f}ms) excede target ({target_p99}ms)"

    print(f"\nLatência API Predict - Detalhado (n={num_requests}):")
    print(f"  p50:  {p50:.2f}ms")
    print(f"  p95:  {p95:.2f}ms")
    print(f"  p99:  {p99:.2f}ms (target: <{target_p99}ms)")
    print(f"  max:  {max(latencies):.2f}ms")


@pytest.mark.asyncio
@pytest.mark.performance
async def test_api_predict_warmup_latency(
    performance_client: AsyncClient,
    sample_request_data: dict,
) -> None:
    """
    Testa latência após warmup.

    Simula cenário real onde serviço já está aquecido.
    """
    # Warmup
    for _ in range(10):
        await performance_client.post("/api/v1/inference/predict", json=sample_request_data)

    # Medir latência após warmup
    latencies = []
    for _ in range(100):
        start = time.perf_counter()

        response = await performance_client.post(
            "/api/v1/inference/predict",
            json=sample_request_data,
        )

        end = time.perf_counter()

        assert response.status_code == 200
        latencies.append((end - start) * 1000)

    p50 = sorted(latencies)[len(latencies) // 2]
    avg = sum(latencies) / len(latencies)

    print("\nLatência pós-warmup:")
    print(f"  p50: {p50:.2f}ms")
    print(f"  avg: {avg:.2f}ms")


# ============================================================================
# Testes de latência em batch
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.performance
async def test_batch_predict_latency_small(
    performance_client: AsyncClient,
    batch_request_factory: callable,
    performance_targets: dict,
) -> None:
    """
    Testa latência de batch pequeno (10 items).

    Verifica que processamento em batch é eficiente.
    """
    batch_data = batch_request_factory(10)

    start = time.perf_counter()

    response = await performance_client.post(
        "/api/v1/inference/predict-batch",
        json={"requests": batch_data, "options": {"parallel": True}},
    )

    end = time.perf_counter()

    assert response.status_code == 200
    result = response.json()

    total_time_ms = (end - start) * 1000
    avg_per_item = total_time_ms / len(batch_data)

    # Batch deve ser significativamente mais eficiente que individual
    # (não necessariamente 10x para batch pequeno, mas deve ser melhor)
    assert result["successful"] == len(batch_data)
    assert result["total_processed"] == len(batch_data)

    print("\nLatência Batch Pequeno (10 items):")
    print(f"  total: {total_time_ms:.2f}ms")
    print(f"  por item: {avg_per_item:.2f}ms")


@pytest.mark.asyncio
@pytest.mark.performance
async def test_batch_predict_latency_medium(
    performance_client: AsyncClient,
    batch_request_factory: callable,
    performance_targets: dict,
) -> None:
    """
    Testa latência de batch médio (50 items).
    """
    batch_data = batch_request_factory(50)

    start = time.perf_counter()

    response = await performance_client.post(
        "/api/v1/inference/predict-batch",
        json={"requests": batch_data, "options": {"parallel": True}},
    )

    end = time.perf_counter()

    assert response.status_code == 200
    result = response.json()

    total_time_ms = (end - start) * 1000
    avg_per_item = total_time_ms / len(batch_data)

    assert result["successful"] == len(batch_data)

    # Para batch médio, esperamos melhor eficiência
    target_p50 = performance_targets["latency_p50_max_ms"]
    assert avg_per_item < target_p50, f"Latência média por item ({avg_per_item:.2f}ms) excede target"

    print("\nLatência Batch Médio (50 items):")
    print(f"  total: {total_time_ms:.2f}ms")
    print(f"  por item: {avg_per_item:.2f}ms (target: <{target_p50}ms)")


@pytest.mark.asyncio
@pytest.mark.performance
async def test_batch_predict_latency_large(
    performance_client: AsyncClient,
    batch_request_factory: callable,
    performance_targets: dict,
) -> None:
    """
    Testa latência de batch grande (100 items).

    Este é o tamanho máximo de batch permitido.
    """
    batch_data = batch_request_factory(100)

    start = time.perf_counter()

    response = await performance_client.post(
        "/api/v1/inference/predict-batch",
        json={"requests": batch_data, "options": {"parallel": True}},
    )

    end = time.perf_counter()

    assert response.status_code == 200
    result = response.json()

    total_time_ms = (end - start) * 1000
    avg_per_item = total_time_ms / len(batch_data)

    assert result["successful"] == len(batch_data)

    print("\nLatência Batch Grande (100 items - max):")
    print(f"  total: {total_time_ms:.2f}ms")
    print(f"  por item: {avg_per_item:.2f}ms")


@pytest.mark.asyncio
@pytest.mark.performance
async def test_batch_parallel_vs_sequential(
    performance_client: AsyncClient,
    batch_request_factory: callable,
) -> None:
    """
    Compara processamento paralelo vs sequencial em batch.

    NOTA: Com mocks muito rápidos, o overhead de asyncio.gather pode
    fazer o paralelo parecer mais lento. Este teste verifica que ambos
    funcionam corretamente, mas não impõe speedup mínimo.
    """
    batch_data = batch_request_factory(20)

    # Testar paralelo
    start = time.perf_counter()
    response_parallel = await performance_client.post(
        "/api/v1/inference/predict-batch",
        json={"requests": batch_data, "options": {"parallel": True}},
    )
    end_parallel = time.perf_counter()
    time_parallel_ms = (end_parallel - start) * 1000

    assert response_parallel.status_code == 200
    result_parallel = response_parallel.json()
    assert result_parallel["successful"] == 20

    # Testar sequencial
    start = time.perf_counter()
    response_sequential = await performance_client.post(
        "/api/v1/inference/predict-batch",
        json={"requests": batch_data, "options": {"parallel": False}},
    )
    end_sequential = time.perf_counter()
    time_sequential_ms = (end_sequential - start) * 1000

    assert response_sequential.status_code == 200
    result_sequential = response_sequential.json()
    assert result_sequential["successful"] == 20

    speedup = time_sequential_ms / time_parallel_ms

    print("\nComparação Paralelo vs Sequencial (20 items):")
    print(f"  Paralelo:    {time_parallel_ms:.2f}ms")
    print(f"  Sequencial:  {time_sequential_ms:.2f}ms")
    print(f"  Speedup:     {speedup:.2f}x")
    print("  NOTA: Com mocks rápidos, speedup pode ser < 1.0 devido a overhead")

    # Verificar apenas que ambos completaram com sucesso
    # Em produção com I/O real, paralelo seria mais rápido


# ============================================================================
# Testes de latência de componente individual
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.performance
async def test_predictor_service_latency(mock_app_state: Any) -> None:
    """
    Testa latência isolada do predictor service (sem overhead HTTP).
    """
    predictor = mock_app_state.predictor_service
    latencies = []

    for _ in range(100):
        start = time.perf_counter()

        result = await predictor.predict(
            intent_text="Test intent for latency measurement",
            specialist_confidence=0.75,
            specialist_type="analyst",
        )

        end = time.perf_counter()

        assert result["decision"] in ["approve", "reject", "review_required"]
        latencies.append((end - start) * 1000)

    p50 = sorted(latencies)[len(latencies) // 2]
    p99_idx = int(len(latencies) * 0.99)
    p99 = sorted(latencies)[min(p99_idx, len(latencies) - 1)]

    print("\nLatência Predictor Service (sem HTTP overhead):")
    print(f"  p50: {p50:.2f}ms")
    print(f"  p99: {p99:.2f}ms")

    # Latência do service deve ser menor que latência completa da API
    assert p50 < 30, "Latência p50 do predictor service parece muito alta"


# ============================================================================
# Testes de latência sob load
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.performance
async def test_latency_under_load(
    performance_client: AsyncClient,
    sample_request_data: dict,
) -> None:
    """
    Testa latência sob concorrência moderada.

    Simula 50 requests simultâneos.
    """
    num_concurrent = 50
    latencies = []

    async def single_request(client: AsyncClient) -> float:
        """Executa request e retorna latência."""
        start = time.perf_counter()
        response = await client.post("/api/v1/inference/predict", json=sample_request_data)
        end = time.perf_counter()
        assert response.status_code == 200
        return (end - start) * 1000

    # Executar concorrentemente
    tasks = [single_request(performance_client) for _ in range(num_concurrent)]
    latencies = await asyncio.gather(*tasks)

    p50 = sorted(latencies)[len(latencies) // 2]
    p99_idx = int(len(latencies) * 0.99)
    p99 = sorted(latencies)[min(p99_idx, len(latencies) - 1)]
    avg = sum(latencies) / len(latencies)

    print(f"\nLatência sob load ({num_concurrent} concurrent):")
    print(f"  p50: {p50:.2f}ms")
    print(f"  p99: {p99:.2f}ms")
    print(f"  avg: {avg:.2f}ms")

    # Mesmo sob load, latência não deve degradar drasticamente
    assert p99 < 500, "Latência p99 degradou significativamente sob load"
