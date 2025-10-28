"""
Testes para AuthInterceptor.
"""
import pytest
import jwt
import grpc
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, MagicMock, patch
from prometheus_client import REGISTRY

from neural_hive_specialists.auth_interceptor import AuthInterceptor
from neural_hive_specialists.config import SpecialistConfig
from neural_hive_specialists.metrics import SpecialistMetrics


@pytest.fixture
def config():
    """Fixture de configuração para testes."""
    return SpecialistConfig(
        specialist_type='test-specialist',
        service_name='test-service',
        mlflow_tracking_uri='http://mlflow:5000',
        mlflow_experiment_name='test',
        mlflow_model_name='test-model',
        mongodb_uri='mongodb://localhost:27017',
        redis_cluster_nodes='localhost:6379',
        neo4j_uri='bolt://localhost:7687',
        neo4j_password='test',
        jwt_secret_key='test-secret-key-with-minimum-32-chars-required',
        jwt_algorithm='HS256',
        jwt_issuer='neural-hive',
        jwt_audience='specialists',
        enable_jwt_auth=True,
        jwt_public_endpoints=['HealthCheck', '/grpc.health.v1.Health/Check', '/grpc.health.v1.Health/Watch']
    )


@pytest.fixture
def metrics(config):
    """Fixture de métricas para testes."""
    # Limpar métricas anteriores do registry
    collectors_to_remove = []
    for collector in list(REGISTRY._collector_to_names.keys()):
        if hasattr(collector, '_name') and 'neural_hive' in str(collector._name):
            collectors_to_remove.append(collector)

    for collector in collectors_to_remove:
        try:
            REGISTRY.unregister(collector)
        except Exception:
            pass

    return SpecialistMetrics(config, 'test-specialist')


@pytest.fixture
def auth_interceptor(config, metrics):
    """Fixture de AuthInterceptor."""
    return AuthInterceptor(config, metrics)


@pytest.fixture
def valid_token(config):
    """Fixture de token JWT válido."""
    payload = {
        'sub': 'consensus-engine',
        'service_type': 'consensus-engine',
        'iat': datetime.now(timezone.utc),
        'exp': datetime.now(timezone.utc) + timedelta(hours=1),
        'iss': config.jwt_issuer,
        'aud': config.jwt_audience
    }
    return jwt.encode(
        payload,
        config.jwt_secret_key,
        algorithm=config.jwt_algorithm
    )


class TestAuthInterceptor:
    """Testes para AuthInterceptor."""

    def test_initialization(self, auth_interceptor, config):
        """Testa inicialização do interceptor."""
        assert auth_interceptor.jwt_secret == config.jwt_secret_key
        assert auth_interceptor.jwt_algorithm == config.jwt_algorithm
        assert 'HealthCheck' in auth_interceptor.public_endpoints

    def test_extract_token_valid(self, auth_interceptor):
        """Testa extração de token válido."""
        auth_header = 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...'
        token = auth_interceptor._extract_token(auth_header)
        assert token == 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...'

    def test_extract_token_invalid_format(self, auth_interceptor):
        """Testa extração de token com formato inválido."""
        assert auth_interceptor._extract_token('InvalidFormat') is None
        assert auth_interceptor._extract_token('Bearer') is None
        assert auth_interceptor._extract_token('') is None

    def test_validate_token_valid(self, auth_interceptor, config):
        """Testa validação de token válido."""
        payload = {
            'sub': 'consensus-engine',
            'service_type': 'consensus-engine',
            'iat': datetime.now(timezone.utc),
            'exp': datetime.now(timezone.utc) + timedelta(hours=1),
            'iss': config.jwt_issuer,
            'aud': config.jwt_audience
        }
        token = jwt.encode(
            payload,
            config.jwt_secret_key,
            algorithm=config.jwt_algorithm
        )

        decoded = auth_interceptor._validate_token(token)
        assert decoded['sub'] == 'consensus-engine'
        assert decoded['service_type'] == 'consensus-engine'

    def test_validate_token_expired(self, auth_interceptor, config):
        """Testa validação de token expirado."""
        payload = {
            'sub': 'consensus-engine',
            'service_type': 'consensus-engine',
            'iat': datetime.now(timezone.utc) - timedelta(hours=2),
            'exp': datetime.now(timezone.utc) - timedelta(hours=1),
            'iss': config.jwt_issuer,
            'aud': config.jwt_audience
        }
        token = jwt.encode(
            payload,
            config.jwt_secret_key,
            algorithm=config.jwt_algorithm
        )

        with pytest.raises(jwt.ExpiredSignatureError):
            auth_interceptor._validate_token(token)

    def test_validate_token_invalid_signature(self, auth_interceptor, config):
        """Testa validação de token com assinatura inválida."""
        payload = {
            'sub': 'consensus-engine',
            'service_type': 'consensus-engine',
            'iat': datetime.now(timezone.utc),
            'exp': datetime.now(timezone.utc) + timedelta(hours=1),
            'iss': config.jwt_issuer,
            'aud': config.jwt_audience
        }
        token = jwt.encode(
            payload,
            'wrong-secret-key-with-minimum-32-chars',
            algorithm=config.jwt_algorithm
        )

        with pytest.raises(jwt.InvalidTokenError):
            auth_interceptor._validate_token(token)

    def test_validate_token_missing_required_claims(self, auth_interceptor, config):
        """Testa validação de token sem claims obrigatórios."""
        payload = {
            'sub': 'consensus-engine',
            # Faltando 'exp' e 'iat'
            'iss': config.jwt_issuer,
            'aud': config.jwt_audience
        }
        token = jwt.encode(
            payload,
            config.jwt_secret_key,
            algorithm=config.jwt_algorithm
        )

        with pytest.raises(jwt.InvalidTokenError):
            auth_interceptor._validate_token(token)

    def test_check_permissions_valid(self, auth_interceptor):
        """Testa verificação de permissões válidas."""
        payload = {
            'sub': 'consensus-engine',
            'service_type': 'consensus-engine'
        }

        # Testar com nome de método
        assert auth_interceptor._check_permissions(payload, 'EvaluatePlan') is True
        assert auth_interceptor._check_permissions(payload, 'GetCapabilities') is True

        # Testar com path completo
        assert auth_interceptor._check_permissions(payload, '/neural_hive.specialist.SpecialistService/EvaluatePlan') is True
        assert auth_interceptor._check_permissions(payload, '/neural_hive.specialist.SpecialistService/GetCapabilities') is True

    def test_check_permissions_invalid_service_type(self, auth_interceptor):
        """Testa verificação de permissões com service_type inválido."""
        payload = {
            'sub': 'unknown-service',
            'service_type': 'unknown'
        }

        assert auth_interceptor._check_permissions(payload, 'EvaluatePlan') is False

    def test_check_permissions_missing_service_type(self, auth_interceptor):
        """Testa verificação de permissões sem service_type."""
        payload = {
            'sub': 'consensus-engine'
            # Faltando 'service_type'
        }

        assert auth_interceptor._check_permissions(payload, 'EvaluatePlan') is False

    def test_intercept_public_endpoint(self, auth_interceptor):
        """Testa interceptação de endpoint público (sem autenticação)."""
        # Mock continuation
        continuation = Mock(return_value='success')

        # Mock handler_call_details
        handler_call_details = Mock()
        handler_call_details.method = '/neural_hive.specialist.SpecialistService/HealthCheck'
        handler_call_details.invocation_metadata = []

        result = auth_interceptor.intercept_service(continuation, handler_call_details)

        assert result == 'success'
        continuation.assert_called_once()

    def test_intercept_grpc_health_check_bypass(self, auth_interceptor):
        """Testa bypass de /grpc.health.v1.Health/Check sem autenticação."""
        continuation = Mock(return_value='success')

        handler_call_details = Mock()
        handler_call_details.method = '/grpc.health.v1.Health/Check'
        handler_call_details.invocation_metadata = []

        result = auth_interceptor.intercept_service(continuation, handler_call_details)

        assert result == 'success'
        continuation.assert_called_once()

    def test_intercept_grpc_health_watch_bypass(self, auth_interceptor):
        """Testa bypass de /grpc.health.v1.Health/Watch (streaming) sem autenticação."""
        continuation = Mock(return_value='success')

        handler_call_details = Mock()
        handler_call_details.method = '/grpc.health.v1.Health/Watch'
        handler_call_details.invocation_metadata = []

        result = auth_interceptor.intercept_service(continuation, handler_call_details)

        assert result == 'success'
        continuation.assert_called_once()

    def test_intercept_missing_token(self, auth_interceptor, metrics):
        """Testa interceptação sem token."""
        # Mock do handler com tipo unary_unary
        mock_handler = Mock()
        mock_handler.unary_unary = True
        continuation = Mock(return_value=mock_handler)

        handler_call_details = Mock()
        handler_call_details.method = '/neural_hive.specialist.SpecialistService/EvaluatePlan'
        handler_call_details.invocation_metadata = []  # Sem authorization header

        result = auth_interceptor.intercept_service(continuation, handler_call_details)

        # Deve retornar um handler que aborta com UNAUTHENTICATED
        assert result is not None
        # Continuation é chamado para obter o handler original
        continuation.assert_called_once()

    def test_intercept_invalid_token_format(self, auth_interceptor):
        """Testa interceptação com formato de token inválido."""
        # Mock do handler com tipo unary_unary
        mock_handler = Mock()
        mock_handler.unary_unary = True
        continuation = Mock(return_value=mock_handler)

        handler_call_details = Mock()
        handler_call_details.method = '/neural_hive.specialist.SpecialistService/EvaluatePlan'
        handler_call_details.invocation_metadata = [
            ('authorization', 'InvalidFormat')
        ]

        result = auth_interceptor.intercept_service(continuation, handler_call_details)

        # Deve retornar um handler que aborta
        assert result is not None
        # Continuation é chamado para obter o handler original
        continuation.assert_called_once()

    def test_intercept_valid_token(self, auth_interceptor, config):
        """Testa interceptação com token válido."""
        # Criar token válido
        payload = {
            'sub': 'consensus-engine',
            'service_type': 'consensus-engine',
            'iat': datetime.now(timezone.utc),
            'exp': datetime.now(timezone.utc) + timedelta(hours=1),
            'iss': config.jwt_issuer,
            'aud': config.jwt_audience
        }
        token = jwt.encode(
            payload,
            config.jwt_secret_key,
            algorithm=config.jwt_algorithm
        )

        continuation = Mock(return_value='success')

        handler_call_details = Mock()
        handler_call_details.method = '/neural_hive.specialist.SpecialistService/EvaluatePlan'
        handler_call_details.invocation_metadata = [
            ('authorization', f'Bearer {token}')
        ]

        result = auth_interceptor.intercept_service(continuation, handler_call_details)

        assert result == 'success'
        continuation.assert_called_once()

    def test_intercept_expired_token(self, auth_interceptor, config):
        """Testa interceptação com token expirado."""
        # Criar token expirado
        payload = {
            'sub': 'consensus-engine',
            'service_type': 'consensus-engine',
            'iat': datetime.now(timezone.utc) - timedelta(hours=2),
            'exp': datetime.now(timezone.utc) - timedelta(hours=1),
            'iss': config.jwt_issuer,
            'aud': config.jwt_audience
        }
        token = jwt.encode(
            payload,
            config.jwt_secret_key,
            algorithm=config.jwt_algorithm
        )

        # Mock do handler com tipo unary_unary
        mock_handler = Mock()
        mock_handler.unary_unary = True
        continuation = Mock(return_value=mock_handler)

        handler_call_details = Mock()
        handler_call_details.method = '/neural_hive.specialist.SpecialistService/EvaluatePlan'
        handler_call_details.invocation_metadata = [
            ('authorization', f'Bearer {token}')
        ]

        result = auth_interceptor.intercept_service(continuation, handler_call_details)

        # Deve retornar um handler que aborta
        assert result is not None
        # Continuation é chamado para obter o handler original
        continuation.assert_called_once()

    def test_intercept_insufficient_permissions(self, auth_interceptor, config):
        """Testa interceptação com permissões insuficientes."""
        # Criar token com service_type não autorizado
        payload = {
            'sub': 'unknown-service',
            'service_type': 'unknown',
            'iat': datetime.now(timezone.utc),
            'exp': datetime.now(timezone.utc) + timedelta(hours=1),
            'iss': config.jwt_issuer,
            'aud': config.jwt_audience
        }
        token = jwt.encode(
            payload,
            config.jwt_secret_key,
            algorithm=config.jwt_algorithm
        )

        # Mock do handler com tipo unary_unary
        mock_handler = Mock()
        mock_handler.unary_unary = True
        continuation = Mock(return_value=mock_handler)

        handler_call_details = Mock()
        handler_call_details.method = '/neural_hive.specialist.SpecialistService/EvaluatePlan'
        handler_call_details.invocation_metadata = [
            ('authorization', f'Bearer {token}')
        ]

        result = auth_interceptor.intercept_service(continuation, handler_call_details)

        # Deve retornar um handler que aborta
        assert result is not None
        # Continuation é chamado para obter o handler original
        continuation.assert_called_once()

    def test_intercept_auth_disabled(self, config, metrics):
        """Testa interceptação com autenticação desabilitada."""
        config.enable_jwt_auth = False
        interceptor = AuthInterceptor(config, metrics)

        continuation = Mock(return_value='success')

        handler_call_details = Mock()
        handler_call_details.method = '/neural_hive.specialist.SpecialistService/EvaluatePlan'
        handler_call_details.invocation_metadata = []  # Sem token

        result = interceptor.intercept_service(continuation, handler_call_details)

        assert result == 'success'
        continuation.assert_called_once()


class TestAuthInterceptorMetrics:
    """Testes para métricas de autenticação."""

    def test_metrics_auth_success(self, auth_interceptor, config, metrics):
        """Testa incremento de métrica de sucesso."""
        payload = {
            'sub': 'consensus-engine',
            'service_type': 'consensus-engine',
            'iat': datetime.now(timezone.utc),
            'exp': datetime.now(timezone.utc) + timedelta(hours=1),
            'iss': config.jwt_issuer,
            'aud': config.jwt_audience
        }
        token = jwt.encode(
            payload,
            config.jwt_secret_key,
            algorithm=config.jwt_algorithm
        )

        continuation = Mock(return_value='success')
        handler_call_details = Mock()
        handler_call_details.method = '/neural_hive.specialist.SpecialistService/EvaluatePlan'
        handler_call_details.invocation_metadata = [
            ('authorization', f'Bearer {token}')
        ]

        # Verificar estado inicial
        initial_success = metrics.auth_attempts_total.labels('test-specialist', 'success')._value.get()

        # Executar interceptor
        auth_interceptor.intercept_service(continuation, handler_call_details)

        # Verificar que métrica foi incrementada
        final_success = metrics.auth_attempts_total.labels('test-specialist', 'success')._value.get()
        assert final_success > initial_success

    def test_metrics_auth_failure(self, auth_interceptor, metrics):
        """Testa incremento de métrica de falha."""
        continuation = Mock()
        handler_call_details = Mock()
        handler_call_details.method = '/neural_hive.specialist.SpecialistService/EvaluatePlan'
        handler_call_details.invocation_metadata = []  # Sem token

        # Verificar estado inicial
        initial_failure = metrics.auth_attempts_total.labels('test-specialist', 'failure')._value.get()

        # Executar interceptor
        auth_interceptor.intercept_service(continuation, handler_call_details)

        # Verificar que métrica foi incrementada
        final_failure = metrics.auth_attempts_total.labels('test-specialist', 'failure')._value.get()
        assert final_failure > initial_failure

    def test_metrics_auth_request_bypassed(self, auth_interceptor, metrics):
        """Testa métrica unificada para requisições bypassed."""
        continuation = Mock(return_value='success')
        handler_call_details = Mock()
        handler_call_details.method = '/grpc.health.v1.Health/Check'
        handler_call_details.invocation_metadata = []

        # Verificar estado inicial
        initial_bypassed = metrics.auth_requests_total.labels(
            'test-specialist',
            '/grpc.health.v1.Health/Check',
            'bypassed'
        )._value.get()

        # Executar interceptor
        auth_interceptor.intercept_service(continuation, handler_call_details)

        # Verificar que métrica foi incrementada
        final_bypassed = metrics.auth_requests_total.labels(
            'test-specialist',
            '/grpc.health.v1.Health/Check',
            'bypassed'
        )._value.get()
        assert final_bypassed > initial_bypassed

    def test_metrics_auth_request_failed(self, auth_interceptor, metrics):
        """Testa métrica unificada para requisições com falha."""
        continuation = Mock()
        handler_call_details = Mock()
        handler_call_details.method = '/neural_hive.specialist.SpecialistService/EvaluatePlan'
        handler_call_details.invocation_metadata = []

        # Verificar estado inicial
        initial_failed = metrics.auth_requests_total.labels(
            'test-specialist',
            '/neural_hive.specialist.SpecialistService/EvaluatePlan',
            'failed'
        )._value.get()

        # Executar interceptor
        auth_interceptor.intercept_service(continuation, handler_call_details)

        # Verificar que métrica foi incrementada
        final_failed = metrics.auth_requests_total.labels(
            'test-specialist',
            '/neural_hive.specialist.SpecialistService/EvaluatePlan',
            'failed'
        )._value.get()
        assert final_failed > initial_failed

    def test_metrics_validation_duration(self, auth_interceptor, config, metrics):
        """Testa observação de duração de validação de token."""
        payload = {
            'sub': 'consensus-engine',
            'service_type': 'consensus-engine',
            'iat': datetime.now(timezone.utc),
            'exp': datetime.now(timezone.utc) + timedelta(hours=1),
            'iss': config.jwt_issuer,
            'aud': config.jwt_audience
        }
        token = jwt.encode(
            payload,
            config.jwt_secret_key,
            algorithm=config.jwt_algorithm
        )

        continuation = Mock(return_value='success')
        handler_call_details = Mock()
        handler_call_details.method = '/neural_hive.specialist.SpecialistService/EvaluatePlan'
        handler_call_details.invocation_metadata = [
            ('authorization', f'Bearer {token}')
        ]

        # Obter contagem inicial de observações via collect()
        initial_samples = list(metrics.auth_token_validation_duration_seconds.collect())
        initial_count = 0
        if initial_samples:
            for sample in initial_samples[0].samples:
                if sample.name.endswith('_count') and sample.labels.get('specialist_type') == 'test-specialist':
                    initial_count = sample.value
                    break

        # Executar interceptor
        auth_interceptor.intercept_service(continuation, handler_call_details)

        # Obter contagem final
        final_samples = list(metrics.auth_token_validation_duration_seconds.collect())
        final_count = 0
        if final_samples:
            for sample in final_samples[0].samples:
                if sample.name.endswith('_count') and sample.labels.get('specialist_type') == 'test-specialist':
                    final_count = sample.value
                    break

        # Verificar que houve observação
        assert final_count > initial_count
