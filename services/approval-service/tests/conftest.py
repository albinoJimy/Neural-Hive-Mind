"""
Configuracao e fixtures compartilhadas para testes do Approval Service
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock

from src.config.settings import Settings
from src.models.approval import (
    ApprovalRequest,
    ApprovalDecision,
    ApprovalResponse,
    ApprovalStats,
    RiskBand,
    ApprovalStatus
)


@pytest.fixture
def mock_settings():
    """Mock Settings object"""
    settings = MagicMock(spec=Settings)
    settings.environment = 'test'
    settings.debug = True
    settings.log_level = 'DEBUG'
    settings.service_name = 'approval-service'
    settings.service_version = '1.0.0'

    # Kafka settings
    settings.kafka_bootstrap_servers = 'localhost:9092'
    settings.kafka_consumer_group_id = 'approval-service-test'
    settings.kafka_approval_requests_topic = 'cognitive-plans-approval-requests'
    settings.kafka_approval_responses_topic = 'cognitive-plans-approval-responses'
    settings.kafka_auto_offset_reset = 'earliest'
    settings.kafka_enable_auto_commit = False
    settings.kafka_session_timeout_ms = 30000
    settings.kafka_max_poll_interval_ms = 300000
    settings.kafka_enable_idempotence = True
    settings.kafka_transactional_id = None
    settings.kafka_security_protocol = 'PLAINTEXT'
    settings.kafka_sasl_mechanism = None
    settings.kafka_sasl_username = None
    settings.kafka_sasl_password = None
    settings.schema_registry_url = None

    # MongoDB settings
    settings.mongodb_uri = 'mongodb://localhost:27017'
    settings.mongodb_database = 'neural_hive_test'
    settings.mongodb_collection = 'plan_approvals_test'
    settings.mongodb_max_pool_size = 10
    settings.mongodb_timeout_ms = 5000

    # Keycloak settings
    settings.keycloak_url = 'http://localhost:8080'
    settings.keycloak_realm = 'neural-hive'
    settings.keycloak_client_id = 'approval-service'
    settings.admin_role_name = 'neural-hive-admin'

    # Observability settings
    settings.otel_endpoint = 'http://localhost:4317'
    settings.otel_tls_verify = False
    settings.prometheus_port = 8000
    settings.jaeger_sampling_rate = 1.0

    # Rate limiting
    settings.rate_limit_requests_per_minute = 100

    return settings


@pytest.fixture
def sample_cognitive_plan():
    """Plano cognitivo de exemplo para testes"""
    return {
        'plan_id': 'plan-001',
        'intent_id': 'intent-001',
        'risk_score': 0.85,
        'risk_band': 'high',
        'is_destructive': True,
        'destructive_tasks': ['task-2', 'task-3'],
        'risk_matrix': {
            'business': 0.7,
            'security': 0.9,
            'operational': 0.6
        },
        'requires_approval': True,
        'approval_status': 'pending',
        'tasks': [
            {'task_id': 'task-1', 'type': 'query', 'description': 'Buscar dados'},
            {'task_id': 'task-2', 'type': 'delete', 'description': 'Remover registros antigos'},
            {'task_id': 'task-3', 'type': 'truncate', 'description': 'Limpar tabela temporaria'}
        ],
        'created_at': datetime.utcnow().isoformat()
    }


@pytest.fixture
def sample_approval_request(sample_cognitive_plan):
    """ApprovalRequest de exemplo para testes"""
    return ApprovalRequest(
        approval_id='approval-001',
        plan_id=sample_cognitive_plan['plan_id'],
        intent_id=sample_cognitive_plan['intent_id'],
        risk_score=sample_cognitive_plan['risk_score'],
        risk_band=RiskBand.HIGH,
        is_destructive=sample_cognitive_plan['is_destructive'],
        destructive_tasks=sample_cognitive_plan['destructive_tasks'],
        risk_matrix=sample_cognitive_plan['risk_matrix'],
        status=ApprovalStatus.PENDING,
        requested_at=datetime.utcnow(),
        cognitive_plan=sample_cognitive_plan
    )


@pytest.fixture
def sample_approval_decision():
    """ApprovalDecision de exemplo para testes"""
    return ApprovalDecision(
        plan_id='plan-001',
        decision='approved',
        approved_by='admin@example.com',
        approved_at=datetime.utcnow(),
        comments='Aprovado apos revisao manual'
    )


@pytest.fixture
def sample_approval_response():
    """ApprovalResponse de exemplo para testes"""
    return ApprovalResponse(
        plan_id='plan-001',
        intent_id='intent-001',
        decision='approved',
        approved_by='admin@example.com',
        approved_at=datetime.utcnow(),
        cognitive_plan={'plan_id': 'plan-001'}
    )


@pytest.fixture
def mock_mongodb_client():
    """Mock MongoDBClient"""
    client = MagicMock()
    client.initialize = AsyncMock()
    client.close = AsyncMock()
    client.save_approval_request = AsyncMock(return_value='approval-001')
    client.get_approval_by_plan_id = AsyncMock()
    client.get_pending_approvals = AsyncMock(return_value=[])
    client.update_approval_decision = AsyncMock(return_value=True)
    client.get_approval_stats = AsyncMock(return_value=ApprovalStats(
        pending_count=5,
        approved_count=100,
        rejected_count=10,
        avg_approval_time_seconds=120.5,
        by_risk_band={'high': 3, 'critical': 2}
    ))
    return client


@pytest.fixture
def mock_response_producer():
    """Mock ApprovalResponseProducer"""
    producer = MagicMock()
    producer.initialize = AsyncMock()
    producer.close = AsyncMock()
    producer.send_approval_response = AsyncMock()
    return producer


@pytest.fixture
def mock_metrics():
    """Mock NeuralHiveMetrics"""
    metrics = MagicMock()
    metrics.increment_approval_requests_received = MagicMock()
    metrics.increment_approvals_total = MagicMock()
    metrics.increment_api_requests = MagicMock()
    metrics.observe_processing_duration = MagicMock()
    metrics.observe_time_to_decision = MagicMock()
    metrics.update_pending_gauge = MagicMock()
    return metrics


@pytest.fixture
def admin_user():
    """Usuario admin autenticado para testes"""
    return {
        'user_id': 'user-001',
        'email': 'admin@example.com',
        'name': 'Admin User',
        'preferred_username': 'admin',
        'roles': ['neural-hive-admin', 'user']
    }


@pytest.fixture
def non_admin_user():
    """Usuario nao-admin para testes de autorizacao"""
    return {
        'user_id': 'user-002',
        'email': 'user@example.com',
        'name': 'Regular User',
        'preferred_username': 'regular',
        'roles': ['user']
    }
