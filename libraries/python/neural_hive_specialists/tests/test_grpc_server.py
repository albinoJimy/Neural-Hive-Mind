"""
Testes unitários para grpc_server.

Valida:
- Conversão resiliente de timestamps no GetCapabilities
- Fluxo completo de EvaluatePlan, HealthCheck, GetCapabilities
- Tratamento de erros e cenários edge-case
- Propagação de contexto gRPC (tenant_id, trace_id)
"""

import pytest
import grpc
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timezone
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


# ============================================================================
# Testes Completos do SpecialistServicer (Plano de Implementação)
# ============================================================================

@pytest.mark.unit
class TestSpecialistServicerComplete:
    """
    Testes completos do SpecialistServicer conforme plano de implementação.

    Cobre:
    - EvaluatePlan com sucesso
    - HealthCheck retornando SERVING/NOT_SERVING
    - GetCapabilities com todos os campos
    - Tratamento de erros gRPC
    - Propagação de contexto (tenant_id, trace_id)
    """

    @pytest.fixture
    def mock_specialist_complete(self):
        """Mock completo de BaseSpecialist."""
        specialist = Mock()
        specialist.specialist_type = "test"
        specialist.version = "1.0.0"

        # Mock evaluate_plan
        specialist.evaluate_plan.return_value = {
            'opinion_id': 'test-opinion-123',
            'specialist_type': 'test',
            'specialist_version': '1.0.0',
            'opinion': {
                'confidence_score': 0.85,
                'risk_score': 0.15,
                'recommendation': 'approve',
                'reasoning_summary': 'Test reasoning summary',
                'reasoning_factors': [
                    {
                        'factor_name': 'design_patterns',
                        'weight': 0.25,
                        'score': 0.9,
                        'description': 'Good use of design patterns'
                    },
                    {
                        'factor_name': 'solid_principles',
                        'weight': 0.25,
                        'score': 0.85,
                        'description': 'Adherence to SOLID'
                    }
                ],
                'explainability_token': 'test-token-abc',
                'mitigations': [
                    {
                        'mitigation_id': 'mit-1',
                        'description': 'Consider caching strategy',
                        'priority': 'medium',
                        'estimated_impact': 0.2,
                        'required_actions': ['Add Redis cache', 'Configure TTL']
                    }
                ],
                'metadata': {
                    'domain': 'software_development',
                    'num_tasks': 5
                }
            }
        }

        # Mock health_check
        specialist.health_check.return_value = {
            'status': 'SERVING',
            'details': {
                'model_loaded': 'True',
                'ledger_connected': 'True',
                'cache_connected': 'True'
            }
        }

        # Mock get_capabilities
        specialist.get_capabilities.return_value = {
            'specialist_type': 'test',
            'version': '1.0.0',
            'supported_domains': ['software_development', 'data_analysis'],
            'supported_plan_versions': ['1.0.0', '1.1.0'],
            'metrics': {
                'average_processing_time_ms': 150.0,
                'accuracy_score': 0.92,
                'total_evaluations': 1000,
                'last_model_update': '2025-01-15T10:30:00'
            },
            'configuration': {
                'enable_caching': 'true',
                'max_batch_size': '10'
            }
        }

        return specialist

    @pytest.fixture
    def servicer_complete(self, mock_specialist_complete):
        """Instância de SpecialistServicer com mock completo."""
        return SpecialistServicer(mock_specialist_complete)

    def test_evaluate_plan_success_full_response(self, servicer_complete, mock_specialist_complete):
        """Testa EvaluatePlan com resposta completa."""
        # Arrange
        request = Mock()
        request.plan_id = 'test-plan-123'
        request.intent_id = 'test-intent-456'
        request.correlation_id = 'test-corr-789'
        request.trace_id = 'test-trace'
        request.span_id = 'test-span'
        request.cognitive_plan = b'{"plan_id": "test-plan-123", "tasks": []}'
        request.plan_version = '1.0.0'
        request.context = {'tenant_id': 'test-tenant'}
        request.timeout_ms = 5000

        context = Mock()
        context.invocation_metadata.return_value = []

        # Act
        with patch('neural_hive_specialists.grpc_server.PROTO_AVAILABLE', True):
            with patch('neural_hive_specialists.grpc_server.specialist_pb2') as mock_pb2:
                # Configure mocks para protobuf
                mock_pb2.ReasoningFactor.return_value = Mock()
                mock_pb2.MitigationSuggestion.return_value = Mock()
                mock_pb2.SpecialistOpinion.return_value = Mock()
                mock_pb2.EvaluatePlanResponse.return_value = Mock(
                    opinion_id='test-opinion-123',
                    specialist_type='test'
                )

                response = servicer_complete.EvaluatePlan(request, context)

                # Assert
                mock_specialist_complete.evaluate_plan.assert_called_once_with(request)
                assert mock_pb2.EvaluatePlanResponse.called
                assert mock_pb2.ReasoningFactor.called
                assert mock_pb2.MitigationSuggestion.called

    def test_evaluate_plan_propagates_tenant_id(self, servicer_complete, mock_specialist_complete):
        """Testa que tenant_id é propagado do metadata gRPC."""
        # Arrange
        request = Mock()
        request.plan_id = 'test-plan-123'
        request.intent_id = 'test-intent'
        request.correlation_id = 'test-corr'
        request.trace_id = 'test-trace'
        request.span_id = 'test-span'
        request.cognitive_plan = b'{}'
        request.context = {}

        context = Mock()
        # Simular metadata com x-tenant-id
        context.invocation_metadata.return_value = [('x-tenant-id', 'tenant-abc')]

        # Act
        with patch('neural_hive_specialists.grpc_server.PROTO_AVAILABLE', True):
            with patch('neural_hive_specialists.grpc_server.specialist_pb2') as mock_pb2:
                mock_pb2.EvaluatePlanResponse.return_value = Mock()
                mock_pb2.ReasoningFactor.return_value = Mock()
                mock_pb2.MitigationSuggestion.return_value = Mock()
                mock_pb2.SpecialistOpinion.return_value = Mock()

                with patch('neural_hive_specialists.grpc_server.logger') as mock_logger:
                    servicer_complete.EvaluatePlan(request, context)

                    # Assert - verificar que tenant_id foi propagado
                    # O tenant_id deve ser injetado no request.context
                    assert request.context.get('tenant_id') == 'tenant-abc'

    def test_evaluate_plan_grpc_error_invalid_argument(self, servicer_complete, mock_specialist_complete):
        """Testa EvaluatePlan com erro de argumento inválido."""
        # Arrange
        mock_specialist_complete.evaluate_plan.side_effect = ValueError("Invalid plan format")

        request = Mock()
        request.plan_id = 'invalid-plan'
        request.cognitive_plan = b'invalid'
        context = Mock()
        context.invocation_metadata.return_value = []

        # Act & Assert
        with pytest.raises(ValueError):
            servicer_complete.EvaluatePlan(request, context)

        context.set_code.assert_called_with(grpc.StatusCode.INVALID_ARGUMENT)

    def test_evaluate_plan_grpc_error_tenant_unknown(self, servicer_complete, mock_specialist_complete):
        """Testa EvaluatePlan com tenant desconhecido."""
        # Arrange
        mock_specialist_complete.evaluate_plan.side_effect = ValueError("Tenant desconhecido: xyz")

        request = Mock()
        request.plan_id = 'plan-123'
        request.cognitive_plan = b'{}'
        context = Mock()
        context.invocation_metadata.return_value = []

        # Act & Assert
        with pytest.raises(ValueError):
            servicer_complete.EvaluatePlan(request, context)

        context.set_code.assert_called_with(grpc.StatusCode.INVALID_ARGUMENT)
        assert 'Tenant inválido' in context.set_details.call_args[0][0]

    def test_evaluate_plan_grpc_error_tenant_inactive(self, servicer_complete, mock_specialist_complete):
        """Testa EvaluatePlan com tenant inativo."""
        # Arrange
        mock_specialist_complete.evaluate_plan.side_effect = ValueError("Tenant inativo: xyz")

        request = Mock()
        request.plan_id = 'plan-123'
        request.cognitive_plan = b'{}'
        context = Mock()
        context.invocation_metadata.return_value = []

        # Act & Assert
        with pytest.raises(ValueError):
            servicer_complete.EvaluatePlan(request, context)

        context.set_code.assert_called_with(grpc.StatusCode.PERMISSION_DENIED)

    def test_evaluate_plan_grpc_error_internal(self, servicer_complete, mock_specialist_complete):
        """Testa EvaluatePlan com erro interno."""
        # Arrange
        mock_specialist_complete.evaluate_plan.side_effect = RuntimeError("Internal error")

        request = Mock()
        request.plan_id = 'plan-123'
        request.cognitive_plan = b'{}'
        context = Mock()
        context.invocation_metadata.return_value = []

        # Act & Assert
        with pytest.raises(RuntimeError):
            servicer_complete.EvaluatePlan(request, context)

        context.set_code.assert_called_with(grpc.StatusCode.INTERNAL)

    def test_health_check_serving(self, servicer_complete, mock_specialist_complete):
        """Testa HealthCheck retornando SERVING."""
        # Arrange
        request = Mock()
        request.service_name = 'test'
        context = Mock()

        # Act
        with patch('neural_hive_specialists.grpc_server.PROTO_AVAILABLE', True):
            with patch('neural_hive_specialists.grpc_server.specialist_pb2') as mock_pb2:
                mock_pb2.HealthCheckResponse.SERVING = 1
                mock_pb2.HealthCheckResponse.NOT_SERVING = 2
                mock_pb2.HealthCheckResponse.UNKNOWN = 0
                mock_pb2.HealthCheckResponse.SERVICE_UNKNOWN = 3
                mock_pb2.HealthCheckResponse.return_value = Mock(status=1)

                response = servicer_complete.HealthCheck(request, context)

                # Assert
                mock_specialist_complete.health_check.assert_called_once()
                assert mock_pb2.HealthCheckResponse.called
                call_kwargs = mock_pb2.HealthCheckResponse.call_args[1]
                assert call_kwargs['status'] == mock_pb2.HealthCheckResponse.SERVING

    def test_health_check_not_serving(self, servicer_complete, mock_specialist_complete):
        """Testa HealthCheck retornando NOT_SERVING."""
        # Arrange
        mock_specialist_complete.health_check.return_value = {
            'status': 'NOT_SERVING',
            'details': {'model_loaded': 'False'}
        }

        request = Mock()
        context = Mock()

        # Act
        with patch('neural_hive_specialists.grpc_server.PROTO_AVAILABLE', True):
            with patch('neural_hive_specialists.grpc_server.specialist_pb2') as mock_pb2:
                mock_pb2.HealthCheckResponse.SERVING = 1
                mock_pb2.HealthCheckResponse.NOT_SERVING = 2
                mock_pb2.HealthCheckResponse.UNKNOWN = 0
                mock_pb2.HealthCheckResponse.SERVICE_UNKNOWN = 3
                mock_pb2.HealthCheckResponse.return_value = Mock(status=2)

                response = servicer_complete.HealthCheck(request, context)

                # Assert
                call_kwargs = mock_pb2.HealthCheckResponse.call_args[1]
                assert call_kwargs['status'] == mock_pb2.HealthCheckResponse.NOT_SERVING

    def test_health_check_details_serialization(self, servicer_complete, mock_specialist_complete):
        """Testa que details complexos são serializados como JSON."""
        # Arrange
        mock_specialist_complete.health_check.return_value = {
            'status': 'SERVING',
            'details': {
                'simple_value': 'string',
                'complex_dict': {'nested': 'value'},
                'complex_list': [1, 2, 3]
            }
        }

        request = Mock()
        context = Mock()

        # Act
        with patch('neural_hive_specialists.grpc_server.PROTO_AVAILABLE', True):
            with patch('neural_hive_specialists.grpc_server.specialist_pb2') as mock_pb2:
                mock_pb2.HealthCheckResponse.SERVING = 1
                mock_pb2.HealthCheckResponse.return_value = Mock()

                servicer_complete.HealthCheck(request, context)

                # Assert - verificar que details foi convertido para strings
                call_kwargs = mock_pb2.HealthCheckResponse.call_args[1]
                details = call_kwargs['details']
                assert details['simple_value'] == 'string'
                assert '"nested"' in details['complex_dict']  # JSON serializado
                assert '[1, 2, 3]' in details['complex_list']  # JSON serializado

    def test_get_capabilities_full_response(self, servicer_complete, mock_specialist_complete):
        """Testa GetCapabilities com resposta completa."""
        # Arrange
        request = Mock()
        context = Mock()

        # Act
        with patch('neural_hive_specialists.grpc_server.PROTO_AVAILABLE', True):
            with patch('neural_hive_specialists.grpc_server.specialist_pb2') as mock_pb2:
                mock_pb2.CapabilityMetrics.return_value = Mock()
                mock_pb2.GetCapabilitiesResponse.return_value = Mock(
                    specialist_type='test',
                    version='1.0.0'
                )

                response = servicer_complete.GetCapabilities(request, context)

                # Assert
                mock_specialist_complete.get_capabilities.assert_called_once()
                assert mock_pb2.GetCapabilitiesResponse.called

                call_kwargs = mock_pb2.GetCapabilitiesResponse.call_args[1]
                assert call_kwargs['specialist_type'] == 'test'
                assert call_kwargs['version'] == '1.0.0'
                assert 'software_development' in call_kwargs['supported_domains']
                assert '1.0.0' in call_kwargs['supported_plan_versions']

    def test_get_capabilities_with_valid_iso8601_timestamp(self, servicer_complete, mock_specialist_complete):
        """Testa GetCapabilities com timestamp ISO-8601 válido."""
        # Arrange
        mock_specialist_complete.get_capabilities.return_value = {
            'specialist_type': 'test',
            'version': '1.0.0',
            'supported_domains': ['test'],
            'supported_plan_versions': ['1.0.0'],
            'metrics': {
                'average_processing_time_ms': 100.0,
                'accuracy_score': 0.95,
                'total_evaluations': 42,
                'last_model_update': '2025-01-15T10:30:00Z'  # Com 'Z'
            },
            'configuration': {}
        }

        request = Mock()
        context = Mock()

        # Act
        with patch('neural_hive_specialists.grpc_server.PROTO_AVAILABLE', True):
            with patch('neural_hive_specialists.grpc_server.specialist_pb2') as mock_pb2:
                mock_pb2.CapabilityMetrics.return_value = Mock()
                mock_pb2.GetCapabilitiesResponse.return_value = Mock()

                servicer_complete.GetCapabilities(request, context)

                # Assert - CapabilityMetrics deve incluir last_model_update
                assert mock_pb2.CapabilityMetrics.called
                call_kwargs = mock_pb2.CapabilityMetrics.call_args[1]
                assert 'last_model_update' in call_kwargs

    def test_get_capabilities_handles_exception(self, servicer_complete, mock_specialist_complete):
        """Testa GetCapabilities com exceção."""
        # Arrange
        mock_specialist_complete.get_capabilities.side_effect = RuntimeError("Database error")

        request = Mock()
        context = Mock()

        # Act & Assert
        with pytest.raises(RuntimeError):
            servicer_complete.GetCapabilities(request, context)

        context.set_code.assert_called_with(grpc.StatusCode.INTERNAL)


@pytest.mark.unit
class TestBuildEvaluatePlanResponseComplete:
    """Testes completos do método _build_evaluate_plan_response."""

    @pytest.fixture
    def servicer(self):
        """Cria servicer para testes."""
        specialist = Mock()
        specialist.specialist_type = 'test'
        return SpecialistServicer(specialist)

    def test_build_response_with_explainability(self, servicer):
        """Testa construção de resposta com metadados de explainability."""
        eval_result = {
            'opinion_id': 'opinion-123',
            'specialist_type': 'test',
            'specialist_version': '1.0.0',
            'opinion': {
                'confidence_score': 0.85,
                'risk_score': 0.2,
                'recommendation': 'approve',
                'reasoning_summary': 'Test',
                'reasoning_factors': [],
                'explainability_token': 'token-123',
                'explainability': {
                    'method': 'shap',
                    'model_version': '1.0.0',
                    'model_type': 'RandomForest',
                    'feature_importances': [
                        {
                            'feature_name': 'task_count',
                            'importance': 0.35,
                            'contribution': 'positive'
                        },
                        {
                            'feature_name': 'dependency_ratio',
                            'importance': 0.25,
                            'contribution': 'negative'
                        }
                    ]
                },
                'mitigations': [],
                'metadata': {}
            }
        }

        with patch('neural_hive_specialists.grpc_server.specialist_pb2') as mock_pb2:
            mock_pb2.ReasoningFactor.return_value = Mock()
            mock_pb2.MitigationSuggestion.return_value = Mock()
            mock_pb2.FeatureImportance.return_value = Mock()
            mock_pb2.ExplainabilityMetadata.return_value = Mock()
            mock_pb2.SpecialistOpinion.return_value = Mock()
            mock_pb2.EvaluatePlanResponse.return_value = Mock()

            servicer._build_evaluate_plan_response(eval_result, processing_time_ms=150)

            # Assert - ExplainabilityMetadata deve ser construído
            assert mock_pb2.ExplainabilityMetadata.called
            exp_call_kwargs = mock_pb2.ExplainabilityMetadata.call_args[1]
            assert exp_call_kwargs['method'] == 'shap'
            assert exp_call_kwargs['model_version'] == '1.0.0'
            assert exp_call_kwargs['model_type'] == 'RandomForest'

            # Assert - FeatureImportance deve ser construído para cada feature
            assert mock_pb2.FeatureImportance.call_count == 2

    def test_build_response_without_explainability(self, servicer):
        """Testa construção de resposta sem metadados de explainability."""
        eval_result = {
            'opinion_id': 'opinion-123',
            'specialist_type': 'test',
            'specialist_version': '1.0.0',
            'opinion': {
                'confidence_score': 0.85,
                'risk_score': 0.2,
                'recommendation': 'approve',
                'reasoning_summary': 'Test',
                'reasoning_factors': [],
                'explainability_token': 'token-123',
                # Sem 'explainability'
                'mitigations': [],
                'metadata': {}
            }
        }

        with patch('neural_hive_specialists.grpc_server.specialist_pb2') as mock_pb2:
            mock_pb2.ReasoningFactor.return_value = Mock()
            mock_pb2.MitigationSuggestion.return_value = Mock()
            mock_pb2.SpecialistOpinion.return_value = Mock()
            mock_pb2.EvaluatePlanResponse.return_value = Mock()

            servicer._build_evaluate_plan_response(eval_result, processing_time_ms=150)

            # Assert - ExplainabilityMetadata NÃO deve ser construído
            assert not mock_pb2.ExplainabilityMetadata.called

    def test_build_response_metadata_converted_to_strings(self, servicer):
        """Testa que metadata é convertido para map<string, string>."""
        eval_result = {
            'opinion_id': 'opinion-123',
            'specialist_type': 'test',
            'specialist_version': '1.0.0',
            'opinion': {
                'confidence_score': 0.85,
                'risk_score': 0.2,
                'recommendation': 'approve',
                'reasoning_summary': 'Test',
                'reasoning_factors': [],
                'explainability_token': 'token-123',
                'mitigations': [],
                'metadata': {
                    'string_value': 'test',
                    'int_value': 42,
                    'float_value': 3.14,
                    'bool_value': True
                }
            }
        }

        with patch('neural_hive_specialists.grpc_server.specialist_pb2') as mock_pb2:
            mock_pb2.ReasoningFactor.return_value = Mock()
            mock_pb2.MitigationSuggestion.return_value = Mock()
            mock_pb2.SpecialistOpinion.return_value = Mock()
            mock_pb2.EvaluatePlanResponse.return_value = Mock()

            servicer._build_evaluate_plan_response(eval_result, processing_time_ms=150)

            # Assert - SpecialistOpinion deve receber metadata como strings
            opinion_call_kwargs = mock_pb2.SpecialistOpinion.call_args[1]
            metadata = opinion_call_kwargs['metadata']
            assert metadata['string_value'] == 'test'
            assert metadata['int_value'] == '42'
            assert metadata['float_value'] == '3.14'
            assert metadata['bool_value'] == 'True'

    def test_build_response_timestamp_creation(self, servicer):
        """Testa que timestamp evaluated_at é criado corretamente."""
        eval_result = {
            'opinion_id': 'opinion-123',
            'specialist_type': 'test',
            'specialist_version': '1.0.0',
            'opinion': {
                'confidence_score': 0.85,
                'risk_score': 0.2,
                'recommendation': 'approve',
                'reasoning_summary': 'Test',
                'reasoning_factors': [],
                'explainability_token': 'token-123',
                'mitigations': [],
                'metadata': {}
            }
        }

        with patch('neural_hive_specialists.grpc_server.specialist_pb2') as mock_pb2:
            mock_pb2.ReasoningFactor.return_value = Mock()
            mock_pb2.MitigationSuggestion.return_value = Mock()
            mock_pb2.SpecialistOpinion.return_value = Mock()
            mock_pb2.EvaluatePlanResponse.return_value = Mock()

            servicer._build_evaluate_plan_response(eval_result, processing_time_ms=150)

            # Assert - EvaluatePlanResponse deve incluir evaluated_at
            response_call_kwargs = mock_pb2.EvaluatePlanResponse.call_args[1]
            assert 'evaluated_at' in response_call_kwargs
            timestamp = response_call_kwargs['evaluated_at']
            assert isinstance(timestamp, Timestamp)
            assert timestamp.seconds > 0


@pytest.mark.unit
class TestHealthServicer:
    """Testes para HealthServicer."""

    def test_check_serving(self):
        """Testa Check quando status é SERVING."""
        from neural_hive_specialists.grpc_server import HealthServicer

        specialist = Mock()
        specialist.health_check.return_value = {
            'status': 'SERVING',
            'details': {}
        }

        servicer = HealthServicer(specialist)
        request = Mock()
        context = Mock()

        response = servicer.Check(request, context)

        assert response['status'] == 1  # SERVING

    def test_check_not_serving(self):
        """Testa Check quando status é NOT_SERVING."""
        from neural_hive_specialists.grpc_server import HealthServicer

        specialist = Mock()
        specialist.health_check.return_value = {
            'status': 'NOT_SERVING',
            'details': {}
        }

        servicer = HealthServicer(specialist)
        request = Mock()
        context = Mock()

        response = servicer.Check(request, context)

        assert response['status'] == 2  # NOT_SERVING

    def test_check_handles_exception(self):
        """Testa Check quando ocorre exceção."""
        from neural_hive_specialists.grpc_server import HealthServicer

        specialist = Mock()
        specialist.health_check.side_effect = RuntimeError("Error")

        servicer = HealthServicer(specialist)
        request = Mock()
        context = Mock()

        response = servicer.Check(request, context)

        assert response['status'] == 2  # NOT_SERVING

    def test_watch_streaming(self):
        """Testa Watch (streaming)."""
        from neural_hive_specialists.grpc_server import HealthServicer

        specialist = Mock()
        specialist.health_check.return_value = {
            'status': 'SERVING',
            'details': {}
        }

        servicer = HealthServicer(specialist)
        request = Mock()
        context = Mock()

        responses = list(servicer.Watch(request, context))

        assert len(responses) == 1
        assert responses[0]['status'] == 1  # SERVING
