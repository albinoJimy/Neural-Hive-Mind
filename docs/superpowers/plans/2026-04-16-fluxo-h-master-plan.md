# Fluxo H - Plano Mestre: Legacy Migration

> **Para agentic workers:** Este plano implementa o Fluxo H (Documentação → Software Migrado) que estende o Fluxo G com capacidades de migração de sistemas legados.

**Goal:** Implementar o Fluxo H completo - da ingestão de documentação legada até software migrado em produção

**Architecture:** O Fluxo H estende o Fluxo G (100% completo) com 3 componentes principais:
1. Doc Ingestion Service (novo)
2. Data Migration System / Fluxo I (novo)
3. Cutover Orchestration (extensão do orchestrator)

**Tech Stack:** Python 3.12+, FastAPI, Kafka, MongoDB, Redis, Neo4j, Debezium (CDC)

---

## Visão Geral do Fluxo H

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          FLUXO H - LEGACY MIGRATION                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   DOCUMENTAÇÃO LEGADA                                                        │
│   ├─ PDF (manual técnico)                                                   │
│   ├─ Word (especificações)                                                  │
│   ├─ Visio (diagramas)                                                      │
│   └─ Postman (APIs)                                                         │
│          ↓                                                                   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                     DOC INGESTION SERVICE (NOVO)                    │   │
│   │  ┌─────────────┐  ┌───────────────┐  ┌─────────────┐  ┌────────┐   │   │
│   │  │ PDF Parser  │→ │ Word Parser   │→ │ Visio Parser│→ │Postman │   │   │
│   │  │ (PyPDF2)    │  │ (python-docx) │  │ (lxml/s vg) │  │Parser  │   │   │
│   │  └─────────────┘  └───────────────┘  └─────────────┘  └───┬────┘   │   │
│   │                                                   │                │        │   │
│   │  ┌────────────────────────────────────────────────────────────────┐  │   │
│   │  │            ENTITY EXTRACTOR (LLM-based)                      │  │   │
│   │  │  Functionalities │ Requirements │ Data Models │ APIs         │  │   │
│   │  └───────────────────────────┬────────────────────────────────┘  │   │
│   └──────────────────────────────┼─────────────────────────────────────┘   │
│                                  ↓                                         │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    FLUXO G (100% COMPLETO)                          │   │
│   │   STE → Consensus → Requirements → Architecture → Code → Deploy    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                  ↓                                         │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │              DATA MIGRATION SYSTEM / FLUXO I (NOVO)                │   │
│   │  ┌──────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────┐   │   │
│   │  │Schema Mapper │→ │CDC Pipeline │→ │Data Validator│→ │Cutover  │   │   │
│   │  │(LLM-based)   │  │(Debezium)   │  │(Great Expect)│  │Orchestr.│   │   │
│   │  └──────────────┘  └─────────────┘  └─────────────┘  └────┬────┘   │   │
│   └────────────────────────────────────────────────────────────┼───────┘   │
│                                                                 ↓           │
└─────────────────────────────────────────────────────────────────────────────┘
                                                                  ↓
                                                   ┌─────────────────────────┐
                                                   │ SOFTWARE MIGRADO       │
                                                   │ • Código moderno        │
                                                   │ • Dados migrados        │
                                                   │ • Legado desativado     │
                                                   └─────────────────────────┘
```

---

## Diferenças Fluxo G vs Fluxo H

| Aspecto | Fluxo G | Fluxo H |
|---------|--------|---------|
| **Entrada** | Ideia em texto natural | Documentação legada (PDF, Word, etc.) |
| **Estratégia** | Greenfield (do zero) | Brownfield (modernização) |
| **Análise** | NLU de intenção | Extração de entidades de docs |
| **Dados** | Novo schema | Preservação + migração |
| **Deploy** | Deploy direto | Cutover gradual |
| **Tempo** | ~2 horas | ~2.5 horas |
| **Componentes** | 7 sistemas | 7 + Doc Ingestion + Data Migration |

---

## Fases de Implementação

### Fase 1: Doc Ingestion Service
**Objetivo:** Criar serviço para ingestão e parse de documentação legada

**Porta:** 8018

**Componentes:**
1. **PDF Parser** - Extrai texto de PDFs técnicos
2. **Word Parser** - Extrai texto de .docx
3. **Visio Parser** - Extrai diagramas
4. **Postman Parser** - Extrai coleções/contratos API
5. **Entity Extractor** - LLM para extrair funcionalidades, requisitos, modelos
6. **Schema Generator** - Gera CognitivePlan a partir de entidades

**Eventos Kafka:**
- Produz: `doc.ingested`, `doc.entities_extracted`
- Consome: `doc.uploaded`

**Testes:** 30 unitários + 10 integração

---

### Fase 2: Data Migration System (Fluxo I)
**Objetivo:** Sistema completo de migração de dados

**Porta:** 8019

**Componentes:**
1. **Schema Mapper** - Mapeia schemas legado→moderno (LLM)
2. **CDC Pipeline** - Change Data Capture via Debezium
3. **Data Validator** - Valida integridade (Great Expectations)
4. **Migration Orchestrator** - Orquestra fases de migração
5. **Rollback Manager** - Rollback automático se falhar

**Eventos Kafka:**
- Produz: `data.migration.started`, `data.migration.progress`, `data.migration.completed`
- Consome: `architecture.plan`

**Testes:** 40 unitários + 15 integração

---

### Fase 3: Cutover Orchestration
**Objetivo:** Orquestrar migração gradual com rollback seguro

**Extensões ao Orchestrator:**
1. **Cutover Workflow Temporal** - Novo workflow para cutover
2. **Traffic Switcher** - Redireciona tráfego gradualmente
3. **Health Monitor** - Monitora saúde do novo sistema
4. **Rollback Trigger** - Automatic rollback baseado em métricas

**Estratégia de Cutover:**
- Shadow mode (paralelo, sem produção)
- Canary (5% → 25% → 50% → 100%)
- Blue-Green (switch instantâneo)

**Testes:** 20 integração E2E

---

### Fase 4: Integração Fluxo H Completo
**Objetivo:** Integrar Doc Ingestion + Fluxo G + Data Migration

**Integrações:**
1. Doc Ingestion → Gateway Intenções
2. Data Migration → Orchestrator Dynamic
3. Cutover → CI/CD Pipeline

**Testes:** 25 E2E ponta a ponta

---

### Fase 5: Testing & Hardening
**Objetivo:** Testes de carga, segurança e documentação

**Entregas:**
- Locust load tests (Doc Ingestion, Data Migration)
- Security scanning (análise de documentos, CDC)
- Operations runbooks
- Grafana dashboards

---

## Serviços a Criar/Modificar

| Serviço | Porta | Status | Ação |
|---------|------|--------|------|
| doc-ingestion | 8018 | ❌ Novo | Criar |
| data-migration | 8019 | ❌ Novo | Criar |
| orchestrator-dynamic | 8003 | ✅ Existe | Estender (cutover) |
| gateway-intencoes | 8000 | ✅ Existe | Estender (doc upload) |

---

## Esforço Estimado

| Fase | Duração | Pessoa-Semanas |
|------|---------|----------------|
| Fase 1: Doc Ingestion | 2 semanas | 10 |
| Fase 2: Data Migration | 3 semanas | 15 |
| Fase 3: Cutover | 1 semana | 5 |
| Fase 4: Integração | 1 semana | 5 |
| Fase 5: Testing | 1 semana | 5 |
| **Total** | **8 semanas** | **40** |

---

## Critérios de Sucesso

### Fase 1: Doc Ingestion
- [ ] Upload de PDF/Word/Visio/Postman via API
- [ ] Extração de texto com >90% precisão
- [ ] Entity extractor identifica funcionalidades, requisitos, data models
- [ ] Gera CognitivePlan válido para STE

### Fase 2: Data Migration
- [ ] Schema mapper cria mapeamento legado→novo
- [ ] CDC pipeline sincroniza dados em <1s
- [ ] Data validator valida 100% de integridade
- [ ] Rollback funciona em <30s

### Fase 3: Cutover
- [ ] Traffic switch funciona sem downtime
- [ ] Health monitor detecta falhas em <10s
- [ ] Rollback automático ativado por erro >5%

### Fase 4: Integração
- [ ] Doc upload → Software migrado fluxo completo
- [ ] Todos os eventos Kafka conectados
- [ ] Tracing completo (Jaeger)

### Fase 5: Testing
- [ ] Load test: 100 docs/hora throughput
- [ ] Security scan sem vulnerabilidades críticas
- [ ] Runbooks completos documentados

---

## Próximos Passos

1. **Fase 1.1:** Setup do serviço doc-ingestion (FastAPI + estrutura)
2. **Fase 1.2:** Implementar PDF Parser (PyPDF2)
3. **Fase 1.3:** Implementar Entity Extractor (LLM)
4. **Fase 1.4:** Testes e documentação

**Iniciar com:** `python -m src.api.main` (doc-ingestion service)
