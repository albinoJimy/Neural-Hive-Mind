"""
Testes de integração gRPC para especialistas.

Valida comunicação gRPC real com os especialistas (quando disponíveis).

Estes testes requerem:
- Especialistas rodando localmente ou em Kubernetes
- Conexão de rede funcional

Marcar com @pytest.mark.integration para execução condicional.
"""

import pytest
import json
import grpc
from typing import Tuple, Generator

# Tentar importar protobuf stubs
try:
    from neural_hive_specialists.proto_gen import specialist_pb2, specialist_pb2_grpc
    PROTO_AVAILABLE = True
except ImportError:
    PROTO_AVAILABLE = False
    specialist_pb2 = None
    specialist_pb2_grpc = None


# Lista de especialistas a testar com suas portas padrão
SPECIALISTS = [
    ('architecture', 'specialist-architecture', 50051),
    ('behavior', 'specialist-behavior', 50052),
    ('business', 'specialist-business', 50053),
    ('evolution', 'specialist-evolution', 50054),
    ('technical', 'specialist-technical', 50055),
]


def _create_test_cognitive_plan(specialist_type: str) -> dict:
    """Cria plano cognitivo de teste para um especialista."""
    return {
        'plan_id': f'test-plan-{specialist_type}-integration',
        'intent_id': 'test-intent-integration',
        'correlation_id': 'test-correlation-integration',
        'trace_id': 'test-trace-integration',
        'span_id': 'test-span-integration',
        'version': '1.0.0',
        'original_domain': 'software_development',
        'original_priority': 'normal',
        'original_security_level': 'public',
        'tasks': [
            {
                'task_id': 'task-1',
                'task_type': 'analysis',
                'name': 'Analyze Architecture',
                'description': f'Test task for {specialist_type} specialist - '
                              'analyze software architecture using design patterns, '
                              'SOLID principles, and modular design',
                'dependencies': [],
                'estimated_duration_ms': 1000,
                'required_capabilities': ['analysis'],
                'parameters': {'mode': 'test'},
                'metadata': {}
            },
            {
                'task_id': 'task-2',
                'task_type': 'validation',
                'name': 'Validate Results',
                'description': 'Validate and test the analysis results',
                'dependencies': ['task-1'],
                'estimated_duration_ms': 500,
                'required_capabilities': ['validation'],
                'parameters': {},
                'metadata': {}
            }
        ],
        'execution_order': ['task-1', 'task-2'],
        'risk_score': 0.3,
        'risk_band': 'low',
        'complexity_score': 0.5,
        'metadata': {
            'test_mode': 'integration',
            'specialist': specialist_type
        }
    }


@pytest.fixture(params=SPECIALISTS, ids=[s[0] for s in SPECIALISTS])
def specialist_channel(request) -> Generator[Tuple[str, grpc.Channel], None, None]:
    """
    Cria canal gRPC para cada especialista.

    Yields:
        Tuple de (specialist_type, channel)
    """
    if not PROTO_AVAILABLE:
        pytest.skip("Protobuf stubs not available")

    specialist_type, service_name, port = request.param

    # Tentar conectar ao especialista
    channel = grpc.insecure_channel(f'localhost:{port}')

    # Verificar se o canal está conectado (com timeout)
    try:
        grpc.channel_ready_future(channel).result(timeout=2)
    except grpc.FutureTimeoutError:
        channel.close()
        pytest.skip(f"Specialist {specialist_type} not available at localhost:{port}")

    yield specialist_type, channel

    channel.close()


@pytest.fixture
def grpc_stub(specialist_channel) -> Tuple[str, 'specialist_pb2_grpc.SpecialistServiceStub']:
    """Cria stub do cliente gRPC."""
    specialist_type, channel = specialist_channel
    stub = specialist_pb2_grpc.SpecialistServiceStub(channel)
    return specialist_type, stub


@pytest.mark.integration
@pytest.mark.skipif(not PROTO_AVAILABLE, reason="Protobuf stubs not available")
class TestEvaluatePlanIntegration:
    """Testes de integração para EvaluatePlan."""

    def test_evaluate_plan_returns_valid_response(self, grpc_stub):
        """Testa EvaluatePlan em especialista real."""
        specialist_type, stub = grpc_stub

        # Criar plano cognitivo de teste
        cognitive_plan = _create_test_cognitive_plan(specialist_type)

        # Criar request
        request = specialist_pb2.EvaluatePlanRequest(
            plan_id=cognitive_plan['plan_id'],
            intent_id=cognitive_plan['intent_id'],
            correlation_id=cognitive_plan['correlation_id'],
            trace_id=cognitive_plan['trace_id'],
            span_id=cognitive_plan['span_id'],
            cognitive_plan=json.dumps(cognitive_plan).encode('utf-8'),
            plan_version='1.0.0',
            timeout_ms=5000
        )

        # Executar chamada gRPC
        response = stub.EvaluatePlan(request, timeout=10)

        # Validações estruturais
        assert response.opinion_id, "opinion_id deve estar presente"
        assert response.specialist_type == specialist_type, \
            f"specialist_type deve ser {specialist_type}"
        assert response.specialist_version, "specialist_version deve estar presente"

        # Validações de opinion
        opinion = response.opinion
        assert 0.0 <= opinion.confidence_score <= 1.0, \
            "confidence_score deve estar entre 0 e 1"
        assert 0.0 <= opinion.risk_score <= 1.0, \
            "risk_score deve estar entre 0 e 1"
        assert opinion.recommendation in ['approve', 'reject', 'review_required', 'conditional'], \
            f"recommendation inválida: {opinion.recommendation}"
        assert opinion.reasoning_summary, "reasoning_summary deve estar presente"

        # Validações de processamento
        assert response.processing_time_ms > 0, "processing_time_ms deve ser positivo"
        assert response.evaluated_at.seconds > 0, "evaluated_at deve ser válido"

    def test_evaluate_plan_returns_reasoning_factors(self, grpc_stub):
        """Testa que EvaluatePlan retorna fatores de raciocínio."""
        specialist_type, stub = grpc_stub

        cognitive_plan = _create_test_cognitive_plan(specialist_type)

        request = specialist_pb2.EvaluatePlanRequest(
            plan_id=cognitive_plan['plan_id'],
            intent_id=cognitive_plan['intent_id'],
            correlation_id=cognitive_plan['correlation_id'],
            trace_id=cognitive_plan['trace_id'],
            span_id=cognitive_plan['span_id'],
            cognitive_plan=json.dumps(cognitive_plan).encode('utf-8'),
            plan_version='1.0.0',
            timeout_ms=5000
        )

        response = stub.EvaluatePlan(request, timeout=10)

        # Validar reasoning_factors
        assert len(response.opinion.reasoning_factors) > 0, \
            "Deve haver pelo menos um reasoning_factor"

        for factor in response.opinion.reasoning_factors:
            assert factor.factor_name, "factor_name deve estar presente"
            assert 0.0 <= factor.weight <= 1.0, \
                f"weight deve estar entre 0 e 1: {factor.weight}"
            assert 0.0 <= factor.score <= 1.0, \
                f"score deve estar entre 0 e 1: {factor.score}"


@pytest.mark.integration
@pytest.mark.skipif(not PROTO_AVAILABLE, reason="Protobuf stubs not available")
class TestHealthCheckIntegration:
    """Testes de integração para HealthCheck."""

    def test_health_check_returns_serving(self, grpc_stub):
        """Testa HealthCheck em especialista real."""
        specialist_type, stub = grpc_stub

        request = specialist_pb2.HealthCheckRequest(service_name=specialist_type)
        response = stub.HealthCheck(request, timeout=5)

        # Deve retornar SERVING ou NOT_SERVING (nunca UNKNOWN em produção)
        assert response.status in [
            specialist_pb2.HealthCheckResponse.SERVING,
            specialist_pb2.HealthCheckResponse.NOT_SERVING
        ], f"status inválido: {response.status}"

    def test_health_check_returns_details(self, grpc_stub):
        """Testa que HealthCheck retorna detalhes."""
        specialist_type, stub = grpc_stub

        request = specialist_pb2.HealthCheckRequest(service_name=specialist_type)
        response = stub.HealthCheck(request, timeout=5)

        # Deve incluir pelo menos 'model_loaded' nos details
        assert 'model_loaded' in response.details, \
            "details deve incluir 'model_loaded'"


@pytest.mark.integration
@pytest.mark.skipif(not PROTO_AVAILABLE, reason="Protobuf stubs not available")
class TestGetCapabilitiesIntegration:
    """Testes de integração para GetCapabilities."""

    def test_get_capabilities_returns_valid_response(self, grpc_stub):
        """Testa GetCapabilities em especialista real."""
        specialist_type, stub = grpc_stub

        request = specialist_pb2.GetCapabilitiesRequest()
        response = stub.GetCapabilities(request, timeout=5)

        # Validações estruturais
        assert response.specialist_type == specialist_type, \
            f"specialist_type deve ser {specialist_type}"
        assert response.version, "version deve estar presente"
        assert len(response.supported_domains) > 0, \
            "supported_domains deve ter pelo menos um item"
        assert len(response.supported_plan_versions) > 0, \
            "supported_plan_versions deve ter pelo menos um item"

    def test_get_capabilities_returns_metrics(self, grpc_stub):
        """Testa que GetCapabilities retorna métricas."""
        specialist_type, stub = grpc_stub

        request = specialist_pb2.GetCapabilitiesRequest()
        response = stub.GetCapabilities(request, timeout=5)

        # Metrics pode ser opcional, mas se presente deve ter campos válidos
        if response.HasField('metrics'):
            metrics = response.metrics
            assert metrics.average_processing_time_ms >= 0, \
                "average_processing_time_ms deve ser >= 0"
            assert 0.0 <= metrics.accuracy_score <= 1.0, \
                "accuracy_score deve estar entre 0 e 1"
            assert metrics.total_evaluations >= 0, \
                "total_evaluations deve ser >= 0"


@pytest.mark.integration
@pytest.mark.skipif(not PROTO_AVAILABLE, reason="Protobuf stubs not available")
class TestGrpcErrorHandlingIntegration:
    """Testes de integração para tratamento de erros gRPC."""

    def test_invalid_plan_returns_invalid_argument(self, grpc_stub):
        """Testa que plano inválido retorna INVALID_ARGUMENT."""
        specialist_type, stub = grpc_stub

        # Criar request com plano inválido
        request = specialist_pb2.EvaluatePlanRequest(
            plan_id='invalid-plan',
            intent_id='test-intent',
            correlation_id='test-corr',
            trace_id='test-trace',
            span_id='test-span',
            cognitive_plan=b'not-valid-json',  # JSON inválido
            plan_version='1.0.0',
            timeout_ms=5000
        )

        # Deve retornar erro (INVALID_ARGUMENT ou INTERNAL)
        with pytest.raises(grpc.RpcError) as exc_info:
            stub.EvaluatePlan(request, timeout=10)

        # Aceitar INVALID_ARGUMENT ou INTERNAL (depende da implementação)
        assert exc_info.value.code() in [
            grpc.StatusCode.INVALID_ARGUMENT,
            grpc.StatusCode.INTERNAL
        ]

    def test_empty_plan_returns_error(self, grpc_stub):
        """Testa que plano vazio retorna erro."""
        specialist_type, stub = grpc_stub

        # Criar request com plano vazio
        request = specialist_pb2.EvaluatePlanRequest(
            plan_id='',  # ID vazio
            intent_id='test-intent',
            cognitive_plan=b'{}',  # Plano vazio mas JSON válido
            plan_version='1.0.0',
            timeout_ms=5000
        )

        # Pode retornar erro ou resposta com baixa confiança
        # (depende da implementação)
        try:
            response = stub.EvaluatePlan(request, timeout=10)
            # Se não falhar, confidence deve ser baixa para plano vazio
            assert response.opinion.confidence_score <= 0.6, \
                "Plano vazio deve ter baixa confiança"
        except grpc.RpcError:
            # Erro é aceitável para plano inválido
            pass


@pytest.mark.integration
@pytest.mark.skipif(not PROTO_AVAILABLE, reason="Protobuf stubs not available")
class TestGrpcMetadataIntegration:
    """Testes de integração para propagação de metadados gRPC."""

    def test_tenant_id_propagated_via_metadata(self, grpc_stub):
        """Testa que tenant_id é propagado via metadata."""
        specialist_type, stub = grpc_stub

        cognitive_plan = _create_test_cognitive_plan(specialist_type)

        request = specialist_pb2.EvaluatePlanRequest(
            plan_id=cognitive_plan['plan_id'],
            intent_id=cognitive_plan['intent_id'],
            correlation_id=cognitive_plan['correlation_id'],
            trace_id=cognitive_plan['trace_id'],
            span_id=cognitive_plan['span_id'],
            cognitive_plan=json.dumps(cognitive_plan).encode('utf-8'),
            plan_version='1.0.0',
            timeout_ms=5000
        )

        # Adicionar tenant_id via metadata
        metadata = [('x-tenant-id', 'test-tenant-integration')]

        # Chamada deve funcionar com metadata
        response = stub.EvaluatePlan(request, timeout=10, metadata=metadata)

        # Resposta deve ser válida
        assert response.opinion_id, "Resposta deve ter opinion_id"
        assert response.specialist_type == specialist_type


# ============================================================================
# Testes de Performance (opcional)
# ============================================================================

@pytest.mark.integration
@pytest.mark.performance
@pytest.mark.skipif(not PROTO_AVAILABLE, reason="Protobuf stubs not available")
class TestGrpcPerformanceIntegration:
    """Testes de performance gRPC (opcional)."""

    def test_evaluate_plan_latency(self, grpc_stub):
        """Testa latência de EvaluatePlan."""
        import time

        specialist_type, stub = grpc_stub

        cognitive_plan = _create_test_cognitive_plan(specialist_type)

        request = specialist_pb2.EvaluatePlanRequest(
            plan_id=cognitive_plan['plan_id'],
            intent_id=cognitive_plan['intent_id'],
            correlation_id=cognitive_plan['correlation_id'],
            trace_id=cognitive_plan['trace_id'],
            span_id=cognitive_plan['span_id'],
            cognitive_plan=json.dumps(cognitive_plan).encode('utf-8'),
            plan_version='1.0.0',
            timeout_ms=5000
        )

        # Medir latência
        start_time = time.time()
        response = stub.EvaluatePlan(request, timeout=10)
        elapsed_ms = (time.time() - start_time) * 1000

        # Latência deve ser menor que 5 segundos para teste básico
        assert elapsed_ms < 5000, \
            f"Latência muito alta: {elapsed_ms}ms"

        # processing_time_ms reportado deve ser coerente
        assert response.processing_time_ms < elapsed_ms * 1.1, \
            "processing_time_ms não pode ser maior que elapsed_ms"

    def test_health_check_fast_response(self, grpc_stub):
        """Testa que HealthCheck responde rapidamente."""
        import time

        specialist_type, stub = grpc_stub

        request = specialist_pb2.HealthCheckRequest(service_name=specialist_type)

        # Medir latência
        start_time = time.time()
        response = stub.HealthCheck(request, timeout=5)
        elapsed_ms = (time.time() - start_time) * 1000

        # HealthCheck deve responder em menos de 500ms
        assert elapsed_ms < 500, \
            f"HealthCheck muito lento: {elapsed_ms}ms"
