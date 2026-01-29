"""
Testes de integração E2E para servidor gRPC com autenticação JWT.

Este módulo testa o servidor gRPC completo com interceptor de autenticação,
incluindo chamadas reais aos métodos gRPC e validação de Health Check bypass.
"""
import pytest
import grpc
import jwt
import time
import threading
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, MagicMock

from neural_hive_specialists.grpc_server import create_grpc_server_with_observability
from neural_hive_specialists.config import SpecialistConfig
from neural_hive_specialists.metrics import SpecialistMetrics

try:
    from neural_hive_specialists.proto_gen import specialist_pb2, specialist_pb2_grpc
    from grpc_health.v1 import health_pb2, health_pb2_grpc

    PROTO_AVAILABLE = True
except ImportError:
    PROTO_AVAILABLE = False
    pytest.skip("Protobuf stubs não disponíveis", allow_module_level=True)


# Porta de teste única para evitar conflitos
TEST_PORT = 50099


@pytest.fixture(scope="module")
def config():
    """Configuração de teste com JWT habilitado."""
    return SpecialistConfig(
        specialist_type="test-specialist",
        service_name="test-service",
        mlflow_tracking_uri="http://mlflow:5000",
        mlflow_experiment_name="test",
        mlflow_model_name="test-model",
        mongodb_uri="mongodb://localhost:27017",
        redis_cluster_nodes="localhost:6379",
        neo4j_uri="bolt://localhost:7687",
        neo4j_password="test",
        jwt_secret_key="test-secret-key-with-minimum-32-chars-required-for-e2e",
        jwt_algorithm="HS256",
        jwt_issuer="neural-hive",
        jwt_audience="specialists",
        enable_jwt_auth=True,
        jwt_public_endpoints=[
            "HealthCheck",
            "/grpc.health.v1.Health/Check",
            "/grpc.health.v1.Health/Watch",
        ],
        grpc_port=TEST_PORT,
        environment="test",
    )


@pytest.fixture(scope="module")
def mock_specialist(config):
    """Mock de especialista para testes."""
    specialist = Mock()
    specialist.specialist_type = "test-specialist"
    specialist.config = config
    specialist.metrics = SpecialistMetrics(config, "test-specialist")

    # Mock de métodos
    specialist.health_check.return_value = {"status": "SERVING", "details": {}}

    specialist.get_capabilities.return_value = {
        "specialist_type": "test-specialist",
        "version": "1.0.0",
        "supported_domains": ["test"],
        "supported_plan_versions": ["1.0.0"],
        "metrics": {},
        "configuration": {},
    }

    specialist.evaluate_plan.return_value = {
        "opinion_id": "test-opinion-123",
        "specialist_type": "test-specialist",
        "specialist_version": "1.0.0",
        "opinion": {
            "confidence_score": 0.95,
            "risk_score": 0.1,
            "recommendation": "approve",
            "reasoning_summary": "Test evaluation",
            "reasoning_factors": [],
            "explainability_token": "",
            "mitigations": [],
            "metadata": {},
        },
    }

    return specialist


@pytest.fixture(scope="module")
def server(config, mock_specialist):
    """Inicia servidor gRPC de teste."""
    grpc_server = create_grpc_server_with_observability(mock_specialist, config)
    grpc_server.start()

    # Aguardar servidor iniciar
    time.sleep(0.5)

    yield grpc_server

    # Cleanup
    grpc_server.stop(grace=1)


@pytest.fixture
def valid_token(config):
    """Gera token JWT válido."""
    payload = {
        "sub": "consensus-engine",
        "service_type": "consensus-engine",
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "iss": config.jwt_issuer,
        "aud": config.jwt_audience,
    }
    return jwt.encode(payload, config.jwt_secret_key, algorithm=config.jwt_algorithm)


@pytest.fixture
def expired_token(config):
    """Gera token JWT expirado."""
    payload = {
        "sub": "consensus-engine",
        "service_type": "consensus-engine",
        "iat": datetime.now(timezone.utc) - timedelta(hours=2),
        "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        "iss": config.jwt_issuer,
        "aud": config.jwt_audience,
    }
    return jwt.encode(payload, config.jwt_secret_key, algorithm=config.jwt_algorithm)


@pytest.fixture
def invalid_token(config):
    """Gera token JWT com assinatura inválida."""
    payload = {
        "sub": "consensus-engine",
        "service_type": "consensus-engine",
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "iss": config.jwt_issuer,
        "aud": config.jwt_audience,
    }
    return jwt.encode(
        payload,
        "wrong-secret-key-minimum-32-chars-invalid",
        algorithm=config.jwt_algorithm,
    )


class TestHealthCheckBypass:
    """Testes de bypass de autenticação para Health Check."""

    def test_grpc_health_check_without_token(self, server, config):
        """Testa que Health/Check funciona sem token JWT."""
        channel = grpc.insecure_channel(f"localhost:{TEST_PORT}")
        stub = health_pb2_grpc.HealthStub(channel)

        try:
            # Chamar Check sem metadata de autenticação
            request = health_pb2.HealthCheckRequest(service="")
            response = stub.Check(request, timeout=2)

            # Deve retornar SERVING sem exigir autenticação
            assert response.status == health_pb2.HealthCheckResponse.SERVING

        finally:
            channel.close()

    def test_grpc_health_watch_without_token(self, server, config):
        """Testa que Health/Watch (streaming) funciona sem token JWT."""
        channel = grpc.insecure_channel(f"localhost:{TEST_PORT}")
        stub = health_pb2_grpc.HealthStub(channel)

        try:
            # Chamar Watch sem metadata de autenticação (método streaming)
            request = health_pb2.HealthCheckRequest(service="")
            responses = stub.Watch(request, timeout=2)

            # Deve retornar pelo menos uma resposta sem exigir autenticação
            response = next(responses)
            assert response.status == health_pb2.HealthCheckResponse.SERVING

        finally:
            channel.close()

    def test_specialist_health_check_without_token(self, server, config):
        """Testa que SpecialistService/HealthCheck funciona sem token."""
        channel = grpc.insecure_channel(f"localhost:{TEST_PORT}")
        stub = specialist_pb2_grpc.SpecialistServiceStub(channel)

        try:
            # Chamar HealthCheck sem metadata de autenticação
            request = specialist_pb2.HealthCheckRequest()
            response = stub.HealthCheck(request, timeout=2)

            # Deve retornar sucesso sem exigir autenticação
            assert response.status == specialist_pb2.HealthCheckResponse.SERVING

        finally:
            channel.close()


class TestAuthenticatedRequests:
    """Testes de requisições autenticadas."""

    def test_evaluate_plan_with_valid_token(
        self, server, config, valid_token, mock_specialist
    ):
        """Testa EvaluatePlan com token válido."""
        channel = grpc.insecure_channel(f"localhost:{TEST_PORT}")
        stub = specialist_pb2_grpc.SpecialistServiceStub(channel)

        try:
            # Criar metadata com token
            metadata = [("authorization", f"Bearer {valid_token}")]

            # Chamar EvaluatePlan
            request = specialist_pb2.EvaluatePlanRequest(
                plan_id="test-plan-123",
                intent_id="test-intent-456",
                trace_id="test-trace-789",
                plan=specialist_pb2.ExecutionPlan(
                    plan_id="test-plan-123", description="Test plan"
                ),
            )
            response = stub.EvaluatePlan(request, metadata=metadata, timeout=2)

            # Deve retornar resposta bem-sucedida
            assert response.opinion_id == "test-opinion-123"
            assert response.specialist_type == "test-specialist"

            # Verificar que método do mock foi chamado
            mock_specialist.evaluate_plan.assert_called()

        finally:
            channel.close()

    def test_evaluate_plan_without_token(self, server, config):
        """Testa EvaluatePlan sem token - deve falhar com UNAUTHENTICATED."""
        channel = grpc.insecure_channel(f"localhost:{TEST_PORT}")
        stub = specialist_pb2_grpc.SpecialistServiceStub(channel)

        try:
            request = specialist_pb2.EvaluatePlanRequest(
                plan_id="test-plan-123",
                intent_id="test-intent-456",
                trace_id="test-trace-789",
                plan=specialist_pb2.ExecutionPlan(
                    plan_id="test-plan-123", description="Test plan"
                ),
            )

            # Deve lançar exceção UNAUTHENTICATED
            with pytest.raises(grpc.RpcError) as exc_info:
                stub.EvaluatePlan(request, timeout=2)

            assert exc_info.value.code() == grpc.StatusCode.UNAUTHENTICATED
            assert "Missing authorization header" in exc_info.value.details()

        finally:
            channel.close()

    def test_evaluate_plan_with_expired_token(self, server, config, expired_token):
        """Testa EvaluatePlan com token expirado - deve falhar com UNAUTHENTICATED."""
        channel = grpc.insecure_channel(f"localhost:{TEST_PORT}")
        stub = specialist_pb2_grpc.SpecialistServiceStub(channel)

        try:
            metadata = [("authorization", f"Bearer {expired_token}")]

            request = specialist_pb2.EvaluatePlanRequest(
                plan_id="test-plan-123",
                intent_id="test-intent-456",
                trace_id="test-trace-789",
                plan=specialist_pb2.ExecutionPlan(
                    plan_id="test-plan-123", description="Test plan"
                ),
            )

            # Deve lançar exceção UNAUTHENTICATED
            with pytest.raises(grpc.RpcError) as exc_info:
                stub.EvaluatePlan(request, metadata=metadata, timeout=2)

            assert exc_info.value.code() == grpc.StatusCode.UNAUTHENTICATED
            assert "expired" in exc_info.value.details().lower()

        finally:
            channel.close()

    def test_evaluate_plan_with_invalid_token(self, server, config, invalid_token):
        """Testa EvaluatePlan com token inválido - deve falhar com UNAUTHENTICATED."""
        channel = grpc.insecure_channel(f"localhost:{TEST_PORT}")
        stub = specialist_pb2_grpc.SpecialistServiceStub(channel)

        try:
            metadata = [("authorization", f"Bearer {invalid_token}")]

            request = specialist_pb2.EvaluatePlanRequest(
                plan_id="test-plan-123",
                intent_id="test-intent-456",
                trace_id="test-trace-789",
                plan=specialist_pb2.ExecutionPlan(
                    plan_id="test-plan-123", description="Test plan"
                ),
            )

            # Deve lançar exceção UNAUTHENTICATED
            with pytest.raises(grpc.RpcError) as exc_info:
                stub.EvaluatePlan(request, metadata=metadata, timeout=2)

            assert exc_info.value.code() == grpc.StatusCode.UNAUTHENTICATED
            assert "invalid" in exc_info.value.details().lower()

        finally:
            channel.close()

    def test_get_capabilities_with_valid_token(
        self, server, config, valid_token, mock_specialist
    ):
        """Testa GetCapabilities com token válido."""
        channel = grpc.insecure_channel(f"localhost:{TEST_PORT}")
        stub = specialist_pb2_grpc.SpecialistServiceStub(channel)

        try:
            metadata = [("authorization", f"Bearer {valid_token}")]

            request = specialist_pb2.GetCapabilitiesRequest()
            response = stub.GetCapabilities(request, metadata=metadata, timeout=2)

            # Deve retornar resposta bem-sucedida
            assert response.specialist_type == "test-specialist"
            assert response.version == "1.0.0"

            # Verificar que método do mock foi chamado
            mock_specialist.get_capabilities.assert_called()

        finally:
            channel.close()


class TestMetricsIntegration:
    """Testes de integração de métricas de autenticação."""

    def test_metrics_recorded_for_bypassed_requests(
        self, server, config, mock_specialist
    ):
        """Testa que métricas são registradas para requisições bypassed."""
        metrics = mock_specialist.metrics

        # Obter estado inicial da métrica
        initial_bypassed = metrics.auth_requests_total.labels(
            "test-specialist", "/grpc.health.v1.Health/Check", "bypassed"
        )._value.get()

        # Fazer chamada a Health/Check (bypass)
        channel = grpc.insecure_channel(f"localhost:{TEST_PORT}")
        stub = health_pb2_grpc.HealthStub(channel)

        try:
            request = health_pb2.HealthCheckRequest(service="")
            stub.Check(request, timeout=2)
        finally:
            channel.close()

        # Verificar que métrica foi incrementada
        final_bypassed = metrics.auth_requests_total.labels(
            "test-specialist", "/grpc.health.v1.Health/Check", "bypassed"
        )._value.get()

        assert final_bypassed > initial_bypassed

    def test_metrics_recorded_for_successful_auth(
        self, server, config, valid_token, mock_specialist
    ):
        """Testa que métricas são registradas para autenticação bem-sucedida."""
        metrics = mock_specialist.metrics

        # Obter estado inicial
        initial_success = metrics.auth_requests_total.labels(
            "test-specialist",
            "/neural_hive.specialist.SpecialistService/GetCapabilities",
            "success",
        )._value.get()

        # Fazer chamada autenticada
        channel = grpc.insecure_channel(f"localhost:{TEST_PORT}")
        stub = specialist_pb2_grpc.SpecialistServiceStub(channel)

        try:
            metadata = [("authorization", f"Bearer {valid_token}")]
            request = specialist_pb2.GetCapabilitiesRequest()
            stub.GetCapabilities(request, metadata=metadata, timeout=2)
        finally:
            channel.close()

        # Verificar que métrica foi incrementada
        final_success = metrics.auth_requests_total.labels(
            "test-specialist",
            "/neural_hive.specialist.SpecialistService/GetCapabilities",
            "success",
        )._value.get()

        assert final_success > initial_success

    def test_metrics_recorded_for_failed_auth(self, server, config, mock_specialist):
        """Testa que métricas são registradas para falha de autenticação."""
        metrics = mock_specialist.metrics

        # Obter estado inicial
        initial_failed = metrics.auth_requests_total.labels(
            "test-specialist",
            "/neural_hive.specialist.SpecialistService/EvaluatePlan",
            "failed",
        )._value.get()

        # Fazer chamada sem token (deve falhar)
        channel = grpc.insecure_channel(f"localhost:{TEST_PORT}")
        stub = specialist_pb2_grpc.SpecialistServiceStub(channel)

        try:
            request = specialist_pb2.EvaluatePlanRequest(
                plan_id="test",
                intent_id="test",
                trace_id="test",
                plan=specialist_pb2.ExecutionPlan(plan_id="test", description="test"),
            )

            with pytest.raises(grpc.RpcError):
                stub.EvaluatePlan(request, timeout=2)
        finally:
            channel.close()

        # Verificar que métrica foi incrementada
        final_failed = metrics.auth_requests_total.labels(
            "test-specialist",
            "/neural_hive.specialist.SpecialistService/EvaluatePlan",
            "failed",
        )._value.get()

        assert final_failed > initial_failed
