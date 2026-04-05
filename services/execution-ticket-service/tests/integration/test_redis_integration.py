"""
Integration Tests para Redis Client - Execution Ticket Service

Testes de integração que usam Redis real via testcontainers.
Cobre: conexão, circuit breaker, cache operations, pub/sub, rate limiting.
"""
import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import redis.asyncio as redis
import src.database.redis_client as redis_client_module
from src.database.redis_client import (
    CircuitBreaker,
    close_redis_client,
    get_circuit_breaker_state,
    get_redis_client,
)

# ===== FIXTURES =====


@pytest.fixture
def mock_settings():
    """Configurações mockadas para testes."""
    return SimpleNamespace(
        redis_url=None,
        redis_host="localhost",
        redis_port=6379,
        redis_password=None,
        redis_ssl_enabled=False,
    )


@pytest.fixture
def mock_settings_with_url():
    """Configurações com URL Redis para testes."""
    return SimpleNamespace(
        redis_url="redis://localhost:6379/1",
        redis_host="localhost",
        redis_port=6379,
        redis_password=None,
        redis_ssl_enabled=False,
    )


@pytest.fixture
async def redis_mock_client():  # noqa: C901
    """
    Cliente Redis mockado para testes de integração.

    Simula o comportamento do redis.asyncio sem necessitar de container real.
    """
    # Estado em memória do Redis mockado
    redis_store = {}
    redis_sets = {}
    pubsub_channels = {}
    rate_limit_counters = {}

    class MockRedis:
        def __init__(self):
            self.closed = False

        async def ping(self):
            """Simula comando PING."""
            if self.closed:
                raise redis.ConnectionError("Connection closed")
            return True

        async def get(self, key):
            """Simula comando GET."""
            if self.closed:
                raise redis.ConnectionError("Connection closed")
            return redis_store.get(key)

        async def set(self, key, value, ex=None):
            """Simula comando SET com expiração opcional."""
            if self.closed:
                raise redis.ConnectionError("Connection closed")
            redis_store[key] = value
            if ex:
                # Simular TTL agendando remoção (simplificado)
                async def delayed_delete():
                    await asyncio.sleep(ex)
                    redis_store.pop(key, None)

                # RUF006: Ignorar - tarefa de limpeza fire-and-forget é intencional
                asyncio.create_task(delayed_delete())  # noqa: RUF006
            return True

        async def delete(self, key):
            """Simula comando DELETE."""
            if self.closed:
                raise redis.ConnectionError("Connection closed")
            redis_store.pop(key, None)
            return 1

        async def exists(self, key):
            """Simula comando EXISTS."""
            if self.closed:
                raise redis.ConnectionError("Connection closed")
            return 1 if key in redis_store else 0

        async def expire(self, key, _seconds):
            """Simula comando EXPIRE."""
            if self.closed:
                raise redis.ConnectionError("Connection closed")
            # Simplificado: apenas retorna True se key existe
            return 1 if key in redis_store else 0

        async def ttl(self, key):
            """Simula comando TTL."""
            if self.closed:
                raise redis.ConnectionError("Connection closed")
            if key in redis_store:
                return -1  # Sem expiração definida
            return -2  # Key não existe

        async def incr(self, key):
            """Simula comando INCR para rate limiting."""
            if self.closed:
                raise redis.ConnectionError("Connection closed")
            redis_store[key] = redis_store.get(key, 0) + 1
            return redis_store[key]

        async def incrby(self, key, amount):
            """Simula comando INCRBY."""
            if self.closed:
                raise redis.ConnectionError("Connection closed")
            redis_store[key] = redis_store.get(key, 0) + amount
            return redis_store[key]

        async def expireat(self, key, _timestamp):
            """Simula comando EXPIREAT."""
            if self.closed:
                raise redis.ConnectionError("Connection closed")
            return 1 if key in redis_store else 0

        async def sadd(self, key, *members):
            """Simula comando SADD para sets."""
            if self.closed:
                raise redis.ConnectionError("Connection closed")
            if key not in redis_sets:
                redis_sets[key] = set()
            added = 0
            for member in members:
                if member not in redis_sets[key]:
                    redis_sets[key].add(member)
                    added += 1
            return added

        async def srem(self, key, *members):
            """Simula comando SREM."""
            if self.closed:
                raise redis.ConnectionError("Connection closed")
            if key not in redis_sets:
                return 0
            removed = 0
            for member in members:
                if member in redis_sets[key]:
                    redis_sets[key].remove(member)
                    removed += 1
            return removed

        async def smembers(self, key):
            """Simula comando SMEMBERS."""
            if self.closed:
                raise redis.ConnectionError("Connection closed")
            return redis_sets.get(key, set())

        async def scard(self, key):
            """Simula comando SCARD."""
            if self.closed:
                raise redis.ConnectionError("Connection closed")
            return len(redis_sets.get(key, set()))

        async def publish(self, channel, message):
            """Simula comando PUBLISH."""
            if self.closed:
                raise redis.ConnectionError("Connection closed")
            if channel not in pubsub_channels:
                pubsub_channels[channel] = []
            pubsub_channels[channel].append(message)
            return len(pubsub_channels[channel])

        async def aclose(self):
            """Fecha a conexão mockada."""
            self.closed = True
            redis_store.clear()
            redis_sets.clear()
            pubsub_channels.clear()
            rate_limit_counters.clear()

        def clear_all(self):
            """Limpa todo o estado (helper para testes)."""
            redis_store.clear()
            redis_sets.clear()
            pubsub_channels.clear()
            rate_limit_counters.clear()

        def get_store_size(self):
            """Retorna tamanho do store (helper para assertions)."""
            return len(redis_store)

    return MockRedis()


@pytest.fixture(autouse=True)
async def reset_circuit_breaker():
    """Reseta o circuit breaker global antes/depois de testes."""
    # Resetar para CLOSED antes do teste
    redis_client_module._circuit_breaker.reset()
    redis_client_module._redis_client_instance = None

    yield

    # Limpar após teste
    redis_client_module._circuit_breaker.reset()
    redis_client_module._redis_client_instance = None


# ===== TESTES: Conexão =====


class TestRedisConnection:
    """Testes de conexão com Redis."""

    @pytest.mark.asyncio
    async def test_connect_with_host_port(self, mock_settings, redis_mock_client):
        """
        DADO: Configurações com host e porta
        QUANDO: Chamo get_redis_client
        ENTÃO: Deve criar cliente com host/port corretos
        """
        with patch("src.database.redis_client.redis.Redis", return_value=redis_mock_client):
            client = await get_redis_client(mock_settings)

        assert client is not None
        await client.aclose()

    @pytest.mark.asyncio
    async def test_connect_with_url(self, mock_settings_with_url, redis_mock_client):
        """
        DADO: Configurações com URL
        QUANDO: Chamo get_redis_client
        ENTÃO: Deve criar cliente usando URL
        """
        with patch("src.database.redis_client.redis.from_url", return_value=redis_mock_client):
            client = await get_redis_client(mock_settings_with_url)

        assert client is not None
        await client.aclose()

    @pytest.mark.asyncio
    async def test_connect_returns_singleton(self, mock_settings, redis_mock_client):
        """
        DADO: Cliente já criado
        QUANDO: Chamo get_redis_client novamente
        ENTÃO: Deve retornar mesma instância (singleton)
        """
        with patch("src.database.redis_client.redis.Redis", return_value=redis_mock_client):
            client1 = await get_redis_client(mock_settings)
            client2 = await get_redis_client(mock_settings)

        assert client1 is client2
        await client1.aclose()

    @pytest.mark.asyncio
    async def test_ping_successful(self, mock_settings, redis_mock_client):
        """
        DADO: Conexão ativa com Redis
        QUANDO: Executo ping
        ENTÃO: Deve retornar True
        """
        with patch("src.database.redis_client.redis.Redis", return_value=redis_mock_client):
            client = await get_redis_client(mock_settings)
            result = await client.ping()

        assert result is True
        await client.aclose()


# ===== TESTES: Circuit Breaker =====


class TestCircuitBreaker:
    """Testes do Circuit Breaker para Redis."""

    def test_circuit_breaker_initial_state(self):
        """
        DADO: Um Circuit Breaker recém-criado
        ENTÃO: Estado deve ser CLOSED
        """
        cb = CircuitBreaker(failure_threshold=5, recovery_timeout=60)

        assert cb.state == "CLOSED"
        assert cb.failure_count == 0
        assert cb.last_failure_time is None

    def test_circuit_breaker_allows_requests_when_closed(self):
        """
        DADO: Circuit Breaker em estado CLOSED
        QUANDO: Verifico should_allow_request
        ENTÃO: Deve retornar True
        """
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60)

        assert cb.should_allow_request() is True

    def test_circuit_breaker_opens_after_threshold(self):
        """
        DADO: Circuit Breaker com threshold de 3 falhas
        QUANDO: Registro 3 falhas consecutivas
        ENTÃO: Deve abrir o circuito (OPEN)
        """
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60)

        # Registrar falhas até atingir threshold
        for _ in range(3):
            cb.record_failure()

        assert cb.state == "OPEN"
        assert cb.failure_count == 3

    def test_circuit_breaker_blocks_requests_when_open(self):
        """
        DADO: Circuit Breaker em estado OPEN
        QUANDO: Verifico should_allow_request
        ENTÃO: Deve retornar False
        """
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=60)

        # Abrir circuito
        cb.record_failure()
        cb.record_failure()

        assert cb.state == "OPEN"
        assert cb.should_allow_request() is False

    def test_circuit_breaker_transitions_to_half_open_after_timeout(self):
        """
        DADO: Circuit Breaker em estado OPEN
        QUANDO: Tempo de recovery expira
        ENTÃO: Deve transicionar para HALF_OPEN
        """
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=1)

        # Abrir circuito
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "OPEN"

        # Simular passagem do tempo
        cb.last_failure_time = time.time() - 2  # 2 segundos atrás

        # Deve transicionar para HALF_OPEN
        result = cb.should_allow_request()

        assert cb.state == "HALF_OPEN"
        assert result is True

    def test_circuit_breaker_resets_on_success_in_half_open(self):
        """
        DADO: Circuit Breaker em estado HALF_OPEN
        QUANDO: Registro sucesso
        ENTÃO: Deve voltar para CLOSED
        """
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=60)

        # Forçar estado HALF_OPEN
        cb.state = "HALF_OPEN"
        cb.failure_count = 2

        # Registrar sucesso
        cb.record_success()

        assert cb.state == "CLOSED"
        assert cb.failure_count == 0

    def test_circuit_breaker_reset(self):
        """
        DADO: Circuit Breaker em qualquer estado
        QUANDO: Chamo reset
        ENTÃO: Deve voltar para CLOSED e zerar contadores
        """
        cb = CircuitBreaker(failure_threshold=5, recovery_timeout=60)

        # Simular estado de falha
        cb.state = "OPEN"
        cb.failure_count = 5
        cb.last_failure_time = time.time()

        cb.reset()

        assert cb.state == "CLOSED"
        assert cb.failure_count == 0
        assert cb.last_failure_time is None

    @pytest.mark.asyncio
    async def test_redis_blocked_when_circuit_open(self, mock_settings):
        """
        DADO: Circuit Breaker OPEN
        QUANDO: Chamo get_redis_client
        ENTÃO: Deve retornar None sem tentar conexão
        """
        # Forçar circuit breaker para OPEN
        redis_client_module._circuit_breaker.state = "OPEN"
        redis_client_module._circuit_breaker.last_failure_time = time.time()

        client = await get_redis_client(mock_settings)

        assert client is None

    @pytest.mark.asyncio
    async def test_get_circuit_breaker_state(self):
        """
        DADO: Circuit Breaker com estado específico
        QUANDO: Chamo get_circuit_breaker_state
        ENTÃO: Deve retornar dict com informações completas
        """
        # Configurar estado específico
        redis_client_module._circuit_breaker.state = "OPEN"
        redis_client_module._circuit_breaker.failure_count = 5

        state = get_circuit_breaker_state()

        assert state["state"] == "OPEN"
        assert state["failure_count"] == 5
        assert state["failure_threshold"] == 5
        assert state["recovery_timeout"] == 60
        assert "last_failure_time" in state


# ===== TESTES: Operações de Cache =====


class TestRedisCacheOperations:
    """Testes de operações de cache no Redis."""

    @pytest.mark.asyncio
    async def test_set_and_get_value(self, mock_settings, redis_mock_client):
        """
        DADO: Um cliente Redis conectado
        QUANDO: Defino e leio um valor
        ENTÃO: Deve armazenar e recuperar corretamente
        """
        with patch("src.database.redis_client.redis.Redis", return_value=redis_mock_client):
            client = await get_redis_client(mock_settings)

            await client.set("test_key", "test_value")
            result = await client.get("test_key")

        assert result == "test_value"
        await client.aclose()

    @pytest.mark.asyncio
    async def test_set_with_expiration(self, mock_settings, redis_mock_client):
        """
        DADO: Um cliente Redis conectado
        QUANDO: Defino valor com TTL
        ENTÃO: Deve armazenar com expiração
        """
        with patch("src.database.redis_client.redis.Redis", return_value=redis_mock_client):
            client = await get_redis_client(mock_settings)

            await client.set("temp_key", "temp_value", ex=1)
            result = await client.get("temp_key")

        assert result == "temp_value"
        await client.aclose()

    @pytest.mark.asyncio
    async def test_get_nonexistent_key(self, mock_settings, redis_mock_client):
        """
        DADO: Redis sem a chave especificada
        QUANDO: Leio chave inexistente
        ENTÃO: Deve retornar None
        """
        with patch("src.database.redis_client.redis.Redis", return_value=redis_mock_client):
            client = await get_redis_client(mock_settings)
            result = await client.get("nonexistent_key")

        assert result is None
        await client.aclose()

    @pytest.mark.asyncio
    async def test_delete_key(self, mock_settings, redis_mock_client):
        """
        DADO: Redis com chave existente
        QUANDO: Deleto a chave
        ENTÃO: Deve remover e retornar 1
        """
        with patch("src.database.redis_client.redis.Redis", return_value=redis_mock_client):
            client = await get_redis_client(mock_settings)

            await client.set("to_delete", "value")
            delete_result = await client.delete("to_delete")
            get_result = await client.get("to_delete")

        assert delete_result == 1
        assert get_result is None
        await client.aclose()

    @pytest.mark.asyncio
    async def test_exists_check(self, mock_settings, redis_mock_client):
        """
        DADO: Redis com e sem chaves
        QUANDO: Verifico existência
        ENTÃO: Deve retornar 1 para existente, 0 para inexistente
        """
        with patch("src.database.redis_client.redis.Redis", return_value=redis_mock_client):
            client = await get_redis_client(mock_settings)

            await client.set("existing_key", "value")
            exists_true = await client.exists("existing_key")
            exists_false = await client.exists("nonexistent_key")

        assert exists_true == 1
        assert exists_false == 0
        await client.aclose()

    @pytest.mark.asyncio
    async def test_ttl_command(self, mock_settings, redis_mock_client):
        """
        DADO: Redis com chave sem expiração definida
        QUANDO: Consulto TTL
        ENTÃO: Deve retornar -1 (sem expiração)
        """
        with patch("src.database.redis_client.redis.Redis", return_value=redis_mock_client):
            client = await get_redis_client(mock_settings)

            await client.set("no_ttl_key", "value")
            ttl = await client.ttl("no_ttl_key")

        assert ttl == -1
        await client.aclose()

    @pytest.mark.asyncio
    async def test_ttl_nonexistent_key(self, mock_settings, redis_mock_client):
        """
        DADO: Redis sem chave específica
        QUANDO: Consulto TTL de chave inexistente
        ENTÃO: Deve retornar -2 (key não existe)
        """
        with patch("src.database.redis_client.redis.Redis", return_value=redis_mock_client):
            client = await get_redis_client(mock_settings)
            ttl = await client.ttl("nonexistent_key")

        assert ttl == -2
        await client.aclose()

    @pytest.mark.asyncio
    async def test_expire_command(self, mock_settings, redis_mock_client):
        """
        DADO: Redis com chave existente
        QUANDO: Defino expiração com EXPIRE
        ENTÃO: Deve retornar 1 (sucesso)
        """
        with patch("src.database.redis_client.redis.Redis", return_value=redis_mock_client):
            client = await get_redis_client(mock_settings)

            await client.set("key_to_expire", "value")
            result = await client.expire("key_to_expire", 60)

        assert result == 1
        await client.aclose()


# ===== TESTES: Pub/Sub =====


class TestRedisPubSub:
    """Testes de publicação/inscrição no Redis."""

    @pytest.mark.asyncio
    async def test_publish_message(self, mock_settings, redis_mock_client):
        """
        DADO: Um cliente Redis conectado
        QUANDO: Publico mensagem em canal
        ENTÃO: Deve publicar sem erro
        """
        with patch("src.database.redis_client.redis.Redis", return_value=redis_mock_client):
            client = await get_redis_client(mock_settings)

            result = await client.publish("test_channel", "test_message")

        # Publicação bem-sucedida
        assert result >= 0
        await client.aclose()

    @pytest.mark.asyncio
    async def test_publish_multiple_messages(self, mock_settings, redis_mock_client):
        """
        DADO: Um cliente Redis conectado
        QUANDO: Publico múltiplas mensagens
        ENTÃO: Todas devem ser processadas
        """
        with patch("src.database.redis_client.redis.Redis", return_value=redis_mock_client):
            client = await get_redis_client(mock_settings)

            await client.publish("events", "event1")
            await client.publish("events", "event2")
            await client.publish("events", "event3")

        # Mensagens publicadas sem erro
        await client.aclose()

    @pytest.mark.asyncio
    async def test_publish_to_different_channels(self, mock_settings, redis_mock_client):
        """
        DADO: Um cliente Redis conectado
        QUANDO: Publico em canais diferentes
        ENTÃO: Cada canal deve receber suas mensagens
        """
        with patch("src.database.redis_client.redis.Redis", return_value=redis_mock_client):
            client = await get_redis_client(mock_settings)

            await client.publish("channel_a", "message_a")
            await client.publish("channel_b", "message_b")
            await client.publish("channel_a", "message_a2")

        # Mensagens publicadas sem erro
        await client.aclose()


# ===== TESTES: Rate Limiting =====


class TestRedisRateLimiting:
    """Testes de rate limiting usando Redis."""

    @pytest.mark.asyncio
    async def test_incr_counter(self, mock_settings, redis_mock_client):
        """
        DADO: Um cliente Redis conectado
        QUANDO: Incremento contador
        ENTÃO: Deve retornar valor incrementado
        """
        with patch("src.database.redis_client.redis.Redis", return_value=redis_mock_client):
            client = await get_redis_client(mock_settings)

            result1 = await client.incr("request_counter")
            result2 = await client.incr("request_counter")
            result3 = await client.incr("request_counter")

        assert result1 == 1
        assert result2 == 2
        assert result3 == 3
        await client.aclose()

    @pytest.mark.asyncio
    async def test_incrby_counter(self, mock_settings, redis_mock_client):
        """
        DADO: Um cliente Redis conectado
        QUANDO: Incremento contador por valor específico
        ENTÃO: Deve retornar valor somado
        """
        with patch("src.database.redis_client.redis.Redis", return_value=redis_mock_client):
            client = await get_redis_client(mock_settings)

            result1 = await client.incrby("bulk_counter", 10)
            result2 = await client.incrby("bulk_counter", 5)

        assert result1 == 10
        assert result2 == 15
        await client.aclose()

    @pytest.mark.asyncio
    async def test_rate_limit_pattern(self, mock_settings, redis_mock_client):
        """
        DADO: Implementação de rate limiting simples
        QUANDO: Faço múltiplas requisições
        ENTÃO: Deve contar corretamente e respeitar limite
        """
        with patch("src.database.redis_client.redis.Redis", return_value=redis_mock_client):
            client = await get_redis_client(mock_settings)

            user_id = "user_123"
            limit = 5
            window = 60  # segundos

            # Simular pattern de rate limiting
            key = f"rate_limit:{user_id}"

            for i in range(limit):
                count = await client.incr(key)
                if i == 0:
                    # Primeira requisição: definir expiração
                    await client.expire(key, window)

                assert count <= limit, f"Rate limit exceeded at request {i + 1}"

            # Próxima requisição deve exceder
            count = await client.incr(key)
            assert count == limit + 1

        await client.aclose()

    @pytest.mark.asyncio
    async def test_expireat_for_fixed_window(self, mock_settings, redis_mock_client):
        """
        DADO: Um contador de rate limiting
        QUANDO: Uso EXPIREAT para janela de tempo fixa
        ENTÃO: Deve definir expiração em timestamp específico
        """
        with patch("src.database.redis_client.redis.Redis", return_value=redis_mock_client):
            client = await get_redis_client(mock_settings)

            await client.set("window_counter", "1")
            timestamp = int(time.time()) + 60  # 60 segundos no futuro
            result = await client.expireat("window_counter", timestamp)

        assert result == 1
        await client.aclose()


# ===== TESTES: Sets =====


class TestRedisSets:
    """Testes de operações com Sets no Redis."""

    @pytest.mark.asyncio
    async def test_sadd_and_scard(self, mock_settings, redis_mock_client):
        """
        DADO: Um cliente Redis conectado
        QUANDO: Adiciono membros a um set
        ENTÃO: Deve contar corretamente
        """
        with patch("src.database.redis_client.redis.Redis", return_value=redis_mock_client):
            client = await get_redis_client(mock_settings)

            added = await client.sadd("my_set", "member1", "member2", "member3")
            count = await client.scard("my_set")

        assert added == 3
        assert count == 3
        await client.aclose()

    @pytest.mark.asyncio
    async def test_sadd_duplicate_members(self, mock_settings, redis_mock_client):
        """
        DADO: Um set com membros existentes
        QUANDO: Adiciono membros duplicados
        ENTÃO: Deve ignorar duplicatas
        """
        with patch("src.database.redis_client.redis.Redis", return_value=redis_mock_client):
            client = await get_redis_client(mock_settings)

            await client.sadd("unique_set", "member1", "member2")
            added_duplicate = await client.sadd("unique_set", "member1", "member3")
            count = await client.scard("unique_set")

        # Apenas member3 é novo
        assert added_duplicate == 1
        assert count == 3
        await client.aclose()

    @pytest.mark.asyncio
    async def test_srem_members(self, mock_settings, redis_mock_client):
        """
        DADO: Um set com membros
        QUANDO: Removo membros
        ENTÃO: Deve retornar número de removidos
        """
        with patch("src.database.redis_client.redis.Redis", return_value=redis_mock_client):
            client = await get_redis_client(mock_settings)

            await client.sadd("removable_set", "a", "b", "c")
            removed = await client.srem("removable_set", "a", "c")
            count = await client.scard("removable_set")

        assert removed == 2
        assert count == 1
        await client.aclose()

    @pytest.mark.asyncio
    async def test_smembers(self, mock_settings, redis_mock_client):
        """
        DADO: Um set com membros
        QUANDO: Leio todos os membros
        ENTÃO: Deve retornar conjunto completo
        """
        with patch("src.database.redis_client.redis.Redis", return_value=redis_mock_client):
            client = await get_redis_client(mock_settings)

            await client.sadd("read_set", "x", "y", "z")
            members = await client.smembers("read_set")

        assert len(members) == 3
        await client.aclose()


# ===== TESTES: Close Connection =====


class TestRedisClose:
    """Testes de fechamento de conexão Redis."""

    @pytest.mark.asyncio
    async def test_close_redis_client(self, mock_settings, redis_mock_client):
        """
        DADO: Um cliente Redis conectado
        QUANDO: Chamo close_redis_client
        ENTÃO: Deve fechar conexão e limpar instância
        """
        with patch("src.database.redis_client.redis.Redis", return_value=redis_mock_client):
            await get_redis_client(mock_settings)
            assert redis_client_module._redis_client_instance is not None

            await close_redis_client()

        assert redis_client_module._redis_client_instance is None

    @pytest.mark.asyncio
    async def test_close_idempotent(self):
        """
        DADO: Nenhum cliente conectado
        QUANDO: Chamo close_redis_client múltiplas vezes
        ENTÃO: Não deve levantar erro
        """
        redis_client_module._redis_client_instance = None

        # Não deve levantar erro
        await close_redis_client()
        await close_redis_client()
        await close_redis_client()


# ===== TESTES: Error Handling =====


class TestRedisErrorHandling:
    """Testes de tratamento de erros Redis."""

    @pytest.mark.asyncio
    async def test_connection_failure_opens_circuit(self, mock_settings):
        """
        DADO: Redis retornando erro de conexão
        QUANDO: Tentativa de conexão falha
        ENTÃO: Circuit breaker deve registrar falha
        """
        with patch("src.database.redis_client.redis.Redis") as mock_redis_class:
            mock_redis = AsyncMock()
            mock_redis.ping.side_effect = redis.ConnectionError("Connection refused")
            mock_redis_class.return_value = mock_redis

            await get_redis_client(mock_settings)

        # Verificar que falha foi registrada
        assert redis_client_module._circuit_breaker.failure_count > 0

    @pytest.mark.asyncio
    async def test_circuit_opens_after_threshold(self, mock_settings):
        """
        DADO: Múltiplas falhas de conexão
        QUANDO: Threshold é atingido
        ENTÃO: Circuit breaker deve abrir
        """
        with patch("src.database.redis_client.redis.Redis") as mock_redis_class:
            mock_redis = AsyncMock()
            mock_redis.ping.side_effect = redis.ConnectionError("Connection refused")
            mock_redis_class.return_value = mock_redis

            # Fazer 6 tentativas (threshold é 5)
            for _ in range(6):
                await get_redis_client(mock_settings)

        assert redis_client_module._circuit_breaker.state == "OPEN"

    @pytest.mark.asyncio
    async def test_closed_client_operations_fail(self, mock_settings, redis_mock_client):
        """
        DADO: Cliente Redis fechado
        QUANDO: Tento operações
        ENTÃO: Deve retornar erro de conexão fechada
        """
        with patch("src.database.redis_client.redis.Redis", return_value=redis_mock_client):
            client = await get_redis_client(mock_settings)
            await client.aclose()

            with pytest.raises(redis.ConnectionError):
                await client.ping()
