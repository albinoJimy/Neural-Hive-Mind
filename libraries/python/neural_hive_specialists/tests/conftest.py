"""
Fixtures compartilhadas para todos os testes da biblioteca neural_hive_specialists.
"""

import pytest
from unittest.mock import Mock, MagicMock
from typing import Dict, Any
import uuid

from neural_hive_specialists.config import SpecialistConfig
from neural_hive_specialists.schemas import CognitivePlanSchema, TaskSchema


# ============================================================================
# Fixtures de Configuração
# ============================================================================

@pytest.fixture
def mock_config():
    """Retorna SpecialistConfig com valores de teste."""
    return SpecialistConfig(
        specialist_type="test",
        specialist_version="1.0.0",
        service_name="test-specialist",
        environment="test",
        log_level="DEBUG",
        mlflow_tracking_uri="http://localhost:5000",
        mlflow_experiment_name="test-experiment",
        mlflow_model_name="test-model",
        mlflow_model_stage="Production",
        mongodb_uri="mongodb://localhost:27017",
        mongodb_database="test_neural_hive",
        mongodb_opinions_collection="test_opinions",
        redis_cluster_nodes="localhost:6379",
        neo4j_uri="bolt://localhost:7687",
        neo4j_password="test_password",
        grpc_port=50051,
        http_port=8000,
        supported_domains=["test_domain"],
        supported_plan_versions=["1.0.0"],
        circuit_breaker_failure_threshold=5,
        circuit_breaker_recovery_timeout=60,
        enable_circuit_breaker=True,
        ledger_buffer_size=100,
        mlflow_cache_ttl_seconds=3600,
        enable_explainability=True,
        enable_caching=True,
        enable_model_monitoring=True,
        # Desabilitar assinatura digital em testes
        enable_digital_signature=False,
        enable_schema_validation=False,
        ledger_schema_version="2.0.0",
    )


@pytest.fixture
def mock_config_no_circuit_breaker(mock_config):
    """Retorna SpecialistConfig com circuit breakers desabilitados."""
    config = mock_config.copy()
    config.enable_circuit_breaker = False
    return config


# ============================================================================
# Fixtures de Componentes Mockados
# ============================================================================

@pytest.fixture
def mock_mlflow_client(mocker, mock_config):
    """MLflowClient mockado com métodos stub."""
    client = mocker.MagicMock()
    client.config = mock_config
    client._enabled = True
    client._model_cache = {}
    client.used_expired_cache_recently = False
    client._circuit_breaker_state = 'closed'
    client.load_model_with_fallback = mocker.MagicMock(return_value=Mock())
    client.get_last_model_update = mocker.MagicMock(return_value="2025-01-10T12:00:00Z")
    client.is_connected = mocker.MagicMock(return_value=True)
    return client


@pytest.fixture
def mock_ledger_client(mocker, mock_config):
    """LedgerClient mockado."""
    client = mocker.MagicMock()
    client.config = mock_config
    client._buffer_max_size = mock_config.ledger_buffer_size
    client._opinion_buffer = mocker.MagicMock()
    client._opinion_buffer.qsize = mocker.MagicMock(return_value=0)
    client._circuit_breaker_state = 'closed'
    client._last_save_was_buffered = False
    client.save_opinion_with_fallback = mocker.MagicMock(return_value="opinion-123")
    client.get_opinion = mocker.MagicMock(return_value=None)
    client.is_connected = mocker.MagicMock(return_value=True)
    client.get_buffer_size = mocker.MagicMock(return_value=0)
    client.was_last_save_buffered = mocker.MagicMock(return_value=False)
    return client


@pytest.fixture
def mock_explainability_gen(mocker, mock_config):
    """ExplainabilityGenerator mockado."""
    gen = mocker.MagicMock()
    gen.config = mock_config
    gen._circuit_breaker_state = 'closed'
    gen.generate = mocker.MagicMock(return_value=(
        "explainability-token-123",
        {
            "method": "heuristic",
            "model_version": "heuristic",
            "model_type": "heuristic",
            "feature_importances": []
        }
    ))
    return gen


@pytest.fixture
def mock_metrics(mocker):
    """SpecialistMetrics mockado."""
    metrics = mocker.MagicMock()
    metrics.record_evaluation_time = mocker.MagicMock()
    metrics.increment_evaluation_count = mocker.MagicMock()
    metrics.set_circuit_breaker_state = mocker.MagicMock()
    metrics.increment_circuit_breaker_failure = mocker.MagicMock()
    metrics.increment_fallback_used = mocker.MagicMock()
    return metrics


# ============================================================================
# Fixtures de Dados de Teste
# ============================================================================

@pytest.fixture
def sample_cognitive_plan() -> Dict[str, Any]:
    """Retorna plano cognitivo válido."""
    return {
        "plan_id": f"plan-{uuid.uuid4()}",
        "version": "1.0.0",
        "intent_id": f"intent-{uuid.uuid4()}",
        "correlation_id": f"corr-{uuid.uuid4()}",
        "trace_id": f"trace-{uuid.uuid4()}",
        "span_id": f"span-{uuid.uuid4()}",
        "tasks": [
            {
                "task_id": "task-1",
                "task_type": "analysis",
                "name": "Analyze Data",
                "description": "Analyze input data",
                "dependencies": [],
                "estimated_duration_ms": 1000,
                "required_capabilities": ["data_analysis"],
                "parameters": {"param1": "value1"},
                "metadata": {}
            },
            {
                "task_id": "task-2",
                "task_type": "transformation",
                "name": "Transform Data",
                "description": "Transform analyzed data",
                "dependencies": ["task-1"],
                "estimated_duration_ms": 2000,
                "required_capabilities": ["data_transformation"],
                "parameters": {},
                "metadata": {}
            }
        ],
        "execution_order": ["task-1", "task-2"],
        "original_domain": "test_domain",
        "original_priority": "normal",
        "original_security_level": "public",
        "risk_score": 0.3,
        "risk_band": "low",
        "complexity_score": 0.5,
        "metadata": {}
    }


@pytest.fixture
def sample_cognitive_plan_invalid() -> Dict[str, Any]:
    """Retorna plano cognitivo com erros de validação."""
    return {
        "plan_id": "",  # Inválido: vazio
        "version": "1.0",  # Inválido: não é semver completo
        "intent_id": f"intent-{uuid.uuid4()}",
        "tasks": [],  # Inválido: sem tarefas
        "original_domain": "test_domain",
        "original_priority": "invalid_priority",  # Inválido
    }


@pytest.fixture
def sample_evaluation_result() -> Dict[str, Any]:
    """Retorna resultado de avaliação válido."""
    return {
        "recommendation": "approve",
        "confidence_score": 0.85,
        "risk_score": 0.2,
        "estimated_effort_hours": 8.5,
        "reasoning_summary": "Modelo sugere aprovação baseado nas características X, Y e Z.",
        "reasoning_factors": [
            {
                "factor": "Technical feasibility",
                "weight": 0.3,
                "score": 0.9,
                "contribution": "positive"
            },
            {
                "factor": "Resource availability",
                "weight": 0.25,
                "score": 0.8,
                "contribution": "positive"
            }
        ],
        "suggested_mitigations": [
            {
                "risk": "Data quality issues",
                "mitigation": "Implement data validation",
                "priority": "high"
            }
        ],
        "metadata": {
            "model_used": "RandomForestClassifier",
            "features_analyzed": 15
        }
    }


@pytest.fixture
def sample_opinion() -> Dict[str, Any]:
    """Retorna parecer estruturado completo."""
    return {
        "opinion_id": f"opinion-{uuid.uuid4()}",
        "specialist_type": "test",
        "specialist_version": "1.0.0",
        "plan_id": f"plan-{uuid.uuid4()}",
        "intent_id": f"intent-{uuid.uuid4()}",
        "correlation_id": f"corr-{uuid.uuid4()}",
        "recommendation": "proceed",
        "confidence_score": 0.85,
        "risk_score": 0.2,
        "estimated_effort_hours": 8.5,
        "reasoning_factors": [
            {
                "factor": "Technical feasibility",
                "weight": 0.3,
                "score": 0.9,
                "contribution": "positive"
            }
        ],
        "suggested_mitigations": [
            {
                "risk": "Data quality issues",
                "mitigation": "Implement data validation",
                "priority": "high"
            }
        ],
        "explainability_token": "explainability-token-123",
        "processing_time_ms": 150.5,
        "timestamp": "2025-01-10T12:00:00Z",
        "metadata": {}
    }


# ============================================================================
# Fixtures de gRPC (para testes de contrato)
# ============================================================================

@pytest.fixture
def mock_specialist(mocker, mock_config):
    """Retorna especialista mockado para testes gRPC."""
    specialist = mocker.MagicMock()
    specialist.specialist_type = mock_config.specialist_type
    specialist.specialist_version = mock_config.specialist_version
    specialist.config = mock_config

    # Mock evaluate_plan para retornar parecer válido
    specialist.evaluate_plan = mocker.MagicMock(return_value={
        'opinion_id': 'test-opinion-123',
        'specialist_type': mock_config.specialist_type,
        'specialist_version': mock_config.specialist_version,
        'opinion': {
            'confidence_score': 0.85,
            'risk_score': 0.2,
            'recommendation': 'approve',
            'reasoning_summary': 'Test reasoning',
            'reasoning_factors': [],
            'explainability_token': 'test-token',
            'mitigations': [],
            'metadata': {}
        }
    })

    # Mock health_check
    specialist.health_check = mocker.MagicMock(return_value={
        'status': 'SERVING',
        'details': {}
    })

    # Mock get_capabilities
    specialist.get_capabilities = mocker.MagicMock(return_value={
        'specialist_type': mock_config.specialist_type,
        'version': mock_config.specialist_version,
        'supported_domains': mock_config.supported_domains,
        'supported_plan_versions': mock_config.supported_plan_versions,
        'metrics': {
            'average_processing_time_ms': 100.0,
            'accuracy_score': 0.95,
            'total_evaluations': 1000,
            'last_model_update': '2025-01-10T12:00:00'
        },
        'configuration': {}
    })

    return specialist


@pytest.fixture
def grpc_server(mock_specialist, mock_config):
    """Servidor gRPC de teste."""
    import grpc
    from neural_hive_specialists.grpc_server import create_grpc_server_with_observability

    server = create_grpc_server_with_observability(mock_specialist, mock_config)
    port = server.add_insecure_port('localhost:0')
    server.start()

    yield port

    server.stop(grace=0)


@pytest.fixture
def grpc_channel(grpc_server):
    """Canal gRPC de teste."""
    import grpc

    channel = grpc.insecure_channel(f'localhost:{grpc_server}')
    yield channel
    channel.close()


@pytest.fixture
def grpc_stub(grpc_channel):
    """Stub do cliente gRPC."""
    from neural_hive_specialists.proto_gen import specialist_pb2_grpc

    return specialist_pb2_grpc.SpecialistServiceStub(grpc_channel)


# ============================================================================
# Fixtures de Integração (testcontainers)
# ============================================================================

@pytest.fixture(scope="session")
def mongodb_container():
    """Container MongoDB com escopo de sessão."""
    pytest.importorskip("testcontainers")
    from testcontainers.mongodb import MongoDbContainer

    container = MongoDbContainer("mongo:7.0")
    container.start()

    yield container

    container.stop()


@pytest.fixture(scope="session")
def redis_container():
    """Container Redis com escopo de sessão."""
    pytest.importorskip("testcontainers")
    from testcontainers.redis import RedisContainer

    container = RedisContainer("redis:7-alpine")
    container.start()

    yield container

    container.stop()


@pytest.fixture
def mongodb_uri(mongodb_container):
    """URI de conexão MongoDB."""
    return mongodb_container.get_connection_url()


@pytest.fixture
def redis_uri(redis_container):
    """URI de conexão Redis."""
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    return f"{host}:{port}"


# ============================================================================
# Fixtures de Limpeza
# ============================================================================

@pytest.fixture(autouse=True)
def cleanup_metrics():
    """Limpa registros Prometheus entre testes."""
    yield
    # Limpeza será implementada se necessário


@pytest.fixture(autouse=True)
def reset_circuit_breakers():
    """Reseta estado de circuit breakers entre testes."""
    yield
    # Reset será implementado se necessário
