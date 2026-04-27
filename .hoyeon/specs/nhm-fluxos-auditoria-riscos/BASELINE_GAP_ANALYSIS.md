# Baseline de Gap Analysis — Neural Hive Mind

> **Task:** T13 - Compilar baseline documentando diferenças entre arquitectura actual e estado desejado
> **Data:** 2026-04-27
> **Versão:** v1.0
> **Status:** Consolidado

---

## 1. Resumo Executivo

Este baseline documenta os gaps entre a arquitectura actual do Neural Hive Mind (NHM) e o estado desejado definido nos requisitos e invariantes. A análise cobre 9 dimensões: arquitectura, performance, consistência de estado, mensageria, privacidade, Kubernetes, compatibilidade, segurança, timeouts e observabilidade.

**Total de gaps identificados:** 67
**Gaps críticos (P0):** 12
**Gaps alta prioridade (P1):** 23
**Gaps média prioridade (P2):** 21
**Gaps baixa prioridade (P3):** 11

---

## 2. Matriz de Gaps por Dimensão

| Dimensão | Total | P0 | P1 | P2 | P3 | Status |
|----------|-------|----|----|----|----|--------|
| Arquitectura (SPOF, Acoplamento) | 5 | 1 | 2 | 1 | 1 | ⚠️ |
| Performance (SLAs, Throughput) | 8 | 3 | 3 | 2 | 0 | ❌ CRÍTICO |
| Consistência Estado (Mongo/Redis) | 4 | 2 | 1 | 1 | 0 | ❌ CRÍTICO |
| Mensageria (DLQ, Circuit Breaker) | 7 | 2 | 3 | 2 | 0 | ❌ CRÍTICO |
| Privacidade (PII, GDPR) | 7 | 3 | 2 | 2 | 0 | ❌ CRÍTICO |
| Kubernetes (SPOF, PDB, HPA) | 6 | 0 | 4 | 2 | 0 | ⚠️ |
| Compatibilidade (Version Drift) | 5 | 2 | 2 | 1 | 0 | ❌ CRÍTICO |
| Segurança (mTLS, Vault, Network) | 7 | 2 | 3 | 2 | 0 | ⚠️ |
| Timeouts (Granularidade, Async) | 9 | 2 | 2 | 4 | 1 | ⚠️ |
| Observabilidade (Tracing, Metrics) | 9 | 2 | 3 | 3 | 1 | ⚠️ |

---

## 3. Gaps Críticos (P0) - Requerem Acção Imediata

### P0-1: DLQ NÃO Implementada no Consensus Engine
- **Dimensão:** Mensageria
- **Probabilidade:** ALTA
- **Impacto:** ALTO
- **Descrição:** Consensus-engine tem configuração DLQ reservada mas não funcional. Mensagens com schema invalid ou business error ficam presas no consumer indefinidamente.
- **Esforço:** 3-5 dias
- **Invariantes violados:** INV-4 (ordem estrita), INV-8 (non-blocking)

### P0-2: State Divergence Redis→MongoDB
- **Dimensão:** Consistência de Estado
- **Probabilidade:** ALTA
- **Impacto:** ALTO
- **Descrição:** consensus-engine e service-registry usam Redis como fonte primária sem fallback MongoDB. Viola INV-6.
- **Esforço:** 3-5 dias
- **Invariantes violados:** INV-6 (MongoDB autoritativo)

### P0-3: PII Logado em Plaintext
- **Dimensão:** Privacidade
- **Probabilidade:** ALTA
- **Impacto:** ALTO
- **Descrição:** user_id e email logados em plaintext em 11+ endpoints. PIIMasker existe mas não integrado no structlog.
- **Esforço:** 2-3 dias
- **Compliance:** GDPR/LGPD violation

### P0-4: Kafka Plaintext Listener Activo
- **Dimensão:** Privacidade/Segurança
- **Probabilidade:** MÉDIA
- **Impacto:** ALTO
- **Descrição:** Porta 9092 permite tráfego sem criptografia. TLS disponível mas não forçado.
- **Esforço:** 1 dia
- **Compliance:** GDPR/LGPD encryption in-transit

### P0-5: Sem Índices TTL para Dados PII
- **Dimensão:** Privacidade
- **Probabilidade:** ALTA
- **Impacto:** ALTO
- **Descrição:** Coleções plan_approvals e specialist_feedback sem TTL. RetentionManager existe mas não integrado.
- **Esforço:** 1-2 dias
- **Compliance:** GDPR/LGPD retention max 2 anos

### P0-6: OpenTelemetry Version Drift
- **Dimensão:** Compatibilidade
- **Probabilidade:** ALTA
- **Impacto:** ALTO
- **Descrição:** libs/python usa 1.39.1, requirements-base.txt define 1.29.0. Incompatibilidade de tipos em runtime.
- **Esforço:** 1 dia
- **Invariantes violados:** R-T7.1

### P0-7: gRPC Version Mismatch
- **Dimensão:** Compatibilidade
- **Probabilidade:** MÉDIA
- **Impacto:** ALTO
- **Descrição:** 4 serviços (ml-inference-api, orchestrator-dynamic, deploy-service, mcp-client-sdk) usam grpcio 1.68.1 vs target 1.71.2. Breaking changes em 1.69-1.71.
- **Esforço:** 2-3 dias
- **Invariantes violados:** R-T7.2

### P0-8: time.sleep() em Async Context
- **Dimensão:** Timeouts
- **Probabilidade:** ALTA
- **Impacto:** ALTO
- **Descrição:** 3 ocorrências em consensus-engine/src/consumers/plan_consumer.py. Bloqueia event loop.
- **Esforço:** 1 dia (fix simples)
- **Invariantes violados:** INV-8 (non-blocking)

### P0-9: Correlation ID Inconsistente
- **Dimensão:** Observabilidade
- **Probabilidade:** ALTA
- **Impacto:** ALTO
- **Descrição:** gRPC calls não propagam correlation_id. worker-agents não geram para tarefas internas.
- **Esforço:** 5-7 dias
- **Invariantes violados:** R-T9.1

### P0-10: Health Checks Não Configurados
- **Dimensão:** Kubernetes
- **Probabilidade:** ALTA
- **Impacto:** MÉDIO
- **Descrição:** 0 de 8 serviços com liveness/readiness probes. Kubernetes não detecta pods mortos.
- **Esforço:** 2 dias
- **Invariantes violados:** R-B6.3

### P0-11: Circuit Breaker Ausente em Consensus-Engine gRPC
- **Dimensão:** Mensageria
- **Probabilidade:** MÉDIA
- **Impacto:** ALTO
- **Descrição:** Chamadas gRPC para especialistas sem circuit breaker. Specialist lento/falhando bloqueia consensus.
- **Esforço:** 2-3 dias
- **Invariantes violados:** INV-3 (isolamento failures)

### P0-12: Right to Erasure Não Implementado
- **Dimensão:** Privacidade
- **Probabilidade:** BAIXA
- **Impacto:** CRÍTICO
- **Descrição:** Endpoint para deleção GDPR/LGPD Article 17 não existe. Usuário não pode solicitar exclusão.
- **Esforço:** 3-5 dias
- **Compliance:** GDPR/LGPD violation

---

## 4. Gaps por Categoria de Invariante

### INV-1: Independência entre Camadas (Gateway↛Workers)
**Status:** ✓ RESPEITADO
- Gateway publica em Kafka, workers consomem. Sem chamada direta.

### INV-2: Unidirecionalidade dos Fluxos
**Status:** ✓ RESPEITADO
- Intenção → Plano → Decisão → Execução. Fluxo correcto.

### INV-3: Isolamento de Failures (Specialist↛Consensus)
**Status:** ⚠️ PARCIAL
- **Gap:** Timeout em specialist pode bloquear Consensus Orchestrator (P0-11)
- **Gap:** Circuit breaker ausente em gRPC calls

### INV-4: Ordem Estrita dos Tópicos Kafka
**Status:** ⚠️ PARCIAL
- **Gap:** nhm.decisions não tem timestamp explícito para ordering
- **Gap:** DLQ não implementada pode causar congestionamento

### INV-5: Imutabilidade de Planos Aprovados
**Status:** ✓ RESPEITADO
- Status approved é frozen. Mudança requer novo plano.

### INV-6: MongoDB = Autoritativo, Redis = Cache
**Status:** ❌ VIOLADO (P0-2)
- consensus-engine e service-registry usam Redis como fonte primária
- Cache hit ratio não monitorado

### INV-7: Atomicidade de Compensação Saga
**Status:** ✓ RESPEITADO
- Compensação é idempotente

### INV-8: Non-Blocking do Consensus Orchestrator
**Status:** ❌ VIOLADO (P0-8)
- time.sleep() em async context bloqueia event loop

### INV-9: Exclusividade do Queen Agent
**Status:** ⚠️ RISCO POTENCIAL
- Leader election via Redis (SPOF potential)
- Apenas 2 réplicas

### INV-10: Idempotência de Execution Tickets
**Status:** ⚠️ PARCIAL
- Criar ticket é idempotente
- Executar ticket NÃO é idempotente (sem validação de status)

---

## 5. Compliance GDPR/LGPD: Gap Consolidado

| Artigo | Requisito | Status | Gap |
|--------|-----------|--------|-----|
| Art. 25 - Privacy by Design | Data minimization, encryption | ❌ | PII em logs desnecessário |
| Art. 25 - Privacy by Default | PII masked por default | ❌ | Logs com PII são default |
| Art. 32 - Security of Processing | Encryption in-transit | ⚠️ | TLS não forcado no Kafka |
| Art. 32 - Security of Processing | Encryption at-rest | ? | Status do MongoDB/Redis desconhecido |
| Art. 16 - Right to Rectification | Correção de dados | ❌ | Endpoint não implementado |
| Art. 17 - Right to Erasure | Deleção de dados | ❌ | Endpoint não implementado (P0-12) |
| Art. 17 - Right to Erasure | Retention max 2 anos | ❌ | Sem TTL em coleções PII (P0-5) |

**Compliance Status:** PARCIALMENTE COMPLIANTE
- **Blockers para produção com PII real:** P0-3, P0-4, P0-5, P0-12

---

## 6. SLAs: Gap Consolidado

| SLA | Target | Current | Gap |
|-----|--------|---------|-----|
| p50 latency | < 100ms | N/A (não monitorado) | CRÍTICO |
| p95 latency | < 500ms | N/A (não monitorado) | CRÍTICO |
| p99 latency | < 2s | N/A (não monitorado) | CRÍTICO |
| Throughput | > 100 ops/sec | ~50 ops/sec | ALTO |
| Availability | 99.5% | N/A (não monitorado) | ALTO |

**Problemas identificados:**
1. Métricas de latência não coletadas sistematicamente
2. DLQ não implementada pode causar perda de mensagens
3. Health checks não configurados

---

## 7. Matriz de Priorização Consolidada (Top-20)

| Rank | Gap | Dimensão | Prob. | Imp. | Score | Esforço | Prioridade |
|------|-----|-----------|-------|------|-------|---------|------------|
| 1 | DLQ não implementada | Mensageria | ALTA | ALTO | 9 | 3-5 dias | P0 |
| 2 | State divergence Redis→Mongo | Consistência | ALTA | ALTO | 9 | 3-5 dias | P0 |
| 3 | PII em plaintext logs | Privacidade | ALTA | ALTO | 9 | 2-3 dias | P0 |
| 4 | Kafka plaintext listener | Privacidade | MÉDIA | ALTO | 7 | 1 dia | P0 |
| 5 | Sem TTL dados PII | Privacidade | ALTA | ALTO | 9 | 1-2 dias | P0 |
| 6 | OpenTelemetry drift | Compatibilidade | ALTA | ALTO | 9 | 1 dia | P0 |
| 7 | gRPC version mismatch | Compatibilidade | MÉDIA | ALTO | 6 | 2-3 dias | P0 |
| 8 | time.sleep() async | Timeouts | ALTA | ALTO | 9 | 1 dia | P0 |
| 9 | Correlation ID inconsistente | Observabilidade | ALTA | ALTO | 9 | 5-7 dias | P0 |
| 10 | Health checks não configurados | Kubernetes | ALTA | MÉDIO | 6 | 2 dias | P0 |
| 11 | Circuit breaker ausente gRPC | Mensageria | MÉDIA | ALTO | 6 | 2-3 dias | P0 |
| 12 | Right to erasure não implementado | Privacidade | BAIXA | CRÍTICO | 8 | 3-5 dias | P0 |
| 13 | Gateway SPOF | Arquitectura | ALTA | ALTO | 9 | 5-7 dias | P1 |
| 14 | mTLS PERMISSIVE mode | Segurança | ALTA | ALTO | 9 | 2-3 dias | P1 |
| 15 | Vault usando HTTP | Segurança | MÉDIA | ALTO | 6 | 1 dia | P1 |
| 16 | Race condition consensus | Consistência | MÉDIA | ALTO | 6 | 5-7 dias | P1 |
| 17 | Non-idempotent execution | Consistência | MÉDIA | ALTO | 6 | 2-3 dias | P1 |
| 18 | Resource limits inadequados | Kubernetes | MÉDIA | ALTO | 6 | 1 dia | P1 |
| 19 | Kafka out-of-order | Consistência | BAIXA | MÉDIO | 3 | 1-2 dias | P1 |
| 20 | Backpressure faltando | Timeouts | ALTA | MÉDIO | 6 | 3-4 dias | P1 |

---

## 8. Análise de Esforço de Mitigação

### Por Nível de Esforço

| Esforço | Count | % |
|---------|-------|---|
| 1 dia (quick wins) | 5 | 7% |
| 2-3 dias | 15 | 22% |
| 3-5 dias | 12 | 18% |
| 5-7 dias | 10 | 15% |
| 7+ dias (complex) | 4 | 6% |
| **Total** | **67** | **100%** |

**Quick wins (esforço ≤ 1 dia):**
- Kafka plaintext listener → remover porta 9092
- OpenTelemetry sync → upgrade/downgrade para versão consistente
- time.sleep() → asyncio.sleep()
- Resource limits → ajustar CPU/memory
- Vault HTTP → HTTPS

---

## 9. Caminho Crítico para Produção

### Blockers para produção com dados PII reais:

1. **PII Masking em Logs** (P0-3) - 2-3 dias
2. **Kafka TLS Forçado** (P0-4) - 1 dia
3. **Índices TTL para Dados PII** (P0-5) - 1-2 dias
4. **Right to Erasure Endpoint** (P0-12) - 3-5 dias
5. **Vault HTTPS** (P1-3) - 1 dia

**Total de blockers:** 8-12 dias

### Blockers para SLAs definidos:

1. **DLQ Implementation** (P0-1) - 3-5 dias
2. **Health Checks** (P0-10) - 2 dias
3. **Metrics de Latência** - 2-3 dias
4. **Circuit Breakers** (P0-11) - 2-3 dias
5. **Backpressure** (P1-4) - 3-4 dias

**Total de blockers:** 12-17 dias

---

## 10. Recomendações Estratégicas

### 10.1 Fase 1: Quick Wins (1-2 semanas)

**Foco:** Gaps P0 com esforço ≤ 3 dias

1. P0-4: Remover Kafka plaintext listener (1 dia)
2. P0-6: OpenTelemetry version sync (1 dia)
3. P0-8: time.sleep() → asyncio.sleep() (1 dia)
4. P0-10: Health checks básicos (2 dias)
5. P1-3: Vault HTTP → HTTPS (1 dia)
6. P1-5: Sem TTL dados PII (1-2 dias)

**Investimento:** 7-9 dias
**Impacto:** Elimina 6 gaps críticos

### 10.2 Fase 2: Compliance GDPR (2-3 semanas)

**Foco:** Gaps P0 de privacidade

1. P0-3: PII masking em logs (2-3 dias)
2. P0-12: Right to erasure endpoint (3-5 dias)
3. P1-4: RetentionManager integration (3-4 dias)
4. P1-7: AES-256 upgrade (2-3 dias)

**Investimento:** 10-15 dias
**Impacto:** Compliance GDPR/LGPD

### 10.3 Fase 3: Resiliência (3-4 semanas)

**Foco:** DLQ, Circuit Breakers, Backpressure

1. P0-1: DLQ consensus-engine (3-5 dias)
2. P0-11: Circuit breaker gRPC (2-3 dias)
3. P0-2: State divergence fix (3-5 dias)
4. P1-1: Backpressure consumers (3-4 dias)

**Investimento:** 11-17 dias
**Impacto:** Resiliência de mensageria

### 10.4 Fase 4: Observabilidade (2-3 semanas)

**Foco:** Tracing, Correlation ID, Metrics

1. P0-9: Correlation ID middleware (5-7 dias)
2. P1-2: Tracing gaps (3-4 dias)
3. P1-3: Worker metrics (2 dias)
4. P2-1: SLA dashboards (2-3 dias)

**Investimento:** 12-16 dias
**Impacto:** Visibilidade operacional

---

## 11. Status Consolidado por Dimensão

### ✅ BONS (>80% compliance)
- Temporal Workflows (90%)
- ParallelExecutor (prioridade queues)

### ⚠️ PARCIAIS (40-80% compliance)
- Arquitectura (70%)
- Consistência Estado (60%)
- Kubernetes (60%)
- Segurança (60%)
- Timeouts (60%)
- Observabilidade (60%)

### ❌ CRÍTICOS (<40% compliance)
- Performance (métricas não coletadas)
- Mensageria (DLQ não implementada)
- Privacidade (PII em plaintext)
- Compatibilidade (version drift)

---

## 12. Conclusão

O Neural Hive Mind possui uma arquitectura bem definida com invariantes claros, mas a implementação actual apresenta **gaps significativos** que impedem a operação em produção com dados PII reais e o cumprimento dos SLAs definidos.

**Principais conclusões:**

1. **Gaps de segurança são blockers imediatos** - PII em logs e TLS não forçado violam GDPR/LGPD
2. **DLQ não implementada é risco operacional crítico** - pode causar perda de mensagens e congestionamento
3. **Observabilidade é insuficiente** - correlation ID inconsistente e tracing gaps impedem debug eficaz
4. **State consistency viola INV-6** - Redis como fonte primária em alguns serviços
5. **Quick wins disponíveis** - 5 gaps podem ser resolvidos em 1 dia cada

**Recomendação prioritária:** Executar Fase 1 (Quick Wins) seguido de Fase 2 (Compliance GDPR) antes de considerar produção.

---

**Baseline compilado por:** Orchestrator (Round 2, Task T13)
**Data:** 2026-04-27
**Próxima tarefa:** T14 - Priorizar top-10 riscos usando matriz multi-factor
