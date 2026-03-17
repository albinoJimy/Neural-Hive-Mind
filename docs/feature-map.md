# Feature Map — Neural-Hive-Mind

**Projecto:** Neural-Hive-Mind
**Última Actualização:** 2026-03-17
**Completude Global:** ~79%

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
│  Orchestrator      █████████████████████████████████░░░░░  80%        │
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
│  Analyst           ██████████████████████████████░░░░░░  70%        │
│  Scout             ███████████████████████░░░░░░░░░░░░░  50%        │
│  Guard             ██████████████████████████████████░░░  85%        │
│  Optimizer         ██████████████████████░░░░░░░░░░░░░░  45%        │
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
│  MCP Servers       ██████████████████████████░░░░░░░░░░  60%        │
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
- [x] Consenso hierárquico (GAPS-03) - 5 níveis de senioridade, 68 testes

### Orchestrator Dynamic (80%)
- [x] Conversão Plans → Tickets
- [x] Orquestração Temporal
- [x] SLA monitoring
- [x] Flow C complete
- [ ] Priorização dinâmica
- [ ] Saga avançada

### Approval Service (95%)
- [x] API de aprovação
- [x] Consumer Kafka
- [x] Integração MongoDB
- [x] ML model v7
- [x] Feedback loop
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

## Bibliotecas Python — Detalhe

### neural_hive_domain (100%)
- [x] Models (CognitivePlan, SpecialistOpinion, etc.)
- [x] DTOs
- [x] Events
- [x] Value Objects

### neural_hive_specialists (90%)
- [x] BaseSpecialist
- [x] Especialistas concretos
- [x] Behaviours
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

### neural_hive_ml (75%)
- [x] Feature engineering
- [x] Modelos de aprovação
- [x] NLP features
- [ ] Online learning
- [ ] Model versioning

---

## Gaps Identificados

### Críticos (Must)
1. **Explainability API** — Explicação de decisões dos especialistas
2. **Memory Layer** — Persistência de memória de longo prazo
3. **Consensus hierárquico** — Especialistas seniors vs juniors

### Importantes (Should)
1. **MCP Servers** — Integração completa com MCP
2. **Scout Agents** — Exploração autónoma
3. **Optimizer Agents** — Otimização de workflows

### Nice to Have (Could)
1. **Multi-idioma** no STE
2. **Election protocol** no Queen Agent
3. **Online learning** contínuo

---

## Próximo Ticket

**Epic:** Enriquecimento de Feedback com Semantic Features
**Status:** Em Progresso
**Próximo:** Implementar captura de `intent_raw_text` no pipeline completo

---

## Actualizar

Para regenerar este mapa:
```bash
~/.claude/plugins/dev-planner/scripts/feature-map-gen.sh
```
