# tests/e2e/conftest_platform.py
"""
Fixtures para E2E tests de Platform Health e Kafka Flow.

Este módulo fornece:
- HTTP client para health checks
- Helper para verificar saúde de serviços
- Configuração de URLs de serviços (mockável para testes locais)
- Configuração de Kafka (mockável para testes locais)
"""

import asyncio
import os
import time
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import httpx
import pytest

# ============================================================================
# Service URLs Configuration
# ============================================================================

# URLs padrão para ambiente Kubernetes (pode ser sobrescrito via ENV)
DEFAULT_SERVICE_URLS: dict[str, str] = {
    "gateway-intencoes": "http://gateway-intencoes.neural-hive-gateway.svc.cluster.local:8000",
    "semantic-translation-engine": "http://semantic-translation-engine.neural-hive-semantic.svc.cluster.local:8001",
    "consensus-engine": "http://consensus-engine.neural-hive-consensus.svc.cluster.local:8002",
    "orchestrator-dynamic": "http://orchestrator-dynamic.neural-hive-orchestration.svc.cluster.local:8003",
    "approval-service": "http://approval-service.neural-hive-approval.svc.cluster.local:8004",
    "worker-agents": "http://worker-agents.neural-hive-execution.svc.cluster.local:8005",
    "queen-agent": "http://queen-agent.neural-hive-agents.svc.cluster.local:8006",
    "service-registry": "http://service-registry.neural-hive-registry.svc.cluster.local:8007",
    "analyst-agents": "http://analyst-agents.neural-hive-analyst.svc.cluster.local:8010",
    "scout-agents": "http://scout-agents.neural-hive-scout.svc.cluster.local:8011",
    "guard-agents": "http://guard-agents.neural-hive-guard.svc.cluster.local:8012",
    "optimizer-agents": "http://optimizer-agents.neural-hive-optimizer.svc.cluster.local:8013",
    "self-healing-engine": "http://self-healing-engine.neural-hive-healing.svc.cluster.local:8014",
    "execution-ticket-service": "http://execution-ticket-service.neural-hive-tickets.svc.cluster.local:8015",
    "sla-management-system": "http://sla-management-system.neural-hive-sla.svc.cluster.local:8016",
    "code-forge": "http://code-forge.neural-hive-codeforge.svc.cluster.local:8017",
    "mcp-tool-catalog": "http://mcp-tool-catalog.neural-hive-mcp.svc.cluster.local:8018",
    "memory-layer-api": "http://memory-layer-api.neural-hive-memory.svc.cluster.local:8019",
    "explainability-api": "http://explainability-api.neural-hive-explainability.svc.cluster.local:8020",
    "specialist-architecture": "http://specialist-architecture.neural-hive-specialists.svc.cluster.local:8021",
    "specialist-business": "http://specialist-business.neural-hive-specialists.svc.cluster.local:8022",
    "specialist-technical": "http://specialist-technical.neural-hive-specialists.svc.cluster.local:8023",
    "specialist-behavior": "http://specialist-behavior.neural-hive-specialists.svc.cluster.local:8024",
    "specialist-evolution": "http://specialist-evolution.neural-hive-specialists.svc.cluster.local:8025",
}


def get_service_urls() -> dict[str, str]:
    """
    Retorna URLs dos serviços configurados.

    Prioridade:
    1. Variável de ambiente específica (ex: GATEWAY_INTENCOES_URL)
    2. PLATFORM_BASE_URL + porta padrão
    3. URL padrão Kubernetes
    """
    urls = {}

    # Permitir sobrescrever via BASE_URL para testes locais
    base_url = os.getenv("PLATFORM_BASE_URL", "")

    for service, default_url in DEFAULT_SERVICE_URLS.items():
        env_var = f"{service.upper().replace('-', '_')}_URL"
        env_value = os.getenv(env_var)

        if env_value:
            urls[service] = env_value
        elif base_url:
            # Extrair porta da URL padrão
            port = default_url.split(":")[-1]
            urls[service] = f"{base_url}:{port}"
        else:
            urls[service] = default_url

    return urls


# ============================================================================
# Kafka Topics Configuration
# ============================================================================

DEFAULT_KAFKA_TOPICS: dict[str, str] = {
    # Cognitive Pipeline
    "intentions": "intentions",
    "plans.ready": "plans.ready",
    "plans.consensus": "plans.consensus",
    "execution.tickets": "execution.tickets",
    "execution.results": "execution.results",
    "telemetry.orchestration": "telemetry.orchestration",
    # Approval Flow
    "approval.requests": "approval.requests",
    "approval.responses": "approval.responses",
    "approval.dlq": "approval.dlq",
    # MCP
    "mcp.tool.selection.requests": "mcp.tool.selection.requests",
    "mcp.tool.selection.responses": "mcp.tool.selection.responses",
    # Self-Healing
    "self.healing.events": "self.healing.events",
    "self.healing.alerts": "self.healing.alerts",
    # Memory
    "memory.sync.events": "memory.sync.events",
    "memory.dlq": "memory.dlq",
}


def get_kafka_config() -> dict[str, str]:
    """
    Retorna configuração do Kafka.

    Retorna:
        Dict com bootstrap_servers e topics.
    """
    return {
        "bootstrap_servers": os.getenv(
            "KAFKA_BOOTSTRAP_SERVERS",
            "neural-hive-kafka-bootstrap.neural-hive-kafka.svc.cluster.local:9092",
        ),
        "schema_registry": os.getenv(
            "KAFKA_SCHEMA_REGISTRY",
            "http://neural-hive-kafka-schema-registry.neural-hive-kafka.svc.cluster.local:8081",
        ),
        "topics": DEFAULT_KAFKA_TOPICS,
    }


# ============================================================================
# Pytest Configuration
# ============================================================================


def pytest_configure(config: pytest.Config) -> None:
    """Configura pytest com marcadores específicos."""
    config.addinivalue_line("markers", "platform_health: Testes de saúde de toda a plataforma")
    config.addinivalue_line("markers", "kafka_flow: Testes de fluxo Kafka end-to-end")


# ============================================================================
# Fixtures - HTTP Client
# ============================================================================


@pytest.fixture(scope="session")
def event_loop() -> asyncio.AbstractEventLoop:
    """Cria event loop para testes assíncronos."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest.fixture
async def http_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """
    HTTP client assíncrono para requisições HTTP.

    Usa timeout curto (10s) para testes falharem rápido se serviços
    não responderem.
    """
    timeout = httpx.Timeout(10.0, connect=5.0)
    limits = httpx.Limits(max_keepalive_connections=10, max_connections=20)

    async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
        yield client


# ============================================================================
# Fixtures - Service URLs e Kafka Config
# ============================================================================


@pytest.fixture
def service_urls() -> dict[str, str]:
    """URLs base dos serviços para testes."""
    return get_service_urls()


@pytest.fixture
def kafka_config() -> dict[str, str]:
    """Configuração do Kafka para testes."""
    return get_kafka_config()


# ============================================================================
# ServiceHealthHelper Class
# ============================================================================


class ServiceHealthHelper:
    """
    Helper para verificar saúde de serviços.

    Métodos:
        check_health: Verifica endpoint /health
        check_ready: Verifica endpoint /ready
        check_all: Verifica ambos os endpoints
    """

    def __init__(self, client: httpx.AsyncClient, base_url: str):
        self.client = client
        self.base_url = base_url.rstrip("/")

    async def check_health(self) -> dict[str, any]:
        """
        Verifica endpoint /health do serviço.

        Returns:
            Dict com:
                - available (bool): serviço respondeu
                - status_code (int|None): HTTP status ou None se timeout
                - response (dict|None): corpo da resposta JSON ou None
                - error (str|None): mensagem de erro se houver
                - response_time_ms (int): tempo de resposta em ms
        """
        start_time = time.time()

        try:
            response = await self.client.get(f"{self.base_url}/health")
            response_time = int((time.time() - start_time) * 1000)

            return {
                "available": True,
                "status_code": response.status_code,
                "response": response.json() if response.content else None,
                "error": None,
                "response_time_ms": response_time,
            }
        except httpx.TimeoutException:
            response_time = int((time.time() - start_time) * 1000)
            return {
                "available": False,
                "status_code": None,
                "response": None,
                "error": "timeout",
                "response_time_ms": response_time,
            }
        except httpx.ConnectError:
            response_time = int((time.time() - start_time) * 1000)
            return {
                "available": False,
                "status_code": None,
                "response": None,
                "error": "connection_refused",
                "response_time_ms": response_time,
            }
        except Exception as e:
            response_time = int((time.time() - start_time) * 1000)
            return {
                "available": False,
                "status_code": None,
                "response": None,
                "error": str(e),
                "response_time_ms": response_time,
            }

    async def check_ready(self) -> dict[str, any]:
        """
        Verifica endpoint /ready do serviço.

        Returns:
            Dict com mesma estrutura de check_health.
        """
        start_time = time.time()

        try:
            response = await self.client.get(f"{self.base_url}/ready")
            response_time = int((time.time() - start_time) * 1000)

            return {
                "available": True,
                "status_code": response.status_code,
                "response": response.json() if response.content else None,
                "error": None,
                "response_time_ms": response_time,
            }
        except httpx.TimeoutException:
            response_time = int((time.time() - start_time) * 1000)
            return {
                "available": False,
                "status_code": None,
                "response": None,
                "error": "timeout",
                "response_time_ms": response_time,
            }
        except httpx.ConnectError:
            response_time = int((time.time() - start_time) * 1000)
            return {
                "available": False,
                "status_code": None,
                "response": None,
                "error": "connection_refused",
                "response_time_ms": response_time,
            }
        except Exception as e:
            response_time = int((time.time() - start_time) * 1000)
            return {
                "available": False,
                "status_code": None,
                "response": None,
                "error": str(e),
                "response_time_ms": response_time,
            }

    async def check_all(self) -> dict[str, any]:
        """
        Verifica ambos endpoints (/health e /ready).

        Returns:
            Dict com health e ready results.
        """
        health_result, ready_result = await asyncio.gather(
            self.check_health(),
            self.check_ready(),
            return_exceptions=True,
        )

        # Handle exceptions from gather
        if isinstance(health_result, Exception):
            health_result = {"available": False, "error": str(health_result)}
        if isinstance(ready_result, Exception):
            ready_result = {"available": False, "error": str(ready_result)}

        return {
            "health": health_result,
            "ready": ready_result,
        }


# ============================================================================
# Fixtures - Health Helpers
# ============================================================================


@pytest.fixture
def health_helper_factory(http_client: httpx.AsyncClient):
    """
    Factory para criar ServiceHealthHelper.

    Usage:
        helper = health_helper_factory("http://service:8000")
        result = await helper.check_health()
    """

    def _create_helper(base_url: str) -> ServiceHealthHelper:
        return ServiceHealthHelper(http_client, base_url)

    return _create_helper


@pytest.fixture
async def platform_health_helpers(
    http_client: httpx.AsyncClient,
    service_urls: dict[str, str],
) -> dict[str, ServiceHealthHelper]:
    """
    Retorna dict com ServiceHealthHelper para todos os serviços.
    """
    return {
        service_name: ServiceHealthHelper(http_client, url)
        for service_name, url in service_urls.items()
    }


# ============================================================================
# Fixtures - Kafka Mock (para testes locais)
# ============================================================================


@pytest.fixture
def mock_kafka_producer():
    """
    Mock de Kafka producer para testes locais.

    Usado quando Kafka real não está disponível.
    """
    producer = AsyncMock()

    async def mock_produce(topic, value, key=None):
        # Simula produção bem-sucedida
        return True

    async def mock_flush():
        # Simula flush
        return True

    producer.produce = mock_produce
    producer.flush = mock_flush

    return producer


@pytest.fixture
def mock_kafka_consumer():
    """
    Mock de Kafka consumer para testes locais.

    Usado quando Kafka real não está disponível.
    """
    consumer = AsyncMock()

    async def mock_consume(topics, timeout_ms=1000):
        # Simula consumo vazio por padrão
        return []

    consumer.subscribe = AsyncMock()
    consumer.consume = mock_consume
    consumer.close = AsyncMock()

    return consumer


# ============================================================================
# Fixtures - Test Data
# ============================================================================


@pytest.fixture
def sample_intent() -> dict[str, any]:
    """
    Intent de exemplo para testes de fluxo Kafka.
    """
    return {
        "intent_id": f"intent-test-{uuid.uuid4().hex[:8]}",
        "correlation_id": f"corr-test-{uuid.uuid4().hex[:8]}",
        "text": "Criar endpoint para health check",
        "intent_type": "code_generation",
        "priority": 5,
        "timestamp": datetime.now(UTC).isoformat(),
        "session_id": f"session-test-{uuid.uuid4().hex[:8]}",
    }


@pytest.fixture
def sample_cognitive_plan() -> dict[str, any]:
    """
    Plano cognitivo de exemplo para testes de fluxo Kafka.
    """
    plan_id = f"plan-test-{uuid.uuid4().hex[:8]}"
    intent_id = f"intent-test-{uuid.uuid4().hex[:8]}"

    return {
        "plan_id": plan_id,
        "intent_id": intent_id,
        "correlation_id": f"corr-test-{uuid.uuid4().hex[:8]}",
        "description": "Test Plan",
        "created_at": datetime.now(UTC).isoformat(),
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
        "sla_deadline": (datetime.now(UTC) + timedelta(hours=4)).isoformat(),
    }
