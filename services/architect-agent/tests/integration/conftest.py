"""Pytest configuration e fixtures para testes de integração do Architect Agent.

Este módulo fornece fixtures para testes E2E usando Docker Compose.
Os testes de integração utilizam serviços reais (MongoDB, Kafka, OPA) via containers.
"""
import asyncio
import os
import pytest
import pytest_asyncio
from typing import AsyncGenerator, Generator
import subprocess
import time
from motor.motor_asyncio import AsyncIOMotorClient
from confluent_kafka import Consumer, Producer
import structlog

from src.config.settings import get_settings
from src.api.app import create_app
from src.repositories.architecture_repository import ArchitectureRepository
from src.repositories.validation_repository import ValidationRepository
from src.repositories.evolution_repository import EvolutionRepository

logger = structlog.get_logger(__name__)

# Flag para controlar se o Docker Compose deve ser gerenciado pelo pytest
MANAGE_DOCKER = os.getenv("MANAGE_DOCKER", "true").lower() == "true"

# Compose file path
COMPOSE_FILE = os.path.join(os.path.dirname(__file__), "docker-compose.integration.yml")


@pytest.fixture(scope="session")
def event_loop():
    """Cria event loop para testes assíncronos."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def docker_compose():
    """Gerencia ciclo de vida do Docker Compose para testes de integração."""
    if not MANAGE_DOCKER:
        logger.info("DOCKER_MANAGEMENT_DISABLED", message="Assuming services are already running")
        yield
        return

    logger.info("docker_compose_starting")

    # Iniciar containers
    subprocess.run(
        ["docker-compose", "-f", COMPOSE_FILE, "up", "-d"], check=True, capture_output=True
    )

    # Aguardar serviços ficarem prontos
    _wait_for_services()

    yield

    # Derrubar containers
    logger.info("docker_compose_stopping")
    subprocess.run(
        ["docker-compose", "-f", COMPOSE_FILE, "down", "-v"], check=True, capture_output=True
    )


def _wait_for_services(timeout: int = 60):
    """Aguarda que os serviços essenciais estejam prontos.

    Args:
        timeout: Tempo máximo de espera em segundos
    """
    settings = get_settings()
    start_time = time.time()

    services_ready = {
        "mongodb": False,
        "kafka": False,
        "opa": False,
    }

    while time.time() - start_time < timeout:
        # Verificar MongoDB
        if not services_ready["mongodb"]:
            try:
                client = AsyncIOMotorClient(settings.mongodb.url, serverSelectionTimeoutMS=2000)
                client.admin.command("ping")
                services_ready["mongodb"] = True
                logger.info("mongodb_ready")
            except Exception:
                pass

        # Verificar Kafka
        if not services_ready["kafka"]:
            try:
                conf = {
                    "bootstrap.servers": settings.kafka.bootstrap_servers,
                    "group.id": "test-health-check",
                    "auto.offset.reset": "earliest",
                }
                consumer = Consumer(conf)
                consumer.list_topics(timeout=2)
                consumer.close()
                services_ready["kafka"] = True
                logger.info("kafka_ready")
            except Exception:
                pass

        # Verificar OPA (se configurado)
        if not services_ready["opa"]:
            try:
                import httpx

                response = httpx.get(f"{settings.opa.url}/health", timeout=2)
                if response.status_code == 200:
                    services_ready["opa"] = True
                    logger.info("opa_ready")
            except Exception:
                pass

        if all(services_ready.values()):
            logger.info("all_services_ready")
            return

        time.sleep(2)

    not_ready = [k for k, v in services_ready.items() if not v]
    raise Exception(f"Services not ready after {timeout}s: {not_ready}")


@pytest.fixture
async def mongo_client(docker_compose) -> AsyncGenerator[AsyncIOMotorClient, None]:
    """Cliente MongoDB para testes de integração."""
    settings = get_settings()
    client = AsyncIOMotorClient(settings.mongodb.url)

    # Garantir database limpa
    await client.drop_database(settings.mongodb.database)

    yield client

    # Cleanup
    await client.drop_database(settings.mongodb.database)
    client.close()


@pytest.fixture
async def mongo_database(mongo_client) -> AsyncGenerator:
    """Database instance para testes."""
    settings = get_settings()
    return mongo_client[settings.mongodb.database]


@pytest.fixture
def kafka_producer(docker_compose) -> Generator:
    """Producer Kafka para testes."""
    settings = get_settings()
    conf = {
        "bootstrap.servers": settings.kafka.bootstrap_servers,
        "client.id": "architect-agent-test-producer",
    }
    producer = Producer(conf)
    yield producer
    producer.flush()


@pytest.fixture
def kafka_consumer(docker_compose) -> Generator:
    """Consumer Kafka para testes."""
    settings = get_settings()
    conf = {
        "bootstrap.servers": settings.kafka.bootstrap_servers,
        "group.id": f"architect-agent-test-{time.time()}",
        "auto.offset.reset": "earliest",
    }
    consumer = Consumer(conf)
    yield consumer
    consumer.close()


@pytest.fixture
def opa_url(docker_compose) -> str:
    """URL do OPA para testes."""
    settings = get_settings()
    return settings.opa.url


@pytest.fixture
async def test_app(docker_compose, mongo_client):
    """Aplicação FastAPI configurada para testes."""
    from fastapi.testclient import TestClient

    app = create_app()
    client = TestClient(app)
    yield client


@pytest.fixture
async def architecture_repository(mongo_database):
    """Repository de arquitetura para testes."""
    return ArchitectureRepository()


@pytest.fixture
async def validation_repository(mongo_database):
    """Repository de validação para testes."""
    return ValidationRepository()


@pytest.fixture
async def evolution_repository(mongo_database):
    """Repository de evolução para testes."""
    return EvolutionRepository()


@pytest.fixture
def sample_cognitive_plan():
    """Plano cognitivo de exemplo para testes."""
    return {
        "plan_id": "plan-test-integration-001",
        "intent": {
            "action": "design",
            "subject": "payment_processing_api",
            "context": {
                "domain": "technical",
                "requirements": ["rest", "authentication", "pci_compliance"],
            },
        },
        "original_intent_text": "Design a payment processing API with REST endpoints and PCI compliance",
        "specialists": ["technical", "architecture", "security"],
        "created_at": "2026-03-27T10:00:00Z",
    }


@pytest.fixture
def sample_architecture_plan():
    """Plano de arquitetura de exemplo para testes."""
    from src.models.architecture import ArchitecturePlan, ArchitectureType, Component, Pattern

    return ArchitecturePlan(
        plan_id="arch-test-integration-001",
        cognitive_plan_id="plan-test-integration-001",
        architecture_type=ArchitectureType.MICROSERVICES,
        components=[
            Component(
                name="api-gateway",
                stack="python/fastapi",
                replicas=2,
                ha=True,
            ),
            Component(
                name="payment-service",
                stack="python/fastapi",
                replicas=3,
                ha=True,
            ),
        ],
        patterns=[Pattern.API_GATEWAY, Pattern.CIRCUIT_BREAKER],
        rationale="Microservices architecture for independent scaling and fault isolation",
        requirements={"scalability": "high", "availability": "99.9%"},
    )


@pytest.fixture
def sample_validation_report():
    """Relatório de validação de exemplo para testes."""
    from src.models.validation import (
        ValidationReport,
        Violation,
        Suggestion,
        Trend,
        ViolationType,
        Severity,
    )

    return ValidationReport(
        report_id="validation-test-001",
        repo_url="https://github.com/example/repo",
        branch="main",
        health_score=85,
        trend=Trend.STABLE,
        violations=[
            Violation(
                type=ViolationType.SECURITY,
                severity=Severity.HIGH,
                location="src/auth.py:45",
                description="Hardcoded API key detected",
                suggestion="Move to environment variables",
            ),
        ],
        suggestions=[
            Suggestion(
                priority=1,
                description="Add input validation to API endpoints",
                effort="low",
                affected_files=["src/api/handlers.py"],
            ),
        ],
    )
