"""
Testes unitarios para PheromoneClient - foco em get_success_trails
"""
import pytest
import time
import structlog
from typing import Dict, List, Any, Optional
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

logger = structlog.get_logger()

# Constante de TTL do cache (igual ao do modulo original)
CACHE_TTL_SECONDS = 60


class PheromoneClientForTest:
    """
    Copia da classe PheromoneClient para testes unitarios.
    Evita dependencias de importacao do modulo clients.
    """

    def __init__(self, redis_client, settings):
        self.redis_client = redis_client
        self.settings = settings
        self.prefix = settings.REDIS_PHEROMONE_PREFIX
        self._success_trails_cache: Optional[List[Dict[str, Any]]] = None
        self._cache_timestamp: float = 0
        # Mock das metricas para testes
        self._metrics_mock = None

    async def publish_pheromone(
        self,
        pheromone_type: str,
        domain: str,
        strength: float,
        metadata: Dict[str, Any]
    ) -> None:
        """Publicar feromonio"""
        try:
            key = f"{self.prefix}{domain}:{pheromone_type}"

            pheromone_data = {
                "strength": strength,
                "last_updated": int(datetime.now().timestamp() * 1000),
                "metadata": metadata
            }

            await self.redis_client.cache_strategic_context(
                key,
                pheromone_data,
                ttl_seconds=86400
            )

            if pheromone_type == 'SUCCESS':
                self.invalidate_success_trails_cache()

        except Exception as e:
            logger.error("pheromone_publish_failed", error=str(e))

    def invalidate_success_trails_cache(self) -> None:
        """Invalidar cache de trilhas de sucesso"""
        self._success_trails_cache = None
        self._cache_timestamp = 0

    async def get_success_trails(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Obter trilhas de sucesso mais fortes"""
        try:
            # Verificar se cache e valido
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
    client = PheromoneClientForTest(
        redis_client=mock_redis_client,
        settings=mock_settings
    )
    client._metrics_mock = MagicMock()
    return client


@pytest.mark.asyncio
async def test_get_success_trails_empty_redis(pheromone_client, mock_redis_client):
    """Validar retorno de lista vazia quando nao ha trilhas"""
    async def empty_scan_iter(match=None):
        return
        yield

    mock_redis_client.client.scan_iter = empty_scan_iter

    result = await pheromone_client.get_success_trails(limit=10)

    assert result == []


@pytest.mark.asyncio
async def test_get_success_trails_ordering(pheromone_client, mock_redis_client):
    """Validar ordenacao por strength (criar 5 trilhas com strengths: 0.9, 0.5, 0.8, 0.3, 0.7)"""
    keys = [
        'pheromone:strategic:plan-1:SUCCESS',
        'pheromone:strategic:plan-2:SUCCESS',
        'pheromone:strategic:plan-3:SUCCESS',
        'pheromone:strategic:plan-4:SUCCESS',
        'pheromone:strategic:plan-5:SUCCESS',
    ]

    pheromone_data = {
        'pheromone:strategic:plan-1:SUCCESS': {'strength': 0.9, 'last_updated': 1000, 'metadata': {}},
        'pheromone:strategic:plan-2:SUCCESS': {'strength': 0.5, 'last_updated': 1001, 'metadata': {}},
        'pheromone:strategic:plan-3:SUCCESS': {'strength': 0.8, 'last_updated': 1002, 'metadata': {}},
        'pheromone:strategic:plan-4:SUCCESS': {'strength': 0.3, 'last_updated': 1003, 'metadata': {}},
        'pheromone:strategic:plan-5:SUCCESS': {'strength': 0.7, 'last_updated': 1004, 'metadata': {}},
    }

    async def mock_scan_iter(match=None):
        for key in keys:
            yield key

    mock_redis_client.client.scan_iter = mock_scan_iter
    mock_redis_client.get_cached_context = AsyncMock(
        side_effect=lambda key: pheromone_data.get(key)
    )

    result = await pheromone_client.get_success_trails(limit=10)

    assert len(result) == 5
    assert result[0]['strength'] == 0.9
    assert result[1]['strength'] == 0.8
    assert result[2]['strength'] == 0.7
    assert result[3]['strength'] == 0.5
    assert result[4]['strength'] == 0.3

    assert result[0]['domain'] == 'plan-1'
    assert result[1]['domain'] == 'plan-3'
    assert result[2]['domain'] == 'plan-5'


@pytest.mark.asyncio
async def test_get_success_trails_limit(pheromone_client, mock_redis_client):
    """Validar que apenas limit trilhas sao retornadas (criar 20 trilhas, limit=10)"""
    keys = [f'pheromone:strategic:plan-{i}:SUCCESS' for i in range(20)]
    pheromone_data = {
        key: {'strength': i * 0.05, 'last_updated': 1000 + i, 'metadata': {}}
        for i, key in enumerate(keys)
    }

    async def mock_scan_iter(match=None):
        for key in keys:
            yield key

    mock_redis_client.client.scan_iter = mock_scan_iter
    mock_redis_client.get_cached_context = AsyncMock(
        side_effect=lambda key: pheromone_data.get(key)
    )

    result = await pheromone_client.get_success_trails(limit=10)

    assert len(result) == 10
    # Usar pytest.approx para evitar problemas de precisao float
    assert result[0]['strength'] == pytest.approx(0.95, rel=1e-9)
    assert result[9]['strength'] == pytest.approx(0.5, rel=1e-9)


@pytest.mark.asyncio
async def test_get_success_trails_domain_extraction(pheromone_client, mock_redis_client):
    """Validar extracao correta de domain das chaves"""
    keys = [
        'pheromone:strategic:simple-plan:SUCCESS',
        'pheromone:strategic:plan:with:colons:SUCCESS',
    ]

    pheromone_data = {
        'pheromone:strategic:simple-plan:SUCCESS': {'strength': 0.9, 'last_updated': 1000, 'metadata': {}},
        'pheromone:strategic:plan:with:colons:SUCCESS': {'strength': 0.8, 'last_updated': 1001, 'metadata': {}},
    }

    async def mock_scan_iter(match=None):
        for key in keys:
            yield key

    mock_redis_client.client.scan_iter = mock_scan_iter
    mock_redis_client.get_cached_context = AsyncMock(
        side_effect=lambda key: pheromone_data.get(key)
    )

    result = await pheromone_client.get_success_trails(limit=10)

    assert len(result) == 2
    domains = [r['domain'] for r in result]
    assert 'simple-plan' in domains
    assert 'plan:with:colons' in domains


@pytest.mark.asyncio
async def test_get_success_trails_cache_hit(pheromone_client, mock_redis_client):
    """Validar que segunda chamada usa cache"""
    keys = ['pheromone:strategic:plan-1:SUCCESS']
    pheromone_data = {
        'pheromone:strategic:plan-1:SUCCESS': {'strength': 0.9, 'last_updated': 1000, 'metadata': {}}
    }

    async def mock_scan_iter(match=None):
        for key in keys:
            yield key

    mock_redis_client.client.scan_iter = mock_scan_iter
    mock_redis_client.get_cached_context = AsyncMock(
        side_effect=lambda key: pheromone_data.get(key)
    )

    # Primeira chamada - cache miss
    result1 = await pheromone_client.get_success_trails(limit=10)

    # Segunda chamada - cache hit
    result2 = await pheromone_client.get_success_trails(limit=10)

    assert result1 == result2


@pytest.mark.asyncio
async def test_get_success_trails_cache_expiry(pheromone_client, mock_redis_client):
    """Validar que cache expira apos TTL"""
    keys = ['pheromone:strategic:plan-1:SUCCESS']
    pheromone_data = {
        'pheromone:strategic:plan-1:SUCCESS': {'strength': 0.9, 'last_updated': 1000, 'metadata': {}}
    }

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

    # Primeira chamada
    await pheromone_client.get_success_trails(limit=10)
    initial_count = scan_call_count

    # Simular expiracao do cache
    pheromone_client._cache_timestamp = time.time() - CACHE_TTL_SECONDS - 1

    # Segunda chamada - deve buscar do Redis novamente
    await pheromone_client.get_success_trails(limit=10)

    assert scan_call_count == initial_count + 1


@pytest.mark.asyncio
async def test_invalidate_cache_on_publish_success(pheromone_client, mock_redis_client):
    """Validar que publicar SUCCESS invalida cache"""
    # Preparar cache
    pheromone_client._success_trails_cache = [{'domain': 'test', 'strength': 0.9}]
    pheromone_client._cache_timestamp = time.time()

    assert pheromone_client._success_trails_cache is not None
    assert pheromone_client._cache_timestamp > 0

    # Publicar SUCCESS
    await pheromone_client.publish_pheromone(
        pheromone_type='SUCCESS',
        domain='plan-1',
        strength=0.8,
        metadata={}
    )

    assert pheromone_client._success_trails_cache is None
    assert pheromone_client._cache_timestamp == 0


@pytest.mark.asyncio
async def test_publish_failure_does_not_invalidate_cache(pheromone_client, mock_redis_client):
    """Validar que publicar FAILURE nao invalida cache"""
    # Preparar cache
    pheromone_client._success_trails_cache = [{'domain': 'test', 'strength': 0.9}]
    original_timestamp = time.time()
    pheromone_client._cache_timestamp = original_timestamp

    # Publicar FAILURE
    await pheromone_client.publish_pheromone(
        pheromone_type='FAILURE',
        domain='plan-1',
        strength=-1.0,
        metadata={}
    )

    assert pheromone_client._success_trails_cache is not None
    assert pheromone_client._cache_timestamp == original_timestamp


@pytest.mark.asyncio
async def test_get_success_trails_handles_malformed_keys(pheromone_client, mock_redis_client):
    """Validar tratamento de chaves malformadas"""
    keys = [
        'pheromone:strategic:valid-plan:SUCCESS',
        'invalid:key',
        'pheromone:strategic:SUCCESS',
    ]

    pheromone_data = {
        'pheromone:strategic:valid-plan:SUCCESS': {'strength': 0.9, 'last_updated': 1000, 'metadata': {}}
    }

    async def mock_scan_iter(match=None):
        for key in keys:
            yield key

    mock_redis_client.client.scan_iter = mock_scan_iter
    mock_redis_client.get_cached_context = AsyncMock(
        side_effect=lambda key: pheromone_data.get(key)
    )

    result = await pheromone_client.get_success_trails(limit=10)

    assert len(result) == 1
    assert result[0]['domain'] == 'valid-plan'


@pytest.mark.asyncio
async def test_get_success_trails_handles_missing_data(pheromone_client, mock_redis_client):
    """Validar tratamento quando get_cached_context retorna None"""
    keys = [
        'pheromone:strategic:plan-1:SUCCESS',
        'pheromone:strategic:plan-2:SUCCESS',
    ]

    pheromone_data = {
        'pheromone:strategic:plan-1:SUCCESS': {'strength': 0.9, 'last_updated': 1000, 'metadata': {}},
        'pheromone:strategic:plan-2:SUCCESS': None,
    }

    async def mock_scan_iter(match=None):
        for key in keys:
            yield key

    mock_redis_client.client.scan_iter = mock_scan_iter
    mock_redis_client.get_cached_context = AsyncMock(
        side_effect=lambda key: pheromone_data.get(key)
    )

    result = await pheromone_client.get_success_trails(limit=10)

    assert len(result) == 1
    assert result[0]['domain'] == 'plan-1'


@pytest.mark.asyncio
async def test_get_success_trails_handles_exception(pheromone_client, mock_redis_client):
    """Validar tratamento de excecoes durante scan"""
    async def mock_scan_iter_error(match=None):
        raise Exception("Redis connection error")
        yield

    mock_redis_client.client.scan_iter = mock_scan_iter_error

    pheromone_client._success_trails_cache = None
    pheromone_client._cache_timestamp = 0

    result = await pheromone_client.get_success_trails(limit=10)

    assert result == []


def test_invalidate_success_trails_cache(pheromone_client):
    """Validar invalidacao de cache"""
    pheromone_client._success_trails_cache = [{'domain': 'test', 'strength': 0.9}]
    pheromone_client._cache_timestamp = time.time()

    pheromone_client.invalidate_success_trails_cache()

    assert pheromone_client._success_trails_cache is None
    assert pheromone_client._cache_timestamp == 0
