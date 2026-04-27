"""
Unit tests para Performance Tracker.
"""

import asyncio

import pytest

from neural_hive_llm.registry import (
    PerformanceTracker,
    RequestMetric,
    get_tracker,
    reset_tracker,
)


@pytest.fixture(autouse=True)
def reset_tracker_before_each():
    """Reseta tracker antes de cada teste."""
    reset_tracker()
    yield
    reset_tracker()


@pytest.mark.asyncio
async def test_tracker_initialization():
    """Testa inicialização do tracker."""
    tracker = get_tracker()

    metrics = await tracker.get_metrics("test-model")
    assert metrics["model_id"] == "test-model"
    assert metrics["request_count"] == 0
    assert metrics["success_rate"] == 0.0


@pytest.mark.asyncio
async def test_record_request():
    """Testa registro de requisição."""
    tracker = get_tracker()

    metric = RequestMetric(
        model_id="test-model",
        success=True,
        latency_ms=500.0,
        prompt_tokens=100,
        completion_tokens=200,
        estimated_cost_usd=0.01,
    )

    await tracker.record_request(metric)

    metrics = await tracker.get_metrics("test-model")
    assert metrics["request_count"] == 1
    assert metrics["success_count"] == 1
    assert metrics["failure_count"] == 0
    assert metrics["success_rate"] == 1.0
    assert metrics["avg_latency_ms"] == 500.0


@pytest.mark.asyncio
async def test_record_multiple_requests():
    """Testa registro de múltiplas requisições."""
    tracker = get_tracker()

    metrics = [
        RequestMetric(
            model_id="test-model",
            success=True,
            latency_ms=400.0,
            prompt_tokens=100,
            completion_tokens=200,
            estimated_cost_usd=0.01,
        ),
        RequestMetric(
            model_id="test-model",
            success=True,
            latency_ms=600.0,
            prompt_tokens=150,
            completion_tokens=250,
            estimated_cost_usd=0.015,
        ),
        RequestMetric(
            model_id="test-model",
            success=False,
            latency_ms=0.0,
            prompt_tokens=0,
            completion_tokens=0,
            estimated_cost_usd=0.0,
            error_message="timeout",
        ),
    ]

    for metric in metrics:
        await tracker.record_request(metric)

    result = await tracker.get_metrics("test-model")
    assert result["request_count"] == 3
    assert result["success_count"] == 2
    assert result["failure_count"] == 1
    assert result["success_rate"] == 2 / 3
    assert result["avg_latency_ms"] == 500.0  # Média apenas de sucessos


@pytest.mark.asyncio
async def test_metrics_calculation():
    """Testa cálculo de métricas agregadas."""
    tracker = get_tracker()

    # Registra 10 requisições com latências variadas
    for i in range(10):
        latency = 100 + (i * 50)  # 100, 150, 200, ..., 550
        await tracker.record_request(
            RequestMetric(
                model_id="test-model",
                success=True,
                latency_ms=float(latency),
                prompt_tokens=100,
                completion_tokens=200,
                estimated_cost_usd=0.01,
            )
        )

    metrics = await tracker.get_metrics("test-model")

    assert metrics["request_count"] == 10
    assert metrics["avg_latency_ms"] == 325.0
    assert metrics["p50_latency_ms"] == 325.0
    # P95 de [100, 150, 200, 250, 300, 350, 400, 450, 500, 550] é 527.5
    assert abs(metrics["p95_latency_ms"] - 527.5) < 0.1
    # P99 é aprox 545.5 (valor exacto pode variar ligeiramente)
    assert abs(metrics["p99_latency_ms"] - 545.5) < 1.0


@pytest.mark.asyncio
async def test_compare_models():
    """Testa comparação entre modelos."""
    tracker = get_tracker()

    # Registra métricas para modelo A (mais rápido)
    for _ in range(10):
        await tracker.record_request(
            RequestMetric(
                model_id="model-a",
                success=True,
                latency_ms=200.0,
                prompt_tokens=100,
                completion_tokens=200,
                estimated_cost_usd=0.01,
            )
        )

    # Registra métricas para modelo B (mais barato)
    for _ in range(10):
        await tracker.record_request(
            RequestMetric(
                model_id="model-b",
                success=True,
                latency_ms=500.0,
                prompt_tokens=100,
                completion_tokens=200,
                estimated_cost_usd=0.005,
            )
        )

    comparison = await tracker.compare_models(["model-a", "model-b"])

    assert comparison["best_performance"] == "model-a"
    assert comparison["best_cost"] == "model-b"


@pytest.mark.asyncio
async def test_health_status():
    """Testa status de saúde de modelo."""
    tracker = get_tracker()

    # Modelo sem métricas
    health = await tracker.get_health_status("unknown-model")
    assert health["health"] == "unknown"

    # Modelo saudável (> 99% sucesso)
    for _ in range(10):
        await tracker.record_request(
            RequestMetric(
                model_id="healthy-model",
                success=True,
                latency_ms=200.0,
                prompt_tokens=100,
                completion_tokens=200,
                estimated_cost_usd=0.01,
            )
        )

    health = await tracker.get_health_status("healthy-model")
    assert health["health"] == "healthy"

    # Modelo degradado (95-99% sucesso)
    for i in range(100):
        success = i < 97  # 97% sucesso
        await tracker.record_request(
            RequestMetric(
                model_id="degraded-model",
                success=success,
                latency_ms=300.0 if success else 0.0,
                prompt_tokens=100,
                completion_tokens=200,
                estimated_cost_usd=0.01 if success else 0.0,
            )
        )

    health = await tracker.get_health_status("degraded-model")
    assert health["health"] == "degraded"

    # Modelo não saudável (< 95% sucesso)
    for i in range(100):
        success = i < 80  # 80% sucesso
        await tracker.record_request(
            RequestMetric(
                model_id="unhealthy-model",
                success=success,
                latency_ms=400.0 if success else 0.0,
                prompt_tokens=100,
                completion_tokens=200,
                estimated_cost_usd=0.01 if success else 0.0,
            )
        )

    health = await tracker.get_health_status("unhealthy-model")
    assert health["health"] == "unhealthy"


@pytest.mark.asyncio
async def test_cleanup_old_metrics():
    """Testa limpeza de métricas antigas."""
    tracker = PerformanceTracker(max_history_size=1000, window_minutes=1)

    # Registra métrica atual
    await tracker.record_request(
        RequestMetric(
            model_id="test-model",
            success=True,
            latency_ms=200.0,
            prompt_tokens=100,
            completion_tokens=200,
            estimated_cost_usd=0.01,
        )
    )

    metrics = await tracker.get_metrics("test-model")
    assert metrics["request_count"] == 1

    # Aguarda janela passar
    await asyncio.sleep(70)

    # Registra nova métrica (triggers cleanup)
    await tracker.record_request(
        RequestMetric(
            model_id="test-model",
            success=True,
            latency_ms=300.0,
            prompt_tokens=100,
            completion_tokens=200,
            estimated_cost_usd=0.01,
        )
    )

    # Métricas antigas devem ter sido removidas
    metrics = await tracker.get_metrics("test-model", window_minutes=5)
    # Apenas a métrica recente deve estar presente
    assert metrics["request_count"] == 1


@pytest.mark.asyncio
async def test_max_history_size():
    """Testa limite máximo de histórico."""
    tracker = PerformanceTracker(max_history_size=5, window_minutes=60)

    # Registra 10 requisições
    for i in range(10):
        await tracker.record_request(
            RequestMetric(
                model_id="test-model",
                success=True,
                latency_ms=100.0 + i * 10,
                prompt_tokens=100,
                completion_tokens=200,
                estimated_cost_usd=0.01,
            )
        )

    metrics = await tracker.get_metrics("test-model")
    # Apenas as últimas 5 devem estar presentes
    assert metrics["request_count"] == 5


@pytest.mark.asyncio
async def test_tokens_per_second():
    """Testa cálculo de tokens por segundo."""
    tracker = get_tracker()

    # Requisição com 200 tokens em 500ms = 400 tokens/seg
    await tracker.record_request(
        RequestMetric(
            model_id="test-model",
            success=True,
            latency_ms=500.0,
            prompt_tokens=100,
            completion_tokens=200,
            estimated_cost_usd=0.01,
        )
    )

    metrics = await tracker.get_metrics("test-model")
    assert abs(metrics["avg_tokens_per_second"] - 400.0) < 1.0


@pytest.mark.asyncio
async def test_cost_aggregation():
    """Testa agregação de custos."""
    tracker = get_tracker()

    await tracker.record_request(
        RequestMetric(
            model_id="test-model",
            success=True,
            latency_ms=500.0,
            prompt_tokens=1000,
            completion_tokens=500,
            estimated_cost_usd=0.05,
        )
    )

    await tracker.record_request(
        RequestMetric(
            model_id="test-model",
            success=True,
            latency_ms=600.0,
            prompt_tokens=800,
            completion_tokens=400,
            estimated_cost_usd=0.04,
        )
    )

    metrics = await tracker.get_metrics("test-model")

    assert metrics["total_cost_usd"] == 0.09
    assert metrics["total_tokens_in"] == 1800
    assert metrics["total_tokens_out"] == 900
    assert metrics["avg_cost_per_1k_tokens"] == 0.09 / 2.7


@pytest.mark.asyncio
async def test_cleanup_all():
    """Testa limpeza de todos os dados."""
    tracker = get_tracker()

    # Registra alguns dados
    for i in range(5):
        await tracker.record_request(
            RequestMetric(
                model_id="test-model",
                success=True,
                latency_ms=200.0,
                prompt_tokens=100,
                completion_tokens=200,
                estimated_cost_usd=0.01,
            )
        )

    metrics = await tracker.get_metrics("test-model")
    assert metrics["request_count"] == 5

    # Limpa tudo
    await tracker.cleanup()

    metrics = await tracker.get_metrics("test-model")
    assert metrics["request_count"] == 0
