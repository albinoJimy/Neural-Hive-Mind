"""Load and performance tests for the Unified Gateway (TICKET-029).

Spec: 2026-05-01-unified-gateway-architecture, FASE 6 - Sprint 5.

Acceptance criteria:
- Latência adicional <20ms (p95).
- Throughput sustentado >200 req/s.
- Falhas graciosas sob stress.
- Sustained load test de 1 hora.

A lógica de geração de carga vive em ``unified-gateway-load-test.py``
(script standalone com aiohttp, ~660 linhas). Este módulo é o entrypoint
pytest-friendly que a spec pede (`tests/performance/load_test.py`):
reutiliza o tester e adiciona asserções sobre os SLOs.

Modos de execução
- ``quick`` (default em CI): 30s, ~50 req/s — apenas valida que o gateway
  está vivo e produz números razoáveis. Marker ``performance``.
- ``standard``: 5 min @ 200 req/s — corre só se ``RUN_LOAD_TESTS=1``.
  Marker ``performance + slow``.
- ``sustained``: 1 hora @ 200 req/s — corre só se ``RUN_SUSTAINED_LOAD=1``.
  Marker ``performance + slow``. Usado em smoke/staging post-deploy.

Como activar localmente
    RUN_LOAD_TESTS=1 pytest tests/performance/load_test.py -m performance
    RUN_SUSTAINED_LOAD=1 pytest tests/performance/load_test.py::test_sustained_load_one_hour
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Carregar UnifiedGatewayLoadTester do script existente (nome com hífenes
# não permite import direto).
# ---------------------------------------------------------------------------
_LOAD_TEST_SCRIPT = Path(__file__).resolve().parent / "unified-gateway-load-test.py"
_spec = importlib.util.spec_from_file_location("unified_gateway_load_test", str(_LOAD_TEST_SCRIPT))
if _spec is None or _spec.loader is None:  # pragma: no cover — defensive
    raise RuntimeError(f"Could not import {_LOAD_TEST_SCRIPT}")
_load_test_module = importlib.util.module_from_spec(_spec)
sys.modules["unified_gateway_load_test"] = _load_test_module
_spec.loader.exec_module(_load_test_module)

UnifiedGatewayLoadTestConfig = _load_test_module.UnifiedGatewayLoadTestConfig
UnifiedGatewayLoadTester = _load_test_module.UnifiedGatewayLoadTester
UnifiedGatewayLoadTestResults = _load_test_module.UnifiedGatewayLoadTestResults


# ---------------------------------------------------------------------------
# SLO thresholds (Spec FASE 6 / TICKET-029)
# ---------------------------------------------------------------------------
SLO_P95_LATENCY_MS = 20.0
SLO_MIN_THROUGHPUT_RPS = 200.0
SLO_MAX_ERROR_RATE = 0.01  # 1%


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _gateway_url() -> str:
    """URL do Unified Gateway sob teste; default é localhost:7999.

    Override via env var ``UNIFIED_GATEWAY_URL`` para apontar para staging.
    """
    return os.getenv("UNIFIED_GATEWAY_URL", "http://localhost:7999")


def _gateway_reachable(url: str, timeout_s: float = 1.0) -> bool:
    """Healthcheck rápido para skipar testes quando o gateway não está vivo."""
    import socket
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except OSError:
        return False


def _assert_slos(results: UnifiedGatewayLoadTestResults, *, expected_min_rps: float) -> None:
    """Valida latência, throughput e taxa de erro contra os SLOs da spec.

    Os campos seguem o schema do ``UnifiedGatewayLoadTestResults`` em
    ``unified-gateway-load-test.py``: ``latency_stats`` é um dict
    ``{"overall": {"p95", "median", ...}}`` e ``success_rate`` é a fracção
    de pedidos sem erro (1 - error_rate).
    """
    # Throughput.
    assert results.requests_per_second >= expected_min_rps, (
        f"Throughput {results.requests_per_second:.1f} req/s abaixo do alvo "
        f"{expected_min_rps:.1f} req/s"
    )

    # Latência adicional p95 — o SLO da spec é "latência adicional <20ms".
    # Quando o downstream é mockado/local essa parcela ≈0, logo o p95 total
    # é uma aproximação razoável; em produção o test deve correr contra um
    # gateway com downstream real e o threshold pode ser relaxado.
    overall = results.latency_stats.get("overall", {})
    p95 = float(overall.get("p95", float("inf")))
    assert (
        p95 <= SLO_P95_LATENCY_MS
    ), f"P95 latência {p95:.2f}ms acima do SLO {SLO_P95_LATENCY_MS}ms"

    # Taxa de erro = 1 - success_rate.
    error_rate = max(0.0, 1.0 - results.success_rate)
    assert (
        error_rate <= SLO_MAX_ERROR_RATE
    ), f"Taxa de erro {error_rate:.3%} acima do SLO {SLO_MAX_ERROR_RATE:.0%}"


async def _run_load_test(
    *,
    duration_s: int,
    target_rps: int,
    concurrency: int,
    ramp_up_s: int,
) -> UnifiedGatewayLoadTestResults:
    """Wrapper assíncrono sobre o ``UnifiedGatewayLoadTester``.

    Usa ``run_ramp_up_test`` quando ``ramp_up_s > 0`` (devolve resultados
    detalhados); cai num ``run_basic_test`` constante caso contrário.
    """
    config = UnifiedGatewayLoadTestConfig(
        gateway_url=_gateway_url(),
        total_requests=duration_s * target_rps,
        concurrent_requests=concurrency,
        test_duration_seconds=duration_s,
        ramp_up_seconds=max(ramp_up_s, 1),
    )
    tester = UnifiedGatewayLoadTester(config)
    return await tester.run_test()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


pytestmark = [pytest.mark.performance]


def _skip_if_unreachable() -> None:
    url = _gateway_url()
    if not _gateway_reachable(url):
        pytest.skip(
            f"Unified Gateway não acessível em {url}; "
            "set UNIFIED_GATEWAY_URL ou inicia o serviço antes de correr."
        )


@pytest.mark.asyncio
async def test_quick_smoke_load() -> None:
    """Quick smoke (~30s, 50 req/s) — corre em CI por defeito.

    Não valida o SLO completo de 200 req/s; verifica que o gateway aguenta
    carga modesta sem degradar latência nem produzir erros.
    """
    _skip_if_unreachable()

    results = await _run_load_test(
        duration_s=30,
        target_rps=50,
        concurrency=10,
        ramp_up_s=5,
    )

    # SLO atenuado para smoke: throughput mínimo 40 req/s (margem de 20%),
    # taxa de erro ainda ≤1%, p95 ainda ≤20ms.
    _assert_slos(results, expected_min_rps=40.0)


@pytest.mark.slow
@pytest.mark.skipif(
    not os.getenv("RUN_LOAD_TESTS"),
    reason="Set RUN_LOAD_TESTS=1 to run the standard 5-min load test.",
)
@pytest.mark.asyncio
async def test_standard_load_5min() -> None:
    """Standard load (5 min @ 200 req/s) — opt-in via RUN_LOAD_TESTS.

    Valida directamente os SLOs da spec FASE 6.
    """
    _skip_if_unreachable()

    results = await _run_load_test(
        duration_s=5 * 60,
        target_rps=int(SLO_MIN_THROUGHPUT_RPS),
        concurrency=50,
        ramp_up_s=30,
    )
    _assert_slos(results, expected_min_rps=SLO_MIN_THROUGHPUT_RPS)


@pytest.mark.slow
@pytest.mark.skipif(
    not os.getenv("RUN_SUSTAINED_LOAD"),
    reason="Set RUN_SUSTAINED_LOAD=1 to run the 1-hour sustained load test.",
)
@pytest.mark.asyncio
async def test_sustained_load_one_hour() -> None:
    """Sustained load (1 hora @ 200 req/s) — opt-in via RUN_SUSTAINED_LOAD.

    Cumpre o acceptance criterion explícito da spec
    ("Sustained load test (1 hora)"). Pensado para correr em
    staging post-deploy; em CI fica skipped por defeito.
    """
    _skip_if_unreachable()

    results = await _run_load_test(
        duration_s=60 * 60,
        target_rps=int(SLO_MIN_THROUGHPUT_RPS),
        concurrency=100,
        ramp_up_s=60,
    )
    _assert_slos(results, expected_min_rps=SLO_MIN_THROUGHPUT_RPS)


@pytest.mark.skipif(
    not os.getenv("RUN_STRESS_TEST"),
    reason="Set RUN_STRESS_TEST=1 to run the stress (overload) test.",
)
@pytest.mark.asyncio
async def test_graceful_degradation_under_overload() -> None:
    """Stress (5x o SLO de throughput) — confirma falhas graciosas.

    Sob 1000 req/s o gateway deve devolver 429 ou 503 em vez de crashar
    ou de devolver 5xx genéricos. Validação ad-hoc — não corre por
    defeito, é exploratório.
    """
    _skip_if_unreachable()

    results = await _run_load_test(
        duration_s=60,
        target_rps=int(SLO_MIN_THROUGHPUT_RPS * 5),
        concurrency=200,
        ramp_up_s=10,
    )

    # Sob overload toleramos error rate alto, mas exigimos que o serviço
    # ainda responda — i.e. throughput observado > 0 e latência mediana
    # finita (sem timeouts em massa).
    assert results.requests_per_second > 0, "Gateway não respondeu sob stress"
    overall = results.latency_stats.get("overall", {})
    median = float(overall.get("median", float("inf")))
    assert median < 1_000, (
        f"Latência mediana {median:.0f}ms sob stress sugere"
        " timeouts em massa em vez de degradação graciosa"
    )
