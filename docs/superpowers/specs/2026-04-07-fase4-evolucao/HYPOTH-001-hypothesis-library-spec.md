# HYPOTH-001: Biblioteca Persistente de Hipóteses

**Data:** 2026-04-07
**Prioridade:** ALTA
**Estimativa:** L (2-3 semanas)

---

## Metadata

| Campo | Valor |
|-------|-------|
| Componente | Hypothesis Library |
| Localização | services/hypothesis-library/ |
| Status Atual | PARCIAL (40%) |
| Status Alvo | IMPLEMENTADO (90%+) |

---

## 1. Validação Funcionalidade

### 1.1 Funcionalidade Esperada

Baseado na especificação da Fase 4, o componente deve:
- Biblioteca persistente de hipóteses com versionamento
- Ciclo de vida completo: proposta → aprovada → em_teste → concluída
- Tracking de resultados e aprendizados
- Busca e consulta avançada
- Integração com motor de experimentação

### 1.2 Funcionalidade Implementada

**Atual:**
- Modelo `OptimizationHypothesis` existe (96 linhas)
- Método `to_experiment_request()` para conversão
- Validação de viabilidade

**Gaps Identificados:**
- ❌ Biblioteca persistente não existe (só modelo)
- ❌ Sem versionamento de hipóteses
- ❌ Sem tracking de resultados
- ❌ Sem API REST dedicada
- ❌ Sem busca/consulta avançada

### 1.3 Gaps de Funcionalidade

- [x] HYPOTH-001-01: Criar serviço `hypothesis-library` ✅ (2026-04-09)
- [x] HYPOTH-001-02: Implementar persistência MongoDB de hipóteses ✅ (2026-04-09)
- [x] HYPOTH-001-03: Implementar versionamento de hipóteses ✅ (2026-04-09)
- [x] HYPOTH-001-04: Implementar ciclo de vida (workflow) ✅ (2026-04-09)
- [x] HYPOTH-001-05: Criar API REST completa ✅ (2026-04-09)
- [x] HYPOTH-001-06: Implementar busca e filtros avançados ✅ (2026-04-09)
- [x] HYPOTH-001-07: Integração com ExperimentationEngine ✅ (2026-04-09)
- [x] HYPOTH-001-08: Sistema de aprovação de hipóteses ✅ (2026-04-09)

---

## 2. Validação Testes

### 2.1 Cobertura Unitária

**Atual:** N/A

**Gaps:**
- [ ] HYPOTH-001-09: Testar CRUD de hipóteses
- [ ] HYPOTH-001-10: Testar versionamento
- [ ] HYPOTH-001-11: Testar workflow de estados
- [ ] HYPOTH-001-12: Testar busca e filtros

### 2.2 Cobertura Integração

**Gaps:**
- [ ] HYPOTH-001-13: Teste E2E de criação até experimento
- [ ] HYPOTH-001-14: Teste de integração com ExperimentationEngine
- [ ] HYPOTH-001-15: Teste de aprovação/rejeição

---

## 3. Validação Integração

### 3.1 Dependências Externas

| Serviço | Método | Status |
|---------|--------|--------|
| MongoDB | Persistência | ❌ |
| ExperimentationEngine | Criação de experimentos | ⚠️ Parcial |
| Kafka | Eventos | ❌ |
| MLflow | Resultados | ❌ |

### 3.2 Gaps de Integração

- [ ] HYPOTH-001-16: MongoDB collection para hipóteses
- [ ] HYPOTH-001-17: Producer Kafka para eventos de hipóteses
- [ ] HYPOTH-001-18: Consumer para resultados de experimentos
- [ ] HYPOTH-001-19: Integração com ExperimentationEngine

---

## 4. Validação Observabilidade

### 4.1 Métricas Prometheus

**Gaps:**
- [ ] HYPOTH-001-20: `hypothesis_created_total`
- [ ] HYPOTH-001-21: `hypothesis_approved_total`
- [ ] HYPOTH-001-22: `hypothesis_tested_total`
- [ ] HYPOTH-001-23: `hypothesis_status_current{status}`

### 4.2 Tracing OpenTelemetry

**Gaps:**
- [ ] HYPOTH-001-24: Spans para operações CRUD
- [ ] HYPOTH-001-25: Spans para workflow

### 4.3 Logging Structlog

**Gaps:**
- [ ] HYPOTH-001-26: Logs estruturados de mudanças de estado
- [ ] HYPOTH-001-27: Logs de aprovações

---

## 5. Validação Documentação

### 5.1 Documentação Técnica

| Doc | Existe | Localização |
|-----|--------|-------------|
| README | ❌ | — |
| API Docs | ❌ | — |
| Workflow Guide | ❌ | — |

### 5.2 Gaps de Documentação

- [ ] HYPOTH-001-28: README com instruções
- [ ] HYPOTH-001-29: API Documentation (OpenAPI)
- [ ] HYPOTH-001-30: Guia de workflow de hipóteses
- [ ] HYPOTH-001-31: Exemplos de hipóteses bem-sucedidas

---

## 6. Tickets Decompostos

### HYPOTH-001-01: Criar serviço `hypothesis-library`

**Tipo:** feature
**Estimativa:** S (2-3 dias)
**Status:** ✅ COMPLETO (2026-04-09)

**Descrição:**
Criar estrutura do serviço FastAPI.

**Acceptance Criteria:**
- [x] Projeto criado com FastAPI
- [x] Configuração (settings, logging, MongoDB)
- [x] Dockerfile e docker-compose
- [x] Health check endpoint
- [x] Estrutura de diretórios

---

### HYPOTH-001-02: Implementar persistência MongoDB de hipóteses

**Tipo:** feature
**Estimativa:** M (1 semana)
**Status:** ✅ COMPLETO (2026-04-09)

**Descrição:**
Implementar models e repository para hipóteses.

**Acceptance Criteria:**
- [x] Schema MongoDB (Pydantic models)
- [x] `Hypothesis` model com campos completos
- [x] `HypothesisRepository` class
- [x] Indexes: status, created_at, tags, author
- [x] CRUD operations
- [x] Testes de integração

**Model Schema:**
```python
class Hypothesis(BaseModel):
    id: PyObjectId
    title: str
    description: str
    background: str  # Por que esta hipótese é relevante
    expected_outcome: str
    metrics: List[str]  # Métricas que serão afetadas
    status: HypothesisStatus
    author: str
    tags: List[str]
    created_at: datetime
    updated_at: datetime
    versions: List[int]  # Version history
    current_version: int
    experiment_id: Optional[str]
    results: Optional[HypothesisResults]
```

---

### HYPOTH-001-03: Implementar versionamento de hipóteses

**Tipo:** feature
**Estimativa:** M (1 semana)
**Status:** ✅ COMPLETO (2026-04-09)

**Descrição:**
Implementar versionamento completo de hipóteses.

**Acceptance Criteria:**
- [x] `HypothesisVersion` model
- [x] Sistema de versionamento (create_version, get_version, list_versions)
- [x] Comparação entre versões (diff)
- [x] Revert para versão anterior
- [x] Testes de versionamento

---

### HYPOTH-001-04: Implementar ciclo de vida (workflow)

**Tipo:** feature
**Estimativa:** M (1 semana)
**Status:** ✅ COMPLETO (2026-04-09)

**Descrição:**
Implementar workflow de estados da hipótese.

**Estados:**
- `DRAFT` - Rascunho inicial
- `PROPOSED` - Proposta para revisão
- `APPROVED` - Aprovada para teste
- `IN_TESTING` - Experimento em andamento
- `COMPLETED` - Experimento concluído
- `ACCEPTED` - Hipótese validada
- `REJECTED` - Hipótese refutada
- `ARCHIVED` - Arquivada

**Acceptance Criteria:**
- [x] `HypothesisStatus` enum
- [x] Máquina de estados com transições válidas
- [x] `transition_to()` method com validação
- [x] Eventos Kafka em cada transição
- [x] Testes de transições

---

### HYPOTH-001-05: Criar API REST completa

**Tipo:** feature
**Estimativa:** M (1 semana)
**Status:** ✅ COMPLETO (2026-04-09)

**Descrição:**
Implementar API REST para gerenciar hipóteses.

**Endpoints:**
- `POST /api/v1/hypotheses` - Criar hipótese
- `GET /api/v1/hypotheses` - Listar (com filtros)
- `GET /api/v1/hypotheses/{id}` - Obter hipótese
- `PUT /api/v1/hypotheses/{id}` - Atualizar
- `DELETE /api/v1/hypotheses/{id}` - Arquivar
- `POST /api/v1/hypotheses/{id}/propose` - Propor
- `POST /api/v1/hypotheses/{id}/approve` - Aprovar
- `POST /api/v1/hypotheses/{id}/reject` - Rejeitar
- `POST /api/v1/hypotheses/{id}/start-test` - Iniciar teste
- `POST /api/v1/hypotheses/{id}/complete` - Completar
- `GET /api/v1/hypotheses/{id}/versions` - Listar versões

**Acceptance Criteria:**
- [x] Todos os endpoints implementados
- [x] Validação de requests
- [x] Paginação e filtros
- [x] OpenAPI documentation
- [x] Testes de integração

---

### HYPOTH-001-06: Implementar busca e filtros avançados

**Tipo:** feature
**Estimativa:** S (2-3 dias)
**Status:** ✅ COMPLETO (2026-04-09)

**Descrição:**
Implementar busca avançada com filtros múltiplos.

**Acceptance Criteria:**
- [x] Busca por texto (title, description)
- [x] Filtro por status
- [x] Filtro por autor
- [x] Filtro por tags
- [x] Filtro por intervalo de datas
- [x] Ordenação (created_at, updated_at, title)
- [x] Agregações (count by status)

---

### HYPOTH-001-07: Integração com ExperimentationEngine

**Tipo:** feature
**Estimativa:** M (1 semana)
**Status:** ✅ COMPLETO (2026-04-09)

**Descrição:**
Integrar criação de experimentos a partir de hipóteses.

**Acceptance Criteria:**
- [x] Método `to_experiment_request()` melhorado
- [x] Cliente HTTP/gRPC para ExperimentationEngine
- [x] Criação automática de experimento ao aprovar hipótese
- [x] Atualização do experiment_id na hipótese
- [x] Callback ao completar experimento
- [x] Testes de integração

---

### HYPOTH-001-08: Sistema de aprovação de hipóteses

**Tipo:** feature
**Estimativa:** M (1 semana)
**Status:** ✅ COMPLETO (2026-04-09)

**Descrição:**
Implementar sistema de aprovação com revisão.

**Acceptance Criteria:**
- [x] Lista de revisores
- [x] Aprovação pode requerer N revisores
- [x] Comentários em hipóteses
- [x] Notificação (Slack/Kafka) em proposta
- [x] Histórico de aprovações
- [x] Testes de workflow

---

## 7. Workflow Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        HYPOTHESIS LIFECYCLE                             │
└─────────────────────────────────────────────────────────────────────────┘

    [DRAFT]                [PROPOSED]              [APPROVED]
       │                      │                       │
       │ create               │ propose               │ approve
       ▼                      ▼                       ▼
   ┌───────┐             ┌───────────┐          ┌───────────┐
   │ Author│             │ Reviewers │          │ Reviewers │
   └───────┘             └───────────┘          └───────────┘
       │                      │                       │
       │                      │ reject                │
       ▼                      ▼                       ▼
   [ARCHIVED]           [REJECTED]           [IN_TESTING]
                                                  │
                                                  │ start_experiment
                                                  ▼
                                           ┌──────────────┐
                                           │ Experiment   │
                                           │ Running...   │
                                           └──────────────┘
                                                  │
                                    ┌─────────────┴─────────────┐
                                    │                           │
                                    │ complete                  │ fail
                                    ▼                           ▼
                              [COMPLETED]              [REJECTED]
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
                    │ validated                     │ refuted
                    ▼                               ▼
                [ACCEPTED]                     [REJECTED]
                    │                               │
                    └───────────────┬───────────────┘
                                    │
                                    │ archive_after (180 days)
                                    ▼
                               [ARCHIVED]
```

---

## 8. Resumo Executivo

**Completude Atual:** 40%
**Completude Alvo:** 90%
**Gaps Totais:** 31
**Tickets Propostos:** 8 (acima) + 23 (detalhados nos gaps)
**Estimativa Total:** L (2-3 semanas)

**Dependências:**
- MongoDB
- Kafka
- ExperimentationEngine
- MLflow (opcional)

**Riscos:**
- Workflow pode ser complexo demais
- Necessidade de governança de aprovações

**Mitigações:**
- Começar com workflow simples (draft→approved→testing→completed)
- Governança opcional (configurável)
- Documentação clara de processo
