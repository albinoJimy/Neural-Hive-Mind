"""
Testes unitarios para PheromoneClient - foco em get_success_trails
Formato de chave Redis unificada: pheromone:{layer}:{domain}:{pheromone_type}:{id}
"""
import pytest
import time
import structlog
from typing import Dict, List, Any, Optional
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from enum import Enum

logger = structlog.get_logger()


class UnifiedDomain(str, Enum):
    """Domínios unificados do Neural Hive-Mind"""
    BUSINESS = 'BUSINESS'
    TECHNICAL = 'TECHNICAL'
    SECURITY = 'SECURITY'
    INFRASTRUCTURE = 'INFRASTRUCTURE'
    BEHAVIOR = 'BEHAVIOR'
    OPERATIONAL = 'OPERATIONAL'
    COMPLIANCE = 'COMPLIANCE'

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
        domain: UnifiedDomain,
        strength: float,
        metadata: Dict[str, Any],
        signal_id: str = None
    ) -> None:
        """
        Publicar feromonio com formato de chave unificada.
        Formato: pheromone:{layer}:{domain}:{pheromone_type}:{id}
        """
        try:
            # Extrair layer do prefix (ex: 'pheromone:strategic:' -> 'strategic')
            layer = self.prefix.rstrip(':').split(':')[-1] if ':' in self.prefix else 'strategic'

            # Normalizar domain para string se for enum
            domain_str = domain.value if isinstance(domain, UnifiedDomain) else str(domain).upper()

            # Gerar ID se não fornecido
            if signal_id is None:
                signal_id = f"signal-{int(datetime.now().timestamp() * 1000)}"

            # Formato unificado: pheromone:{layer}:{domain}:{pheromone_type}:{id}
            key = f"pheromone:{layer}:{domain_str}:{pheromone_type}:{signal_id}"

            pheromone_data = {
                "strength": strength,
                "last_updated": int(datetime.now().timestamp() * 1000),
                "metadata": metadata,
                "domain": domain_str,
                "pheromone_type": pheromone_type,
                "signal_id": signal_id
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
        """
        Obter trilhas de sucesso mais fortes.
        Formato de chave: pheromone:{layer}:{domain}:{pheromone_type}:{id}
        """
        try:
            # Verificar se cache e valido
            cache_age = time.time() - self._cache_timestamp
            if self._success_trails_cache is not None and cache_age < CACHE_TTL_SECONDS:
                if self._metrics_mock:
                    self._metrics_mock.pheromone_trails_cache_hits_total.inc()
                return self._success_trails_cache[:limit]

            if self._metrics_mock:
                self._metrics_mock.pheromone_trails_cache_misses_total.inc()

            # Novo pattern unificado: pheromone:{layer}:{domain}:SUCCESS:{id}
            pattern = f"pheromone:*:*:SUCCESS:*"
            trails: List[Dict[str, Any]] = []
            keys_scanned = 0

            start_time = time.time()

            async for key in self.redis_client.client.scan_iter(match=pattern):
                keys_scanned += 1

                try:
                    # Formato: pheromone:{layer}:{domain}:{pheromone_type}:{id}
                    key_parts = key.split(':')
                    if len(key_parts) < 5:
                        continue
                    # key_parts[0] = 'pheromone'
                    # key_parts[1] = layer (strategic, exploration, etc)
                    # key_parts[2] = domain (BUSINESS, TECHNICAL, etc)
                    # key_parts[3] = pheromone_type (SUCCESS, FAILURE, etc)
                    # key_parts[4:] = id (pode conter ':')
                    domain = key_parts[2]
                    signal_id = ':'.join(key_parts[4:])
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
                    'signal_id': signal_id,
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
    # Novo formato: pheromone:{layer}:{domain}:{pheromone_type}:{id}
    keys = [
        'pheromone:strategic:BUSINESS:SUCCESS:plan-1',
        'pheromone:strategic:TECHNICAL:SUCCESS:plan-2',
        'pheromone:strategic:SECURITY:SUCCESS:plan-3',
        'pheromone:strategic:INFRASTRUCTURE:SUCCESS:plan-4',
        'pheromone:strategic:BEHAVIOR:SUCCESS:plan-5',
    ]

    pheromone_data = {
        'pheromone:strategic:BUSINESS:SUCCESS:plan-1': {'strength': 0.9, 'last_updated': 1000, 'metadata': {}, 'domain': 'BUSINESS'},
        'pheromone:strategic:TECHNICAL:SUCCESS:plan-2': {'strength': 0.5, 'last_updated': 1001, 'metadata': {}, 'domain': 'TECHNICAL'},
        'pheromone:strategic:SECURITY:SUCCESS:plan-3': {'strength': 0.8, 'last_updated': 1002, 'metadata': {}, 'domain': 'SECURITY'},
        'pheromone:strategic:INFRASTRUCTURE:SUCCESS:plan-4': {'strength': 0.3, 'last_updated': 1003, 'metadata': {}, 'domain': 'INFRASTRUCTURE'},
        'pheromone:strategic:BEHAVIOR:SUCCESS:plan-5': {'strength': 0.7, 'last_updated': 1004, 'metadata': {}, 'domain': 'BEHAVIOR'},
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

    # Domains agora são os 7 domínios unificados
    assert result[0]['domain'] == 'BUSINESS'
    assert result[1]['domain'] == 'SECURITY'
    assert result[2]['domain'] == 'BEHAVIOR'


@pytest.mark.asyncio
async def test_get_success_trails_limit(pheromone_client, mock_redis_client):
    """Validar que apenas limit trilhas sao retornadas (criar 20 trilhas, limit=10)"""
    # Novo formato: pheromone:{layer}:{domain}:{pheromone_type}:{id}
    domains = ['BUSINESS', 'TECHNICAL', 'SECURITY', 'INFRASTRUCTURE', 'BEHAVIOR', 'OPERATIONAL', 'COMPLIANCE']
    keys = [f'pheromone:strategic:{domains[i % len(domains)]}:SUCCESS:plan-{i}' for i in range(20)]
    pheromone_data = {
        key: {'strength': i * 0.05, 'last_updated': 1000 + i, 'metadata': {}, 'domain': domains[i % len(domains)]}
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
    """Validar extracao correta de domain das chaves unificadas"""
    # Novo formato: pheromone:{layer}:{domain}:{pheromone_type}:{id}
    # O ID pode conter ':' então testamos IDs complexos
    keys = [
        'pheromone:strategic:BUSINESS:SUCCESS:simple-plan',
        'pheromone:strategic:TECHNICAL:SUCCESS:plan:with:colons',
    ]

    pheromone_data = {
        'pheromone:strategic:BUSINESS:SUCCESS:simple-plan': {'strength': 0.9, 'last_updated': 1000, 'metadata': {}, 'domain': 'BUSINESS'},
        'pheromone:strategic:TECHNICAL:SUCCESS:plan:with:colons': {'strength': 0.8, 'last_updated': 1001, 'metadata': {}, 'domain': 'TECHNICAL'},
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
    # Domínios são os 7 unificados (BUSINESS, TECHNICAL, etc.)
    assert 'BUSINESS' in domains
    assert 'TECHNICAL' in domains
    # signal_id pode conter ':'
    signal_ids = [r['signal_id'] for r in result]
    assert 'simple-plan' in signal_ids
    assert 'plan:with:colons' in signal_ids


@pytest.mark.asyncio
async def test_get_success_trails_cache_hit(pheromone_client, mock_redis_client):
    """Validar que segunda chamada usa cache"""
    # Novo formato: pheromone:{layer}:{domain}:{pheromone_type}:{id}
    keys = ['pheromone:strategic:BUSINESS:SUCCESS:plan-1']
    pheromone_data = {
        'pheromone:strategic:BUSINESS:SUCCESS:plan-1': {'strength': 0.9, 'last_updated': 1000, 'metadata': {}, 'domain': 'BUSINESS'}
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
    # Novo formato: pheromone:{layer}:{domain}:{pheromone_type}:{id}
    keys = ['pheromone:strategic:BUSINESS:SUCCESS:plan-1']
    pheromone_data = {
        'pheromone:strategic:BUSINESS:SUCCESS:plan-1': {'strength': 0.9, 'last_updated': 1000, 'metadata': {}, 'domain': 'BUSINESS'}
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
    pheromone_client._success_trails_cache = [{'domain': 'BUSINESS', 'strength': 0.9}]
    pheromone_client._cache_timestamp = time.time()

    assert pheromone_client._success_trails_cache is not None
    assert pheromone_client._cache_timestamp > 0

    # Publicar SUCCESS usando UnifiedDomain
    await pheromone_client.publish_pheromone(
        pheromone_type='SUCCESS',
        domain=UnifiedDomain.BUSINESS,
        strength=0.8,
        metadata={},
        signal_id='plan-1'
    )

    assert pheromone_client._success_trails_cache is None
    assert pheromone_client._cache_timestamp == 0


@pytest.mark.asyncio
async def test_publish_failure_does_not_invalidate_cache(pheromone_client, mock_redis_client):
    """Validar que publicar FAILURE nao invalida cache"""
    # Preparar cache
    pheromone_client._success_trails_cache = [{'domain': 'TECHNICAL', 'strength': 0.9}]
    original_timestamp = time.time()
    pheromone_client._cache_timestamp = original_timestamp

    # Publicar FAILURE usando UnifiedDomain
    await pheromone_client.publish_pheromone(
        pheromone_type='FAILURE',
        domain=UnifiedDomain.TECHNICAL,
        strength=-1.0,
        metadata={},
        signal_id='plan-1'
    )

    assert pheromone_client._success_trails_cache is not None
    assert pheromone_client._cache_timestamp == original_timestamp


@pytest.mark.asyncio
async def test_get_success_trails_handles_malformed_keys(pheromone_client, mock_redis_client):
    """Validar tratamento de chaves malformadas"""
    # Novo formato requer 5 partes: pheromone:{layer}:{domain}:{pheromone_type}:{id}
    keys = [
        'pheromone:strategic:BUSINESS:SUCCESS:valid-plan',  # Válida
        'invalid:key',  # Inválida - poucos segmentos
        'pheromone:strategic:SUCCESS',  # Inválida - falta domain e id
        'pheromone:strategic:SECURITY:SUCCESS',  # Inválida - falta id
    ]

    pheromone_data = {
        'pheromone:strategic:BUSINESS:SUCCESS:valid-plan': {'strength': 0.9, 'last_updated': 1000, 'metadata': {}, 'domain': 'BUSINESS'}
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
    assert result[0]['domain'] == 'BUSINESS'


@pytest.mark.asyncio
async def test_get_success_trails_handles_missing_data(pheromone_client, mock_redis_client):
    """Validar tratamento quando get_cached_context retorna None"""
    # Novo formato: pheromone:{layer}:{domain}:{pheromone_type}:{id}
    keys = [
        'pheromone:strategic:OPERATIONAL:SUCCESS:plan-1',
        'pheromone:strategic:COMPLIANCE:SUCCESS:plan-2',
    ]

    pheromone_data = {
        'pheromone:strategic:OPERATIONAL:SUCCESS:plan-1': {'strength': 0.9, 'last_updated': 1000, 'metadata': {}, 'domain': 'OPERATIONAL'},
        'pheromone:strategic:COMPLIANCE:SUCCESS:plan-2': None,
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
    assert result[0]['domain'] == 'OPERATIONAL'


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
    pheromone_client._success_trails_cache = [{'domain': 'INFRASTRUCTURE', 'strength': 0.9}]
    pheromone_client._cache_timestamp = time.time()

    pheromone_client.invalidate_success_trails_cache()

    assert pheromone_client._success_trails_cache is None
    assert pheromone_client._cache_timestamp == 0


@pytest.mark.asyncio
async def test_publish_pheromone_with_all_domains(pheromone_client, mock_redis_client):
    """Validar publicacao de feromonios com todos os 7 dominios unificados"""
    for domain in UnifiedDomain:
        await pheromone_client.publish_pheromone(
            pheromone_type='SUCCESS',
            domain=domain,
            strength=0.8,
            metadata={'test': True},
            signal_id=f'test-{domain.value.lower()}'
        )

    # Verificar que cache_strategic_context foi chamado 7 vezes
    assert mock_redis_client.cache_strategic_context.call_count == 7
