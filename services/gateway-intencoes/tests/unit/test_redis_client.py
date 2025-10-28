"""
Unit tests for Redis Client
Test Redis operations, circuit breaker, and cluster-aware pipeline functionality
"""

import asyncio
import json
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock, call
from redis.exceptions import ConnectionError, TimeoutError, RedisError, RedisClusterException

from src.cache.redis_client import (
    RedisClient,
    CircuitBreaker,
    CircuitBreakerError,
    get_redis_client,
    close_redis_client
)


@pytest.fixture
async def mock_redis_cluster():
    """Mock RedisCluster for testing"""
    mock = AsyncMock()
    mock.ping = AsyncMock(return_value=True)
    mock.get = AsyncMock()
    mock.setex = AsyncMock(return_value=True)
    mock.delete = AsyncMock(return_value=1)
    mock.exists = AsyncMock(return_value=1)
    mock.set = AsyncMock(return_value=True)
    mock.pipeline = Mock()
    mock.keyslot = Mock()
    mock.cluster_info = AsyncMock(return_value={
        "node1": {"role": "master", "slots": [0, 5460]},
        "node2": {"role": "master", "slots": [5461, 10922]},
        "node3": {"role": "master", "slots": [10923, 16383]}
    })
    mock.close = AsyncMock()
    return mock


@pytest.fixture
async def redis_client(mock_redis_cluster):
    """Create RedisClient with mocked cluster connection"""
    with patch('src.cache.redis_client.RedisCluster', return_value=mock_redis_cluster):
        client = RedisClient()
        client.redis = mock_redis_cluster
        yield client
        # Cleanup
        if client.redis:
            await client.close()


class TestCircuitBreaker:
    """Test circuit breaker functionality"""

    def test_initial_state(self):
        """Circuit breaker should start in CLOSED state"""
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=10)
        assert cb.state == "CLOSED"
        assert cb.failure_count == 0

    def test_record_failure(self):
        """Circuit breaker should track failures"""
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=10)

        cb.record_failure()
        assert cb.failure_count == 1
        assert cb.state == "CLOSED"

        cb.record_failure()
        assert cb.failure_count == 2
        assert cb.state == "CLOSED"

        cb.record_failure()
        assert cb.failure_count == 3
        assert cb.state == "OPEN"

    def test_reset(self):
        """Circuit breaker should reset to CLOSED state"""
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=10)
        cb.failure_count = 2
        cb.state = "HALF_OPEN"

        cb.reset()
        assert cb.failure_count == 0
        assert cb.state == "CLOSED"
        assert cb.last_failure_time is None

    @pytest.mark.asyncio
    async def test_circuit_breaker_decorator(self):
        """Test circuit breaker as decorator"""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)

        @cb
        async def failing_operation():
            raise ConnectionError("Test error")

        @cb
        async def success_operation():
            return "success"

        # First failure
        with pytest.raises(ConnectionError):
            await failing_operation()
        assert cb.failure_count == 1

        # Second failure - should open circuit
        with pytest.raises(ConnectionError):
            await failing_operation()
        assert cb.state == "OPEN"

        # Circuit is open - should raise CircuitBreakerError
        with pytest.raises(CircuitBreakerError):
            await success_operation()

        # Wait for recovery timeout
        await asyncio.sleep(0.15)

        # Should be in HALF_OPEN state, successful operation should reset
        result = await success_operation()
        assert result == "success"
        assert cb.state == "CLOSED"


class TestRedisClient:
    """Test RedisClient operations"""

    @pytest.mark.asyncio
    async def test_get_cache_hit(self, redis_client, mock_redis_cluster):
        """Test successful cache get (hit)"""
        test_value = {"key": "value", "nested": {"data": 123}}
        mock_redis_cluster.get.return_value = json.dumps(test_value)

        result = await redis_client.get("test_key", "test_intent")

        assert result == test_value
        assert redis_client.hit_count == 1
        assert redis_client.miss_count == 0
        mock_redis_cluster.get.assert_called_once_with("test_key")

    @pytest.mark.asyncio
    async def test_get_cache_miss(self, redis_client, mock_redis_cluster):
        """Test cache get when key doesn't exist (miss)"""
        mock_redis_cluster.get.return_value = None

        result = await redis_client.get("missing_key", "test_intent")

        assert result is None
        assert redis_client.hit_count == 0
        assert redis_client.miss_count == 1
        mock_redis_cluster.get.assert_called_once_with("missing_key")

    @pytest.mark.asyncio
    async def test_get_with_plain_string(self, redis_client, mock_redis_cluster):
        """Test get with plain string value (not JSON)"""
        mock_redis_cluster.get.return_value = "plain_string_value"

        result = await redis_client.get("string_key", "test_intent")

        assert result == "plain_string_value"
        assert redis_client.hit_count == 1

    @pytest.mark.asyncio
    async def test_set_with_json_serialization(self, redis_client, mock_redis_cluster):
        """Test set with automatic JSON serialization"""
        test_value = {"key": "value", "number": 42}

        result = await redis_client.set("test_key", test_value, ttl=3600, intent_type="test")

        assert result is True
        expected_json = json.dumps(test_value, ensure_ascii=False)
        mock_redis_cluster.setex.assert_called_once_with("test_key", 3600, expected_json)

    @pytest.mark.asyncio
    async def test_set_with_default_ttl(self, redis_client, mock_redis_cluster):
        """Test set uses default TTL when not specified"""
        redis_client.settings.redis_default_ttl = 300

        result = await redis_client.set("test_key", "test_value", intent_type="test")

        assert result is True
        mock_redis_cluster.setex.assert_called_once_with("test_key", 300, "test_value")

    @pytest.mark.asyncio
    async def test_delete(self, redis_client, mock_redis_cluster):
        """Test delete operation"""
        mock_redis_cluster.delete.return_value = 1

        result = await redis_client.delete("test_key", "test_intent")

        assert result is True
        mock_redis_cluster.delete.assert_called_once_with("test_key")

    @pytest.mark.asyncio
    async def test_delete_non_existent(self, redis_client, mock_redis_cluster):
        """Test delete of non-existent key"""
        mock_redis_cluster.delete.return_value = 0

        result = await redis_client.delete("missing_key", "test_intent")

        assert result is False
        mock_redis_cluster.delete.assert_called_once_with("missing_key")

    @pytest.mark.asyncio
    async def test_exists(self, redis_client, mock_redis_cluster):
        """Test exists operation"""
        mock_redis_cluster.exists.return_value = 1

        result = await redis_client.exists("test_key")

        assert result is True
        mock_redis_cluster.exists.assert_called_once_with("test_key")

    @pytest.mark.asyncio
    async def test_exists_missing_key(self, redis_client, mock_redis_cluster):
        """Test exists for missing key"""
        mock_redis_cluster.exists.return_value = 0

        result = await redis_client.exists("missing_key")

        assert result is False

    @pytest.mark.asyncio
    async def test_pipeline_single_slot(self, redis_client, mock_redis_cluster):
        """Test pipeline with all operations in same slot"""
        # Mock keyslot to return same slot for all keys
        mock_redis_cluster.keyslot.return_value = 12345

        # Mock pipeline
        mock_pipe = AsyncMock()
        mock_pipe.execute = AsyncMock(return_value=["value1", True, 1])
        mock_redis_cluster.pipeline.return_value = mock_pipe

        operations = [
            {"method": "get", "args": ["key1"]},
            {"method": "set", "args": ["key2", "value2"]},
            {"method": "delete", "args": ["key3"]}
        ]

        results = await redis_client.pipeline_operations(operations)

        assert results == ["value1", True, 1]
        assert mock_redis_cluster.keyslot.call_count == 3
        mock_redis_cluster.pipeline.assert_called_once()
        mock_pipe.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_pipeline_multi_slot(self, redis_client, mock_redis_cluster):
        """Test pipeline with operations across different slots"""
        # Mock keyslot to return different slots
        mock_redis_cluster.keyslot.side_effect = [100, 200, 100]  # key1 and key3 in slot 100, key2 in slot 200

        # Create separate mock pipelines for each slot
        mock_pipe1 = AsyncMock()
        mock_pipe1.execute = AsyncMock(return_value=["value1", 1])  # Results for slot 100

        mock_pipe2 = AsyncMock()
        mock_pipe2.execute = AsyncMock(return_value=[True])  # Result for slot 200

        mock_redis_cluster.pipeline.side_effect = [mock_pipe1, mock_pipe2]

        operations = [
            {"method": "get", "args": ["key1"]},  # slot 100
            {"method": "set", "args": ["key2", "value2"]},  # slot 200
            {"method": "delete", "args": ["key3"]}  # slot 100
        ]

        results = await redis_client.pipeline_operations(operations)

        # Results should be in original order
        assert results == ["value1", True, 1]
        assert mock_redis_cluster.keyslot.call_count == 3
        assert mock_redis_cluster.pipeline.call_count == 2

    @pytest.mark.asyncio
    async def test_pipeline_with_keyless_operations(self, redis_client, mock_redis_cluster):
        """Test pipeline with keyless operations like PING"""
        mock_redis_cluster.keyslot.return_value = 12345

        # Create mock pipelines
        mock_pipe_keyed = AsyncMock()
        mock_pipe_keyed.execute = AsyncMock(return_value=["value1", True])

        mock_pipe_keyless = AsyncMock()
        mock_pipe_keyless.execute = AsyncMock(return_value=["PONG"])

        mock_redis_cluster.pipeline.side_effect = [mock_pipe_keyed, mock_pipe_keyless]

        operations = [
            {"method": "get", "args": ["key1"]},
            {"method": "ping", "args": []},  # Keyless operation
            {"method": "set", "args": ["key2", "value2"]}
        ]

        results = await redis_client.pipeline_operations(operations)

        # Results should maintain order
        assert results == ["value1", "PONG", True]
        assert mock_redis_cluster.pipeline.call_count == 2

    @pytest.mark.asyncio
    async def test_pipeline_error_handling(self, redis_client, mock_redis_cluster):
        """Test pipeline error handling"""
        mock_redis_cluster.keyslot.return_value = 12345

        mock_pipe = AsyncMock()
        mock_pipe.execute = AsyncMock(side_effect=RedisClusterException("CROSSSLOT error"))
        mock_redis_cluster.pipeline.return_value = mock_pipe

        operations = [
            {"method": "get", "args": ["key1"]},
            {"method": "set", "args": ["key2", "value2"]}
        ]

        results = await redis_client.pipeline_operations(operations)

        assert results == []  # Should return empty list on error

    @pytest.mark.asyncio
    async def test_circuit_breaker_integration(self, redis_client, mock_redis_cluster):
        """Test circuit breaker integration with Redis operations"""
        # Make operations fail to trigger circuit breaker
        mock_redis_cluster.get.side_effect = ConnectionError("Connection failed")

        # First few failures should work normally
        for i in range(redis_client.circuit_breaker.failure_threshold):
            result = await redis_client.get(f"key{i}")
            assert result is None

        # Circuit should now be open
        assert redis_client.circuit_breaker.state == "OPEN"

    @pytest.mark.asyncio
    async def test_get_cache_stats(self, redis_client, mock_redis_cluster):
        """Test cache statistics retrieval"""
        redis_client.hit_count = 10
        redis_client.miss_count = 5
        redis_client.circuit_breaker.state = "CLOSED"

        stats = await redis_client.get_cache_stats()

        assert stats["hits"] == 10
        assert stats["misses"] == 5
        assert stats["hit_ratio"] == 10 / 15
        assert stats["circuit_breaker_state"] == "CLOSED"
        assert stats["connected"] is True
        assert len(stats["cluster_nodes"]) == 3

    @pytest.mark.asyncio
    async def test_acquire_lock(self, redis_client, mock_redis_cluster):
        """Test distributed lock acquisition"""
        mock_redis_cluster.set.return_value = True
        mock_redis_cluster.delete.return_value = 1

        async with redis_client.acquire_lock("test_lock", timeout=10):
            # Lock acquired
            mock_redis_cluster.set.assert_called_with(
                "test_lock", "locked", nx=True, ex=10
            )

        # Lock released
        mock_redis_cluster.delete.assert_called_with("test_lock")

    @pytest.mark.asyncio
    async def test_acquire_lock_already_held(self, redis_client, mock_redis_cluster):
        """Test lock acquisition when already held"""
        # First attempt fails, subsequent attempts succeed
        mock_redis_cluster.set.side_effect = [False, False, True]

        async with redis_client.acquire_lock("test_lock", timeout=10, wait_timeout=2):
            pass  # Should eventually acquire after retries

        assert mock_redis_cluster.set.call_count >= 2

    @pytest.mark.asyncio
    async def test_acquire_lock_timeout(self, redis_client, mock_redis_cluster):
        """Test lock acquisition timeout"""
        mock_redis_cluster.set.return_value = False  # Lock never available

        with pytest.raises(TimeoutError):
            async with redis_client.acquire_lock("test_lock", timeout=10, wait_timeout=1):
                pass

    @pytest.mark.asyncio
    async def test_extract_key(self, redis_client):
        """Test key extraction from operation arguments"""
        # Test with positional argument
        key = redis_client._extract_key(("test_key",), {})
        assert key == "test_key"

        # Test with keyword argument 'key'
        key = redis_client._extract_key((), {"key": "test_key2"})
        assert key == "test_key2"

        # Test with keyword argument 'name'
        key = redis_client._extract_key((), {"name": "test_key3"})
        assert key == "test_key3"

        # Test with no key
        key = redis_client._extract_key((), {})
        assert key is None

        # Test with non-string first argument
        key = redis_client._extract_key((123,), {})
        assert key is None


class TestRedisClientSingleton:
    """Test singleton pattern for Redis client"""

    @pytest.mark.asyncio
    async def test_get_redis_client_singleton(self):
        """Test that get_redis_client returns the same instance"""
        with patch('src.cache.redis_client.RedisClient') as MockRedisClient:
            mock_instance = Mock()
            mock_instance.initialize = AsyncMock()
            MockRedisClient.return_value = mock_instance

            # Reset global client
            import src.cache.redis_client
            src.cache.redis_client._redis_client = None

            client1 = await get_redis_client()
            client2 = await get_redis_client()

            assert client1 is client2
            MockRedisClient.assert_called_once()
            mock_instance.initialize.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_redis_client(self):
        """Test closing the global Redis client"""
        with patch('src.cache.redis_client.RedisClient') as MockRedisClient:
            mock_instance = Mock()
            mock_instance.initialize = AsyncMock()
            mock_instance.close = AsyncMock()
            MockRedisClient.return_value = mock_instance

            # Reset and create client
            import src.cache.redis_client
            src.cache.redis_client._redis_client = None

            client = await get_redis_client()
            await close_redis_client()

            mock_instance.close.assert_called_once()
            assert src.cache.redis_client._redis_client is None


@pytest.mark.asyncio
async def test_initialization_with_settings(monkeypatch):
    """Test Redis client initialization with settings"""
    from src.config.settings import Settings

    mock_settings = Mock(spec=Settings)
    mock_settings.redis_cluster_nodes = "localhost:7000,localhost:7001,localhost:7002"
    mock_settings.redis_password = "test_password"
    mock_settings.redis_ca_cert_path = None
    mock_settings.redis_max_connections = 100
    mock_settings.redis_timeout = 5000
    mock_settings.redis_default_ttl = 300

    with patch('src.cache.redis_client.get_settings', return_value=mock_settings):
        with patch('src.cache.redis_client.RedisCluster') as MockRedisCluster:
            mock_cluster = AsyncMock()
            mock_cluster.ping = AsyncMock(return_value=True)
            MockRedisCluster.return_value = mock_cluster

            client = RedisClient()
            await client.initialize()

            MockRedisCluster.assert_called_once()
            call_kwargs = MockRedisCluster.call_args[1]

            assert len(call_kwargs["startup_nodes"]) == 3
            assert call_kwargs["password"] == "test_password"
            assert call_kwargs["max_connections_per_node"] == 100 // 3
            assert call_kwargs["socket_timeout"] == 5.0
            assert call_kwargs["decode_responses"] is True
            assert call_kwargs["skip_full_coverage_check"] is False


@pytest.mark.asyncio
async def test_initialization_with_ssl(monkeypatch):
    """Test Redis client initialization with SSL"""
    from src.config.settings import Settings

    mock_settings = Mock(spec=Settings)
    mock_settings.redis_cluster_nodes = "localhost:7000"
    mock_settings.redis_password = "test_password"
    mock_settings.redis_ca_cert_path = "/path/to/ca.crt"
    mock_settings.redis_max_connections = 100
    mock_settings.redis_timeout = 5000
    mock_settings.redis_default_ttl = 300

    with patch('src.cache.redis_client.get_settings', return_value=mock_settings):
        with patch('src.cache.redis_client.ssl.create_default_context') as mock_ssl:
            mock_ssl_context = Mock()
            mock_ssl.return_value = mock_ssl_context

            with patch('src.cache.redis_client.RedisCluster') as MockRedisCluster:
                mock_cluster = AsyncMock()
                mock_cluster.ping = AsyncMock(return_value=True)
                MockRedisCluster.return_value = mock_cluster

                client = RedisClient()
                await client.initialize()

                mock_ssl.assert_called_once_with(cafile="/path/to/ca.crt")
                MockRedisCluster.assert_called_once()
                call_kwargs = MockRedisCluster.call_args[1]
                assert call_kwargs["ssl"] is True
                assert call_kwargs["ssl_ca_certs"] == "/path/to/ca.crt"