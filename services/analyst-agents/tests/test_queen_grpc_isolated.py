"""Teste isolado do cliente gRPC do Queen Agent"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
import grpc


# Criar mocks antes de importar
class MockInsightType:
    STRATEGIC = 'STRATEGIC'
    value = 'STRATEGIC'


class MockPriority:
    HIGH = 'HIGH'
    value = 'HIGH'


class MockRecommendation:
    def __init__(self, action, priority, estimated_impact):
        self.action = action
        self.priority = priority
        self.estimated_impact = estimated_impact


class MockRelatedEntity:
    def __init__(self, entity_type, entity_id, relationship):
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.relationship = relationship


class MockTimeWindow:
    def __init__(self, start_timestamp, end_timestamp):
        self.start_timestamp = start_timestamp
        self.end_timestamp = end_timestamp


class MockAnalystInsight:
    def __init__(self):
        self.insight_id = 'test-insight-123'
        self.version = '1.0.0'
        self.correlation_id = 'corr-123'
        self.trace_id = 'trace-123'
        self.span_id = 'span-123'
        self.insight_type = MockInsightType()
        self.priority = MockPriority()
        self.title = 'Test Insight'
        self.summary = 'Test summary'
        self.detailed_analysis = 'Test analysis'
        self.data_sources = ['test']
        self.metrics = {'metric1': 0.5}
        self.confidence_score = 0.8
        self.impact_score = 0.7
        self.recommendations = [MockRecommendation('Test action', 'HIGH', 0.8)]
        self.related_entities = [MockRelatedEntity('service', 'svc-1', 'affects')]
        self.time_window = MockTimeWindow(1000000000, 1000003600)
        self.created_at = 1000003600
        self.valid_until = 1000007200
        self.tags = ['test']
        self.metadata = {'source': 'test'}
        self.hash = 'testhash'
        self.schema_version = 1


@pytest.mark.asyncio
async def test_send_insight_invokes_submit_insight():
    """Teste que verifica se SubmitInsight é invocado quando um insight é enviado"""
    # Setup mocks
    mock_channel = AsyncMock()
    mock_channel.channel_ready = AsyncMock()

    mock_stub = MagicMock()
    mock_response = MagicMock()
    mock_response.accepted = True
    mock_response.insight_id = 'test-insight-123'
    mock_response.message = 'Aceito'
    mock_stub.SubmitInsight = AsyncMock(return_value=mock_response)

    mock_pb2 = MagicMock()
    mock_pb2.SubmitInsightRequest = MagicMock(return_value=MagicMock())
    mock_pb2.Recommendation = MagicMock(return_value=MagicMock())
    mock_pb2.RelatedEntity = MagicMock(return_value=MagicMock())
    mock_pb2.TimeWindow = MagicMock(return_value=MagicMock())

    mock_pb2_grpc = MagicMock()
    mock_pb2_grpc.QueenAgentStub = MagicMock(return_value=mock_stub)

    # Patch imports e criar cliente
    with patch('grpc.aio.insecure_channel', return_value=mock_channel):
        with patch.dict('sys.modules', {
            'src.proto.queen_agent_pb2': mock_pb2,
            'src.proto.queen_agent_pb2_grpc': mock_pb2_grpc,
        }):
            # Import após patches
            from src.clients.queen_agent_grpc_client import QueenAgentGRPCClient

            client = QueenAgentGRPCClient(host='localhost', port=50051)
            await client.initialize()

            # Enviar insight
            insight = MockAnalystInsight()
            result = await client.send_strategic_insight(insight)

            # Verificações
            assert result is True
            mock_stub.SubmitInsight.assert_called_once()
            assert mock_pb2.SubmitInsightRequest.called


@pytest.mark.asyncio
async def test_client_initialization():
    """Teste que verifica inicialização do cliente"""
    mock_channel = AsyncMock()
    mock_channel.channel_ready = AsyncMock()

    mock_stub = MagicMock()
    mock_pb2_grpc = MagicMock()
    mock_pb2_grpc.QueenAgentStub = MagicMock(return_value=mock_stub)

    with patch('grpc.aio.insecure_channel', return_value=mock_channel):
        with patch.dict('sys.modules', {
            'src.proto.queen_agent_pb2_grpc': mock_pb2_grpc,
        }):
            from src.clients.queen_agent_grpc_client import QueenAgentGRPCClient

            client = QueenAgentGRPCClient(host='test-host', port=9999)
            await client.initialize()

            assert client.channel is not None
            assert client.stub is not None
            mock_channel.channel_ready.assert_called_once()


@pytest.mark.asyncio
async def test_retry_logic():
    """Teste que verifica lógica de retry"""
    mock_channel = AsyncMock()
    mock_channel.channel_ready = AsyncMock()

    # Criar erro gRPC
    mock_error = grpc.RpcError()
    mock_error.code = lambda: grpc.StatusCode.UNAVAILABLE

    # Success response
    mock_success = MagicMock()
    mock_success.accepted = True
    mock_success.insight_id = 'test-123'
    mock_success.message = 'Success after retry'

    # Stub com side_effect: primeiro falha, depois sucesso
    mock_stub = MagicMock()
    mock_stub.SubmitInsight = AsyncMock(side_effect=[mock_error, mock_success])

    mock_pb2 = MagicMock()
    mock_pb2.SubmitInsightRequest = MagicMock(return_value=MagicMock())
    mock_pb2.Recommendation = MagicMock(return_value=MagicMock())
    mock_pb2.RelatedEntity = MagicMock(return_value=MagicMock())
    mock_pb2.TimeWindow = MagicMock(return_value=MagicMock())

    mock_pb2_grpc = MagicMock()
    mock_pb2_grpc.QueenAgentStub = MagicMock(return_value=mock_stub)

    with patch('grpc.aio.insecure_channel', return_value=mock_channel):
        with patch('asyncio.sleep', new_callable=AsyncMock):  # Mock sleep
            with patch.dict('sys.modules', {
                'src.proto.queen_agent_pb2': mock_pb2,
                'src.proto.queen_agent_pb2_grpc': mock_pb2_grpc,
            }):
                from src.clients.queen_agent_grpc_client import QueenAgentGRPCClient

                client = QueenAgentGRPCClient(host='localhost', port=50051)
                await client.initialize()

                insight = MockAnalystInsight()
                result = await client.send_strategic_insight(insight)

                # Deve ter tentado 2 vezes
                assert result is True
                assert mock_stub.SubmitInsight.call_count == 2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
