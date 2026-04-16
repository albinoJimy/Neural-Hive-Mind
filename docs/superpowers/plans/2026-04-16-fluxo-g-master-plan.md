# Fluxo G - Plano Mestre (Master Plan)

> **Epic 1: Fluxo G (Ideia → Software)**
> **Versão:** 1.0
> **Data:** 2026-04-16
> **Status:** Planning Complete

---

## Resumo Executivo

O **Fluxo G** é um pipeline automatizado que transforma ideias em linguagem natural em software funcional. Este plano detalha a implementação completa em **5 fases**, **62 tarefas**, estimadas em **26-31 semanas** (5-8 meses).

### Objetivos

1. **Automatizar** o caminho de idea → deployed software
2. **Integrar** serviços existentes (architect-agent, code-forge) com novos serviços
3. **Evitar duplicações** identificados na análise profunda
4. **Entregar** sistema production-ready com monitoring e operações

### Métricas de Sucesso

| Métrica | Target |
|---------|--------|
| Tempo idea → código | < 15 minutos |
| Qualidade do código | > 70% testes passando |
| Disponibilidade | > 99.5% uptime |
| Satisfação usuário | > 4.0/5.0 |

---

## Roadmap Visual

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          FLUXO G - ROADMAP 2026                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Q2 2026                    Q3 2026                    Q4 2026              │
│  ┌─────────┐              ┌─────────┐              ┌─────────┐            │
│  │  ABR    │              │  MAI    │              │  JUN    │            │
│  │         │              │         │              │         │            │
│  │ ▓▓▓▓▓▓▓▓ │              │ ▓▓▓▓▓▓▓▓ │              │ ▓▓▓▓▓▓▓▓ │            │
│  │ FASE 1  │──────────────▶│ FASE 2  │──────────────▶│ FASE 3  │            │
│  │Foundation│              │Core Svc  │              │Knowledge│            │
│  └─────────┘              └─────────┘              └─────────┘            │
│                                                                             │
│  Q3 2026                    Q4 2026                                         │
│  ┌─────────┐              ┌─────────┐                                      │
│  │  JUL    │              │  AGO    │                                      │
│  │         │              │         │                                      │
│  │ ▓▓▓▓▓▓▓▓ │──────────────▶│ ▓▓▓▓▓▓▓▓ │                                      │
│  │ FASE 4  │              │ FASE 5  │                                      │
│  │Integration│             │Hardening│                                      │
│  └─────────┘              └─────────┘                                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

  MILESTONES:

  ★ M1: Foundation Ready      (Fim Fase 1) - Sprint 4
  ★ M2: Core Services Ready    (Fim Fase 2) - Sprint 8
  ★ M3: Knowledge Ready        (Fim Fase 3) - Sprint 12
  ★ M4: Pipeline Functional     (Fim Fase 4) - Sprint 16
  ★ M5: Production Ready       (Fim Fase 5) - Sprint 20
```

---

## Detalhamento das Fases

### Fase 1: Foundation (Sprints 1-4, ~4 semanas)

**Objetivo:** Estender architect-agent para suportar Fluxo G

| Serviço | Ação | Esforço |
|---------|------|---------|
| architect-agent (8008) | ESTENDER - BoundedContexts, Diagrams, TechStack | 4 semanas |

**Novas Capacidades:**
- `BoundedContextsIdentifier` - Identifica contextos delimitados
- `ArchitectureDiagramGenerator` - Gera diagramas C4/Mermaid
- `TechStackRecommender` - Recomenda stack baseado em requisitos

**Dependências:** Nenhuma (pode começar imediatamente)

**Arquivo Detalhado:** `docs/superpowers/plans/2026-04-16-fluxo-g-fase1-foundation.md`

---

### Fase 2: Core Services (Sprints 5-8, ~6 semanas)

**Objetivo:** Criar serviços de Requirements e Documentation

| Serviço | Ação | Esforço |
|---------|------|---------|
| requirements-engineering (8010) | NOVO | 4 semanas |
| documentation-generation (8014) | NOVO | 3 semanas |

**Novos Serviços:**
- RequirementsEngineeringSystem: Gera user stories, acceptance criteria, data models
- DocumentationGenerationSystem: Gera README, OpenAPI, diagramas

**Dependências:** Fase 1 (usa architect-agent)

**Arquivo Detalhado:** `docs/superpowers/plans/2026-04-16-fluxo-g-fase2-core-services.md`

---

### Fase 3: Knowledge & Approvals (Sprints 9-12, ~6 semanas)

**Objetivo:** Criar serviços de RAG e Approval

| Serviço | Ação | Esforço |
|---------|------|---------|
| knowledge-graph-rag (8016) | NOVO | 4 semanas |
| approval-gateway (8017) | NOVO | 4 semanas |

**Novos Serviços:**
- KnowledgeGraphRAG: Busca híbrida Neo4j + Qdrant + Fallback
- ApprovalGateway: Aprovação cíclica com JWT tokens

**Dependências:** Fase 1 (usa architect-agent para context)

**Arquivo Detalhado:** `docs/superpowers/plans/2026-04-16-fluxo-g-fase3-knowledge-approvals.md`

---

### Fase 4: Orchestration Integration (Sprints 13-16, ~6 semanas)

**Objetivo:** Integrar todos os serviços no orchestrator-dynamic

| Serviço | Ação | Esforço |
|---------|------|---------|
| orchestrator-dynamic (8003) | INTEGRAR | 6 semanas |

**Novos Componentes:**
- Kafka topics (15 tópicos)
- Temporal workflow + activities
- REST API endpoints
- Pipeline store (MongoDB)
- Workers dedicados

**Dependências:** Fases 1-3 completas

**Arquivo Detalhado:** `docs/superpowers/plans/2026-04-16-fluxo-g-fase4-orchestration-integration.md`

---

### Fase 5: Testing & Hardening (Sprints 17-20, ~6 semanas)

**Objetivo:** Testes, segurança, performance, documentação

| Componente | Ação | Esforço |
|------------|------|---------|
| Load Tests | Locust scripts | 1 semana |
| Security Scans | Bandit, Safety, Trivy | 1 semana |
| Performance | Benchmarks + tuning | 2 semanas |
| Monitoring | Grafana dashboards | 1 semana |
| Documentation | Operations + Runbooks | 1 semana |

**Entregas:**
- 100% testes passando
- 0 vulnerabilidades críticas
- Dashboard operacional
- Runbooks completos

**Dependências:** Fase 4 completa

**Arquivo Detalhado:** `docs/superpowers/plans/2026-04-16-fluxo-g-fase5-testing-hardening.md`

---

## Arquitetura Final

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              FLUXO G PIPELINE                                  │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌─────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐        │
│  │  USER   │───▶│  REST API   │───▶│  TEMPORAL   │───▶│   WORKER    │        │
│  │ INTENT  │    │  (FastAPI)  │    │  WORKFLOW   │    │   ACTIVITIES │        │
│  └─────────┘    └─────────────┘    └─────────────┘    └──────┬──────┘        │
│                                                    │          │              │
│  ┌─────────────────────────────────────────────────┘          │              │
│                                                              │              │
│  ┌─────────────────────────────────────────────────────────────┼──────────┐  │
│  │                                                             │          │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │          │  │
│  │  │ Requirements │  │ Architecture  │  │     RAG      │     │          │  │
│  │  │   (8010)     │  │   (8008)     │  │   (8016)     │     │          │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘     │          │  │
│  │                                                            │          │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │          │  │
│  │  │  Docs Gen    │  │   Approval   │  │  Code Forge  │     │          │  │
│  │  │   (8014)     │  │   (8017)     │  │   (8005)     │     │          │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘     │          │  │
│  │                                                            │          │  │
│  └─────────────────────────────────────────────────────────────┼──────────┘  │
│                                                              │              │
│  ┌─────────────────────────────────────────────────────────────┘              │
│                                                              │              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │    Kafka     │  │   MongoDB    │  │    Redis     │  │  Temporal    │   │
│  │   (Events)   │  │  (Persist)   │  │   (Cache)    │  │ (Orchestration)│ │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘   │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Serviços Consolidados

### Serviços Estendidos (3)

| Serviço | Extensões | Status |
|---------|-----------|--------|
| architect-agent (8008) | BoundedContexts, Diagrams, TechStack | Fase 1 |
| code-forge (8005) | Integração via activities | Fase 4 |
| orchestrator-dynamic (8003) | Workflow, API, Workers | Fase 4 |

### Novos Serviços (5)

| Serviço | Porta | Descrição | Fase |
|---------|-------|-----------|------|
| requirements-engineering | 8010 | Gera requisitos, user stories | Fase 2 |
| documentation-generation | 8014 | Gera docs, diagramas | Fase 2 |
| knowledge-graph-rag | 8016 | RAG híbrido Neo4j+Qdrant | Fase 3 |
| approval-gateway | 8017 | Aprovação cíclica JWT | Fase 3 |

---

## Cronograma Detalhado

### Sprint 1-4 (4 semanas): Foundation

| Sprint | Foco | Entregas |
|--------|------|----------|
| 1 | BoundedContexts | Identificador de contextos |
| 2 | Diagram Generator | C4/Mermaid diagrams |
| 3 | TechStack Recommender | Recomendação de stack |
| 4 | Integration | Arquitet-agent estendido |

**Milestone M1:** Foundation Ready

### Sprint 5-8 (4 semanas): Core Services

| Sprint | Foco | Entregas |
|--------|------|----------|
| 5 | Requirements Service | User stories, acceptance criteria |
| 6 | Requirements API | REST endpoints |
| 7 | Documentation Service | README, OpenAPI |
| 8 | Integration | Core services integrados |

**Milestone M2:** Core Services Ready

### Sprint 9-12 (6 semanas): Knowledge & Approvals

| Sprint | Foco | Entregas |
|--------|------|----------|
| 9 | RAG Foundation | Neo4j+Qdrant client |
| 10 | RAG Query Engine | Hybrid search |
| 11 | Approval Gateway | JWT tokens, cyclic workflow |
| 12 | Integration | Knowledge & Approval integrados |

**Milestone M3:** Knowledge Ready

### Sprint 13-16 (6 semanas): Orchestration

| Sprint | Foco | Entregas |
|--------|------|----------|
| 13 | Kafka Topics | 15 tópicos criados |
| 14 | Temporal Workflow | Pipeline workflow |
| 15 | REST API | Endpoints de pipeline |
| 16 | Workers | Workers dedicados |

**Milestone M4:** Pipeline Functional

### Sprint 17-20 (6 semanas): Hardening

| Sprint | Foco | Entregas |
|--------|------|----------|
| 17 | Load Tests | Locust scripts |
| 18 | Security | Scans, rate limiting |
| 19 | Performance | Benchmarks, tuning |
| 20 | Documentation | Ops, runbooks |

**Milestone M5:** Production Ready

---

## Matriz de Dependências

```
Fase 1 (Foundation)
   │
   └──▶ Fase 2 (Core Services)
           │
           ├──▶ Fase 3 (Knowledge & Approvals)
           │       │
           │       └──▶ Fase 4 (Orchestration)
           │               │
           └───────────────┴──▶ Fase 5 (Hardening)
```

### Dependências Técnicas

| Fase | Dependências |
|------|--------------|
| Fase 1 | Nenhuma |
| Fase 2 | Fase 1 (architect-agent) |
| Fase 3 | Fase 1 (architect-agent context) |
| Fase 4 | Fases 1, 2, 3 completas |
| Fase 5 | Fase 4 completa |

---

## Recursos Necessários

### Time

| Papel | FTE | Duração |
|-------|-----|---------|
| Backend Engineer | 2 | 6 meses |
| ML Engineer | 1 | 3 meses |
| DevOps Engineer | 1 | 6 meses |
| QA Engineer | 1 | 4 meses |
| Tech Writer | 1 | 2 meses |

### Infraestrutura

| Recurso | Quantidade | Especificação |
|---------|-----------|---------------|
| Nodes K8s | 6+ | 4 CPU, 16GB RAM |
| Kafka Cluster | 1 | 3 brokers |
| MongoDB | 1 | 3-node replica set |
| Redis | 1 | 6GB RAM |
| Neo4j | 1 | 4GB RAM |
| Qdrant | 1 | 4GB RAM |
| Temporal | 1 | 2GB RAM |

---

## Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| LLM API rate limit | Média | Alto | Fallback templates, cache |
| Performance RAG | Baixa | Médio | Fallback rápido, hybrid search |
| Aprovação bottleneck | Média | Alto | Auto-approve timeout, async |
| Worker OOM | Baixa | Médio | Memory profiling, limits |
| Service dependencies | Alta | Alto | Circuit breakers, retries |

---

## Gates de Aprovação

Cada fase requer aprovação antes de prosseguir:

### Gate 1 (Após Fase 1)
- [ ] architect-agent estendido funciona
- [ ] Diagramas C4 gerados corretamente
- [ ] TechStack recommender retorna valores válidos
- [ ] Testes unitários passando

### Gate 2 (Após Fase 2)
- [ ] Requirements service gera user stories válidos
- [ ] Documentation service gera docs corretamente
- [ ] APIs REST funcionam
- [ ] Integração com architect-agent funciona

### Gate 3 (Após Fase 3)
- [ ] RAG retorna resultados relevantes
- [ ] Fallback funciona quando RAG falha
- [ ] Approval workflow completo funciona
- [ ] JWT tokens seguros

### Gate 4 (Após Fase 4)
- [ ] Pipeline end-to-end funciona
- [ ] Kafka events publicados
- [ ] Workers processam activities
- [ ] REST API completa funcional

### Gate 5 (Após Fase 5)
- [ ] Load tests passam (baseline atingido)
- [ ] 0 vulnerabilidades críticas
- [ ] Performance targets atingidos
- [ ] Documentação completa
- [ ] Runbooks testados

---

## Monitoramento e KPIs

### KPIs de Desenvolvimento

| KPI | Target | Mensuração |
|-----|--------|-----------|
| Velocidade | >2 tarefas/sprint | Burndown chart |
| Qualidade | <5 bugs/sprint | Bug tracker |
| Coverage | >70% | pytest-cov |
| Cycle time | <2 dias/tarefa | Git analytics |

### KPIs de Produção

| KPI | Target | Alerta |
|-----|--------|--------|
| Pipeline success rate | >95% | <90% |
| Pipeline duration (p95) | <15min | >20min |
| API latency (p95) | <500ms | >1s |
| Error rate | <1% | >5% |
| Availability | >99.5% | <99% |

---

## Plano de Rollout

### Ambiente de Desenvolvimento

- Disponível imediatamente
- Docker Compose local
- Features experimentais

### Ambiente de Staging

- Deploy ao final de Fase 4
- Kubernetes namespace `staging`
- Testes de aceitação

### Ambiente de Produção

- Deploy gradual após Fase 5
- Canary: 10% → 50% → 100%
- Feature flags para rollback rápido

---

## Pós-Launch

### Iteração 1 (Mês 1-2 pós-launch)
- Coletar feedback de usuários
- Ajustar prompts LLM
- Otimizar performance

### Iteração 2 (Mês 3-4 pós-launch)
- Adicionar novos templates
- Melhorar RAG accuracy
- Expandir documentação

### Iteração 3 (Mês 5-6 pós-launch)
- Machine learning online
- Auto-tuning de parâmetros
- Expansão para outros fluxos

---

## Documentação Relacionada

| Documento | Caminho |
|-----------|---------|
| Análise de Duplicações | `docs/ANALISE_PROFUNDA_DUPLICACOES_COMPLETUDE_2026-04-15.md` |
| Integração Fluxo G | `docs/INTEGRACAO_FLUXOS_SERVICOS_FALTANTES.md` |
| Fase 1 Detalhado | `docs/superpowers/plans/2026-04-16-fluxo-g-fase1-foundation.md` |
| Fase 2 Detalhado | `docs/superpowers/plans/2026-04-16-fluxo-g-fase2-core-services.md` |
| Fase 3 Detalhado | `docs/superpowers/plans/2026-04-16-fluxo-g-fase3-knowledge-approvals.md` |
| Fase 4 Detalhado | `docs/superpowers/plans/2026-04-16-fluxo-g-fase4-orchestration-integration.md` |
| Fase 5 Detalhado | `docs/superpowers/plans/2026-04-16-fluxo-g-fase5-testing-hardening.md` |

---

## Aprovação

| Papel | Nome | Assinatura | Data |
|-------|------|------------|------|
| Product Owner | |___________|____|
| Tech Lead | |___________|____|
| Architecture | |___________|____|
| DevOps | |___________|____|
| Security | |___________|____|

---

## Changelog

| Data | Versão | Mudança |
|------|--------|---------|
| 2026-04-16 | 1.0 | Plano inicial completo |

---

*Plano Mestre criado em 2026-04-16*
*Total: 62 tarefas em 5 fases, 26-31 semanas*
*Owner: Neural-Hive-Mind Team*
