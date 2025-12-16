"""
Testes de integração gRPC entre serviços
"""
import asyncio
from typing import Dict

import grpc
import pytest

# Imports dos clientes
from services.optimizer_agents.src.clients.analyst_agents_grpc_client import AnalystAgentsGrpcClient
from services.optimizer_agents.src.clients.queen_agent_grpc_client import QueenAgentGrpcClient
from services.analyst_agents.src.clients.queen_agent_grpc_client import QueenAgentGRPCClient


@pytest.mark.asyncio
@pytest.mark.integration
async def test_optimizer_to_analyst_grpc():
    """Testar comunicação Optimizer -> Analyst Agents"""
    client = AnalystAgentsGrpcClient()
    await client.connect()

    result = await client.request_causal_analysis(
        target_component="test-service",
        degradation_metrics={"latency_p99": 500},
        context={"environment": "test"},
    )

    assert result is not None
    assert "root_cause" in result or "analysis_type" in result
    assert "confidence_score" in result or "results" in result

    await client.disconnect()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_optimizer_to_queen_grpc():
    """Testar comunicação Optimizer -> Queen Agent"""
    client = QueenAgentGrpcClient()
    await client.connect()

    result = await client.request_approval(
        optimization_id="test-opt-123",
        optimization_type="WEIGHT_RECALIBRATION",
        hypothesis={"description": "Test optimization"},
        risk_score=0.3,
    )

    assert result is not None
    assert "approved" in result
    assert "decision_id" in result

    await client.disconnect()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_analyst_to_queen_grpc():
    """Testar comunicação Analyst -> Queen Agent"""
    from services.analyst_agents.src.models.insight import AnalystInsight, InsightType, Priority, TimeWindow

    client = QueenAgentGRPCClient(host="localhost", port=50051)
    await client.initialize()

    insight = AnalystInsight(
        insight_id="test-insight-123",
        version="1.0.0",
        correlation_id="test-corr",
        trace_id="test-trace",
        span_id="test-span",
        insight_type=InsightType.STRATEGIC,
        priority=Priority.HIGH,
        title="Test Insight",
        summary="Test summary",
        detailed_analysis="Test analysis",
        data_sources=["test"],
        metrics={"test_metric": 0.9},
        confidence_score=0.85,
        impact_score=0.75,
        recommendations=[],
        related_entities=[],
        time_window=TimeWindow(start_timestamp=1000, end_timestamp=2000),
        created_at=1500,
        tags=["test"],
    )

    result = await client.send_strategic_insight(insight)
    assert result is True

    await client.close()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_grpc_error_handling():
    """Testar error handling em falhas gRPC"""
    client = QueenAgentGrpcClient()

    # Tentar conectar em endpoint inválido
    client.settings.queen_agent_endpoint = "localhost:99999"

    with pytest.raises(Exception):
        await client.connect()
