"""
Testes de integração para timeouts específicos no cliente gRPC de specialists.

Valida que o SpecialistsGrpcClient usa timeouts específicos por specialist
e registra métricas corretamente.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timezone
import uuid

from google.protobuf.timestamp_pb2 import Timestamp


@pytest.fixture
def config_with_specific_timeouts():
    """Config com timeouts específicos por specialist"""
    config = MagicMock()
    config.specialist_business_endpoint = 'localhost:50051'
    config.specialist_technical_endpoint = 'localhost:50052'
    config.specialist_behavior_endpoint = 'localhost:50053'
    config.specialist_evolution_endpoint = 'localhost:50054'
    config.specialist_architecture_endpoint = 'localhost:50055'
    config.grpc_timeout_ms = 30000
    config.grpc_max_retries = 3
    config.spiffe_enabled = False
    config.environment = 'dev'

    # Configurar timeouts específicos
    config.specialist_business_timeout_ms = 120000
    config.specialist_technical_timeout_ms = None
    config.specialist_behavior_timeout_ms = None
    config.specialist_evolution_timeout_ms = None
    config.specialist_architecture_timeout_ms = None

    def get_specialist_timeout_ms(specialist_type: str) -> int:
        timeout_field = f'specialist_{specialist_type}_timeout_ms'
        specific_timeout = getattr(config, timeout_field, None)
        return specific_timeout if specific_timeout is not None else config.grpc_timeout_ms

    config.get_specialist_timeout_ms = get_specialist_timeout_ms
    return config


@pytest.fixture
def mock_evaluate_plan_response():
    """Response protobuf válida de EvaluatePlan"""
    from neural_hive_specialists.proto_gen import specialist_pb2

    response = specialist_pb2.EvaluatePlanResponse(
        opinion_id=str(uuid.uuid4()),
        specialist_type='business',
        specialist_version='1.0.9',
        opinion='APPROVE',
        confidence=0.95,
        reasoning='Plan aligns with business objectives.',
        processing_time_ms=50000
    )

    # Adicionar timestamp válido
    timestamp = Timestamp()
    timestamp.FromDatetime(datetime.now(timezone.utc))
    response.evaluated_at.CopyFrom(timestamp)

    # Adicionar opinion field com os campos esperados
    response.opinion.confidence_score = 0.95
    response.opinion.risk_score = 0.15
    response.opinion.recommendation = 'approve'
    response.opinion.reasoning_summary = 'Plan is viable'
    response.opinion.explainability_token = 'token-123'
    response.opinion.explainability.method = 'SHAP'
    response.opinion.explainability.model_version = '1.0'
    response.opinion.explainability.model_type = 'RandomForest'

    return response


class TestSpecialistsGrpcClientTimeouts:
    """Testes de integração para timeouts específicos no cliente gRPC"""

    @pytest.mark.asyncio
    async def test_evaluate_plan_uses_specific_timeout_for_business(
        self,
        config_with_specific_timeouts,
        mock_evaluate_plan_response
    ):
        """Deve usar timeout específico de 120s para Business Specialist"""
        from src.clients.specialists_grpc_client import SpecialistsGrpcClient

        client = SpecialistsGrpcClient(config_with_specific_timeouts)

        # Mock do stub
        mock_stub = AsyncMock()
        mock_stub.EvaluatePlan = AsyncMock(return_value=mock_evaluate_plan_response)
        client.stubs['business'] = mock_stub

        cognitive_plan = {
            'plan_id': str(uuid.uuid4()),
            'intent_id': str(uuid.uuid4()),
            'correlation_id': str(uuid.uuid4()),
            'version': '1.0.0'
        }
        trace_context = {'trace_id': str(uuid.uuid4()), 'span_id': str(uuid.uuid4())}

        # Executar com mock do asyncio.wait_for para capturar timeout
        with patch('src.clients.specialists_grpc_client.asyncio.wait_for') as mock_wait_for:
            mock_wait_for.return_value = mock_evaluate_plan_response
            await client.evaluate_plan('business', cognitive_plan, trace_context)

            # Verificar que wait_for foi chamado com timeout de 120s (120000ms / 1000)
            assert mock_wait_for.call_args[1]['timeout'] == 120.0

    @pytest.mark.asyncio
    async def test_evaluate_plan_uses_fallback_timeout_for_technical(
        self,
        config_with_specific_timeouts,
        mock_evaluate_plan_response
    ):
        """Deve usar timeout global de 30s para Technical Specialist (sem timeout específico)"""
        from src.clients.specialists_grpc_client import SpecialistsGrpcClient

        client = SpecialistsGrpcClient(config_with_specific_timeouts)

        # Mock do stub para technical
        mock_response = MagicMock()
        mock_response.opinion_id = str(uuid.uuid4())
        mock_response.specialist_type = 'technical'
        mock_response.specialist_version = '1.0.9'
        mock_response.processing_time_ms = 5000

        timestamp = Timestamp()
        timestamp.FromDatetime(datetime.now(timezone.utc))
        mock_response.evaluated_at = timestamp
        mock_response.HasField = lambda x: True

        mock_response.opinion = MagicMock()
        mock_response.opinion.confidence_score = 0.88
        mock_response.opinion.risk_score = 0.12
        mock_response.opinion.recommendation = 'approve'
        mock_response.opinion.reasoning_summary = 'Technically feasible'
        mock_response.opinion.reasoning_factors = []
        mock_response.opinion.explainability_token = 'token-456'
        mock_response.opinion.explainability.method = 'LIME'
        mock_response.opinion.explainability.model_version = '1.0'
        mock_response.opinion.explainability.model_type = 'XGBoost'
        mock_response.opinion.mitigations = []
        mock_response.opinion.metadata = {}

        mock_stub = AsyncMock()
        mock_stub.EvaluatePlan = AsyncMock(return_value=mock_response)
        client.stubs['technical'] = mock_stub

        cognitive_plan = {
            'plan_id': str(uuid.uuid4()),
            'intent_id': str(uuid.uuid4()),
            'correlation_id': str(uuid.uuid4()),
            'version': '1.0.0'
        }
        trace_context = {'trace_id': str(uuid.uuid4()), 'span_id': str(uuid.uuid4())}

        # Executar com mock do asyncio.wait_for para capturar timeout
        with patch('src.clients.specialists_grpc_client.asyncio.wait_for') as mock_wait_for:
            mock_wait_for.return_value = mock_response
            await client.evaluate_plan('technical', cognitive_plan, trace_context)

            # Verificar que wait_for foi chamado com timeout de 30s (30000ms / 1000)
            assert mock_wait_for.call_args[1]['timeout'] == 30.0

    @pytest.mark.asyncio
    async def test_evaluate_plan_timeout_records_metrics(
        self,
        config_with_specific_timeouts
    ):
        """Deve registrar métricas quando ocorre timeout"""
        from src.clients.specialists_grpc_client import SpecialistsGrpcClient

        client = SpecialistsGrpcClient(config_with_specific_timeouts)

        # Mock do stub
        mock_stub = AsyncMock()
        client.stubs['business'] = mock_stub

        cognitive_plan = {
            'plan_id': str(uuid.uuid4()),
            'intent_id': str(uuid.uuid4()),
            'correlation_id': str(uuid.uuid4()),
            'version': '1.0.0'
        }
        trace_context = {'trace_id': str(uuid.uuid4()), 'span_id': str(uuid.uuid4())}

        # Simular timeout
        with patch('src.clients.specialists_grpc_client.asyncio.wait_for') as mock_wait_for:
            mock_wait_for.side_effect = asyncio.TimeoutError()

            with patch('src.clients.specialists_grpc_client.ConsensusMetrics') as mock_metrics:
                with pytest.raises(asyncio.TimeoutError):
                    await client.evaluate_plan('business', cognitive_plan, trace_context)

                # Verificar que métricas de timeout foram registradas
                mock_metrics.observe_specialist_invocation_duration.assert_called()
                mock_metrics.increment_specialist_invocation.assert_called_with(
                    specialist_type='business',
                    status='timeout'
                )
                mock_metrics.increment_specialist_timeout.assert_called_with('business')

    @pytest.mark.asyncio
    async def test_evaluate_plan_grpc_error_records_metrics(
        self,
        config_with_specific_timeouts
    ):
        """Deve registrar métricas quando ocorre erro gRPC"""
        import grpc
        from src.clients.specialists_grpc_client import SpecialistsGrpcClient

        client = SpecialistsGrpcClient(config_with_specific_timeouts)

        # Mock do stub
        mock_stub = AsyncMock()
        client.stubs['technical'] = mock_stub

        cognitive_plan = {
            'plan_id': str(uuid.uuid4()),
            'intent_id': str(uuid.uuid4()),
            'correlation_id': str(uuid.uuid4()),
            'version': '1.0.0'
        }
        trace_context = {'trace_id': str(uuid.uuid4()), 'span_id': str(uuid.uuid4())}

        # Simular erro gRPC
        mock_grpc_error = MagicMock(spec=grpc.RpcError)
        mock_grpc_error.code.return_value = grpc.StatusCode.UNAVAILABLE
        mock_grpc_error.code.return_value.name = 'UNAVAILABLE'

        with patch('src.clients.specialists_grpc_client.asyncio.wait_for') as mock_wait_for:
            mock_wait_for.side_effect = mock_grpc_error

            with patch('src.clients.specialists_grpc_client.ConsensusMetrics') as mock_metrics:
                with pytest.raises(grpc.RpcError):
                    await client.evaluate_plan('technical', cognitive_plan, trace_context)

                # Verificar que métricas de erro gRPC foram registradas
                mock_metrics.observe_specialist_invocation_duration.assert_called()
                mock_metrics.increment_specialist_invocation.assert_called_with(
                    specialist_type='technical',
                    status='grpc_error'
                )
                mock_metrics.increment_specialist_grpc_error.assert_called()

    @pytest.mark.asyncio
    async def test_evaluate_plan_success_records_metrics(
        self,
        config_with_specific_timeouts,
        mock_evaluate_plan_response
    ):
        """Deve registrar métricas de sucesso quando invocação completa"""
        from src.clients.specialists_grpc_client import SpecialistsGrpcClient

        client = SpecialistsGrpcClient(config_with_specific_timeouts)

        # Mock do stub
        mock_stub = AsyncMock()
        mock_stub.EvaluatePlan = AsyncMock(return_value=mock_evaluate_plan_response)
        client.stubs['business'] = mock_stub

        cognitive_plan = {
            'plan_id': str(uuid.uuid4()),
            'intent_id': str(uuid.uuid4()),
            'correlation_id': str(uuid.uuid4()),
            'version': '1.0.0'
        }
        trace_context = {'trace_id': str(uuid.uuid4()), 'span_id': str(uuid.uuid4())}

        with patch('src.clients.specialists_grpc_client.asyncio.wait_for') as mock_wait_for:
            mock_wait_for.return_value = mock_evaluate_plan_response

            with patch('src.clients.specialists_grpc_client.ConsensusMetrics') as mock_metrics:
                await client.evaluate_plan('business', cognitive_plan, trace_context)

                # Verificar que métricas de sucesso foram registradas
                mock_metrics.observe_specialist_invocation_duration.assert_called()
                mock_metrics.increment_specialist_invocation.assert_called_with(
                    specialist_type='business',
                    status='success'
                )
