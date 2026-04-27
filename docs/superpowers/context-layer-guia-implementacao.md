# Context Layer - Guia de Implementação Passo-a-Passo

> **Data:** 2026-04-23
> **Status:** Guia Executivo para Desenvolvedores
> **Documentação Relacionada:**
> - [Análise Técnica Profunda](./context-layer-analise-tecnica-profunda.md)
> - [Exemplos de Código Práticos](./context-layer-codigo-pratico.md)

---

## Resumo Executivo para Desenvolvedores

O Context Layer é um **componente crítico** que permite ao Neural Hive Mind:
1. **Diferenciar** intenções de geração (Fluxo G) vs. operação (Fluxo C)
2. **Orquestrar inteligentemente** workflows baseado em contexto rico
3. **Detectar e mascarar** PII para compliance
4. **Rastrear causalidade** entre intenções, decisões e execuções

Este guia fornece um **caminho claro e não-intrusivo** para implementar o Context Layer no codebase existente.

---

## Pré-requisitos

### Habilidades Necessárias
- ✅ Python 3.10+ (Pydantic, FastAPI, async/await)
- ✅ Familiaridade com gRPC (protobuf)
- ✅ Conhecimento de Docker e Kubernetes
- ✅ Experiência com MongoDB, Redis, Kafka

### Stack Técnica
- **Service:** FastAPI + gRPC (Python)
- **Database:** MongoDB (contextos) + Redis (cache)
- **Messaging:** Kafka (eventos de contexto)
- **Observability:** OpenTelemetry (tracing)
- **Testing:** pytest + pytest-asyncio

---

## Passo 1: Criar Biblioteca neural_hive_context (Semana 1)

### 1.1 Criar Estrutura da Biblioteca

```bash
# Criar diretório
mkdir -p libraries/python/neural_hive_context/neural_hive_context
cd libraries/python/neural-Hive-Mind

# Criar estrutura
cd libraries/python/neural_hive_context/neural_hive_context
mkdir -p {models,client,exceptions}

# Criar arquivos de pacote
touch __init__.py
touch models/__init__.py
touch client/__init__.py
touch exceptions/__init__.py
```

### 1.2 Definir Modelos de Domínio

**Arquivo:** `libraries/python/neural_hive_context/neural_hive_context/models/context.py`

```python
from enum import Enum
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field

class WorkflowType(str, Enum):
    """Tipo de workflow a executar"""
    ORCHESTRATION = "orchestration"  # Fluxo C - modificar existente
    GENERATION = "generation"        # Fluxo G - criar novo

class IntentType(str, Enum):
    """Tipo de intenção inferida"""
    QUERY = "query"
    TRANSFORM = "transform"
    VALIDATE = "validate"
    GENERATE = "generate"
    ANALYZE = "analyze"
    OPERATE = "operate"
    UNKNOWN = "unknown"

class IntentContext(BaseModel):
    """Contexto da intenção do usuário"""
    intent_type: IntentType
    raw_intent: str
    normalized_intent: str
    confidence_score: float = Field(ge=0.0, le=1.0)
    is_ambiguous: bool = False
    requires_clarification: bool = False
    target_domain: Optional[str] = None
    affected_services: list[str] = Field(default_factory=list)
    is_greenfield: bool = False
    estimated_complexity: Optional[str] = None

class SystemContext(BaseModel):
    """Contexto do estado atual do sistema"""
    active_services: list[str] = Field(default_factory=list)
    kafka_topics: list[str] = Field(default_factory=list)
    database_collections: list[str] = Field(default_factory=list)
    deployed_routes: dict[str, str] = Field(default_factory=dict)
    infrastructure_load: dict[str, float] = Field(default_factory=dict)
    service_health: dict[str, str] = Field(default_factory=dict)
    active_incidents: list[str] = Field(default_factory=list)

class SecurityContext(BaseModel):
    """Contexto de segurança"""
    user_id: Optional[str] = None
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    pii_detected: bool = False
    pii_entities: list[str] = Field(default_factory=list)
    pii_masked: bool = False

class RichContext(BaseModel):
    """Contexto rico unificado - Modelo principal"""
    context_id: str
    correlation_id: str
    intent_id: str
    intent: IntentContext
    system: SystemContext
    security: SecurityContext
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0)
    suggested_workflow: WorkflowType = WorkflowType.ORCHESTRATION
    routing_decision: Optional[str] = None
    routing_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

### 1.3 Criar Cliente gRPC Básico

**Arquivo:** `libraries/python/neural_hive_context/neural_hive_context/client/context_manager_client.py`

```python
import grpc
from typing import Optional, Any
import structlog

from neural_hive_context.models.context import RichContext, WorkflowType

logger = structlog.get_logger(__name__)

class ContextManagerClient:
    """Cliente gRPC para Context Manager"""

    def __init__(self, host: str = "context-manager:50051"):
        self.host = host
        self.channel = None
        self.stub = None

    async def initialize(self):
        """Inicializa conexão gRPC"""
        try:
            self.channel = grpc.aio.insecure_channel(self.host)
            await self.channel.channel_ready()
            logger.info("Context Manager client initialized", host=self.host)
        except Exception as e:
            logger.error("Failed to initialize Context Manager client", error=str(e))
            raise

    async def close(self):
        """Fecha conexão"""
        if self.channel:
            await self.channel.close()

    async def get_context(self, context_id: str) -> Optional[RichContext]:
        """
        Busca contexto rico por ID

        Returns:
            RichContext ou None se não encontrado
        """
        try:
            # TODO: Implementar chamada gRPC real
            # Por agora, retorna mock
            logger.warning("Context Manager gRPC not implemented yet", context_id=context_id)
            return None
        except Exception as e:
            logger.error("Failed to get context", context_id=context_id, error=str(e))
            return None

    async def build_context(self, intent_envelope: Any, session_id: Optional[str] = None) -> Optional[RichContext]:
        """
        Constrói contexto rico a partir de Intent Envelope

        Returns:
            RichContext ou None em caso de erro
        """
        try:
            # TODO: Implementar chamada gRPC real
            logger.warning("Context Manager gRPC not implemented yet")
            return None
        except Exception as e:
            logger.error("Failed to build context", error=str(e))
            return None

    async def route_workflow(
        self,
        cognitive_plan: Any,
        context: RichContext,
    ) -> tuple[WorkflowType, float, str]:
        """
        Rotear workflow baseado em contexto

        Returns:
            (workflow_type, confidence, reasoning)
        """
        try:
            # TODO: Implementar chamada gRPC real
            logger.warning("Context Manager gRPC not implemented yet")
            return WorkflowType.ORCHESTRATION, 0.5, "Default (not implemented)"
        except Exception as e:
            logger.error("Failed to route workflow", error=str(e))
            return WorkflowType.ORCHESTRATION, 0.5, f"Error: {str(e)}"
```

### 1.4 Testar Biblioteca

**Arquivo:** `libraries/python/neural_hive_context/tests/test_models.py`

```python
import pytest
from datetime import datetime
from neural_hive_context.models.context import (
    RichContext,
    IntentContext,
    SystemContext,
    SecurityContext,
    WorkflowType,
    IntentType,
)

def test_intent_context():
    """Testa criação de IntentContext"""
    context = IntentContext(
        intent_type=IntentType.GENERATE,
        raw_intent="Criar novo sistema",
        normalized_intent="criar novo sistema",
        confidence_score=0.85,
        target_domain="payments",
        is_greenfield=True,
    )

    assert context.intent_type == IntentType.GENERATE
    assert context.is_greenfield is True
    assert context.target_domain == "payments"

def test_system_context():
    """Testa criação de SystemContext"""
    context = SystemContext(
        active_services=["service-1", "service-2"],
        kafka_topics=["topic-1", "topic-2"],
        service_health={"service-1": "healthy", "service-2": "healthy"},
    )

    assert len(context.active_services) == 2
    assert len(context.kafka_topics) == 2
    assert context.service_health["service-1"] == "healthy"

def test_security_context():
    """Testa criação de SecurityContext"""
    context = SecurityContext(
        user_id="user-123",
        roles=["admin", "user"],
        permissions=["read", "write"],
        pii_detected=True,
        pii_entities=["EMAIL", "PHONE"],
    )

    assert context.user_id == "user-123"
    assert "admin" in context.roles
    assert context.pii_detected is True
    assert "EMAIL" in context.pii_entities

def test_rich_context():
    """Testa criação de RichContext"""
    intent = IntentContext(
        intent_type=IntentType.GENERATE,
        raw_intent="Criar novo sistema",
        normalized_intent="criar novo sistema",
        confidence_score=0.85,
        is_greenfield=True,
    )

    system = SystemContext(
        active_services=[],
        service_health={},
    )

    security = SecurityContext(
        user_id="user-123",
        roles=["admin"],
        permissions=["write"],
    )

    context = RichContext(
        context_id="ctx-abc",
        correlation_id="corr-123",
        intent_id="intent-456",
        intent=intent,
        system=system,
        security=security,
        suggested_workflow=WorkflowType.GENERATION,
        routing_confidence=0.85,
    )

    assert context.context_id == "ctx-abc"
    assert context.suggested_workflow == WorkflowType.GENERATION
    assert context.routing_confidence == 0.85
```

---

## Passo 2: Modificar CognitivePlan (Semana 2)

### 2.1 Adicionar Campos ao Modelo

**Arquivo:** `services/semantic-translation-engine/src/models/cognitive_plan.py`

```python
from neural_hive_context.models.context import WorkflowType  # ✅ NOVO IMPORT

class CognitivePlan(BaseModel):
    # --- CAMPOS EXISTENTES (não modificar) ---
    plan_id: str
    intent_id: str
    correlation_id: str | None
    trace_id: str | None
    tasks: list[TaskNode]
    risk_score: float
    requires_approval: bool
    is_destructive: bool

    # --- NOVOS CAMPOS (NON-BREAKING COM DEFAULTS) ---
    workflow_type: WorkflowType = Field(
        default=WorkflowType.ORCHESTRATION,
        description="Tipo de workflow a executar (orchestration ou generation)"
    )
    context_id: Optional[str] = Field(
        None,
        description="ID do contexto rico associado a este plano"
    )
    workflow_confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Confiança na classificação do tipo de workflow"
    )
    workflow_reasoning: Optional[str] = Field(
        None,
        description="Justificativa para o tipo de workflow escolhido"
    )
```

### 2.2 Atualizar Schema Avro

**Arquivo:** `schemas/cognitive-plan/cognitive-plan.avsc`

```json
{
  "type": "record",
  "name": "CognitivePlan",
  "namespace": "neural.hive.cognitive",
  "fields": [
    {"name": "plan_id", "type": "string"},
    {"name": "intent_id", "type": "string"},
    {"name": "correlation_id", "type": ["null", "string"], "default": null},
    {"name": "trace_id", "type": ["null", "string"], "default": null},
    {"name": "tasks", "type": {"type": "array", "items": "TaskNode"}},
    {"name": "risk_score", "type": "double"},
    {"name": "requires_approval", "type": "boolean"},
    {"name": "is_destructive", "type": "boolean"},

    {"name": "workflowType", "type": ["null", {
      "type": "enum",
      "name": "WorkflowType",
      "symbols": ["ORCHESTRATION", "GENERATION"]
    }], "default": "ORCHESTRATION"},

    {"name": "contextId", "type": ["null", "string"], "default": null},
    {"name": "workflowConfidence", "type": ["null", "double"], "default": 0.5},
    {"name": "workflowReasoning", "type": ["null", "string"], "default": null}
  ]
}
```

### 2.3 Testar Modificações

```bash
# Testar compatibilidade
cd services/semantic-translation-engine
pytest tests/test_cognitive_plan.py -v

# Testar serialização Avro
pytest tests/test_avro_serialization.py -v
```

---

## Passo 3: Criar Service Context Manager (Semana 2-3)

### 3.1 Criar Estrutura do Serviço

```bash
# Criar diretório
mkdir -p services/context-manager/src/{api,services,models,clients}
cd services/context-manager/src

# Criar arquivos
touch __init__.py
touch main.py
touch requirements.txt
touch Dockerfile
```

### 3.2 Criar Aplicação FastAPI

**Arquivo:** `services/context-manager/src/main.py`

```python
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from src.api.routers import context_router
from src.clients.mongodb_client import MongoDBClient
from src.clients.redis_client import RedisClient
from src.config.settings import Settings

settings = Settings()
app = FastAPI(
    title="Context Manager API",
    description="Gerenciamento de contexto rico para Neural Hive-Mind",
    version="1.0.0",
)

# Include routers
app.include_router(context_router.router, prefix="/api/v1/context", tags=["context"])

@app.on_event("startup")
async def startup():
    """Inicializa clientes de banco de dados"""
    app.mongodb = MongoDBClient(settings.mongodb_uri, "neural_hive_context")
    await app.mongodb.initialize()

    app.redis = RedisClient(settings.redis_url)
    await app.redis.initialize()

@app.on_event("shutdown")
async def shutdown():
    """Fecha conexões"""
    await app.mongodb.close()
    await app.redis.close()

@app.get("/health")
async def health():
    """Health check"""
    return {"status": "healthy"}
```

### 3.3 Criar Router de Contexto

**Arquivo:** `services/context-manager/src/api/routers/context.py`

```python
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from neural_hive_context.models.context import RichContext

router = APIRouter()

@router.get("/{context_id}")
async def get_context(context_id: str) -> RichContext:
    """
    Busca contexto rico por ID

    Args:
        context_id: ID do contexto

    Returns:
        RichContext
    """
    # TODO: Implementar busca no MongoDB
    pass

@router.post("/")
async def create_context(context: RichContext) -> dict:
    """
    Cria novo contexto rico

    Args:
        context: RichContext a ser criado

    Returns:
        Dict com context_id criado
    """
    # TODO: Implementar criação no MongoDB
    pass
```

---

## Passo 4: Modificar Decision Consumer (Semana 3)

### 4.1 Atualizar Consumer para Roteamento

**Arquivo:** `services/orchestrator-dynamic/src/consumers/decision_consumer.py`

```python
from neural_hive_context.models.context import WorkflowType  # ✅ NOVO IMPORT
from neural_hive_context.client import ContextManagerClient  # ✅ NOVO IMPORT

class DecisionConsumer:
    def __init__(self, settings, temporal_client):
        self.settings = settings
        self.temporal = temporal_client

        # ✅ NOVO: Inicializar cliente do Context Manager
        self.context_client = ContextManagerClient(
            host=settings.context_manager_host
        )

    async def process_decision(self, decision: ConsolidatedDecision):
        """Processa decisão com roteamento inteligente"""
        # ✅ NOVO: Extrair CognitivePlan
        cognitive_plan = CognitivePlan(**decision.cognitive_plan)
        workflow_type = cognitive_plan.workflow_type

        logger.info(
            "Processing decision",
            decision_id=decision.decision_id,
            workflow_type=workflow_type,
        )

        # ✅ NOVO: Roteamento inteligente
        if workflow_type == WorkflowType.GENERATION:
            workflow_cls = FluxoGWorkflow
            logger.info(
                "Routing to Fluxo G (generation workflow)",
                decision_id=decision.decision_id,
            )
        else:
            workflow_cls = OrchestrationWorkflow
            logger.info(
                "Routing to Fluxo C (orchestration workflow)",
                decision_id=decision.decision_id,
            )

        # ✅ NOVO: Buscar contexto rico se disponível
        context_data = {}
        if cognitive_plan.context_id:
            try:
                context = await self.context_client.get_context(cognitive_plan.context_id)
                if context:
                    context_data = context.dict()
            except Exception as e:
                logger.warning(
                    "Failed to fetch context (continuing without)",
                    decision_id=decision.decision_id,
                    error=str(e),
                )

        # Executar workflow
        await self.temporal.start_workflow(
            workflow_cls.run,
            {
                "cognitive_plan": cognitive_plan.dict(),
                "consolidated_decision": decision.dict(),
                "context": context_data,
            },
            id=decision.decision_id,
            task_queue=self.settings.temporal_task_queue,
        )
```

---

## Passo 5: Implementar Context Router (Semana 4)

### 5.1 Criar Router

**Arquivo:** `services/context-manager/src/services/context_router.py`

```python
from typing import Tuple
from neural_hive_context.models.context import (
    RichContext,
    WorkflowType,
    CognitivePlan,
)

class ContextRouter:
    """Roteamento inteligente baseado em contexto rico"""

    GENERATION_KEYWORDS = [
        "criar", "novo sistema", "desenvolver", "implementar",
        "greenfield", "do zero", "from scratch", "nova feature",
    ]

    ORCHESTRATION_KEYWORDS = [
        "executar", "processar", "calcular", "consultar",
        "buscar", "listar", "atualizar", "deletar",
    ]

    async def route_workflow(
        self,
        cognitive_plan: CognitivePlan,
        context: RichContext,
    ) -> Tuple[WorkflowType, float, str]:
        """
        Decide qual workflow executar baseado em contexto

        Returns:
            (workflow_type, confidence, reasoning)
        """
        # 1. Verificar indicação explícita
        if cognitive_plan.workflow_type != WorkflowType.ORCHESTRATION:
            return (
                cognitive_plan.workflow_type,
                cognitive_plan.workflow_confidence or 0.7,
                cognitive_plan.workflow_reasoning or "Explicit workflow type",
            )

        # 2. Análise semântica
        workflow_type, confidence, reasoning = self._analyze_keywords(
            context.intent.raw_intent.lower()
        )

        # 3. Verificar se domínio existe
        if workflow_type == WorkflowType.ORCHESTRATION:
            if context.intent.target_domain not in context.system.active_services:
                confidence = max(confidence, 0.8)
                reasoning = f"Target domain '{context.intent.target_domain}' does not exist"
                workflow_type = WorkflowType.GENERATION

        # Default
        if workflow_type is None:
            workflow_type = WorkflowType.ORCHESTRATION
            confidence = 0.5
            reasoning = "Default routing to orchestration"

        return workflow_type, confidence, reasoning

    def _analyze_keywords(self, intent_lower: str) -> Tuple[WorkflowType, float, str]:
        """Analisa keywords para inferir tipo de workflow"""
        gen_score = sum(1 for kw in self.GENERATION_KEYWORDS if kw in intent_lower)
        op_score = sum(1 for kw in self.ORCHESTRATION_KEYWORDS if kw in intent_lower)

        if gen_score > op_score:
            confidence = 0.7 + (gen_score * 0.05)
            return WorkflowType.GENERATION, confidence, f"{gen_score} generation keywords vs {op_score} operation"
        elif op_score > gen_score:
            confidence = 0.7 + (op_score * 0.05)
            return WorkflowType.ORCHESTRATION, confidence, f"{op_score} operation keywords vs {gen_score} generation"
        else:
            return None, 0.0, "Keyword analysis inconclusive"
```

---

## Passo 6: Implementar PII Detector (Semana 5)

### 6.1 Criar Detector

**Arquivo:** `services/context-manager/src/services/pii_detector.py`

```python
import re
from typing import List, Tuple

class PIIDetector:
    """Detecção de Informação Pessoalmente Identificável"""

    PII_PATTERNS = {
        "EMAIL": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        "PHONE": r'\b(?:\+?(\d{1,3}))?[-. (]*(\d{3})[-. )]*(\d{3})[-. ]*(\d{4})(?: *x(\d+))?\b',
        "SSN": r'\b\d{3}-\d{2}-\d{4}\b',
    }

    def __init__(self):
        self.compiled_patterns = {
            entity_type: re.compile(pattern, re.IGNORECASE)
            for entity_type, pattern in self.PII_PATTERNS.items()
        }

    async def detect_pii(self, text: str) -> List[str]:
        """Detecta entidades PII no texto"""
        if not text:
            return []

        detected = []
        for entity_type, pattern in self.compiled_patterns.items():
            if pattern.search(text):
                detected.append(entity_type)

        return detected

    async def mask_pii(self, text: str, entities: List[str]) -> Tuple[str, dict]:
        """Mascara entidades PII no texto"""
        if not text or not entities:
            return text, {}

        masked = text
        mapping = {}
        counter = 0

        for entity_type in entities:
            if entity_type not in self.compiled_patterns:
                continue

            pattern = self.compiled_patterns[entity_type]
            matches = list(pattern.finditer(text))

            for match in reversed(matches):
                original = match.group()
                placeholder = f"[{entity_type}_{counter}]"
                masked = masked[:match.start()] + placeholder + masked[match.end():]
                mapping[placeholder] = original
                counter += 1

        return masked, mapping
```

---

## Passo 7: Testing & Deploy (Semana 6)

### 7.1 Testes E2E

```bash
# Testar biblioteca neural_hive_context
cd libraries/python/neural_hive_context
pytest tests/ -v

# Testar Context Manager
cd services/context-manager
pytest tests/ -v

# Testar integração Decision Consumer
cd services/orchestrator-dynamic
pytest tests/integration/test_decision_consumer.py -v
```

### 7.2 Deploy Local

```bash
# Build Docker images
make build-local

# Deploy services
make deploy-local

# Verificar health checks
kubectl get pods -n neural-hive
```

### 7.3 Deploy EKS

```bash
# Push para ECR
make push-ecr

# Deploy
make deploy-eks

# Monitorar logs
kubectl logs -f -n neural-hive context-manager-pod
```

---

## Checkpoint & Validação

### ✅ Critérios de Sucesso por Fase

| Fase | Critérios | Status |
|------|-----------|--------|
| **Fase 1** | Biblioteca neural_hive_context criada e testável | ⬜ |
| **Fase 2** | CognitivePlan com workflow_type (backward compatible) | ⬜ |
| **Fase 3** | Context Manager service starta com health check | ⬜ |
| **Fase 4** | Decision Consumer roteia para Fluxo G quando apropriado | ⬜ |
| **Fase 5** | Context Router classifica workflow_type com >70% precisão | ⬜ |
| **Fase 6** | PII Detector detecta EMAIL/PHONE com >95% precisão | ⬜ |
| **Fase 7** | Testes E2E passam para ambos os fluxos (C e G) | ⬜ |

---

## Troubleshooting Comum

### Problema: CognitivePlan não serializa para Avro

**Solução:**
```python
# Verificar que to_avro_dict() retorna campos novos
plan = CognitivePlan(...)
avro_dict = plan.to_avro_dict()
assert "workflowType" in avro_dict
assert avro_dict["workflowType"] in ["ORCHESTRATION", "GENERATION"]
```

### Problema: Decision Consumer sempre roteia para Orchestration

**Solução:**
```python
# Verificar que workflow_type está sendo extraído corretamente
cognitive_plan = CognitivePlan(**decision.cognitive_plan)
print(f"Workflow type: {cognitive_plan.workflow_type}")  # Deve ser GENERATION ou ORCHESTRATION

# Verificar logs
kubectl logs -n neural-hive orchestrator-dynamic-pod --tail=100 | grep "Routing to"
```

### Problema: Context Manager não responde

**Solução:**
```bash
# Verificar se pod está rodando
kubectl get pods -n neural-hive | grep context-manager

# Verificar logs
kubectl logs -n neural-hive context-manager-pod

# Verificar health check
kubectl exec -n neural-hive context-manager-pod -- curl http://localhost:8000/health
```

---

## Próximos Passos

Após completar os passos acima:

1. **Implementar System Context** (integrar com Service Registry)
2. **Implementar Conversational Context** (sessão e histórico)
3. **Implementar Decision Context** (histórico de decisões)
4. **Otimizar performance** (cache, lazy loading)
5. **Adicionar dashboards** (observabilidade do Context Layer)

---

## Referências

- [Análise Técnica Profunda](./context-layer-analise-tecnica-profunda.md)
- [Exemplos de Código Práticos](./context-layer-codigo-pratico.md)
- [Espec Original](./2026-04-22-context-layer-deep-analysis.md)

---

*Guia de Implementação - 2026-04-23*
