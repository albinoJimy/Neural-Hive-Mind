"""
Integration tests for Redis Cluster
Test real Redis Cluster operations with testcontainers
"""

import asyncio
import json
import pytest
import time
from typing import Dict, Any

# Skip tests if dependencies not available
pytest_plugins = []

try:
    from testcontainers.redis import RedisContainer
    TESTCONTAINERS_AVAILABLE = True
except ImportError:
    TESTCONTAINERS_AVAILABLE = False

from src.cache.redis_client import RedisClient, CircuitBreakerError
from src.config.settings import get_settings


@pytest.mark.skipif(not TESTCONTAINERS_AVAILABLE, reason="testcontainers not available")
@pytest.mark.integration
class TestRedisClusterIntegration:
    """Integration tests with real Redis cluster"""

    @pytest.fixture(scope="class")
    async def redis_cluster_container(self):
        """Start Redis cluster container for testing"""
        # Note: For a real cluster test, we'd need multiple Redis nodes
        # This is a simplified single-node test
        with RedisContainer("redis:7-alpine") as redis:
            redis.with_command("redis-server --port 7000 --cluster-enabled yes --cluster-config-file nodes.conf --cluster-node-timeout 5000 --appendonly yes")
            yield redis

    @pytest.fixture(scope="class")
    async def redis_client_integration(self, redis_cluster_container):
        """Create Redis client connected to test cluster"""
        # Mock settings for integration test
        import os
        from unittest.mock import patch, Mock

        test_settings = Mock()
        test_settings.redis_cluster_nodes = f"localhost:{redis_cluster_container.get_exposed_port(7000)}"
        test_settings.redis_password = None
        test_settings.redis_ca_cert_path = None
        test_settings.redis_max_connections = 10
        test_settings.redis_timeout = 5000
        test_settings.redis_default_ttl = 300

        with patch('src.cache.redis_client.get_settings', return_value=test_settings):
            client = RedisClient()
            await client.initialize()
            yield client
            await client.close()

    @pytest.mark.asyncio
    async def test_basic_operations(self, redis_client_integration):
        """Test basic Redis operations"""
        client = redis_client_integration

        # Test set and get
        result = await client.set("test_key", "test_value", ttl=60)
        assert result is True

        value = await client.get("test_key")
        assert value == "test_value"

        # Test exists
        exists = await client.exists("test_key")
        assert exists is True

        # Test delete
        deleted = await client.delete("test_key")
        assert deleted is True

        # Verify deletion
        value = await client.get("test_key")
        assert value is None

        exists = await client.exists("test_key")
        assert exists is False

    @pytest.mark.asyncio
    async def test_json_serialization(self, redis_client_integration):
        """Test JSON serialization and deserialization"""
        client = redis_client_integration

        test_data = {
            "string": "value",
            "number": 42,
            "boolean": True,
            "null": None,
            "array": [1, 2, 3],
            "nested": {"key": "value"}
        }

        # Store complex object
        result = await client.set("json_key", test_data, ttl=60)
        assert result is True

        # Retrieve and verify
        retrieved = await client.get("json_key")
        assert retrieved == test_data

    @pytest.mark.asyncio
    async def test_ttl_expiration(self, redis_client_integration):
        """Test TTL expiration"""
        client = redis_client_integration

        # Set key with short TTL
        result = await client.set("ttl_key", "ttl_value", ttl=1)
        assert result is True

        # Verify key exists
        value = await client.get("ttl_key")
        assert value == "ttl_value"

        # Wait for expiration
        await asyncio.sleep(1.5)

        # Verify key expired
        value = await client.get("ttl_key")
        assert value is None

    @pytest.mark.asyncio
    async def test_pipeline_single_slot(self, redis_client_integration):
        """Test pipeline operations on same hash slot"""
        client = redis_client_integration

        # Use keys with same hash tag to ensure same slot
        operations = [
            {"method": "set", "args": ["{user:123}:name", "John"], "kwargs": {"ex": 60}},
            {"method": "set", "args": ["{user:123}:email", "john@example.com"], "kwargs": {"ex": 60}},
            {"method": "get", "args": ["{user:123}:name"]},
            {"method": "get", "args": ["{user:123}:email"]},
            {"method": "exists", "args": ["{user:123}:name"]},
            {"method": "delete", "args": ["{user:123}:email"]}
        ]

        results = await client.pipeline_operations(operations)

        assert len(results) == 6
        assert results[0] is True  # set name
        assert results[1] is True  # set email
        assert results[2] == "John"  # get name
        assert results[3] == "john@example.com"  # get email
        assert results[4] == 1  # exists name
        assert results[5] == 1  # delete email

        # Verify final state
        name_exists = await client.exists("{user:123}:name")
        email_exists = await client.exists("{user:123}:email")
        assert name_exists is True
        assert email_exists is False

    @pytest.mark.asyncio
    async def test_pipeline_mixed_operations(self, redis_client_integration):
        """Test pipeline with mixed operations"""
        client = redis_client_integration

        # Setup test data
        await client.set("pipeline_test_1", "value1", ttl=60)
        await client.set("pipeline_test_2", {"nested": "object"}, ttl=60)

        operations = [
            {"method": "get", "args": ["pipeline_test_1"]},
            {"method": "get", "args": ["pipeline_test_2"]},
            {"method": "set", "args": ["pipeline_test_3", "value3"], "kwargs": {"ex": 60}},
            {"method": "exists", "args": ["pipeline_test_1"]},
            {"method": "exists", "args": ["nonexistent_key"]}
        ]

        results = await client.pipeline_operations(operations)

        assert len(results) == 5
        assert results[0] == "value1"
        assert results[1] == {"nested": "object"}
        assert results[2] is True  # set result
        assert results[3] == 1  # exists true
        assert results[4] == 0  # exists false

    @pytest.mark.asyncio
    async def test_distributed_lock(self, redis_client_integration):
        """Test distributed lock functionality"""
        client = redis_client_integration

        lock_key = "test_lock"

        # Test successful lock acquisition
        async with client.acquire_lock(lock_key, timeout=10):
            # Verify lock exists
            exists = await client.exists(lock_key)
            assert exists is True

        # Verify lock released
        exists = await client.exists(lock_key)
        assert exists is False

    @pytest.mark.asyncio
    async def test_circuit_breaker_recovery(self, redis_client_integration):
        """Test circuit breaker recovery behavior"""
        client = redis_client_integration

        # Reset circuit breaker
        client.circuit_breaker.reset()

        # Force circuit breaker to open by triggering failures
        original_redis = client.redis
        client.redis = None  # This will cause failures

        # Trigger enough failures to open circuit
        for i in range(client.circuit_breaker.failure_threshold):
            result = await client.get(f"test_key_{i}")
            assert result is None

        assert client.circuit_breaker.state == "OPEN"

        # Restore connection
        client.redis = original_redis

        # Wait for recovery timeout with a short time
        client.circuit_breaker.recovery_timeout = 0.1
        await asyncio.sleep(0.15)

        # Next operation should work and reset circuit breaker
        result = await client.set("recovery_test", "success", ttl=60)
        assert result is True
        assert client.circuit_breaker.state == "CLOSED"

    @pytest.mark.asyncio
    async def test_cache_statistics(self, redis_client_integration):
        """Test cache statistics tracking"""
        client = redis_client_integration

        # Reset counters
        client.hit_count = 0
        client.miss_count = 0

        # Generate some hits and misses
        await client.get("nonexistent1")  # miss
        await client.get("nonexistent2")  # miss

        await client.set("hit_test", "value", ttl=60)
        await client.get("hit_test")  # hit
        await client.get("hit_test")  # hit

        await client.get("nonexistent3")  # miss

        # Check statistics
        stats = await client.get_cache_stats()

        assert stats["hits"] == 2
        assert stats["misses"] == 3
        assert stats["hit_ratio"] == 2 / 5
        assert stats["connected"] is True

    @pytest.mark.asyncio
    async def test_error_handling(self, redis_client_integration):
        """Test error handling for invalid operations"""
        client = redis_client_integration

        # Test pipeline with invalid operation should not crash
        operations = [
            {"method": "get", "args": ["valid_key"]},
            {"method": "invalid_operation", "args": ["test"]},  # This should fail
            {"method": "set", "args": ["another_key", "value"], "kwargs": {"ex": 60}}
        ]

        # The pipeline should handle errors gracefully
        try:
            results = await client.pipeline_operations(operations)
            # If it doesn't raise an exception, check that some operations succeeded
            assert isinstance(results, list)
        except Exception as e:
            # It's acceptable for this to raise an exception
            assert "invalid_operation" in str(e).lower() or "unknown" in str(e).lower()

    @pytest.mark.asyncio
    async def test_concurrent_operations(self, redis_client_integration):
        """Test concurrent Redis operations"""
        client = redis_client_integration

        async def worker(worker_id: int):
            """Worker function for concurrent testing"""
            results = []
            for i in range(10):
                key = f"worker_{worker_id}_key_{i}"
                value = f"worker_{worker_id}_value_{i}"

                await client.set(key, value, ttl=120)
                retrieved = await client.get(key)
                results.append(retrieved == value)

            return all(results)

        # Run multiple workers concurrently
        workers = [worker(i) for i in range(5)]
        results = await asyncio.gather(*workers)

        # All workers should succeed
        assert all(results)

    @pytest.mark.asyncio
    async def test_large_data_handling(self, redis_client_integration):
        """Test handling of large data objects"""
        client = redis_client_integration

        # Create a large object
        large_object = {
            "data": ["item_" + str(i) for i in range(1000)],
            "metadata": {f"key_{i}": f"value_{i}" for i in range(100)},
            "description": "This is a test object with a lot of data " * 100
        }

        # Store large object
        result = await client.set("large_object", large_object, ttl=120)
        assert result is True

        # Retrieve and verify
        retrieved = await client.get("large_object")
        assert retrieved == large_object
        assert len(retrieved["data"]) == 1000
        assert len(retrieved["metadata"]) == 100

    @pytest.mark.asyncio
    async def test_key_patterns_and_slots(self, redis_client_integration):
        """Test different key patterns and their hash slot distribution"""
        client = redis_client_integration

        # Test keys with hash tags (should go to same slot)
        hash_tag_keys = [
            "{user:123}:profile",
            "{user:123}:settings",
            "{user:123}:preferences"
        ]

        # Test regular keys (may go to different slots)
        regular_keys = [
            "user:456:profile",
            "user:456:settings",
            "user:456:preferences"
        ]

        # Set all keys
        for key in hash_tag_keys + regular_keys:
            await client.set(key, f"value_for_{key}", ttl=120)

        # Pipeline operations with hash tag keys should work efficiently
        hash_tag_ops = [
            {"method": "get", "args": [key]} for key in hash_tag_keys
        ]

        hash_tag_results = await client.pipeline_operations(hash_tag_ops)
        assert len(hash_tag_results) == 3
        assert all(result.startswith("value_for_") for result in hash_tag_results)

        # Pipeline operations with regular keys should also work
        regular_ops = [
            {"method": "get", "args": [key]} for key in regular_keys
        ]

        regular_results = await client.pipeline_operations(regular_ops)
        assert len(regular_results) == 3
        assert all(result.startswith("value_for_") for result in regular_results)


@pytest.mark.integration
@pytest.mark.skipif(not TESTCONTAINERS_AVAILABLE, reason="testcontainers not available")
class TestRedisFailureScenarios:
    """Test Redis failure scenarios and recovery"""

    @pytest.fixture
    async def redis_client_with_short_timeout(self, redis_cluster_container):
        """Create Redis client with short timeouts for failure testing"""
        from unittest.mock import patch, Mock

        test_settings = Mock()
        test_settings.redis_cluster_nodes = f"localhost:{redis_cluster_container.get_exposed_port(7000)}"
        test_settings.redis_password = None
        test_settings.redis_ca_cert_path = None
        test_settings.redis_max_connections = 10
        test_settings.redis_timeout = 100  # Very short timeout
        test_settings.redis_default_ttl = 300

        with patch('src.cache.redis_client.get_settings', return_value=test_settings):
            client = RedisClient()
            client.circuit_breaker.failure_threshold = 2  # Lower threshold for testing
            client.circuit_breaker.recovery_timeout = 0.5  # Shorter recovery time
            await client.initialize()
            yield client
            await client.close()

    @pytest.mark.asyncio
    async def test_connection_failure_handling(self, redis_client_with_short_timeout):
        """Test handling of connection failures"""
        client = redis_client_with_short_timeout

        # Normal operation should work
        result = await client.set("test_key", "test_value", ttl=60)
        assert result is True

        value = await client.get("test_key")
        assert value == "test_value"

        # Simulate connection issues by breaking the client
        original_redis = client.redis
        client.redis = None

        # Operations should fail gracefully
        result = await client.get("test_key")
        assert result is None

        result = await client.set("another_key", "value", ttl=60)
        assert result is False

        # Restore connection
        client.redis = original_redis

        # Should work again
        result = await client.get("test_key")
        assert result == "test_value"