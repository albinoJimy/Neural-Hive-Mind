# Context Layer: Análise Profunda e Design Completo

> **Data:** 2026-04-22
> **Status:** Análise Completa
> **Epic:** Context Layer para Neural Hive Mind

---

## Resumo Executivo

O Neural Hive Mind possui um **Memory Layer** funcional mas carece de um **Context Layer unificado** que:

1. **Orquestra inteligentemente** workflows baseado em contexto rico
2. **Rastreia causalidade** entre intenções, decisões e execuções
3. **Fornece contexto conversacional** para experiências contínuas
4. **Garante segurança** com PII masking, autorização contextual e auditoria
5. **Permite racionalidade** na tomada de decisões com inferência de intenção

---

## Parte 1: Estado Actual (Análise Profunda)

### 1.1 O Que Já Existe

#### Memory Layer API (`services/memory-layer-api/`)

**Capacidades Actuais:**
- 4 camadas de armazenamento: Redis (hot), MongoDB (warm), Neo4j (semantic), ClickHouse (cold)
- Roteamento automático baseado em `query_type` e `time_range`
- Sincronização em tempo real via Kafka
- Data quality monitoring
- Lineage tracking
- Retention policy management

**Modelos Existentes:**
```python
class MemoryQueryRequest(BaseModel):
    query_type: QueryType  # CONTEXT, SEMANTIC, HISTORICAL, LINEAGE, QUALITY
    entity_id: str
    time_range: Optional[tuple[datetime, datetime]]
    use_cache: bool = True
```

**Limitações Identificadas:**
1. **Query-focused only** - Não há construção proactiva de contexto
2. **No session management** - Sessões conversacionais não são rastreadas
3. **No system state** - Estado actual dos serviços não é mantido
4. **No decision history** - Histórico de decisões não é ligado causalmente
5. **No intent inference** - Detecção de ambiguidade ou inferência de intenção real

#### Modelos de Domínio Existentes

**CognitivePlan** (`semantic-translation-engine`):
```python
class CognitivePlan(BaseModel):
    plan_id: str
    intent_id: str
    original_intent_text: str | None  # ← Adicionado recentemente
    correlation_id: str | None
    trace_id: str | None
    tasks: list[TaskNode]
    risk_score: float
    requires_approval: bool
    is_destructive: bool
    # ...
```

**ConsolidatedDecision** (`consensus-engine`):
```python
class ConsolidatedDecision(BaseModel):
    decision_id: str
    plan_id: str
    intent_id: str
    correlation_id: Optional[str]
    final_decision: DecisionType
    specialist_votes: list[SpecialistVote]
    cognitive_plan: Optional[dict[str, Any]]
    # ...
```

**GAP Crítico Identificado:**
- Não há campo `flow_type` em CognitivePlan
- Decision consumer não roteia baseado em tipo de intenção
- Fluxo G existe mas nunca é executado

### 1.2 Fluxos Existentes

```
FLUXO A (Capture):
User → Gateway (NLU + PII) → IntentEnvelope → Kafka

FLUXO B (Planning):
IntentEnvelope → STE → CognitivePlan → Kafka

FLUXO Consenso:
CognitivePlan → Specialists → ConsensusEngine → ConsolidatedDecision → Kafka

FLUXO C (Orchestration) ← ÚNICO EXECUTADO:
ConsolidatedDecision → Orchestrator → OrchestrationWorkflow → Workers

FLUXO G (Generation) ← NUNCA EXECUTADO:
CognitivePlan → FluxoGWorkflow → Requirements → Docs → Knowledge → Approval
```

**Problema:** O `decision_consumer.py` linha 562-567 SEMPRE executa `OrchestrationWorkflow`.

---

## Parte 2: Definição de Contexto

### 2.1 O Que É Contexto?

**Contexto** é o conjunto de informações que cercam e dão significado a um evento ou decisão. No NHM, contexto inclui:

| Dimensão | Descrição | Exemplo |
|----------|-----------|---------|
| **Intent** | O que o usuário quer fazer | "Criar novo serviço de pagamentos" |
| **System** | Estado actual da plataforma | Serviços activos, portas em uso, topics Kafka |
| **Temporal** | Quando e sequência de eventos | Timestamp, workflow parent, causalidade |
| **Conversational** | Histórico da interacção | Sessão ID, intenções anteriores, entidades resolvidas |
| **Business** | Contexto de negócio | Sprint actual, tickets JIRA, SLA |
| **Decision** | Histórico de decisões | Decisões anteriores que afectam esta |
| **Security** | Autorização e auditoria | User ID, roles, PII detected |
| **Execution** | Estado de workflows activos | Tickets em execução, SAGA states |

### 2.2 Tipos de Contexto

```python
class ContextType(str, Enum):
    """Tipos de contexto no NHM"""
    INTENT = "intent"           # Contexto da intenção do usuário
    SYSTEM = "system"           # Estado actual do sistema
    TEMPORAL = "temporal"       # Quando e sequência
    CONVERSATIONAL = "conversational"  # Histórico da sessão
    BUSINESS = "business"       # Contexto de negócio
    DECISION = "decision"       # Histórico de decisões
    SECURITY = "security"       # Autorização e PII
    EXECUTION = "execution"     # Workflows activos
```

---

## Parte 3: Context Layer Architecture

### 3.1 Arquitectura Proposta

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        CONTEXT LAYER (NOVO)                                │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                    Context Manager Service                           │  │
│  │  Porta: 8010                                                          │  │
│  │  - context_builder.py    # Constrói contexto rico                    │  │
│  │  - context_router.py     # Roteamento inteligente                   │  │
│  │  - context_store.py      # Persistência (MongoDB + Redis)           │  │
│  │  - context_retriever.py  # Query contextual                         │  │
│  │  - context_inferencer.py # Inferência de intenção                   │  │
│  │  - pii_detector.py       # Detecção de PII                         │  │
│  │  - security_context.py   # Autorização contextual                   │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                       Context Dimensions                             │  │
│  │                                                                        │  │
│  │  ┌───────────────┐ ┌───────────────┐ ┌───────────────┐ ┌────────────┐ │  │
│  │  │ Intent        │ │ System        │ │ Temporal      │ │ Session    │ │  │
│  │  │ Context       │ │ Context       │ │ Context       │ │ Context    │ │  │
│  │  └───────────────┘ └───────────────┘ └───────────────┘ └────────────┘ │  │
│  │  ┌───────────────┐ ┌───────────────┐ ┌───────────────┐ ┌────────────┐ │  │
│  │  │ Business      │ │ Decision      │ │ Security      │ │ Execution  │ │  │
│  │  │ Context       │ │ Context       │ │ Context       │ │ Context    │ │  │
│  │  └───────────────┘ └───────────────┘ └───────────────┘ └────────────┘ │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                    Data Sources (Read)                               │  │
│  │  Service Registry │ Knowledge Graph │ Memory Layer │ State Store    │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                    Event Streams (Write)                             │  │
│  │  Kafka: context.events, context.queries, context.updates             │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        ▼                       ▼                       ▼
┌───────────────┐     ┌───────────────┐     ┌───────────────┐
│   Decision    │     │   Analyst     │     │     NLU       │
│   Consumer    │     │   Agents      │     │   Enhanced    │
│  (Router)     │     │ (Analysis)    │     │  (Context)    │
└───────────────┘     └───────────────┘     └───────────────┘
```

### 3.2 Ciclo de Vida do Contexto

```
1. CAPTURA (Fluxo A):
   IntentEnvelope → ContextManager.build_intent_context()
   - Detecta PII
   - Classifica tipo de intenção
   - Inicia/extrai sessão

2. ENRIQUECIMENTO (Fluxo B):
   CognitivePlan → ContextManager.enrich_context()
   - Adiciona contexto de sistema
   - Infere tipo de workflow (orchestration vs generation)
   - Calcula complexidade

3. DECISÃO (Fluxo Consenso):
   ConsolidatedDecision → ContextManager.add_decision_context()
   - Adiciona ao histórico de decisões
   - Rastreia causalidade

4. ROTEAMENTO (Fluxo C/G):
   ContextManager.route_workflow()
   - Decide workflow baseado em contexto rico
   - Verifica autorização

5. EXECUÇÃO (Fluxo C ou G):
   Workflow → ContextManager.update_execution_context()
   - Rastreia estado de execução
   - Atualiza SAGA states

6. FINALIZAÇÃO:
   Result → ContextManager.finalize_context()
   - Persiste contexto completo
   - Limpeza de dados sensíveis
```

---

## Parte 4: Modelos de Contexto

### 4.1 Modelo Unificado de Contexto

```python
# libraries/python/neural_hive_context/neural_hive_context/models/context.py

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field

class IntentType(str, Enum):
    """Tipo de intenção inferida"""
    QUERY = "query"           # Consultar dados
    TRANSFORM = "transform"   # Transformar dados
    VALIDATE = "validate"     # Validar algo
    GENERATE = "generate"     # Gerar novo software → Fluxo G
    ANALYZE = "analyze"       # Analisar sistema
    OPERATE = "operate"       # Operações CRUD
    UNKNOWN = "unknown"       # Requer clarificação

class WorkflowType(str, Enum):
    """Tipo de workflow a executar"""
    ORCHESTRATION = "orchestration"  # Fluxo C - modificar existente
    GENERATION = "generation"        # Fluxo G - criar novo

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
    estimated_complexity: Optional[str] = None  # low, medium, high, very_high

    # Análise de sentimento e urgência
    sentiment: Optional[str] = None  # positive, neutral, negative
    urgency: Optional[str] = None    # low, medium, high, critical

class SystemContext(BaseModel):
    """Contexto do estado actual do sistema"""
    active_services: list[str] = Field(default_factory=list)
    kafka_topics: list[str] = Field(default_factory=list)
    database_collections: list[str] = Field(default_factory=list)
    deployed_routes: dict[str, str] = Field(default_factory=dict)
    infrastructure_load: dict[str, float] = Field(default_factory=dict)

    # Estado de saúde
    service_health: dict[str, str] = Field(default_factory=dict)  # service -> status
    active_incidents: list[str] = Field(default_factory=list)

    # Métricas
    total_requests_per_second: float = 0.0
    error_rate: float = 0.0
    avg_latency_ms: float = 0.0

class TemporalContext(BaseModel):
    """Contexto temporal e causal"""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    correlation_id: str
    trace_id: Optional[str] = None
    span_id: Optional[str] = None

    # Causalidade
    parent_workflow_id: Optional[str] = None
    causality_chain: list[str] = Field(default_factory=list)
    root_intent_id: Optional[str] = None  # Intent original que iniciou a cadeia

    # Timing
    estimated_duration_ms: Optional[int] = None
    deadline_ms: Optional[int] = None

class ConversationalContext(BaseModel):
    """Contexto conversacional"""
    session_id: str
    turn_number: int = 1
    previous_intents: list[str] = Field(default_factory=list)
    resolved_entities: dict[str, Any] = Field(default_factory=dict)
    user_preferences: dict[str, Any] = Field(default_factory=dict)

    # Estado da conversa
    conversation_state: str = "active"  # active, paused, completed
    pending_clarifications: list[str] = Field(default_factory=list)

    # UserInfo
    user_id: Optional[str] = None
    user_locale: str = "pt-BR"
    user_timezone: str = "UTC"

class BusinessContext(BaseModel):
    """Contexto de negócio e domínio"""
    current_sprint: Optional[str] = None
    active_tickets: list[str] = Field(default_factory=list)
    business_rules: list[str] = Field(default_factory=list)
    sla_constraints: dict[str, Any] = Field(default_factory=dict)

    # Project info
    project_id: Optional[str] = None
    epic_id: Optional[str] = None
    team_context: dict[str, str] = Field(default_factory=dict)

class DecisionContext(BaseModel):
    """Contexto de decisões anteriores"""
    related_decisions: list[str] = Field(default_factory=list)  # decision_ids
    decision_pattern: Optional[str] = None
    approval_history: list[dict[str, Any]] = Field(default_factory=list)

    # Rationale
    reasoning_context: dict[str, Any] = Field(default_factory=dict)
    expert_opinions: dict[str, str] = Field(default_factory=dict)

class SecurityContext(BaseModel):
    """Contexto de segurança"""
    user_id: Optional[str] = None
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)

    # PII Detection
    pii_detected: bool = False
    pii_entities: list[str] = Field(default_factory=list)  # EMAIL, PHONE, SSN, etc.
    pii_masked: bool = False

    # Audit
    audit_log_id: Optional[str] = None
    compliance_checks: dict[str, bool] = Field(default_factory=dict)

class ExecutionContext(BaseModel):
    """Contexto de execução activa"""
    active_tickets: list[str] = Field(default_factory=list)
    saga_states: dict[str, str] = Field(default_factory=dict)
    workflow_status: dict[str, str] = Field(default_factory=dict)

    # Progress
    completion_percentage: float = 0.0
    current_step: Optional[str] = None
    remaining_steps: list[str] = Field(default_factory=list)

class RichContext(BaseModel):
    """Contexto rico unificado - O modelo principal do Context Layer"""

    # Identificação
    context_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    correlation_id: str
    intent_id: str

    # Dimensões de contexto
    intent: IntentContext
    system: SystemContext
    temporal: TemporalContext
    conversational: Optional[ConversationalContext] = None
    business: Optional[BusinessContext] = None
    decision: Optional[DecisionContext] = None
    security: SecurityContext
    execution: Optional[ExecutionContext] = None

    # Metadados para análise
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0)
    completeness_score: float = Field(default=0.0, ge=0.0, le=1.0)
    requires_approval: bool = False
    suggested_workflow: WorkflowType = WorkflowType.ORCHESTRATION

    # Routing
    routing_decision: Optional[str] = None  # "orchestration" ou "generation"
    routing_confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    valid_until: Optional[datetime] = None

    def calculate_completeness(self) -> float:
        """Calcula score de completude do contexto"""
        dimensions = [
            self.intent,
            self.system,
            self.temporal,
            self.conversational,
            self.business,
            self.decision,
            self.security,
            self.execution,
        ]
        present = sum(1 for d in dimensions if d is not None)
        return present / len(dimensions)
```

### 4.2 Extensão do CognitivePlan

```python
# services/semantic-translation-engine/src/models/cognitive_plan.py

class CognitivePlan(BaseModel):
    # ... campos existentes ...

    # NOVO: Campo para roteamento de workflow
    workflow_type: WorkflowType = Field(
        default=WorkflowType.ORCHESTRATION,
        description="Tipo de workflow a executar (orchestration ou generation)"
    )

    # NOVO: Contexto rico associado
    context_id: Optional[str] = Field(
        None,
        description="ID do contexto rico associado a este plano"
    )

    # NOVO: Confiança na classificação do tipo de workflow
    workflow_confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Confiança na classificação do tipo de workflow"
    )
```

---

## Parte 5: Serviços do Context Layer

### 5.1 Context Builder

```python
# services/context-manager/src/services/context_builder.py

class ContextBuilder:
    """Constrói contexto rico a partir de múltiplas fontes"""

    def __init__(
        self,
        service_registry_client,
        knowledge_graph_client,
        memory_layer_client,
        pii_detector,
    ):
        self.service_registry = service_registry_client
        self.knowledge_graph = knowledge_graph_client
        self.memory = memory_layer_client
        self.pii = pii_detector

    async def build_intent_context(
        self,
        intent_envelope: IntentEnvelope,
        session_id: Optional[str] = None,
    ) -> IntentContext:
        """Constrói contexto da intenção"""
        raw_text = intent_envelope.intent.get("text", "")

        # Detectar PII
        pii_entities = await self.pii.detect_pii(raw_text)

        # Classificar tipo de intenção
        intent_type = await self._classify_intent(raw_text)

        # Verificar se é greenfield
        is_greenfield = await self._is_greenfield_intent(raw_text, intent_type)

        return IntentContext(
            intent_type=intent_type,
            raw_intent=raw_text,
            normalized_intent=intent_envelope.normalized_intent,
            confidence_score=intent_envelope.confidence,
            is_ambiguous=intent_envelope.ambiguity_score > 0.5,
            requires_clarification=intent_envelope.ambiguity_score > 0.7,
            target_domain=intent_envelope.domain,
            is_greenfield=is_greenfield,
            estimated_complexity=await self._estimate_complexity(raw_text),
        )

    async def build_system_context(self) -> SystemContext:
        """Constrói contexto do sistema actual"""
        services = await self.service_registry.get_all_services()
        topics = await self.service_registry.get_kafka_topics()
        health = await self.service_registry.get_health_status()

        return SystemContext(
            active_services=[s.name for s in services],
            kafka_topics=topics,
            deployed_routes={
                route.path: route.service_id
                for s in services
                for route in s.routes
            },
            service_health={s.name: s.status for s in services},
            infrastructure_load=await self._get_infrastructure_load(),
        )

    async def build_temporal_context(
        self,
        correlation_id: str,
        parent_workflow_id: Optional[str] = None,
    ) -> TemporalContext:
        """Constrói contexto temporal"""
        # Buscar causal chain se parent existir
        causality_chain = []
        root_intent_id = None

        if parent_workflow_id:
            parent_context = await self.memory.query(
                query_type="context",
                entity_id=parent_workflow_id,
            )
            if parent_context:
                causality_chain = parent_context.get("causality_chain", [])
                causality_chain.append(parent_workflow_id)
                root_intent_id = parent_context.get("root_intent_id")

        return TemporalContext(
            correlation_id=correlation_id,
            trace_id=trace_id.get(),
            span_id=span_id.get(),
            parent_workflow_id=parent_workflow_id,
            causality_chain=causality_chain,
            root_intent_id=root_intent_id,
        )

    async def build_conversational_context(
        self,
        session_id: str,
        user_id: Optional[str] = None,
    ) -> ConversationalContext:
        """Constrói contexto conversacional"""
        # Buscar histórico da sessão
        session_history = await self.memory.query(
            query_type="historical",
            entity_id=f"session:{session_id}",
        )

        return ConversationalContext(
            session_id=session_id,
            turn_number=len(session_history.get("intents", [])) + 1,
            previous_intents=session_history.get("intents", []),
            resolved_entities=session_history.get("entities", {}),
            user_preferences=session_history.get("preferences", {}),
            user_id=user_id,
        )

    async def build_security_context(
        self,
        user_id: Optional[str] = None,
        raw_intent: str = "",
    ) -> SecurityContext:
        """Constrói contexto de segurança"""
        # Detectar PII
        pii_entities = await self.pii.detect_pii(raw_intent) if raw_intent else []

        # Buscar roles e permissões
        roles = []
        permissions = []
        if user_id:
            user_data = await self.memory.query(
                query_type="context",
                entity_id=f"user:{user_id}",
            )
            roles = user_data.get("roles", [])
            permissions = user_data.get("permissions", [])

        return SecurityContext(
            user_id=user_id,
            roles=roles,
            permissions=permissions,
            pii_detected=len(pii_entities) > 0,
            pii_entities=pii_entities,
            pii_masked=False,  # Será marcado True após masking
        )
```

### 5.2 Context Router

```python
# services/context-manager/src/services/context_router.py

class ContextRouter:
    """Roteamento inteligente baseado em contexto rico"""

    async def route_workflow(
        self,
        cognitive_plan: CognitivePlan,
        context: RichContext,
    ) -> tuple[WorkflowType, float, str]:
        """
        Decide qual workflow executar baseado em contexto.

        Returns:
            (workflow_type, confidence, reasoning)
        """
        # 1. Verificar indicação explícita no plano
        if cognitive_plan.workflow_type != WorkflowType.ORCHESTRATION:
            return (
                cognitive_plan.workflow_type,
                cognitive_plan.workflow_confidence,
                "Explicit workflow type in CognitivePlan",
            )

        # 2. Análise semântica da intenção
        intent_lower = context.intent.raw_intent.lower()
        generation_keywords = [
            "criar", "novo sistema", "desenvolver", "implementar",
            "greenfield", "do zero", "from scratch", "nova feature"
        ]
        operation_keywords = [
            "executar", "processar", "calcular", "consultar",
            "buscar", "listar", "atualizar", "deletar"
        ]

        gen_score = sum(1 for kw in generation_keywords if kw in intent_lower)
        op_score = sum(1 for kw in operation_keywords if kw in intent_lower)

        if gen_score > op_score:
            return (
                WorkflowType.GENERATION,
                0.7 + (gen_score * 0.05),
                f"Semantic analysis: {gen_score} generation keywords vs {op_score} operation keywords"
            )

        # 3. Verificar se domínio alvo existe
        if context.intent.target_domain:
            domain_exists = context.intent.target_domain in context.system.active_services
            if not domain_exists:
                return (
                    WorkflowType.GENERATION,
                    0.8,
                    f"Target domain '{context.intent.target_domain}' does not exist in system"
                )

        # 4. Verificar contexto conversacional
        if context.conversational:
            prev_intents = " ".join(context.conversational.previous_intents)
            if "sistema existente" in prev_intents or "já está" in prev_intents:
                return (
                    WorkflowType.ORCHESTRATION,
                    0.75,
                    "Conversational context indicates existing system operation"
                )

        # 5. Análise de complexidade
        if context.intent.estimated_complexity in ["high", "very_high"]:
            # Alta complexidade pode indicar criação de sistema novo
            return (
                WorkflowType.GENERATION,
                0.6,
                f"High complexity ({context.intent.estimated_complexity}) suggests system creation"
            )

        # 6. Verificar se há serviços afectados
        if not context.intent.affected_services:
            # Sem serviços afectados → provavelmente greenfield
            return (
                WorkflowType.GENERATION,
                0.65,
                "No affected services identified, suggests greenfield"
            )

        # Default: Orchestration (comportamento conservador)
        return (
            WorkflowType.ORCHESTRATION,
            0.5,
            "Default routing to orchestration (no strong signal for generation)"
        )
```

### 5.3 PII Detector

```python
# services/context-manager/src/services/pii_detector.py

class PIIDetector:
    """Detecção de Informação Pessoalmente Identificável"""

    PII_PATTERNS = {
        "EMAIL": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        "PHONE": r'\b(?:\+?(\d{1,3}))?[-. (]*(\d{3})[-. )]*(\d{3})[-. ]*(\d{4})(?: *x(\d+))?\b',
        "SSN": r'\b\d{3}-\d{2}-\d{4}\b',
        "CREDIT_CARD": r'\b(?:\d[ -]*?){13,16}\b',
        "IP_ADDRESS": r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b',
        "PASSPORT": r'\b[A-Z0-9<]{9}\b',
    }

    async def detect_pii(self, text: str) -> list[str]:
        """Detecta entidades PII no texto"""
        detected = []

        for entity_type, pattern in self.PII_PATTERNS.items():
            if re.search(pattern, text):
                detected.append(entity_type)

        return detected

    async def mask_pii(self, text: str, entities: list[str]) -> tuple[str, dict]:
        """
        Mascara entidades PII no texto.

        Returns:
            (masked_text, mapping) onde mapping contém {placeholder: original_value}
        """
        masked = text
        mapping = {}
        counter = 0

        for entity_type in entities:
            pattern = self.PII_PATTERNS[entity_type]
            matches = re.finditer(pattern, text)

            for match in matches:
                original = match.group()
                placeholder = f"[{entity_type}_{counter}]"
                masked = masked.replace(original, placeholder)
                mapping[placeholder] = original
                counter += 1

        return masked, mapping
```

---

## Parte 6: Integração com Fluxos Existentes

### 6.1 Modificação no Semantic Translation Engine

```python
# services/semantic-translation-engine/src/services/translation_orchestrator.py

class TranslationOrchestrator:
    def __init__(self):
        self.context_client = ContextManagerClient()

    async def translate(
        self,
        intent_envelope: IntentEnvelope,
    ) -> CognitivePlan:
        # ... lógica existente de tradução ...

        # NOVO: Consultar Context Manager para classificar workflow
        context = await self.context_client.build_context(
            intent_envelope=intent_envelope,
        )

        # Classificar tipo de workflow
        workflow_type, confidence, reasoning = await self.context_client.route_workflow(
            cognitive_plan=plan,
            context=context,
        )

        # Adicionar ao plano
        plan.workflow_type = workflow_type
        plan.workflow_confidence = confidence
        plan.context_id = context.context_id
        plan.metadata["workflow_routing_reasoning"] = reasoning

        return plan
```

### 6.2 Modificação no Decision Consumer

```python
# services/orchestrator-dynamic/src/consumers/decision_consumer.py

class DecisionConsumer:
    def __init__(self):
        self.context_client = ContextManagerClient()

    async def process_decision(self, decision: ConsolidatedDecision):
        # 1. Recuperar contexto enriquecido
        context_id = decision.cognitive_plan.get("context_id")
        context = await self.context_client.get_context(context_id)

        # 2. Recuperar workflow type do plano
        cognitive_plan = CognitivePlan(**decision.cognitive_plan)
        workflow_type = cognitive_plan.workflow_type

        # 3. Executar workflow correcto
        if workflow_type == WorkflowType.GENERATION:
            workflow_cls = FluxoGWorkflow
        else:
            workflow_cls = OrchestrationWorkflow

        await self.temporal_client.start_workflow(
            workflow_cls.run,
            {
                "cognitive_plan": cognitive_plan.dict(),
                "consolidated_decision": decision.dict(),
                "context": context.dict(),
            },
            id=context.temporal.correlation_id,
            task_queue=self.config.temporal_task_queue,
        )
```

---

## Parte 7: Segurança e Compliance

### 7.1 Autorização Contextual

```python
# services/context-manager/src/services/security_context.py

class SecurityContextManager:
    """Gestão de segurança baseada em contexto"""

    async def check_authorization(
        self,
        context: RichContext,
        required_permission: str,
    ) -> tuple[bool, str]:
        """
        Verifica autorização baseada em contexto rico.

        Returns:
            (authorized, reason)
        """
        user_id = context.security.user_id
        roles = context.security.roles
        permissions = context.security.permissions

        # 1. Verificar permissão explícita
        if required_permission in permissions:
            return True, "User has explicit permission"

        # 2. Verificar role-based
        admin_roles = ["admin", "superuser"]
        if any(role in roles for role in admin_roles):
            return True, "User has admin role"

        # 3. Verificar se é greenfield (requer permissão especial)
        if context.intent.is_greenfield:
            if "greenfield:create" not in permissions:
                return False, "Greenfield operations require special permission"

        # 4. Verificar se é operação destrutiva
        if context.execution and any(
            s in context.execution.current_step.lower()
            for s in ["delete", "drop", "truncate"]
        ):
            if "destructive:execute" not in permissions:
                return False, "Destructive operations require special permission"

        # 5. Verificar PII
        if context.security.pii_detected:
            if "pii:access" not in permissions:
                return False, "PII access requires special permission"

        return False, "User lacks required permission"
```

### 7.2 Auditoria

```python
# services/context-manager/src/services/audit_logger.py

class AuditLogger:
    """Registo de auditoria para decisões contextuais"""

    async def log_context_decision(
        self,
        context: RichContext,
        decision: str,
        reasoning: str,
    ):
        """Regista decisão baseada em contexto"""
        audit_entry = {
            "audit_id": str(uuid.uuid4()),
            "timestamp": datetime.utcnow(),
            "context_id": context.context_id,
            "correlation_id": context.temporal.correlation_id,
            "user_id": context.security.user_id,
            "decision": decision,
            "reasoning": reasoning,
            "intent_type": context.intent.intent_type,
            "workflow_type": context.suggested_workflow,
            "pii_detected": context.security.pii_detected,
            "routing_confidence": context.routing_confidence,
        }

        await self.mongodb.insert_one(
            collection="audit_context_decisions",
            document=audit_entry,
        )
```

---

## Parte 8: Implementação Faseada

### Fase 1: Foundation (1-2 semanas)
- Estrutura do serviço `context-manager`
- Modelos de domínio (`neural_hive_context`)
- Cliente gRPC para Context Manager

### Fase 2: Intent & System Context (2-3 semanas)
- IntentContext com classificação
- SystemContext com Service Registry integration
- PII Detector básico

### Fase 3: Routing Integration (1-2 semanas)
- Modificação em CognitivePlan
- Context Router
- Integração no Semantic Translation Engine

### Fase 4: Decision Consumer Fix (1 semana)
- Modificação no decision_consumer.py
- Roteamento para FluxoGWorkflow
- Testes E2E

### Fase 5: Conversational & Business Context (2 semanas)
- Session management
- Conversational context
- Business context integration

### Fase 6: Security & Audit (1-2 semanas)
- Security context
- Autorização contextual
- Audit logging

### Fase 7: Testing & Documentation (1 semana)
- Testes E2E completos
- Documentação de API
- Operações

**Total: 11-14 semanas**

---

## Parte 9: Critérios de Sucesso

- [ ] Contexto unificado disponível para todos os fluxos
- [ ] Roteamento automático entre Fluxo C e Fluxo G
- [ ] Detecção de PII com >95% de precisão
- [ ] Autorização contextual funcional
- [ ] Auditoria completa de decisões contextuais
- [ ] Session management para experiências conversacionais
- [ ] Latência de contexto < 100ms (p95)
- [ ] Testes E2E passando para todos os fluxos

---

## Parte 10: Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Context overhead alto | Média | Médio | Cache agressivo, lazy loading |
| PII false positives | Média | Alto | Threshold ajustável, whitelisting |
| Routing errors | Baixa | Alto | Fallback para Orchestration, audit trail |
| Session state explosion | Baixa | Médio | TTL agressivo, cleanup jobs |

---

## Próximos Passos

1. Criar spec detalhado em Agent OS
2. Criar branch `feat/context-layer`
3. Implementar Fase 1 (Foundation)
4. Iterar pelas fases seguintes
5. Integration testing com todos os fluxos

---

*Análise completa - 2026-04-22*
