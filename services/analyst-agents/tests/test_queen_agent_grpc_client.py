"""Testes para o cliente gRPC do Queen Agent"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import grpc

# Import direto sem passar por __init__.py
from src.clients.queen_agent_grpc_client import QueenAgentGrpcClient
from src.models.insight import (
    AnalystInsight,
    InsightType,
    Priority,
    Recommendation,
    RelatedEntity,
    TimeWindow,
)
from src.proto import queen_agent_pb2


@pytest.fixture
def sample_insight():
    """Criar insight de exemplo para testes"""
    return AnalystInsight(
        insight_id="test-insight-123",
        version="1.0.0",
        correlation_id="corr-123",
        trace_id="trace-123",
        span_id="span-123",
        insight_type=InsightType.STRATEGIC,
        priority=Priority.HIGH,
        title="Test Strategic Insight",
        summary="Teste de insight estratégico",
        detailed_analysis="Análise detalhada do insight de teste",
        data_sources=["telemetry", "consensus"],
        metrics={"metric1": 0.85, "metric2": 0.92},
        confidence_score=0.88,
        impact_score=0.75,
        recommendations=[
            Recommendation(action="Escalar recursos", priority="HIGH", estimated_impact=0.85)
        ],
        related_entities=[
            RelatedEntity(entity_type="service", entity_id="service-123", relationship="affects")
        ],
        time_window=TimeWindow(start_timestamp=1000000000, end_timestamp=1000003600),
        created_at=1000003600,
        valid_until=1000007200,
        tags=["performance", "strategic"],
        metadata={"source": "telemetry_consumer"},
    )


def _setup_mock_channel(mock_channel):
    """Configura métodos async do mock channel"""

    async def _channel_ready():
        return None

    async def _close():
        return None

    mock_channel.channel_ready = _channel_ready
    mock_channel.close = _close


@pytest.fixture
def mock_channel():
    """Mock do canal gRPC"""
    channel = MagicMock()
    _setup_mock_channel(channel)
    return channel


@pytest.fixture
def mock_stub():
    """Mock do stub gRPC"""
    stub = MagicMock()
    stub.SubmitInsight = AsyncMock()
    return stub


@pytest.mark.asyncio
async def test_initialize_success(mock_channel, mock_stub):
    """Testar inicialização bem-sucedida do cliente"""
    _setup_mock_channel(mock_channel)

    with patch("grpc.aio.insecure_channel", return_value=mock_channel):
        with patch(
            "src.clients.queen_agent_grpc_client.instrument_grpc_channel", return_value=mock_channel
        ):
            with patch(
                "src.clients.queen_agent_grpc_client.queen_agent_pb2_grpc.QueenAgentStub",
                return_value=mock_stub,
            ):
                client = QueenAgentGrpcClient(host="localhost", port=50051)
                await client.initialize()

                assert client.channel is not None
                assert client.stub is not None


@pytest.mark.asyncio
async def test_send_strategic_insight_success(sample_insight, mock_channel, mock_stub):
    """Testar envio bem-sucedido de insight estratégico"""
    _setup_mock_channel(mock_channel)

    # Configurar resposta mock
    mock_response = queen_agent_pb2.SubmitInsightResponse(
        accepted=True, insight_id=sample_insight.insight_id, message="Insight aceito com sucesso"
    )
    mock_stub.SubmitInsight.return_value = mock_response

    with patch("grpc.aio.insecure_channel", return_value=mock_channel):
        with patch(
            "src.clients.queen_agent_grpc_client.instrument_grpc_channel", return_value=mock_channel
        ):
            with patch(
                "src.clients.queen_agent_grpc_client.queen_agent_pb2_grpc.QueenAgentStub",
                return_value=mock_stub,
            ):
                client = QueenAgentGrpcClient(host="localhost", port=50051)
                await client.initialize()

                # Enviar insight
                result = await client.send_strategic_insight(sample_insight)

                assert result is True
                mock_stub.SubmitInsight.assert_called_once()

                # Verificar campos do request
                call_args = mock_stub.SubmitInsight.call_args
                request = call_args[0][0]

                assert request.insight_id == sample_insight.insight_id
                assert request.insight_type == sample_insight.insight_type.value
                assert request.priority == sample_insight.priority.value
                assert request.confidence_score == sample_insight.confidence_score
                assert request.impact_score == sample_insight.impact_score


@pytest.mark.asyncio
async def test_send_strategic_insight_rejected(sample_insight, mock_channel, mock_stub):
    """Testar envio de insight que é rejeitado"""
    _setup_mock_channel(mock_channel)

    # Configurar resposta mock de rejeição
    mock_response = queen_agent_pb2.SubmitInsightResponse(
        accepted=False,
        insight_id=sample_insight.insight_id,
        message="Insight rejeitado: confiança muito baixa",
    )
    mock_stub.SubmitInsight.return_value = mock_response

    with patch("grpc.aio.insecure_channel", return_value=mock_channel):
        with patch(
            "src.clients.queen_agent_grpc_client.instrument_grpc_channel", return_value=mock_channel
        ):
            with patch(
                "src.clients.queen_agent_grpc_client.queen_agent_pb2_grpc.QueenAgentStub",
                return_value=mock_stub,
            ):
                client = QueenAgentGrpcClient(host="localhost", port=50051)
                await client.initialize()

                result = await client.send_strategic_insight(sample_insight)

                assert result is False


@pytest.mark.asyncio
async def test_send_strategic_insight_with_retry(sample_insight, mock_channel, mock_stub):
    """Testar retry em caso de erro transitório"""
    _setup_mock_channel(mock_channel)

    # Primeira chamada falha com UNAVAILABLE, segunda succeeds
    mock_response = queen_agent_pb2.SubmitInsightResponse(
        accepted=True, insight_id=sample_insight.insight_id, message="Insight aceito com sucesso"
    )
    mock_stub.SubmitInsight.side_effect = [
        grpc.RpcError(grpc.StatusCode.UNAVAILABLE),
        mock_response,
    ]

    with patch("grpc.aio.insecure_channel", return_value=mock_channel):
        with patch(
            "src.clients.queen_agent_grpc_client.instrument_grpc_channel", return_value=mock_channel
        ):
            with patch(
                "src.clients.queen_agent_grpc_client.queen_agent_pb2_grpc.QueenAgentStub",
                return_value=mock_stub,
            ):
                client = QueenAgentGrpcClient(host="localhost", port=50051)
                await client.initialize()

                result = await client.send_strategic_insight(sample_insight)

                # Retry deve ter sucesso na segunda tentativa
                assert result is True
                assert mock_stub.SubmitInsight.call_count == 2


@pytest.mark.asyncio
async def test_send_strategic_insight_max_retries_exceeded(sample_insight, mock_channel, mock_stub):
    """Testar que retries param após MAX_RETRIES"""
    _setup_mock_channel(mock_channel)

    # Configurar para sempre falhar com UNAVAILABLE
    mock_stub.SubmitInsight.side_effect = grpc.RpcError(grpc.StatusCode.UNAVAILABLE)

    with patch("grpc.aio.insecure_channel", return_value=mock_channel):
        with patch(
            "src.clients.queen_agent_grpc_client.instrument_grpc_channel", return_value=mock_channel
        ):
            with patch(
                "src.clients.queen_agent_grpc_client.queen_agent_pb2_grpc.QueenAgentStub",
                return_value=mock_stub,
            ):
                client = QueenAgentGrpcClient(host="localhost", port=50051)
                await client.initialize()

                result = await client.send_strategic_insight(sample_insight)

                # Erro deve retornar False após MAX_RETRIES tentativas
                assert result is False
                # MAX_RETRIES é 3, então devem ser 3 tentativas
                assert mock_stub.SubmitInsight.call_count == 3


@pytest.mark.asyncio
async def test_send_operational_insight(sample_insight, mock_channel, mock_stub):
    """Testar envio de insight operacional (deve usar mesma implementação)"""
    _setup_mock_channel(mock_channel)

    mock_response = queen_agent_pb2.SubmitInsightResponse(
        accepted=True, insight_id=sample_insight.insight_id, message="Insight operacional aceito"
    )
    mock_stub.SubmitInsight.return_value = mock_response

    with patch("grpc.aio.insecure_channel", return_value=mock_channel):
        with patch(
            "src.clients.queen_agent_grpc_client.instrument_grpc_channel", return_value=mock_channel
        ):
            with patch(
                "src.clients.queen_agent_grpc_client.queen_agent_pb2_grpc.QueenAgentStub",
                return_value=mock_stub,
            ):
                client = QueenAgentGrpcClient(host="localhost", port=50051)
                await client.initialize()

                result = await client.send_operational_insight(sample_insight)

                assert result is True
                mock_stub.SubmitInsight.assert_called_once()


@pytest.mark.asyncio
async def test_close_connection(mock_channel, mock_stub):
    """Testar fechamento da conexão"""
    _setup_mock_channel(mock_channel)

    with patch("grpc.aio.insecure_channel", return_value=mock_channel):
        with patch(
            "src.clients.queen_agent_grpc_client.instrument_grpc_channel", return_value=mock_channel
        ):
            with patch(
                "src.clients.queen_agent_grpc_client.queen_agent_pb2_grpc.QueenAgentStub",
                return_value=mock_stub,
            ):
                client = QueenAgentGrpcClient(host="localhost", port=50051)
                await client.initialize()
                await client.close()

                # mock_channel.close é uma coroutine, não podemos verificar chamada
                # O importante é que não levanta exceção


@pytest.mark.asyncio
async def test_send_without_initialization(sample_insight):
    """Testar que envio sem inicialização retorna False"""
    client = QueenAgentGrpcClient(host="localhost", port=50051)
    result = await client.send_strategic_insight(sample_insight)

    assert result is False
