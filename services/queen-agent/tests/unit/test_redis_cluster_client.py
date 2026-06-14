"""
TR-1 — Queen Agent Redis Cluster Client

Testes unitários para a migração do RedisClient de modo standalone
(`redis.asyncio.Redis`) para cluster (`redis.asyncio.cluster.RedisCluster`).

Spec: `.agent-os/specs/2026-05-22-pipeline-flow-recovery/` (TR-1).

Background:
- Cliente standalone fazia `Redis(host=nodes[0])` → apenas conectado
  ao primeiro nó. Operações cujo hash slot caísse fora desse nó
  recebiam `CLUSTERDOWN Hash slot not served`.
- Cluster Redis tem 16384 slots distribuídos por 3 master nodes
  (10.244.2.73, 10.244.3.214, 10.244.2.243).
- O cliente cluster trata automaticamente os redirects `MOVED` e
  `ASK` no transporte; estes testes verificam que a configuração do
  cliente os habilita (`require_full_coverage=False`,
  `reinitialize_steps`).
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Garantir que src/ está no PYTHONPATH (mesma estratégia do conftest do repo).
# Path: tests/unit/test_redis_cluster_client.py -> parent x3 = queen-agent/
SRC = Path(__file__).resolve().parent.parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _settings(
    nodes: str = "redis-0.local:6379,redis-1.local:6379,redis-2.local:6379",
    password: str = "",
    ssl: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        REDIS_CLUSTER_NODES=nodes,
        REDIS_PASSWORD=password,
        REDIS_SSL_ENABLED=ssl,
    )


@pytest.fixture()
def cluster_patch():
    """Patch RedisCluster + ClusterNode no módulo do client."""
    with patch("src.clients.redis_client.RedisCluster") as mock_cluster, patch(
        "src.clients.redis_client.ClusterNode"
    ) as mock_node:
        instance = MagicMock()
        instance.ping = AsyncMock(return_value=True)
        instance.aclose = AsyncMock()
        instance.setex = AsyncMock()
        instance.get = AsyncMock()
        instance.set = AsyncMock()
        instance.delete = AsyncMock()
        instance.incr = AsyncMock()
        instance.keys = AsyncMock(return_value=[])
        mock_cluster.return_value = instance
        # ClusterNode é só um construtor, devolve um sentinel.
        mock_node.side_effect = lambda host, port: f"node:{host}:{port}"
        yield mock_cluster, mock_node, instance


@pytest.mark.asyncio()
async def test_initialize_uses_cluster_client_with_all_nodes(cluster_patch):
    """RedisCluster recebe TODOS os nodes parseados (não só o primeiro)."""
    mock_cluster, mock_node, _ = cluster_patch
    from src.clients.redis_client import RedisClient

    client = RedisClient(_settings())
    await client.initialize()

    assert mock_node.call_count == 3, "Deveria parsear 3 nodes do cluster"
    mock_node.assert_any_call(host="redis-0.local", port=6379)
    mock_node.assert_any_call(host="redis-1.local", port=6379)
    mock_node.assert_any_call(host="redis-2.local", port=6379)

    mock_cluster.assert_called_once()
    kwargs = mock_cluster.call_args.kwargs
    assert "startup_nodes" in kwargs, "RedisCluster precisa de startup_nodes"
    assert len(kwargs["startup_nodes"]) == 3


@pytest.mark.asyncio()
async def test_initialize_defaults_port_when_missing(cluster_patch):
    """Node sem `:porto` assume 6379 (default Redis)."""
    _, mock_node, _ = cluster_patch
    from src.clients.redis_client import RedisClient

    client = RedisClient(_settings(nodes="redis-only-host"))
    await client.initialize()

    mock_node.assert_called_once_with(host="redis-only-host", port=6379)


@pytest.mark.asyncio()
async def test_initialize_empty_password_passed_as_none(cluster_patch):
    """REDIS_PASSWORD='' deve ser passado como None — evita auth handshake."""
    mock_cluster, _, _ = cluster_patch
    from src.clients.redis_client import RedisClient

    client = RedisClient(_settings(password=""))
    await client.initialize()

    assert mock_cluster.call_args.kwargs.get("password") is None


@pytest.mark.asyncio()
async def test_initialize_non_empty_password_passed_through(cluster_patch):
    """Password não-vazio é propagado tal-qual."""
    mock_cluster, _, _ = cluster_patch
    from src.clients.redis_client import RedisClient

    client = RedisClient(_settings(password="hunter2"))
    await client.initialize()

    assert mock_cluster.call_args.kwargs.get("password") == "hunter2"


@pytest.mark.asyncio()
async def test_initialize_ssl_flag_propagated(cluster_patch):
    """REDIS_SSL_ENABLED é propagado para o cliente."""
    mock_cluster, _, _ = cluster_patch
    from src.clients.redis_client import RedisClient

    client = RedisClient(_settings(ssl=True))
    await client.initialize()

    assert mock_cluster.call_args.kwargs.get("ssl") is True


@pytest.mark.asyncio()
async def test_initialize_tolerates_partial_slot_coverage(cluster_patch):
    """`require_full_coverage=False` — sobrevive a re-shard parcial."""
    mock_cluster, _, _ = cluster_patch
    from src.clients.redis_client import RedisClient

    client = RedisClient(_settings())
    await client.initialize()

    assert mock_cluster.call_args.kwargs.get("require_full_coverage") is False


@pytest.mark.asyncio()
async def test_initialize_sets_reinitialize_steps(cluster_patch):
    """`reinitialize_steps` controla com que frequência a topology é
    recarregada após MOVED/ASK. Esperado >= 1."""
    mock_cluster, _, _ = cluster_patch
    from src.clients.redis_client import RedisClient

    client = RedisClient(_settings())
    await client.initialize()

    reinit = mock_cluster.call_args.kwargs.get("reinitialize_steps")
    assert reinit is not None
    assert reinit >= 1


@pytest.mark.asyncio()
async def test_initialize_decode_responses_true(cluster_patch):
    """decode_responses=True — caller espera str, não bytes."""
    mock_cluster, _, _ = cluster_patch
    from src.clients.redis_client import RedisClient

    client = RedisClient(_settings())
    await client.initialize()

    assert mock_cluster.call_args.kwargs.get("decode_responses") is True


@pytest.mark.asyncio()
async def test_initialize_pings_after_construction(cluster_patch):
    """Falha de conectividade deve ser detectada na inicialização."""
    _, _, instance = cluster_patch
    from src.clients.redis_client import RedisClient

    client = RedisClient(_settings())
    await client.initialize()

    instance.ping.assert_awaited_once()


@pytest.mark.asyncio()
async def test_initialize_raises_on_clusterdown(cluster_patch):
    """`CLUSTERDOWN` na inicialização é propagado (não silenciado)."""
    _, _, instance = cluster_patch
    instance.ping.side_effect = RuntimeError("CLUSTERDOWN Hash slot not served")
    from src.clients.redis_client import RedisClient

    client = RedisClient(_settings())
    with pytest.raises(RuntimeError, match="CLUSTERDOWN"):
        await client.initialize()


@pytest.mark.asyncio()
async def test_cache_strategic_context_uses_setex(cluster_patch):
    """cache_strategic_context delega em setex (compatível com cluster)."""
    _, _, instance = cluster_patch
    from src.clients.redis_client import RedisClient

    client = RedisClient(_settings())
    await client.initialize()
    await client.cache_strategic_context("ctx:abc", {"foo": "bar"}, 300)

    instance.setex.assert_awaited_once()
    args = instance.setex.await_args.args
    assert args[0] == "ctx:abc"
    assert args[1] == 300
    assert '"foo": "bar"' in args[2]


@pytest.mark.asyncio()
async def test_get_cached_context_returns_parsed_json(cluster_patch):
    """get_cached_context faz json.loads do valor retornado pelo cluster."""
    _, _, instance = cluster_patch
    instance.get.return_value = '{"foo": "bar"}'
    from src.clients.redis_client import RedisClient

    client = RedisClient(_settings())
    await client.initialize()
    result = await client.get_cached_context("ctx:abc")

    assert result == {"foo": "bar"}


@pytest.mark.asyncio()
async def test_get_cached_context_returns_none_when_missing(cluster_patch):
    """get_cached_context retorna None se chave não existir."""
    _, _, instance = cluster_patch
    instance.get.return_value = None
    from src.clients.redis_client import RedisClient

    client = RedisClient(_settings())
    await client.initialize()
    result = await client.get_cached_context("ctx:missing")

    assert result is None


@pytest.mark.asyncio()
async def test_get_cached_context_swallows_errors(cluster_patch):
    """Erros no get NÃO propagam — retorna None (resiliência cache)."""
    _, _, instance = cluster_patch
    instance.get.side_effect = RuntimeError("MOVED 12345 10.0.0.1:6379")
    from src.clients.redis_client import RedisClient

    client = RedisClient(_settings())
    await client.initialize()
    result = await client.get_cached_context("ctx:redirected")

    # No cluster client, MOVED é tratado internamente; mas se chegasse
    # cá, o método deveria continuar a engolir para não bloquear o
    # caller. A política actual é "log_and_continue".
    assert result is None


@pytest.mark.asyncio()
async def test_set_decision_lock_uses_nx_and_ex(cluster_patch):
    """Lock distribuído usa SET NX EX (atómico, single-key)."""
    _, _, instance = cluster_patch
    instance.set.return_value = True
    from src.clients.redis_client import RedisClient

    client = RedisClient(_settings())
    await client.initialize()
    ok = await client.set_decision_lock("scale-out", 60)

    assert ok is True
    instance.set.assert_awaited_once()
    kwargs = instance.set.await_args.kwargs
    assert kwargs.get("nx") is True
    assert kwargs.get("ex") == 60


@pytest.mark.asyncio()
async def test_set_decision_lock_returns_false_when_already_held(cluster_patch):
    """Lock já existente: set retorna None → caller vê False."""
    _, _, instance = cluster_patch
    instance.set.return_value = None
    from src.clients.redis_client import RedisClient

    client = RedisClient(_settings())
    await client.initialize()
    ok = await client.set_decision_lock("scale-out", 60)

    assert ok is False


@pytest.mark.asyncio()
async def test_release_decision_lock_deletes_key(cluster_patch):
    """release_decision_lock chama DELETE na chave do lock."""
    _, _, instance = cluster_patch
    from src.clients.redis_client import RedisClient

    client = RedisClient(_settings())
    await client.initialize()
    await client.release_decision_lock("scale-out")

    instance.delete.assert_awaited_once_with("decision:lock:scale-out")


@pytest.mark.asyncio()
async def test_increment_decision_counter_uses_incr(cluster_patch):
    """increment_decision_counter chama INCR (atómico, single-key)."""
    _, _, instance = cluster_patch
    instance.incr.return_value = 42
    from src.clients.redis_client import RedisClient

    client = RedisClient(_settings())
    await client.initialize()
    n = await client.increment_decision_counter("scale-out")

    assert n == 42
    instance.incr.assert_awaited_once_with("decision:counter:scale-out")


@pytest.mark.asyncio()
async def test_get_decision_stats_uses_keys_fanout(cluster_patch):
    """get_decision_stats faz KEYS + GET — em cluster, KEYS faz fan-out
    a todos os masters automaticamente via RedisCluster."""
    _, _, instance = cluster_patch
    instance.keys.return_value = [
        "decision:counter:scale-out",
        "decision:counter:scale-in",
    ]
    # `get` é chamado uma vez por chave; configurar side_effect cíclico.
    instance.get.side_effect = ["10", "3"]
    from src.clients.redis_client import RedisClient

    client = RedisClient(_settings())
    await client.initialize()
    stats = await client.get_decision_stats()

    assert stats == {"scale-out": 10, "scale-in": 3}
    instance.keys.assert_awaited_once_with("decision:counter:*")


@pytest.mark.asyncio()
async def test_close_releases_cluster_connection(cluster_patch):
    """close() invoca aclose() do cluster client (libera connection pool).

    TR-1: RedisCluster.close() está deprecated desde redis-py 5.0; o
    wrapper RedisClient.close() delega em aclose() para evitar
    DeprecationWarning.
    """
    _, _, instance = cluster_patch
    from src.clients.redis_client import RedisClient

    client = RedisClient(_settings())
    await client.initialize()
    await client.close()

    instance.aclose.assert_awaited_once()
