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

from src.clients.analyst_agents_grpc_client import AnalystAgentsGrpcClient  # noqa: E402
from src.clients.analyst_agents_grpc_client import analyst_agent_pb2  # noqa: E402


@pytest.fixture
def settings():
    return SimpleNamespace(analyst_agents_endpoint="localhost:50055", grpc_timeout=1.0)


@pytest.fixture
def mock_channel():
    channel = AsyncMock()
    channel.channel_ready = AsyncMock()
    channel.close = AsyncMock()
    return channel


@pytest.mark.asyncio
async def test_connect_creates_stub(settings, mock_channel):
    mock_stub = MagicMock()
    with patch("grpc.aio.insecure_channel", return_value=mock_channel), patch(
        "src.clients.analyst_agents_grpc_client.analyst_agent_pb2_grpc.AnalystAgentServiceStub",
        return_value=mock_stub,
    ), patch("src.clients.analyst_agents_grpc_client.get_settings", return_value=settings):
        client = AnalystAgentsGrpcClient()
        await client.connect()

        assert client.stub is mock_stub
        mock_channel.channel_ready.assert_called_once()


@pytest.mark.asyncio
async def test_request_causal_analysis_fallback_execute_analysis(settings):
    mock_stub = MagicMock(spec_set=["ExecuteAnalysis"])
    mock_stub.ExecuteAnalysis = AsyncMock(
        return_value=analyst_agent_pb2.ExecuteAnalysisResponse(
            analysis_id="analysis-1", results={"root_cause": 0.9}, confidence=0.92
        )
    )

    with patch("src.clients.analyst_agents_grpc_client.get_settings", return_value=settings):
        client = AnalystAgentsGrpcClient()
        client.stub = mock_stub

        response = await client.request_causal_analysis(
            target_component="api", degradation_metrics={"latency_p99": 500}, context={"env": "test"}
        )

        assert response is not None
        assert "results" in response
        mock_stub.ExecuteAnalysis.assert_called_once()


@pytest.mark.asyncio
async def test_get_historical_insights_uses_query_insights(settings):
    mock_stub = MagicMock(spec_set=["QueryInsights"])
    mock_stub.QueryInsights = AsyncMock(
        return_value=analyst_agent_pb2.QueryInsightsResponse(total_count=1)
    )

    fixed_time = 1_700_000_000  # seconds epoch

    with patch("time.time", return_value=fixed_time), patch(
        "src.clients.analyst_agents_grpc_client.get_settings", return_value=settings
    ):
        client = AnalystAgentsGrpcClient()
        client.stub = mock_stub

        result = await client.get_historical_insights(target_component="worker", time_range="24h")

        assert result is not None
        assert "total_count" in result
        mock_stub.QueryInsights.assert_called_once()
        request = mock_stub.QueryInsights.call_args[0][0]
        assert request.insight_type == "worker"
        assert request.start_timestamp == int(fixed_time * 1000) - 24 * 60 * 60 * 1000
        assert request.end_timestamp == int(fixed_time * 1000)


@pytest.mark.asyncio
async def test_validate_optimization_hypothesis_handles_rpc_error(settings):
    mock_error = grpc.RpcError()
    mock_error.code = lambda: grpc.StatusCode.UNAVAILABLE

    mock_stub = MagicMock(spec_set=["ExecuteAnalysis"])
    mock_stub.ExecuteAnalysis = AsyncMock(side_effect=mock_error)

    with patch("src.clients.analyst_agents_grpc_client.get_settings", return_value=settings):
        client = AnalystAgentsGrpcClient()
        client.stub = mock_stub

        result = await client.validate_optimization_hypothesis({"hypothesis_id": "h1"})

        assert result is None
        mock_stub.ExecuteAnalysis.assert_called_once()
