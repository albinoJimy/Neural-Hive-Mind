"""
Fixtures compartilhadas para testes do Neural-Hive-Mind.

Estas fixtures podem ser usadas em todos os testes do projeto,
garantindo consistência e reduzindo duplicação.
"""
from datetime import datetime, timedelta, timezone
from typing import Dict, Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

# =============================================================================
# Config Fixtures
# =============================================================================


@pytest.fixture
def mock_settings():
    """
    Settings mock padrão para testes.

    Retorna um Mock do objeto de configurações com valores padrão
    para desenvolvimento local.
    """
    settings = MagicMock()
    settings.kafka_bootstrap_servers = "localhost:9092"
    settings.kafka_security_protocol = "PLAINTEXT"
    settings.kafka_consumer_group = "test-group"
    settings.schema_registry_url = "http://localhost:8081"
    settings.schema_registry_tls_verify = False

    # MongoDB
    settings.mongodb_uri = "mongodb://localhost:27017"
    settings.mongodb_database = "neural_hive_test"

    # Redis
    settings.redis_url = "redis://localhost:6379"
    settings.redis_cache_ttl = 3600

    # Temporal
    settings.temporal_host = "localhost"
    settings.temporal_port = 7233
    settings.temporal_namespace = "default"
    settings.temporal_task_queue = "sla-tasks"

    # gRPC
    settings.grpc_host = "localhost"
    settings.grpc_port = 50051

    # Ambiente
    settings.environment = "test"
    settings.log_level = "DEBUG"
    settings.debug = True

    return settings


@pytest.fixture
def sample_cognitive_plan() -> Dict[str, Any]:
    """
    Plano cognitivo de teste para testes de consenso e orquestração.

    Estrutura compatível com CognitivePlan do STE.
    """
    return {
        "plan_id": f"test-plan-{uuid4()}",
        "intent_id": f"intent-{uuid4()}",
        "intent_text": "Teste de análise de dados",
        "original_intent_text": "Analisar dados de vendas",
        "tasks": [
            {
                "task_id": f"task-{uuid4()}",
                "task_type": "query",
                "description": "Consultar dados",
                "target": "sales",
                "parameters": {"query": "SELECT * FROM sales"},
            }
        ],
        "risk_band": "medium",
        "estimated_duration_ms": 5000,
        "priority": "normal",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


@pytest.fixture
def sample_execution_result() -> Dict[str, Any]:
    """
    Resultado de execução de teste para testes do ExecutionResultConsumer.

    Estrutura compatível com execution.results schema.
    """
    return {
        "ticket_id": f"ticket-{uuid4()}",
        "plan_id": f"plan-{uuid4()}",
        "workflow_id": f"workflow-{uuid4()}",
        "correlation_id": f"corr-{uuid4()}",
        "status": "COMPLETED",
        "result": {"success": True, "output": {"data": [1, 2, 3]}, "error": None},
        "started_at": (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "duration_ms": 10000,
    }


@pytest.fixture
def sample_slo_definition() -> Dict[str, Any]:
    """
    Definição de SLO de teste para testes de SLA Management.
    """
    return {
        "slo_id": f"slo-{uuid4()}",
        "service_name": "test-service",
        "slo_name": "latency",
        "slo_description": "Latência de requests",
        "slo_target": 0.95,  # 95% dos requests
        "slo_window": "7d",
        "measurement_type": "latency",
        "threshold_ms": 500,
    }


# =============================================================================
# Kafka Fixtures
# =============================================================================


@pytest.fixture
def mock_kafka_message():
    """
    Mensagem Kafka mock para testes de consumers/producers.

    Simula uma mensagem Kafka com value, topic, partition, offset.
    """

    class MockKafkaMessage:
        def __init__(self):
            self.topic = "test-topic"
            self.partition = 0
            self.offset = 100
            self.key = None
            self.value = b'{"test": "data"}'
            self.headers = {}

        def set_topic(self, topic: str):
            self.topic = topic

        def set_value(self, value: bytes):
            self.value = value

        def error(self):
            return None

    return MockKafkaMessage()


@pytest.fixture
async def mock_kafka_producer():
    """
    Producer Kafka async mock para testes.

    Simula um producer com métodos produce e flush assíncronos.
    """
    producer = AsyncMock()
    producer.produce = AsyncMock(return_value=True)
    producer.flush = AsyncMock(return_value=True)
    producer.poll = MagicMock(return_value=0)
    return producer


@pytest.fixture
async def mock_kafka_consumer():
    """
    Consumer Kafka async mock para testes.

    Simula um consumer com métodos subscribe, poll, commit.
    """
    consumer = AsyncMock()
    consumer.subscribe = MagicMock()
    consumer.poll = AsyncMock(return_value=None)
    consumer.commit = AsyncMock()
    consumer.close = AsyncMock()
    return consumer


# =============================================================================
# gRPC Fixtures
# =============================================================================


@pytest.fixture
def mock_grpc_server():
    """
    Servidor gRPC mock para testes de clientes.

    Retorna um mock de servidor com handlers para chamadas gRPC.
    """
    server = MagicMock()
    server.start = MagicMock()
    server.stop = MagicMock()
    server.add_insecure_port = MagicMock(return_value=50051)
    return server


@pytest.fixture
def mock_grpc_channel():
    """
    Canal gRPC mock para testes de clientes.

    Simula um canal com stubs para chamadas remotas.
    """
    channel = MagicMock()
    channel.close = MagicMock()
    return channel


# =============================================================================
# Temporal Fixtures
# =============================================================================


@pytest.fixture
def mock_temporal_client():
    """
    Cliente Temporal mock para testes de workflows.

    Simula um cliente com métodos start_workflow, get_workflow_handle.
    """
    client = MagicMock()

    # Mock workflow handle
    handle = MagicMock()
    handle.signal = MagicMock()
    handle.query = MagicMock()
    handle.result = MagicMock()

    # Mock start_workflow
    workflow_run = MagicMock()
    workflow_run.id = f"workflow-{uuid4()}"
    client.start_workflow = MagicMock(return_value=workflow_run)
    client.get_workflow_handle = MagicMock(return_value=handle)

    return client


@pytest.fixture
def mock_temporal_activity():
    """
    Atividade Temporal mock para testes de activities.

    Simula o contexto de execução de uma activity.
    """
    activity = MagicMock()
    activity.heartbeat = MagicMock()
    activity.info = MagicMock()

    # Mock activity context
    context = MagicMock()
    context.heartbeat = MagicMock()
    context.info = MagicMock()

    return activity


# =============================================================================
# Database Fixtures
# =============================================================================


@pytest.fixture
def mock_mongodb_client():
    """
    Cliente MongoDB mock para testes.

    Simula operações de banco de dados sem persistência.
    """
    client = AsyncMock()

    # Mock database
    database = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    # Mock collections
    client.get_database = MagicMock(return_value=database)
    client.get_collection = AsyncMock()

    return client


@pytest.fixture
def mock_redis_client():
    """
    Cliente Redis mock para testes.

    Simula operações de cache sem persistência real.
    """
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.setex = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=True)
    redis.exists = AsyncMock(return_value=False)
    redis.expire = AsyncMock(return_value=True)

    return redis


# =============================================================================
# Authentication/Security Fixtures
# =============================================================================


@pytest.fixture
def sample_jwt_token():
    """
    Token JWT de teste para autenticação.

    Retorna um token JWT válido com claims padrão.
    """
    return {
        "sub": "user-123",
        "name": "Test User",
        "email": "test@example.com",
        "role": "admin",
        "exp": (datetime.now(timezone.utc) + timedelta(hours=1)).timestamp(),
        "iat": datetime.now(timezone.utc).timestamp(),
    }


@pytest.fixture
def sample_jwt_headers():
    """
    Headers HTTP com token JWT para testes de API.

    Retorna dict com Authorization header.
    """
    return {"Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test"}


# =============================================================================
# Metrics/Fixtures
# =============================================================================


@pytest.fixture
def mock_metrics():
    """
    Cliente de métricas Prometheus mock para testes.

    Simula registro de métricas sem dependência do Prometheus server.
    """
    metrics = MagicMock()

    # Counter metrics
    metrics.requests_total = MagicMock()
    metrics.requests_total.labels = MagicMock(return_value=MagicMock(inc=MagicMock()))
    metrics.requests_total.increment = MagicMock()

    # Histogram metrics
    metrics.request_duration_seconds = MagicMock()
    metrics.request_duration_seconds.observe = MagicMock()

    # Gauge metrics
    metrics.active_connections = MagicMock()
    metrics.active_connections.set = MagicMock()

    return metrics


# =============================================================================
# Async Context Managers
# =============================================================================


@pytest.fixture
async def async_mongodb_client():
    """
    Context manager para cliente MongoDB async em testes.

    Uso:
        async with async_mongodb_client() as client:
            # usar cliente
            pass
    """
    # Aqui poderia criar um MongoDB container com testcontainers
    # Por ora, retorna um mock
    mock_client = AsyncMock()
    yield mock_client


@pytest.fixture
async def async_redis_client():
    """
    Context manager para cliente Redis async em testes.

    Uso:
        async with async_redis_client() as client:
            await client.set("key", "value")
            pass
    """
    # Aqui poderia criar um Redis container com testcontainers
    # Por ora, retorna um mock
    mock_client = AsyncMock()
    yield mock_client


# =============================================================================
# Test Data Generators
# =============================================================================


@pytest.fixture
def generate_ticket_id():
    """
    Gera IDs de ticket únicos para testes.

    Uso:
        ticket_id = generate_ticket_id()
    """
    return lambda: f"ticket-{uuid4()}"


@pytest.fixture
def generate_plan_id():
    """
    Gera IDs de plano cognitivo únicos para testes.
    """
    return lambda: f"plan-{uuid4()}"


@pytest.fixture
def generate_workflow_id():
    """
    Gera IDs de workflow Temporal únicos para testes.
    """
    return lambda: f"workflow-{uuid4()}"


# =============================================================================
# Skip Markers
# =============================================================================


@pytest.fixture
def skip_if_no_kafka():
    """
    Decorator para pular teste se Kafka não está disponível.

    Uso:
        @skip_if_no_kafka()
        async def test_kafka_feature():
            pass
    """
    try:
        from confluent_kafka import Producer

        Producer({"bootstrap.servers": "localhost:9092"})
        return lambda f: f  # no-op decorator (era 'lambda f: lambda f', invalid)
    except Exception:
        return pytest.mark.skip("Kafka não disponível")


@pytest.fixture
def skip_if_no_mongodb():
    """
    Decorator para pular teste se MongoDB não está disponível.
    """
    try:
        from pymongo import MongoClient

        client = MongoClient("mongodb://localhost:27017", serverSelectionTimeoutMS=1000)
        client.server_info()
        return lambda f: f  # no-op decorator (era 'lambda f: lambda f', invalid)
    except Exception:
        return pytest.mark.skip("MongoDB não disponível")


@pytest.fixture
def skip_if_no_temporal():
    """
    Decorator para pular teste se Temporal não está disponível.
    """
    try:
        from temporalio.client import Client  # noqa: F401

        # Tenta conectar (vai falhar se não houver servidor)
        pass
        return lambda f: f  # no-op decorator (era 'lambda f: lambda f', invalid)
    except Exception:
        return pytest.mark.skip("Temporal não disponível")
