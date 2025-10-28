"""
Testes de integração para FeedbackAPI.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, MagicMock, patch
from neural_hive_specialists.feedback import create_feedback_router
from neural_hive_specialists.config import SpecialistConfig
from neural_hive_specialists.compliance import AuditLogger
from fastapi import FastAPI


@pytest.fixture
def mock_config():
    """Configuração mock."""
    return SpecialistConfig(
        specialist_type='technical',
        service_name='test-specialist',
        mongodb_uri='mongodb://localhost:27017',
        mlflow_tracking_uri='http://localhost:5000',
        mlflow_experiment_name='test-experiment',
        mlflow_model_name='test-model',
        redis_cluster_nodes='localhost:6379',
        neo4j_uri='bolt://localhost:7687',
        neo4j_password='test-password',
        jwt_secret_key='test-secret-key-minimum-32-chars-long',
        feedback_require_authentication=False,  # Desabilitar auth para testes
        feedback_rating_min=0.0,
        feedback_rating_max=1.0
    )


@pytest.fixture
def mock_feedback_collector():
    """FeedbackCollector mock."""
    collector = Mock()
    collector.validate_opinion_exists = Mock(return_value=True)
    collector.submit_feedback = Mock(return_value='feedback-test123')
    collector.get_feedback_by_opinion = Mock(return_value=[])
    collector.get_feedback_statistics = Mock(return_value={
        'count': 10,
        'avg_rating': 0.85,
        'distribution': {'approve': 7, 'reject': 3}
    })
    # Usar método público get_opinion_metadata ao invés de acesso direto
    collector.get_opinion_metadata = Mock(return_value={
        'plan_id': 'plan-test',
        'specialist_type': 'technical'
    })
    return collector


@pytest.fixture
def test_app(mock_config, mock_feedback_collector):
    """Aplicação FastAPI de teste."""
    app = FastAPI()
    router = create_feedback_router(mock_feedback_collector, mock_config)
    app.include_router(router, prefix="/api/v1")
    return app


@pytest.fixture
def test_client(test_app):
    """Cliente de teste."""
    return TestClient(test_app)


@pytest.fixture
def valid_feedback_request():
    """Request válido de feedback."""
    return {
        'opinion_id': 'opinion-test',
        'human_rating': 0.9,
        'human_recommendation': 'approve',
        'feedback_notes': 'Análise correta'
    }


class TestFeedbackAPI:
    """Testes da API de feedback."""

    def test_submit_feedback_success(self, test_client, valid_feedback_request):
        """Teste de submissão bem-sucedida."""
        response = test_client.post('/api/v1/feedback', json=valid_feedback_request)

        assert response.status_code == 201
        data = response.json()
        assert data['feedback_id'] == 'feedback-test123'
        assert data['opinion_id'] == 'opinion-test'
        assert data['status'] == 'success'

    def test_submit_feedback_invalid_rating(self, test_client, valid_feedback_request):
        """Teste com rating inválido."""
        valid_feedback_request['human_rating'] = 1.5

        response = test_client.post('/api/v1/feedback', json=valid_feedback_request)

        assert response.status_code == 422  # Validation error

    def test_submit_feedback_invalid_recommendation(self, test_client, valid_feedback_request):
        """Teste com recomendação inválida."""
        valid_feedback_request['human_recommendation'] = 'invalid'

        response = test_client.post('/api/v1/feedback', json=valid_feedback_request)

        assert response.status_code == 422  # Validation error

    def test_submit_feedback_opinion_not_found(self, test_client, valid_feedback_request, mock_feedback_collector):
        """Teste quando opinião não existe."""
        mock_feedback_collector.get_opinion_metadata.side_effect = ValueError("Opinião opinion-test não encontrada no ledger")

        response = test_client.post('/api/v1/feedback', json=valid_feedback_request)

        assert response.status_code == 404

    def test_submit_feedback_missing_required_field(self, test_client):
        """Teste com campo obrigatório faltando."""
        incomplete_request = {
            'opinion_id': 'test'
            # Falta human_rating e human_recommendation
        }

        response = test_client.post('/api/v1/feedback', json=incomplete_request)

        assert response.status_code == 422  # Validation error

    def test_get_feedback_by_opinion_success(self, test_client, mock_feedback_collector):
        """Teste de busca de feedbacks por opinião."""
        from neural_hive_specialists.feedback import FeedbackDocument
        from datetime import datetime

        mock_feedbacks = [
            FeedbackDocument(
                opinion_id='opinion-test',
                plan_id='plan-test',
                specialist_type='technical',
                human_rating=0.9,
                human_recommendation='approve',
                submitted_by='test'
            )
        ]
        mock_feedback_collector.get_feedback_by_opinion.return_value = mock_feedbacks

        response = test_client.get('/api/v1/feedback/opinion/opinion-test')

        assert response.status_code == 200
        data = response.json()
        assert data['count'] == 1
        assert len(data['feedbacks']) == 1

    def test_get_feedback_stats_success(self, test_client, mock_feedback_collector):
        """Teste de estatísticas de feedback."""
        response = test_client.get('/api/v1/feedback/stats?specialist_type=technical&window_days=30')

        assert response.status_code == 200
        data = response.json()
        assert data['count'] == 10
        assert data['avg_rating'] == 0.85
        assert 'distribution' in data


class TestFeedbackAPIAuthentication:
    """Testes de autenticação da API."""

    @pytest.fixture
    def auth_config(self):
        """Configuração com autenticação habilitada."""
        return SpecialistConfig(
            specialist_type='technical',
            service_name='test-specialist',
            mongodb_uri='mongodb://localhost:27017',
            mlflow_tracking_uri='http://localhost:5000',
            mlflow_experiment_name='test-experiment',
            mlflow_model_name='test-model',
            redis_cluster_nodes='localhost:6379',
            neo4j_uri='bolt://localhost:7687',
            neo4j_password='test-password',
            feedback_require_authentication=True,
            feedback_allowed_roles=['human_expert'],
            jwt_secret_key='test-secret-key-minimum-32-chars-long'
        )

    @pytest.fixture
    def mock_audit_logger(self):
        """Mock do AuditLogger."""
        audit_logger = Mock(spec=AuditLogger)
        audit_logger.log_data_access = Mock()
        return audit_logger

    @pytest.fixture
    def auth_app(self, auth_config, mock_feedback_collector, mock_audit_logger):
        """App com autenticação e audit logger."""
        app = FastAPI()
        router = create_feedback_router(
            mock_feedback_collector,
            auth_config,
            audit_logger=mock_audit_logger
        )
        app.include_router(router, prefix="/api/v1")
        # Armazenar audit_logger no app para acesso nos testes
        app.state.audit_logger = mock_audit_logger
        return app

    @pytest.fixture
    def auth_client(self, auth_app):
        """Cliente com autenticação."""
        return TestClient(auth_app)

    def test_submit_feedback_requires_authentication(self, auth_client, valid_feedback_request):
        """Teste que autenticação é requerida."""
        response = auth_client.post('/api/v1/feedback', json=valid_feedback_request)

        assert response.status_code == 401

    def test_submit_feedback_with_valid_token(self, auth_client, valid_feedback_request):
        """Teste com token JWT válido."""
        import jwt
        from datetime import datetime, timedelta

        # Gerar token válido
        payload = {
            'sub': 'test@example.com',
            'role': 'human_expert',
            'exp': datetime.utcnow() + timedelta(hours=1)
        }
        token = jwt.encode(payload, 'test-secret-key-minimum-32-chars-long', algorithm='HS256')

        headers = {'Authorization': f'Bearer {token}'}
        response = auth_client.post(
            '/api/v1/feedback',
            json=valid_feedback_request,
            headers=headers
        )

        # Note: Pode falhar por outros motivos (opinion not found, etc)
        # mas não deve ser 401
        assert response.status_code != 401

    def test_audit_log_missing_token(self, auth_client, auth_app, valid_feedback_request):
        """Teste que falta de token é auditada."""
        audit_logger = auth_app.state.audit_logger

        response = auth_client.post('/api/v1/feedback', json=valid_feedback_request)

        assert response.status_code == 401
        # Verificar que log_data_access foi chamado
        audit_logger.log_data_access.assert_called_once()
        call_args = audit_logger.log_data_access.call_args
        assert call_args[1]['operation'] == 'feedback_auth_denied'
        assert call_args[1]['resource_id'] == 'feedback_api'
        assert call_args[1]['details']['reason'] == 'missing_token'
        assert call_args[1]['details']['status_code'] == 401

    def test_audit_log_invalid_token(self, auth_client, auth_app, valid_feedback_request):
        """Teste que token inválido é auditado."""
        audit_logger = auth_app.state.audit_logger

        headers = {'Authorization': 'Bearer invalid-token-xyz'}
        response = auth_client.post(
            '/api/v1/feedback',
            json=valid_feedback_request,
            headers=headers
        )

        assert response.status_code == 401
        # Verificar que log_data_access foi chamado
        audit_logger.log_data_access.assert_called_once()
        call_args = audit_logger.log_data_access.call_args
        assert call_args[1]['operation'] == 'feedback_auth_denied'
        assert call_args[1]['resource_id'] == 'feedback_api'
        assert call_args[1]['details']['reason'] == 'invalid_token'
        assert call_args[1]['details']['status_code'] == 401

    def test_audit_log_unauthorized_role(self, auth_client, auth_app, valid_feedback_request):
        """Teste que role não autorizado é auditado."""
        import jwt
        from datetime import datetime, timedelta

        audit_logger = auth_app.state.audit_logger

        # Gerar token com role não autorizado
        payload = {
            'sub': 'unauthorized@example.com',
            'role': 'unauthorized_role',
            'exp': datetime.utcnow() + timedelta(hours=1)
        }
        token = jwt.encode(payload, 'test-secret-key-minimum-32-chars-long', algorithm='HS256')

        headers = {'Authorization': f'Bearer {token}'}
        response = auth_client.post(
            '/api/v1/feedback',
            json=valid_feedback_request,
            headers=headers
        )

        assert response.status_code == 403
        # Verificar que log_data_access foi chamado
        audit_logger.log_data_access.assert_called_once()
        call_args = audit_logger.log_data_access.call_args
        assert call_args[1]['operation'] == 'feedback_auth_denied'
        assert call_args[1]['resource_id'] == 'feedback_api'
        assert call_args[1]['details']['reason'] == 'insufficient_permissions'
        assert call_args[1]['details']['sub'] == 'unauthorized@example.com'
        assert call_args[1]['details']['role'] == 'unauthorized_role'
        assert call_args[1]['details']['status_code'] == 403

    def test_audit_log_expired_token(self, auth_client, auth_app, valid_feedback_request):
        """Teste que token expirado é auditado."""
        import jwt
        from datetime import datetime, timedelta

        audit_logger = auth_app.state.audit_logger

        # Gerar token expirado
        payload = {
            'sub': 'test@example.com',
            'role': 'human_expert',
            'exp': datetime.utcnow() - timedelta(hours=1)  # Expirado há 1 hora
        }
        token = jwt.encode(payload, 'test-secret-key-minimum-32-chars-long', algorithm='HS256')

        headers = {'Authorization': f'Bearer {token}'}
        response = auth_client.post(
            '/api/v1/feedback',
            json=valid_feedback_request,
            headers=headers
        )

        assert response.status_code == 401
        # Verificar que log_data_access foi chamado
        audit_logger.log_data_access.assert_called_once()
        call_args = audit_logger.log_data_access.call_args
        assert call_args[1]['operation'] == 'feedback_auth_denied'
        assert call_args[1]['resource_id'] == 'feedback_api'
        assert call_args[1]['details']['reason'] == 'expired_token'
        assert call_args[1]['details']['status_code'] == 401
