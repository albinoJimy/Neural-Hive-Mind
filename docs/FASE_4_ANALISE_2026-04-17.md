# Fase 4: Orchestration Integration - Análise de Completude

> **Data:** 2026-04-17
> **Spec:** `docs/superpowers/plans/2026-04-16-fluxo-g-fase4-orchestration-integration.md`
> **Status:** ~60% Completude

---

## Resumo Executivo

A Fase 4 implementa a orquestração end-to-end do Fluxo G via Temporal, integrando todos os serviços das fases anteriores (requirements-engineering, documentation-generation, knowledge-graph-rag, approval-gateway).

**Status Crítico:** O workflow e atividades existem mas **NÃO estão registrados no Temporal Worker**.

---

## 1. Workflow Temporal (FluxoGWorkflow)

### Status: **✅ Implementado** (mas não registrado)

### Arquivo: `src/workflows/fluxo_g_workflow.py`

| Estágio | Atividade | Serviço Alvo | Status |
|---------|-----------|--------------|--------|
| G1 | generate_requirements | requirements-engineering (8010) | ✅ |
| G2 | generate_documentation | documentation-generation (8014) | ✅ |
| G3 | update_knowledge_graph | knowledge-graph-rag (8016) | ✅ |
| G4 | request_approval | approval-gateway (8017) | ✅ |
| G5 | query_knowledge_graph | knowledge-graph-rag (8016) | ✅ |

### Características Implementadas

- ✅ Pipeline sequencial com 5 estágios
- ✅ Retry policy em cada activity (max_attempts=2)
- ✅ Skip approvals condicional
- ✅ Tratamento de aprovações que requerem revisão humana
- ✅ Logging estruturado com structlog
- ✅ Resultado agregado com todos os artefatos

### Código Principal

```python
@workflow.defn
class FluxoGWorkflow:
    @workflow.run
    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        # G1: Requirements Engineering
        requirements_result = await workflow.execute_activity(
            generate_requirements,
            args=[cognitive_plan, original_intent],
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=RetryPolicy(maximum_attempts=2)
        )
        # ... G2-G5 stages
```

---

## 2. Activities de Integração

### Status: **✅ Implementadas** (mas não registradas)

### Arquivo: `src/activities/fluxo_g_integration.py`

| Activity | Propósito | Stub Fallback | Status |
|----------|-----------|---------------|--------|
| `generate_requirements` | POST /requirements/from-plan | ✅ | ✅ |
| `generate_documentation` | POST /documentation/from-plan | ✅ | ✅ |
| `update_knowledge_graph` | POST /nodes + /relations | ✅ | ✅ |
| `request_approval` | POST /approvals/request | ✅ | ✅ |
| `query_knowledge_graph` | POST /rag/context | ✅ | ✅ |

### Padrão de Fallback

Todas as activities implementam fallback para stub quando HTTP client não está disponível:

```python
async def generate_requirements(cognitive_plan: dict, original_intent: str = None) -> dict:
    if not _http_client:
        return {
            "requirements_set_id": f"REQ-SET-{plan_id}",
            "status": "stub"
        }
    # ... chamada HTTP real
```

---

## 3. Testes

### Status: **✅ 10/10 passing**

#### Activities Tests (`tests/activities/test_fluxo_g_integration.py`)

- ✅ 3 testes generate_requirements (success, error, no_client)
- ✅ 1 teste generate_documentation
- ✅ 2 testes update_knowledge_graph (success, no_client)
- ✅ 2 testes request_approval (success, requires_human)
- ✅ 2 testes query_knowledge_graph (success, no_client)

#### Workflow Tests (`tests/workflows/test_fluxo_g_workflow.py`)

- ⚠️ **ImportError** (não relacionado ao Fluxo G):
  - `ModuleNotFoundError: No module named 'src.models.migration'`
  - Este erro é em `data_migration_workflow.py`, não no FluxoGWorkflow
  - Os testes do workflow não podem rodar devido a este erro

---

## 4. Temporal Worker Registration

### Status: **❌ CRÍTICO - Não Registrado**

### Arquivo: `src/workers/temporal_worker.py`

O worker **NÃO importa** nem **registra** FluxoGWorkflow ou suas activities.

#### Workflows Registrados (linha 437)
```python
workflows=[OrchestrationWorkflow, DataMigrationWorkflow],
```

**Faltam:**
- `FluxoGWorkflow` ❌

#### Activities Registradas (linhas 438-461)
```python
activities=[
    # Orchestration activities
    validate_cognitive_plan,
    audit_validation,
    # ... (16 activities total)
    # Data Migration activities
    analyze_legacy_schema,
    # ... (9 activities)
],
```

**Faltam:**
- `generate_requirements` ❌
- `generate_documentation` ❌
- `update_knowledge_graph` ❌
- `request_approval` ❌
- `query_knowledge_graph` ❌

### Impacto

O workflow e activities existem mas **nunca serão executados** pelo Temporal porque não estão registrados no worker.

---

## 5. Kafka Topics

### Status: **❌ Não Implementado**

#### Topics Definidos no Spec (11 topics)

- `fluxo-g.intent.received` (3 partitions)
- `fluxo-g.requirements.generated` (3 partitions)
- `fluxo-g.architecture.generated` (3 partitions)
- `fluxo-g.rag.queries` (6 partitions)
- `fluxo-g.rag.results` (6 partitions)
- `fluxo-g.documentation.generated` (3 partitions)
- `fluxo-g.approval.requested` (3 partitions)
- `fluxo-g.approval.completed` (3 partitions)
- `fluxo-g.code.generated` (3 partitions)
- `fluxo-g.pipeline.completed` (3 partitions)
- `fluxo-g.pipeline.failed` (3 partitions)

#### Dead Letter Topics (4 DLTs)

- `fluxo-g.requirements.dlt`
- `fluxo-g.architecture.dlt`
- `fluxo-g.documentation.dlt`
- `fluxo-g.approval.dlt`

#### Arquivo Esperado vs Realidade

**Spec define:** `infrastructure/kafka/topics/fluxo-g-topics.yaml`

**Realidade:** Diretório `infrastructure/` não existe no projeto.

**Nota:** O Kafka está configurado em `docker-compose.yml` principal com `auto.create.topics.enable=true`, então os tópicos seriam criados automaticamente, mas sem as configurações específicas (partitions, retention).

---

## 6. Docker Compose Fase 4

### Arquivo: `tests/e2e/docker-compose.fase4.yml`

**Serviços Incluídos:**
- ✅ MongoDB
- ✅ Kafka (simplificado)
- ✅ MLflow
- ✅ Redis
- ✅ hypothesis-library (porta 8010)
- ✅ learning-doc-generator (porta 8009)
- ✅ experiment-impact-analyzer (porta 8011)

**Serviços Faltantes para Fase 4:**
- ❌ requirements-engineering
- ❌ documentation-generation
- ❌ knowledge-graph-rag
- ❌ approval-gateway
- ❌ architect-agent
- ❌ orchestrator-dynamic

Este compose parece ser para testes de ML/experiments, não para o Fluxo G.

---

## Gaps Principais

### Gap 1: Worker Registration (CRÍTICO)

**Problema:** FluxoGWorkflow e activities não estão registrados no Temporal Worker.

**Impacto:** O workflow nunca será executado.

**Solução:**
```python
# Em temporal_worker.py, adicionar imports:
from src.workflows.fluxo_g_workflow import FluxoGWorkflow
from src.activities.fluxo_g_integration import (
    generate_requirements,
    generate_documentation,
    update_knowledge_graph,
    request_approval,
    query_knowledge_graph,
    set_fluxo_g_dependencies,
)

# Adicionar aos workflows registrados:
workflows=[OrchestrationWorkflow, DataMigrationWorkflow, FluxoGWorkflow],

# Adicionar às activities registradas:
activities=[
    # ... existing activities
    generate_requirements,
    generate_documentation,
    update_knowledge_graph,
    request_approval,
    query_knowledge_graph,
],
```

### Gap 2: Kafka Topics Configuration

**Problema:** Tópicos do Fluxo G não estão configurados como recursos Kafka.

**Impacto:** Tópicos criados com configurações padrão (não-ótimas).

**Solução:** Criar `infrastructure/kafka/topics/fluxo-g-topics.yaml` com as configurações do spec.

### Gap 3: Docker Compose Fase 4

**Problema:** Compose existente não inclui os serviços do Fluxo G.

**Impacto:** Impossível testar E2E o Fluxo G.

**Solução:** Atualizar `tests/e2e/docker-compose.fase4.yml` com todos os serviços necessários.

### Gap 4: Workflow Tests ImportError

**Problema:** `ModuleNotFoundError: No module named 'src.models.migration'` em `data_migration_workflow.py`.

**Impacto:** Testes do FluxoGWorkflow não podem rodar.

**Solução:** Criar o módulo faltante ou corrigir o import.

---

## Componentes Implementados vs Spec

| Componente | Spec | Implementado | Status |
|------------|------|--------------|--------|
| `fluxo_g_workflow.py` | ✓ | ✓ | Completamente implementado |
| `fluxo_g_integration.py` | ✓ | ✓ | 5 activities com stub fallback |
| Testes activities | ✓ | ✓ | 10/10 passando |
| Testes workflow | ✓ | ⚠️ | ImportError (não-related) |
| Worker registration | ✓ | ❌ | **NÃO registrado** |
| Kafka topics config | ✓ | ❌ | Não implementado |
| Docker compose Fase 4 | ✓ | ⚠️ | Incompleto |
| Kafka producer | ✓ | ❓ | Não verificado |

---

## Completude por Área

| Área | Completude | Notas |
|------|------------|-------|
| **Workflow Implementation** | 95% | Todos os 5 estágios implementados |
| **Activities Implementation** | 100% | 5 activities com stub fallback |
| **Activities Tests** | 100% | 10/10 passando |
| **Workflow Tests** | 0% | ImportError impede execução |
| **Worker Registration** | 0% | **CRÍTICO - Não registrado** |
| **Kafka Topics** | 0% | Config não existe |
| **Docker Compose** | 30% | Apenas serviços básicos |
| **Integração Kafka** | ? | Producer injection não verificado |

**Completude Global:** ~60%

---

## Ações Necessárias

### Prioridade ALTA (Bloqueante)

1. **Registrar FluxoGWorkflow no worker**
   - Importar workflow e activities
   - Adicionar à lista de workflows/activities
   - Injetar dependências HTTP via `set_fluxo_g_dependencies()`

2. **Corrigir ImportError em data_migration**
   - Criar `src/models/migration.py` ou corrigir import
   - Permitir que testes do workflow rodem

### Prioridade MÉDIA

3. **Criar configuração de tópicos Kafka**
   - Criar diretório `infrastructure/kafka/topics/`
   - Implementar `fluxo-g-topics.yaml`

4. **Atualizar docker-compose.fase4.yml**
   - Adicionar services: requirements-engineering, documentation-generation, etc.
   - Configurar redes e volumes

### Prioridade BAIXA

5. **Verificar injeção do Kafka Producer**
   - Confirmar que activities podem publicar eventos
   - Implementar publicação nos tópicos do Fluxo G

6. **Adicionar testes E2E**
   - Teste completo do pipeline G1-G5
   - Verificar publicação de eventos Kafka

---

## Próximos Passos

1. **CRÍTICO:** Corrigir worker registration do FluxoGWorkflow
2. Corrigir import error em data_migration
3. Rodar testes do workflow para verificar funcionamento
4. Implementar/verificar configuração de tópicos Kafka
5. Atualizar docker compose para testes E2E
6. Analisar Fase 5 (Hardening & Production)
