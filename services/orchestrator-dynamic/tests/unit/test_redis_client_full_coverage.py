"""Teste unitário para FIX-3 (I2): RedisCluster com require_full_coverage=False.

Em cluster com cobertura parcial de slots, lookups workflow:by:ticket:* falhavam
com RedisClusterException. O fix adiciona require_full_coverage=False à
instanciação do RedisCluster (alinhado com o service-registry).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
import src.clients.redis_client as redis_client_module
from src.clients.redis_client import get_redis_client


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Garante singleton limpo entre testes."""
    redis_client_module._redis_client_instance = None
    redis_client_module._circuit_breaker = None
    yield
    redis_client_module._redis_client_instance = None
    redis_client_module._circuit_breaker = None


def _build_config():
    config = MagicMock()
    config.redis_cluster_nodes = "redis-host:6379"
    config.redis_password = "secret"
    config.redis_ssl_enabled = False
    config.service_name = "orchestrator-dynamic"
    config.REDIS_CIRCUIT_BREAKER_ENABLED = False
    return config


@pytest.mark.asyncio()
async def test_redis_cluster_instantiated_with_require_full_coverage(monkeypatch):
    captured_kwargs = {}

    def _fake_cluster(*_args, **kwargs):
        captured_kwargs.update(kwargs)
        instance = MagicMock()
        instance.ping = AsyncMock(return_value=True)
        return instance

    monkeypatch.setattr(redis_client_module.redis, "RedisCluster", _fake_cluster)

    client = await get_redis_client(config=_build_config())

    assert client is not None
    # FIX-3: o parâmetro chave que tolera cobertura parcial de slots.
    assert captured_kwargs.get("require_full_coverage") is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
