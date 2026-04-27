# Context Layer - Análise Técnica Profunda do Codebase

> **Data:** 2026-04-23
> **Status:** Análise Técnica Complementar
> **Contexto:** Aplicações Práticas ao Codebase Atual do NHM

---

## Resumo Executivo

Esta análise complementa o documento existente (`2026-04-22-context-layer-deep-analysis.md`) focando em **como aplicar o Context Layer de forma prática ao código existente do Neural Hive Mind**, identificando:

1. **Gaps específicos de implementação** entre a spec e o código atual
2. **Oportunidades de integração** não-intrusivas
3. **Prioridades técnicas** baseadas na arquitetura existente
4. **Migração incremental** sem breaking changes

---

## Parte 1: Estado Actual vs. Spec Original

### 1.1 O Que Já Existe no Codebase

#### ✅ Componentes Implementados

| Componente | Arquivo | Status | Notas |
|-----------|---------|--------|-------|
| **Memory Layer API** | `services/memory-layer-api/` | ✅ OPERACIONAL | 4 camadas funcionando |
| **UnifiedMemoryClient** | `src/clients/unified_memory_client.py` | ✅ OPERACIONAL | Roteamento hot→warm→cold |
| **IntentEnvelope** | `gateway-intencoes/src/models/intent_envelope.py` | ✅ OPERACIONAL | Context básico presente |
| **CognitivePlan** | `semantic-translation-engine/src/models/` | ✅ OPERACIONAL | Missing: `workflow_type`, `context_id` |
| **ConsolidatedDecision** | `consensus-engine/src/models/` | ✅ OPERACIONAL | Missing: `workflow_type` |
| **FlowCContext** | `neural_hive_integration/models/` | ✅ OPERACIONAL | Contexto de correlação |
| **Observability Context** | `neural_hive_observability/context.py` | ✅ OPERACIONAL | Propagação distribuída |

#### ❌ Componentes Ausentes (Especificados na Doc Original)

| Componente | Prioridade | Impacto | Estimativa |
|-----------|-----------|--------|-----------|
| **ContextManager Service** | CRÍTICA | Alto | 2-3 semanas |
| **RichContext Model** | CRÍTICA | Alto | 1 semana |
| **PII Detector** | ALTA | Médio | 3-4 dias |
| **ContextRouter** | CRÍTICA | Alto | 1-2 semanas |
| **Session Management** | MÉDIA | Médio | 1 semana |
| **Security Context** | ALTA | Alto | 3-5 dias |

---

## Parte 2: Análise de Gaps Específicos

### 2.1 GAP CRÍTICO: Missing `workflow_type` em CognitivePlan

**Local:** `services/semantic-translation-engine/src/models/cognitive_plan.py`

#### Problema Atual

```python
# Código ATUAL (missing workflow_type)
class CognitivePlan(BaseModel):
    plan_id: str
    intent_id: str
    correlation_id: str | None
    trace_id: str | None
    tasks: list[TaskNode]
    risk_score: float
    requires_approval: bool
    is_destructive: bool
    # ❌ CAMPO AUSENTE: workflow_type
    # ❌ CAMPO AUSENTE: context_id
    # ❌ CAMPO AUSENTE: workflow_confidence
```

#### Impacto

**Bloqueia completamente:** Roteamento entre Fluxo C e Fluxo G

**Consequência:** Decision consumer sempre roteia para `OrchestrationWorkflow`, mesmo para intenções de geração.

#### Solução Proposta

```python
from enum import Enum

class WorkflowType(str, Enum):
    """Tipo de workflow a executar"""
    ORCHESTRATION = "orchestration"  # Fluxo C - modificar existente
    GENERATION = "generation"        # Fluxo G - criar novo

class CognitivePlan(BaseModel):
    # ... campos existentes ...

    # ✅ NOVOS CAMPOS (NON-BREAKING COM DEFAULTS)
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
```

**Migração:** Non-breaking (defaults mantêm compatibilidade)

---

### 2.2 GAP CRÍTICO: Decision Consumer Sem Roteamento

**Local:** `services/orchestrator-dynamic/src/consumers/decision_consumer.py` (linhas 562-567)

#### Problema Atual

```python
# Código ATUAL (SEMPRE roteia para Orchestration)
async def process_decision(self, decision: ConsolidatedDecision):
    # ... validações ...

    # ❌ HARDCODED: Sempre usa OrchestrationWorkflow
    await self.temporal_client.start_workflow(
        OrchestrationWorkflow.run,  # ← HARDCODED
        {
            "cognitive_plan": decision.cognitive_plan,
            "consolidated_decision": decision.dict(),
        },
        id=decision.decision_id,
        task_queue=self.config.temporal_task_queue,
    )
```

#### Impacto

**Bloqueia completamente:** Execução do Fluxo G

**Consequência:** Intenções de geração (criar novo sistema) são roteadas incorretamente para Orchestration.

#### Solução Proposta

```python
async def process_decision(self, decision: ConsolidatedDecision):
    # ... validações existentes ...

    # ✅ NOVO: Extrair workflow_type do CognitivePlan
    cognitive_plan = CognitivePlan(**decision.cognitive_plan)
    workflow_type = cognitive_plan.workflow_type

    # ✅ NOVO: Roteamento inteligente
    if workflow_type == WorkflowType.GENERATION:
        workflow_cls = FluxoGWorkflow  # ← FLUXO G (nunca executado)
        logger.info(
            "Routing to Fluxo G (generation workflow)",
            decision_id=decision.decision_id,
            context_id=cognitive_plan.context_id,
        )
    else:
        workflow_cls = OrchestrationWorkflow  # ← FLUXO C (sempre executado)
        logger.info(
            "Routing to Fluxo C (orchestration workflow)",
            decision_id=decision.decision_id,
        )

    # ✅ NOVO: Executar workflow correto
    await self.temporal_client.start_workflow(
        workflow_cls.run,
        {
            "cognitive_plan": cognitive_plan.dict(),
            "consolidated_decision": decision.dict(),
            # ✅ NOVO: Adicionar contexto rico se disponível
            "context": await self._get_context_if_available(cognitive_plan.context_id),
        },
        id=decision.decision_id,
        task_queue=self.config.temporal_task_queue,
    )

async def _get_context_if_available(self, context_id: Optional[str]) -> dict:
    """Busca contexto rico se Context Manager estiver disponível"""
    if not context_id:
        return {}

    try:
        context_client = ContextManagerClient()
        context = await context_client.get_context(context_id)
        return context.dict()
    except Exception as e:
        logger.warning("Failed to fetch context", context_id=context_id, error=str(e))
        return {}
```

**Migração:** Feature flag + fallback (sem breaking changes)

---

### 2.3 GAP MÉDIO: Semantic Parser sem Context Enrichment

**Local:** `services/semantic-translation-engine/src/services/semantic_parser.py`

#### Problema Atual

```python
# Código ATUAL (contexto histórico limitado)
async def parse(self, intent_envelope: dict) -> dict[str, Any]:
    # ... extração de objetivos, entidades, etc ...

    # ✅ EXISTE: Enriquecimento histórico básico
    historical_context = await self._enrich_with_history(
        intent_envelope.get("id"), domain, intent.get("text", "")
    )

    # ❌ AUSENTE: Contexto de sistema (serviços ativos, health, etc)
    # ❌ AUSENTE: Contexto conversacional (sessão, turnos anteriores)
    # ❌ AUSENTE: Inferência de workflow_type (orchestration vs generation)
    # ❌ AUSENTE: Detecção PII

    intermediate_representation = {
        "intent_id": intent_envelope.get("id"),
        "domain": domain,
        # ... campos existentes ...
        "historical_context": historical_context,
    }

    return intermediate_representation
```

#### Solução Proposta (Integração Não-Intrusiva)

```python
# services/semantic-translation-engine/src/services/semantic_parser_extended.py

class SemanticParserExtended(SemanticParser):
    """Extensão não-intrusiva do SemanticParser com Context Layer"""

    def __init__(self, *args, context_client: Optional[ContextManagerClient] = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.context_client = context_client  # ✅ Opcional (não obriga deploy do Context Manager)

    async def parse_with_context(
        self,
        intent_envelope: dict,
        session_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Parseia intenção com contexto rico extendido.

        Mantém compatibilidade com parse() mas adiciona contexto.
        """
        # ✅ Usar implementação base
        base_result = await self.parse(intent_envelope)

        # ✅ Enriquecer com contexto se Context Manager disponível
        if self.context_client:
            try:
                context = await self.context_client.build_context(
                    intent_envelope=intent_envelope,
                    session_id=session_id,
                )

                # ✅ Inferir workflow_type
                workflow_type, confidence, reasoning = await self.context_client.route_workflow(
                    cognitive_plan=base_result,
                    context=context,
                )

                # ✅ Adicionar ao resultado (non-breaking)
                base_result.update({
                    "context_id": context.context_id,
                    "workflow_type": workflow_type.value,
                    "workflow_confidence": confidence,
                    "workflow_reasoning": reasoning,
                    "system_context": context.system.dict(),
                    "conversational_context": context.conversational.dict() if context.conversational else None,
                    "security_context": context.security.dict(),
                })

                logger.info(
                    "Intent parseado com contexto rico",
                    intent_id=intent_envelope.get("id"),
                    workflow_type=workflow_type,
                    confidence=confidence,
                )
            except Exception as e:
                logger.warning(
                    "Failed to enrich with context (continuing without)",
                    intent_id=intent_envelope.get("id"),
                    error=str(e),
                )
                # ✅ Continua sem contexto (fallback graceful)

        return base_result
```

**Migração:** Dependency injection + feature flag

---

### 2.4 GAP MÉDIO: Memory Layer API Missing Context Queries

**Local:** `services/memory-layer-api/src/clients/unified_memory_client.py`

#### Problema Atual

```python
# Código ATUAL (query types existentes)
class QueryType(str, Enum):
    CONTEXT = "context"       # ✅ EXISTE mas retorna apenas MongoDB
    SEMANTIC = "semantic"     # Neo4j
    HISTORICAL = "historical" # ClickHouse
    LINEAGE = "lineage"       # MongoDB + Neo4j
    QUALITY = "quality"       # Data quality monitor

# ❌ AUSENTE: QueryType.CONTEXT não retorna RichContext completo
# ❌ AUSENTE: Não integra com Context Manager
```

#### Solução Proposta (Extensão Não-Intrusiva)

```python
# services/memory-layer-api/src/services/context_enricher_service.py

class ContextEnricherService:
    """Serviço para enriquecer queries de contexto com Context Manager"""

    def __init__(
        self,
        unified_client: UnifiedMemoryClient,
        context_manager_client: Optional[ContextManagerClient] = None,
    ):
        self.memory = unified_client
        self.context = context_manager_client  # ✅ Opcional

    async def query_rich_context(
        self,
        entity_id: str,
        context_type: str = "all",
        include_intent: bool = True,
        include_system: bool = True,
        include_security: bool = True,
    ) -> dict[str, Any]:
        """
        Query contexto rico com múltiplas fontes.

        Fallback graceful se Context Manager não disponível.
        """
        # ✅ Query base do Memory Layer
        base_context = await self.memory.query(
            query_type="context",
            entity_id=entity_id,
            use_cache=True,
        )

        # ✅ Enriquecer com Context Manager se disponível
        if self.context:
            try:
                rich_context = await self.context.get_context(entity_id)

                # ✅ Filtrar dimensões solicitadas
                result = {
                    "entity_id": entity_id,
                    "context_id": rich_context.context_id,
                    "base_context": base_context,
                }

                if include_intent:
                    result["intent"] = rich_context.intent.dict()
                if include_system:
                    result["system"] = rich_context.system.dict()
                if include_security:
                    result["security"] = rich_context.security.dict()

                return result
            except Exception as e:
                logger.warning(
                    "Failed to query Context Manager (returning base only)",
                    entity_id=entity_id,
                    error=str(e),
                )
                # ✅ Fallback para base context

        # ✅ Retornar base context se Context Manager não disponível
        return {
            "entity_id": entity_id,
            "context_id": None,
            "base_context": base_context,
        }

# services/memory-layer-api/src/api/routers/context.py

@router.get("/context/{entity_id}")
async def get_context(
    entity_id: str,
    dimensions: str = Query("all", description="Dimensões: intent,system,security,all"),
    include_rich: bool = Query(False, description="Incluir contexto rico do Context Manager"),
):
    """Endpoint unificado para queries de contexto"""
    enricher = app_state["context_enricher"]

    # ✅ Parse dimensões
    include_intent = dimensions in ["all", "intent"]
    include_system = dimensions in ["all", "system"]
    include_security = dimensions in ["all", "security"]

    # ✅ Query com ou sem Context Manager (based on feature flag)
    result = await enricher.query_rich_context(
        entity_id=entity_id,
        context_type=dimensions,
        include_intent=include_intent,
        include_system=include_system,
        include_security=include_security,
    )

    return JSONResponse(content=result)
```

**Migração:** Novo endpoint + service (non-breaking)

---

## Parte 3: Estratégia de Implementação Incremental

### 3.1 Fase 1: Foundation (Semana 1-2)

**Objetivo:** Criar base técnica sem breaking changes

#### Tarefas

1. **Criar biblioteca `neural_hive_context`**
   - Local: `libraries/python/neural_hive_context/`
   - Conteúdo: Modelos Pydantic (RichContext, IntentContext, etc.)
   - **Non-breaking:** Nova biblioteca independente

2. **Criar cliente gRPC básico**
   - Local: `libraries/python/neural_hive_context/neural_hive_context/client.py`
   - Funcionalidade: get_context(), build_context()
   - **Non-breaking:** Opcional para consumidores

3. **Criar service skeleton**
   - Local: `services/context-manager/`
   - Stack: FastAPI + gRPC + MongoDB + Redis
   - **Non-breaking:** Serviço separado (não afeta existentes)

#### Critérios de Sucesso
- ✅ Biblioteca importável sem erros
- ✅ Cliente gRPC funcional (mock inicial)
- ✅ Service starta com health check

---

### 3.2 Fase 2: CognitivePlan Extension (Semana 2-3)

**Objetivo:** Adicionar `workflow_type` sem breaking changes

#### Tarefas

1. **Modificar CognitivePlan model**
   - Local: `semantic-translation-engine/src/models/cognitive_plan.py`
   - Adicionar: `workflow_type`, `context_id`, `workflow_confidence`
   - **Non-breaking:** Defaults mantêm comportamento atual

2. **Avro schema update**
   - Local: `schemas/cognitive-plan/cognitive-plan.avsc`
   - Adicionar campos opcionais
   - **Non-breaking:** Backward compatible Avro

3. **Testes unitários**
   - Validar defaults (workflow_type = ORCHESTRATION)
   - Validar serialização Avro

#### Critérios de Sucesso
- ✅ Todos os testes existentes passam
- ✅ Novos campos com defaults funcionam
- ✅ Avro schema backward compatible

---

### 3.3 Fase 3: Decision Consumer Routing (Semana 3-4)

**Objetivo:** Rotear para Fluxo G quando apropriado

#### Tarefas

1. **Modificar decision_consumer.py**
   - Local: `orchestrator-dynamic/src/consumers/decision_consumer.py`
   - Adicionar lógica de roteamento baseada em `workflow_type`
   - **Non-breaking:** Feature flag para habilitar roteamento

2. **Fallback graceful**
   - Se Context Manager não disponível → usar roteamento baseado em heurísticas
   - Se workflow_type ausente → default para ORCHESTRATION

3. **Testes E2E**
   - Cenário: Intenção de geração → Fluxo G
   - Cenário: Intenção de operação → Fluxo C
   - Cenário: Fallback sem Context Manager

#### Critérios de Sucesso
- ✅ Feature flag desligada → comportamento atual
- ✅ Feature flag ligada → roteamento funcional
- ✅ Fallbacks funcionam

---

### 3.4 Fase 4: Context Router Basic (Semana 4-5)

**Objetivo:** Implementar roteamento baseado em heurísticas

#### Tarefas

1. **Criar ContextRouter service**
   - Local: `context-manager/src/services/context_router.py`
   - Heurísticas básicas:
     - Keywords (criar/novo vs executar/processar)
     - Verificar se domínio existe em Service Registry
     - Verificar affected_services

2. **Cliente Context Manager**
   - Local: `context-manager/src/api/clients/context_manager_client.py`
   - Métodos: `build_context()`, `route_workflow()`

3. **Integração Semantic Translation Engine**
   - Local: `semantic-translation-engine/src/services/translation_orchestrator.py`
   - Dependency injection de Context Manager client
   - **Non-breaking:** Feature flag

#### Critérios de Sucesso
- ✅ Router classifica workflow_type com >70% precisão (testes manuais)
- ✅ Semantic Engine enriquece CognitivePlan com workflow_type
- ✅ Fallback se Context Manager não disponível

---

### 3.5 Fase 5: PII Detector (Semana 5-6)

**Objetivo:** Detectar PII em intenções

#### Tarefas

1. **Criar PIIDetector service**
   - Local: `context-manager/src/services/pii_detector.py`
   - Padrões regex básicos: EMAIL, PHONE, SSN, CREDIT_CARD

2. **Integration Gateway**
   - Local: `gateway-intencoes/src/services/pii_detection_service.py`
   - Detectar PII durante NLU pipeline
   - Maskar entidades detectadas

3. **Context Security**
   - Local: `context-manager/src/services/security_context.py`
   - Adicionar `pii_detected`, `pii_entities` ao SecurityContext

#### Critérios de Sucesso
- ✅ Detecção de PII funcional
- ✅ Masking preserva formato para validação
- ✅ PII logged em SecurityContext

---

### 3.6 Fase 6: System Context Integration (Semana 6-7)

**Objetivo:** Adicionar contexto de sistema

#### Tarefas

1. **Service Registry client**
   - Local: `context-manager/src/clients/service_registry_client.py`
   - Consultar: serviços ativos, topics Kafka, health status

2. **SystemContext builder**
   - Local: `context-manager/src/services/context_builder.py`
   - `build_system_context()`: popula SystemContext

3. **Integration Memory Layer**
   - Local: `memory-layer-api/src/services/context_enricher_service.py`
   - Novo endpoint `/context/{entity_id}?include_rich=true`

#### Critérios de Sucesso
- ✅ SystemContext populado com dados reais
- ✅ Memory Layer API retorna contexto rico
- ✅ Latência < 100ms (p95)

---

### 3.7 Fase 7: Testing & Documentation (Semana 7-8)

**Objetivo:** Garantir qualidade e operabilidade

#### Tarefas

1. **Testes E2E completos**
   - Cenário: Intenção de geração completa (Fluxo G)
   - Cenário: Intenção de operação completa (Fluxo C)
   - Cenário: Fallback sem Context Manager

2. **Documentação**
   - API do Context Manager
   - Guia de integração (feature flags, fallbacks)
   - Runbooks operacionais

3. **Performance testing**
   - Latência de contexto < 100ms (p95)
   - Throughput > 100 req/s por pod
   - Memory overhead < 100MB per pod

#### Critérios de Sucesso
- ✅ Todos os testes E2E passam
- ✅ Documentação completa
- ✅ Performance SLOs atendidos

---

## Parte 4: Prioridades Técnicas

### 4.1 Criticidade (Must-Have vs Nice-to-Have)

| Prioridade | Componente | Razão | Impacto se não implementado |
|-----------|-----------|-------|----------------------------|
| **P0** | `workflow_type` em CognitivePlan | Bloqueia roteamento C↔G | Fluxo G nunca executado |
| **P0** | Decision Consumer routing | Habilita Fluxo G | Intenções de geração falham |
| **P0** | Context Router básico | Classifica workflow | Roteamento não funciona |
| **P1** | System Context | Enrichment crítico | Decisões sem contexto de sistema |
| **P1** | PIIDetector | Compliance | PII não detectado/mascarado |
| **P2** | Conversational Context | Experiência conversacional | Sem histórico de sessão |
| **P2** | Business Context | Contexto de negócio | Sem contexto de sprint/tickets |
| **P3** | Decision History | Causalidade | Sem rastreamento causal |
| **P3** | Session Management | UX avançada | Sem continuidade conversacional |

---

### 4.2 Dependências

```
P0: workflow_type em CognitivePlan
  ↓ depende de
P0: Context Router básico (para classificar)
  ↓ depende de
P1: System Context (para verificar se domínio existe)
  ↓ depende de
Service Registry integration

P0: Decision Consumer routing
  ↓ depende de
P0: workflow_type em CognitivePlan
  ↓ depende de
Context Manager client (opcional - fallback heurísticas)

P1: PIIDetector
  ↓ independente
  ← pode ser paralelo com P0

P2: Conversational Context
  ↓ depende de
Session management
  ↓ depende de
MongoDB para histórico de sessões
```

---

## Parte 5: Riscos e Mitigações

### 5.1 Riscos Técnicos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| **Latência de contexto > 100ms** | Média | Médio | Cache agressivo (TTL 5 min), lazy loading |
| **Context Manager unavailable** | Baixa | Alto | Fallback para roteamento heurístico, feature flags |
| **False positives em PIIDetector** | Média | Alto | Threshold ajustável, whitelisting de padrões |
| **Routing errors (G→C ou C→G)** | Baixa | Alto | Audit trail, manual override via admin UI |
| **Session state explosion** | Baixa | Médio | TTL agressivo (30 min), cleanup jobs diários |
| **Breaking changes em schemas Avro** | Baixa | Alto | Versionamento de schemas, backward compatibility test |

---

### 5.2 Riscos de Implementação

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| **Scope creep** | Alta | Médio | Fases bem definidas, critérios de sucesso claros |
| **Time overrun** | Média | Alto | Priorização P0/P1, P2/P3 para iteração futura |
| **Resource contention** | Baixa | Médio | Load testing antes de deploy, autoscaling |
| **Team dependency** | Média | Baixo | Documentação clara, onboarding |

---

## Parte 6: Métricas de Sucesso

### 6.1 Métricas Técnicas

| Métrica | SLO | Métrica Atual | Alvo |
|---------|-----|---------------|------|
| **Latência de contexto** | < 100ms p95 | N/A | 50ms p95 |
| **Precisão de routing** | > 80% | N/A | 90% |
| **Detecção de PII** | > 95% | N/A | 98% |
| **Disponibilidade Context Manager** | > 99.9% | N/A | 99.95% |
| **Throughput Context Manager** | > 100 req/s/pod | N/A | 200 req/s/pod |

---

### 6.2 Métricas de Negócio

| Métrica | Alvo | Impacto |
|---------|------|---------|
| **% de intenções de geração roteadas para Fluxo G** | > 95% | Fluxo G funcional |
| **% de PII detectado e mascarado** | > 99% | Compliance |
| **Tempo médio para resolver intenção** | < 4 horas | Contexto reduz latência |
| **Satisfação do usuário** | > 4.5/5 | Contexto melhora UX |

---

## Parte 7: Próximos Passos Imediatos

### 7.1 Esta Semana (Semana 1)

1. **Criar biblioteca `neural_hive_context`**
   ```bash
   mkdir -p libraries/python/neural_hive_context/neural_hive_context
   cd libraries/python/neural_hive_context
   # Criar estrutura: models/, client/, exceptions/
   ```

2. **Criar service skeleton `context-manager`**
   ```bash
   mkdir -p services/context-manager/src/{api,services,models}
   # Boilerplate FastAPI + gRPC + MongoDB + Redis
   ```

3. **Definir modelos Pydantic**
   - RichContext, IntentContext, SystemContext, etc.
   - Baseado na spec original mas simplificado (P0/P1 primeiro)

---

### 7.2 Próxima Semana (Semana 2)

1. **Modificar CognitivePlan model**
   - Adicionar `workflow_type`, `context_id`, `workflow_confidence`
   - Update Avro schema

2. **Criar Context Router básico**
   - Heurísticas de keywords
   - Verificação de Service Registry

3. **Testes unitários**
   - CognitivePlan com novos campos
   - Context Router com casos de teste

---

## Parte 8: Conclusão

### Resumo

O Neural Hive Mind possui uma **fundação sólida** (Memory Layer, Observability, IntentEnvelope) que facilita a implementação do Context Layer. Os principais gaps são:

1. **workflow_type ausente em CognitivePlan** (P0 - crítico)
2. **Decision Consumer hardcoded para Orchestration** (P0 - crítico)
3. **Context Manager inexistente** (P0 - crítico)
4. **System Context não integrado** (P1 - alto)
5. **PII Detector inexistente** (P1 - alto)

A abordagem recomendada é **incremental e não-intrusiva**:
- Fase 1-3: Foundation + P0 features (4 semanas)
- Fase 4-7: P1/P2 features (4 semanas)
- Semana 8: Testing + documentation

Com esta abordagem, o **Fluxo G pode ser funcional em 4 semanas** e o Context Layer completo em 8 semanas.

---

*Análise técnica profunda - 2026-04-23*
