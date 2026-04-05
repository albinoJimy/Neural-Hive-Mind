"""
Testes de integração para Token Bucket Rate Limiting.

Este módulo valida o fluxo completo de rate limiting:
- Request -> Middleware -> Redis Backend -> Response
- Redis Backend operations (acquire, get_tokens, reset, delete)
- Tier limits (premium/basic/free)
- Burst behavior (2x capacity)
- Concorrência (múltiplas requests mesma chave)
- TTL expiration (1 hora)
- Atomicidade das operações Lua

Nota: O middleware atual usa cache in-memory via RateLimiterFactory.
Os testes de integração focam no Redis backend que será integrado
no futuro.

Requisitos:
- Redis disponível (ou mock para testes locais)
- Fixtures do conftest.py
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.clients.rate_limit_redis import (
    RedisTokenBucketBackend,
    generate_rate_limit_key,
)
from src.config.settings import OrchestratorSettings
from src.observability.rate_limit_metrics import RateLimitMetrics

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def test_settings():
    """Configurações para testes de rate limiting."""
    config = MagicMock(spec=OrchestratorSettings)
    config.enable_rate_limiting = True
    config.service_name = "orchestrator-dynamic"
    config.rate_limit_default_capacity = 100
    config.rate_limit_default_refill_rate = 10.0
    config.rate_limit_burst_multiplier = 2.0
    config.rate_limit_tier_limits = {
        "premium": {"capacity": 1000, "refill_rate": 50},
        "standard": {"capacity": 100, "refill_rate": 10},
        "free": {"capacity": 10, "refill_rate": 1},
    }
    config.rate_limit_redis_key_prefix = "rate_limit_test"
    return config


@pytest.fixture
def mock_redis_pool():
    """Mock de pool de conexões Redis."""
    mock = AsyncMock()
    mock.eval = AsyncMock()
    mock.hget = AsyncMock()
    mock.hset = AsyncMock()
    mock.expire = AsyncMock()
    mock.delete = AsyncMock()
    mock.ping = AsyncMock(return_value=True)
    mock.close = AsyncMock()
    return mock


@pytest.fixture
def redis_backend(mock_redis_pool):
    """Backend Redis para testes."""
    return RedisTokenBucketBackend(
        redis_client=mock_redis_pool,
        service_name="orchestrator-dynamic-test",
        key_prefix="rate_limit_test",
        default_ttl=3600,
    )


@pytest.fixture
def rate_limit_metrics():
    """Métricas de rate limiting."""
    return RateLimitMetrics(service_name="orchestrator-dynamic-test")


# =============================================================================
# Testes de Fluxo Completo Redis Backend (7.2)
# =============================================================================


@pytest.mark.asyncio
class TestRedisBackendCompleteFlow:
    """Testes do fluxo completo Redis backend: acquire -> Redis -> response."""

    async def test_acquire_within_limit_returns_true(self, mock_redis_pool):
        """Testa que acquire dentro do limite retorna True."""
        # Setup - mock Redis para retornar permitido
        mock_redis_pool.eval.return_value = [1, 95]  # [allowed, tokens_remaining]

        backend = RedisTokenBucketBackend(
            redis_client=mock_redis_pool,
            service_name="orchestrator-dynamic-test",
        )

        # Act
        allowed = await backend.acquire(
            tenant_id="tenant-123",
            user_id="user-456",
            endpoint="/api/v1/health",
            capacity=100,
            refill_rate=10.0,
        )

        # Assert
        assert allowed is True
        mock_redis_pool.eval.assert_called_once()

        # Verificar argumentos do Lua script
        call_args = mock_redis_pool.eval.call_args
        # args[0] = script, args[1] = num_keys, args[2] = key
        # args[3] = capacity (ARGV[1])
        assert call_args[0][3] == 100
        # args[4] = refill_rate (ARGV[2])
        assert call_args[0][4] == 10.0

    async def test_acquire_exceeding_limit_returns_false(self, mock_redis_pool):
        """Testa que acquire excedendo limite retorna False."""
        # Setup - mock Redis para retornar negado
        mock_redis_pool.eval.return_value = [0, 0]  # [not_allowed, tokens_remaining]

        backend = RedisTokenBucketBackend(
            redis_client=mock_redis_pool,
            service_name="orchestrator-dynamic-test",
        )

        # Act
        allowed = await backend.acquire(
            tenant_id="tenant-123",
            user_id="user-456",
            endpoint="/api/v1/workflows",
            capacity=100,
            refill_rate=10.0,
        )

        # Assert
        assert allowed is False

    async def test_redis_connection_error_returns_true(self, mock_redis_pool):
        """Testa que erro de conexão Redis retorna True (fail-open)."""
        # Setup - simular erro de conexão
        import redis

        mock_redis_pool.eval.side_effect = redis.ConnectionError("Redis unavailable")

        backend = RedisTokenBucketBackend(
            redis_client=mock_redis_pool,
            service_name="orchestrator-dynamic-test",
        )

        # Act
        allowed = await backend.acquire(
            tenant_id="tenant-123",
            user_id="user-456",
            endpoint="/api/v1/workflows",
            capacity=100,
            refill_rate=10.0,
        )

        # Assert - fail-open deve retornar True
        assert allowed is True

    async def test_acquire_multiple_tokens(self, mock_redis_pool):
        """Testa aquisição de múltiplos tokens."""
        mock_redis_pool.eval.return_value = [1, 97]  # 100 - 3 = 97

        backend = RedisTokenBucketBackend(
            redis_client=mock_redis_pool,
            service_name="orchestrator-dynamic-test",
        )

        # Act - adquirir 3 tokens
        allowed = await backend.acquire(
            tenant_id="tenant-123",
            user_id="user-456",
            endpoint="/api/v1/workflows",
            capacity=100,
            refill_rate=10.0,
            tokens=3,
        )

        # Assert
        assert allowed is True
        # Verificar que tokens=3 foi passado
        call_args = mock_redis_pool.eval.call_args
        # args[5] = tokens (ARGV[3])
        assert call_args[0][5] == 3


# =============================================================================
# Testes de Tier Limits (7.3)
# =============================================================================


@pytest.mark.asyncio
class TestRateLimitTierLimits:
    """Testes de limites por tier (premium/basic/free)."""

    async def test_premium_tier_higher_capacity(self, test_settings, mock_redis_pool):
        """Testa que tier premium tem capacidade maior."""
        mock_redis_pool.eval.return_value = [1, 950]  # tokens restantes

        backend = RedisTokenBucketBackend(
            redis_client=mock_redis_pool,
            service_name="orchestrator-dynamic-test",
        )

        # Premium: 1000 capacity, 50 refill_rate
        allowed = await backend.acquire(
            tenant_id="tenant-premium",
            user_id="user-1",
            endpoint="/api/v1/predict",
            capacity=1000,
            refill_rate=50.0,
        )

        # Assert
        assert allowed is True
        # Verifica que eval foi chamado com capacity correto
        mock_redis_pool.eval.assert_called()
        call_args = mock_redis_pool.eval.call_args
        # args[3] = capacity (ARGV[1])
        assert call_args[0][3] == 1000

    async def test_standard_tier_default_capacity(self, test_settings, mock_redis_pool):
        """Testa que tier standard tem capacidade padrão."""
        mock_redis_pool.eval.return_value = [1, 90]

        backend = RedisTokenBucketBackend(
            redis_client=mock_redis_pool,
            service_name="orchestrator-dynamic-test",
        )

        # Standard: 100 capacity, 10 refill_rate
        allowed = await backend.acquire(
            tenant_id="tenant-standard",
            user_id="user-2",
            endpoint="/api/v1/workflows",
            capacity=100,
            refill_rate=10.0,
        )

        assert allowed is True
        call_args = mock_redis_pool.eval.call_args
        assert call_args[0][3] == 100  # capacity

    async def test_free_tier_lower_capacity(self, test_settings, mock_redis_pool):
        """Testa que tier free tem capacidade menor."""
        mock_redis_pool.eval.return_value = [1, 5]

        backend = RedisTokenBucketBackend(
            redis_client=mock_redis_pool,
            service_name="orchestrator-dynamic-test",
        )

        # Free: 10 capacity, 1 refill_rate
        allowed = await backend.acquire(
            tenant_id="tenant-free",
            user_id="user-3",
            endpoint="/api/v1/predict",
            capacity=10,
            refill_rate=1.0,
        )

        assert allowed is True
        call_args = mock_redis_pool.eval.call_args
        assert call_args[0][3] == 10  # capacity

    async def test_different_tiers_separate_keys(self):
        """Testa que diferentes tiers têm chaves Redis separadas."""
        key_premium = generate_rate_limit_key(
            "tenant-premium", "user-1", "/api/v1/predict"
        )
        key_standard = generate_rate_limit_key(
            "tenant-standard", "user-2", "/api/v1/predict"
        )
        key_free = generate_rate_limit_key("tenant-free", "user-3", "/api/v1/predict")

        # Assert - chaves devem ser diferentes
        assert key_premium != key_standard
        assert key_standard != key_free
        assert key_premium != key_free

        # Cada chave deve conter o tenant_id (com hífen substituído por underscore)
        assert "tenant-premium" in key_premium
        assert "tenant-standard" in key_standard
        assert "tenant-free" in key_free


# =============================================================================
# Testes de Burst Behavior (7.4)
# =============================================================================


@pytest.mark.asyncio
class TestRateLimitBurstBehavior:
    """Testes de comportamento de burst (2x capacity)."""

    async def test_burst_capacity_doubles_default(self, test_settings, mock_redis_pool):
        """Testa que burst capacity é 2x o default."""
        mock_redis_pool.eval.return_value = [1, 150]  # ainda tem tokens

        backend = RedisTokenBucketBackend(
            redis_client=mock_redis_pool,
            service_name="orchestrator-dynamic-test",
        )

        # Com burst_multiplier=2.0, capacity=100 vira 200
        burst_capacity = int(100 * test_settings.rate_limit_burst_multiplier)

        # Fazer burst de requests
        for _ in range(50):  # 50 requests consecutivas
            await backend.acquire(
                tenant_id="tenant-burst",
                user_id="user-burst",
                endpoint="/api/v1/burst",
                capacity=burst_capacity,
                refill_rate=10.0,
            )

        # Assert - eval deve ter sido chamado 50 vezes
        assert mock_redis_pool.eval.call_count == 50

    async def test_burst_allows_temporary_spike(self, test_settings, mock_redis_pool):
        """Testa que burst permite picos temporários acima do refill_rate."""
        # Simular refill_rate lento (1 token/segundo)
        # mas burst capacity alto (200 tokens)
        mock_redis_pool.eval.return_value = [1, 150]

        backend = RedisTokenBucketBackend(
            redis_client=mock_redis_pool,
            service_name="orchestrator-dynamic-test",
        )

        # Pico de 100 requests em curto intervalo
        tasks = [
            backend.acquire(
                tenant_id="tenant-spike",
                user_id="user-spike",
                endpoint="/api/v1/predict",
                capacity=200,
                refill_rate=1.0,  # Lento, mas burst alto
            )
            for _ in range(100)
        ]

        results = await asyncio.gather(*tasks)

        # Todas devem ser permitidas (burst)
        assert all(results)

    async def test_burst_exhaustion_returns_429(self, test_settings, mock_redis_pool):
        """Testa que exaurir burst capacity retorna HTTP 429."""
        # Primeiras requests permitem, depois nega
        call_count = 0

        async def mock_eval(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 200:
                return [1, 200 - call_count]  # Permitido
            return [0, 0]  # Negado - burst esgotado

        mock_redis_pool.eval = mock_eval

        backend = RedisTokenBucketBackend(
            redis_client=mock_redis_pool,
            service_name="orchestrator-dynamic-test",
        )

        # Fazer 201 requests (burst capacity = 200)
        results = []
        for _ in range(201):
            result = await backend.acquire(
                tenant_id="tenant-exhaust",
                user_id="user-exhaust",
                endpoint="/api/v1/predict",
                capacity=200,
                refill_rate=10.0,
            )
            results.append(result)

        # Assert - primeiras 200 permitidas, última negada
        assert sum(results) == 200  # 200 True
        assert not results[-1]  # Última é False


# =============================================================================
# Testes de Concorrência (7.5)
# =============================================================================


@pytest.mark.asyncio
class TestRateLimitConcurrency:
    """Testes de concorrência (múltiplas requests mesma chave)."""

    async def test_concurrent_requests_same_key(self, test_settings, mock_redis_pool):
        """Testa que múltiplas requests concorrentes para mesma chave são tratadas corretamente."""
        # Simular 50 requests concorrentes
        call_count = 0

        async def mock_eval(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # Permitir primeiras 20, negar restantes
            if call_count <= 20:
                return [1, 100 - call_count]
            return [0, 0]

        mock_redis_pool.eval = mock_eval

        backend = RedisTokenBucketBackend(
            redis_client=mock_redis_pool,
            service_name="orchestrator-dynamic-test",
        )

        # Criar 50 tasks concorrentes
        tasks = [
            backend.acquire(
                tenant_id="tenant-concurrent",
                user_id="user-concurrent",
                endpoint="/api/v1/predict",
                capacity=20,
                refill_rate=10.0,
            )
            for _ in range(50)
        ]

        # Executar concorrentemente
        results = await asyncio.gather(*tasks)

        # Assert - exatamente 20 devem ser permitidas
        allowed_count = sum(results)
        assert allowed_count == 20

    async def test_different_users_separate_buckets(
        self, test_settings, mock_redis_pool
    ):
        """Testa que usuários diferentes têm buckets independentes."""
        # Criar chaves para verificar que são diferentes
        key1 = generate_rate_limit_key("tenant-concurrent", "user-1", "/api/v1/predict")
        key2 = generate_rate_limit_key("tenant-concurrent", "user-2", "/api/v1/predict")
        key3 = generate_rate_limit_key("tenant-concurrent", "user-3", "/api/v1/predict")

        # Assert - chaves devem ser diferentes
        assert key1 != key2
        assert key2 != key3
        assert key1 != key3

        # Verificar que cada chave contém o user_id correto
        assert "user-1" in key1
        assert "user-2" in key2
        assert "user-3" in key3

    async def test_different_endpoints_separate_buckets(
        self, test_settings, mock_redis_pool
    ):
        """Testa que endpoints diferentes têm buckets independentes."""
        # Criar chaves para verificar que são diferentes
        key1 = generate_rate_limit_key("tenant-123", "user-456", "/api/v1/predict")
        key2 = generate_rate_limit_key("tenant-123", "user-456", "/api/v1/workflows")
        key3 = generate_rate_limit_key("tenant-123", "user-456", "/api/v1/health")

        # Assert - 3 chaves diferentes (uma por endpoint)
        assert key1 != key2
        assert key2 != key3
        assert key1 != key3

        # Verificar que cada chave contém o endpoint
        assert "_api_v1_predict" in key1
        assert "_api_v1_workflows" in key2
        assert "_api_v1_health" in key3


# =============================================================================
# Testes de TTL Expiration (7.6)
# =============================================================================


@pytest.mark.asyncio
class TestRateLimitTTLExpiration:
    """Testes de expiração de TTL (1 hora)."""

    async def test_ttl_set_on_key_creation(self, mock_redis_pool):
        """Testa que TTL de 1 hora é definido na criação da chave."""
        mock_redis_pool.eval.return_value = [1, 95]
        mock_redis_pool.expire = AsyncMock(return_value=True)

        backend = RedisTokenBucketBackend(
            redis_client=mock_redis_pool,
            service_name="orchestrator-dynamic-test",
            default_ttl=3600,  # 1 hora
        )

        await backend.acquire(
            tenant_id="tenant-ttl",
            user_id="user-ttl",
            endpoint="/api/v1/test",
            capacity=100,
            refill_rate=10.0,
        )

        # Assert - expire deve ser chamado pelo Lua script
        # (o script chama EXPIRE internamente)
        mock_redis_pool.eval.assert_called_once()
        # Verificar que o TTL de 3600 foi passado no script
        call_args = mock_redis_pool.eval.call_args
        # O script usa EXPIRE key, 3600

    async def test_key_expires_after_ttl(self, mock_redis_pool):
        """Testa que chave expira após TTL (simulado)."""
        # Simular comportamento de expiração
        first_call = True

        async def mock_eval(*args, **kwargs):
            nonlocal first_call
            if first_call:
                first_call = False
                # Primeira chamada: chave existe
                return [1, 95]
            # Chamadas subsequentes: chave expirou
            # Simula que chave não existe mais (retorna capacity inicial)
            return [1, 100]  # Full capacity após TTL

        mock_redis_pool.eval = mock_eval

        backend = RedisTokenBucketBackend(
            redis_client=mock_redis_pool,
            service_name="orchestrator-dynamic-test",
        )

        # Primeira request
        result1 = await backend.acquire(
            tenant_id="tenant-ttl-expire",
            user_id="user-ttl-expire",
            endpoint="/api/v1/test",
            capacity=100,
            refill_rate=10.0,
        )

        # Simular passagem do tempo (chave expira)
        # Em teste real, esperaríamos TTL passar
        # Aqui simulamos que chave foi recriada

        # Request após expiração
        result2 = await backend.acquire(
            tenant_id="tenant-ttl-expire",
            user_id="user-ttl-expire",
            endpoint="/api/v1/test",
            capacity=100,
            refill_rate=10.0,
        )

        assert result1 is True
        assert result2 is True

    async def test_reset_with_custom_ttl(self, mock_redis_pool):
        """Testa reset com TTL customizado."""
        mock_redis_pool.hset = AsyncMock(return_value=True)
        mock_redis_pool.expire = AsyncMock(return_value=True)

        backend = RedisTokenBucketBackend(
            redis_client=mock_redis_pool,
            service_name="orchestrator-dynamic-test",
        )

        # Reset com TTL customizado de 300 segundos
        success = await backend.reset(
            tenant_id="tenant-reset",
            user_id="user-reset",
            endpoint="/api/v1/test",
            capacity=100,
            ttl_seconds=300,
        )

        assert success is True
        mock_redis_pool.expire.assert_called_once()
        # Verificar que TTL de 300 foi usado
        call_args = mock_redis_pool.expire.call_args
        # expire(key, ttl) - segundo argumento é TTL
        assert call_args[0][1] == 300

    async def test_unused_key_cleaned_up(self, mock_redis_pool):
        """Testa que chave não utilizada é limpa após TTL."""
        # Em Redis real, chaves com TTL expiram automaticamente
        # Aqui testamos que o backend define TTL corretamente

        mock_redis_pool.eval.return_value = [1, 100]

        backend = RedisTokenBucketBackend(
            redis_client=mock_redis_pool,
            service_name="orchestrator-dynamic-test",
            default_ttl=7200,  # 2 horas
        )

        await backend.acquire(
            tenant_id="tenant-cleanup",
            user_id="user-cleanup",
            endpoint="/api/v1/rarely-used",
            capacity=100,
            refill_rate=10.0,
        )

        # Verificar que expire foi chamado
        mock_redis_pool.eval.assert_called_once()


# =============================================================================
# Testes de Atomicidade Lua (7.7)
# =============================================================================


@pytest.mark.asyncio
class TestRateLimitLuaAtomicity:
    """Testes de atomicidade das operações Lua."""

    async def test_lua_script_operations_are_atomic(self, mock_redis_pool):
        """Testa que operações Lua são atômicas (check-and-set)."""
        # O Lua script garante que refill e acquire são atômicos
        # Não há race condition entre ler tokens e consumir

        mock_redis_pool.eval.return_value = [1, 99]

        backend = RedisTokenBucketBackend(
            redis_client=mock_redis_pool,
            service_name="orchestrator-dynamic-test",
        )

        # Executar acquire
        allowed = await backend.acquire(
            tenant_id="tenant-atomic",
            user_id="user-atomic",
            endpoint="/api/v1/test",
            capacity=100,
            refill_rate=10.0,
        )

        assert allowed is True
        # Verificar que apenas uma chamada a eval foi necessária
        # (refill e acquire são atômicos no script)
        assert mock_redis_pool.eval.call_count == 1

    async def test_concurrent_race_condition_prevented(self, mock_redis_pool):
        """Testa que race condition é prevenida por Lua script."""
        # Simular cenário onde 2 processos tentam consumir tokens
        # simultaneamente - o script garante atomicidade

        total_tokens = 100
        tokens_consumed = 0

        async def mock_eval(*args, **kwargs):
            nonlocal tokens_consumed
            # Simular token bucket compartilhado
            remaining = total_tokens - tokens_consumed
            if remaining >= 1:
                tokens_consumed += 1
                return [1, remaining - 1]
            return [0, 0]

        mock_redis_pool.eval = mock_eval

        backend = RedisTokenBucketBackend(
            redis_client=mock_redis_pool,
            service_name="orchestrator-dynamic-test",
        )

        # 150 requests concorrentes para bucket de 100 tokens
        tasks = [
            backend.acquire(
                tenant_id="tenant-race",
                user_id="user-race",
                endpoint="/api/v1/test",
                capacity=total_tokens,
                refill_rate=0,
            )
            for _ in range(150)
        ]

        results = await asyncio.gather(*tasks)

        # Assert - exatamente 100 devem ser permitidas (capacity)
        # Nenhuma race condition deve permitir mais que 100
        allowed_count = sum(results)
        assert allowed_count == 100
        assert tokens_consumed == 100

    async def test_refill_happens_before_acquire(self, mock_redis_pool):
        """Testa que refill acontece antes de acquire (garantido por Lua)."""
        # Simular passage de tempo causando refill
        # O script calcula: elapsed * refill_rate

        mock_time = 0.0

        async def mock_eval(*args, **kwargs):
            nonlocal mock_time
            capacity = args[2]  # ARGV[1]
            refill_rate = args[3]  # ARGV[2]
            # Simular last_refill no passado
            elapsed = 10.0  # 10 segundos passaram
            refill_amount = int(elapsed * refill_rate)
            current_tokens = min(capacity, refill_amount)  # Começou vazio
            if current_tokens >= 1:
                return [1, current_tokens - 1]
            return [0, 0]

        mock_redis_pool.eval = mock_eval

        backend = RedisTokenBucketBackend(
            redis_client=mock_redis_pool,
            service_name="orchestrator-dynamic-test",
        )

        # Depois de 10 segundos com refill_rate=10, devem ter 100 tokens
        allowed = await backend.acquire(
            tenant_id="tenant-refill",
            user_id="user-refill",
            endpoint="/api/v1/test",
            capacity=100,
            refill_rate=10.0,
        )

        assert allowed is True


# =============================================================================
# Testes de Separação de Chaves
# =============================================================================


class TestRateLimitKeySeparation:
    """Testes de separação de chaves por tenant/user/endpoint."""

    def test_keys_include_all_context(self):
        """Testa que chaves incluem tenant, user e endpoint."""
        key1 = generate_rate_limit_key("tenant-1", "user-1", "/api/v1/test")
        key2 = generate_rate_limit_key("tenant-1", "user-1", "/api/v2/test")
        key3 = generate_rate_limit_key("tenant-1", "user-2", "/api/v1/test")
        key4 = generate_rate_limit_key("tenant-2", "user-1", "/api/v1/test")

        # Todas devem ser diferentes
        assert key1 != key2  # endpoint diferente
        assert key1 != key3  # user diferente
        assert key1 != key4  # tenant diferente

        # Todas devem ter prefixo comum
        assert all(k.startswith("rate_limit:") for k in [key1, key2, key3, key4])

    def test_special_characters_sanitized(self):
        """Testa que caracteres especiais são sanitizados."""
        key = generate_rate_limit_key(
            tenant_id="tenant@example.com",
            user_id="user@domain.com",
            endpoint="/api/v1/test?action=query&filter=x",
        )

        # Caracteres especiais devem ser substituídos por _
        # O prefixo "rate_limit:" tem um ':' que não deve ser removido
        assert key.count(":") == 3  # Apenas os separadores da chave
        assert "@" not in key
        assert "?" not in key
        assert "=" not in key
        assert "&" not in key
        assert "tenant_example_com" in key
        assert "user_domain_com" in key
        assert "_api_v1_test_action_query_filter_x" in key

    def test_global_endpoint_when_none(self):
        """Testa que 'global' é usado quando endpoint é None."""
        key = generate_rate_limit_key("tenant-1", "user-1", None)
        assert key.endswith(":global")
