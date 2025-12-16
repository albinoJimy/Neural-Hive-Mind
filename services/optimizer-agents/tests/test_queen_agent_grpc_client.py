import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import grpc
import pytest

# Stub heavy external deps pulled by src.clients package init
for module_name in [
    "kubernetes",
    "kubernetes.client",
    "kubernetes.config",
    "clickhouse_driver",
    "pymongo",
    "mlflow",
    "mlflow.tracking",
    "mlflow.entities",
    "motor",
    "motor.motor_asyncio",
    "redis",
    "redis.asyncio",
    "redis.asyncio.cluster",
]:
    sys.modules.setdefault(module_name, MagicMock())

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.clients.queen_agent_grpc_client import QueenAgentGrpcClient  # noqa: E402
from src.clients.queen_agent_grpc_client import queen_agent_pb2  # noqa: E402


@pytest.fixture
def settings():
    return SimpleNamespace(queen_agent_endpoint="localhost:50052", grpc_timeout=1.0)


@pytest.fixture
def mock_channel():
    channel = AsyncMock()
    channel.channel_ready = AsyncMock()
    channel.close = AsyncMock()
    return channel


@pytest.mark.asyncio
async def test_connect_initializes_stub(settings, mock_channel):
    mock_stub = MagicMock()
    with patch("grpc.aio.insecure_channel", return_value=mock_channel), patch(
        "src.clients.queen_agent_grpc_client.queen_agent_pb2_grpc.QueenAgentStub", return_value=mock_stub
    ), patch("src.clients.queen_agent_grpc_client.get_settings", return_value=settings):
        client = QueenAgentGrpcClient()
        await client.connect()

        assert client.stub is mock_stub
        mock_channel.channel_ready.assert_called_once()


@pytest.mark.asyncio
async def test_request_approval_maps_response(settings):
    response = queen_agent_pb2.RequestExceptionResponse(exception_id="exc-1", status="APPROVED")
    mock_stub = MagicMock(spec_set=["RequestExceptionApproval"])
    mock_stub.RequestExceptionApproval = AsyncMock(return_value=response)

    with patch("src.clients.queen_agent_grpc_client.get_settings", return_value=settings):
        client = QueenAgentGrpcClient()
        client.stub = mock_stub

        decision = await client.request_approval(
            optimization_id="opt-1",
            optimization_type="WEIGHT_RECALIBRATION",
            hypothesis={"description": "desc"},
            risk_score=0.2,
        )

        assert decision["approved"] is True
        assert decision["decision_id"] == "exc-1"
        mock_stub.RequestExceptionApproval.assert_called_once()


@pytest.mark.asyncio
async def test_get_strategic_priorities_returns_status(settings):
    response = queen_agent_pb2.SystemStatusResponse(
        system_score=0.9, sla_compliance=0.99, error_rate=0.01, resource_saturation=0.5, active_incidents=0, timestamp=123
    )
    mock_stub = MagicMock(spec_set=["GetSystemStatus"])
    mock_stub.GetSystemStatus = AsyncMock(return_value=response)

    with patch("src.clients.queen_agent_grpc_client.get_settings", return_value=settings):
        client = QueenAgentGrpcClient()
        client.stub = mock_stub

        priorities = await client.get_strategic_priorities()

        assert priorities is not None
        assert priorities["updated_at"] == 123
        mock_stub.GetSystemStatus.assert_called_once()


@pytest.mark.asyncio
async def test_request_approval_rpc_error_returns_none(settings):
    mock_error = grpc.RpcError()
    mock_error.code = lambda: grpc.StatusCode.UNAVAILABLE

    mock_stub = MagicMock(spec_set=["RequestExceptionApproval"])
    mock_stub.RequestExceptionApproval = AsyncMock(side_effect=mock_error)

    with patch("src.clients.queen_agent_grpc_client.get_settings", return_value=settings):
        client = QueenAgentGrpcClient()
        client.stub = mock_stub

        result = await client.request_approval(
            optimization_id="opt-err",
            optimization_type="WEIGHT_RECALIBRATION",
            hypothesis={"description": "desc"},
            risk_score=0.9,
        )

        assert result is None
