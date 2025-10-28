"""
Testes unitários para grpc_server.

Valida a conversão resiliente de timestamps no GetCapabilities.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime
from google.protobuf.timestamp_pb2 import Timestamp

from neural_hive_specialists.grpc_server import SpecialistServicer


class TestSpecialistServicer:
    """Testes para SpecialistServicer."""

    @pytest.fixture
    def mock_specialist(self):
        """Cria mock do especialista."""
        specialist = Mock()
        specialist.specialist_type = "test_specialist"
        return specialist

    @pytest.fixture
    def servicer(self, mock_specialist):
        """Cria servicer para testes."""
        return SpecialistServicer(mock_specialist)

    def test_build_get_capabilities_response_with_valid_timestamp(self, servicer):
        """Testa conversão com timestamp válido ISO-8601."""
        capabilities = {
            'specialist_type': 'test',
            'version': '1.0.0',
            'supported_domains': ['test'],
            'supported_plan_versions': ['v1'],
            'metrics': {
                'average_processing_time_ms': 100.0,
                'accuracy_score': 0.95,
                'total_evaluations': 42,
                'last_model_update': '2024-01-15T10:30:00'
            },
            'configuration': {}
        }

        with patch('neural_hive_specialists.grpc_server.specialist_pb2') as mock_pb2:
            # Configurar mocks
            mock_metrics = Mock()
            mock_response = Mock()
            mock_pb2.CapabilityMetrics.return_value = mock_metrics
            mock_pb2.GetCapabilitiesResponse.return_value = mock_response

            response = servicer._build_get_capabilities_response(capabilities)

            # Verificar que CapabilityMetrics foi chamado com timestamp
            assert mock_pb2.CapabilityMetrics.called
            call_kwargs = mock_pb2.CapabilityMetrics.call_args[1]
            assert call_kwargs['average_processing_time_ms'] == 100.0
            assert call_kwargs['accuracy_score'] == 0.95
            assert call_kwargs['total_evaluations'] == 42
            assert 'last_model_update' in call_kwargs

    def test_build_get_capabilities_response_with_none_timestamp(self, servicer):
        """Testa conversão quando timestamp é None."""
        capabilities = {
            'specialist_type': 'test',
            'version': '1.0.0',
            'supported_domains': ['test'],
            'supported_plan_versions': ['v1'],
            'metrics': {
                'average_processing_time_ms': 100.0,
                'accuracy_score': 0.95,
                'total_evaluations': 42,
                'last_model_update': None
            },
            'configuration': {}
        }

        with patch('neural_hive_specialists.grpc_server.specialist_pb2') as mock_pb2:
            # Configurar mocks
            mock_metrics = Mock()
            mock_response = Mock()
            mock_pb2.CapabilityMetrics.return_value = mock_metrics
            mock_pb2.GetCapabilitiesResponse.return_value = mock_response

            response = servicer._build_get_capabilities_response(capabilities)

            # Verificar que CapabilityMetrics foi chamado SEM timestamp
            assert mock_pb2.CapabilityMetrics.called
            call_kwargs = mock_pb2.CapabilityMetrics.call_args[1]
            assert call_kwargs['average_processing_time_ms'] == 100.0
            assert call_kwargs['accuracy_score'] == 0.95
            assert call_kwargs['total_evaluations'] == 42
            assert 'last_model_update' not in call_kwargs

    def test_build_get_capabilities_response_with_invalid_timestamp(self, servicer):
        """Testa conversão quando timestamp tem formato inválido."""
        capabilities = {
            'specialist_type': 'test',
            'version': '1.0.0',
            'supported_domains': ['test'],
            'supported_plan_versions': ['v1'],
            'metrics': {
                'average_processing_time_ms': 100.0,
                'accuracy_score': 0.95,
                'total_evaluations': 42,
                'last_model_update': 'invalid-format'
            },
            'configuration': {}
        }

        with patch('neural_hive_specialists.grpc_server.specialist_pb2') as mock_pb2:
            with patch('neural_hive_specialists.grpc_server.logger') as mock_logger:
                # Configurar mocks
                mock_metrics = Mock()
                mock_response = Mock()
                mock_pb2.CapabilityMetrics.return_value = mock_metrics
                mock_pb2.GetCapabilitiesResponse.return_value = mock_response

                response = servicer._build_get_capabilities_response(capabilities)

                # Verificar que warning foi logado
                assert mock_logger.warning.called
                warning_call = mock_logger.warning.call_args
                assert 'Invalid last_model_update format' in warning_call[0][0]

                # Verificar que CapabilityMetrics foi chamado SEM timestamp
                assert mock_pb2.CapabilityMetrics.called
                call_kwargs = mock_pb2.CapabilityMetrics.call_args[1]
                assert 'last_model_update' not in call_kwargs

    def test_build_get_capabilities_response_with_empty_metrics(self, servicer):
        """Testa conversão quando metrics está vazio."""
        capabilities = {
            'specialist_type': 'test',
            'version': '1.0.0',
            'supported_domains': ['test'],
            'supported_plan_versions': ['v1'],
            'metrics': {},
            'configuration': {}
        }

        with patch('neural_hive_specialists.grpc_server.specialist_pb2') as mock_pb2:
            # Configurar mocks
            mock_response = Mock()
            mock_pb2.GetCapabilitiesResponse.return_value = mock_response

            response = servicer._build_get_capabilities_response(capabilities)

            # Verificar que CapabilityMetrics NÃO foi chamado (metrics vazio)
            assert not mock_pb2.CapabilityMetrics.called

            # Verificar que GetCapabilitiesResponse foi chamado com metrics=None
            assert mock_pb2.GetCapabilitiesResponse.called
            call_kwargs = mock_pb2.GetCapabilitiesResponse.call_args[1]
            assert call_kwargs['metrics'] is None

    def test_get_capabilities_handles_none_gracefully(self, servicer, mock_specialist):
        """Testa que GetCapabilities não falha com timestamp None."""
        # Simular retorno do specialist com last_model_update como None
        mock_specialist.get_capabilities.return_value = {
            'specialist_type': 'test',
            'version': '1.0.0',
            'supported_domains': ['test'],
            'supported_plan_versions': ['v1'],
            'metrics': {
                'average_processing_time_ms': 100.0,
                'accuracy_score': 0.95,
                'total_evaluations': 42,
                'last_model_update': None
            },
            'configuration': {}
        }

        request = Mock()
        context = Mock()

        with patch('neural_hive_specialists.grpc_server.PROTO_AVAILABLE', True):
            with patch('neural_hive_specialists.grpc_server.specialist_pb2') as mock_pb2:
                # Configurar mocks para não gerar erro
                mock_pb2.CapabilityMetrics.return_value = Mock()
                mock_pb2.GetCapabilitiesResponse.return_value = Mock()

                # Esta chamada NÃO deve lançar ValueError
                response = servicer.GetCapabilities(request, context)

                # Verificar que não houve erro
                assert not context.set_code.called
                assert response is not None


@pytest.mark.unit
class TestEvaluatePlan:
    """Testes do método EvaluatePlan."""

    @pytest.fixture
    def mock_specialist(self):
        """Cria mock do especialista."""
        specialist = Mock()
        specialist.specialist_type = "test_specialist"
        specialist.evaluate_plan = Mock(return_value={
            'opinion_id': 'opinion-123',
            'specialist_type': 'test',
            'specialist_version': '1.0.0',
            'opinion': {
                'confidence_score': 0.85,
                'risk_score': 0.2,
                'recommendation': 'approve',
                'reasoning_summary': 'Test reasoning',
                'reasoning_factors': [{'factor': 'test', 'weight': 0.5}],
                'explainability_token': 'token-123',
                'mitigations': [],
                'metadata': {}
            },
            'processing_time_ms': 150
        })
        return specialist

    @pytest.fixture
    def servicer(self, mock_specialist):
        """Cria servicer para testes."""
        return SpecialistServicer(mock_specialist)

    def test_evaluate_plan_happy_path(self, servicer, mock_specialist):
        """Testa caminho feliz do EvaluatePlan."""
        request = Mock()
        request.plan_id = "plan-123"
        request.cognitive_plan = b'{"test": "plan"}'
        context = Mock()

        with patch('neural_hive_specialists.grpc_server.specialist_pb2') as mock_pb2:
            mock_pb2.EvaluatePlanResponse.return_value = Mock()
            mock_pb2.ReasoningFactor.return_value = Mock()

            response = servicer.EvaluatePlan(request, context)

            # Verificar que specialist.evaluate_plan foi chamado
            mock_specialist.evaluate_plan.assert_called_once_with(request)
            # Verificar que resposta foi construída
            assert mock_pb2.EvaluatePlanResponse.called

    def test_evaluate_plan_logs_request(self, servicer, mock_specialist):
        """Verifica que logging acontece."""
        request = Mock()
        request.plan_id = "plan-123"
        request.cognitive_plan = b'{"test": "plan"}'
        context = Mock()

        with patch('neural_hive_specialists.grpc_server.logger') as mock_logger:
            with patch('neural_hive_specialists.grpc_server.specialist_pb2') as mock_pb2:
                mock_pb2.EvaluatePlanResponse.return_value = Mock()
                mock_pb2.ReasoningFactor.return_value = Mock()

                servicer.EvaluatePlan(request, context)

                # Verificar que log foi registrado
                assert mock_logger.info.called

    def test_evaluate_plan_handles_exception(self, servicer, mock_specialist):
        """Testa tratamento de exceção."""
        request = Mock()
        mock_specialist.evaluate_plan = Mock(side_effect=Exception("Test error"))
        context = Mock()

        with patch('neural_hive_specialists.grpc_server.logger'):
            servicer.EvaluatePlan(request, context)

            # Verificar que context.set_code foi chamado com erro
            context.set_code.assert_called_once()
            context.set_details.assert_called_once()


@pytest.mark.unit
class TestHealthCheck:
    """Testes do método HealthCheck."""

    @pytest.fixture
    def servicer(self):
        """Cria servicer para testes."""
        specialist = Mock()
        specialist.specialist_type = "test"
        return SpecialistServicer(specialist)

    def test_health_check_serving(self, servicer):
        """Testa health check quando status é SERVING."""
        servicer.specialist.health_check = Mock(return_value={
            'status': 'SERVING',
            'details': {'model_loaded': 'True', 'ledger_connected': 'True'}
        })

        request = Mock()
        context = Mock()

        with patch('neural_hive_specialists.grpc_server.health_pb2') as mock_health_pb2:
            mock_health_pb2.HealthCheckResponse.return_value = Mock()
            mock_health_pb2.HealthCheckResponse.SERVING = 1

            response = servicer.HealthCheck(request, context)

            # Verificar mapeamento correto
            assert mock_health_pb2.HealthCheckResponse.called

    def test_health_check_not_serving(self, servicer):
        """Testa health check quando status é NOT_SERVING."""
        servicer.specialist.health_check = Mock(return_value={
            'status': 'NOT_SERVING',
            'details': {'model_loaded': 'False'}
        })

        request = Mock()
        context = Mock()

        with patch('neural_hive_specialists.grpc_server.health_pb2') as mock_health_pb2:
            mock_health_pb2.HealthCheckResponse.return_value = Mock()
            mock_health_pb2.HealthCheckResponse.NOT_SERVING = 2

            response = servicer.HealthCheck(request, context)

            assert mock_health_pb2.HealthCheckResponse.called


@pytest.mark.unit
class TestBuildEvaluatePlanResponse:
    """Testes do método _build_evaluate_plan_response."""

    @pytest.fixture
    def servicer(self):
        """Cria servicer para testes."""
        specialist = Mock()
        return SpecialistServicer(specialist)

    def test_build_response_maps_all_fields(self, servicer):
        """Verifica mapeamento correto de todos os campos."""
        eval_result = {
            'opinion_id': 'opinion-123',
            'specialist_type': 'test',
            'specialist_version': '1.0.0',
            'opinion': {
                'confidence_score': 0.85,
                'risk_score': 0.2,
                'recommendation': 'approve',
                'reasoning_summary': 'Test',
                'reasoning_factors': [
                    {'factor': 'test', 'weight': 0.5, 'score': 0.9, 'contribution': 'positive'}
                ],
                'explainability_token': 'token-123',
                'explainability': {'method': 'shap'},
                'mitigations': [{'description': 'Test mitigation', 'priority': 'high'}],
                'metadata': {'key': 'value'}
            },
            'processing_time_ms': 150,
            'evaluated_at': '2025-01-01T00:00:00'
        }

        with patch('neural_hive_specialists.grpc_server.specialist_pb2') as mock_pb2:
            mock_pb2.EvaluatePlanResponse.return_value = Mock()
            mock_pb2.ReasoningFactor.return_value = Mock()
            mock_pb2.Mitigation.return_value = Mock()

            response = servicer._build_evaluate_plan_response(eval_result)

            # Verificar chamadas
            assert mock_pb2.EvaluatePlanResponse.called
            assert mock_pb2.ReasoningFactor.called
            assert mock_pb2.Mitigation.called


@pytest.mark.unit
class TestCreateGRPCServer:
    """Testes da função create_grpc_server_with_observability."""

    def test_creates_server_with_servicers(self, mock_config):
        """Testa criação de servidor com servicers registrados."""
        specialist = Mock()

        with patch('neural_hive_specialists.grpc_server.grpc.server') as mock_server:
            with patch('neural_hive_specialists.grpc_server.specialist_pb2_grpc'):
                with patch('neural_hive_specialists.grpc_server.health_pb2_grpc'):
                    mock_grpc_server = Mock()
                    mock_server.return_value = mock_grpc_server

                    from neural_hive_specialists.grpc_server import create_grpc_server_with_observability
                    server = create_grpc_server_with_observability(specialist, mock_config)

                    # Verificar que servidor foi criado
                    assert mock_server.called
                    # Verificar que add_insecure_port foi chamado
                    assert mock_grpc_server.add_insecure_port.called

    def test_server_options_configured(self, mock_config):
        """Verifica que opções do servidor são configuradas."""
        specialist = Mock()

        with patch('neural_hive_specialists.grpc_server.grpc.server') as mock_server:
            with patch('neural_hive_specialists.grpc_server.specialist_pb2_grpc'):
                with patch('neural_hive_specialists.grpc_server.health_pb2_grpc'):
                    from neural_hive_specialists.grpc_server import create_grpc_server_with_observability
                    server = create_grpc_server_with_observability(specialist, mock_config)

                    # Verificar que opções foram passadas
                    call_args = mock_server.call_args
                    assert call_args is not None
