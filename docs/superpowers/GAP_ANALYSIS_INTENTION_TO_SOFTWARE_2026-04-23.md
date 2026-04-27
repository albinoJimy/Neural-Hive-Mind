# Gap Analysis - Intenção → Software com Autocorreção

**Data:** 2026-04-23
**Tipo:** Análise de Gaps Críticos
**Objetivo:** Identificar impedimentos para NHM cumprir 100% do fluxo intenção → software com autocorreção

---

## Resumo Executivo

### Veredito: 🔴 CRÍTICO - GAPS FUNDAMENTAIS

O Neural Hive Mind **NÃO cumpre atualmente** o objetivo de transformar intenção em software com autocorreção. Existem gaps críticos em múltiplas camadas do sistema.

| Gap | Severidade | Impacto | Status |
|-----|-----------|---------|--------|
| **Fluxo G Bloqueado** | 🔴 P0 | Software nunca é gerado | Confirmado |
| **Code-Forge Isolado** | 🔴 P0 | Sem geração de código real | Confirmado |
| **Routing Inexistente** | 🔴 P0 | Sem C↔G, só Fluxo C | Confirmado |
| **Autocorreção Parcial** | 🟡 P1 | Correção mas não geração | Parcial |
| **Feedback Loop Incompleto** | 🟡 P1 | Sem replay automático | Parcial |

---

## Parte 1: Fluxo Completo Esperado

### 1.1 Arquitetura Esperada (Ideal)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    FLUXO COMPLETO INTENÇÃO → SOFTWARE                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐              │
│  │   USER   │───▶│ GATEWAY  │───▶│   STE    │───▶│ CONSENSUS│              │
│  │ INTENTION│    │  (NLU)   │    │ (Parse)  │    │ (Merge)  │              │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘              │
│       │              │               │               │                      │
│       │              ▼               ▼               ▼                      │
│       │         ┌─────────────────────────────────────────────┐            │
│       │         │          CONTEXT LAYER (Router)              │            │
│       │         │  ┌─────────────────┐    ┌─────────────────┐ │            │
│       │         │  │  TYPE: MODIFY   │    │   TYPE: CREATE  │ │            │
│       │         │  │  → Fluxo C      │    │   → Fluxo G     │ │            │
│       │         │  └─────────────────┘    └─────────────────┘ │            │
│       │         └─────────────────────────────────────────────┘            │
│       │                      │                      │                       │
│       │               ┌──────┴──────┐        ┌──────┴──────┐                │
│       │               │             │        │             │                │
│       ▼               ▼             ▼        ▼             ▼                │
│  ┌──────────┐   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │  RESULT  │   │ FLUXO C  │  │ FLUXO G  │  │CODE-FORGE │  │  SOFTWARE │   │
│  │          │   │(Modify)  │  │(Create)  │  │(Generate) │  │ GENERATED │   │
│  └──────────┘   └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
│                                           │               │               │
│                                           ▼               ▼               │
│                                    ┌────────────────────────────┐         │
│                                    │   SELF-HEALING ENGINE       │         │
│                                    │  - Error Detection          │         │
│                                    │  - Auto-Remediation         │         │
│                                    │  - Replay Loop              │         │
│                                    └────────────────────────────┘         │
│                                             │                              │
│                                             ▼                              │
│                                    ┌────────────────────────────┐         │
│                                    │   FEEDBACK LOOP             │         │
│                                    │  - Metrics Collection       │         │
│                                    │  - Learning Signal          │         │
│                                    │  - Specialist Feedback      │         │
│                                    └────────────────────────────┘         │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Etapas do Fluxo Ideal

| Etapa | Componente | Ação | Saída |
|-------|-----------|------|-------|
| **E0** | Gateway Intenções | NLU + Intent Classification | `classified_intent` |
| **E1** | STE | Semantic Translation | `cognitive_plan` |
| **E2** | Consensus Engine | Specialist Aggregation | `consolidated_decision` |
| **E3** | Context Layer | **TYPE DETECTION + ROUTING** | `workflow_type` |
| **E4A** | Orchestrator (C) | Execute Existing Software | `execution_result` |
| **E4B** | Fluxo G Workflow | Generate Requirements+Docs | `artifacts` |
| **E5** | Code-Forge | **GENERATE CODE** | `software_package` |
| **E6** | Self-Healing | Detect+Fix Errors | `corrected_result` |
| **E7** | Feedback Loop | Learn+Improve | `learning_signal` |

---

## Parte 2: GAPS CRÍTICOS IDENTIFICADOS

### Gap #1: Fluxo G Bloqueado (🔴 P0)

**Localização:** `/services/orchestrator-dynamic/src/consumers/decision_consumer.py:563`

**Problema:**
```python
# LINHA 563 - HARDCODED PARA FLUXO C
await self.temporal_client.start_workflow(
    OrchestrationWorkflow.run,  # ❌ SEMPRE Fluxo C
    input_data,
    id=workflow_id,
    task_queue=self.config.temporal_task_queue,
)
```

**Impacto:**
- ❌ Fluxo G **NUNCA** executa
- ❌ Software novo **NUNCA** é gerado
- ❌ Workflow `FluxoGWorkflow` existe mas está inacessível

**Evidência:**
```python
# workflow __init__.py NÃO exporta FluxoGWorkflow
__all__ = ["OrchestrationWorkflow", "DataMigrationWorkflow"]
# FluxoGWorkflow está registrado no worker mas NÃO exportado
```

**Correção Necessária:**
1. Adicionar `workflow_type` ao `CognitivePlan`
2. Implementar lógica de routing em `decision_consumer.py`
3. Exportar `FluxoGWorkflow` no `__init__.py`

---

### Gap #2: Code-Forge Isolado (🔴 P0)

**Problema:**
O `code-forge` é um serviço completo com capacidade de geração de código, mas **NÃO está integrado** no Fluxo G.

**Evidência:**
```bash
# code-forge tem PipelineEngine para geração de código
services/code-forge/src/services/pipeline_engine.py

# MAS não há activity que o chame no Fluxo G
services/orchestrator-dynamic/src/activities/fluxo_g_integration.py
# Contém: generate_requirements, generate_documentation, request_approval
# NÃO CONTÉM: generate_code, build_package, deploy_service
```

**Fluxo G Atual (Incompleto):**
```
FluxoGWorkflow:
  ├─ G1: generate_requirements       ✅ IMPLEMENTADO
  ├─ G2: generate_documentation      ✅ IMPLEMENTADO
  ├─ G3: update_knowledge_graph      ✅ IMPLEMENTADO
  ├─ G4: request_approval            ✅ IMPLEMENTADO
  ├─ G5: query_rag                   ✅ IMPLEMENTADO
  └─ G6: GENERATE_CODE               ❌ AUSENTE
  └─ G7: BUILD_PACKAGE               ❌ AUSENTE
  └─ G8: DEPLOY_SOFTWARE             ❌ AUSENTE
```

**Correção Necessária:**
1. Criar activities para integrar com code-forge
2. Adicionar etapas G6-G8 no FluxoGWorkflow
3. Implementar handoff entre requirements → code generation

---

### Gap #3: Context Layer Inexistente (🔴 P0)

**Problema:**
Não existe lógica de decisão entre Fluxo C (modify) e Fluxo G (create). O routing está hardcoded para Fluxo C.

**CognitivePlan - Campos Atuais:**
```python
class CognitivePlan(BaseModel):
    plan_id: str
    intent_id: str
    summary: str
    workflow_definition: dict
    # ❌ workflow_type: Literal["orchestration", "generation"] AUSENTE
```

**Evidência:**
```bash
grep -rn "workflow_type" services/semantic-translation-engine/src/models/
# Resultado: (nenhum)
```

**Correção Necessária:**
1. Adicionar campo `workflow_type` ao `CognitivePlan`
2. Implementar lógica de classificação no STE ou Consensus
3. Atualizar `decision_consumer.py` para routing dinâmico

---

### Gap #4: Self-Healing Parcial (🟡 P1)

**Status Atual:**
| Funcionalidade | Status | Observação |
|---------------|--------|------------|
| Detecção de Erros | ✅ | `trigger_self_healing` implementado |
| Auto-Remediação | ✅ | Circuit breakers funcionais |
| Replay de Workflow | ❌ | **AUSENTE** |
| Aprendizado com Erros | ⚠️ | Parcial (active learning) |

**Evidência:**
```python
# services/orchestrator-dynamic/src/activities/result_consolidation.py:735
async def trigger_self_healing(
    workflow_id: str,
    inconsistencies: list[dict],
    ...
):
    # Dispara autocura, mas NÃO executa replay
```

**Problema:**
Self-healing detecta e corrige erros, mas **não replays** o workflow do início. O loop de autocorreção está incompleto.

**Correção Necessária:**
1. Implementar `replay_workflow` após correção
2. Garantir que erros de geração de código disparem replay
3. Adicionar métricas de success rate pós-autocorreção

---

### Gap #5: Feedback Loop Incompleto (🟡 P1)

**Componentes Existentes:**
| Componente | Status | Capacidade |
|-----------|--------|-----------|
| `active_learning` | ✅ | Coleta de feedback balanceado |
| `specialist_feedback` | ✅ | Armazena feedback dos especialistas |
| `ml_training` | ✅ | Retreina modelos com feedback |
| `replay_signal` | ❌ | **AUSENTE** - não dispara re-execução |

**Problema:**
O feedback é coletado e usado para treinar modelos, mas **não dispara replay** de workflows com base em melhorias.

**Correção Necessária:**
1. Implementar signal de `replay_workflow` baseado em melhoria de modelo
2. Criar fila de workflows para replay após model update
3. Monitorar ganho de performance pós-replay

---

## Parte 3: Maturidade por Camada

### 3.1 Tabela de Maturidade

| Camada | Componente | Maturidade | Gaps | Status |
|--------|-----------|-----------|------|--------|
| **E0** | Gateway Intenções | 90% | NLU avançado OK | ✅ |
| **E1** | STE | 85% | Falta workflow_type | ⚠️ |
| **E2** | Consensus Engine | 80% | BMA simplificado | ⚠️ |
| **E3** | Context Layer | **0%** | **Não implementado** | ❌ |
| **E4A** | Orchestrator C | 95% | Workflow funcional | ✅ |
| **E4B** | Fluxo G | 20% | **Sem geração código** | ❌ |
| **E5** | Code-Forge | 70% | **Não integrado** | ❌ |
| **E6** | Self-Healing | 60% | Sem replay | ⚠️ |
| **E7** | Feedback Loop | 50% | Sem auto-replay | ⚠️ |

### 3.2 Gaps por Severidade

| Severidade | Gap | Componentes Afetados |
|-----------|-----|---------------------|
| **🔴 P0** | Fluxo G Bloqueado | decision_consumer.py |
| **🔴 P0** | Code-Forge Isolado | fluxo_g_workflow.py |
| **🔴 P0** | Context Layer Ausente | CognitivePlan, STE |
| **🟡 P1** | Self-Healing Parcial | result_consolidation.py |
| **🟡 P1** | Feedback Loop Incompleto | active_learning, ml_training |
| **🟢 P2** | BMA Simplificado | consensus-engine |
| **🟢 P2** | AI-Washing | specialist-* (5 serviços) |

---

## Parte 4: Análise Detalhada por Gap

### 4.1 Gap #1: Fluxo G Bloqueado

**Arquivos Envolvidos:**
```
services/orchestrator-dynamic/src/consumers/decision_consumer.py
services/orchestrator-dynamic/src/workflows/__init__.py
services/orchestrator-dynamic/src/workflows/fluxo_g_workflow.py
services/orchestrator-dynamic/src/workflows/orchestration_workflow.py
services/semantic-translation-engine/src/models/cognitive_plan.py
```

**Mudanças Necessárias:**

1. **CognitivePlan** - Adicionar workflow_type:
```python
# services/semantic-translation-engine/src/models/cognitive_plan.py
class CognitivePlan(BaseModel):
    # ... campos existentes ...
    workflow_type: Literal["orchestration", "generation"] = "orchestration"
    confidence_score: float = 0.0
```

2. **decision_consumer** - Implementar routing:
```python
# services/orchestrator-dynamic/src/consumers/decision_consumer.py
workflow_type = cognitive_plan.get("workflow_type", "orchestration")

if workflow_type == "generation":
    from src.workflows.fluxo_g_workflow import FluxoGWorkflow
    await self.temporal_client.start_workflow(
        FluxoGWorkflow.run,  # ← Fluxo G
        input_data,
        id=workflow_id,
        task_queue=self.config.temporal_task_queue,
    )
else:
    await self.temporal_client.start_workflow(
        OrchestrationWorkflow.run,  # ← Fluxo C
        input_data,
        id=workflow_id,
        task_queue=self.config.temporal_task_queue,
    )
```

3. **__init__.py** - Exportar FluxoGWorkflow:
```python
from .fluxo_g_workflow import FluxoGWorkflow

__all__ = ["OrchestrationWorkflow", "DataMigrationWorkflow", "FluxoGWorkflow"]
```

---

### 4.2 Gap #2: Code-Forge Integration

**Arquivos Envolvidos:**
```
services/orchestrator-dynamic/src/activities/fluxo_g_integration.py
services/orchestrator-dynamic/src/workflows/fluxo_g_workflow.py
services/code-forge/src/services/pipeline_engine.py
services/code-forge/src/api/
```

**Mudanças Necessárias:**

1. **Nova Activity** - `generate_code_activity.py`:
```python
@activity.defn
async def generate_code(
    requirements_set: dict[str, Any],
    documentation: dict[str, Any],
    cognitive_plan: dict[str, Any],
) -> dict[str, Any]:
    """
    Gera código a partir de requisitos e documentação.

    Integra com code-forge via API ou client direto.
    """
    # Chamar code-forge API
    response = await _http_client.post(
        "http://code-forge:8020/api/v1/pipelines/execute",
        json={
            "ticket_type": "code_generation",
            "requirements": requirements_set,
            "documentation": documentation,
            "plan": cognitive_plan,
        },
        timeout=300.0,  # 5 minutos
    )
    return response.json()
```

2. **Atualizar FluxoGWorkflow** - Adicionar G6-G8:
```python
# Após G5 (rag_enrichment):

# === G6: Code Generation ===
self._status = "generating_code"
workflow.logger.info("G6: Gerando código")

code_result = await workflow.execute_activity(
    generate_code,
    args=[requirements_result, docs_result, cognitive_plan],
    start_to_close_timeout=timedelta(seconds=600),  # 10 minutos
    retry_policy=RetryPolicy(maximum_attempts=1),
)

# === G7: Build & Package ===
self._status = "building_package"
# ... chamada ao code-forge para build

# === G8: Deploy (opcional) ===
self._status = "deploying"
# ... chamada ao deploy service
```

---

### 4.3 Gap #3: Context Layer Implementation

**Abordagem Recomendada: Multi-Signal Classification**

**Signals para Routing:**
1. **Intent Keywords:** "criar", "novo", "from scratch" → Fluxo G
2. **Domain Similarity:** Similaridade com planos existentes no grafo
3. **Resource Availability:** Se recursos não existem → Fluxo G
4. **Complexity Score:** Alta complexidade → Fluxo G com aprovação

**Implementação:**
```python
# services/semantic-translation-engine/src/services/context_classifier.py
class ContextClassifier:
    async def classify_workflow_type(
        self, intent: str, cognitive_plan: CognitivePlan
    ) -> tuple[Literal["orchestration", "generation"], float]:
        """
        Classifica se o workflow deve ser Orchestration (C) ou Generation (G).

        Returns:
            (workflow_type, confidence_score)
        """
        signals = []

        # Signal 1: Intent Keywords
        create_keywords = ["criar", "novo", "from scratch", "build", "desenvolver"]
        if any(kw in intent.lower() for kw in create_keywords):
            signals.append(("keyword", 0.7, "generation"))

        # Signal 2: Domain Similarity (via Knowledge Graph)
        similar_plans = await self._query_similar_plans(cognitive_plan)
        if similar_plans["count"] == 0:
            signals.append(("domain", 0.8, "generation"))

        # Signal 3: Resource Availability
        resources_exist = await self._check_resources(cognitive_plan)
        if not resources_exist:
            signals.append(("resource", 0.9, "generation"))

        # Aggregate signals
        return self._aggregate_signals(signals)
```

---

### 4.4 Gap #4: Self-Healing Replay

**Implementação Necessária:**
```python
# services/orchestrator-dynamic/src/activities/self_healing_replay.py
@activity.defn
async def replay_workflow_after_healing(
    original_workflow_id: str,
    workflow_type: str,
    corrected_input: dict,
) -> dict[str, Any]:
    """
    Replay workflow após autocorreção.

    Se a autocorreção foi bem-sucedida, reexecutar o workflow
    do início com o input corrigido.
    """
    # Reexecutar workflow
    if workflow_type == "generation":
        from src.workflows.fluxo_g_workflow import FluxoGWorkflow
        workflow_class = FluxoGWorkflow
    else:
        from src.workflows.orchestration_workflow import OrchestrationWorkflow
        workflow_class = OrchestrationWorkflow

    # Iniciar novo workflow com ID correlacionado
    new_workflow_id = f"{original_workflow_id}-replay-{uuid.uuid4().hex[:8]}"

    # ... executar workflow
```

---

### 4.5 Gap #5: Feedback-Driven Replay

**Implementação Necessária:**
```python
# services/orchestrator-dynamic/src/services/feedback_replay_service.py
class FeedbackReplayService:
    async def check_and_replay_on_model_update(self):
        """
        Verifica se há workflows que devem ser re-executados
        após atualização de modelo ML.
        """
        # Buscar workflows falhados onde o modelo causou a falha
        failed_workflows = await self._get_failed_workflows_by_cause("ml_prediction")

        # Para cada workflow, verificar se o modelo melhorou
        for wf in failed_workflows:
            model_version = wf["model_version"]
            current_version = await self._get_current_model_version()

            if current_version > model_version:
                # Disparar replay
                await self._trigger_replay(wf["workflow_id"])
```

---

## Parte 5: Roadmap de Correção

### Fase 1: Desbloquear Fluxo G (1-2 semanas)

**Ticket:** GAP-FG-001

- [ ] FG-01: Adicionar `workflow_type` ao CognitivePlan
- [ ] FG-02: Implementar lógica de routing em decision_consumer
- [ ] FG-03: Exportar FluxoGWorkflow no __init__.py
- [ ] FG-04: Testar routing C↔G com intenções de teste
- [ ] FG-05: Atualizar documentação

**Entregável:** Fluxo G executável via routing dinâmico

### Fase 2: Integrar Code-Forge (2-3 semanas)

**Ticket:** GAP-CF-001

- [ ] CF-01: Criar activity `generate_code` para code-forge
- [ ] CF-02: Criar activity `build_package` para code-forge
- [ ] CF-03: Adicionar etapas G6-G8 no FluxoGWorkflow
- [ ] CF-04: Implementar handoff requirements → code
- [ ] CF-05: Testar geração de código end-to-end

**Entregável:** Software gerado automaticamente via Fluxo G

### Fase 3: Implementar Context Layer (2-3 semanas)

**Ticket:** GAP-CL-001

- [ ] CL-01: Criar ContextClassifier com multi-signal
- [ ] CL-02: Integrar classificação no STE
- [ ] CL-03: Adicionar métricas de confiança
- [ ] CL-04: Testar precisão de routing (target: >85%)
- [ ] CL-05: Implementar fallback para revisão humana

**Entregável:** Routing automático C↔G com 85%+ precisão

### Fase 4: Completar Self-Healing (1-2 semanas)

**Ticket:** GAP-SH-001

- [ ] SH-01: Implementar `replay_workflow` activity
- [ ] SH-02: Integrar replay após autocorreção
- [ ] SH-03: Adicionar métricas de success rate pós-replay
- [ ] SH-04: Testar loop de autocorreção completo

**Entregável:** Self-healing com replay automático

### Fase 5: Fechar Feedback Loop (1-2 semanas)

**Ticket:** GAP-FB-001

- [ ] FB-01: Implementar signal de replay pós-model-update
- [ ] FB-02: Criar fila de workflows pendentes de replay
- [ ] FB-03: Monitorar ganho de performance
- [ ] FB-04: Testar loop de aprendizado completo

**Entregável:** Sistema que melhoria com uso

---

## Parte 6: Priorização e Estimativa

### Tabela de Trabalho

| Fase | Gap | Esforço | Impacto | Prioridade |
|------|-----|---------|---------|------------|
| 1 | FG-001 | 1-2 sem | 🔴 Crítico | P0 |
| 2 | CF-001 | 2-3 sem | 🔴 Crítico | P0 |
| 3 | CL-001 | 2-3 sem | 🟡 Alto | P1 |
| 4 | SH-001 | 1-2 sem | 🟡 Alto | P1 |
| 5 | FB-001 | 1-2 sem | 🟢 Médio | P2 |

**Timeline Total:** 7-12 semanas para 100% do objetivo

### Quick Wins (1-3 dias)

- [ ] Adicionar `workflow_type` ao CognitivePlan (4h)
- [ ] Exportar FluxoGWorkflow no __init__.py (1h)
- [ ] Criar activity stub para `generate_code` (8h)
- [ ] Adicionar routing básico por keyword (8h)

---

## Parte 7: Conclusão

### Estado Atual

O Neural Hive Mind é um sistema **altamente sofisticado** com:
- ✅ NLU avançado (Gateway)
- ✅ Semantic parsing (STE)
- ✅ Specialist aggregation (Consensus)
- ✅ Orchestration robusta (Fluxo C)
- ✅ Self-healing parcial
- ✅ ML pipelines funcionais

### Gaps Críticos

Mas **não cumpre o objetivo principal** porque:
1. ❌ Fluxo G está **bloqueado** (hardcoded para Fluxo C)
2. ❌ Code-Forge está **isolado** (não integrado)
3. ❌ Context Layer está **ausente** (sem routing C↔G)
4. ❌ Autocorreção é **parcial** (sem replay)
5. ❌ Feedback loop é **incompleto** (sem auto-replay)

### Caminho para 100%

Com as correções propostas:
- **7-12 semanas** para implementar todos os gaps
- **Fases 1-2 (P0)**: 3-5 semanas para software gerável
- **Fases 3-5 (P1-P2)**: 4-7 semanas para excelência

### Recomendação Imediata

**Iniciar pela Fase 1 (Desbloquear Fluxo G)** pois:
1. Desbloqueia funcionalidade crítica existente
2. Baixo esforço (1-2 semanas)
3. Alto impacto (permite testar Fluxo G)
4. Pré-requisito para Fase 2 (Code-Forge integration)

---

**Fim da Gap Analysis**
**Data:** 2026-04-23
**Status:** Análise completa de gaps críticos
**Próximo Passo:** Priorizar Fase 1 para desbloquear Fluxo G
