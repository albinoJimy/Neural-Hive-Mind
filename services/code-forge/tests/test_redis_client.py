"""Testes unitários para RedisClient"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.clients.redis_client import RedisClient


@pytest.fixture
def mock_redis():
    """Mock do Redis client"""
    client = AsyncMock()
    client.ping = AsyncMock()
    client.get = AsyncMock()
    client.set = AsyncMock()
    client.setex = AsyncMock()
    client.delete = AsyncMock()
    client.hset = AsyncMock()
    client.hgetall = AsyncMock()
    client.expire = AsyncMock()
    client.close = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_start_standalone_success(mock_redis):
    """Testar inicialização em modo standalone"""
    with patch('src.clients.redis_client.Redis', return_value=mock_redis):
        client = RedisClient('redis://localhost:6379')
        await client.start()

        assert client.client is not None
        mock_redis.ping.assert_awaited_once()


@pytest.mark.asyncio
async def test_stop_closes_connection(mock_redis):
    """Testar fechamento da conexão"""
    with patch('src.clients.redis_client.Redis', return_value=mock_redis):
        client = RedisClient('redis://localhost:6379')
        await client.start()
        await client.stop()

        mock_redis.close.assert_awaited_once()
        assert client.client is None


@pytest.mark.asyncio
async def test_cache_template_success(mock_redis):
    """Testar cacheamento de template"""
    with patch('src.clients.redis_client.Redis', return_value=mock_redis):
        client = RedisClient('redis://localhost:6379')
        await client.start()

        template = {'name': 'test-template', 'content': 'print("hello")'}
        await client.cache_template('tpl-1', template, ttl=300)

        mock_redis.setex.assert_awaited_once()
        call_args = mock_redis.setex.call_args
        assert call_args[0][0] == 'template:tpl-1'
        assert call_args[0][1] == 300


@pytest.mark.asyncio
async def test_get_cached_template_hit(mock_redis):
    """Testar recuperação de template em cache"""
    template = {'name': 'test-template', 'content': 'print("hello")'}
    mock_redis.get.return_value = json.dumps(template)

    with patch('src.clients.redis_client.Redis', return_value=mock_redis):
        client = RedisClient('redis://localhost:6379')
        await client.start()

        result = await client.get_cached_template('tpl-1')

        assert result == template
        mock_redis.get.assert_awaited_once_with('template:tpl-1')


@pytest.mark.asyncio
async def test_get_cached_template_miss(mock_redis):
    """Testar cache miss de template"""
    mock_redis.get.return_value = None

    with patch('src.clients.redis_client.Redis', return_value=mock_redis):
        client = RedisClient('redis://localhost:6379')
        await client.start()

        result = await client.get_cached_template('nonexistent')

        assert result is None


@pytest.mark.asyncio
async def test_invalidate_template(mock_redis):
    """Testar invalidação de template"""
    mock_redis.delete.return_value = 1

    with patch('src.clients.redis_client.Redis', return_value=mock_redis):
        client = RedisClient('redis://localhost:6379')
        await client.start()

        deleted = await client.invalidate_template('tpl-1')

        assert deleted is True
        mock_redis.delete.assert_awaited_once_with('template:tpl-1')


@pytest.mark.asyncio
async def test_set_pipeline_state(mock_redis):
    """Testar salvamento de estado de pipeline"""
    with patch('src.clients.redis_client.Redis', return_value=mock_redis):
        client = RedisClient('redis://localhost:6379')
        await client.start()

        state = {'stage': 'build', 'progress': 50}
        await client.set_pipeline_state('pipe-1', state)

        mock_redis.hset.assert_awaited_once()
        mock_redis.expire.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_pipeline_state_found(mock_redis):
    """Testar recuperação de estado de pipeline existente"""
    mock_redis.hgetall.return_value = {
        'stage': '"build"',
        'progress': '50'
    }

    with patch('src.clients.redis_client.Redis', return_value=mock_redis):
        client = RedisClient('redis://localhost:6379')
        await client.start()

        state = await client.get_pipeline_state('pipe-1')

        assert state is not None
        assert state['stage'] == 'build'


@pytest.mark.asyncio
async def test_get_pipeline_state_not_found(mock_redis):
    """Testar busca de estado de pipeline não existente"""
    mock_redis.hgetall.return_value = {}

    with patch('src.clients.redis_client.Redis', return_value=mock_redis):
        client = RedisClient('redis://localhost:6379')
        await client.start()

        state = await client.get_pipeline_state('nonexistent')

        assert state is None


@pytest.mark.asyncio
async def test_acquire_lock_success(mock_redis):
    """Testar aquisição de lock bem-sucedida"""
    mock_redis.set.return_value = True

    with patch('src.clients.redis_client.Redis', return_value=mock_redis):
        client = RedisClient('redis://localhost:6379')
        await client.start()

        acquired = await client.acquire_lock('resource-1', timeout=30)

        assert acquired is True
        mock_redis.set.assert_awaited_once()
        call_args = mock_redis.set.call_args
        assert call_args[0][0] == 'lock:resource-1'
        assert call_args[1]['nx'] is True
        assert call_args[1]['ex'] == 30


@pytest.mark.asyncio
async def test_acquire_lock_failure(mock_redis):
    """Testar falha na aquisição de lock (já existe)"""
    mock_redis.set.return_value = None  # SETNX retorna None se já existe

    with patch('src.clients.redis_client.Redis', return_value=mock_redis):
        client = RedisClient('redis://localhost:6379')
        await client.start()

        acquired = await client.acquire_lock('resource-1')

        assert acquired is False


@pytest.mark.asyncio
async def test_release_lock_success(mock_redis):
    """Testar liberação de lock"""
    mock_redis.delete.return_value = 1

    with patch('src.clients.redis_client.Redis', return_value=mock_redis):
        client = RedisClient('redis://localhost:6379')
        await client.start()

        released = await client.release_lock('resource-1')

        assert released is True
        mock_redis.delete.assert_awaited_once_with('lock:resource-1')


@pytest.mark.asyncio
async def test_release_lock_with_owner_check(mock_redis):
    """Testar liberação de lock verificando owner"""
    mock_redis.get.return_value = 'owner-123'
    mock_redis.delete.return_value = 1

    with patch('src.clients.redis_client.Redis', return_value=mock_redis):
        client = RedisClient('redis://localhost:6379')
        await client.start()

        released = await client.release_lock('resource-1', owner='owner-123')

        assert released is True


@pytest.mark.asyncio
async def test_release_lock_wrong_owner(mock_redis):
    """Testar falha ao liberar lock de outro owner"""
    mock_redis.get.return_value = 'owner-456'  # Outro owner

    with patch('src.clients.redis_client.Redis', return_value=mock_redis):
        client = RedisClient('redis://localhost:6379')
        await client.start()

        released = await client.release_lock('resource-1', owner='owner-123')

        assert released is False
        mock_redis.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_extend_lock_success(mock_redis):
    """Testar extensão de lock"""
    mock_redis.expire.return_value = True

    with patch('src.clients.redis_client.Redis', return_value=mock_redis):
        client = RedisClient('redis://localhost:6379')
        await client.start()

        extended = await client.extend_lock('resource-1', timeout=60)

        assert extended is True
        mock_redis.expire.assert_awaited_once()


@pytest.mark.asyncio
async def test_health_check_success(mock_redis):
    """Testar health check bem-sucedido"""
    with patch('src.clients.redis_client.Redis', return_value=mock_redis):
        client = RedisClient('redis://localhost:6379')
        await client.start()

        healthy = await client.health_check()

        assert healthy is True


@pytest.mark.asyncio
async def test_health_check_failure(mock_redis):
    """Testar health check com falha"""
    mock_redis.ping.side_effect = [None, Exception('Connection lost')]

    with patch('src.clients.redis_client.Redis', return_value=mock_redis):
        client = RedisClient('redis://localhost:6379')
        await client.start()

        healthy = await client.health_check()

        assert healthy is False


@pytest.mark.asyncio
async def test_operations_raise_when_not_started():
    """Testar que operações falham quando cliente não iniciado"""
    client = RedisClient('redis://localhost:6379')

    with pytest.raises(RuntimeError, match='Redis client not started'):
        await client.cache_template('tpl-1', {})

    with pytest.raises(RuntimeError, match='Redis client not started'):
        await client.get_cached_template('tpl-1')

    with pytest.raises(RuntimeError, match='Redis client not started'):
        await client.set_pipeline_state('pipe-1', {})


@pytest.mark.asyncio
async def test_set_value_with_ttl(mock_redis):
    """Testar armazenamento de valor com TTL"""
    with patch('src.clients.redis_client.Redis', return_value=mock_redis):
        client = RedisClient('redis://localhost:6379')
        await client.start()

        await client.set_value('key-1', 'value-1', ttl=60)

        mock_redis.setex.assert_awaited_once_with('key-1', 60, 'value-1')


@pytest.mark.asyncio
async def test_set_value_without_ttl(mock_redis):
    """Testar armazenamento de valor sem TTL"""
    with patch('src.clients.redis_client.Redis', return_value=mock_redis):
        client = RedisClient('redis://localhost:6379')
        await client.start()

        await client.set_value('key-1', 'value-1')

        mock_redis.set.assert_awaited_once_with('key-1', 'value-1')


@pytest.mark.asyncio
async def test_get_value(mock_redis):
    """Testar recuperação de valor"""
    mock_redis.get.return_value = 'value-1'

    with patch('src.clients.redis_client.Redis', return_value=mock_redis):
        client = RedisClient('redis://localhost:6379')
        await client.start()

        value = await client.get_value('key-1')

        assert value == 'value-1'
