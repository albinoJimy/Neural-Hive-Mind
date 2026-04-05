"""
Configurações pytest para testes E2E do Execution Ticket Service.

Este módulo fornece fixtures para subir serviços dependentes (PostgreSQL, Kafka, Redis)
via Docker ou usando testcontainers para testes de integração e E2E.
"""
import asyncio
import os
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock

import pytest

# Importar testcontainers apenas quando necessário (evita conflito com módulo kafka)
try:
    from testcontainers.core.container import DockerContainer
    from testcontainers.core.waiting_utils import wait_for_logs
    from testcontainers.kafka import KafkaContainer
    from testcontainers.postgres import PostgresContainer
    from testcontainers.redis import RedisContainer
    TESTCONTAINERS_AVAILABLE = True
except ImportError:
    TESTCONTAINERS_AVAILABLE = False
    # Criar classes dummy para testes sem Docker
    KafkaContainer = None
    PostgresContainer = None
    RedisContainer = None

# Importar modelos para usar nos mocks
from src.models import ExecutionTicket, SLA, QoS, TaskType, Priority, RiskBand, SecurityLevel, TicketStatus

# Configurar variáveis de ambiente para testes E2E
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5432")
os.environ.setdefault("POSTGRES_USER", "test_user")
os.environ.setdefault("POSTGRES_PASSWORD", "test_pass")
os.environ.setdefault("POSTGRES_DATABASE", "test_tickets")
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-32-bytes-long-for-testing")
os.environ.setdefault("ENVIRONMENT", "test")


# ===== OPÇÃO 1: Usar testcontainers (recomendado para CI) =====

@pytest.fixture(scope="session")
def postgres_container() -> Generator[PostgresContainer, None, None]:
    """
    Sobe container PostgreSQL para testes E2E.

    Usa testcontainers para gerenciar o ciclo de vida do container.
    """
    postgres = PostgresContainer(
        image="postgres:17-alpine",
        username="test_user",
        password="test_pass",
        dbname="test_tickets",
        port=5432,
    )

    try:
        postgres.start()
        # Atualizar variáveis de ambiente com a porta exposta
        os.environ["POSTGRES_PORT"] = postgres.get_exposed_port(5432)
        os.environ["POSTGRES_HOST"] = "localhost"

        yield postgres

    finally:
        postgres.stop()


@pytest.fixture(scope="session")
def redis_container() -> Generator[RedisContainer, None, None]:
    """
    Sobe container Redis para testes E2E.
    """
    redis = RedisContainer(image="redis:7-alpine")

    try:
        redis.start()
        redis_url = f"redis://{redis.get_container_host_ip()}:{redis.get_exposed_port(6379)}/0"
        os.environ["REDIS_URL"] = redis_url

        yield redis

    finally:
        redis.stop()


@pytest.fixture(scope="session")
def kafka_container() -> Generator[KafkaContainer, None, None]:
    """
    Sobe container Kafka para testes E2E.
    """
    kafka = KafkaContainer(image="confluentinc/cp-kafka:7.7.1")

    try:
        kafka.start()
        bootstrap_servers = kafka.get_bootstrap_server()
        os.environ["KAFKA_BOOTSTRAP_SERVERS"] = bootstrap_servers

        yield kafka

    finally:
        kafka.stop()


# ===== OPÇÃO 2: Fixtures mockadas (mais rápidas para desenvolvimento local) =====

@pytest.fixture
def mock_postgres_client():
    """
    Cliente PostgreSQL mockado para testes E2E rápidos.

    Em produção, usar postgres_container.
    """
    client = AsyncMock()

    # Funções auxiliares para criar mocks
    def get_ticket_orm(ticket_data):
        mock_orm = MagicMock()
        if isinstance(ticket_data, dict):
            mock_orm.ticket_id = ticket_data.get('ticket_id', 'test-ticket')
            mock_orm.plan_id = ticket_data.get('plan_id', 'plan-123')
            mock_orm.task_type = ticket_data.get('task_type', 'BUILD')
            mock_orm.intent_id = ticket_data.get('intent_id', 'intent-123')
            mock_orm.decision_id = ticket_data.get('decision_id', 'decision-123')
            mock_orm.description = ticket_data.get('description', 'Test ticket')
            mock_orm.dependencies = ticket_data.get('dependencies', [])
            mock_orm.parameters = ticket_data.get('parameters', {})
            mock_orm.metadata = ticket_data.get('metadata', {})
            mock_orm.sla = ticket_data.get('sla', {'deadline': 0, 'timeout_ms': 30000, 'max_retries': 3})
            mock_orm.qos = ticket_data.get('qos', {
                'delivery_mode': 'AT_MOST_ONCE',
                'consistency': 'EVENTUAL',
                'durability': 'TRANSIENT',
            })
            mock_orm.priority = ticket_data.get('priority', 'NORMAL')
            mock_orm.risk_band = ticket_data.get('risk_band', 'medium')
            mock_orm.security_level = ticket_data.get('security_level', 'INTERNAL')
            mock_orm.created_at = ticket_data.get('created_at', 0)
            mock_orm.started_at = ticket_data.get('started_at')
            mock_orm.completed_at = ticket_data.get('completed_at')
        else:
            mock_orm.ticket_id = getattr(ticket_data, 'ticket_id', 'test-ticket')
            mock_orm.plan_id = getattr(ticket_data, 'plan_id', 'plan-123')
            mock_orm.task_type = getattr(ticket_data, 'task_type', 'BUILD')
            mock_orm.intent_id = getattr(ticket_data, 'intent_id', 'intent-123')
            mock_orm.decision_id = getattr(ticket_data, 'decision_id', 'decision-123')
            mock_orm.description = getattr(ticket_data, 'description', 'Test ticket')
            mock_orm.dependencies = getattr(ticket_data, 'dependencies', [])
            mock_orm.parameters = getattr(ticket_data, 'parameters', {})
            mock_orm.metadata = getattr(ticket_data, 'metadata', {})
            mock_orm.sla = getattr(ticket_data, 'sla', {'deadline': 0, 'timeout_ms': 30000, 'max_retries': 3})
            mock_orm.qos = getattr(ticket_data, 'qos', {
                'delivery_mode': 'AT_MOST_ONCE',
                'consistency': 'EVENTUAL',
                'durability': 'TRANSIENT',
            })
            mock_orm.priority = getattr(ticket_data, 'priority', 'NORMAL')
            mock_orm.risk_band = getattr(ticket_data, 'risk_band', 'medium')
            mock_orm.security_level = getattr(ticket_data, 'security_level', 'INTERNAL')
            mock_orm.created_at = getattr(ticket_data, 'created_at', 0)
            mock_orm.started_at = getattr(ticket_data, 'started_at', None)
            mock_orm.completed_at = getattr(ticket_data, 'completed_at', None)

        mock_orm.status = "PENDING"
        mock_orm.retry_count = 0
        mock_orm.error_message = None
        mock_orm.estimated_duration_ms = 5000
        mock_orm.actual_duration_ms = None
        mock_orm.compensation_ticket_id = None
        mock_orm.correlation_id = None
        mock_orm.trace_id = None
        mock_orm.span_id = None
        mock_orm.required_capabilities = []
        mock_orm.schema_version = 1

        # to_pydantic retorna o próprio dict em formato apropriado
        def to_pydantic_impl():
            from src.models import SLA, QoS, TaskType, Priority, RiskBand, SecurityLevel, TicketStatus
            return ExecutionTicket(
                ticket_id=mock_orm.ticket_id,
                plan_id=mock_orm.plan_id,
                intent_id=mock_orm.intent_id,
                decision_id=mock_orm.decision_id,
                task_id=mock_orm.ticket_id,
                task_type=TaskType.BUILD,
                description=mock_orm.description,
                dependencies=mock_orm.dependencies,
                status=TicketStatus.PENDING,
                priority=Priority.NORMAL,
                risk_band=RiskBand.medium,
                sla=SLA(**mock_orm.sla),
                qos=QoS(**mock_orm.qos),
                parameters=mock_orm.parameters,
                required_capabilities=mock_orm.required_capabilities,
                security_level=SecurityLevel.INTERNAL,
                created_at=mock_orm.created_at,
                started_at=mock_orm.started_at,
                completed_at=mock_orm.completed_at,
                estimated_duration_ms=mock_orm.estimated_duration_ms,
                actual_duration_ms=mock_orm.actual_duration_ms,
                retry_count=mock_orm.retry_count,
                error_message=mock_orm.error_message,
                compensation_ticket_id=mock_orm.compensation_ticket_id,
                metadata=mock_orm.metadata,
                schema_version=mock_orm.schema_version,
            )

        mock_orm.to_pydantic = to_pydantic_impl
        return mock_orm

    async def mock_create_ticket(ticket):
        return get_ticket_orm(ticket)

    async def mock_get_ticket_by_id(ticket_id):
        if ticket_id == "non-existent":
            return None
        mock_orm = MagicMock()
        mock_orm.ticket_id = ticket_id
        mock_orm.plan_id = "plan-123"
        mock_orm.status = "PENDING"
        mock_orm.retry_count = 0
        mock_orm.error_message = None
        mock_orm.to_pydantic = MagicMock(return_value=mock_orm)
        return mock_orm

    async def mock_update_ticket_status(ticket_id, status, error_message=None):
        mock_orm = MagicMock()
        mock_orm.ticket_id = ticket_id
        mock_orm.plan_id = "plan-123"
        mock_orm.status = status
        mock_orm.error_message = error_message
        mock_orm.retry_count = 0
        mock_orm.to_pydantic = MagicMock(return_value=mock_orm)
        return mock_orm

    async def mock_increment_retry_count(ticket_id):
        mock_orm = MagicMock()
        mock_orm.ticket_id = ticket_id
        mock_orm.plan_id = "plan-123"
        mock_orm.status = "PENDING"
        mock_orm.retry_count = 1
        mock_orm.to_pydantic = MagicMock(return_value=mock_orm)
        return mock_orm

    async def mock_list_tickets(filters, offset, limit):
        return []

    async def mock_count_tickets(filters):
        return 0

    # Usar AsyncMock para rastrear chamadas
    client.create_ticket = AsyncMock(side_effect=mock_create_ticket)
    client.get_ticket_by_id = AsyncMock(side_effect=mock_get_ticket_by_id)
    client.update_ticket_status = AsyncMock(side_effect=mock_update_ticket_status)
    client.increment_retry_count = AsyncMock(side_effect=mock_increment_retry_count)
    client.list_tickets = AsyncMock(side_effect=mock_list_tickets)
    client.count_tickets = AsyncMock(side_effect=mock_count_tickets)

    return client


@pytest.fixture
def mock_mongodb_client():
    """Cliente MongoDB mockado para testes E2E."""
    client = AsyncMock()

    # Usar AsyncMock diretamente para métodos
    client.save_ticket_audit = AsyncMock(return_value=True)
    client.log_status_change = AsyncMock(return_value=True)
    client.db = MagicMock()
    client.db.__getitem__ = MagicMock(return_value=MagicMock())

    return client


@pytest.fixture
def mock_redis_client():
    """Cliente Redis mockado para testes E2E."""
    client = AsyncMock()

    # Estado simulado do Redis
    redis_store = {}

    async def mock_get(key):
        return redis_store.get(key)

    async def mock_set(key, value, ex=None):
        redis_store[key] = value
        return True

    async def mock_delete(key):
        redis_store.pop(key, None)
        return True

    client.get = mock_get
    client.set = mock_set
    client.delete = mock_delete
    client.clear = lambda: redis_store.clear()

    return client


@pytest.fixture
def mock_kafka_producer():
    """Kafka producer mockado para testes E2E."""
    producer = AsyncMock()

    # Estado compartilhado para rastrear mensagens publicadas
    class KafkaState:
        def __init__(self):
            self.messages = []

        def append(self, msg):
            self.messages.append(msg)

        def clear(self):
            self.messages.clear()

        def __len__(self):
            return len(self.messages)

        def __getitem__(self, index):
            return self.messages[index]

    kafka_state = KafkaState()

    async def mock_publish_ticket(ticket, key=None, timeout_ms=5000):
        kafka_state.append({"ticket": ticket, "key": key})
        return True

    producer.publish_ticket = mock_publish_ticket
    producer._messages = kafka_state
    producer.clear = kafka_state.clear

    return producer


@pytest.fixture
def mock_webhook_manager():
    """Webhook manager mockado para testes E2E."""
    manager = AsyncMock()

    # Estado compartilhado para rastrear webhooks
    class WebhookState:
        def __init__(self):
            self.webhooks = []

        def append(self, event):
            self.webhooks.append(event)

        def clear(self):
            self.webhooks.clear()

        def get_list(self):
            return list(self.webhooks)

        def __len__(self):
            return len(self.webhooks)

    webhook_state = WebhookState()

    async def mock_enqueue_webhook(event):
        webhook_state.append(event)
        return True

    async def mock_start():
        return True

    async def mock_stop():
        return True

    manager.enqueue_webhook = mock_enqueue_webhook
    manager.start = mock_start
    manager.stop = mock_stop
    manager._webhooks = webhook_state
    manager.get_webhooks = webhook_state.get_list
    manager.clear = webhook_state.clear

    return manager


# ===== FIXTURES compartilhadas =====

@pytest.fixture
def sample_ticket_data():
    """Dados de ticket de exemplo para testes."""
    from datetime import datetime, timezone

    return {
        "ticket_id": "test-ticket-001",
        "plan_id": "plan-123",
        "intent_id": "intent-456",
        "decision_id": "decision-789",
        "task_id": "task-001",
        "task_type": "BUILD",
        "description": "Test ticket for E2E tests",
        "dependencies": [],
        "status": "PENDING",
        "priority": "NORMAL",
        "risk_band": "medium",
        "sla": {
            "deadline": None,
            "timeout_ms": 30000,
            "max_retries": 3,
        },
        "qos": {
            "delivery_mode": "AT_MOST_ONCE",
            "consistency": "EVENTUAL",
            "durability": "TRANSIENT",
        },
        "parameters": {"test_param": "test_value"},
        "required_capabilities": [],
        "security_level": "INTERNAL",
        "created_at": int(datetime.now(timezone.utc).timestamp() * 1000),
        "started_at": None,
        "completed_at": None,
        "estimated_duration_ms": 5000,
        "actual_duration_ms": None,
        "retry_count": 0,
        "error_message": None,
        "compensation_ticket_id": None,
        "metadata": {
            "idempotency_key": "test-idempotency-001",
            "webhook_url": "http://localhost:9999/webhook",
        },
        "schema_version": 1,
    }


@pytest.fixture
def sample_compensation_ticket_data():
    """Dados de ticket de compensação de exemplo."""
    from datetime import datetime, timezone

    return {
        "ticket_id": "comp-ticket-001",
        "plan_id": "plan-123",
        "intent_id": "intent-456",
        "decision_id": "decision-789",
        "task_id": "compensate-ticket-001",
        "task_type": "COMPENSATE",
        "description": "Compensation ticket for failed operation",
        "dependencies": [],
        "status": "PENDING",
        "priority": "HIGH",
        "risk_band": "high",
        "sla": {
            "deadline": None,
            "timeout_ms": 120000,
            "max_retries": 1,
        },
        "qos": {
            "delivery_mode": "AT_LEAST_ONCE",
            "consistency": "STRONG",
            "durability": "PERSISTENT",
        },
        "parameters": {
            "action": "rollback",
            "reason": "Original task failed",
            "original_ticket_id": "test-ticket-001",
        },
        "required_capabilities": [],
        "security_level": "INTERNAL",
        "created_at": int(datetime.now(timezone.utc).timestamp() * 1000),
        "started_at": None,
        "completed_at": None,
        "estimated_duration_ms": 2000,
        "actual_duration_ms": None,
        "retry_count": 0,
        "error_message": None,
        "compensation_ticket_id": None,
        "metadata": {},
        "schema_version": 1,
    }


@pytest.fixture
async def setup_test_environment(
    mock_postgres_client,
    mock_mongodb_client,
    mock_redis_client,
    mock_kafka_producer,
    mock_webhook_manager,
):
    """
    Configura ambiente de teste com todos os mocks injetados.

    Este fixture aplica patches nos módulos do serviço para usar os mocks.
    """
    from unittest.mock import patch

    # Patches para os clientes
    with patch("src.database.postgres_client.get_postgres_client", return_value=mock_postgres_client), \
         patch("src.database.mongodb_client.get_mongodb_client", return_value=mock_mongodb_client), \
         patch("src.database.redis_client.get_redis_client", return_value=mock_redis_client), \
         patch("src.kafka.producer.get_kafka_producer", return_value=mock_kafka_producer), \
         patch("src.webhooks.webhook_manager.start_webhook_manager", return_value=mock_webhook_manager):

        # Limpar estado antes do teste
        mock_redis_client.clear()
        mock_kafka_producer.clear()
        mock_webhook_manager.clear()

        yield {
            "postgres": mock_postgres_client,
            "mongodb": mock_mongodb_client,
            "redis": mock_redis_client,
            "kafka": mock_kafka_producer,
            "webhook": mock_webhook_manager,
        }

    # Limpar estado após o teste
    mock_redis_client.clear()
    mock_kafka_producer.clear()
    mock_webhook_manager.clear()


@pytest.fixture
def event_loop():
    """
    Cria event loop personalizado para testes assíncronos.

    Garante que cada teste tem seu próprio event loop isolado.
    """
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
