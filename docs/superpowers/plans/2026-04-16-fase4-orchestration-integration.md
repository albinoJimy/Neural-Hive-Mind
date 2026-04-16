# Fase 4: Orchestration Integration - Plano de Implementação (Remaining 25%)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Completar integração dos serviços de engenharia Fluxo G no service registry e orchestrator, permitindo descoberta e orquestração dinâmica.

**Architecture:** Cada serviço se registra no startup via EngineeringServiceRegistryClient (gRPC), envia heartbeats periódicos, e pode ser descoberto pelo orchestrator-dynamic via ServiceRegistryClient.

**Tech Stack:** Python 3.12+, FastAPI, gRPC, Structlog, asyncio

---

## Contexto Já Implementado (75% completo)

- ✅ AgentType estendido com 5 novos tipos (REQUIREMENTS_ENGINEERING=5, DOCUMENTATION_GENERATION=6, KNOWLEDGE_GRAPH_RAG=7, APPROVAL_GATEWAY=8, ARCHITECT_AGENT=9)
- ✅ EngineeringServiceRegistryClient criado com 17 testes passando
- ✅ ServiceRegistryClient no orchestrator atualizado com type_map (5-9)
- ✅ Proto regenerado (service_registry_pb2.py)

## Serviços a Integrar (Remaining 25%)

| Serviço | Porta | AgentType | Capabilidades |
|---------|-------|-----------|---------------|
| requirements-engineering | 8010 | REQUIREMENTS_ENGINEERING (5) | requirements_generation, user_stories, acceptance_criteria, data_model_design |
| documentation-generation | 8014 | DOCUMENTATION_GENERATION (6) | readme_generation, api_docs, markdown_generation, mermaid_rendering |
| knowledge-graph-rag | 8016 | KNOWLEDGE_GRAPH_RAG (7) | rag_query, contextual_retrieval, template_indexing, code_indexing |
| approval-gateway | 8017 | APPROVAL_GATEWAY (8) | approval_management, artifact_storage, jwt_tokens, notifications |

---

### Task 1: Integrar Service Registry no requirements-engineering (8010)

**Files:**
- Modify: `services/requirements-engineering/src/main.py`
- Test: `services/requirements-engineering/tests/integration/test_service_registry_integration.py` (NOVO)

**Contexto:**
- O serviço requirements-engineering já tem FastAPI app em `src/main.py`
- Precisa adicionar lifespan handler para registro/deregistro
- Porta: 8010
- AgentType: REQUIREMENTS_ENGINEERING (5)

- [ ] **Step 1: Adicionar import do EngineeringServiceRegistryClient**

```python
# Adicionar no topo do main.py
from src.clients.engineering_service_registry_client import (
    EngineeringServiceRegistryClient,
)
from src.proto import service_registry_pb2
```

- [ ] **Step 2: Criar lifespan handler com service registry**

```python
# Substituir o lifespan atual (se existir) ou criar novo
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    registry_client = None
    try:
        registry_client = EngineeringServiceRegistryClient(
            service_name="requirements-engineering",
            agent_type=service_registry_pb2.REQUIREMENTS_ENGINEERING,
        )

        if await registry_client.initialize():
            agent_id = await registry_client.register(
                capabilities=[
                    "requirements_generation",
                    "user_stories",
                    "acceptance_criteria",
                    "data_model_design",
                ],
                metadata={
                    "kafka_consumer": "cognitive_plan_consumer",
                    "kafka_producer": "requirements_producer",
                    "version": "1.0.0",
                },
            )

            if agent_id:
                logger.info(
                    "service_registered_successfully",
                    service="requirements-engineering",
                    agent_id=agent_id,
                    port=8010,
                )
                # Iniciar heartbeat a cada 30s
                await registry_client.start_heartbeat(interval_seconds=30)
                app.state.registry_client = registry_client
            else:
                logger.error("service_registration_failed", service="requirements-engineering")
        else:
            logger.error("service_registry_init_failed", service="requirements-engineering")

        yield

    finally:
        # Shutdown
        if registry_client:
            await registry_client.close()
            logger.info("service_deregistered", service="requirements-engineering")
```

- [ ] **Step 3: Atualizar FastAPI app para usar lifespan**

```python
# Se já existir app = FastAPI(...), adicionar lifespan=
app = FastAPI(
    title="Requirements Engineering Service",
    version="1.0.0",
    lifespan=lifespan,  # ADICIONAR ou ATUALIZAR esta linha
)
```

- [ ] **Step 4: Verificar se imports existem**

Verifique se o main.py já tem os imports necessários (asyncio, contextlib, logger). Adicione se faltar:

```python
import asyncio
from contextlib import asynccontextmanager
import structlog
```

- [ ] **Step 5: Criar teste de integração**

```python
# Criar arquivo: tests/integration/test_service_registry_integration.py
"""Testes de integração com service registry."""

import pytest
from src.proto import service_registry_pb2
from src.clients.engineering_service_registry_client import EngineeringServiceRegistryClient


@pytest.mark.asyncio
async def test_requirements_engineering_registration():
    """Testa registro do requirements-engineering no service registry."""
    client = EngineeringServiceRegistryClient(
        "requirements-engineering",
        service_registry_pb2.REQUIREMENTS_ENGINEERING,
    )

    initialized = await client.initialize()
    assert initialized is True

    agent_id = await client.register(
        capabilities=[
            "requirements_generation",
            "user_stories",
            "acceptance_criteria",
            "data_model_design",
        ]
    )
    assert agent_id is not None
    assert client._registered is True

    await client.close()
```

- [ ] **Step 6: Rodar testes localmente**

```bash
cd services/requirements-engineering
pytest tests/integration/test_service_registry_integration.py -v
```

Expected: PASS (se service registry estiver rodando)

- [ ] **Step 7: Commit**

```bash
git add services/requirements-engineering/src/main.py
git add services/requirements-engineering/tests/integration/test_service_registry_integration.py
git commit -m "feat(reg-eng): integrate service registry registration on startup"
```

---

### Task 2: Integrar Service Registry no documentation-generation (8014)

**Files:**
- Modify: `services/documentation-generation/src/main.py`
- Test: `services/documentation-generation/tests/integration/test_service_registry_integration.py` (NOVO)

**Contexto:**
- Porta: 8014
- AgentType: DOCUMENTATION_GENERATION (6)
- Já tem Kafka consumers/producers

- [ ] **Step 1: Adicionar imports do service registry**

```python
# Adicionar no topo do main.py
from src.clients.engineering_service_registry_client import (
    EngineeringServiceRegistryClient,
)
from src.proto import service_registry_pb2
import asyncio
from contextlib import asynccontextmanager
```

- [ ] **Step 2: Criar lifespan handler**

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    registry_client = None
    try:
        registry_client = EngineeringServiceRegistryClient(
            service_name="documentation-generation",
            agent_type=service_registry_pb2.DOCUMENTATION_GENERATION,
        )

        if await registry_client.initialize():
            agent_id = await registry_client.register(
                capabilities=[
                    "readme_generation",
                    "api_docs",
                    "markdown_generation",
                    "mermaid_rendering",
                    "architecture_docs",
                ],
                metadata={
                    "kafka_consumer": "architecture_plan_consumer",
                    "version": "1.0.0",
                },
            )

            if agent_id:
                logger.info(
                    "service_registered_successfully",
                    service="documentation-generation",
                    agent_id=agent_id,
                    port=8014,
                )
                await registry_client.start_heartbeat(interval_seconds=30)
                app.state.registry_client = registry_client
            else:
                logger.error("service_registration_failed", service="documentation-generation")

        yield

    finally:
        if registry_client:
            await registry_client.close()
            logger.info("service_deregistered", service="documentation-generation")
```

- [ ] **Step 3: Atualizar FastAPI app**

```python
app = FastAPI(
    title="Documentation Generation Service",
    version="1.0.0",
    lifespan=lifespan,
)
```

- [ ] **Step 4: Criar teste de integração**

```python
# Criar: tests/integration/test_service_registry_integration.py
@pytest.mark.asyncio
async def test_documentation_generation_registration():
    """Testa registro do documentation-generation no service registry."""
    client = EngineeringServiceRegistryClient(
        "documentation-generation",
        service_registry_pb2.DOCUMENTATION_GENERATION,
    )

    initialized = await client.initialize()
    assert initialized is True

    agent_id = await client.register(
        capabilities=[
            "readme_generation",
            "api_docs",
            "markdown_generation",
            "mermaid_rendering",
            "architecture_docs",
        ]
    )
    assert agent_id is not None

    await client.close()
```

- [ ] **Step 5: Commit**

```bash
git add services/documentation-generation/src/main.py
git add services/documentation-generation/tests/integration/test_service_registry_integration.py
git commit -m "feat(doc-gen): integrate service registry registration on startup"
```

---

### Task 3: Integrar Service Registry no knowledge-graph-rag (8016)

**Files:**
- Modify: `services/knowledge-graph-rag/src/main.py`
- Test: `services/knowledge-graph-rag/tests/integration/test_service_registry_integration.py` (NOVO)

**Contexto:**
- Porta: 8016
- AgentType: KNOWLEDGE_GRAPH_RAG (7)
- Usa Neo4j e Qdrant

- [ ] **Step 1: Adicionar imports do service registry**

```python
from src.clients.engineering_service_registry_client import (
    EngineeringServiceRegistryClient,
)
from src.proto import service_registry_pb2
import asyncio
from contextlib import asynccontextmanager
```

- [ ] **Step 2: Criar lifespan handler**

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    registry_client = None
    try:
        registry_client = EngineeringServiceRegistryClient(
            service_name="knowledge-graph-rag",
            agent_type=service_registry_pb2.KNOWLEDGE_GRAPH_RAG,
        )

        if await registry_client.initialize():
            agent_id = await registry_client.register(
                capabilities=[
                    "rag_query",
                    "contextual_retrieval",
                    "template_indexing",
                    "code_indexing",
                ],
                metadata={
                    "neo4j": "enabled",
                    "qdrant": "enabled",
                    "version": "1.0.0",
                },
            )

            if agent_id:
                logger.info(
                    "service_registered_successfully",
                    service="knowledge-graph-rag",
                    agent_id=agent_id,
                    port=8016,
                )
                await registry_client.start_heartbeat(interval_seconds=30)
                app.state.registry_client = registry_client
            else:
                logger.error("service_registration_failed", service="knowledge-graph-rag")

        yield

    finally:
        if registry_client:
            await registry_client.close()
            logger.info("service_deregistered", service="knowledge-graph-rag")
```

- [ ] **Step 3: Atualizar FastAPI app**

```python
app = FastAPI(
    title="Knowledge Graph RAG Service",
    version="1.0.0",
    lifespan=lifespan,
)
```

- [ ] **Step 4: Criar teste de integração**

```python
# Criar: tests/integration/test_service_registry_integration.py
@pytest.mark.asyncio
async def test_knowledge_graph_rag_registration():
    """Testa registro do knowledge-graph-rag no service registry."""
    client = EngineeringServiceRegistryClient(
        "knowledge-graph-rag",
        service_registry_pb2.KNOWLEDGE_GRAPH_RAG,
    )

    initialized = await client.initialize()
    assert initialized is True

    agent_id = await client.register(
        capabilities=[
            "rag_query",
            "contextual_retrieval",
            "template_indexing",
            "code_indexing",
        ]
    )
    assert agent_id is not None

    await client.close()
```

- [ ] **Step 5: Commit**

```bash
git add services/knowledge-graph-rag/src/main.py
git add services/knowledge-graph-rag/tests/integration/test_service_registry_integration.py
git commit -m "feat(kg-rag): integrate service registry registration on startup"
```

---

### Task 4: Integrar Service Registry no approval-gateway (8017)

**Files:**
- Modify: `services/approval-gateway/src/main.py`
- Test: `services/approval-gateway/tests/integration/test_service_registry_integration.py` (NOVO)

**Contexto:**
- Porta: 8017
- AgentType: APPROVAL_GATEWAY (8)
- Gerencia aprovações e artifacts

- [ ] **Step 1: Adicionar imports do service registry**

```python
from src.clients.engineering_service_registry_client import (
    EngineeringServiceRegistryClient,
)
from src.proto import service_registry_pb2
import asyncio
from contextlib import asynccontextmanager
```

- [ ] **Step 2: Criar lifespan handler**

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    registry_client = None
    try:
        registry_client = EngineeringServiceRegistryClient(
            service_name="approval-gateway",
            agent_type=service_registry_pb2.APPROVAL_GATEWAY,
        )

        if await registry_client.initialize():
            agent_id = await registry_client.register(
                capabilities=[
                    "approval_management",
                    "artifact_storage",
                    "jwt_tokens",
                    "notifications",
                ],
                metadata={
                    "mongodb": "enabled",
                    "jwt": "enabled",
                    "version": "1.0.0",
                },
            )

            if agent_id:
                logger.info(
                    "service_registered_successfully",
                    service="approval-gateway",
                    agent_id=agent_id,
                    port=8017,
                )
                await registry_client.start_heartbeat(interval_seconds=30)
                app.state.registry_client = registry_client
            else:
                logger.error("service_registration_failed", service="approval-gateway")

        yield

    finally:
        if registry_client:
            await registry_client.close()
            logger.info("service_deregistered", service="approval-gateway")
```

- [ ] **Step 3: Atualizar FastAPI app**

```python
app = FastAPI(
    title="Approval Gateway Service",
    version="1.0.0",
    lifespan=lifespan,
)
```

- [ ] **Step 4: Criar teste de integração**

```python
# Criar: tests/integration/test_service_registry_integration.py
@pytest.mark.asyncio
async def test_approval_gateway_registration():
    """Testa registro do approval-gateway no service registry."""
    client = EngineeringServiceRegistryClient(
        "approval-gateway",
        service_registry_pb2.APPROVAL_GATEWAY,
    )

    initialized = await client.initialize()
    assert initialized is True

    agent_id = await client.register(
        capabilities=[
            "approval_management",
            "artifact_storage",
            "jwt_tokens",
            "notifications",
        ]
    )
    assert agent_id is not None

    await client.close()
```

- [ ] **Step 5: Commit**

```bash
git add services/approval-gateway/src/main.py
git add services/approval-gateway/tests/integration/test_service_registry_integration.py
git commit -m "feat(approval-gw): integrate service registry registration on startup"
```

---

### Task 5: Testar descoberta de serviços via orchestrator

**Files:**
- Test: `services/orchestrator-dynamic/tests/integration/test_service_discovery.py` (NOVO)

**Contexto:**
- O orchestrator-dynamic já tem ServiceRegistryClient atualizado com type_map
- Precisa testar descoberta dos 4 novos tipos de serviços

- [ ] **Step 1: Criar teste de descoberta de serviços**

```python
# Criar: services/orchestrator-dynamic/tests/integration/test_service_discovery.py
"""Testes de descoberta de serviços Fluxo G."""

import pytest
from src.clients.service_registry_client import ServiceRegistryClient


@pytest.mark.asyncio
async def test_discover_requirements_engineering():
    """Testa descoberta do serviço requirements-engineering."""
    client = ServiceRegistryClient()
    await client.initialize()

    # Descobrir agentes por tipo
    agents = await client.discover_agents(
        agent_type="REQUIREMENTS_ENGINEERING",
    )

    assert len(agents) > 0
    assert agents[0]["type"] == "REQUIREMENTS_ENGINEERING"
    assert "requirements_generation" in agents[0]["capabilities"]

    await client.close()


@pytest.mark.asyncio
async def test_discover_documentation_generation():
    """Testa descoberta do serviço documentation-generation."""
    client = ServiceRegistryClient()
    await client.initialize()

    agents = await client.discover_agents(
        agent_type="DOCUMENTATION_GENERATION",
    )

    assert len(agents) > 0
    assert agents[0]["type"] == "DOCUMENTATION_GENERATION"
    assert "readme_generation" in agents[0]["capabilities"]

    await client.close()


@pytest.mark.asyncio
async def test_discover_knowledge_graph_rag():
    """Testa descoberta do serviço knowledge-graph-rag."""
    client = ServiceRegistryClient()
    await client.initialize()

    agents = await client.discover_agents(
        agent_type="KNOWLEDGE_GRAPH_RAG",
    )

    assert len(agents) > 0
    assert agents[0]["type"] == "KNOWLEDGE_GRAPH_RAG"
    assert "rag_query" in agents[0]["capabilities"]

    await client.close()


@pytest.mark.asyncio
async def test_discover_approval_gateway():
    """Testa descoberta do serviço approval-gateway."""
    client = ServiceRegistryClient()
    await client.initialize()

    agents = await client.discover_agents(
        agent_type="APPROVAL_GATEWAY",
    )

    assert len(agents) > 0
    assert agents[0]["type"] == "APPROVAL_GATEWAY"
    assert "approval_management" in agents[0]["capabilities"]

    await client.close()


@pytest.mark.asyncio
async def test_discover_all_engineering_services():
    """Testa descoberta de todos os serviços de engenharia."""
    client = ServiceRegistryClient()
    await client.initialize()

    # Descobrir todos sem filtro de tipo
    agents = await client.discover_agents()

    # Filtrar apenas serviços de engenharia
    engineering_types = {
        "REQUIREMENTS_ENGINEERING",
        "DOCUMENTATION_GENERATION",
        "KNOWLEDGE_GRAPH_RAG",
        "APPROVAL_GATEWAY",
    }

    engineering_agents = [
        a for a in agents if a.get("type") in engineering_types
    ]

    assert len(engineering_agents) >= 4  # Pelo menos 4 serviços

    await client.close()
```

- [ ] **Step 2: Commit**

```bash
git add services/orchestrator-dynamic/tests/integration/test_service_discovery.py
git commit -m "test(orchestrator): add service discovery integration tests"
```

---

### Task 6: Validar E2E e atualizar documentação

**Files:**
- Update: `docs/FASE_4_ORCHESTRATION_INTEGRATION_2026-04-16.md`
- Update: `docs/FLUXO_G_STATUS_2026-04_16.md`

- [ ] **Step 1: Atualizar FASE_4 com status 100%**

Adicionar seção de conclusão ao FASE_4_ORCHESTRATION_INTEGRATION_2026-04-16.md:

```markdown
## Conclusão (2026-04-16)

### Status: ✅ 100% Completo

### Serviços Integrados

Todos os 4 serviços de engenharia agora se registram automaticamente no startup:

| Serviço | Porta | AgentType | Capabilities |
|---------|-------|-----------|--------------|
| requirements-engineering | 8010 | REQUIREMENTS_ENGINEERING | 4 capabilities |
| documentation-generation | 8014 | DOCUMENTATION_GENERATION | 5 capabilities |
| knowledge-graph-rag | 8016 | KNOWLEDGE_GRAPH_RAG | 4 capabilities |
| approval-gateway | 8017 | APPROVAL_GATEWAY | 4 capabilities |

### Testes Implementados

- 4 testes de integração de registro (um por serviço)
- 5 testes de descoberta via orchestrator
- Total: 9 novos testes de integração

### Fluxo Validado

1. Serviço starta → registra-se no service registry
2. Service registry atribui agent_id
3. Serviço envia heartbeats a cada 30s
4. Orchestrator pode descobrir serviços via `discover_agents()`
5. Serviço deregistra-se no shutdown

### Próxima Fase

FASE 5: Testing & Hardening
- Testes E2E completos
- Testes de carga
- Monitoring dashboards
```

- [ ] **Step 2: Atualizar FLUXO_G_STATUS com Fase 4 100%**

Atualizar a seção Fase 4 no FLUXO_G_STATUS_2026-04_16.md:

```markdown
## Fase 4: Orchestration Integration ✅ 100%

**Objetivo:** Integrar novos serviços no fluxo orquestrado

**Progresso:**
- ✅ AgentType estendido com 5 novos tipos
- ✅ EngineeringServiceRegistryClient criado (60 testes)
- ✅ ServiceRegistryClient type_map atualizado
- ✅ requirements-engineering integrado (8010)
- ✅ documentation-generation integrado (8014)
- ✅ knowledge-graph-rag integrado (8016)
- ✅ approval-gateway integrado (8017)
- ✅ Testes de descoberta implementados

**Testes:** 69 testes totais (60 unit + 9 integração)
```

- [ ] **Step 3: Commit final da documentação**

```bash
git add docs/FASE_4_ORCHESTRATION_INTEGRATION_2026-04-16.md
git add docs/FLUXO_G_STATUS_2026-04_16.md
git commit -m "docs(fase4): update to 100% complete status"
```

- [ ] **Step 4: Push para o repositório**

```bash
git push origin feat/FASE4-ORCHESTRATION-INTEGRATION
```

---

## Métricas de Sucesso

Ao finalizar este plano:

- [ ] 4 serviços integrados com service registry
- [ ] 9 novos testes de integração criados
- [ ] Descoberta de serviços validada via orchestrator
- [ ] FASE 4 marcada como 100% completa
- [ ] Total de testes da Fase 4: 69 (60 existentes + 9 novos)
