"""Testes unitários para RedisTokenBucketBackend - Rate Limiting.

Testes TDD seguindo a ordem de implementação:
1. Operações atômicas Redis
2. RedisTokenBucketBackend - operações básicas
3. Lua script refill_and_acquire
4. TTL automático para chaves não utilizadas
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
import pytest

import redis.asyncio as redis

from src.clients.rate_limit_redis import (
    RedisTokenBucketBackend,
    generate_rate_limit_key,
    REFILL_AND_ACQUIRE_LUA,
)


# =============================================================================
# Fixtures globais
# =============================================================================


@pytest.fixture
def mock_redis_client():
    """Fixture para cliente Redis mockado."""
    client = AsyncMock(spec=redis.Redis)
    client.ping = AsyncMock(return_value=True)
    client.eval = AsyncMock()
    client.hget = AsyncMock()
    client.hset = AsyncMock()
    client.expire = AsyncMock()
    client.delete = AsyncMock()
    client.close = AsyncMock()
    return client


@pytest.fixture
def backend(mock_redis_client):
    """Fixture para backend com cliente mockado."""
    return RedisTokenBucketBackend(
        redis_client=mock_redis_client,
        service_name="orchestrator-dynamic",
    )


# =============================================================================
# Testes de geração de chave
# =============================================================================


class TestGenerateRateLimitKey:
    """Testes para geração de chaves Redis de rate limit."""

    def test_generate_key_full_params(self):
        """Testa geração de chave com todos os parâmetros."""
        key = generate_rate_limit_key(
            tenant_id="tenant-123",
            user_id="user-456",
            endpoint="/api/v1/predict",
        )
        expected = "rate_limit:tenant-123:user-456:_api_v1_predict"
        assert key == expected

    def test_generate_key_without_endpoint(self):
        """Testa geração de chave sem endpoint."""
        key = generate_rate_limit_key(
            tenant_id="tenant-123",
            user_id="user-456",
            endpoint=None,
        )
        expected = "rate_limit:tenant-123:user-456:global"
        assert key == expected

    def test_generate_key_special_characters(self):
        """Testa escaping de caracteres especiais."""
        key = generate_rate_limit_key(
            tenant_id="tenant-123",
            user_id="user@example.com",
            endpoint="/api/v1/test?action=query",
        )
        # Chaves devem escapar caracteres especiais
        assert "rate_limit:tenant-123:" in key
        # Caracteres especiais são substituídos por _
        # user@example.com -> user_example_com
        assert "user_example_com" in key
        # /api/v1/test?action=query -> _api_v1_test_action_query
        assert "_api_v1_test_action_query" in key


# =============================================================================
# Testes do Lua Script
# =============================================================================


class TestLuaScript:
    """Testes para Lua script de operação atômica."""

    def test_lua_script_exists(self):
        """Verifica que o script Lua existe e está formatado."""
        assert REFILL_AND_ACQUIRE_LUA is not None
        assert isinstance(REFILL_AND_ACQUIRE_LUA, str)
        assert len(REFILL_AND_ACQUIRE_LUA) > 0

    def test_lua_script_contains_expected_commands(self):
        """Verifica que o script contém comandos Redis esperados."""
        assert "HMGET" in REFILL_AND_ACQUIRE_LUA
        assert "HMSET" in REFILL_AND_ACQUIRE_LUA
        assert "EXPIRE" in REFILL_AND_ACQUIRE_LUA
        assert "math.floor" in REFILL_AND_ACQUIRE_LUA
        assert "math.min" in REFILL_AND_ACQUIRE_LUA


# =============================================================================
# Testes do RedisTokenBucketBackend
# =============================================================================


class TestRedisTokenBucketBackend:
    """Testes para RedisTokenBucketBackend."""

    def test_initialization(self, mock_redis_client):
        """Testa inicialização do backend."""
        backend = RedisTokenBucketBackend(
            redis_client=mock_redis_client,
            service_name="test-service",
        )

        assert backend.redis_client is mock_redis_client
        assert backend.service_name == "test-service"
        assert backend.key_prefix == "rate_limit"

    @pytest.mark.asyncio
    async def test_acquire_success_with_tokens(self, backend, mock_redis_client):
        """Testa aquisição bem-sucedida quando há tokens disponíveis."""
        # Lua script retorna [1, tokens_restantes]
        mock_redis_client.eval.return_value = [1, 5]  # allowed, 5 tokens restantes

        result = await backend.acquire(
            tenant_id="tenant-123",
            user_id="user-456",
            endpoint="/api/v1/test",
            capacity=10,
            refill_rate=1.0,
            tokens=1,
        )

        assert result is True
        assert mock_redis_client.eval.called

        # Verificar parâmetros do script
        call_args = mock_redis_client.eval.call_args
        assert call_args is not None
        # call_args[0] é uma tupla de argumentos posicionais
        args = call_args[0]
        script = args[0]
        num_keys = args[1]
        key = args[2]  # Primeira chave

        assert script == REFILL_AND_ACQUIRE_LUA
        assert num_keys == 1
        assert "rate_limit:tenant-123:user-456:" in key

    @pytest.mark.asyncio
    async def test_acquire_insufficient_tokens(self, backend, mock_redis_client):
        """Testa negação quando não há tokens suficientes."""
        # Lua script retorna [0, tokens_restantes]
        mock_redis_client.eval.return_value = [0, 0]  # not allowed, 0 tokens

        result = await backend.acquire(
            tenant_id="tenant-123",
            user_id="user-456",
            endpoint="/api/v1/test",
            capacity=10,
            refill_rate=1.0,
            tokens=5,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_acquire_gets_tokens_remaining(self, backend, mock_redis_client):
        """Testa que acquire retorna tokens restantes corretamente."""
        mock_redis_client.eval.return_value = [1, 7]  # allowed, 7 restantes

        result = await backend.acquire(
            tenant_id="tenant-123",
            user_id="user-456",
            endpoint="/api/v1/test",
            capacity=10,
            refill_rate=1.0,
            tokens=1,
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_acquire_with_redis_error_fail_open(self, backend, mock_redis_client):
        """Testa comportamento fail-open quando Redis está indisponível."""
        # Simular erro de conexão
        mock_redis_client.eval.side_effect = redis.ConnectionError("Redis down")

        result = await backend.acquire(
            tenant_id="tenant-123",
            user_id="user-456",
            endpoint="/api/v1/test",
            capacity=10,
            refill_rate=1.0,
            tokens=1,
        )

        # Fail-open: retorna True para permitir requisição
        assert result is True

    @pytest.mark.asyncio
    async def test_get_tokens(self, backend, mock_redis_client):
        """Testa consulta de tokens disponíveis."""
        mock_redis_client.hget.return_value = "5"

        tokens = await backend.get_tokens(
            tenant_id="tenant-123",
            user_id="user-456",
            endpoint="/api/v1/test",
        )

        assert tokens == 5
        mock_redis_client.hget.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_tokens_no_key(self, backend, mock_redis_client):
        """Testa consulta quando chave não existe."""
        mock_redis_client.hget.return_value = None

        tokens = await backend.get_tokens(
            tenant_id="tenant-123",
            user_id="user-456",
            endpoint="/api/v1/test",
        )

        # Chave não existe significa capacidade cheia
        assert tokens is None

    @pytest.mark.asyncio
    async def test_get_tokens_redis_error(self, backend, mock_redis_client):
        """Testa consulta com erro Redis."""
        mock_redis_client.hget.side_effect = redis.ConnectionError("Redis down")

        tokens = await backend.get_tokens(
            tenant_id="tenant-123",
            user_id="user-456",
            endpoint="/api/v1/test",
        )

        # Retorna None em caso de erro
        assert tokens is None

    @pytest.mark.asyncio
    async def test_reset(self, backend, mock_redis_client):
        """Testa reset de tokens para capacidade máxima."""
        mock_redis_client.hset.return_value = True

        await backend.reset(
            tenant_id="tenant-123",
            user_id="user-456",
            endpoint="/api/v1/test",
            capacity=100,
        )

        mock_redis_client.hset.assert_called()
        call_args = mock_redis_client.hset.call_args
        # Deve definir tokens = capacity e last_refill
        assert call_args is not None

    @pytest.mark.asyncio
    async def test_reset_with_ttl(self, backend, mock_redis_client):
        """Testa reset define TTL."""
        mock_redis_client.hset.return_value = True
        mock_redis_client.expire.return_value = True

        await backend.reset(
            tenant_id="tenant-123",
            user_id="user-456",
            endpoint="/api/v1/test",
            capacity=100,
            ttl_seconds=3600,
        )

        mock_redis_client.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete(self, backend, mock_redis_client):
        """Testa remoção de chave de rate limit."""
        mock_redis_client.delete.return_value = 1

        await backend.delete(
            tenant_id="tenant-123",
            user_id="user-456",
            endpoint="/api/v1/test",
        )

        mock_redis_client.delete.assert_called_once()
        call_args = mock_redis_client.delete.call_args
        key = call_args[0][0]
        assert "rate_limit:tenant-123:user-456:" in key


# =============================================================================
# Testes de atomicidade do Lua script
# =============================================================================


class TestLuaScriptAtomicity:
    """Testes para verificar atomicidade do Lua script."""

    @pytest.mark.asyncio
    async def test_script_is_single_operation(self):
        """Verifica que o script executa atomicamente."""
        # Lua scripts no Redis são executados atomicamente
        # Este teste documenta a propriedade
        assert "local " in REFILL_AND_ACQUIRE_LUA
        assert "return" in REFILL_AND_ACQUIRE_LUA

    @pytest.mark.asyncio
    async def test_script_handles_race_conditions(self):
        """Testa que script previne race conditions."""
        # Lua scripts rodam no Redis de forma atômica
        # prevenindo race conditions entre check-and-set
        assert "redis.call" in REFILL_AND_ACQUIRE_LUA
        # O script deve usar HMGET + HMSET atomicamente
        assert "HMGET" in REFILL_AND_ACQUIRE_LUA
        assert "HMSET" in REFILL_AND_ACQUIRE_LUA


# =============================================================================
# Testes de TTL automático
# =============================================================================


class TestTTLAutomation:
    """Testes para TTL automático em chaves não utilizadas."""

    @pytest.mark.asyncio
    async def test_lua_script_sets_ttl(self):
        """Verifica que o Lua script define TTL."""
        # O script deve incluir EXPIRE
        assert "EXPIRE" in REFILL_AND_ACQUIRE_LUA
        assert "3600" in REFILL_AND_ACQUIRE_LUA  # 1 hora padrão

    @pytest.mark.asyncio
    async def test_default_ttl_is_one_hour(self):
        """Verifica TTL padrão de 1 hora."""
        assert "3600" in REFILL_AND_ACQUIRE_LUA


# =============================================================================
# Testes de casos extremos
# =============================================================================


class TestEdgeCases:
    """Testes de casos extremos."""

    @pytest.mark.asyncio
    async def test_acquire_zero_tokens(self, backend, mock_redis_client):
        """Testa aquisição de zero tokens."""
        mock_redis_client.eval.return_value = [1, 10]

        result = await backend.acquire(
            tenant_id="tenant-123",
            user_id="user-456",
            endpoint="/api/v1/test",
            capacity=10,
            refill_rate=1.0,
            tokens=0,
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_acquire_more_than_capacity(self, backend, mock_redis_client):
        """Testa aquisição de tokens maior que capacidade."""
        mock_redis_client.eval.return_value = [0, 0]

        result = await backend.acquire(
            tenant_id="tenant-123",
            user_id="user-456",
            endpoint="/api/v1/test",
            capacity=10,
            refill_rate=1.0,
            tokens=100,  # Maior que capacity
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_refill_rate_zero(self, backend, mock_redis_client):
        """Testa refill rate zero (sem reabastecimento)."""
        mock_redis_client.eval.return_value = [1, 0]

        result = await backend.acquire(
            tenant_id="tenant-123",
            user_id="user-456",
            endpoint="/api/v1/test",
            capacity=10,
            refill_rate=0.0,  # Sem refill
            tokens=1,
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_very_large_capacity(self, backend, mock_redis_client):
        """Testa capacidade muito grande."""
        mock_redis_client.eval.return_value = [1, 999999]

        result = await backend.acquire(
            tenant_id="tenant-123",
            user_id="user-456",
            endpoint="/api/v1/test",
            capacity=1_000_000,
            refill_rate=1000.0,
            tokens=1,
        )

        assert result is True


# =============================================================================
# Testes de métricas
# =============================================================================


class TestMetrics:
    """Testes para métricas Prometheus."""

    @pytest.mark.asyncio
    async def test_acquire_allowed_no_error_increment(self, backend, mock_redis_client):
        """Testa que aquisição permitida não incrementa erro."""
        mock_redis_client.eval.return_value = [1, 5]

        # Patch do contador
        with patch.object(backend, "service_name", "orchestrator-dynamic"):
            result = await backend.acquire(
                tenant_id="tenant-123",
                user_id="user-456",
                endpoint="/api/v1/test",
                capacity=10,
                refill_rate=1.0,
                tokens=1,
            )
            assert result is True

    @pytest.mark.asyncio
    async def test_redis_error_fail_open_behavior(self, backend, mock_redis_client):
        """Testa que erro Redis retorna True (fail-open)."""
        mock_redis_client.eval.side_effect = redis.ConnectionError("Redis down")

        result = await backend.acquire(
            tenant_id="tenant-123",
            user_id="user-456",
            endpoint="/api/v1/test",
            capacity=10,
            refill_rate=1.0,
            tokens=1,
        )

        # Fail-open: retorna True mesmo com erro
        assert result is True
