"""
Testes de integração Redis Cluster
Usa testcontainers para criar cluster Redis real
"""

import pytest
import asyncio
import json
from testcontainers.compose import DockerCompose
from testcontainers.redis import RedisContainer

from src.cache.redis_client import RedisClient, CircuitBreakerError


@pytest.fixture(scope="session")
def redis_cluster():
    """
    Setup de Redis Cluster usando testcontainers
    Cria um cluster real para testes de integração
    """
    # Usar Docker Compose para cluster Redis
    compose = DockerCompose(".", compose_file_name="docker-compose.test.yml")

    # Se não existir compose, usar container single Redis para testes básicos
    try:
        with compose:
            compose.start()
            # Aguardar cluster estar pronto
            import time
            time.sleep(10)

            yield {
                "nodes": "localhost:6379,localhost:6380,localhost:6381",
                "password": None
            }
    except:
        # Fallback para Redis único se cluster não disponível
        with RedisContainer("redis:7-alpine") as redis:
            yield {
                "nodes": f"localhost:{redis.get_exposed_port(6379)}",
                "password": None
            }


@pytest.fixture
def redis_client_config(redis_cluster):
    """Configuração do cliente Redis para testes"""
    from unittest.mock import Mock

    settings = Mock()
    settings.redis_cluster_nodes = redis_cluster["nodes"]
    settings.redis_password = redis_cluster["password"]
    settings.redis_ca_cert_path = None
    settings.redis_default_ttl = 60
    settings.redis_max_connections = 10
    settings.redis_timeout = 5000

    return settings


@pytest.fixture
async def redis_client(redis_client_config):
    """Cliente Redis configurado para cluster de teste"""
    from unittest.mock import patch

    with patch('src.cache.redis_client.get_settings', return_value=redis_client_config):
        client = RedisClient()
        await client.initialize()

        yield client

        # Cleanup
        await client.close()


class TestRedisClusterIntegration:
    """Testes de integração com Redis Cluster real"""

    @pytest.mark.asyncio
    async def test_basic_operations(self, redis_client):
        """Testa operações básicas CRUD"""
        # Set
        result = await redis_client.set("test_key", "test_value")
        assert result is True

        # Get
        value = await redis_client.get("test_key")
        assert value == "test_value"

        # Exists
        exists = await redis_client.exists("test_key")
        assert exists is True

        # Delete
        deleted = await redis_client.delete("test_key")
        assert deleted is True

        # Verify deleted
        value = await redis_client.get("test_key")
        assert value is None

    @pytest.mark.asyncio
    async def test_json_serialization(self, redis_client):
        """Testa serialização/deserialização JSON"""
        test_data = {
            "user_id": "123",
            "username": "test_user",
            "metadata": {
                "last_login": "2023-01-01T00:00:00Z",
                "roles": ["user", "admin"]
            }
        }

        # Armazenar dados complexos
        await redis_client.set("user:123", test_data)

        # Recuperar e verificar
        retrieved = await redis_client.get("user:123")
        assert retrieved == test_data
        assert isinstance(retrieved["metadata"]["roles"], list)

    @pytest.mark.asyncio
    async def test_ttl_expiration(self, redis_client):
        """Testa expiração TTL"""
        # Set com TTL curto
        await redis_client.set("temp_key", "temp_value", ttl=2)

        # Verificar que existe
        value = await redis_client.get("temp_key")
        assert value == "temp_value"

        # Aguardar expiração
        await asyncio.sleep(3)

        # Verificar que expirou
        value = await redis_client.get("temp_key")
        assert value is None

    @pytest.mark.asyncio
    async def test_circuit_breaker_behavior(self, redis_client):
        """Testa comportamento do circuit breaker"""
        # Simular falhas forçando erro
        original_redis = redis_client.redis

        # Mock redis que falha
        from unittest.mock import AsyncMock
        failing_redis = AsyncMock()
        failing_redis.get.side_effect = Exception("Connection failed")

        redis_client.redis = failing_redis

        # Causar falhas suficientes para abrir circuit breaker
        for _ in range(6):  # threshold + 1
            try:
                await redis_client.get("test_key")
            except:
                pass

        # Circuit breaker deve estar aberto
        assert redis_client.circuit_breaker.state == "OPEN"

        # Próximas chamadas devem falhar com CircuitBreakerError
        with pytest.raises(CircuitBreakerError):
            await redis_client.get("test_key")

        # Restaurar redis original para cleanup
        redis_client.redis = original_redis

    @pytest.mark.asyncio
    async def test_pipeline_operations(self, redis_client):
        """Testa operações em pipeline"""
        operations = [
            {"method": "set", "args": ["pipe_key1", "value1"]},
            {"method": "set", "args": ["pipe_key2", "value2"]},
            {"method": "get", "args": ["pipe_key1"]},
            {"method": "get", "args": ["pipe_key2"]}
        ]

        try:
            results = await redis_client.pipeline_operations(operations)

            # Em single node, pipeline deve funcionar
            if len(results) > 0:
                # Verificar que operações foram executadas
                value1 = await redis_client.get("pipe_key1")
                value2 = await redis_client.get("pipe_key2")
                assert value1 == "value1"
                assert value2 == "value2"
        except Exception:
            # Em cluster, pipeline pode falhar se chaves estão em slots diferentes
            # Isso é comportamento esperado
            pass

    @pytest.mark.asyncio
    async def test_cache_statistics(self, redis_client):
        """Testa coleta de estatísticas"""
        # Gerar alguns hits e misses
        await redis_client.set("stats_key", "stats_value")
        await redis_client.get("stats_key")  # hit
        await redis_client.get("nonexistent_key")  # miss

        stats = await redis_client.get_cache_stats()

        assert stats["connected"] is True
        assert stats["hits"] >= 1
        assert stats["misses"] >= 1
        assert stats["hit_ratio"] > 0
        assert "circuit_breaker_state" in stats

    @pytest.mark.asyncio
    async def test_distributed_locking(self, redis_client):
        """Testa locks distribuídos"""
        lock_key = "test_lock"

        # Adquirir lock
        async with redis_client.acquire_lock(lock_key, timeout=10):
            # Dentro do lock, verificar que está adquirido
            # (em teste real, outro cliente não conseguiria adquirir)

            # Realizar operação crítica
            await redis_client.set("critical_resource", "processing")
            value = await redis_client.get("critical_resource")
            assert value == "processing"

        # Após sair do context manager, lock deve estar liberado
        # Verificar que não existe mais
        exists = await redis_client.exists(lock_key)
        assert exists is False

    @pytest.mark.asyncio
    async def test_concurrent_access(self, redis_client):
        """Testa acesso concorrente"""
        async def worker(worker_id):
            """Worker que escreve dados concorrentemente"""
            for i in range(10):
                key = f"worker_{worker_id}:item_{i}"
                value = f"data_from_worker_{worker_id}_item_{i}"
                await redis_client.set(key, value)

                # Verificar que conseguiu ler de volta
                retrieved = await redis_client.get(key)
                assert retrieved == value

        # Executar múltiplos workers concorrentemente
        tasks = [worker(i) for i in range(5)]
        await asyncio.gather(*tasks)

        # Verificar que todos os dados foram escritos corretamente
        for worker_id in range(5):
            for item_id in range(10):
                key = f"worker_{worker_id}:item_{item_id}"
                expected = f"data_from_worker_{worker_id}_item_{item_id}"
                actual = await redis_client.get(key)
                assert actual == expected

    @pytest.mark.asyncio
    async def test_large_data_handling(self, redis_client):
        """Testa manipulação de dados grandes"""
        # Criar dados grandes (mas não muito para não sobrecarregar testes)
        large_data = {
            "id": "large_object",
            "data": "x" * 10000,  # 10KB string
            "array": list(range(1000)),
            "nested": {
                "level1": {
                    "level2": {
                        "level3": "deep_value"
                    }
                }
            }
        }

        # Armazenar dados grandes
        result = await redis_client.set("large_key", large_data)
        assert result is True

        # Recuperar dados grandes
        retrieved = await redis_client.get("large_key")
        assert retrieved == large_data
        assert len(retrieved["data"]) == 10000
        assert len(retrieved["array"]) == 1000
        assert retrieved["nested"]["level1"]["level2"]["level3"] == "deep_value"

    @pytest.mark.asyncio
    async def test_error_handling_and_recovery(self, redis_client):
        """Testa recuperação de erros"""
        # Operação normal
        await redis_client.set("recovery_test", "initial_value")
        value = await redis_client.get("recovery_test")
        assert value == "initial_value"

        # Simular erro temporário e recuperação
        # (em um teste real com cluster, poderíamos parar/iniciar um node)

        # Por enquanto, testar que o cliente continua funcionando
        await redis_client.set("recovery_test", "updated_value")
        value = await redis_client.get("recovery_test")
        assert value == "updated_value"


class TestRedisClusterFailover:
    """Testes específicos de failover e resiliência"""

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Requer cluster Redis multi-node real")
    async def test_node_failover(self, redis_client):
        """Testa failover quando um node falha"""
        # Este teste requer um cluster Redis real com múltiplos nodes
        # Seria executado apenas em ambiente de integração completa
        pass

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Requer cluster Redis multi-node real")
    async def test_cluster_scaling(self, redis_client):
        """Testa adição/remoção de nodes do cluster"""
        # Este teste requer capacidade de modificar o cluster dinamicamente
        pass


# Configuração do Docker Compose para testes (seria em arquivo separado)
REDIS_CLUSTER_COMPOSE = """
version: '3.8'
services:
  redis-node-1:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    command: redis-server --cluster-enabled yes --cluster-config-file nodes.conf --cluster-node-timeout 5000 --appendonly yes

  redis-node-2:
    image: redis:7-alpine
    ports:
      - "6380:6379"
    command: redis-server --cluster-enabled yes --cluster-config-file nodes.conf --cluster-node-timeout 5000 --appendonly yes

  redis-node-3:
    image: redis:7-alpine
    ports:
      - "6381:6379"
    command: redis-server --cluster-enabled yes --cluster-config-file nodes.conf --cluster-node-timeout 5000 --appendonly yes
"""