# Platform Health & Kafka Standardization - Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Padronizar health checks e tópicos Kafka em todos os serviços do Neural-Hive-Mind através da biblioteca neural_hive_api.

**Architecture:** Criar biblioteca compartilhada com HealthRouter (FastAPI) e KafkaTopicsConfig (base class). Migrar 22 serviços para novo padrão de health (/health, /health/live, /health/ready) e 17 serviços para novo padrão de tópicos ({service}.{domain}.{event}).

**Tech Stack:** Python 3.12, FastAPI, AIOKafka, pytest

---

## Task 1: Create neural_hive_api Library Structure

**Files:**
- Create: `libraries/python/neural_hive_api/pyproject.toml`
- Create: `libraries/python/neural_hive_api/neural_hive_api/__init__.py`
- Create: `libraries/python/neural_hive_api/neural_hive_api/health/__init__.py`
- Create: `libraries/python/neural_hive_api/neural_hive_api/health/models.py`
- Create: `libraries/python/neural_hive_api/neural_hive_api/health/checks.py`

- [ ] **Step 1: Create pyproject.toml**

\`\`\`toml
[project]
name = "neural-hive-api"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115.0",
    "pydantic>=2.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "httpx>=0.27.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
\`\`\`

- [ ] **Step 2: Create root __init__.py**

\`\`\`python
"""Neural Hive API - Shared API components for NHM services."""

__version__ = "0.1.0"
\`\`\`

- [ ] **Step 3: Create health package __init__.py**

\`\`\`python
"""Health check components."""

from .models import HealthResponse, HealthStatus, CheckResult
from .checks import BaseHealthCheck

__all__ = ["HealthResponse", "HealthStatus", "CheckResult", "BaseHealthCheck"]
\`\`\`

- [ ] **Step 4: Create health/models.py**

\`\`\`python
"""Health check response models."""

from enum import Enum
from pydantic import BaseModel
from datetime import datetime


class HealthStatus(str, Enum):
    """Status de saúde do serviço."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class CheckResult(BaseModel):
    """Resultado de um check individual."""
    name: str
    status: HealthStatus
    message: str | None = None


class HealthResponse(BaseModel):
    """Response padrão do health check."""
    status: HealthStatus
    service: str
    timestamp: datetime
    checks: dict[str, HealthStatus]
\`\`\`

- [ ] **Step 5: Create health/checks.py**

\`\`\`python
"""Base health check classes."""

from abc import ABC, abstractmethod
from .models import HealthStatus, CheckResult


class BaseHealthCheck(ABC):
    """Base class para health checks."""

    def __init__(self, name: str, critical: bool = True):
        self.name = name
        self.critical = critical

    @abstractmethod
    async def check(self) -> CheckResult:
        """Executa o check e retorna resultado."""
        pass
\`\`\`

- [ ] **Step 6: Commit library structure**

\`\`\`bash
git add libraries/python/neural_hive_api/
git commit -m "feat: create neural_hive_api library structure"
\`\`\`

---

## Task 2: Implement HealthRouter

**Files:**
- Create: `libraries/python/neural_hive_api/neural_hive_api/health/router.py`

- [ ] **Step 1: Write failing test for HealthRouter**

\`\`\`python
# libraries/python/neural_hive_api/tests/test_health_router.py
import pytest
from fastapi import FastAPI
from neural_hive_api.health import HealthRouter, HealthStatus


@pytest.mark.asyncio
async def test_health_router_creates_endpoints():
    """Router deve criar /health, /health/live, /health/ready."""
    router = HealthRouter("test-service")
    app = FastAPI()
    router.add_route(app)
    
    routes = [r.path for r in app.routes]
    assert "/health" in routes
    assert "/health/live" in routes
    assert "/health/ready" in routes
\`\`\`

- [ ] **Step 2: Run test to verify it fails**

\`\`\`bash
cd libraries/python/neural_hive_api
pytest tests/test_health_router.py::test_health_router_creates_endpoints -v
\`\`\`
Expected: FAIL - "HealthRouter not defined"

- [ ] **Step 3: Implement HealthRouter**

\`\`\`python
# libraries/python/neural_hive_api/neural_hive_api/health/router.py
from datetime import datetime
from fastapi import FastAPI, Response
from .models import HealthResponse, HealthStatus, CheckResult
from .checks import BaseHealthCheck


class HealthRouter:
    """Router padronizado de health check."""

    def __init__(self, service_name: str):
        self.service_name = service_name
        self.checks: list[BaseHealthCheck] = []

    def register_check(self, check: BaseHealthCheck) -> None:
        """Registra um check customizado."""
        self.checks.append(check)

    def add_route(self, app: FastAPI) -> None:
        """Adiciona rotas de health à app FastAPI."""
        app.add_api_route("/health", self._health)
        app.add_api_route("/health/live", self._liveness)
        app.add_api_route("/health/ready", self._readiness)

    async def _execute_checks(self) -> dict[str, HealthStatus]:
        """Executa todos os checks e retorna resultados."""
        results = {}
        for check in self.checks:
            try:
                result = await check.check()
                results[result.name] = result.status
            except Exception:
                results[check.name] = HealthStatus.UNHEALTHY
        return results

    def _aggregate_status(self, checks: dict[str, HealthStatus]) -> HealthStatus:
        """Agrega status dos checks."""
        if not checks:
            return HealthStatus.HEALTHY
        
        values = list(checks.values())
        if HealthStatus.UNHEALTHY in values:
            return HealthStatus.UNHEALTHY
        if HealthStatus.DEGRADED in values:
            return HealthStatus.DEGRADED
        return HealthStatus.HEALTHY

    async def _health(self) -> HealthResponse:
        """Endpoint principal - status agregado."""
        checks = await self._execute_checks()
        status = self._aggregate_status(checks)
        return HealthResponse(
            status=status,
            service=self.service_name,
            timestamp=datetime.utcnow(),
            checks=checks
        )

    async def _liveness(self) -> HealthResponse:
        """Liveness probe - serviço está vivo?"""
        return HealthResponse(
            status=HealthStatus.HEALTHY,
            service=self.service_name,
            timestamp=datetime.utcnow(),
            checks={}
        )

    async def _readiness(self) -> HealthResponse:
        """Readiness probe - serviço pode receber tráfego?"""
        checks = await self._execute_checks()
        status = self._aggregate_status(checks)
        return HealthResponse(
            status=status,
            service=self.service_name,
            timestamp=datetime.utcnow(),
            checks=checks
        )
\`\`\`

- [ ] **Step 4: Run test to verify it passes**

\`\`\`bash
cd libraries/python/neural_hive_api
pytest tests/test_health_router.py -v
\`\`\`
Expected: PASS

- [ ] **Step 5: Write additional tests**

\`\`\`python
@pytest.mark.asyncio
async def test_health_returns_200_when_healthy():
    """Health deve retornar 200 quando saudável."""
    router = HealthRouter("test-service")
    app = FastAPI()
    router.add_route(app)
    
    client = TestClient(app)
    response = client.get("/health")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "test-service"


@pytest.mark.asyncio
async def test_health_degraded_when_non_critical_check_fails():
    """Health deve retornar degraded quando check não-crítico falha."""
    router = HealthRouter("test-service")
    
    class FailingCheck(BaseHealthCheck):
        def __init__(self):
            super().__init__("failing", critical=False)
        
        async def check(self):
            return CheckResult(name="failing", status=HealthStatus.UNHEALTHY, message="Failed")
    
    router.register_check(FailingCheck())
    app = FastAPI()
    router.add_route(app)
    
    client = TestClient(app)
    response = client.get("/health")
    
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
\`\`\`

- [ ] **Step 6: Run all tests and commit**

\`\`\`bash
cd libraries/python/neural_hive_api
pytest tests/ -v
git add .
git commit -m "feat: implement HealthRouter with tests"
\`\`\`

---

## Task 3: Implement Kafka Topics Config

**Files:**
- Create: `libraries/python/neural_hive_api/neural_hive_api/kafka/__init__.py`
- Create: `libraries/python/neural_hive_api/neural_hive_api/kafka/topics.py`
- Create: `libraries/python/neural_hive_api/tests/test_kafka_topics.py`

- [ ] **Step 1: Write failing test for KafkaTopicsConfig**

\`\`\`python
# libraries/python/neural_hive_api/tests/test_kafka_topics.py
import pytest
from neural_hive_api.kafka import KafkaTopicsConfig


class TestTopics(KafkaTopicsConfig):
    PREFIX = "test"
    EXECUTION = KafkaTopicsConfig.get_topic("execution", "results")


def test_topic_format_service_domain_event():
    """Tópico deve seguir formato service.domain.event"""
    topics = TestTopics()
    assert topics.EXECUTION == "test.execution.results"
\`\`\`

- [ ] **Step 2: Run test to verify it fails**

\`\`\`bash
cd libraries/python/neural_hive_api
pytest tests/test_kafka_topics.py::test_topic_format_service_domain_event -v
\`\`\`
Expected: FAIL

- [ ] **Step 3: Implement KafkaTopicsConfig**

\`\`\`python
# libraries/python/neural_hive_api/neural_hive_api/kafka/__init__.py
"""Kafka topics configuration components."""

from .topics import KafkaTopicsConfig

__all__ = ["KafkaTopicsConfig"]


# libraries/python/neural_hive_api/neural_hive_api/kafka/topics.py
from abc import ABC, abstractmethod


class KafkaTopicsConfig(ABC):
    """Base class para configuração de tópicos Kafka."""
    
    PREFIX: str = ""
    
    @classmethod
    def get_topic(cls, domain: str, event: str) -> str:
        """Retorna tópico no formato {PREFIX}.{domain}.{event}."""
        prefix = cls.PREFIX if cls.PREFIX else cls.__name__.lower().replace("topics", "")
        return f"{prefix}.{domain}.{event}"
    
    @abstractmethod
    def get_all_topics(self) -> dict[str, str]:
        """Retorna mapping nome_tópico → tópico."""
        pass
\`\`\`

- [ ] **Step 4: Run test to verify it passes**

\`\`\`bash
cd libraries/python/neural_hive_api
pytest tests/test_kafka_topics.py -v
\`\`\`
Expected: PASS

- [ ] **Step 5: Write additional tests and commit**

\`\`\`python
def test_empty_prefix_allowed():
    """PREFIX vazio deve ser permitido."""
    class NoPrefixTopics(KafkaTopicsConfig):
        PREFIX = ""
    
    topics = NoPrefixTopics()
    assert topics.get_topic("test", "event") == ".test.event"


def test_get_all_topics_raises_not_implemented():
    """get_all_topics deve ser implementado por subclasses."""
    topics = KafkaTopicsConfig()
    with pytest.raises(NotImplementedError):
        topics.get_all_topics()
\`\`\`

\`\`\`bash
cd libraries/python/neural_hive_api
pytest tests/ -v
git add .
git commit -m "feat: implement KafkaTopicsConfig with tests"
\`\`\`

---

## Task 4: Migrate analyst-agents Service (Pilot)

**Files:**
- Modify: `services/analyst-agents/requirements.txt`
- Modify: `services/analyst-agents/src/main.py`
- Modify: `services/analyst-agents/src/config/settings.py`
- Create: `services/analyst-agents/tests/integration/test_health.py`
- Create: `services/analyst-agents/tests/integration/test_kafka.py`

- [ ] **Step 1: Add neural_hive_api to requirements.txt**

\`\`\`bash
echo "neural-hive-api @ file:///home/jimy/NHM/Neural-Hive-Mind/libraries/python/neural_hive_api" >> \
  services/analyst-agents/requirements.txt
\`\`\`

- [ ] **Step 2: Remove old health endpoint, use new router**

\`\`\`python
# services/analyst-agents/src/main.py - BEFORE:
from .api.health import router as health_router
app.include_router(health_router)

# AFTER:
from neural_hive_api.health import HealthRouter
health_router = HealthRouter("analyst-agents")
health_router.add_route(app)
\`\`\`

- [ ] **Step 3: Update KafkaTopicsConfig in settings.py**

\`\`\`python
# services/analyst-agents/src/config/settings.py - BEFORE:
class Settings(BaseSettings):
    KAFKA_TOPICS_TELEMETRY: str = "telemetry.aggregated"
    KAFKA_TOPICS_CONSENSUS: str = "plans.consensus"
    # ...

# AFTER:
from neural_hive_api.kafka import KafkaTopicsConfig

class AnalystTopics(KafkaTopicsConfig):
    PREFIX = "analyst"
    
    TELEMETRY = get_topic("telemetry", "aggregated")
    CONSENSUS = get_topic("plans", "consensus")
    EXECUTION = get_topic("execution", "results")
    PHEROMONES = get_topic("pheromones", "signals")
    INSIGHTS = get_topic("insights", "analyzed")
    
    def get_all_topics(self) -> dict[str, str]:
        return {
            "telemetry": self.TELEMETRY,
            "consensus": self.CONSENSUS,
            "execution": self.EXECUTION,
            "pheromones": self.PHEROMONES,
            "insights": self.INSIGHTS,
        }

class Settings(BaseSettings):
    topics: AnalystTopics = AnalystTopics()
\`\`\`

- [ ] **Step 4: Update producer/consumer to use new topic names**

\`\`\`python
# Find and replace:
# OLD: settings.KAFKA_TOPICS_TELEMETRY
# NEW: settings.topics.TELEMETRY
\`\`\`

- [ ] **Step 5: Write integration test for health**

\`\`\`python
# services/analyst-agents/tests/integration/test_health.py
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_endpoint_returns_200():
    """GET /health deve retornar 200."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_health_live_returns_200():
    """GET /health/live deve retornar 200."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/health/live")
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_health_ready_returns_200():
    """GET /health/ready deve retornar 200."""
    async with AsyncClient(app=app, base_url="http=") as client:
        response = await client.get("/health/ready")
        assert response.status_code == 200
\`\`\`

- [ ] **Step 6: Write integration test for Kafka**

\`\`\`python
# services/analyst-agents/tests/integration/test_kafka.py
import pytest


@pytest.mark.asyncio
async def test_producer_sends_to_correct_topic():
    """Producer deve enviar para analyst.{domain}.{event}."""
    from analyst_agents.config import Settings
    
    settings = Settings()
    assert settings.topics.TELEMETRY == "analyst.telemetry.aggregated"
    assert settings.topics.CONSENSUS == "analyst.plans.consensus"
\`\`\`

- [ ] **Step 7: Run tests and commit**

\`\`\`bash
cd services/analyst-agents
pytest tests/integration/ -v
git add .
git commit -m "feat(migrate): use neural_hive_api for health and kafka"
\`\`\`

---

## Task 5: Migrate optimizer-agents Service (Pilot)

**Files:**
- Modify: `services/optimizer-agents/requirements.txt`
- Modify: `services/optimizer-agents/src/main.py`
- Modify: `services/optimizer-agents/src/config/settings.py`
- Create: `services/optimizer-agents/tests/integration/test_health.py`

- [ ] **Step 1: Add neural_hive_api dependency**

\`\`\`bash
echo "neural-hive-api @ file:///home/jimy/NHM/Neural-Hive-Mind/libraries/python/neural_hive_api" >> \
  services/optimizer-agents/requirements.txt
\`\`\`

- [ ] **Step 2: Replace old health router**

\`\`\`python
# services/optimizer-agents/src/main.py
from neural_hive_api.health import HealthRouter

# Remover:
# from .api.health import router as health_router

# Adicionar:
health_router = HealthRouter("optimizer-agents")
health_router.add_route(app)
\`\`\`

- [ ] **Step 3: Update KafkaTopicsConfig**

\`\`\`python
# services/optimizer-agents/src/config/settings.py
from neural_hive_api.kafka import KafkaTopicsConfig

class OptimizerTopics(KafkaTopicsConfig):
    PREFIX = "optimizer"
    
    TELEMETRY = get_topic("telemetry", "aggregated")
    RECOMMENDATIONS = get_topic("recommendations", "generated")
    FEEDBACK = get_topic("feedback", "received")
    
    def get_all_topics(self) -> dict[str, str]:
        return {
            "telemetry": self.TELEMETRY,
            "recommendations": self.RECOMMENDATIONS,
            "feedback": self.FEEDBACK,
        }
\`\`\`

- [ ] **Step 4: Write integration tests**

\`\`\`python
# services/optimizer-agents/tests/integration/test_health.py
@pytest.mark.asyncio
async def test_optimizer_health_endpoints():
    """Todos os endpoints health devem responder."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        r1 = await client.get("/health")
        r2 = await client.get("/health/live")
        r3 = await client.get("/health/ready")
        
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r3.status_code == 200
\`\`\`

- [ ] **Step 5: Run tests and commit**

\`\`\`bash
cd services/optimizer-agents
pytest tests/integration/ -v
git add .
git commit -m "feat(migrate): use neural_hive_api for health and kafka"
\`\`\`

---

## Task 6: Batch 1 Migration - Core Services

**Services:** consensus-engine, orchestrator-dynamic, gateway-intencoes

**Files per service:** requirements.txt, main.py, settings.py

- [ ] **Step 1: Migrate consensus-engine**

\`\`\`bash
# 1. Add dependency
echo "neural-hive-api @ file:///$PWD/../../libraries/python/neural_hive_api" >> \
  services/consensus-engine/requirements.txt

# 2. Update health in main.py - replace @app.get("/health") with HealthRouter
# 3. Update KafkaTopicsConfig in settings.py
# 4. Update producer/consumer topic references
# 5. Write integration tests
# 6. Run tests
\`\`\`

- [ ] **Step 2: Migrate orchestrator-dynamic**

\`\`\`bash
# Same pattern - remove /health/opa, /health/kafka-producer sub-endpoints
# Replace with single HealthRouter + registered checks
\`\`\`

- [ ] **Step 3: Migrate gateway-intencoes**

\`\`\`bash
# Same pattern
\`\`\`

- [ ] **Step 4: Test batch 1 together**

\`\`\`bash
# Test communication between migrated services
pytest tests/integration/test_batch1_communication.py -v
\`\`\`

- [ ] **Step 5: Commit batch 1**

\`\`\`bash
git add services/consensus-engine services/orchestrator-dynamic services/gateway-intencoes
git commit -m "feat(batch1): migrate core services to neural_hive_api"
\`\`\`

---

## Task 7: Batch 2 Migration - Specialist Services

**Services:** queen-agent, scout-agents, guard-agents, analyst-agents (done), self-healing-engine

- [ ] **Step 1: Migrate queen-agent**
- [ ] **Step 2: Migrate scout-agents**
- [ ] **Step 3: Migrate guard-agents**
- [ ] **Step 4: Migrate self-healing-engine**
- [ ] **Step 5: Test batch 2 together**
- [ ] **Step 6: Commit batch 2**

---

## Task 8: Batch 3 Migration - Supporting Services

**Services:** approval-service, execution-ticket-service, feature-store, explainability-api, mcp-tool-catalog, memory-layer-api, semantic-translation-engine

- [ ] **Step 1-7: Migrate each service (same pattern)**
- [ ] **Step 8: Test batch 3 together**
- [ ] **Step 9: Commit batch 3**

---

## Task 9: Batch 4 Migration - Infrastructure Services

**Services:** service-registry, sla-management-system, specialist-architecture, specialist-behavior, specialist-business, specialist-evolution, specialist-technical

- [ ] **Step 1-7: Migrate each service**
- [ ] **Step 8: Test batch 4 together**
- [ ] **Step 9: Commit batch 4**

---

## Task 10: E2E Tests

**Files:**
- Create: `tests/e2e/test_platform_health.py`
- Create: `tests/e2e/test_kafka_flow.py`

- [ ] **Step 1: Create conftest.py with fixtures**

\`\`\`python
# tests/e2e/conftest.py
import pytest
from docker import DockerClient


@pytest.fixture(scope="session")
async def kafka_container(docker_client: DockerClient):
    """Kafka container para E2E tests."""
    container = docker_client.run(
        "bitnami/kafka:latest",
        environment={
            "KAFKA_CFG_ZOOKEEPER_CONNECT": "zookeeper:2181",
        },
        ports={"9092": "9092"},
    )
    yield container
    container.stop()


@pytest.fixture(scope="session")
async def all_services():
    """Sobe todos os serviços para E2E."""
    # Implement docker-compose up
    pass
\`\`\`

- [ ] **Step 2: Write platform health test**

\`\`\`python
# tests/e2e/test_platform_health.py
@pytest.mark.e2e
async def test_all_services_respond_to_health(all_services):
    """Todos os serviços devem responder a /health."""
    services = [
        "analyst-agents:8000",
        "optimizer-agents:8001",
        "consensus-engine:8002",
        # ... todos os 22 serviços
    ]
    
    for service in services:
        host, port = service.split(":")
        async with httpx.AsyncClient() as client:
            response = await client.get(f"http://{host}:{port}/health")
            assert response.status_code == 200
\`\`\`

- [ ] **Step 3: Write Kafka flow test**

\`\`\`python
# tests/e2e/test_kafka_flow.py
@pytest.mark.e2e
async def test_intent_to_orchestration_flow(kafka_container, all_services):
    """Fluxo completo: intent → STE → consensus → orchestrator."""
    # 1. Send intent to gateway
    # 2. Verify topic names: analyst.telemetry.aggregated
    # 3. Verify consensus received: analyst.plans.consensus
    # 4. Verify orchestrator received: orchestrator.strategic.adjustments
\`\`\`

- [ ] **Step 4: Run E2E tests**

\`\`\`bash
pytest tests/e2e/ -v --tb=short
\`\`\`

- [ ] **Step 5: Commit E2E tests**

\`\`\`bash
git add tests/e2e/
git commit -m "test: add E2E tests for health and Kafka"
\`\`\`

---

## Task 11: Documentation

**Files:**
- Create: `docs/platform-standardization/HEALTH_CHECK_STANDARD.md`
- Create: `docs/platform-standardization/KAFKA_TOPICS_STANDARD.md`
- Create: `docs/platform-standardization/MIGRATION_GUIDE.md`
- Create: `libraries/python/neural_hive_api/README.md`

- [ ] **Step 1: Write HEALTH_CHECK_STANDARD.md**

- [ ] **Step 2: Write KAFKA_TOPICS_STANDARD.md**

- [ ] **Step 3: Write MIGRATION_GUIDE.md**

- [ ] **Step 4: Write neural_hive_api README.md**

- [ ] **Step 5: Commit documentation**

\`\`\`bash
git add docs/ libraries/python/neural_hive_api/README.md
git commit -m "docs: add platform standardization documentation"
\`\`\`

---

## Task 12: Cleanup and Merge

- [ ] **Step 1: Remove old health.py files from all services**

\`\`\`bash
find services/ -name "health.py" -path "*/api/*" -delete
\`\`\`

- [ ] **Step 2: Remove feature flags if any**

- [ ] **Step 3: Run full test suite**

\`\`\`bash
pytest tests/unit/ tests/integration/ tests/e2e/ -v
\`\`\`

- [ ] **Step 4: Update feature-map.md**

- [ ] **Step 5: Update MEMORY.md**

- [ ] **Step 6: Final commit**

\`\`\`bash
git add .
git commit -m "chore: cleanup legacy health code, finalize migration"
\`\`\`

---

## Task 13: Create PR and Handoff

- [ ] **Step 1: Push to remote**

\`\`\`bash
git push origin feat/platform-health-kafka-standardization
\`\`\`

- [ ] **Step 2: Create PR with description**

- [ ] **Step 3: Request review**

---

**Total Estimated Time:** 21 hours (~3 days)

**Branch:** `feat/platform-health-kafka-standardization`

**Success Criteria:**
- All 22 services with standardized health endpoints
- All 17 services with standardized Kafka topic names
- E2E tests passing
- Zero regressions in existing functionality
