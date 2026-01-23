"""
Testes de integracao para PheromoneClient com Redis.

Requer Redis real ou testcontainers.
Marcados com pytest.mark.integration para execucao separada.

Atualizado para usar formato unificado de chaves via DomainMapper:
pheromone:{layer}:{domain}:{type}:{id?}
"""
import pytest
import os
import json
import asyncio
from unittest.mock import MagicMock

from neural_hive_domain import UnifiedDomain


# Verificar se Redis esta disponivel
REDIS_AVAILABLE = os.getenv('REDIS_TEST_HOST') or os.getenv('INTEGRATION_TESTS', 'false').lower() == 'true'


@pytest.fixture
async def redis_client():
    """Cria cliente Redis real para testes de integracao"""
    from redis.asyncio import Redis

    host = os.getenv('REDIS_TEST_HOST', 'localhost')
    port = int(os.getenv('REDIS_TEST_PORT', '6379'))
    password = os.getenv('REDIS_TEST_PASSWORD', None)

    client = Redis(
        host=host,
        port=port,
        password=password,
        decode_responses=True
    )

    try:
        await client.ping()
    except Exception as e:
        pytest.skip(f"Redis nao disponivel: {e}")

    yield client

    # Cleanup: remover chaves de teste (formato unificado)
    test_keys = await client.keys('pheromone:strategic:*:*')
    if test_keys:
        await client.delete(*test_keys)

    await client.close()


@pytest.fixture
def mock_redis_client_wrapper(redis_client):
    """Wrapper para RedisClient que usa Redis real"""
    class RealRedisClientWrapper:
        def __init__(self, client):
            self.client = client

        async def cache_strategic_context(self, key: str, data: dict, ttl_seconds: int):
            await self.client.setex(key, ttl_seconds, json.dumps(data))

        async def get_cached_context(self, key: str):
            data = await self.client.get(key)
            if data:
                return json.loads(data)
            return None

    return RealRedisClientWrapper(redis_client)


@pytest.fixture
def mock_settings():
    """Mock de configuracoes - REDIS_PHEROMONE_PREFIX deprecated, chaves via DomainMapper"""
    settings = MagicMock()
    # DEPRECATED: Chaves agora são geradas via DomainMapper.to_pheromone_key()
    settings.REDIS_PHEROMONE_PREFIX = 'pheromone:strategic:'
    return settings


@pytest.fixture
def pheromone_client(mock_redis_client_wrapper, mock_settings):
    """Instancia do PheromoneClient com Redis real"""
    from src.clients.pheromone_client import PheromoneClient
    return PheromoneClient(
        redis_client=mock_redis_client_wrapper,
        settings=mock_settings
    )


async def populate_redis_with_pheromones(redis_client, count: int, prefix: str = 'test-plan'):
    """Popula Redis com feromonios de teste usando formato unificado.

    Formato: pheromone:strategic:{domain}:SUCCESS
    Usa domínios válidos do UnifiedDomain.
    """
    # Usar domínios válidos do UnifiedDomain para testes
    valid_domains = [d.value for d in UnifiedDomain]

    for i in range(count):
        domain = valid_domains[i % len(valid_domains)]
        # Adicionar sufixo único para permitir múltiplas chaves por domínio
        # Nota: No formato real, não haveria sufixo, mas para testes precisamos de chaves únicas
        key = f'pheromone:strategic:{domain}:SUCCESS'
        if i >= len(valid_domains):
            # Para testes com muitos itens, usar chave com ID
            key = f'pheromone:strategic:{domain}:SUCCESS:{prefix}-{i}'
        data = {
            'strength': (i + 1) / count,  # 0.01 a 1.0
            'last_updated': 1000000 + i,
            'metadata': {'decision_id': f'dec-{i}', 'test': True, 'domain': domain}
        }
        await redis_client.setex(key, 3600, json.dumps(data))


async def populate_redis_with_mixed_pheromones(redis_client, count: int):
    """Popula Redis com mix de SUCCESS, FAILURE, WARNING usando formato unificado."""
    valid_domains = [d.value for d in UnifiedDomain]
    pheromone_types = ['SUCCESS', 'FAILURE', 'WARNING']

    for i in range(count):
        ptype = pheromone_types[i % 3]
        domain = valid_domains[i % len(valid_domains)]
        key = f'pheromone:strategic:{domain}:{ptype}'
        data = {
            'strength': (i + 1) / count if ptype == 'SUCCESS' else -((i + 1) / count),
            'last_updated': 1000000 + i,
            'metadata': {'decision_id': f'dec-{i}', 'type': ptype, 'domain': domain}
        }
        await redis_client.setex(key, 3600, json.dumps(data))


@pytest.mark.integration
@pytest.mark.skipif(not REDIS_AVAILABLE, reason="Redis nao disponivel")
@pytest.mark.asyncio
async def test_get_success_trails_real_redis(pheromone_client, redis_client):
    """
    Teste com Redis real.
    Popula Redis com 100 feromonios SUCCESS e valida retorno ordenado.
    """
    from unittest.mock import patch, MagicMock

    # Popular Redis com 100 feromonios SUCCESS
    await populate_redis_with_pheromones(redis_client, 100, prefix='test-real')

    with patch('src.clients.pheromone_client.QueenAgentMetrics') as mock_metrics:
        mock_metrics.pheromone_trails_cache_misses_total = MagicMock()
        mock_metrics.pheromone_trails_cache_hits_total = MagicMock()
        mock_metrics.pheromone_trails_scan_duration_seconds = MagicMock()
        mock_metrics.pheromone_trails_keys_scanned_total = MagicMock()

        # Buscar trilhas
        result = await pheromone_client.get_success_trails(limit=10)

    # Validacoes
    assert len(result) == 10
    # Verificar ordenacao decrescente por strength
    for i in range(len(result) - 1):
        assert result[i]['strength'] >= result[i + 1]['strength'], \
            f"Ordenacao incorreta: {result[i]['strength']} < {result[i + 1]['strength']}"

    # Verificar que os 10 mais fortes foram retornados
    assert result[0]['strength'] == 1.0  # O mais forte tem strength 1.0


@pytest.mark.integration
@pytest.mark.skipif(not REDIS_AVAILABLE, reason="Redis nao disponivel")
@pytest.mark.asyncio
async def test_scan_pattern_matching(pheromone_client, redis_client):
    """
    Valida que apenas SUCCESS sao retornados quando ha mix de tipos.
    """
    from unittest.mock import patch, MagicMock

    # Popular Redis com mix de SUCCESS, FAILURE, WARNING
    await populate_redis_with_mixed_pheromones(redis_client, 30)

    with patch('src.clients.pheromone_client.QueenAgentMetrics') as mock_metrics:
        mock_metrics.pheromone_trails_cache_misses_total = MagicMock()
        mock_metrics.pheromone_trails_cache_hits_total = MagicMock()
        mock_metrics.pheromone_trails_scan_duration_seconds = MagicMock()
        mock_metrics.pheromone_trails_keys_scanned_total = MagicMock()

        result = await pheromone_client.get_success_trails(limit=20)

    # Validacoes
    # De 30 feromonios, apenas 10 sao SUCCESS (indices 0, 3, 6, 9, 12, 15, 18, 21, 24, 27)
    assert len(result) == 10

    # Verificar que todos sao SUCCESS (tem strength positivo)
    for trail in result:
        assert trail['strength'] > 0, f"Trail nao-SUCCESS encontrada: {trail}"
        assert 'test-mixed' in trail['domain']


@pytest.mark.integration
@pytest.mark.skipif(not REDIS_AVAILABLE, reason="Redis nao disponivel")
@pytest.mark.asyncio
async def test_cache_invalidation_flow(pheromone_client, redis_client):
    """
    Testa fluxo de invalidacao de cache:
    1. Busca trilhas (popula cache)
    2. Publica novo SUCCESS
    3. Valida que cache foi invalidado
    4. Busca trilhas novamente (deve buscar do Redis)
    """
    from unittest.mock import patch, MagicMock

    # Popular Redis com 10 feromonios
    await populate_redis_with_pheromones(redis_client, 10, prefix='test-cache')

    with patch('src.clients.pheromone_client.QueenAgentMetrics') as mock_metrics:
        mock_metrics.pheromone_trails_cache_misses_total = MagicMock()
        mock_metrics.pheromone_trails_cache_hits_total = MagicMock()
        mock_metrics.pheromone_trails_scan_duration_seconds = MagicMock()
        mock_metrics.pheromone_trails_keys_scanned_total = MagicMock()

        # 1. Buscar trilhas (popula cache)
        result1 = await pheromone_client.get_success_trails(limit=5)
        assert len(result1) == 5

        # Verificar que cache esta populado
        assert pheromone_client._success_trails_cache is not None
        original_cache_timestamp = pheromone_client._cache_timestamp

        # 2. Publicar novo SUCCESS com domínio válido
        await pheromone_client.publish_pheromone(
            pheromone_type='SUCCESS',
            domain='business',  # Usar domínio válido do UnifiedDomain
            strength=0.99,
            metadata={'test': 'invalidation'}
        )

        # 3. Validar que cache foi invalidado
        assert pheromone_client._success_trails_cache is None
        assert pheromone_client._cache_timestamp == 0

        # 4. Buscar trilhas novamente
        result2 = await pheromone_client.get_success_trails(limit=10)

        # Novo resultado deve incluir o feromonio publicado
        assert len(result2) > 0
        domains = [t['domain'] for t in result2]
        assert 'BUSINESS' in domains  # UnifiedDomain.BUSINESS.value

        # Cache deve estar populado novamente
        assert pheromone_client._success_trails_cache is not None
        assert pheromone_client._cache_timestamp > original_cache_timestamp


@pytest.mark.integration
@pytest.mark.skipif(not REDIS_AVAILABLE, reason="Redis nao disponivel")
@pytest.mark.asyncio
async def test_publish_and_retrieve_flow(pheromone_client, redis_client):
    """
    Testa fluxo completo de publicacao e recuperacao usando domínios unificados.
    """
    from unittest.mock import patch, MagicMock

    # Domínios válidos para publicação
    valid_domains = ['business', 'technical', 'security', 'infrastructure', 'behavior']

    with patch('src.clients.pheromone_client.QueenAgentMetrics') as mock_metrics:
        mock_metrics.pheromone_trails_cache_misses_total = MagicMock()
        mock_metrics.pheromone_trails_cache_hits_total = MagicMock()
        mock_metrics.pheromone_trails_scan_duration_seconds = MagicMock()
        mock_metrics.pheromone_trails_keys_scanned_total = MagicMock()

        # Publicar varios feromonios SUCCESS com domínios válidos
        for i, domain in enumerate(valid_domains):
            await pheromone_client.publish_pheromone(
                pheromone_type='SUCCESS',
                domain=domain,
                strength=0.5 + (i * 0.1),  # 0.5, 0.6, 0.7, 0.8, 0.9
                metadata={'index': i}
            )

        # Buscar trilhas
        result = await pheromone_client.get_success_trails(limit=3)

    # Validacoes
    assert len(result) == 3

    # Verificar ordenacao (mais fortes primeiro)
    assert result[0]['strength'] == 0.9  # behavior
    assert result[1]['strength'] == 0.8  # infrastructure
    assert result[2]['strength'] == 0.7  # security


@pytest.mark.integration
@pytest.mark.skipif(not REDIS_AVAILABLE, reason="Redis nao disponivel")
@pytest.mark.asyncio
async def test_large_scale_scan(pheromone_client, redis_client):
    """
    Teste de escala com 1000 feromonios no Redis real.
    """
    from unittest.mock import patch, MagicMock
    import time

    # Popular Redis com 1000 feromonios
    await populate_redis_with_pheromones(redis_client, 1000, prefix='test-scale')

    with patch('src.clients.pheromone_client.QueenAgentMetrics') as mock_metrics:
        mock_metrics.pheromone_trails_cache_misses_total = MagicMock()
        mock_metrics.pheromone_trails_cache_hits_total = MagicMock()
        mock_metrics.pheromone_trails_scan_duration_seconds = MagicMock()
        mock_metrics.pheromone_trails_keys_scanned_total = MagicMock()

        # Medir latencia
        start = time.perf_counter()
        result = await pheromone_client.get_success_trails(limit=50)
        elapsed_ms = (time.perf_counter() - start) * 1000

    # Validacoes
    assert len(result) == 50
    print(f"\nLarge scale scan: {elapsed_ms:.2f}ms para 1000 chaves")

    # Verificar que os 50 mais fortes foram retornados
    assert result[0]['strength'] == 1.0
    assert result[49]['strength'] == 0.951  # (1000-49)/1000
