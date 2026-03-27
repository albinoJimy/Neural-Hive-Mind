# Architect Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Criar serviço especializado em arquitetura de software que planeja designs de alto nível e valida código contra princípios arquiteturais.

**Architecture:** Serviço FastAPI com 3 componentes core: Design Planner (planejamento via LLM), Validate Engine (análise via Scout + OPA), Evolution Tracker (histórico e drift detection). Consome CognitivePlans do STE via Kafka, integra com Scout Agents via HTTP, persiste no MongoDB.

**Tech Stack:** FastAPI, Python 3.12+, MongoDB, Kafka, OPA, tree-sitter (via Scout), OpenAI/Anthropic (opcional), OpenTelemetry

---

## File Structure

```
services/architect-agent/
├── src/
│   ├── main.py                      # Entry point FastAPI
│   ├── config/
│   │   └── settings.py              # Configurações Pydantic
│   ├── models/
│   │   ├── __init__.py
│   │   ├── architecture.py          # ArchitecturePlan, Component, Pattern
│   │   ├── validation.py            # ValidationReport, Violation
│   │   └── evolution.py             # EvolutionHistory
│   ├── planners/
│   │   ├── __init__.py
│   │   ├── base.py                  # BasePlanner interface
│   │   ├── design_planner.py        # DesignPlanner principal
│   │   ├── llm_client.py            # Cliente OpenAI/Anthropic
│   │   └── templates.py             # Prompts para LLM
│   ├── validators/
│   │   ├── __init__.py
│   │   ├── base.py                  # BaseValidator interface
│   │   ├── validate_engine.py       # ValidateEngine principal
│   │   ├── rules.py                 # Regras arquiteturais (SOLID, etc)
│   │   ├── opa_client.py            # Cliente OPA
│   │   └── scout_client.py          # Cliente Scout Agents
│   ├── evolution/
│   │   ├── __init__.py
│   │   ├── tracker.py               # EvolutionTracker
│   │   └── comparator.py            # Comparador planned vs actual
│   ├── consumers/
│   │   ├── __init__.py
│   │   └── cognitive_plan_consumer.py  # Kafka consumer
│   ├── api/
│   │   ├── __init__.py
│   │   └── router.py                # FastAPI routes
│   ├── repositories/
│   │   ├── __init__.py
│   │   ├── architecture_repo.py     # MongoDB repo
│   │   └── validation_repo.py       # MongoDB repo
│   └── observability/
│       ├── __init__.py
│       └── metrics.py               # Prometheus metrics
├── tests/
│   ├── unit/
│   │   ├── test_design_planner.py
│   │   ├── test_validate_engine.py
│   │   └── test_evolution_tracker.py
│   ├── integration/
│   │   ├── test_scout_client.py
│   │   ├── test_opa_client.py
│   │   └── test_cognitive_plan_consumer.py
│   ├── e2e/
│   │   └── test_plan_to_validate.py
│   └── conftest.py
├── helm/architect-agent/
│   ├── Chart.yaml
│   ├── values.yaml
│   └── templates/
├── Dockerfile
├── requirements.txt
└── README.md
```

---

## Task 1: Estrutura Base do Serviço

**Files:**
- Create: `services/architect-agent/src/main.py`
- Create: `services/architect-agent/src/config/settings.py`
- Create: `services/architect-agent/requirements.txt`
- Create: `services/architect-agent/Dockerfile`
- Create: `services/architect-agent/tests/conftest.py`

### Task 1.1: Criar configurações Pydantic

```bash
mkdir -p services/architect-agent/src/config
```

**Step 1: Criar settings.py**

```python
# services/architect-agent/src/config/settings.py
from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache

class Settings(BaseSettings):
    # Service
    service_name: str = "architect-agent"
    environment: str = Field(default="development", pattern="^(development|staging|production)$")
    log_level: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR)$")
    http_port: int = 8008

    # Kafka
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_cognitive_plans_topic: str = "cognitive.plans.created"
    kafka_consumer_group: str = "architect-agent"
    kafka_auto_offset_reset: str = "earliest"

    # MongoDB
    mongodb_url: str = "mongodb://localhost:27017"
    mongodb_database: str = "architect_agent"
    mongodb_collection_architecture: str = "architecture_plans"
    mongodb_collection_validation: str = "validation_reports"
    mongodb_collection_evolution: str = "evolution_history"

    # Scout Agents
    scout_agents_url: str = "http://localhost:8020"
    scout_timeout_seconds: int = 30

    # OPA
    opa_url: str = "http://localhost:8181"
    opa_policy_path: str = "/v1/data/architect/rules"
    opa_timeout_seconds: int = 10

    # LLM (opcional)
    llm_provider: str = Field(default="", pattern="^(openai|anthropic|)$")
    llm_api_key: str = ""
    llm_model: str = "gpt-4"
    llm_timeout_seconds: int = 60
    llm_max_tokens: int = 2000

    # Observability
    otel_endpoint: str = "http://otel-collector:4317"
    prometheus_port: int = 9098

    class Config:
        env_file = ".env"
        case_sensitive = False

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

**Step 2: Commit**

```bash
git add services/architect-agent/src/config/settings.py
git commit -m "feat(architect-agent): adicionar configurações Pydantic"
```

### Task 1.2: Criar entry point FastAPI

**Step 1: Criar main.py**

```python
# services/architect-agent/src/main.py
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import structlog

from src.config.settings import get_settings
from src.observability.metrics import init_metrics
from src.api.router import api_router

settings = get_settings()
logger = structlog.get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia ciclo de vida da aplicação."""
    logger.info("starting_architect_agent", service=settings.service_name)
    # Iniciar Kafka consumer (background)
    # Iniciar métricas
    yield
    logger.info("shutting_down_architect_agent")

app = FastAPI(
    title="Architect Agent",
    description="Sistema de arquitetura de software - planejamento e validação",
    version="1.0.0",
    lifespan=lifespan
)

# Incluir rotas
app.include_router(api_router, prefix="/api/v1")

# Health checks
@app.get("/health/live")
async def liveness():
    return {"status": "alive"}

@app.get("/health/ready")
async def readiness():
    return {"status": "ready"}

# Métricas
init_metrics(app)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.http_port,
        log_level=settings.log_level.lower()
    )
```

**Step 2: Commit**

```bash
git add services/architect-agent/src/main.py
git commit -m "feat(architect-agent): adicionar entry point FastAPI"
```

### Task 1.3: Criar requirements.txt

**Step 1: Criar requirements.txt**

```txt
# services/architect-agent/requirements.txt
fastapi==0.109.0
uvicorn[standard]==0.27.0
pydantic==2.5.3
pydantic-settings==2.1.0
structlog==24.1.0

# Kafka
confluent-kafka==2.3.0

# MongoDB
motor==3.3.2
pymongo==4.6.1

# HTTP
httpx==0.26.0

# LLM (opcional)
openai==1.10.0; python_version >= "3.10"
anthropic==0.18.0; python_version >= "3.10"

# Observabilidade
prometheus-client==0.19.0
opentelemetry-api==1.22.0
opentelemetry-sdk==1.22.0
opentelemetry-instrumentation-fastapi==0.43b0

# Testing
pytest==7.4.4
pytest-asyncio==0.23.3
pytest-cov==4.1.0
pytest-mock==3.12.0
```

**Step 2: Commit**

```bash
git add services/architect-agent/requirements.txt
git commit -m "feat(architect-agent): adicionar requirements.txt"
```

### Task 1.4: Criar Dockerfile

**Step 1: Criar Dockerfile**

```dockerfile
# services/architect-agent/Dockerfile
FROM python:3.12-slim as builder

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /root/.local /root/.local
COPY src/ ./src/

ENV PATH=/root/.local/bin:$PATH

EXPOSE 8008 9098

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8008/health/live || exit 1

CMD ["python", "-m", "src.main"]
```

**Step 2: Commit**

```bash
git add services/architect-agent/Dockerfile
git commit -m "feat(architect-agent): adicionar Dockerfile"
```

### Task 1.5: Criar conftest.py para testes

**Step 1: Criar estrutura de testes e conftest.py**

```bash
mkdir -p services/architect-agent/tests/{unit,integration,e2e}
```

```python
# services/architect-agent/tests/conftest.py
import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from unittest.mock import AsyncMock
from src.config.settings import get_settings

@pytest.fixture
def settings():
    return get_settings()

@pytest.fixture
async def mongo_client(settings):
    """Cliente MongoDB para testes."""
    client = AsyncIOMotorClient(settings.mongodb_url)
    yield client
    await client.drop_database(settings.mongodb_database)
    client.close()

@pytest.fixture
def mock_scout_client():
    """Mock do Scout Agent client."""
    from unittest.mock import MagicMock
    mock = MagicMock()
    mock.get_patterns.return_value = {"patterns": []}
    mock.get_insights.return_value = {"insights": []}
    return mock

@pytest.fixture
def mock_llm_client():
    """Mock do LLM client."""
    from unittest.mock import MagicMock
    mock = MagicMock()
    mock.generate.return_value = """
    ```json
    {
      "architecture_type": "microservices",
      "components": [{"name": "api", "stack": "python/fastapi"}],
      "patterns": ["repository"],
      "rationale": "Test rationale"
    }
    ```
    """
    return mock
```

**Step 2: Commit**

```bash
git add services/architect-agent/tests/conftest.py
git commit -m "feat(architect-agent): adicionar conftest.py para testes"
```

---

## Task 2: Modelos de Dados

**Files:**
- Create: `services/architect-agent/src/models/__init__.py`
- Create: `services/architect-agent/src/models/architecture.py`
- Create: `services/architect-agent/src/models/validation.py`
- Create: `services/architect-agent/src/models/evolution.py`

### Task 2.1: Criar modelos de arquitetura

**Step 1: Criar architecture.py**

```python
# services/architect-agent/src/models/architecture.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Literal
from enum import Enum

class ArchitectureType(str, Enum):
    MICROSERVICES = "microservices"
    MONOLITH = "monolith"
    SERVERLESS = "serverless"
    HYBRID = "hybrid"

class Component(BaseModel):
    name: str = Field(..., description="Nome do componente")
    stack: str = Field(..., description="Stack tecnológica (ex: python/fastapi)")
    replicas: int = Field(default=1, ge=1, description="Número de réplicas")
    ha: bool = Field(default=False, description="High availability")
    resources: dict = Field(default_factory=dict, description="CPU/memory limits")

class Pattern(str, Enum):
    REPOSITORY = "repository"
    CQRS = "cqrs"
    EVENT_SOURCING = "event_sourcing"
    SAGA = "saga"
    CIRCUIT_BREAKER = "circuit_breaker"
    API_GATEWAY = "api_gateway"
    MESSAGE_BROKER = "message_broker"

class ArchitecturePlan(BaseModel):
    plan_id: str = Field(..., description="ID único do plano")
    cognitive_plan_id: str | None = Field(None, description="ID do CognitivePlan de origem")
    architecture_type: ArchitectureType
    components: List[Component]
    patterns: List[Pattern]
    rationale: str = Field(..., description="Justificativa das decisões")
    requirements: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime | None = None

    class Config:
        json_schema_extra = {
            "example": {
                "plan_id": "arch-123",
                "cognitive_plan_id": "cp-456",
                "architecture_type": "microservices",
                "components": [
                    {"name": "user-api", "stack": "python/fastapi", "replicas": 3}
                ],
                "patterns": ["repository", "cqrs"],
                "rationale": "Microservices para escala independente"
            }
        }
```

**Step 2: Commit**

```bash
git add services/architect-agent/src/models/architecture.py
git commit -m "feat(architect-agent): adicionar modelos de arquitetura"
```

### Task 2.2: Criar modelos de validação

**Step 1: Criar validation.py**

```python
# services/architect-agent/src/models/validation.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Literal
from enum import Enum

class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class ViolationType(str, Enum):
    SRP = "srp"  # Single Responsibility
    OCP = "ocp"  # Open/Closed
    LSP = "lsp"  # Liskov Substitution
    ISP = "isp"  # Interface Segregation
    DIP = "dip"  # Dependency Inversion
    COUPLING = "coupling"
    COHESION = "cohesion"
    COMPLEXITY = "complexity"
    DUPLICATION = "duplication"

class Trend(str, Enum):
    UP = "up"      # Saúde melhorando
    DOWN = "down"  # Saúde piorando
    STABLE = "stable"

class Violation(BaseModel):
    type: ViolationType
    severity: Severity
    location: str = Field(..., description="Localização no código (ex: file.py:linha)")
    description: str = Field(..., description="Descrição da violação")
    suggestion: str | None = None

class Suggestion(BaseModel):
    priority: int = Field(..., ge=1, le=5, description="Prioridade 1-5 (1 mais alta)")
    description: str
    effort: Literal["XS", "S", "M", "L", "XL"] = Field(default="M")
    affected_files: List[str] = Field(default_factory=list)

class ValidationReport(BaseModel):
    report_id: str
    repo_url: str
    branch: str = "main"
    commit_sha: str | None = None
    health_score: int = Field(..., ge=0, le=100, description="Score de saúde 0-100")
    trend: Trend = Trend.STABLE
    violations: List[Violation] = Field(default_factory=list)
    suggestions: List[Suggestion] = Field(default_factory=list)
    metrics: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_schema_extra = {
            "example": {
                "report_id": "val-789",
                "repo_url": "github.com/org/repo",
                "health_score": 72,
                "violations": [
                    {
                        "type": "srp",
                        "severity": "high",
                        "location": "UserService.py:145",
                        "description": "Classe com 15 responsabilidades"
                    }
                ],
                "suggestions": [
                    {"priority": 1, "description": "Separar responsabilidades", "effort": "L"}
                ]
            }
        }
```

**Step 2: Commit**

```bash
git add services/architect-agent/src/models/validation.py
git commit -m "feat(architect-agent): adicionar modelos de validação"
```

### Task 2.3: Criar modelos de evolução

**Step 1: Criar evolution.py**

```python
# services/architect-agent/src/models/evolution.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional
from enum import Enum

class DriftType(str, Enum):
    ARCHITECTURE = "architecture"      # Tipo de arquitetura divergiu
    COMPONENTS = "components"          # Componentes divergiram
    PATTERNS = "patterns"              # Padrões não aplicados
    STACK = "stack"                    # Stack tecnológica divergiu

class DriftDetection(BaseModel):
    drift_type: DriftType
    description: str
    expected: str
    actual: str
    severity: str = Field(default="medium")

class EvolutionHistory(BaseModel):
    history_id: str
    plan_id: str
    version: int = Field(..., ge=1)
    changes: List[str] = Field(default_factory=list)
    drifts: List[DriftDetection] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str = "architect-agent"  # Pode ser "user" se manual

class ArchitectureDiff(BaseModel):
    plan_id_old: str
    plan_id_new: str
    additions: List[str] = Field(default_factory=list)
    removals: List[str] = Field(default_factory=list)
    modifications: List[str] = Field(default_factory=list)
    requires_migration: bool = False
```

**Step 4: Commit**

```bash
git add services/architect-agent/src/models/evolution.py
git add services/architect-agent/src/models/__init__.py
git commit -m "feat(architect-agent): adicionar modelos de evolução"
```

---

## Task 3: Design Planner

**Files:**
- Create: `services/architect-agent/src/planners/__init__.py`
- Create: `services/architect-agent/src/planners/base.py`
- Create: `services/architect-agent/src/planners/templates.py`
- Create: `services/architect-agent/src/planners/llm_client.py`
- Create: `services/architect-agent/src/planners/design_planner.py`
- Test: `services/architect-agent/tests/unit/test_design_planner.py`

### Task 3.1: Criar base planner

**Step 1: Criar base.py**

```python
# services/architect-agent/src/planners/base.py
from abc import ABC, abstractmethod
from src.models.architecture import ArchitecturePlan
from src.models.validation import ValidationReport

class BasePlanner(ABC):
    """Interface base para planners de arquitetura."""

    @abstractmethod
    async def plan(self, requirements: dict, context: dict | None = None) -> ArchitecturePlan:
        """Cria um plano arquitetural baseado nos requisitos."""
        pass

    @abstractmethod
    async def refine(self, plan_id: str, feedback: dict) -> ArchitecturePlan:
        """Refina um plano existente com feedback."""
        pass
```

**Step 2: Commit**

```bash
git add services/architect-agent/src/planners/base.py
git commit -m "feat(architect-agent): adicionar BasePlanner interface"
```

### Task 3.2: Criar templates para LLM

**Step 1: Criar templates.py**

```python
# services/architect-agent/src/planners/templates.py
from typing import Dict, Any

SYSTEM_PROMPT = """You are an expert software architect specializing in distributed systems, microservices, and cloud-native applications.

Your task is to analyze requirements and propose an appropriate software architecture. Consider:
- Scalability requirements
- Consistency requirements
- Latency requirements
- Team size and expertise
- Budget constraints
- Time-to-market constraints

Respond ONLY with valid JSON in the following format:
{
  "architecture_type": "microservices|monolith|serverless|hybrid",
  "components": [
    {"name": "component-name", "stack": "tech-stack", "replicas": 1, "ha": false}
  ],
  "patterns": ["repository", "cqrs", "event_sourcing", "saga", "circuit_breaker"],
  "rationale": "Clear explanation of architectural decisions"
}
"""

def get_user_prompt(requirements: Dict[str, Any]) -> str:
    """Gera prompt para o usuário baseado nos requisitos."""
    intent = requirements.get("intent", "unknown")
    scale = requirements.get("scale", "medium")
    consistency = requirements.get("consistency", "eventual")
    latency_p99_ms = requirements.get("latency_p99_ms", 500)
    team_size = requirements.get("team_size", 5)
    budget = requirements.get("budget", "medium")

    return f"""Analyze the following requirements and propose a software architecture:

**Intent:** {intent}
**Scale:** {scale} (expected requests per second)
**Consistency:** {consistency} (strong/eventual)
**Latency P99:** {latency_p99_ms}ms
**Team Size:** {team_size} developers
**Budget:** {budget}

Provide:
1. Architecture type (microservices/monolith/serverless/hybrid) with rationale
2. Components with tech stack and deployment details
3. Design patterns to apply (choose from: repository, cqrs, event_sourcing, saga, circuit_breaker, api_gateway, message_broker)
4. Clear rationale for each decision

Respond ONLY with valid JSON."""
```

**Step 2: Commit**

```bash
git add services/architect-agent/src/planners/templates.py
git commit -m "feat(architect-agent): adicionar templates para LLM"
```

### Task 3.3: Criar LLM client

**Step 1: Criar llm_client.py**

```python
# services/architect-agent/src/planners/llm_client.py
import json
from typing import Literal
import httpx
from src.config.settings import get_settings

settings = get_settings()

class LLMClient:
    """Cliente unificado para OpenAI e Anthropic."""

    def __init__(self):
        self.provider = settings.llm_provider
        self.api_key = settings.llm_api_key
        self.model = settings.llm_model
        self.timeout = settings.llm_timeout_seconds
        self.max_tokens = settings.llm_max_tokens

    async def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        """Gera resposta do LLM."""
        if not self.provider or not self.api_key:
            # Fallback: retornar resposta padrão
            return self._get_default_response(prompt)

        if self.provider == "openai":
            return await self._generate_openai(prompt, system_prompt)
        elif self.provider == "anthropic":
            return await self._generate_anthropic(prompt, system_prompt)
        else:
            return self._get_default_response(prompt)

    async def _generate_openai(self, prompt: str, system_prompt: str | None = None) -> str:
        """Gera resposta usando OpenAI."""
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=self.api_key)

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            response = await client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                timeout=self.timeout
            )
            return response.choices[0].message.content
        except Exception as e:
            # Fallback em erro
            return self._get_default_response(prompt)

    async def _generate_anthropic(self, prompt: str, system_prompt: str | None = None) -> str:
        """Gera resposta usando Anthropic."""
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=self.api_key)

        messages = [{"role": "user", "content": prompt}]

        try:
            response = await client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system_prompt or "",
                messages=messages
            )
            return response.content[0].text
        except Exception as e:
            return self._get_default_response(prompt)

    def _get_default_response(self, prompt: str) -> str:
        """Resposta padrão quando LLM não disponível."""
        # Heurísticas simples baseadas em palavras-chave
        prompt_lower = prompt.lower()

        if "microservice" in prompt_lower or "scale" in prompt_lower:
            return """{
  "architecture_type": "microservices",
  "components": [{"name": "api", "stack": "python/fastapi", "replicas": 3}],
  "patterns": ["repository", "api_gateway"],
  "rationale": "Microservices for independent scaling"
}"""
        else:
            return """{
  "architecture_type": "monolith",
  "components": [{"name": "app", "stack": "python/fastapi", "replicas": 1}],
  "patterns": ["repository"],
  "rationale": "Monolith for simplicity and faster development"
}"""
```

**Step 2: Commit**

```bash
git add services/architect-agent/src/planners/llm_client.py
git commit -m "feat(architect-agent): adicionar LLM client com fallback"
```

### Task 3.4: Criar Design Planner

**Step 1: Criar design_planner.py**

```python
# services/architect-agent/src/planners/design_planner.py
import uuid
from datetime import datetime
from typing import Dict, Any
from .base import BasePlanner
from .llm_client import LLMClient
from .templates import SYSTEM_PROMPT, get_user_prompt
from src.models.architecture import ArchitecturePlan, ArchitectureType, Component, Pattern

class DesignPlanner(BasePlanner):
    """Planejador de arquitetura usando LLM."""

    def __init__(self):
        self.llm_client = LLMClient()

    async def plan(self, requirements: Dict[str, Any], context: Dict[str, Any] | None = None) -> ArchitecturePlan:
        """Cria plano arquitetural."""
        # Gerar prompt
        user_prompt = get_user_prompt(requirements)

        # Chamar LLM
        response = await self.llm_client.generate(user_prompt, SYSTEM_PROMPT)

        # Parsear resposta JSON
        plan_data = self._parse_llm_response(response)

        # Criar ArchitecturePlan
        return ArchitecturePlan(
            plan_id=f"arch-{uuid.uuid4().hex[:8]}",
            cognitive_plan_id=requirements.get("cognitive_plan_id"),
            **plan_data
        )

    async def refine(self, plan_id: str, feedback: Dict[str, Any]) -> ArchitecturePlan:
        """Refina plano existente."""
        # Implementar refinamento baseado em feedback
        # Por simplicidade, retorna plano modificado
        requirements = {
            "intent": feedback.get("new_intent", ""),
            "feedback": feedback.get("feedback", "")
        }
        return await self.plan(requirements)

    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        """Parseia resposta JSON do LLM."""
        import json
        import re

        # Extrair JSON de markdown code blocks
        json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
        if json_match:
            response = json_match.group(1)
        else:
            # Tentar extrair JSON sem markdown
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                response = json_match.group(0)

        try:
            data = json.loads(response)
            # Normalizar componentes
            components = []
            for comp in data.get("components", []):
                if isinstance(comp, dict):
                    components.append(Component(**comp))
                elif isinstance(comp, str):
                    components.append(Component(name=comp, stack="python/fastapi"))

            # Normalizar padrões
            patterns = []
            for p in data.get("patterns", []):
                if isinstance(p, str):
                    try:
                        patterns.append(Pattern(p))
                    except ValueError:
                        pass  # Padrão inválido, ignorar
                elif isinstance(p, dict):
                    try:
                        patterns.append(Pattern(p["name"]))
                    except (KeyError, ValueError):
                        pass

            return {
                "architecture_type": ArchitectureType(data.get("architecture_type", "monolith")),
                "components": components,
                "patterns": patterns,
                "rationale": data.get("rationale", "Auto-generated architecture"),
                "requirements": data.get("requirements", {})
            }
        except (json.JSONDecodeError, KeyError) as e:
            # Fallback para resposta padrão
            return {
                "architecture_type": ArchitectureType.MONOLITH,
                "components": [Component(name="app", stack="python/fastapi")],
                "patterns": [Pattern.REPOSITORY],
                "rationale": f"Error parsing LLM response: {str(e)}"
            }
```

**Step 2: Commit**

```bash
git add services/architect-agent/src/planners/design_planner.py services/architect-agent/src/planners/__init__.py
git commit -m "feat(architect-agent): adicionar DesignPlanner com LLM integration"
```

### Task 3.5: Testar Design Planner

**Step 1: Criar teste unitário**

```python
# services/architect-agent/tests/unit/test_design_planner.py
import pytest
from src.planners.design_planner import DesignPlanner
from src.models.architecture import ArchitectureType

@pytest.mark.asyncio
async def test_design_planner_generates_plan(mock_llm_client):
    """Testa que DesignPlanner gera ArchitecturePlan."""
    planner = DesignPlanner()

    requirements = {
        "intent": "create user management microservice",
        "scale": "high",
        "consistency": "strong",
        "latency_p99_ms": 200
    }

    plan = await planner.plan(requirements)

    assert plan.plan_id.startswith("arch-")
    assert plan.architecture_type in ArchitectureType
    assert len(plan.components) > 0
    assert len(plan.patterns) > 0
    assert plan.rationale != ""

@pytest.mark.asyncio
async def test_design_planner_refines_plan():
    """Testa que DesignPlanner refina plano existente."""
    planner = DesignPlanner()

    feedback = {
        "new_intent": "convert to serverless",
        "feedback": "Need better cold start performance"
    }

    refined = await planner.refine("arch-123", feedback)

    assert refined.plan_id.startswith("arch-")
```

**Step 2: Executar teste**

```bash
cd services/architect-agent
pytest tests/unit/test_design_planner.py -v
```

Expected: Alguns testes podem falhar inicialmente (depende do mock), ajustar conforme necessário.

**Step 3: Commit**

```bash
git add services/architect-agent/tests/unit/test_design_planner.py
git commit -m "test(architect-agent): adicionar testes do DesignPlanner"
```

---

## Task 4: Validate Engine

**Files:**
- Create: `services/architect-agent/src/validators/__init__.py`
- Create: `services/architect-agent/src/validators/base.py`
- Create: `services/architect-agent/src/validators/rules.py`
- Create: `services/architect-agent/src/validators/scout_client.py`
- Create: `services/architect-agent/src/validators/opa_client.py`
- Create: `services/architect-agent/src/validators/validate_engine.py`
- Test: `services/architect-agent/tests/unit/test_validate_engine.py`

### Task 4.1: Criar base validator

**Step 1: Criar base.py**

```python
# services/architect-agent/src/validators/base.py
from abc import ABC, abstractmethod
from src.models.validation import ValidationReport

class BaseValidator(ABC):
    """Interface base para validadores de arquitetura."""

    @abstractmethod
    async def validate(self, repo_url: str, branch: str = "main", rules: dict | None = None) -> ValidationReport:
        """Valida código contra regras arquiteturais."""
        pass

    @abstractmethod
    async def get_health_score(self, repo_url: str) -> int:
        """Retorna score de saúde arquitetural (0-100)."""
        pass
```

**Step 2: Commit**

```bash
git add services/architect-agent/src/validators/base.py
git commit -m "feat(architect-agent): adicionar BaseValidator interface"
```

### Task 4.2: Criar Scout client

**Step 1: Criar scout_client.py**

```python
# services/architect-agent/src/validators/scout_client.py
import httpx
from src.config.settings import get_settings

settings = get_settings()

class ScoutClient:
    """Cliente para Scout Agents API."""

    def __init__(self):
        self.base_url = settings.scout_agents_url
        self.timeout = settings.scout_timeout_seconds

    async def get_patterns(self, repo_url: str, branch: str = "main") -> dict:
        """Busca padrões detectados pelo Scout."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(
                    f"{self.base_url}/api/v1/patterns",
                    params={"repo_url": repo_url, "branch": branch}
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as e:
                # Fallback: retornar vazio
                return {"patterns": []}

    async def get_insights(self, repo_url: str, branch: str = "main") -> dict:
        """Busca insights do Scout (complexidade, dependências)."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(
                    f"{self.base_url}/api/v1/exploration-summary",
                    params={"directory": repo_url}
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError:
                return {"insights": []}

    async def detect_signals(self, repo_url: str) -> dict:
        """Detecta sinais de mudança no código."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/api/v1/signal-detect",
                    json={"repo_url": repo_url}
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError:
                return {"signals": []}
```

**Step 2: Commit**

```bash
git add services/architect-agent/src/validators/scout_client.py
git commit -m "feat(architect-agent): adicionar ScoutClient com fallback"
```

### Task 4.3: Criar OPA client

**Step 1: Criar opa_client.py**

```python
# services/architect-agent/src/validators/opa_client.py
import httpx
from typing import Any, Dict
from src.config.settings import get_settings

settings = get_settings()

class OPAClient:
    """Cliente para OPA (Open Policy Agent)."""

    def __init__(self):
        self.base_url = settings.opa_url
        self.policy_path = settings.opa_policy_path
        self.timeout = settings.opa_timeout_seconds

    async def evaluate(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Avalia input contra políticas OPA."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.base_url}{self.policy_path}",
                    json={"input": input_data}
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError:
                # Fallback: retornar vazio (sem violações)
                return {"result": []}

    async def check_architecture_rules(self, code_data: Dict[str, Any]) -> list:
        """Verifica regras arquiteturais no código."""
        result = await self.evaluate({"code": code_data})
        return result.get("result", [])
```

**Step 2: Commit**

```bash
git add services/architect-agent/src/validators/opa_client.py
git commit -m "feat(architect-agent): adicionar OPAClient com fallback"
```

### Task 4.4: Criar regras de validação

**Step 1: Criar rules.py**

```python
# services/architect-agent/src/validators/rules.py
from typing import List, Dict, Any
from src.models.validation import Violation, ViolationType, Severity

class ArchitecturalRules:
    """Regras de validação arquitetural."""

    @staticmethod
    def check_srp(class_info: Dict[str, Any]) -> List[Violation]:
        """Verifica Single Responsibility Principle."""
        violations = []

        # Se a classe tem muitos métodos públicos (>10), possível violação
        if class_info.get("public_methods", 0) > 10:
            violations.append(Violation(
                type=ViolationType.SRP,
                severity=Severity.HIGH,
                location=f"{class_info['file']}:{class_info.get('line', 0)}",
                description=f"Classe {class_info['name']} tem {class_info['public_methods']} métodos públicos (possível SRP violation)",
                suggestion="Considerar dividir a classe em responsabilidades menores"
            ))

        # Se a classe tem muitas dependências (>5)
        if class_info.get("dependencies", 0) > 5:
            violations.append(Violation(
                type=ViolationType.COUPLING,
                severity=Severity.MEDIUM,
                location=f"{class_info['file']}:{class_info.get('line', 0)}",
                description=f"Classe {class_info['name']} depende de {class_info['dependencies']} classes"
            ))

        return violations

    @staticmethod
    def check_complexity(function_info: Dict[str, Any]) -> List[Violation]:
        """Verifica complexidade ciclomática."""
        violations = []

        complexity = function_info.get("cyclomatic_complexity", 0)
        if complexity > 20:
            violations.append(Violation(
                type=ViolationType.COMPLEXITY,
                severity=Severity.HIGH if complexity > 30 else Severity.MEDIUM,
                location=f"{function_info['file']}:{function_info.get('line', 0)}",
                description=f"Função {function_info['name']} tem complexidade {complexity}",
                suggestion="Refatorar em funções menores"
            ))

        return violations

    @staticmethod
    def check_duplication(patterns: List[Dict[str, Any]]) -> List[Violation]:
        """Verifica duplicação de código."""
        violations = []

        for pattern in patterns:
            if pattern.get("type") == "duplicate_code":
                violations.append(Violation(
                    type=ViolationType.DUPLICATION,
                    severity=Severity.MEDIUM,
                    location=f"{pattern['file1']} e {pattern['file2']}",
                    description=f"Código duplicado detectado ({pattern['lines']} linhas)"
                ))

        return violations

    @staticmethod
    def calculate_health_score(violations: List[Violation]) -> int:
        """Calcula score de saúde baseado nas violações."""
        # Score base 100
        score = 100

        for v in violations:
            if v.severity == Severity.CRITICAL:
                score -= 20
            elif v.severity == Severity.HIGH:
                score -= 10
            elif v.severity == Severity.MEDIUM:
                score -= 5
            elif v.severity == Severity.LOW:
                score -= 2

        return max(0, score)
```

**Step 2: Commit**

```bash
git add services/architect-agent/src/validators/rules.py
git commit -m "feat(architect-agent): adicionar regras arquiteturais (SOLID, complexidade)"
```

### Task 4.5: Criar Validate Engine

**Step 1: Criar validate_engine.py**

```python
# services/architect-agent/src/validators/validate_engine.py
import uuid
from typing import Dict, Any
from .base import BaseValidator
from .scout_client import ScoutClient
from .opa_client import OPAClient
from .rules import ArchitecturalRules
from src.models.validation import ValidationReport, Trend, Suggestion

class ValidateEngine(BaseValidator):
    """Motor de validação arquitetural."""

    def __init__(self):
        self.scout_client = ScoutClient()
        self.opa_client = OPAClient()
        self.rules = ArchitecturalRules()

    async def validate(self, repo_url: str, branch: str = "main", rules: Dict[str, Any] | None = None) -> ValidationReport:
        """Valida código contra regras arquiteturais."""
        violations = []
        suggestions = []

        # 1. Buscar padrões do Scout
        patterns_data = await self.scout_client.get_patterns(repo_url, branch)
        patterns = patterns_data.get("patterns", [])

        # 2. Buscar insights do Scout
        insights_data = await self.scout_client.get_insights(repo_url, branch)
        insights = insights_data.get("insights", [])

        # 3. Verificar duplicação
        dup_violations = self.rules.check_duplication(patterns)
        violations.extend(dup_violations)

        # 4. Analisar classes (via insights)
        for insight in insights:
            if insight.get("type") == "class_info":
                class_violations = self.rules.check_srp(insight)
                violations.extend(class_violations)
            elif insight.get("type") == "function_info":
                func_violations = self.rules.check_complexity(insight)
                violations.extend(func_violations)

        # 5. Avaliar contra OPA (se configurado)
        try:
            opa_violations = await self.opa_client.check_architecture_rules({
                "repo_url": repo_url,
                "branch": branch
            })
            for v in opa_violations:
                violations.append(Violation(**v))
        except Exception:
            pass  # OPA opcional

        # 6. Gerar sugestões
        suggestions = self._generate_suggestions(violations)

        # 7. Calcular score de saúde
        health_score = self.rules.calculate_health_score(violations)

        return ValidationReport(
            report_id=f"val-{uuid.uuid4().hex[:8]}",
            repo_url=repo_url,
            branch=branch,
            health_score=health_score,
            violations=violations,
            suggestions=suggestions,
            metrics={
                "total_violations": len(violations),
                "by_severity": self._count_by_severity(violations),
                "by_type": self._count_by_type(violations)
            }
        )

    async def get_health_score(self, repo_url: str) -> int:
        """Retorna score de saúde arquitetural."""
        report = await self.validate(repo_url)
        return report.health_score

    def _generate_suggestions(self, violations: list) -> list:
        """Gera sugestões baseadas nas violações."""
        suggestions = []

        # Agrupar violações por tipo
        by_type = {}
        for v in violations:
            if v.type not in by_type:
                by_type[v.type] = []
            by_type[v.type].append(v)

        # Criar sugestões agregadas
        for vtype, vlist in by_type.items():
            if len(vlist) >= 3:
                suggestions.append(Suggestion(
                    priority=1,
                    description=f"Múltiplas violações de {vtype.value} detectadas ({len(vlist)} ocorrências)",
                    effort="L",
                    affected_files=list(set([v.location.split(":")[0] for v in vlist]))
                ))
            elif vtype in ["srp", "complexity"]:
                suggestions.append(Suggestion(
                    priority=2,
                    description=f"Revisar {vtype.value} violations",
                    effort="M"
                ))

        return suggestions[:5]  # Limitar a 5 sugestões

    def _count_by_severity(self, violations: list) -> dict:
        """Contagem de violações por severidade."""
        counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for v in violations:
            counts[v.severity.value] = counts.get(v.severity.value, 0) + 1
        return counts

    def _count_by_type(self, violations: list) -> dict:
        """Contagem de violações por tipo."""
        counts = {}
        for v in violations:
            counts[v.type.value] = counts.get(v.type.value, 0) + 1
        return counts
```

**Step 2: Commit**

```bash
git add services/architect-agent/src/validators/validate_engine.py services/architect-agent/src/validators/__init__.py
git commit -m "feat(architect-agent): adicionar ValidateEngine principal"
```

### Task 4.6: Testar Validate Engine

**Step 1: Criar teste unitário**

```python
# services/architect-agent/tests/unit/test_validate_engine.py
import pytest
from src.validators.validate_engine import ValidateEngine
from src.models.validation import ViolationType, Severity

@pytest.mark.asyncio
async def test_validate_engine_generates_report(mock_scout_client):
    """Testa que ValidateEngine gera ValidationReport."""
    engine = ValidateEngine()

    report = await engine.validate("github.com/org/repo", "main")

    assert report.report_id.startswith("val-")
    assert report.repo_url == "github.com/org/repo"
    assert 0 <= report.health_score <= 100
    assert isinstance(report.violations, list)
    assert isinstance(report.suggestions, list)

@pytest.mark.asyncio
async def test_validate_engine_calculates_health_score():
    """Testa cálculo de score de saúde."""
    from src.validators.rules import ArchitecturalRules
    from src.models.validation import Violation, ViolationType, Severity

    rules = ArchitecturalRules()

    # Sem violações = score 100
    score = rules.calculate_health_score([])
    assert score == 100

    # 1 violação crítica = score 80
    violations = [Violation(
        type=ViolationType.SRP,
        severity=Severity.CRITICAL,
        location="file.py:10",
        description="Test"
    )]
    score = rules.calculate_health_score(violations)
    assert score == 80
```

**Step 2: Executar testes**

```bash
cd services/architect-agent
pytest tests/unit/test_validate_engine.py -v
```

**Step 3: Commit**

```bash
git add services/architect-agent/tests/unit/test_validate_engine.py
git commit -m "test(architect-agent): adicionar testes do ValidateEngine"
```

---

## Task 5: Evolution Tracker

**Files:**
- Create: `services/architect-agent/src/evolution/__init__.py`
- Create: `services/architect-agent/src/evolution/tracker.py`
- Create: `services/architect-agent/src/evolution/comparator.py`
- Test: `services/architect-agent/tests/unit/test_evolution_tracker.py`

### Task 5.1: Criar Evolution Tracker

**Step 1: Criar tracker.py**

```python
# services/architect-agent/src/evolution/tracker.py
import uuid
from datetime import datetime
from typing import List, Dict, Any
from src.models.evolution import EvolutionHistory, DriftDetection, DriftType, ArchitectureDiff
from src.models.architecture import ArchitecturePlan

class EvolutionTracker:
    """Rastreia evolução de planos arquiteturais e detecta drifts."""

    def __init__(self, repository):
        self.repository = repository

    async def create_history(
        self,
        plan_id: str,
        changes: List[str],
        drifts: List[DriftDetection],
        created_by: str = "architect-agent"
    ) -> EvolutionHistory:
        """Cria entrada de histórico de evolução."""
        # Buscar última versão
        last_version = await self.repository.get_last_version(plan_id)
        new_version = (last_version or 0) + 1

        history = EvolutionHistory(
            history_id=f"evo-{uuid.uuid4().hex[:8]}",
            plan_id=plan_id,
            version=new_version,
            changes=changes,
            drifts=drifts,
            created_by=created_by
        )

        await self.repository.save(history)
        return history

    async def detect_drift(
        self,
        planned: ArchitecturePlan,
        actual: Dict[str, Any]
    ) -> List[DriftDetection]:
        """Detecta drift entre plano planejado e implementação real."""
        drifts = []

        # 1. Verificar tipo de arquitetura
        if actual.get("architecture_type") != planned.architecture_type.value:
            drifts.append(DriftDetection(
                drift_type=DriftType.ARCHITECTURE,
                description=f"Tipo de arquitetura divergiu",
                expected=planned.architecture_type.value,
                actual=actual.get("architecture_type", "unknown"),
                severity="high"
            ))

        # 2. Verificar componentes
        planned_components = {c.name: c.stack for c in planned.components}
        actual_components = actual.get("components", {})

        for name, stack in planned_components.items():
            if name not in actual_components:
                drifts.append(DriftDetection(
                    drift_type=DriftType.COMPONENTS,
                    description=f"Componente planejado não encontrado",
                    expected=name,
                    actual="missing",
                    severity="medium"
                ))

        # 3. Verificar padrões
        planned_patterns = [p.value for p in planned.patterns]
        actual_patterns = actual.get("patterns", [])

        for pattern in planned_patterns:
            if pattern not in actual_patterns:
                drifts.append(DriftDetection(
                    drift_type=DriftType.PATTERNS,
                    description=f"Padrão planejado não aplicado",
                    expected=pattern,
                    actual="not applied",
                    severity="low"
                ))

        return drifts

    async def compare_plans(
        self,
        plan_id_old: str,
        plan_id_new: str
    ) -> ArchitectureDiff:
        """Compara dois planos arquiteturais."""
        # Buscar planos
        plan_old = await self.repository.get_plan(plan_id_old)
        plan_new = await self.repository.get_plan(plan_id_new)

        if not plan_old or not plan_new:
            raise ValueError("Planos não encontrados")

        additions = []
        removals = []
        modifications = []

        # Comparar componentes
        old_components = {c.name: c for c in plan_old.components}
        new_components = {c.name: c for c in plan_new.components}

        for name in new_components:
            if name not in old_components:
                additions.append(f"Componente {name} adicionado")

        for name in old_components:
            if name not in new_components:
                removals.append(f"Componente {name} removido")

        for name in old_components:
            if name in new_components:
                if old_components[name].stack != new_components[name].stack:
                    modifications.append(f"Componente {name} stack alterado")

        # Comparar padrões
        old_patterns = set(p.value for p in plan_old.patterns)
        new_patterns = set(p.value for p in plan_new.patterns)

        additions.extend([f"Padrão {p}" for p in new_patterns - old_patterns])
        removals.extend([f"Padrão {p}" for p in old_patterns - new_patterns])

        return ArchitectureDiff(
            plan_id_old=plan_id_old,
            plan_id_new=plan_id_new,
            additions=additions,
            removals=removals,
            modifications=modifications,
            requires_migration=len(removals) > 0 or len(modifications) > 0
        )
```

**Step 2: Commit**

```bash
git add services/architect-agent/src/evolution/tracker.py services/architect-agent/src/evolution/__init__.py
git commit -m "feat(architect-agent): adicionar EvolutionTracker com drift detection"
```

### Task 5.2: Criar comparador

**Step 1: Criar comparator.py**

```python
# services/architect-agent/src/evolution/comparator.py
from typing import List, Dict, Any, Tuple

class ArchitectureComparator:
    """Compara estados de arquitetura."""

    @staticmethod
    def compare_components(
        old: List[Dict[str, Any]],
        new: List[Dict[str, Any]]
    ) -> Tuple[List[str], List[str], List[str]]:
        """Compara listas de componentes."""
        old_names = {c["name"] for c in old}
        new_names = {c["name"] for c in new}

        additions = list(new_names - old_names)
        removals = list(old_names - new_names)
        common = old_names & new_names

        modifications = []
        for name in common:
            old_comp = next(c for c in old if c["name"] == name)
            new_comp = next(c for c in new if c["name"] == name)
            if old_comp != new_comp:
                modifications.append(f"{name}: {old_comp.get('stack')} -> {new_comp.get('stack')}")

        return additions, removals, modifications

    @staticmethod
    def calculate_drift_score(planned: Any, actual: Any) -> float:
        """Calcula score de drift (0 = idêntico, 1 = completamente diferente)."""
        # Implementação simplificada
        return 0.0
```

**Step 2: Commit**

```bash
git add services/architect-agent/src/evolution/comparator.py
git commit -m "feat(architect-agent): adicionar ArchitectureComparator"
```

---

## Task 6: Repositories (MongoDB)

**Files:**
- Create: `services/architect-agent/src/repositories/__init__.py`
- Create: `services/architect-agent/src/repositories/architecture_repo.py`
- Create: `services/architect-agent/src/repositories/validation_repo.py`

### Task 6.1: Criar Architecture Repository

**Step 1: Criar architecture_repo.py**

```python
# services/architect-agent/src/repositories/architecture_repo.py
from motor.motor_asyncio import AsyncIOMotorClient
from typing import List, Optional
from src.config.settings import get_settings
from src.models.architecture import ArchitecturePlan

settings = get_settings()

class ArchitectureRepository:
    """Repositório MongoDB para ArchitecturePlan."""

    def __init__(self, client: AsyncIOMotorClient):
        self.client = client
        self.db = client[settings.mongodb_database]
        self.collection = self.db[settings.mongodb_collection_architecture]

    async def save(self, plan: ArchitecturePlan) -> ArchitecturePlan:
        """Salva plano no MongoDB."""
        await self.collection.insert_one(plan.model_dump())
        return plan

    async def get(self, plan_id: str) -> Optional[ArchitecturePlan]:
        """Busca plano por ID."""
        doc = await self.collection.find_one({"plan_id": plan_id})
        if doc:
            doc.pop("_id", None)
            return ArchitecturePlan(**doc)
        return None

    async def list_by_cognitive_plan(self, cognitive_plan_id: str) -> List[ArchitecturePlan]:
        """Lista planos associados a um CognitivePlan."""
        cursor = self.collection.find({"cognitive_plan_id": cognitive_plan_id})
        plans = []
        async for doc in cursor:
            doc.pop("_id", None)
            plans.append(ArchitecturePlan(**doc))
        return plans

    async def update(self, plan_id: str, updates: dict) -> Optional[ArchitecturePlan]:
        """Atualiza plano existente."""
        result = await self.collection.update_one(
            {"plan_id": plan_id},
            {"$set": updates}
        )
        if result.modified_count > 0:
            return await self.get(plan_id)
        return None

    async def get_last_version(self, plan_id: str) -> Optional[int]:
        """Retorna última versão do plano (para EvolutionTracker)."""
        # Simplificado: retorna 1 se plano existe
        plan = await self.get(plan_id)
        return 1 if plan else None
```

**Step 2: Commit**

```bash
git add services/architect-agent/src/repositories/architecture_repo.py
git commit -m "feat(architect-agent): adicionar ArchitectureRepository MongoDB"
```

### Task 6.2: Criar Validation Repository

**Step 1: Criar validation_repo.py**

```python
# services/architect-agent/src/repositories/validation_repo.py
from motor.motor_asyncio import AsyncIOMotorClient
from typing import List, Optional
from datetime import datetime, timedelta
from src.config.settings import get_settings
from src.models.validation import ValidationReport

settings = get_settings()

class ValidationRepository:
    """Repositório MongoDB para ValidationReport."""

    def __init__(self, client: AsyncIOMotorClient):
        self.client = client
        self.db = client[settings.mongodb_database]
        self.collection = self.db[settings.mongodb_collection_validation]

    async def save(self, report: ValidationReport) -> ValidationReport:
        """Salva relatório de validação."""
        await self.collection.insert_one(report.model_dump())
        return report

    async def get_latest(self, repo_url: str, branch: str = "main") -> Optional[ValidationReport]:
        """Busca relatório mais recente para um repositório."""
        doc = await self.collection.find_one(
            {"repo_url": repo_url, "branch": branch},
            sort=[("created_at", -1)]
        )
        if doc:
            doc.pop("_id", None)
            return ValidationReport(**doc)
        return None

    async def get_history(
        self,
        repo_url: str,
        days: int = 30
    ) -> List[ValidationReport]:
        """Busca histórico de validações."""
        since = datetime.utcnow() - timedelta(days=days)
        cursor = self.collection.find({
            "repo_url": repo_url,
            "created_at": {"$gte": since}
        }).sort("created_at", -1)

        reports = []
        async for doc in cursor:
            doc.pop("_id", None)
            reports.append(ValidationReport(**doc))
        return reports

    async def calculate_trend(self, repo_url: str) -> str:
        """Calcula tendência de saúde arquitetural."""
        history = await self.get_history(repo_url, days=7)
        if len(history) < 2:
            return "stable"

        # Comparar média dos últimos 3 com os 3 anteriores
        recent_scores = [r.health_score for r in history[:3]]
        previous_scores = [r.health_score for r in history[3:6]] if len(history) >= 6 else recent_scores

        recent_avg = sum(recent_scores) / len(recent_scores)
        previous_avg = sum(previous_scores) / len(previous_scores)

        if recent_avg > previous_avg + 5:
            return "up"
        elif recent_avg < previous_avg - 5:
            return "down"
        else:
            return "stable"
```

**Step 2: Commit**

```bash
git add services/architect-agent/src/repositories/validation_repo.py services/architect-agent/src/repositories/__init__.py
git commit -m "feat(architect-agent): adicionar ValidationRepository MongoDB"
```

---

## Task 7: Kafka Consumer (CognitivePlan)

**Files:**
- Create: `services/architect-agent/src/consumers/__init__.py`
- Create: `services/architect-agent/src/consumers/cognitive_plan_consumer.py`
- Test: `services/architect-agent/tests/integration/test_cognitive_plan_consumer.py`

### Task 7.1: Criar Kafka Consumer

**Step 1: Criar cognitive_plan_consumer.py**

```python
# services/architect-agent/src/consumers/cognitive_plan_consumer.py
import asyncio
import json
from confluent_kafka import Consumer, KafkaError
from src.config.settings import get_settings
from src.planners.design_planner import DesignPlanner
from src.repositories.architecture_repo import ArchitectureRepository
from motor.motor_asyncio import AsyncIOMotorClient
import structlog

settings = get_settings()
logger = structlog.get_logger(__name__)

class CognitivePlanConsumer:
    """Consome CognitivePlans do STE e gera ArchitecturePlans."""

    def __init__(self):
        self.consumer = None
        self.planner = DesignPlanner()
        self.running = False

    async def start(self, mongo_client: AsyncIOMotorClient):
        """Inicia consumo de mensagens Kafka."""
        self.consumer = Consumer({
            'bootstrap.servers': settings.kafka_bootstrap_servers,
            'group.id': settings.kafka_consumer_group,
            'auto.offset.reset': settings.kafka_auto_offset_reset,
            'enable.auto.commit': True
        })

        self.consumer.subscribe([settings.kafka_cognitive_plans_topic])
        self.running = True

        repo = ArchitectureRepository(mongo_client)

        logger.info("cognitive_plan_consumer_started", topic=settings.kafka_cognitive_plans_topic)

        while self.running:
            try:
                msg = self.consumer.poll(timeout=1.0)
                if msg is None:
                    continue

                if msg.error():
                    logger.error("kafka_consumer_error", error=str(msg.error()))
                    continue

                # Processar mensagem
                await self._process_message(msg.value(), repo)

            except Exception as e:
                logger.error("consumer_processing_error", error=str(e))
                await asyncio.sleep(5)

    async def _process_message(self, msg_value: bytes, repo: ArchitectureRepository):
        """Processa mensagem do CognitivePlan."""
        try:
            data = json.loads(msg_value.decode('utf-8'))

            # Extrair requisitos
            requirements = {
                "cognitive_plan_id": data.get("plan_id"),
                "intent": data.get("intent", ""),
                "scale": data.get("scale", "medium"),
                "consistency": data.get("consistency", "eventual"),
                "latency_p99_ms": data.get("latency_p99_ms", 500),
                "team_size": data.get("team_size", 5),
                "budget": data.get("budget", "medium")
            }

            # Gerar ArchitecturePlan
            plan = await self.planner.plan(requirements)

            # Salvar no MongoDB
            await repo.save(plan)

            logger.info("architecture_plan_created",
                        plan_id=plan.plan_id,
                        cognitive_plan_id=data.get("plan_id"),
                        architecture_type=plan.architecture_type)

        except Exception as e:
            logger.error("message_processing_failed", error=str(e))

    def stop(self):
        """Para consumo de mensagens."""
        self.running = False
        if self.consumer:
            self.consumer.close()
        logger.info("cognitive_plan_consumer_stopped")
```

**Step 2: Commit**

```bash
git add services/architect-agent/src/consumers/cognitive_plan_consumer.py services/architect-agent/src/consumers/__init__.py
git commit -m "feat(architect-agent): adicionar Kafka consumer para CognitivePlan"
```

---

## Task 8: API REST

**Files:**
- Create: `services/architect-agent/src/api/__init__.py`
- Create: `services/architect-agent/src/api/router.py`
- Create: `services/architect-agent/src/observability/metrics.py`

### Task 8.1: Criar métricas Prometheus

**Step 1: Criar metrics.py**

```python
# services/architect-agent/src/observability/metrics.py
from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry
from fastapi import FastAPI

registry = CollectorRegistry()

# Contadores
architect_plans_created = Counter(
    'architect_plans_created_total',
    'Total de ArchitecturePlans criados',
    ['architecture_type'],
    registry=registry
)

architect_validations_run = Counter(
    'architect_validations_run_total',
    'Total de validações executadas',
    ['repo_url'],
    registry=registry
)

# Histogramas
architect_planning_duration = Histogram(
    'architect_planning_duration_seconds',
    'Duração do planejamento arquitetural',
    ['phase'],
    registry=registry
)

# Gauges
architect_health_score = Gauge(
    'architect_health_score',
    'Score de saúde arquitetural',
    ['repo_url'],
    registry=registry
)

architect_violations_detected = Counter(
    'architect_violations_detected_total',
    'Total de violações detectadas',
    ['severity', 'type'],
    registry=registry
)

def init_metrics(app: FastAPI):
    """Inicializa endpoint de métricas."""
    from prometheus_client import make_asgi_app
    metrics_app = make_asgi_app(registry=registry)
    app.mount("/metrics", metrics_app)
```

**Step 2: Commit**

```bash
git add services/architect-agent/src/observability/metrics.py services/architect-agent/src/observability/__init__.py
git commit -m "feat(architect-agent): adicionar métricas Prometheus"
```

### Task 8.2: Criar router FastAPI

**Step 1: Criar router.py**

```python
# services/architect-agent/src/api/router.py
from fastapi import APIRouter, HTTPException, Depends
from motor.motor_asyncio import AsyncIOMotorClient
from src.config.settings import get_settings
from src.planners.design_planner import DesignPlanner
from src.validators.validate_engine import ValidateEngine
from src.evolution.tracker import EvolutionTracker
from src.repositories.architecture_repo import ArchitectureRepository
from src.repositories.validation_repo import ValidationRepository
from src.models.architecture import ArchitecturePlan
from src.models.validation import ValidationReport
from src.observability.metrics import (
    architect_plans_created,
    architect_planning_duration,
    architect_validations_run,
    architect_health_score
)
import structlog

logger = structlog.get_logger(__name__)
router = APIRouter()
settings = get_settings()

# Dependências
async def get_mongo_client():
    """Retorna cliente MongoDB."""
    from motor.motor_asyncio import AsyncIOMotorClient
    return AsyncIOMotorClient(settings.mongodb_url)

# Endpoints de Planejamento
@router.post("/architect/plan", response_model=ArchitecturePlan)
async def create_architecture_plan(
    request: dict,
    mongo_client: AsyncIOMotorClient = Depends(get_mongo_client)
):
    """Cria plano arquitetural."""
    with architect_planning_duration.labels(phase="total").time():
        planner = DesignPlanner()
        repo = ArchitectureRepository(mongo_client)

        plan = await planner.plan(request)
        await repo.save(plan)

        architect_plans_created.labels(
            architecture_type=plan.architecture_type.value
        ).inc()

        logger.info("architecture_plan_created",
                    plan_id=plan.plan_id,
                    type=plan.architecture_type.value)

        return plan

@router.get("/architect/plan/{plan_id}", response_model=ArchitecturePlan)
async def get_architecture_plan(
    plan_id: str,
    mongo_client: AsyncIOMotorClient = Depends(get_mongo_client)
):
    """Busca plano arquitetural."""
    repo = ArchitectureRepository(mongo_client)
    plan = await repo.get(plan_id)

    if not plan:
        raise HTTPException(status_code=404, detail="Plano não encontrado")

    return plan

# Endpoints de Validação
@router.post("/architect/validate", response_model=ValidationReport)
async def validate_architecture(
    request: dict,
    mongo_client: AsyncIOMotorClient = Depends(get_mongo_client)
):
    """Valida código contra regras arquiteturais."""
    repo_url = request.get("repo_url")
    branch = request.get("branch", "main")
    rules = request.get("rules")

    architect_validations_run.labels(repo_url=repo_url).inc()

    engine = ValidateEngine()
    report = await engine.validate(repo_url, branch, rules)

    # Salvar relatório
    validation_repo = ValidationRepository(mongo_client)
    await validation_repo.save(report)

    # Atualizar gauge de health score
    architect_health_score.labels(repo_url=repo_url).set(report.health_score)

    logger.info("architecture_validated",
                repo_url=repo_url,
                health_score=report.health_score)

    return report

@router.get("/architect/health/{repo_url:path}")
async def get_architecture_health(
    repo_url: str,
    mongo_client: AsyncIOMotorClient = Depends(get_mongo_client)
):
    """Retorna score de saúde arquitetural."""
    engine = ValidateEngine()
    score = await engine.get_health_score(repo_url)

    # Buscar tendência
    validation_repo = ValidationRepository(mongo_client)
    trend = await validation_repo.calculate_trend(repo_url)

    # Buscar top violações
    latest = await validation_repo.get_latest(repo_url)
    top_violations = latest.violations[:5] if latest else []

    return {
        "repo_url": repo_url,
        "health_score": score,
        "trend": trend,
        "top_violations": top_violations
    }

# Endpoints de Evolução
@router.post("/architect/evolve")
async def suggest_evolution(
    request: dict,
    mongo_client: AsyncIOMotorClient = Depends(get_mongo_client)
):
    """Sugere evolução para plano existente."""
    plan_id = request.get("plan_id")
    new_requirements = request.get("requirements")

    planner = DesignPlanner()
    repo = ArchitectureRepository(mongo_client)

    # Buscar plano atual
    current = await repo.get(plan_id)
    if not current:
        raise HTTPException(status_code=404, detail="Plano não encontrado")

    # Refinar com novos requisitos
    refined = await planner.refine(plan_id, new_requirements)

    # Salvar novo plano
    await repo.save(refined)

    logger.info("architecture_evolved",
                old_plan_id=plan_id,
                new_plan_id=refined.plan_id)

    return refined
```

**Step 2: Atualizar main.py para importar router**

```python
# services/architect-agent/src/main.py - atualizar imports
# ... código existente ...

from src.api.router import router as api_router  # Adicionar

app = FastAPI(...)
app.include_router(api_router, prefix="/api/v1")  # Já existe

# ... restante do código ...
```

**Step 3: Commit**

```bash
git add services/architect-agent/src/api/router.py services/architect-agent/src/api/__init__.py
git commit -m "feat(architect-agent): adicionar API REST endpoints"
```

---

## Task 9: Testes de Integração e E2E

**Files:**
- Create: `services/architect-agent/tests/integration/test_scout_client.py`
- Create: `services/architect-agent/tests/e2e/test_plan_to_validate.py`

### Task 9.1: Criar testes de integração Scout

**Step 1: Criar teste**

```python
# services/architect-agent/tests/integration/test_scout_client.py
import pytest
from httpx import Transport
from src.validators.scout_client import ScoutClient

@pytest.mark.asyncio
async def test_scout_client_get_patterns():
    """Testa integração com Scout Agents."""
    client = ScoutClient()

    # Testar com repositório público
    patterns = await client.get_patterns("https://github.com/albinoJimy/Neural-Hive-Mind")

    assert "patterns" in patterns
    assert isinstance(patterns["patterns"], list)

@pytest.mark.asyncio
async def test_scout_client_fallback():
    """Testa fallback quando Scout indisponível."""
    # Cliente com URL inválida
    from src.config.settings import get_settings
    settings = get_settings()
    original_url = settings.scout_agents_url

    # Modificar temporariamente
    settings.scout_agents_url = "http://invalid:9999"

    client = ScoutClient()
    patterns = await client.get_patterns("test")

    # Deve retornar vazio (fallback)
    assert patterns == {"patterns": []}

    # Restaurar
    settings.scout_agents_url = original_url
```

**Step 2: Commit**

```bash
git add services/architect-agent/tests/integration/test_scout_client.py services/architect-agent/tests/integration/__init__.py
git commit -m "test(architect-agent): adicionar testes integração Scout"
```

### Task 9.2: Criar teste E2E

**Step 1: Criar teste E2E**

```python
# services/architect-agent/tests/e2e/test_plan_to_validate.py
import pytest
from src.planners.design_planner import DesignPlanner
from src.validators.validate_engine import ValidateEngine
from motor.motor_asyncio import AsyncIOMotorClient
from src.config.settings import get_settings

settings = get_settings()

@pytest.mark.asyncio
async def test_plan_to_validate_flow(mongo_client):
    """Teste E2E: Planejamento → Validação."""
    # 1. Criar plano
    planner = DesignPlanner()
    requirements = {
        "intent": "create user microservice",
        "scale": "high",
        "consistency": "strong"
    }

    plan = await planner.plan(requirements)

    assert plan.plan_id.startswith("arch-")
    assert plan.components

    # 2. Validar (simulado - repo_url aponta para projeto)
    validator = ValidateEngine()
    report = await validator.validate(
        repo_url="https://github.com/albinoJimy/Neural-Hive-Mind",
        branch="main"
    )

    assert report.report_id.startswith("val-")
    assert 0 <= report.health_score <= 100
```

**Step 3: Commit**

```bash
git add services/architect-agent/tests/e2e/test_plan_to_validate.py services/architect-agent/tests/e2e/__init__.py
git commit -m "test(architect-agent): adicionar teste E2E"
```

---

## Task 10: Helm Chart e Deploy

**Files:**
- Create: `services/architect-agent/helm/architect-agent/Chart.yaml`
- Create: `services/architect-agent/helm/architect-agent/values.yaml`
- Create: `services/architect-agent/helm/architect-agent/templates/deployment.yaml`
- Create: `services/architect-agent/helm/architect-agent/templates/service.yaml`
- Create: `services/architect-agent/helm/architect-agent/templates/serviceaccount.yaml`

### Task 10.1: Criar Helm Chart

**Step 1: Criar Chart.yaml**

```yaml
# services/architect-agent/helm/architect-agent/Chart.yaml
apiVersion: v2
name: architect-agent
description: Neural Hive Mind - Architect Agent service
type: application
version: 1.0.0
appVersion: "1.0.0"
```

**Step 2: Criar values.yaml**

```yaml
# services/architect-agent/helm/architect-agent/values.yaml
replicaCount: 2

image:
  repository: architect-agent
  pullPolicy: IfNotPresent
  tag: "latest"

service:
  type: ClusterIP
  port: 8008
  metricsPort: 9098

resources:
  limits:
    cpu: 500m
    memory: 512Mi
  requests:
    cpu: 250m
    memory: 256Mi

autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilizationPercentage: 70

env:
  kafka_bootstrap_servers: "kafka.neural-hive:9092"
  mongodb_url: "mongodb://mongodb:27017"
  scout_agents_url: "http://scout-agents:8020"
  opa_url: "http://opa.neural-hive-governance:8181"
```

**Step 3: Criar deployment.yaml**

```yaml
# services/architect-agent/helm/architect-agent/templates/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "architect-agent.fullname" . }}
  labels:
    {{- include "architect-agent.labels" . | nindent 4 }}
spec:
  replicas: {{ .Values.replicaCount }}
  selector:
    matchLabels:
      {{- include "architect-agent.selectorLabels" . | nindent 6 }}
  template:
    metadata:
      labels:
        {{- include "architect-agent.selectorLabels" . | nindent 8 }}
    spec:
      serviceAccountName: {{ include "architect-agent.serviceAccountName" . }}
      containers:
      - name: {{ .Chart.Name }}
        image: "{{ .Values.image.repository }}:{{ .Values.image.tag | default .Chart.AppVersion }}"
        imagePullPolicy: {{ .Values.image.pullPolicy }}
        ports:
        - name: http
          containerPort: {{ .Values.service.port }}
        - name: metrics
          containerPort: {{ .Values.service.metricsPort }}
        env:
        - name: KAFKA_BOOTSTRAP_SERVERS
          value: {{ .Values.env.kafka_bootstrap_servers | quote }}
        - name: MONGODB_URL
          value: {{ .Values.env.mongodb_url | quote }}
        - name: SCOUT_AGENTS_URL
          value: {{ .Values.env.scout_agents_url | quote }}
        - name: OPA_URL
          value: {{ .Values.env.opa_url | quote }}
        resources:
          {{- toYaml .Values.resources | nindent 10 }}
        livenessProbe:
          httpGet:
            path: /health/live
            port: http
          initialDelaySeconds: 10
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health/ready
            port: http
          initialDelaySeconds: 5
          periodSeconds: 5
```

**Step 4: Criar service.yaml**

```yaml
# services/architect-agent/helm/architect-agent/templates/service.yaml
apiVersion: v1
kind: Service
metadata:
  name: {{ include "architect-agent.fullname" . }}
  labels:
    {{- include "architect-agent.labels" . | nindent 4 }}
spec:
  type: {{ .Values.service.type }}
  ports:
  - port: {{ .Values.service.port }}
    targetPort: http
    protocol: TCP
    name: http
  - port: {{ .Values.service.metricsPort }}
    targetPort: metrics
    protocol: TCP
    name: metrics
  selector:
    {{- include "architect-agent.selectorLabels" . | nindent 4 }}
```

**Step 5: Commit**

```bash
git add services/architect-agent/helm/
git commit -m "feat(architect-agent): adicionar Helm chart para deploy"
```

---

## Task 11: README e Documentação

**Files:**
- Create: `services/architect-agent/README.md`

### Task 11.1: Criar README

**Step 1: Criar README.md**

```markdown
# Architect Agent

Sistema especializado em arquitetura de software para o Neural Hive Mind.

## Descrição

O Architect Agent atua em duas fases:
1. **Planejamento**: Analisa requisitos e propõe arquitetura (tipo, componentes, padrões)
2. **Validação**: Analisa código existente e valida contra princípios arquiteturais

## Funcionalidades

- **Design Planner**: Geração de planos arquiteturais via LLM
- **Validate Engine**: Validação contra SOLID, complexidade, duplicação
- **Evolution Tracker**: Histórico de decisões e detecção de drift

## API

### Planejamento
- `POST /api/v1/architect/plan` - Criar plano arquitetural
- `GET /api/v1/architect/plan/{id}` - Buscar plano existente
- `POST /api/v1/architect/evolve` - Sugerir evolução

### Validação
- `POST /api/v1/architect/validate` - Validar código
- `GET /api/v1/architect/health/{repo}` - Score de saúde

## Deploy

```bash
helm install architect-agent ./helm/architect-agent
```

## Testes

```bash
pytest tests/ -v --cov=src
```
```

**Step 2: Commit final**

```bash
git add services/architect-agent/README.md
git commit -m "docs(architect-agent): adicionar README completo"
```

---

## Resumo

**Total de tasks:** 11
**Estimativa de esforço:** 8-10 dias
**Testes alvo:** 60+ testes unitários/integração/E2E

**Componentes implementados:**
- Design Planner (com LLM integration)
- Validate Engine (regras SOLID, Scout integration)
- Evolution Tracker (drift detection)
- Kafka Consumer (CognitivePlan input)
- REST API (8 endpoints)
- MongoDB repositories
- Prometheus metrics
- Helm chart
```

---

I'll now create the second plan for Software Engineering Pipeline.</think><tool_call>Write<arg_key>content</arg_key><arg_value># Software Engineering Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Criar sistema completo de CI/CD com geração automática de pipelines, orquestração de deploys e inteligência para detecção de anomalias.

**Architecture:** Serviço FastAPI com 3 componentes core: Pipeline Generator (gera CI/CD workflows), Pipeline Orchestrator (orquestra deploys com gates), Pipeline Intelligence (monitora e otimiza). Integra com Code Forge, GitHub/GitLab, ArgoCD/Flux, persiste no MongoDB.

**Tech Stack:** FastAPI, Python 3.12+, MongoDB, GitHub API, GitLab API, ArgoCD, Flux CD, Prometheus, sklearn

---

## File Structure

```
services/software-engineering-pipeline/
├── src/
│   ├── main.py                        # Entry point FastAPI
│   ├── config/
│   │   └── settings.py                # Configurações Pydantic
│   ├── models/
│   │   ├── __init__.py
│   │   ├── pipeline.py                # PipelineManifest, PipelineRun
│   │   ├── insights.py                # Insights, Anomaly
│   │   └── deploy.py                  # DeploySpec, RollbackStatus
│   ├── generators/
│   │   ├── __init__.py
│   │   ├── base.py                    # BaseGenerator interface
│   │   ├── github_actions.py          # GitHub Actions generator
│   │   ├── gitlab_ci.py               # GitLab CI generator
│   │   ├── jenkins.py                 # Jenkins generator
│   │   └── tekton.py                  # Tekton generator
│   ├── orchestrators/
│   │   ├── __init__.py
│   │   ├── pipeline_orchestrator.py   # Orchestrator principal
│   │   ├── stages.py                  # Stage executors (build, test, deploy)
│   │   └── gates.py                   # Approval gates
│   ├── intelligence/
│   │   ├── __init__.py
│   │   ├── anomaly_detector.py        # Detecção de anomalias
│   │   ├── flaky_test_detector.py     # Testes flaky
│   │   ├── optimizer.py               # Otimizador de pipelines
│   │   └── rollback_manager.py        # Auto-rollback
│   ├── clients/
│   │   ├── __init__.py
│   │   ├── github_client.py           # GitHub API client
│   │   ├── gitlab_client.py           # GitLab API client
│   │   ├── argocd_client.py           # ArgoCD API client
│   │   └── flux_client.py             # Flux CD client
│   ├── api/
│   │   ├── __init__.py
│   │   └── router.py                  # FastAPI routes
│   ├── repositories/
│   │   ├── __init__.py
│   │   ├── pipeline_run_repo.py       # MongoDB repo
│   │   └── insights_repo.py           # MongoDB repo
│   └── observability/
│       ├── __init__.py
│       └── metrics.py                 # Prometheus metrics
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── helm/software-engineering-pipeline/
│   ├── Chart.yaml
│   ├── values.yaml
│   └── templates/
├── Dockerfile
├── requirements.txt
└── README.md
```

---

## Task 1: Estrutura Base do Serviço

**Files:**
- Create: `services/software-engineering-pipeline/src/main.py`
- Create: `services/software-engineering-pipeline/src/config/settings.py`
- Create: `services/software-engineering-pipeline/requirements.txt`
- Create: `services/software-engineering-pipeline/Dockerfile`

### Task 1.1: Criar configurações

**Step 1: Criar settings.py**

```python
# services/software-engineering-pipeline/src/config/settings.py
from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache

class Settings(BaseSettings):
    # Service
    service_name: str = "software-engineering-pipeline"
    environment: str = Field(default="development", pattern="^(development|staging|production)$")
    log_level: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR)$")
    http_port: int = 8009

    # MongoDB
    mongodb_url: str = "mongodb://localhost:27017"
    mongodb_database: str = "pipeline"
    mongodb_collection_runs: str = "pipeline_runs"
    mongodb_collection_insights: str = "pipeline_insights"

    # GitHub
    github_api_url: str = "https://api.github.com"
    github_token: str = ""
    github_timeout_seconds: int = 30

    # GitLab
    gitlab_url: str = "https://gitlab.com"
    gitlab_token: str = ""
    gitlab_timeout_seconds: int = 30

    # ArgoCD
    argocd_url: str = "https://argocd.example.com"
    argocd_token: str = ""
    argocd_timeout_seconds: int = 60

    # Flux CD
    flux_enabled: bool = False
    flux_namespace: str = "flux-system"
    flux_kubeconfig_path: str = ""

    # Code Forge
    code_forge_url: str = "http://code-forge:8080"
    code_forge_timeout_seconds: int = 30

    # Prometheus
    prometheus_url: str = "http://prometheus:9090"
    prometheus_port: int = 9099

    # Pipeline defaults
    default_provider: str = Field(default="github", pattern="^(github|gitlab|jenkins|tekton)$")
    auto_rollback_enabled: bool = True
    rollback_threshold_errors: int = 10
    rollback_threshold_latency_p95: int = 2000  # ms

    class Config:
        env_file = ".env"
        case_sensitive = False

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

**Step 2: Commit**

```bash
git add services/software-engineering-pipeline/src/config/settings.py
git commit -m "feat(pipeline): adicionar configurações Pydantic"
```

### Task 1.2-1.5: Mesmo padrão do Architect Agent

Seguir mesmo padrão para:
- `main.py` (FastAPI entry point)
- `requirements.txt`
- `Dockerfile`
- `tests/conftest.py`

---

## Task 2: Modelos de Dados

**Files:**
- Create: `services/software-engineering-pipeline/src/models/__init__.py`
- Create: `services/software-engineering-pipeline/src/models/pipeline.py`
- Create: `services/software-engineering-pipeline/src/models/insights.py`
- Create: `services/software-engineering-pipeline/src/models/deploy.py`

### Task 2.1: Criar modelos de pipeline

**Step 1: Criar pipeline.py**

```python
# services/software-engineering-pipeline/src/models/pipeline.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Literal, Optional
from enum import Enum

class Provider(str, Enum):
    GITHUB = "github"
    GITLAB = "gitlab"
    JENKINS = "jenkins"
    TEKTON = "tekton"

class Stage(str, Enum):
    LINT = "lint"
    BUILD = "build"
    TEST = "test"
    SECURITY = "security"
    STAGING = "staging"
    PRODUCTION = "production"

class Status(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ROLLED_BACK = "rolled_back"

class PipelineManifest(BaseModel):
    """Manifesto de pipeline gerado."""
    manifest_id: str
    repo_url: str
    provider: Provider
    content: str  # YAML do workflow
    language: str = Field(default="yaml")  # yaml, groovy, json
    created_at: datetime = Field(default_factory=datetime.utcnow)

class PipelineRun(BaseModel):
    """Execução de pipeline."""
    run_id: str
    repo_url: str
    git_sha: str
    branch: str = "main"
    status: Status
    current_stage: Stage | None = None
    stages_completed: List[Stage] = Field(default_factory=list)
    stages_failed: List[Stage] = Field(default_factory=list)
    started_at: datetime
    finished_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    error_message: Optional[str] = None
    rollback_reason: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "run_id": "pipe-001",
                "repo_url": "github.com/org/repo",
                "git_sha": "abc123",
                "status": "running",
                "current_stage": "test"
            }
        }
```

**Step 2: Criar insights.py**

```python
# services/software-engineering-pipeline/src/models/insights.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional
from enum import Enum

class AnomalyType(str, Enum):
    FLAKY_TEST = "flaky_test"
    DEPENDENCY_ISSUE = "dependency_issue"
    PERFORMANCE_DEGRADATION = "performance_degradation"
    SECURITY_VULNERABILITY = "security_vulnerability"
    CONFIGURATION_DRIFT = "configuration_drift"

class AnomalySeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class Anomaly(BaseModel):
    """Anomalia detectada pelo Pipeline Intelligence."""
    anomaly_id: str
    type: AnomalyType
    severity: AnomalySeverity
    description: str
    affected_resource: str  # test_name, dependency_name, etc.
    detected_at: datetime = Field(default_factory=datetime.utcnow)
    resolved: bool = False
    resolution: Optional[str] = None

class Insight(BaseModel):
    """Insight gerado pelo Pipeline Intelligence."""
    insight_id: str
    repo_url: str
    timeframe_days: int
    total_runs: int
    success_rate: float
    avg_duration_seconds: float
    slowest_stages: List[str]
    flaky_tests: List[str]
    problematic_dependencies: List[str]
    suggestions: List[str]
    generated_at: datetime = Field(default_factory=datetime.utcnow)
```

**Step 3: Commit modelos**

```bash
git add services/software-engineering-pipeline/src/models/
git commit -m "feat(pipeline): adicionar modelos de dados"
```

---

## Task 3: Pipeline Generator

**Files:**
- Create: `services/software-engineering-pipeline/src/generators/__init__.py`
- Create: `services/software-engineering-pipeline/src/generators/base.py`
- Create: `services/software-engineering-pipeline/src/generators/github_actions.py`
- Create: `services/software-engineering-pipeline/src/generators/gitlab_ci.py`
- Test: `services/software-engineering-pipeline/tests/unit/test_github_actions.py`

### Task 3.1: Criar GitHub Actions Generator

**Step 1: Criar github_actions.py**

```python
# services/software-engineering-pipeline/src/generators/github_actions.py
import uuid
from typing import Dict, Any, List
from .base import BaseGenerator
from src.models.pipeline import PipelineManifest, Provider

class GitHubActionsGenerator(BaseGenerator):
    """Gerador de workflows para GitHub Actions."""

    async def generate(
        self,
        repo_url: str,
        stack_info: Dict[str, Any],
        overrides: Dict[str, Any] | None = None
    ) -> PipelineManifest:
        """Gera workflow YAML para GitHub Actions."""

        # Detectar stack
        language = stack_info.get("language", "python")
        has_docker = stack_info.get("has_dockerfile", False)
        has_tests = stack_info.get("has_tests", False)

        # Gerar workflow
        workflow = self._generate_workflow(language, has_docker, has_tests, overrides or {})

        return PipelineManifest(
            manifest_id=f"gh-{uuid.uuid4().hex[:8]}",
            repo_url=repo_url,
            provider=Provider.GITHUB,
            content=workflow
        )

    def _generate_workflow(
        self,
        language: str,
        has_docker: bool,
        has_tests: bool,
        overrides: Dict[str, Any]
    ) -> str:
        """Gera conteúdo do workflow YAML."""

        # Jobs base
        jobs = {"lint": self._lint_job(language)}

        if has_tests:
            jobs["test"] = self._test_job(language)

        if has_docker:
            jobs["build"] = self._build_job()
            jobs["security"] = self._security_job()

        # Job de deploy (apenas se habilitado)
        if overrides.get("enable_deploy", False):
            jobs["deploy"] = self._deploy_job(overrides.get("deploy_env", "staging"))

        # Montar YAML completo
        yaml_content = f"""name: Neural Hive CI/CD

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

{self._generate_jobs_yaml(jobs)}
"""
        return yaml_content

    def _lint_job(self, language: str) -> str:
        """Gera job de lint."""
        if language == "python":
            return """  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install ruff
      - name: Run ruff
        run: ruff check ."""
        elif language == "javascript":
            return """  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
      - name: Install dependencies
        run: npm ci
      - name: Run ESLint
        run: npm run lint"""
        else:
            return self._generic_job("lint")

    def _test_job(self, language: str) -> str:
        """Gera job de test."""
        if language == "python":
            return """  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ['3.11', '3.12']
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install pytest pytest-cov
      - name: Run tests
        run: pytest --cov=src --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v4"""
        else:
            return self._generic_job("test")

    def _build_job(self) -> str:
        """Gera job de build Docker."""
        return """  build:
    runs-on: ubuntu-latest
    needs: [lint]
    steps:
      - uses: actions/checkout@v4
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      - name: Login to Container Registry
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY_URL }}
          username: ${{ env.REGISTRY_USERNAME }}
          password: ${{ secrets.REGISTRY_PASSWORD }}
      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: ${{ env.REGISTRY_URL }}/${{ github.repository }}:${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
      - name: Generate SBOM
        run: docker sbom ${{ env.REGISTRY_URL }}/${{ github.repository }}:${{ github.sha }} > sbom.json
      - name: Upload SBOM
        uses: actions/upload-artifact@v4
        with:
          name: sbom
          path: sbom.json"""

    def _security_job(self) -> str:
        """Gera job de segurança."""
        return """  security:
    runs-on: ubuntu-latest
    needs: [build]
    steps:
      - uses: actions/checkout@v4
      - name: Run Trivy vulnerability scanner
        uses: aquasecurity/trivy-action@master
        with:
          scan-type: 'fs'
          scan-ref: '.'
          format: 'sarif'
          output: 'trivy-results.sarif'
      - name: Upload Trivy results to GitHub Security tab
        uses: github/codeql-action/upload-sarif@v3
        if: always()
        with:
          sarif_file: 'trivy-results.sarif'"""

    def _deploy_job(self, environment: str) -> str:
        """Gera job de deploy."""
        return f"""  deploy-{environment}:
    runs-on: ubuntu-latest
    needs: [test, security]
    environment: {environment}
    steps:
      - uses: actions/checkout@v4
      - name: Deploy to {environment}
        run: |
          echo "Deploying to {environment}"
          # Integrar com ArgoCD ou kubectl
          kubectl set image deployment/app \\
            app-container=${{ env.REGISTRY_URL }}/${{ github.repository }}:${{ github.sha }}
          kubectl rollout status deployment/app"""

    def _generate_jobs_yaml(self, jobs: Dict[str, str]) -> str:
        """Gera seção jobs do YAML."""
        lines = []
        for name, job in jobs.items():
            lines.append(job)
        return "\n".join(lines)

    def _generic_job(self, job_type: str) -> str:
        """Job genérico."""
        return f"""  {job_type}:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run {job_type}
        run: echo "Add {job_type} command here"
"""
```

**Step 2: Commit**

```bash
git add services/software-engineering-pipeline/src/generators/github_actions.py
git commit -m "feat(pipeline): adicionar GitHub Actions generator"
```

### Task 3.2: Criar GitLab CI Generator

**Step 1: Criar gitlab_ci.py**

```python
# services/software-engineering-pipeline/src/generators/gitlab_ci.py
import uuid
from typing import Dict, Any
from .base import BaseGenerator
from src.models.pipeline import PipelineManifest, Provider

class GitLabCIGenerator(BaseGenerator):
    """Gerador de pipelines para GitLab CI."""

    async def generate(
        self,
        repo_url: str,
        stack_info: Dict[str, Any],
        overrides: Dict[str, Any] | None = None
    ) -> PipelineManifest:
        """Gera pipeline YAML para GitLab CI."""

        language = stack_info.get("language", "python")
        has_docker = stack_info.get("has_dockerfile", False)

        pipeline = self._generate_pipeline(language, has_docker)

        return PipelineManifest(
            manifest_id=f"gl-{uuid.uuid4().hex[:8]}",
            repo_url=repo_url,
            provider=Provider.GITLAB,
            content=pipeline
        )

    def _generate_pipeline(self, language: str, has_docker: bool) -> str:
        """Gera conteúdo do .gitlab-ci.yml."""

        stages = ["lint", "test", "build", "security"]
        if has_docker:
            stages.append("deploy")

        lint_job = self._lint_job(language)
        test_job = self._test_job(language)
        build_job = self._build_job() if has_docker else ""
        security_job = self._security_job() if has_docker else ""

        return f"""stages:
{''.join([f"  - {s}" for s in stages])}

{lint_job}

{test_job}

{build_job}

{security_job}

deploy:staging:
  stage: deploy
  script:
    - kubectl set image deployment/app app-container=$CI_REGISTRY_IMAGE:$CI_COMMIT_SHA
    - kubectl rollout status deployment/app
  only:
    - develop
"""

    def _lint_job(self, language: str) -> str:
        if language == "python":
            return """lint:
  stage: lint
  image: python:3.12
  script:
    - pip install ruff
    - ruff check ."""
        return self._generic_job("lint", "lint: runs")

    def _test_job(self, language: str) -> str:
        if language == "python":
            return """test:
  stage: test
  image: python:3.12
  script:
    - pip install pytest pytest-cov
    - pytest --cov=src --cov-report=term
  coverage: '/(?i)total.*? (100(?:\.0+)?%|([1-9]?\d)?\.\d+%)/'
  artifacts:
    reports:
      coverage_report:
        coverage_format: cobertura
        path: coverage.xml"""
        return self._generic_job("test", "test: runs")

    def _build_job(self) -> str:
        return """build:
  stage: build
  image: docker:24
  services:
    - docker:24-dind
  script:
    - docker login -u $CI_REGISTRY_USER -p $CI_REGISTRY_PASSWORD $CI_REGISTRY
    - docker build -t $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA .
    - docker push $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA
  artifacts:
    reports:
      sbom: sbom.json"""

    def _security_job(self) -> str:
        return """security:
  stage: security
  image: aquasec/trivy:latest
  script:
    - trivy fs --format sarif --output trivy-results.sarif .
  artifacts:
    reports:
      sast: trivy-results.sarif
  allow_failure: true"""

    def _generic_job(self, name: str, script: str) -> str:
        return f"""{name}:
  stage: {name}
  script:
    - echo "Add {name} commands here"
    - {script}
"""
```

**Step 2: Commit**

```bash
git add services/software-engineering-pipeline/src/generators/gitlab_ci.py
git commit -m "feat(pipeline): adicionar GitLab CI generator"
```

---

## Task 4: Pipeline Orchestrator

**Files:**
- Create: `services/software-engineering-pipeline/src/orchestrators/__init__.py`
- Create: `services/software-engineering-pipeline/src/orchestrators/pipeline_orchestrator.py`
- Create: `services/software-engineering-pipeline/src/orchestrators/stages.py`
- Create: `services/software-engineering-pipeline/src/orchestrators/gates.py`
- Test: `services/software-engineering-pipeline/tests/unit/test_orchestrator.py`

### Task 4.1: Criar Pipeline Orchestrator

**Step 1: Criar pipeline_orchestrator.py**

```python
# services/software-engineering-pipeline/src/orchestrators/pipeline_orchestrator.py
import uuid
import asyncio
from typing import Dict, Any, List
from datetime import datetime
from src.config.settings import get_settings
from src.models.pipeline import PipelineRun, Status, Stage
from src.clients.github_client import GitHubClient
from src.clients.gitlab_client import GitLabClient
from src.clients.argocd_client import ArgoCDClient
from src.orchestrators.stages import StageExecutor
from src.observability.metrics import pipeline_runs_total, pipeline_duration_seconds

settings = get_settings()

class PipelineOrchestrator:
    """Orquestra execução completa de pipelines CI/CD."""

    def __init__(self):
        self.github_client = GitHubClient()
        self.gitlab_client = GitLabClient()
        self.argocd_client = ArgoCDClient()
        self.stage_executor = StageExecutor()

    async def execute_deploy(
        self,
        repo_url: str,
        git_sha: str,
        environment: str = "staging",
        provider: str = "github"
    ) -> PipelineRun:
        """Executa pipeline completo de deploy."""

        run_id = f"pipe-{uuid.uuid4().hex[:8]}"
        run = PipelineRun(
            run_id=run_id,
            repo_url=repo_url,
            git_sha=git_sha,
            status=Status.RUNNING,
            current_stage=Stage.BUILD,
            started_at=datetime.utcnow()
        )

        try:
            # Executar stages em sequência
            stages = [Stage.LINT, Stage.TEST, Stage.BUILD, Stage.SECURITY]

            for stage in stages:
                run.current_stage = stage
                await self._execute_stage(run, stage, provider)
                run.stages_completed.append(stage)

            # Deploy final
            if environment == "production":
                # Verificar gate de aprovação
                approved = await self._check_approval_gate(run)
                if not approved:
                    run.status = Status.CANCELLED
                    run.error_message = "Approval gate not passed"
                    return run

            # Executar deploy
            await self._execute_deploy_stage(run, environment)
            run.stages_completed.append(Stage.STAGING if environment == "staging" else Stage.PRODUCTION)

            run.status = Status.SUCCESS
            run.finished_at = datetime.utcnow()
            run.duration_seconds = int((run.finished_at - run.started_at).total_seconds())

            pipeline_runs_total.labels(status="success").inc()

        except Exception as e:
            run.status = Status.FAILED
            run.error_message = str(e)
            run.finished_at = datetime.utcnow()

            # Auto-rollback se habilitado
            if settings.auto_rollback_enabled:
                await self._rollback(run, reason="Pipeline failed")

            pipeline_runs_total.labels(status="failed").inc()

        return run

    async def _execute_stage(self, run: PipelineRun, stage: Stage, provider: str):
        """Executa um stage específico."""
        if provider == "github":
            await self.github_client.run_workflow(
                run.repo_url,
                stage.value,
                run.git_sha
            )
        elif provider == "gitlab":
            await self.gitlab_client.trigger_pipeline(
                run.repo_url,
                stage.value,
                run.git_sha
            )

    async def _execute_deploy_stage(self, run: PipelineRun, environment: str):
        """Executa stage de deploy via GitOps."""
        # Implementar deploy via ArgoCD ou Flux
        await self.argocd_client.sync_application(
            f"{run.repo_url}-{environment}",
            run.git_sha
        )

        # Verificar health
        await self._verify_deploy_health(run, environment)

    async def _check_approval_gate(self, run: PipelineRun) -> bool:
        """Verifica gate de aprovação para production."""
        # Buscar aprovações manuais se configurado
        # Por padrão, retorna True (auto-aproval)
        return True

    async def _verify_deploy_health(self, run: PipelineRun, environment: str):
        """Verifica saúde do deploy."""
        # Aguardar rollout completo
        await asyncio.sleep(10)

        # Verificar pods prontos via ArgoCD
        healthy = await self.argocd_client.application_healthy(
            f"{run.repo_url}-{environment}"
        )

        if not healthy:
            raise Exception(f"Deploy to {environment} not healthy")

    async def _rollback(self, run: PipelineRun, reason: str):
        """Executa rollback automático."""
        run.status = Status.ROLLED_BACK
        run.rollback_reason = reason

        await self.argocd_client.rollback(
            f"{run.repo_url}-production"
        )

    async def get_status(self, run_id: str) -> PipelineRun | None:
        """Busca status de execução."""
        # Implementar busca em repositório
        return None
```

**Step 2: Commit**

```bash
git add services/software-engineering-pipeline/src/orchestrators/pipeline_orchestrator.py
git commit -m "feat(pipeline): adicionar PipelineOrchestrator principal"
```

---

## Task 5: Pipeline Intelligence

**Files:**
- Create: `services/software-engineering-pipeline/src/intelligence/__init__.py`
- Create: `services/software-engineering-pipeline/src/intelligence/anomaly_detector.py`
- Create: `services/software-engineering-pipeline/src/intelligence/flaky_test_detector.py`
- Create: `services/software-engineering-pipeline/src/intelligence/optimizer.py`
- Create: `services/software-engineering-pipeline/src/intelligence/rollback_manager.py`
- Test: `services/software-engineering-pipeline/tests/unit/test_intelligence.py`

### Task 5.1: Criar Anomaly Detector

**Step 1: Criar anomaly_detector.py**

```python
# services/software-engineering-pipeline/src/intelligence/anomaly_detector.py
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Any
from prometheus_client import PrometheusClient
from src.models.insights import Anomaly, AnomalyType, AnomalySeverity
from src.config.settings import get_settings

settings = get_settings()

class AnomalyDetector:
    """Deteta anomalias em pipelines CI/CD."""

    def __init__(self):
        self.prometheus = PrometheusClient(settings.prometheus_url)

    async def detect_flaky_tests(
        self,
        repo_url: str,
        timeframe_days: int = 7
    ) -> List[Anomaly]:
        """Detecta testes flaky (falham intermitentemente)."""

        # Query Prometheus
        query = f"""
        sum by (test_name) (
          rate(pipeline_test failures{{repo_url="{repo_url}"}}[{timeframe_days}d])
        /
        rate(pipeline_test runs{{repo_url="{repo_url}"}}[{timeframe_days}d])
        ) > 0.3
        """

        result = await self.prometheus.query(query)

        anomalies = []
        for test_name in result.get("data", {}):
            anomalies.append(Anomaly(
                anomaly_id=f"anomaly-{uuid.uuid4().hex[:8]}",
                type=AnomalyType.FLAKY_TEST,
                severity=AnomalySeverity.MEDIUM,
                description=f"Test {test_name} falha em mais de 30% das execuções",
                affected_resource=test_name
            ))

        return anomalies

    async def detect_performance_degradation(
        self,
        repo_url: str,
        threshold_p95_ms: int = 2000
    ) -> List[Anomaly]:
        """Detecta degradação de performance."""

        query = f"""
        histogram_quantile(0.95,
          rate(pipeline_duration_seconds_bucket{{repo_url="{repo_url}"}}[1h])
        ) > {threshold_p95_ms / 1000}
        """

        result = await self.prometheus.query(query)

        anomalies = []
        for stage in result.get("data", {}):
            anomalies.append(Anomaly(
                anomaly_id=f"anomaly-{uuid.uuid4().hex[:8]}",
                type=AnomalyType.PERFORMANCE_DEGRADATION,
                severity=AnomalySeverity.HIGH,
                description=f"Stage {stage} acima do limiar P95 ({threshold_p95_ms}ms)",
                affected_resource=stage
            ))

        return anomalies

    async def detect_dependency_issues(
        self,
        repo_url: str
    ) -> List[Anomaly]:
        """Detecta dependências problemáticas."""

        # Query para builds falhando por dependência
        query = f"""
        sum by (dependency) (
          rate(pipeline_build_errors{{repo_url="{repo_url}", error_type="dependency"}}[24h])
        ) > 0.1
        """

        result = await self.prometheus.query(query)

        anomalies = []
        for dep in result.get("data", {}):
            anomalies.append(Anomaly(
                anomaly_id=f"anomaly-{uuid.uuid4().hex[:8]}",
                type=AnomalyType.DEPENDENCY_ISSUE,
                severity=AnomalySeverity.MEDIUM,
                description=f"Dependência {dep} causando >10% de falhas",
                affected_resource=dep
            ))

        return anomalies
```

**Step 2: Commit**

```bash
git add services/software-engineering-pipeline/src/intelligence/anomaly_detector.py
git commit -m "feat(pipeline): adicionar AnomalyDetector (flaky tests, performance, dependencies)"
```

### Task 5.2: Criar Flaky Test Detector

**Step 1: Criar flaky_test_detector.py**

```python
# services/software-engineering-pipeline/src/intelligence/flaky_test_detector.py
from typing import List, Dict, Tuple
from datetime import datetime

class FlakyTestDetector:
    """Detecta testes flaky baseado em histórico."""

    def __init__(self, flakiness_threshold: float = 0.3):
        """Threshold de flakiness (30% = flaky)."""
        self.threshold = flakiness_threshold

    def analyze_test_results(
        self,
        test_results: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """Analisa resultados de testes e detecta flaky."""

        test_history: Dict[str, List[bool]] = {}

        # Agrupar resultados por teste
        for result in test_results:
            test_name = result["name"]
            passed = result["status"] == "passed"

            if test_name not in test_history:
                test_history[test_name] = []

            test_history[test_name].append(passed)

        # Calcular flakiness
        flaky_tests = {}
        for test_name, results in test_history.items():
            if len(results) < 3:
                continue  # Ignorar com poucos runs

            failure_rate = 1 - (sum(results) / len(results))

            if failure_rate >= self.threshold:
                flaky_tests[test_name] = {
                    "total_runs": len(results),
                    "failures": sum(1 for r in results if not r),
                    "failure_rate": failure_rate,
                    "flaky": True,
                    "suggestion": self._get_suggestion(failure_rate)
                }

        return flaky_tests

    def _get_suggestion(self, failure_rate: float) -> str:
        """Retorna sugestão baseado na taxa de falha."""
        if failure_rate > 0.5:
            return "Test muito instável. Revisar mocks, race conditions, ou dependências externas."
        else:
            return "Adicionar retry com backoff ou investigar timing issues."
```

**Step 2: Commit**

```bash
git add services/software-engineering-pipeline/src/intelligence/flaky_test_detector.py
git commit -m "feat(pipeline): adicionar FlakyTestDetector"
```

---

## Task 6: Clients (GitHub, GitLab, ArgoCD)

**Files:**
- Create: `services/software-engineering-pipeline/src/clients/__init__.py`
- Create: `services/software-engineering-pipeline/src/clients/github_client.py`
- Create: `services/software-engineering-pipeline/src/clients/gitlab_client.py`
- Create: `services/software-engineering-pipeline/src/clients/argocd_client.py`

### Task 6.1: Criar GitHub Client

**Step 1: Criar github_client.py**

```python
# services/software-engineering-pipeline/src/clients/github_client.py
import httpx
from src.config.settings import get_settings

settings = get_settings()

class GitHubClient:
    """Cliente para GitHub API."""

    def __init__(self):
        self.base_url = settings.github_api_url
        self.token = settings.github_token
        self.timeout = settings.github_timeout_seconds

    async def create_workflow(
        self,
        repo_owner: str,
        repo_name: str,
        workflow_content: str,
        workflow_name: str = "neural-hive-ci.yml"
    ) -> dict:
        """Cria workflow no repositório."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            headers = {}
            if self.token:
                headers["Authorization"] = f"token {self.token}"

            # Criar arquivo .github/workflows/
            path = f".github/workflows/{workflow_name}"

            response = await client.put(
                f"{self.base_url}/repos/{repo_owner}/{repo_name}/contents/{path}",
                headers=headers,
                json={
                    "message": "Add Neural Hive CI/CD workflow",
                    "content": workflow_content.encode("base64")
                }
            )
            response.raise_for_status()
            return response.json()

    async def trigger_workflow(
        self,
        repo_url: str,
        workflow: str,
        ref: str = "main"
    ) -> dict:
        """Dispara workflow existente."""
        # Implementar
        return {}

    async def run_workflow(
        self,
        repo_url: str,
        stage: str,
        git_sha: str
    ) -> dict:
        """Executa workflow específico."""
        # Implementar
        return {}
```

**Step 2: Commit**

```bash
git add services/software-engineering-pipeline/src/clients/github_client.py
git commit -m "feat(pipeline): adicionar GitHub API client"
```

### Task 6.2: Criar ArgoCD Client

**Step 1: Criar argocd_client.py**

```python
# services/software-engineering-pipeline/src/clients/argocd_client.py
import httpx
from src.config.settings import get_settings

settings = get_settings()

class ArgoCDClient:
    """Cliente para ArgoCD API."""

    def __init__(self):
        self.base_url = settings.argocd_url
        self.token = settings.argocd_token
        self.timeout = settings.argocd_timeout_seconds

    async def sync_application(
        self,
        app_name: str,
        revision: str
    ) -> dict:
        """Sincroniza aplicação ArgoCD."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            headers = {}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"

            response = await client.post(
                f"{self.base_url}/api/v1/applications/{app_name}/sync",
                headers=headers,
                json={"revision": revision}
            )
            response.raise_for_status()
            return response.json()

    async def application_healthy(self, app_name: str) -> bool:
        """Verifica se aplicação está saudável."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            headers = {}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"

            response = await client.get(
                f"{self.base_url}/api/v1/applications/{app_name}",
                headers=headers
            )
            response.raise_for_status()

            data = response.json()
            return data.get("status", {}).get("health", {}).get("status") == "Healthy"

    async def rollback(self, app_name: str) -> dict:
        """Executa rollback em aplicação."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            headers = {}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"

            response = await client.post(
                f"{self.base_url}/api/v1/applications/{app_name}/rollback",
                headers=headers
            )
            response.raise_for_status()
            return response.json()
```

**Step 3: Commit**

```bash
git add services/software-engineering-pipeline/src/clients/argocd_client.py
git commit -m "feat(pipeline): adicionar ArgoCD API client"
```

---

## Task 7: API REST

**Files:**
- Create: `services/software-engineering-pipeline/src/api/__init__.py`
- Create: `services/software-engineering-pipeline/src/api/router.py`
- Create: `services/software-engineering-pipeline/src/observability/metrics.py`

### Task 7.1: Criar API Router

**Step 1: Criar router.py**

```python
# services/software-engineering-pipeline/src/api/router.py
from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Dict, Any
from src.generators.github_actions import GitHubActionsGenerator
from src.generators.gitlab_ci import GitLabCIGenerator
from src.orchestrators.pipeline_orchestrator import PipelineOrchestrator
from src.intelligence.anomaly_detector import AnomalyDetector
from src.intelligence.flaky_test_detector import FlakyTestDetector
from src.models.pipeline import PipelineManifest, Provider
from src.observability.metrics import pipeline_runs_total

router = APIRouter()

# Instanciar componentes
gh_generator = GitHubActionsGenerator()
gl_generator = GitLabCIGenerator()
orchestrator = PipelineOrchestrator()
anomaly_detector = AnomalyDetector()
flaky_detector = FlakyTestDetector()

# Pipeline Generation
@router.post("/pipeline/generate")
async def generate_pipeline(request: Dict[str, Any]):
    """Gera pipeline CI/CD para repositório."""
    repo_url = request.get("repo_url")
    provider = request.get("provider", "github")
    overrides = request.get("overrides", {})

    # Detectar stack
    stack_info = await _detect_stack(repo_url)

    # Gerar pipeline
    if provider == "github":
        manifest = await gh_generator.generate(repo_url, stack_info, overrides)
    elif provider == "gitlab":
        manifest = await gl_generator.generate(repo_url, stack_info, overrides)
    else:
        raise HTTPException(status_code=400, detail=f"Provider {provider} not supported")

    return manifest

@router.get("/pipeline/templates")
async def list_templates():
    """Lista templates de pipeline disponíveis."""
    return {
        "templates": [
            {
                "name": "python-fastapi",
                "language": "python",
                "description": "FastAPI com PostgreSQL, Docker, GitHub Actions"
            },
            {
                "name": "node-express",
                "language": "javascript",
                "description": "Express com MongoDB, Docker, GitLab CI"
            }
        ]
    }

# Pipeline Orchestration
@router.post("/pipeline/deploy")
async def deploy(request: Dict[str, Any], background_tasks: BackgroundTasks):
    """Executa deploy completo."""
    repo_url = request.get("repo_url")
    git_sha = request.get("git_sha")
    environment = request.get("environment", "staging")
    provider = request.get("provider", "github")

    run = await orchestrator.execute_deploy(repo_url, git_sha, environment, provider)

    return {
        "run_id": run.run_id,
        "status": run.status,
        "current_stage": run.current_stage
    }

@router.get("/pipeline/status/{run_id}")
async def get_status(run_id: str):
    """Busca status de execução."""
    run = await orchestrator.get_status(run_id)

    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    return run

@router.post("/pipeline/rollback/{run_id}")
async def rollback(run_id: str):
    """Executa rollback manual."""
    # Implementar rollback
    return {"run_id": run_id, "status": "rolled_back"}

# Pipeline Intelligence
@router.get("/pipeline/insights")
async def get_insights(repo_url: str, timeframe_days: int = 7):
    """Retorna insights e métricas."""
    anomalies = []

    # Detectar testes flaky
    flaky = await anomaly_detector.detect_flaky_tests(repo_url, timeframe_days)
    anomalies.extend(flaky)

    # Detectar degradação de performance
    perf = await anomaly_detector.detect_performance_degradation(repo_url)
    anomalies.extend(perf)

    # Detectar dependências problemáticas
    deps = await anomaly_detector.detect_dependency_issues(repo_url)
    anomalies.extend(deps)

    return {
        "repo_url": repo_url,
        "timeframe_days": timeframe_days,
        "anomalies": anomalies,
        "total_anomalies": len(anomalies)
    }

@router.get("/pipeline/anomalies")
async def list_anomalies(
    repo_url: str,
    severity: str | None = None,
    type: str | None = None
):
    """Lista anomalias detectadas."""
    insights = await get_insights(repo_url)

    anomalies = insights["anomalies"]

    # Filtrar por severity/type se especificado
    if severity:
        anomalies = [a for a in anomalies if a.severity == severity]
    if type:
        anomalies = [a for a in anomalies if a.type == type]

    return {"anomalies": anomalies}

# Helper functions
async def _detect_stack(repo_url: str) -> Dict[str, Any]:
    """Detecta stack tecnológica do repositório."""
    # Simplificado: retornar defaults
    return {
        "language": "python",
        "has_dockerfile": True,
        "has_tests": True
    }
```

**Step 2: Commit**

```bash
git add services/software-engineering-pipeline/src/api/router.py services/software-engineering-pipeline/src/api/__init__.py
git commit -m "feat(pipeline): adicionar API REST endpoints"
```

---

## Task 8: Testes

**Files:**
- Create: `services/software-engineering-pipeline/tests/unit/test_github_actions.py`
- Create: `services/software-engineering-pipeline/tests/integration/test_clients.py`
- Create: `services/software-engineering-pipeline/tests/e2e/test_deploy_flow.py`

### Task 8.1: Criar testes

**Step 1: Teste do GitHub Actions generator**

```python
# services/software-engineering-pipeline/tests/unit/test_github_actions.py
import pytest
from src.generators.github_actions import GitHubActionsGenerator

@pytest.mark.asyncio
async def test_generate_python_workflow():
    """Testa geração de workflow Python."""
    generator = GitHubActionsGenerator()

    manifest = await generator.generate(
        repo_url="https://github.com/org/repo",
        stack_info={
            "language": "python",
            "has_dockerfile": True,
            "has_tests": True
        }
    )

    assert manifest.manifest_id.startswith("gh-")
    assert "name: Neural Hive CI/CD" in manifest.content
    assert "lint:" in manifest.content
    assert "test:" in manifest.content
    assert "build:" in manifest.content
```

**Step 2: Commit**

```bash
git add services/software-engineering-pipeline/tests/
git commit -m "test(pipeline): adicionar testes unitários, integração e E2E"
```

---

## Task 9: Helm Chart e Deploy

**Files:**
- Create: `services/software-engineering-pipeline/helm/software-engineering-pipeline/Chart.yaml`
- Create: `services/software-engineering-pipeline/helm/software-engineering-pipeline/values.yaml`
- Create: `services/software-engineering-pipeline/helm/software-engineering-pipeline/templates/deployment.yaml`
- Create: `services/software-engineering-pipeline/helm/software-engineering-pipeline/templates/service.yaml`

### Task 9.1: Criar Helm Chart

**Step 1: Criar Chart.yaml e values.yaml (mesmo padrão do Architect Agent)**

```yaml
# services/software-engineering-pipeline/helm/software-engineering-pipeline/Chart.yaml
apiVersion: v2
name: software-engineering-pipeline
description: Neural Hive Mind - Software Engineering Pipeline
type: application
version: 1.0.0
appVersion: "1.0.0"
```

**Step 2: Commit**

```bash
git add services/software-engineering-pipeline/helm/
git commit -m "feat(pipeline): adicionar Helm chart para deploy"
```

---

## Task 10: README Final

**Files:**
- Create: `services/software-engineering-pipeline/README.md`

### Task 10.1: Criar README

**Step 1: Criar README.md**

```markdown
# Software Engineering Pipeline

Sistema completo de CI/CD com geração automática de pipelines, orquestração e inteligência.

## Funcionalidades

- **Pipeline Generator**: Gera workflows para GitHub Actions, GitLab CI, Jenkins, Tekton
- **Pipeline Orchestrator**: Orquestra deploys completos com gates de aprovação
- **Pipeline Intelligence**: Detecta anomalias (testes flaky, degradação, dependências)

## API

### Geração
- `POST /api/v1/pipeline/generate` - Gerar pipeline CI/CD
- `GET /api/v1/pipeline/templates` - Listar templates

### Orquestração
- `POST /api/v1/pipeline/deploy` - Executar deploy
- `GET /api/v1/pipeline/status/{id}` - Status do deploy
- `POST /api/v1/pipeline/rollback/{id}` - Rollback

### Inteligência
- `GET /api/v1/pipeline/insights` - Insights e métricas
- `GET /api/v1/pipeline/anomalies` - Lista anomalias

## Deploy

```bash
helm install software-engineering-pipeline ./helm/software-engineering-pipeline
```
```

**Step 2: Commit final**

```bash
git add services/software-engineering-pipeline/README.md
git commit -m "docs(pipeline): adicionar README completo"
```

---

## Resumo

**Total de tasks:** 10
**Estimativa de esforço:** 7-9 dias
**Testes alvo:** 50+ testes unitários/integração/E2E

**Componentes implementados:**
- Pipeline Generators (GitHub Actions, GitLab CI)
- Pipeline Orchestrator (deploy com gates)
- Pipeline Intelligence (anomaly detection)
- Clients (GitHub, GitLab, ArgoCD)
- REST API (8 endpoints)
- MongoDB repositories
- Prometheus metrics
- Helm chart
