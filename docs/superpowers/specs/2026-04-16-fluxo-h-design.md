# Fluxo H - Design Specification

> **Data:** 2026-04-16
> **Versão:** 1.0
> **Tipo:** Migration System (Brownfield)
> **Status:** Design Aprovado

---

## Resumo Executivo

O **Fluxo H** é o sistema de migração de software legado do Neural-Hive-Mind. Ele estende o Fluxo G (criação de software do zero) com capacidades de migração de sistemas existentes, permitindo transformar documentação legada em software moderno completamente migrado.

**Duração estimada:** 8 semanas (40 pessoa-semanas)

**Abordagem:** Monolítico em camadas (seguindo padrão dos serviços existentes)

---

## 1. Arquitetura Geral

O Fluxo H consiste em **3 componentes principais**:

1. **Doc Ingestion Service (8018)** - Parse e análise de documentação legada
2. **Data Migration System (8019)** - Migração de dados com validação
3. **Cutover Orchestrator (8003 estendido)** - Migração gradual com rollback seguro

### Diagrama de Alto Nível

```
DOCUMENTAÇÃO LEGADA
├─ PDF, Word, Visio, Postman
        ↓
DOC INGESTION SERVICE (8018)
├─ 4 Parsers (PDF, Word, Visio, Postman)
├─ Entity Extractor (LLM)
└─ Intent Generator
        ↓
GATEWAY INTENÇÕES (8000)
        ↓
FLUXO G (100% COMPLETO)
STE → Consensus → Requirements → Architecture → Code → Deploy
        ↓
DATA MIGRATION SYSTEM (8019)
├─ Schema Mapper (LLM)
├─ CDC Pipeline (Debezium)
├─ Batch Migrator
└─ Data Validator (Great Expectations)
        ↓
ORCHESTRATOR DYNAMIC - CUTOVER (8003)
├─ Shadow Mode (validação)
├─ Canary Deployment (5% → 25% → 50% → 100%)
├─ Health Monitor
└─ Rollback Manager
        ↓
SOFTWARE MIGRADO EM PRODUÇÃO
```

---

## 2. Doc Ingestion Service (8018)

### Responsabilidade

Ingestionar, parsear e extrair entidades de documentos legados em múltiplos formatos.

### Tecnologias

| Componente | Tecnologia |
|------------|------------|
| PDF Parser | PyPDF2, pdfplumber |
| Word Parser | python-docx |
| Visio Parser | lxml, svg parsing |
| Postman Parser | json schema |
| Entity Extraction | OpenAI GPT-4, Anthropic Claude |
| Storage | MongoDB (metadados) + S3/MinIO (blobs) |
| Streaming | asyncio, chunked processing |

### API Endpoints

```
POST /api/v1/documents/upload
POST /api/v1/documents/{doc_id}/parse
POST /api/v1/documents/{doc_id}/extract
POST /api/v1/documents/{doc_id}/approve
GET  /api/v1/documents/{doc_id}/status
GET  /api/v1/documents/{doc_id}/entities
```

### Eventos Kafka Produzidos

- `doc.uploaded` - Documento recebido
- `doc.parsed` - Conteúdo extraído
- `doc.entities_extracted` - Entidades extraídas
- `doc.approved` - Aprovação humana concedida

---

## 3. Data Migration System (8019)

### Responsabilidade

Mapear schemas, migrar dados (batch + CDC), validar integridade e gerenciar rollback.

### Tecnologias

| Componente | Tecnologia |
|------------|------------|
| Schema Mapping | OpenAI GPT-4 |
| CDC Pipeline | Debezium (MySQL/PostgreSQL binlog) |
| Batch Migration | psycopg2, asyncpg |
| Data Validation | Great Expectations |
| Rollback | Transaction management |

### Estratégia Híbrida

**Batch (Dados Históricos):**
1. Export dump de dados legados
2. Transform conforme Schema Mapper
3. Import para sistema novo
4. Valida integridade

**CDC (Dados Transacionais):**
1. Inicia Debezium connector
2. Captura changes em tempo real
3. Aplica transformações
4. Sincroniza para sistema novo
5. Continua até cutover final

### API Endpoints

```
POST /api/v1/migrations/jobs
GET  /api/v1/migrations/jobs/{job_id}
POST /api/v1/migrations/jobs/{job_id}/schema-mapping
POST /api/v1/migrations/jobs/{job_id}/approve
POST /api/v1/migrations/jobs/{job_id}/start
POST /api/v1/migrations/jobs/{job_id}/rollback
GET  /api/v1/migrations/jobs/{job_id}/progress
POST /api/v1/migrations/jobs/{job_id}/validate
```

### Eventos Kafka Produzidos

- `migration.started` - Migração iniciada
- `migration.progress` - Progresso atualizado
- `migration.batch_completed` - Batch finalizado
- `migration.cdc_started` - CDC iniciado
- `migration.completed` - Migração completa

---

## 4. Cutover Orchestrator (8003 estendido)

### Responsabilidade

Orquestrar migração gradual com shadow mode, canary deployment e rollback automático.

### Estratégia de Cutover

**Fase 1: Shadow Mode (7 dias)**
- Sistema novo em paralelo (sem produção)
- Traffic mirror 100% → shadow
- Validação de métricas (error rate, latência, business)
- Ajustes baseados em resultados

**Fase 2: Canary Deployment**
- 5% (1% usuários) → 24-48h
- 25% → 24-48h
- 50% → 24-48h
- 100% → completo

**Fase 3: Full Cutover**
- Tráfego 100% no novo sistema
- Legado em modo manutenção
- Monitoramento por 7 dias
- Desligar legado

### Critérios de Rollback Automático

- **Rollback imediato** se:
  - Error rate > 5% (5min consecutivos)
  - Sistema target completamente DOWN
  - Data corruption detectada

- **Rollback manual** se:
  - Error rate > 1% (mas <5%)
  - Latência P95 > 2x legacy
  - Bugs críticos de negócio

### Eventos Kafka Produzidos

- `cutover.workflow_started`
- `cutover.shadow_ready`
- `cutover.canary_5`, `cutover.canary_25`, `cutover.canary_50`, `cutover.canary_100`
- `cutover.health_check`
- `cutover.rollback`
- `cutover.completed`

---

## 5. Integração com Fluxo G

O Fluxo H reutiliza todos os componentes do Fluxo G (100% completo):

| Componente Fluxo G | Uso no Fluxo H |
|--------------------|----------------|
| Gateway Intenções | Recebe documentos |
| Semantic Translation Engine | Traduz entidades extraídas |
| Consensus Engine | Consenso sobre plano de migração |
| Requirements Engineering | Extra requirements do doc |
| Architect Agent | Gera arquitetura moderna |
| Code Forge | Gera código moderno |
| Test Generation | Gera testes de migração |
| Documentation Generation | Gera docs do novo sistema |
| Software Engineering Pipeline | Deploy ambos sistemas |
| CI Feedback Loop | Aprende com migrações |

---

## 6. Storage Architecture

### Hybrid Storage (MongoDB + S3/MinIO)

**Metadados (MongoDB):**
- Document info (filename, size, format, upload_date)
- Parse status (processing, completed, failed)
- Extraction results (entities count, intent_id)
- Approval status

**Blobs (S3/MinIO):**
- Arquivos originais (PDF, Word, Visio, Postman)
- Conteúdo parseado (chunks para docs grandes)
- Extraídos em JSON (entities, intents)

### Estrutura de Diretórios S3

```
s3://nhm-documents/
├── {ingestion_id}/raw/
│   ├── user_manual.pdf
│   ├── technical_spec.docx
│   ├── database_schema.vsd
│   └── api_collection.json
└── {ingestion_id}/parsed/
    ├── chunks/ (para docs grandes)
    └── entities/ (JSON)
```

---

## 7. Requisitos Não-Funcionais

### Performance

- **Throughput:** 20-50 documentos/hora
- **Latência:** <15 minutos por documento
- **Concorrência:** Processamento paralelo de múltiplos documentos

### Escalabilidade

- **Horizontal:** Add pods do Doc Ingestion
- **Vertical:** Increase CPU/RAM para parsers
- **Storage:** S3 scales infinitely

### Disponibilidade

- **Target:** 99.9% uptime
- **Recovery Time:** <5 minutos (RTO)
### Data Integrity

- **Validação:** 100% de registros contados
- **Checksum:** SHA256 para todos os dados
- **Reconciliação:** Reports de discrepâncias

---

## 8. Segurança

### Autenticação

- JWT tokens (via approval-gateway)
- Role-based access control
- Service-to-service auth via mTLS

### Authorization

- Permissões por documento
- Aprovação humana tracking
- Audit trail completo

### Data Protection

- Encrypt at rest (S3 server-side encryption)
- Encrypt in transit (TLS 1.3)
- PII detection e masking

---

## 9. Observabilidade

### Métricas Prometheus

| Métrica | Descrição |
|---------|----------|
| `doc_ingestion_docs_processed_total` | Total de documentos processados |
| `doc_ingestion_parser_success_rate` | Taxa de sucesso dos parsers |
| `data_migration_progress_percentage` | Progresso da migração |
| `data_migration_cdc_lag_seconds` | Lag do CDC |
| `cutover_traffic_percentage` | % de tráfego no target |
| `cutover_error_rate_legacy` | Error rate legado |
| `cutover_error_rate_target` | Error rate target |

### Logging

- Structured logging (structlog)
- Trace correlation (correlation_id via todo fluxo)
- Log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL

### Tracing

- OpenTelemetry distributed tracing
- Jaeger span propagation
- Service dependency graphs

---

## 10. Checklist de Validação

### Funcional

- [ ] Upload de 4 formatos (PDF, Word, Visio, Postman)
- [ ] Extração de entidades (funcionalidades, requisitos, schemas, APIs)
- [ ] Schema mapping com aprovação humana
- [ ] Batch migration de dados históricos
- [ ] CDC sync de dados transacionais
- [ ] Validação de integridade referencial
- [ ] Shadow mode com monitoramento
- [ ] Canary deployment progressivo
- [ ] Rollback automático e manual

### Integração

- [ ] Service Registry registration
- [ ] Kafka topics criados
- [ ] Endpoints respondem corretamente
- [ ] Tracing completo de ponta a ponta

### Operações

- [ ] Helm charts criados
- [ ] CI/CD pipelines configurados
- [ ] Dashboards Grafana criados
- [ ] Runbooks documentados
- [ ] Smoke tests passando

---

## 11. Próximos Passos

1. **Aprovar este design** - Marcar tarefa como aprovada
2. **Invocar writing-plans skill** - Criar plano de implementação detalhado
3. **Decompor em tickets** - Criar tarefas específicas
4. **Preparar handoff** - Para Claude Code executar

---

**Aprovado por:** Usuário
**Data:** 2026-04-16
**Próximo:** writing-plans skill → implementação
