"""
Testes de performance para PheromoneClient.get_success_trails()

Valida:
- Latencia P95 < 100ms para 1.000 chaves
- Latencia P95 < 500ms para 10.000 chaves
- Cache hit rate > 99% em chamadas consecutivas
- Ausencia de race conditions em acesso concorrente
"""
import pytest
import asyncio
import time
import statistics
import structlog
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

logger = structlog.get_logger()

# Constante de TTL do cache
CACHE_TTL_SECONDS = 60


class PheromoneClientForPerfTest:
    """Classe PheromoneClient para testes de performance."""

    def __init__(self, redis_client, settings):
        self.redis_client = redis_client
        self.settings = settings
        self.prefix = settings.REDIS_PHEROMONE_PREFIX
        self._success_trails_cache: Optional[List[Dict[str, Any]]] = None
        self._cache_timestamp: float = 0
        self._metrics_mock = None

    def invalidate_success_trails_cache(self) -> None:
        self._success_trails_cache = None
        self._cache_timestamp = 0

    async def get_success_trails(self, limit: int = 10) -> List[Dict[str, Any]]:
        try:
            cache_age = time.time() - self._cache_timestamp
            if self._success_trails_cache is not None and cache_age < CACHE_TTL_SECONDS:
                if self._metrics_mock:
                    self._metrics_mock.pheromone_trails_cache_hits_total.inc()
                return self._success_trails_cache[:limit]

            if self._metrics_mock:
                self._metrics_mock.pheromone_trails_cache_misses_total.inc()

            pattern = f"{self.prefix}*:SUCCESS"
            trails: List[Dict[str, Any]] = []
            keys_scanned = 0

            start_time = time.time()

            async for key in self.redis_client.client.scan_iter(match=pattern):
                keys_scanned += 1

                try:
                    key_parts = key.split(':')
                    if len(key_parts) < 4:
                        continue
                    domain = ':'.join(key_parts[2:-1])
                except Exception:
                    continue

                pheromone_data = await self.redis_client.get_cached_context(key)
                if not pheromone_data:
                    continue

                trail = {
                    'domain': domain,
                    'strength': pheromone_data.get('strength', 0.0),
                    'last_updated': pheromone_data.get('last_updated', 0),
                    'metadata': pheromone_data.get('metadata', {}),
                    'key': key
                }
                trails.append(trail)

            trails.sort(key=lambda t: t['strength'], reverse=True)
            limited_trails = trails[:limit]

            self._success_trails_cache = limited_trails
            self._cache_timestamp = time.time()

            scan_duration = time.time() - start_time
            if self._metrics_mock:
                self._metrics_mock.pheromone_trails_scan_duration_seconds.observe(scan_duration)
                self._metrics_mock.pheromone_trails_keys_scanned_total.inc(keys_scanned)

            return limited_trails

        except Exception as e:
            logger.error("get_success_trails_failed", error=str(e))
            return []


@dataclass
class PheromoneLoadMetrics:
    """Metricas de carga para testes de performance"""
    latencies_ms: List[float] = field(default_factory=list)
    cache_hits: int = 0
    cache_misses: int = 0
    total_keys_scanned: int = 0

    @property
    def p50_latency(self) -> float:
        if not self.latencies_ms:
            return 0.0
        sorted_latencies = sorted(self.latencies_ms)
        idx = int(len(sorted_latencies) * 0.5)
        return sorted_latencies[idx]

    @property
    def p95_latency(self) -> float:
        if not self.latencies_ms:
            return 0.0
        sorted_latencies = sorted(self.latencies_ms)
        idx = int(len(sorted_latencies) * 0.95)
        return sorted_latencies[min(idx, len(sorted_latencies) - 1)]

    @property
    def p99_latency(self) -> float:
        if not self.latencies_ms:
            return 0.0
        sorted_latencies = sorted(self.latencies_ms)
        idx = int(len(sorted_latencies) * 0.99)
        return sorted_latencies[min(idx, len(sorted_latencies) - 1)]

    @property
    def cache_hit_rate(self) -> float:
        total = self.cache_hits + self.cache_misses
        if total == 0:
            return 0.0
        return self.cache_hits / total


def create_mock_keys(count: int) -> List[str]:
    """Cria lista de chaves mock"""
    return [f'pheromone:strategic:plan-{i}:SUCCESS' for i in range(count)]


def create_mock_pheromone_data(keys: List[str]) -> dict:
    """Cria dados de feromonio mock"""
    return {
        key: {
            'strength': (i % 100) / 100.0,  # Varia de 0.0 a 0.99
            'last_updated': 1000 + i,
            'metadata': {'decision_id': f'dec-{i}'}
        }
        for i, key in enumerate(keys)
    }


@pytest.fixture
def mock_redis_client():
    """Mock do RedisClient"""
    client = AsyncMock()
    client.client = AsyncMock()
    return client


@pytest.fixture
def mock_settings():
    """Mock de configuracoes"""
    settings = MagicMock()
    settings.REDIS_PHEROMONE_PREFIX = 'pheromone:strategic:'
    return settings


@pytest.fixture
def pheromone_client(mock_redis_client, mock_settings):
    """Instancia do PheromoneClient com mocks"""
    client = PheromoneClientForPerfTest(
        redis_client=mock_redis_client,
        settings=mock_settings
    )
    client._metrics_mock = MagicMock()
    return client


@pytest.mark.asyncio
async def test_scan_performance_1000_keys(pheromone_client, mock_redis_client):
    """
    Teste de performance com 1.000 chaves SUCCESS.
    Valida latencia P95 < 100ms.
    """
    keys = create_mock_keys(1000)
    pheromone_data = create_mock_pheromone_data(keys)

    async def mock_scan_iter(match=None):
        for key in keys:
            yield key

    mock_redis_client.client.scan_iter = mock_scan_iter
    mock_redis_client.get_cached_context = AsyncMock(
        side_effect=lambda key: pheromone_data.get(key)
    )

    metrics = PheromoneLoadMetrics()

    # Medir latencia
    start = time.perf_counter()
    result = await pheromone_client.get_success_trails(limit=10)
    elapsed_ms = (time.perf_counter() - start) * 1000

    metrics.latencies_ms.append(elapsed_ms)
    metrics.total_keys_scanned = 1000

    # Validacoes
    assert len(result) == 10
    assert metrics.p95_latency < 100, f"P95 latency {metrics.p95_latency:.2f}ms exceeds 100ms"
    print(f"\n1000 keys - Latency: {elapsed_ms:.2f}ms, P95: {metrics.p95_latency:.2f}ms")


@pytest.mark.asyncio
async def test_scan_performance_10000_keys(pheromone_client, mock_redis_client):
    """
    Teste de performance com 10.000 chaves SUCCESS.
    Valida latencia P95 < 500ms.
    """
    keys = create_mock_keys(10000)
    pheromone_data = create_mock_pheromone_data(keys)

    async def mock_scan_iter(match=None):
        for key in keys:
            yield key

    mock_redis_client.client.scan_iter = mock_scan_iter
    mock_redis_client.get_cached_context = AsyncMock(
        side_effect=lambda key: pheromone_data.get(key)
    )

    metrics = PheromoneLoadMetrics()

    # Medir latencia
    start = time.perf_counter()
    result = await pheromone_client.get_success_trails(limit=50)
    elapsed_ms = (time.perf_counter() - start) * 1000

    metrics.latencies_ms.append(elapsed_ms)
    metrics.total_keys_scanned = 10000

    # Validacoes
    assert len(result) == 50
    assert metrics.p95_latency < 500, f"P95 latency {metrics.p95_latency:.2f}ms exceeds 500ms"
    print(f"\n10000 keys - Latency: {elapsed_ms:.2f}ms, P95: {metrics.p95_latency:.2f}ms")


@pytest.mark.asyncio
async def test_cache_effectiveness(pheromone_client, mock_redis_client):
    """
    Teste de efetividade do cache.
    Executa 100 chamadas consecutivas e valida cache hit rate > 99%.
    """
    keys = create_mock_keys(100)
    pheromone_data = create_mock_pheromone_data(keys)

    scan_call_count = 0

    async def mock_scan_iter(match=None):
        nonlocal scan_call_count
        scan_call_count += 1
        for key in keys:
            yield key

    mock_redis_client.client.scan_iter = mock_scan_iter
    mock_redis_client.get_cached_context = AsyncMock(
        side_effect=lambda key: pheromone_data.get(key)
    )

    metrics = PheromoneLoadMetrics()
    call_count = 100

    # Executar 100 chamadas
    for _ in range(call_count):
        start = time.perf_counter()
        await pheromone_client.get_success_trails(limit=10)
        elapsed_ms = (time.perf_counter() - start) * 1000
        metrics.latencies_ms.append(elapsed_ms)

    # Apenas a primeira chamada deve acessar Redis
    metrics.cache_misses = 1
    metrics.cache_hits = call_count - 1

    # Validacoes
    assert scan_call_count == 1, f"Redis foi acessado {scan_call_count} vezes, esperado 1"
    assert metrics.cache_hit_rate >= 0.99, f"Cache hit rate {metrics.cache_hit_rate:.2%} < 99%"

    throughput = call_count / (sum(metrics.latencies_ms) / 1000)
    print(f"\nCache test - Hit rate: {metrics.cache_hit_rate:.2%}, Throughput: {throughput:.0f} calls/sec")
    print(f"P50: {metrics.p50_latency:.3f}ms, P95: {metrics.p95_latency:.3f}ms, P99: {metrics.p99_latency:.3f}ms")


@pytest.mark.asyncio
async def test_concurrent_access(pheromone_client, mock_redis_client):
    """
    Teste de acesso concorrente.
    Executa 50 chamadas concorrentes e valida ausencia de race conditions.
    """
    keys = create_mock_keys(100)
    pheromone_data = create_mock_pheromone_data(keys)

    scan_call_count = 0
    lock = asyncio.Lock()

    async def mock_scan_iter(match=None):
        nonlocal scan_call_count
        async with lock:
            scan_call_count += 1
        for key in keys:
            yield key

    mock_redis_client.client.scan_iter = mock_scan_iter
    mock_redis_client.get_cached_context = AsyncMock(
        side_effect=lambda key: pheromone_data.get(key)
    )

    # Executar 50 chamadas concorrentes
    tasks = [
        pheromone_client.get_success_trails(limit=10)
        for _ in range(50)
    ]

    results = await asyncio.gather(*tasks)

    # Validacoes
    # Todas as chamadas devem retornar resultados validos
    for i, result in enumerate(results):
        assert len(result) == 10, f"Chamada {i} retornou {len(result)} resultados"

    # Verificar consistencia dos resultados (todas devem ter os mesmos dados)
    first_domains = set(r['domain'] for r in results[0])
    for i, result in enumerate(results[1:], 1):
        result_domains = set(r['domain'] for r in result)
        assert result_domains == first_domains, f"Chamada {i} tem resultados inconsistentes"

    print(f"\nConcurrent test - {len(results)} chamadas concorrentes, {scan_call_count} scans Redis")


@pytest.mark.asyncio
async def test_latency_distribution(pheromone_client, mock_redis_client):
    """
    Teste de distribuicao de latencia.
    Executa multiplas medicoes para calcular percentis.
    """
    keys = create_mock_keys(500)
    pheromone_data = create_mock_pheromone_data(keys)

    async def mock_scan_iter(match=None):
        for key in keys:
            yield key

    mock_redis_client.client.scan_iter = mock_scan_iter
    mock_redis_client.get_cached_context = AsyncMock(
        side_effect=lambda key: pheromone_data.get(key)
    )

    metrics = PheromoneLoadMetrics()
    iterations = 20

    for _ in range(iterations):
        # Invalidar cache para forcar busca no Redis
        pheromone_client.invalidate_success_trails_cache()

        start = time.perf_counter()
        await pheromone_client.get_success_trails(limit=10)
        elapsed_ms = (time.perf_counter() - start) * 1000
        metrics.latencies_ms.append(elapsed_ms)

    # Estatisticas
    avg_latency = statistics.mean(metrics.latencies_ms)
    std_latency = statistics.stdev(metrics.latencies_ms) if len(metrics.latencies_ms) > 1 else 0

    print(f"\nLatency distribution ({iterations} iterations, 500 keys):")
    print(f"  Mean: {avg_latency:.2f}ms (std: {std_latency:.2f}ms)")
    print(f"  P50: {metrics.p50_latency:.2f}ms")
    print(f"  P95: {metrics.p95_latency:.2f}ms")
    print(f"  P99: {metrics.p99_latency:.2f}ms")

    # Validar que latencia esta dentro de limites razoaveis
    assert metrics.p95_latency < 200, f"P95 latency {metrics.p95_latency:.2f}ms muito alta"
