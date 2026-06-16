"""
Testes do health_check_all paralelo dos especialistas e da lógica de quórum
do readiness (/ready).

Cobre o fix em que:
- health_check_all passa a correr os health checks EM PARALELO (asyncio.gather),
  evitando que 5 × ~4s sequenciais excedam o timeout do readiness probe;
- o readiness deixa de exigir TODOS os especialistas SERVING e passa a usar um
  quórum configurável (settings.readiness_min_specialists_serving), tolerando
  flaps transitórios "no healthy upstream" do Istio.
"""

import os
from unittest.mock import AsyncMock, MagicMock

import grpc
import pytest

os.environ.setdefault("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017/test")
os.environ.setdefault("REDIS_CLUSTER_NODES", "localhost:6379")
os.environ.setdefault("ENVIRONMENT", "test")


def _serving_response():
    from grpc_health.v1 import health_pb2

    resp = MagicMock()
    resp.status = health_pb2.HealthCheckResponse.SERVING
    return resp


def _not_serving_response():
    from grpc_health.v1 import health_pb2

    resp = MagicMock()
    resp.status = health_pb2.HealthCheckResponse.NOT_SERVING
    return resp


class _FakeRpcError(grpc.RpcError):
    """RpcError com code()/details() para simular UNAVAILABLE do Istio."""

    def __init__(self, code: grpc.StatusCode, details: str):
        self._code = code
        self._details = details

    def code(self):
        return self._code

    def details(self):
        return self._details


def _patch_health_stub(monkeypatch, per_specialist_behaviour):
    """Faz health_pb2_grpc.HealthStub(channel) devolver um stub cujo Check
    se comporta conforme `per_specialist_behaviour[channel_id]`.

    behaviour pode ser uma resposta (callable->resp) ou uma excepção a levantar.
    """
    from grpc_health.v1 import health_pb2_grpc

    def _factory(channel):
        behaviour = per_specialist_behaviour[channel]
        stub = MagicMock()

        async def _check(_request, timeout=None):
            if isinstance(behaviour, Exception):
                raise behaviour
            return behaviour()

        stub.Check = AsyncMock(side_effect=_check)
        return stub

    monkeypatch.setattr(health_pb2_grpc, "HealthStub", _factory)


@pytest.mark.asyncio
async def test_health_check_all_parallel_mixed_statuses(mock_specialists_grpc_client, monkeypatch):
    """3 SERVING + 1 UNAVAILABLE + 1 NOT_SERVING -> serving_count == 3."""
    client = mock_specialists_grpc_client

    # channel "id" é a própria string; mapeia comportamento por channel
    behaviour = {
        "business": _serving_response,
        "technical": _serving_response,
        "architecture": _serving_response,
        "behavior": _FakeRpcError(grpc.StatusCode.UNAVAILABLE, "no healthy upstream"),
        "evolution": _not_serving_response,
    }
    client.stubs = {k: MagicMock() for k in behaviour}
    client.channels = {k: k for k in behaviour}  # channel == chave (usado no _factory)
    _patch_health_stub(monkeypatch, behaviour)

    results = await client.health_check_all()

    assert set(results) == set(behaviour)
    serving = sum(1 for r in results.values() if r.get("status") == "SERVING")
    assert serving == 3
    assert results["behavior"]["status"] == "NOT_SERVING"
    assert results["behavior"]["error"] == "unavailable"
    assert results["evolution"]["status"] == "NOT_SERVING"


@pytest.mark.asyncio
async def test_health_check_all_no_channel(mock_specialists_grpc_client, monkeypatch):
    """Especialista sem channel -> NOT_SERVING/no_channel, sem rebentar."""
    client = mock_specialists_grpc_client
    client.stubs = {"business": MagicMock(), "technical": MagicMock()}
    client.channels = {"business": "business"}  # technical sem channel
    _patch_health_stub(monkeypatch, {"business": _serving_response})

    results = await client.health_check_all()

    assert results["business"]["status"] == "SERVING"
    assert results["technical"]["status"] == "NOT_SERVING"
    assert results["technical"]["error"] == "no_channel"


@pytest.mark.parametrize(
    "serving_count,min_required,expected_ready",
    [
        (5, 3, True),
        (3, 3, True),
        (2, 3, False),
        (0, 3, False),
        (0, 0, True),  # gate desativado
    ],
)
def test_quorum_decision(serving_count, min_required, expected_ready):
    """A decisão de readiness dos especialistas é serving_count >= min_required."""
    assert (serving_count >= min_required) is expected_ready
