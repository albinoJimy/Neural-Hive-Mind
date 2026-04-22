# Design: Analyst Agent Greenfield Expansion

> **Data:** 2026-04-22
> **Status:** Design Aprovado
> **Epic:** Expandir Analyst Agent para Greenfield Analysis

---

## Resumo Executivo

Expandir o **Analyst Agent** para analisar o impacto de criação de **novos sistemas** (greenfield) no Neural Hive Mind, detectando colisões técnicas, dependências, conflitos de regras de negócio e problemas de infraestrutura **antes** da implementação.

### Problema

Actualmente, o Fluxo G (pipeline de geração de software) não valida se um novo sistema irá:
- Colidir com serviços existentes (portas, rotas, topics Kafka)
- Criar dependências inválidas ou circulares
- Conflitar com regras de negócio existentes
- Sobrecarregar a infraestrutura
- Seguir os padrões arquitecturais da plataforma

### Solução

Integrar o Analyst Agent no Fluxo G através de **3 checkpoints de análise**, usando um novo endpoint REST que orquestra múltiplos analisadores especializados.

---

## Arquitectura

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         FLUXO G PIPELINE                                 │
│                                                                          │
│  Intent → Cognitive Plan → G0 → G1 → G1.5 → G2 → G3 → G3.5 → G4 → G5  │
│                              ↑      ↑            ↑                       │
│                         CHECKPOINTS DE ANÁLISE                          │
│                                                                          │
└───────────────────────────────┬┬┬────────────────────────────────────────┘
                                │││
                                └┴┴──────────────────┐
                                                     │
                                     HTTP POST       │
                                  /api/v1/greenfield/analyze
                                                     │
┌─────────────────────────────────────────────────────────────────────────┐
│                      ANALYST AGENT (EXPANDIDO)                           │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │           GREENFIELD ANALYZER SERVICE (NOVO)                        │ │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────────┐   │ │
│  │  │ Collision       │  │ Dependency      │  │ Infrastructure   │   │ │
│  │  │ Detector        │  │ Analyzer        │  │ Analyzer         │   │ │
│  │  └─────────────────┘  └─────────────────┘  └──────────────────┘   │ │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────────┐   │ │
│  │  │ Business Rule   │  │ Architecture    │  │ Impact           │   │ │
│  │  │ Validator       │  │ Validator        │  │ Aggregator       │   │ │
│  │  └─────────────────┘  └─────────────────┘  └──────────────────┘   │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                   │                                     │
│  ┌────────────────────────────────┴──────────────────────────────────┐ │
│  │                      DATA SOURCES ADAPTERS                          │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │ │
│  │  │ Service  │  │ Knowledge│  │ Kafka    │  │ Static Code      │  │ │
│  │  │ Registry │  │ Graph    │  │ Metadata │  │ Analyzer         │  │ │
│  │  │ Client   │  │ Client   │  │ Client   │  │                  │  │ │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘  │ │
│  └────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## API Contract

### Request

```python
POST /api/v1/greenfield/analyze

{
  "checkpoint": "G0" | "G1.5" | "G3.5",
  "plan_id": str,
  "cognitive_plan": {
    "plan_id": str,
    "summary": str,
    "proposed_services": [
      {
        "name": str,
        "port": int,
        "routes": List[str],
        "kafka_topics": List[str],
        "dependencies": List[str],
        "business_rules": List[str]
      }
    ]
  },
  "requirements": dict | None,
  "architecture": dict | None
}
```

### Response

```python
{
  "analysis_id": str,
  "checkpoint": str,
  "status": "approved" | "rejected" | "warning",
  "blocking_issues": List[BlockingIssue],
  "risks": List[Risk],
  "suggestions": List[Suggestion],
  "summary": {
    "collision_count": int,
    "dependency_count": int,
    "infrastructure_score": float,
    "architecture_compliance": float,
    "business_rule_conflicts": int
  }
}
```

### Models

```python
class BlockingIssue(BaseModel):
    category: "COLLISION" | "DEPENDENCY" | "CAPACITY" | "BUSINESS_RULE_COLLISION"
    severity: "CRITICAL" | "HIGH" | "MEDIUM"
    description: str
    affected_component: str
    suggested_fix: str
    blocks_pipeline: bool = True

class Risk(BaseModel):
    category: str
    probability: float
    impact: "LOW" | "MEDIUM" | "HIGH"
    description: str
    mitigation: str

class Suggestion(BaseModel):
    type: "RENAME" | "RECONFIGURE" | "REUSE" | "REFACTOR"
    target: str
    current_value: Any
    suggested_value: Any
    reasoning: str
    confidence: float
```

---

## Analisadores Especializados

### 1. CollisionDetector

Detecta colisões técnicas:
- **Portas:** Serviço com mesma porta TCP
- **Nomes:** Serviço com mesmo nome
- **Rotas API:** Mesmo path em router
- **Topics Kafka:** Mesmo topic name

### 2. DependencyAnalyzer

Analisa dependências:
- Serviços dependentes não existem
- Cadeias de dependência muito profundas
- Dependências circulares potenciais

### 3. BusinessRuleValidator

Valida regras de negócio via embeddings:
- **Duplicadas:** Similaridade > 0.9
- **Conflitantes:** Similaridade 0.7-0.9
- **Sobrepostas:** Similaridade 0.5-0.7

### 4. InfrastructureAnalyzer

Analisa carga em infraestrutura:
- MongoDB: Tamanho de collections, índices
- Kafka: Partitions, consumer groups
- Redis: Memória usada
- Compute: CPU/Memory disponível

### 5. ArchitectureValidator

Valida conformidade arquitectural:
- Padrões da plataforma (microservices, event-driven)
- Conventions (naming, estrutura)
- Best practices (separation of concerns)

---

## Data Sources

| Fonte | Tipo | Queries | Implementação |
|-------|------|---------|---------------|
| Service Registry | MongoDB | get_all_services, get_service_by_port, get_service_by_name | Estender cliente existente |
| Knowledge Graph | Neo4j | dependency_graph, find_business_rules | Estender cliente existente |
| Kafka Metadata | Admin API | list_topics, get_topic_info, check_topic_exists | **Novo cliente** |
| Static Code | Git + AST | analyze_service_definition, extract_routes, extract_port | **Novo analisador** |

---

## Checkpoints do Fluxo G

| Checkpoint | Momento | Profundidade | Análises |
|------------|---------|--------------|----------|
| **G0** | Antes de gerar requisitos | Básica | CollisionDetector |
| **G1.5** | Depois de requirements | Média | + DependencyAnalyzer, BusinessRuleValidator |
| **G3.5** | Antes de aprovação | Completa | + InfrastructureAnalyzer, ArchitectureValidator |

---

## Integração Temporal

### Activity

```python
@activity.defn
async def analyze_greenfield_impact(
    checkpoint: str,
    cognitive_plan: dict,
    requirements: dict = None,
    architecture: dict = None
) -> dict:
    """Chama Analyst Agent para análise de impacto"""
    # Chama POST /api/v1/greenfield/analyze
    # Se status == "rejected", lança ApplicationError
    # Return result
```

### Workflow Modificado

```python
class FluxoGWorkflow:
    @workflow.run
    async def run(self, cognitive_plan: dict, original_intent: str) -> dict:
        # G0: Análise inicial
        g0_analysis = await workflow.execute_activity(
            analyze_greenfield_impact,
            args=["G0", cognitive_plan],
            ...
        )
        if g0_analysis["status"] == "rejected":
            return {"status": "rejected_at_g0", ...}

        # G1: Requirements
        requirements = await workflow.execute_activity(
            generate_requirements, ...
        )

        # G1.5: Análise técnica
        g1_5_analysis = await workflow.execute_activity(
            analyze_greenfield_impact,
            args=["G1.5", cognitive_plan, requirements],
            ...
        )
        if g1_5_analysis["status"] == "rejected":
            return {"status": "rejected_at_g1_5", ...}

        # G2-G3: Documentation, Knowledge Graph
        ...

        # G3.5: Análise completa
        g3_5_analysis = await workflow.execute_activity(
            analyze_greenfield_impact,
            args=["G3.5", cognitive_plan, requirements, architecture],
            ...
        )

        # G4: Approval (com análise no contexto)
        approval = await workflow.execute_activity(
            request_approval,
            args=["greenfield_analysis", {"context": g3_5_analysis}],
            ...
        )
        ...
```

---

## Estrutura de Ficheiros

```
services/analyst-agents/
├── src/
│   ├── api/
│   │   └── greenfield.py                    # NOVO
│   ├── services/
│   │   └── greenfield/
│   │       ├── __init__.py
│   │       ├── analyzer_service.py          # NOVO
│   │       ├── collision_detector.py        # NOVO
│   │       ├── dependency_analyzer.py       # NOVO
│   │       ├── infrastructure_analyzer.py   # NOVO
│   │       ├── business_rule_validator.py   # NOVO
│   │       ├── architecture_validator.py    # NOVO
│   │       └── models.py                    # NOVO
│   ├── clients/
│   │   ├── kafka_metadata_client.py         # NOVO
│   │   ├── static_code_analyzer.py          # NOVO
│   │   ├── service_registry_client.py       # ESTENDER
│   │   └── knowledge_graph_client.py        # ESTENDER
│   └── main.py                              # ADICIONAR ROUTER
├── tests/
│   ├── unit/greenfield/                     # NOVO
│   ├── integration/test_greenfield_analyzer_integration.py  # NOVO
│   └── e2e/test_fluxo_g_greenfield_e2e.py                   # NOVO
└── docs/GREENFIELD_ANALYZER.md              # NOVO

services/orchestrator-dynamic/
├── src/
│   ├── activities/fluxo_g_integration.py    # ADICIONAR ACTIVITY
│   └── workflows/fluxo_g_workflow.py        # ADICIONAR CHECKPOINTS
```

---

## Plano de Implementação

| Fase | Duração | Tarefas |
|------|---------|---------|
| 1: Foundation | 2-3 dias | Estrutura greenfield/, models.py, endpoint stub |
| 2: Collision | 2-3 dias | CollisionDetector, ServiceRegistry estendido, KafkaMetadataClient |
| 3: Dependencies | 2 dias | DependencyAnalyzer, KnowledgeGraph estendido |
| 4: Business Rules | 2-3 dias | BusinessRuleValidator, embeddings |
| 5: Static Analysis | 2 dias | StaticCodeAnalyzer, parsers |
| 6: Orchestration | 2-3 dias | Activity Temporal, FluxoGWorkflow modificado |
| 7: Testing | 2 dias | Testes E2E, load tests, documentação |

**Total: 15-18 dias**

---

## Critérios de Sucesso

- [ ] Detecta colisões de portas, rotas, topics com >95% de precisão
- [ ] Identifica dependências inválidas e circulares
- [ ] Detecta conflitos de regras de negócio com similaridade >0.7
- [ ] Integração com Fluxo G em 3 checkpoints funcionais
- [ ] Testes E2E passando (rejeição em G0, G1.5, G3.5)
- [ ] Latência de análise < 60 segundos (G3.5)
- [ ] Cache Redis reduz latência em >50% para análises repetidas

---

## Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Service Registry inconsistente | Média | Alto | Validar dados + fallback para análise estática |
| Knowledge Graph incompleto | Alta | Médio | Preencher com scraping + manual |
| Análise estática lenta | Média | Médio | Cache agressivo + shallow clone |
| Embeddings imprecisos | Baixa | Médio | Threshold ajustável + revisão manual |

---

## Próximos Passos

1. Criar spec detalhado no Agent OS
2. Criar branch `feat/GAPS-greenfield-analyst`
3. Implementar Fase 1 (Foundation)
4. Iterar pelas fases seguintes
5. Integration testing com Fluxo G
6. Documentação e deploy

---

*Aprovado em 2026-04-22*
