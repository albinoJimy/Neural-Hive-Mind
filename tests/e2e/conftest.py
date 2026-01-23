"""
Pytest configuration and fixtures for E2E tests.

This module provides:
- Custom markers for test categorization
- Session-scoped fixtures for shared resources
- Fixtures for database connections (MongoDB, PostgreSQL)
- Fixtures for Temporal client
- Fixtures for Kafka consumer/producer
- Fixtures for FlowCOrchestrator
"""

import asyncio
import logging
import os
from typing import Any, Dict, Generator, Optional

import pytest

# Conditionally import fixture modules - they may not all exist
pytest_plugins = []

# Try to register each plugin module, skip if not found
_fixture_modules = [
    "tests.e2e.fixtures.kubernetes",
    "tests.e2e.fixtures.kafka",
    "tests.e2e.fixtures.databases",
    "tests.e2e.fixtures.services",
    "tests.e2e.fixtures.test_data",
    "tests.e2e.fixtures.schema_registry",
    "tests.e2e.fixtures.avro_helpers",
    "tests.e2e.fixtures.specialists",
    "tests.e2e.fixtures.circuit_breakers",
]

for module in _fixture_modules:
    try:
        __import__(module)
        pytest_plugins.append(module)
    except ImportError:
        pass

# Configuration from environment
TEMPORAL_ENDPOINT = os.getenv(
    "TEMPORAL_ENDPOINT",
    "temporal-frontend.neural-hive-temporal.svc.cluster.local:7233",
)
TEMPORAL_NAMESPACE = os.getenv("TEMPORAL_NAMESPACE", "default")
MONGODB_URI = os.getenv(
    "MONGODB_URI",
    "mongodb://mongodb-cluster.mongodb-cluster.svc.cluster.local:27017",
)
MONGODB_DATABASE = os.getenv("MONGODB_DATABASE", "neural_hive")
POSTGRESQL_TICKETS_URI = os.getenv(
    "POSTGRESQL_TICKETS_URI",
    "postgresql://postgres:password@postgresql-tickets.neural-hive-orchestration.svc.cluster.local:5432/execution_tickets",
)
POSTGRESQL_TEMPORAL_URI = os.getenv(
    "POSTGRESQL_TEMPORAL_URI",
    "postgresql://postgres:password@postgresql-temporal.neural-hive-temporal.svc.cluster.local:5432/temporal",
)
KAFKA_BOOTSTRAP = os.getenv(
    "KAFKA_BOOTSTRAP",
    "neural-hive-kafka-bootstrap.neural-hive-kafka.svc.cluster.local:9092",
)
REDIS_URL = os.getenv(
    "REDIS_URL",
    "redis://redis-cluster.redis-cluster.svc.cluster.local:6379",
)


def pytest_configure(config: pytest.Config) -> None:
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "e2e: End-to-end tests (requires Kubernetes cluster)")
    config.addinivalue_line("markers", "slow: Slow tests (>1 minute)")
    config.addinivalue_line("markers", "k8s: Tests that interact with Kubernetes")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "flow_c: Flow C specific tests")
    config.addinivalue_line("markers", "phase2: Phase 2 specific tests")


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an event loop for the test session."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
def _configure_logging() -> None:
    """Configure logging for tests."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


# ============================================
# Temporal Fixtures
# ============================================


@pytest.fixture(scope="session")
async def temporal_client():
    """
    Session-scoped Temporal client fixture.

    Provides a connected Temporal client for workflow interactions.
    """
    try:
        from temporalio.client import Client

        client = await Client.connect(
            TEMPORAL_ENDPOINT,
            namespace=TEMPORAL_NAMESPACE,
        )
        yield client
        # Note: temporalio client doesn't have explicit close
    except ImportError:
        pytest.skip("temporalio not installed")
    except Exception as e:
        pytest.skip(f"Could not connect to Temporal: {e}")


@pytest.fixture
async def temporal_test_helper():
    """
    Function-scoped Temporal test helper fixture.

    Provides TemporalTestHelper for workflow validation.
    """
    try:
        from tests.e2e.utils.temporal_helpers import TemporalTestHelper

        helper = TemporalTestHelper(
            endpoint=TEMPORAL_ENDPOINT,
            namespace=TEMPORAL_NAMESPACE,
        )
        await helper.connect()
        yield helper
        await helper.close()
    except ImportError:
        pytest.skip("temporal_helpers not available")
    except Exception as e:
        pytest.skip(f"Could not create Temporal helper: {e}")


# ============================================
# MongoDB Fixtures
# ============================================


@pytest.fixture(scope="session")
def mongodb_client():
    """
    Session-scoped MongoDB client fixture.

    Provides a connected MongoDB database client.
    """
    try:
        from pymongo import MongoClient

        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        # Test connection
        client.server_info()
        db = client[MONGODB_DATABASE]
        yield db
        client.close()
    except ImportError:
        pytest.skip("pymongo not installed")
    except Exception as e:
        pytest.skip(f"Could not connect to MongoDB: {e}")


@pytest.fixture
def mongodb_test_helper():
    """
    Function-scoped MongoDB test helper fixture.

    Provides MongoDBTestHelper for persistence validation.
    """
    try:
        from tests.e2e.utils.database_helpers import MongoDBTestHelper

        helper = MongoDBTestHelper(uri=MONGODB_URI, database=MONGODB_DATABASE)
        helper.connect()
        yield helper
        helper.close()
    except ImportError:
        pytest.skip("database_helpers not available")
    except Exception as e:
        pytest.skip(f"Could not create MongoDB helper: {e}")


# ============================================
# PostgreSQL Fixtures
# ============================================


@pytest.fixture(scope="session")
def postgresql_tickets_conn():
    """
    Session-scoped PostgreSQL connection for execution tickets.

    Provides a connected PostgreSQL connection for ticket queries.
    """
    try:
        import psycopg2

        conn = psycopg2.connect(POSTGRESQL_TICKETS_URI)
        yield conn
        conn.close()
    except ImportError:
        pytest.skip("psycopg2 not installed")
    except Exception as e:
        pytest.skip(f"Could not connect to PostgreSQL tickets: {e}")


@pytest.fixture(scope="session")
def postgresql_temporal_conn():
    """
    Session-scoped PostgreSQL connection for Temporal.

    Provides a connected PostgreSQL connection for Temporal state queries.
    """
    try:
        import psycopg2

        conn = psycopg2.connect(POSTGRESQL_TEMPORAL_URI)
        yield conn
        conn.close()
    except ImportError:
        pytest.skip("psycopg2 not installed")
    except Exception as e:
        pytest.skip(f"Could not connect to PostgreSQL temporal: {e}")


@pytest.fixture
def postgresql_tickets_helper():
    """
    Function-scoped PostgreSQL tickets helper fixture.

    Provides PostgreSQLTicketsHelper for ticket validation.
    """
    try:
        from tests.e2e.utils.database_helpers import PostgreSQLTicketsHelper

        helper = PostgreSQLTicketsHelper(uri=POSTGRESQL_TICKETS_URI)
        helper.connect()
        yield helper
        helper.close()
    except ImportError:
        pytest.skip("database_helpers not available")
    except Exception as e:
        pytest.skip(f"Could not create PostgreSQL helper: {e}")


# ============================================
# Kafka Fixtures
# ============================================


@pytest.fixture
def kafka_test_helper():
    """
    Function-scoped Kafka test helper fixture.

    Provides KafkaTestHelper for message validation.
    """
    try:
        from tests.e2e.utils.kafka_helpers import KafkaTestHelper

        helper = KafkaTestHelper(bootstrap_servers=KAFKA_BOOTSTRAP)
        yield helper
        helper.close()
    except ImportError:
        pytest.skip("kafka_helpers not available")
    except Exception as e:
        pytest.skip(f"Could not create Kafka helper: {e}")


# ============================================
# Redis Fixtures
# ============================================


@pytest.fixture(scope="session")
def redis_client():
    """
    Session-scoped Redis client fixture.

    Provides a connected Redis client.
    """
    try:
        import redis

        client = redis.from_url(REDIS_URL)
        client.ping()  # Test connection
        yield client
        client.close()
    except ImportError:
        pytest.skip("redis not installed")
    except Exception as e:
        pytest.skip(f"Could not connect to Redis: {e}")


# ============================================
# FlowCOrchestrator Fixtures
# ============================================


@pytest.fixture
async def flow_c_orchestrator():
    """
    Function-scoped FlowCOrchestrator fixture.

    Provides an initialized FlowCOrchestrator for Flow C execution.
    """
    try:
        from neural_hive_integration.orchestration.flow_c_orchestrator import (
            FlowCOrchestrator,
        )

        orchestrator = FlowCOrchestrator()
        await orchestrator.initialize()
        yield orchestrator
        await orchestrator.close()
    except ImportError:
        pytest.skip("FlowCOrchestrator not available")
    except Exception as e:
        pytest.skip(f"Could not create FlowCOrchestrator: {e}")


# ============================================
# Test Data Fixtures
# ============================================


@pytest.fixture
def synthetic_decision() -> Dict[str, Any]:
    """
    Fixture providing a synthetic consolidated decision for testing.

    Returns a valid consolidated decision dictionary.
    """
    import uuid
    from datetime import datetime, timedelta

    intent_id = f"intent-test-{uuid.uuid4().hex[:8]}"
    plan_id = f"plan-test-{uuid.uuid4().hex[:8]}"
    decision_id = f"decision-test-{uuid.uuid4().hex[:8]}"
    correlation_id = f"corr-test-{uuid.uuid4().hex[:8]}"

    return {
        "intent_id": intent_id,
        "plan_id": plan_id,
        "decision_id": decision_id,
        "correlation_id": correlation_id,
        "priority": 5,
        "risk_band": "medium",
        "cognitive_plan": {
            "plan_id": plan_id,
            "intent_id": intent_id,
            "correlation_id": correlation_id,
            "description": "Test Plan",
            "created_at": datetime.utcnow().isoformat(),
            "tasks": [
                {
                    "task_id": f"task-{uuid.uuid4().hex[:8]}",
                    "type": "code_generation",
                    "description": "Generate test code",
                    "capabilities": ["python"],
                    "template_id": "default",
                    "parameters": {},
                    "dependencies": [],
                    "priority": 1,
                }
            ],
            "estimated_duration_minutes": 10,
            "sla_deadline": (datetime.utcnow() + timedelta(hours=4)).isoformat(),
        },
        "specialists_opinions": [
            {
                "specialist_type": "technical",
                "confidence": 0.9,
                "recommendation": "approve",
                "reasoning": "Test approval",
            }
        ],
        "consensus_score": 0.9,
        "approved": True,
        "created_at": datetime.utcnow().isoformat(),
    }


@pytest.fixture
def test_plan_id() -> str:
    """Fixture providing a unique test plan ID."""
    import uuid
    return f"plan-pytest-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def test_intent_id() -> str:
    """Fixture providing a unique test intent ID."""
    import uuid
    return f"intent-pytest-{uuid.uuid4().hex[:8]}"


# ============================================
# Status Tracking Fixtures (Flow C)
# ============================================


@pytest.fixture
def ticket_status_tracker(mongodb_test_helper, postgresql_tickets_helper):
    """
    Fixture que fornece TicketStatusTracker configurado.

    Usado para rastrear transições de status em testes do Fluxo C.
    """
    try:
        from tests.e2e.utils.status_tracker import TicketStatusTracker

        tracker = TicketStatusTracker(
            mongodb_helper=mongodb_test_helper,
            postgresql_helper=postgresql_tickets_helper,
            poll_interval_seconds=1.0,
        )
        yield tracker
        tracker.clear_history()
    except ImportError:
        pytest.skip("status_tracker not available")
    except Exception as e:
        pytest.skip(f"Could not create TicketStatusTracker: {e}")


@pytest.fixture
def flow_c_status_tracker(ticket_status_tracker):
    """
    Fixture que fornece FlowCStatusTracker especializado.

    Usado para monitorar etapas C1-C6 do fluxo de orquestração.
    """
    try:
        from tests.e2e.utils.status_tracker import FlowCStatusTracker

        return FlowCStatusTracker(ticket_status_tracker)
    except ImportError:
        pytest.skip("FlowCStatusTracker not available")


@pytest.fixture
def mock_executor_registry():
    """
    Fixture que fornece registry de executores mock.

    Usado para injetar executores simulados em testes de falha.
    """
    class MockExecutorRegistry:
        def __init__(self):
            self._executors = {}

        def register(self, task_type: str, executor):
            self._executors[task_type] = executor

        def get_executor(self, task_type: str):
            return self._executors.get(task_type)

        def has_executor(self, task_type: str) -> bool:
            return task_type in self._executors

    return MockExecutorRegistry()


@pytest.fixture
def flow_c_test_context(
    ticket_status_tracker,
    kafka_test_helper,
    mongodb_test_helper,
    postgresql_tickets_helper,
    temporal_test_helper,
):
    """
    Contexto completo para testes do Fluxo C.

    Agrupa todos os helpers necessários em um único objeto.
    """
    return {
        "status_tracker": ticket_status_tracker,
        "kafka_helper": kafka_test_helper,
        "mongodb_helper": mongodb_test_helper,
        "postgresql_helper": postgresql_tickets_helper,
        "temporal_helper": temporal_test_helper,
    }
