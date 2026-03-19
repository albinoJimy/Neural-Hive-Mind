# Feature Map — Neural-Hive-Mind

**Projecto:** Neural-Hive-Mind
**Última Actualização:** 2026-03-18
**Completude Global:** ~90%

---

## Visão Geral dos Serviços (28)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     SERVIÇOS CORE (8)                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Gateway           ████████████████████████████████████░░░  90%        │
│  STE               ████████████████████████████████████░░  90%        │
│  Consensus         ████████████████████████████████████░░  90%        │
│  Orchestrator      ███████████████████████████████████░░░  85%        │
│  Approval          ████████████████████████████████████████  95%        │
│  Worker Agents     ████████████████████████████████░░░░░░░  75%        │
│  Queen Agent       ████████████████████████████████░░░░░░░  75%        │
│  Service Registry  ████████████████████████████████████░░░  85%        │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                     AGENTES ESPECIALIZADOS (8)                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Analyst           ████████████████████████████████████████ 100%       │
│  Scout             ████████████████████████████████████████████ 100%       │
│  Guard             ██████████████████████████████████░░░  85%        │
│  Optimizer         ████████████████████████████████████████ 100%       │
│  Self-Healing      ██████████████████████████░░░░░░░░░░  55%        │
│  Execution Tickets █████████████████████████████████░░░░  85%        │
│  SLA Management    ████████████████████████████████░░░░░  75%        │
│  Code Forge        ████████████████████████████░░░░░░░░░  65%        │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                     BIBLIOTECAS PYTHON (8)                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Domain            ████████████████████████████████████████ 100%        │
│  Specialists       ███████████████████████████████████░░░░  90%        │
│  Agent SDK         ████████████████████████████████████░░░  85%        │
│  Observability     ████████████████████████████████████████  95%        │
│  ML                ██████████████████████████████████░░░░░  75%        │
│  Resilience        ███████████████████████████████████░░░░  85%        │
│  Risk Scoring      █████████████████████████████████░░░░░░  80%        │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                     INFRAESTRUTURA (6)                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  MCP Servers       ████████████████████████████████████████ 100%        │
│  MCP Tool Catalog  ██████████████████████████████░░░░░░░  70%        │
│  OPA               ████████████████████████████████░░░░░  80%        │
│  Memory Layer      ████████████████████████████████░░░░  75%        │
│  Explainability    ████████████████████████████████████░░  65%        │
│  Infra K8s         █████████████████████████████████░░░░░  80%        │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Serviços Core — Detalhe

### Gateway de Intenções (90%)
- [x] NLU Pipeline
- [x] ASR Pipeline (voz)
- [x] Roteamento adaptativo
- [x] Cache Redis
- [x] Observabilidade
- [x] Segurança OAuth2/Keycloak
- [ ] PII masking avançado

### Semantic Translation Engine (90%)
- [x] Tradução de intenções
- [x] Geração de CognitivePlan
- [x] Enrichment de contexto
- [x] Campo `original_intent_text` implementado
- [ ] Multi-idioma

### Consensus Engine (100%)
- [x] Consenso ponderado
- [x] Deduplicação de opiniões
- [x] Logging detalhado
- [x] Integração Kafka
- [x] Consenso hierárquico (GAPS-03) - 5 níveis de senioridade, 132 testes ✅

### Orchestrator Dynamic (85%)
- [x] Conversão Plans → Tickets
- [x] Orquestração Temporal
- [x] SLA monitoring
- [x] Flow C complete
- [x] Optimization Producer/Consumer (GAPS-07) - Kafka integration, 4 testes ✅
- [ ] Priorização dinâmica
- [ ] Saga avançada

### Approval Service (98%)
- [x] API de aprovação
- [x] Consumer Kafka
- [x] Integração MongoDB
- [x] ML model v7
- [x] Feedback loop
- [x] Active Learning Feedback Collector - 76 testes ✅
- [ ] Dashboard de aprovações

### Worker Agents (75%)
- [x] Query Executor
- [x] Transform Executor
- [x] Validate Executor
- [x] Execução Motor 3.x
- [ ] Mais tipos de executores
- [ ] Execução paralela avançada

### Queen Agent (75%)
- [x] gRPC server
- [x] Coordenação de agentes
- [x] Health checks
- [ ] Election protocol
- [ ] Load balancing

### Service Registry (85%)
- [x] Registo de agentes
- [x] Heartbeat
- [x] Descoberta
- [x] gRPC integration
- [ ] Health scoring
- [ ] Auto-deregistration

---

## Agentes Especializados — Detalhes

### Optimizer Agents (100%)
- [x] Multi-database analyzers (MongoDB, PostgreSQL, Neo4j, Redis, ClickHouse)
- [x] Code analyzer (Python - complexidade ciclomática)
- [x] Kafka consumer para `ticket.completed`
- [x] MongoDB repository para recomendações
- [x] REST API com 8 endpoints
- [x] Auto-apply mechanism com validação de segurança
- [x] Orchestrator hook (OptimizationProducer)
- [x] Suporte a: Python, JS/TS, Go, Java, C#, C/C++, Rust
- [x] MongoDB migration script
- [x] Helm chart para K8s deploy
- [x] **56 testes automatizados** ✅


## Bibliotecas Python — Detalhe

### neural_hive_domain (100%)
- [x] Models (CognitivePlan, SpecialistOpinion, etc.)
- [x] DTOs
- [x] Events
- [x] Value Objects

### neural_hive_specialists (95%)
- [x] BaseSpecialist
- [x] Especialistas concretos
- [x] Behaviours
- [x] Active Learning (balance_analyzer, learning_strategy, feedback_queue)
- [ ] Evolution hooks

### neural_hive_agent_sdk (85%)
- [x] Client templates
- [x] gRPC clients
- [x] Kafka consumers/producers
- [ ] Test utilities

### neural_hive_observability (95%)
- [x] Structured logging (structlog)
- [x] Metrics (Prometheus)
- [x] Tracing (OpenTelemetry)
- [x] Error tracking

### neural_hive_ml (100%)
- [x] Feature engineering
- [x] Modelos de aprovação (v7, v8)
- [x] NLP features
- [x] Active Learning integration
- [x] Online learning (RetrainingJob, DriftDetector)
- [x] Model versioning (MLflowClient, ModelVersionRepository)

---

## Gaps Identificados

### Críticos (Must)
1. **Memory Layer** — Persistência de memória de longo prazo (75%)
2. **ML Online Learning** — Retreinamento contínuo de modelos (40%)

### Importantes (Should)
1. **MCP Servers** — Integração completa com MCP (60%)
2. **Memory Layer API** — Completar endpoints de persistência (75%)

### Nice to Have (Could)
1. **Multi-idioma** no STE
2. **Election protocol** no Queen Agent
3. **Online learning** contínuo

### Concluídos Recentemente
- ✅ **Scout Agents Expansion** (2026-03-19) - Multi-lingua AST (Java, C#, Go, C/C++, Rust), 20 padrões, Signals, Coordination, 412 testes
- ✅ **GAPS-07 Optimizer Agents** (2026-03-18) - Multi-database analyzers, 56 testes, Helm chart
- ✅ **GAPS-06 MCP Servers Integration** (2026-03-18) - HTTP servers, 16 testes, K8s deploy
- ✅ **GAPS-05 Scout Agents** (2026-03-18) - 117 testes, exploração e descoberta autónoma
- ✅ **Active Learning Feedback Collector** (2026-03-17) - 76 testes, ML v8 integration
- ✅ **GAPS-04 Explainability API** (2026-03-17) - 66 testes, SHAP + reasoning extraction
- ✅ **GAPS-03 Consenso Hierárquico** (2026-03-17) - 5 níveis de senioridade, 132 testes

---

## Próximos Épicos Sugeridos

1. **ML: Online Learning** — Retreinamento contínuo dos modelos de aprovação (40%)
2. **Memory Layer API** — Completar endpoints de persistência de memória (75%)
3. **MCP Servers Full Integration** — Integração completa com MCP (60%)

---

## Actualizar

Para regenerar este mapa:
```bash
~/.claude/plugins/dev-planner/scripts/feature-map-gen.sh
```
