# Spec Requirements Document

> Spec: Unified Gateway e Arquitetura Compartilhada
> Created: 2026-05-01
> Status: Planning
> Priority: P0 - Crítica para arquitetura

---

## Overview

Implementar um **Unified Gateway (:7999)** como ponto único de entrada para todos os clientes, com classificação automática de intenção e roteamento para fluxos específicos (A-F, G, H), eliminando duplicações de NLU, PII, Approval e autenticação em toda a codebase.

**Problema Atual:**
- Múltiplos gateways sem centralização (8000, 8010, 8018)
- NLU duplicado em 2+ locais (~1.700 LOC duplicados)
- PII duplicado em 2 implementações (~842 LOC duplicados)
- Approval duplicado em 2+ serviços (~2.000+ LOC duplicados)
- Autenticação descentralizada (SecurityHeadersMiddleware em cada serviço)
- Rate limiting apenas stub, sem implementação real

**Solução Proposta:**
- Unified Gateway (:7999) com Intent Classifier e Flow Router
- NLU Service (:8020) centralizado
- PII Service (:8021) centralizado
- Approval Core Package compartilhado
- Auth/Ratelimit middleware centralizados

---

## User Stories

### US-001: Cliente Simplificado

Como **desenvolvedador cliente**, quero fazer **requests para um único endpoint**, para não precisar saber qual fluxo (A-F, G, H) usar.

**Workflow:**
1. Cliente envia request para `/api/v1/nhm/request`
2. Sistema analisa input + contexto
3. Sistema classifica automaticamente o tipo de fluxo
4. Sistema roteia para o gateway adequado
5. Cliente recebe resposta sem saber da complexidade interna

### US-002: Administração Centralizada

Como **operador do sistema**, quero **gerenciar autenticação e rate limiting em um lugar**, para simplificar a operação.

**Workflow:**
1. Operador configura políticas no Unified Gateway
2. Todas as requests passam pelo gateway
3. Auth e rate limiting são aplicados centralmente
4. Serviços downstream recebem requests já autenticadas

### US-003: Consistência de NLU/PII

Como **desenvolvedor**, quero que **NLU e PII sejam consistentes** em todos os fluxos, para garantir resultados previsíveis.

**Workflow:**
1. NLU Service central é atualizado
2. Todos os fluxos usam a mesma versão
3. Resultados consistentes independente do fluxo
4. Manutenção simplificada (um único lugar para atualizar)

---

## Spec Scope

1. **Unified Gateway (:7999)** - Novo serviço
   - Authentication & Authorization (JWT, API Key, OAuth2)
   - Context Builder (input + tenant + session)
   - Intent Classifier (NLU + heurísticas → Flow Type)
   - Flow Router (proxy para gateways específicos)
   - Rate Limiting (Redis-backed, por tenant)
   - Response Processor (formatação + eventos Kafka)
   - Observabilidade (tracing, metrics, logs)

2. **NLU Service (:8020)** - Novo serviço
   - Extrair NLU do gateway-intencoes (1.303 LOC confirmado)
   - API REST + gRPC
   - Domínio classification (BUSINESS/TECHNICAL/INFRASTRUCTURE/SECURITY)
   - Entity extraction (NER)
   - Confidence calculation
   - Cache Redis (TTL 3600s)
   - Detecção de idioma (pt/en/es)

3. **PII Service (:8021)** - Novo serviço
   - Baseado em neural_hive_specialists/compliance (1.051 LOC total)
   - API REST + gRPC
   - PII detection (23 tipos - PIIDetectorLite)
   - PII masking (reversível via AES-256-GCM - a implementar)
   - Audit logging persistente (MongoDB - a implementar)
   - Auth required (JWT middleware)
   - **Gap crítico:** Unmask reversível requer 5-7 dias de desenvolvimento

4. **Approval Core Package** - Nova biblioteca
   - `neural_hive_approval_common`
   - Modelos unificados (UnifiedApprovalRequest, UnifiedApprovalDecision)
   - Lógica de decisão centralizada
   - Thresholds configuráveis
   - Tests unificados

5. **Refatoração de Serviços Existentes**
   - gateway-intencoes: remover NLU/PII internos (-1.453 LOC confirmado)
   - requirements-engineering: 0 LOC (sem NLU duplicado - já está correto)
   - doc-ingestion: 0 LOC (sem PII duplicado - já está correto)
   - approval-service: migrar para Approval Core (~2.000 LOC)
   - approval-gateway: DEPRECAR, migrar para approval-service
   - Todos os serviços: remover SecurityHeadersMiddleware duplicado

---

## Out of Scope

- Reimplementação completa dos fluxos A-F, G, H
- Mudança de protocolo de Kafka (mantido)
- Mudança de bancos de dados (MongoDB, Redis mantidos)
- Refatoração de especialistas (gRPC services)
- Interface UI nova (apenas API)

---

## Expected Deliverable

1. **Unified Gateway operacional** (:7999)
   - POST `/api/v1/nhm/request` aceita requests de todos os tipos
   - Classifica corretamente intenção (A-F, G ou H) com >90% confiança
   - Rate limiting ativo (100 req/min por tenant)
   - Tracing distribuído funcionando

2. **NLU Service operacional** (:8020)
   - gRPC server respondendo em <50ms (p95)
   - Cache hit rate >70%
   - Testes E2E passando

3. **PII Service operacional** (:8021)
   - Detecta 7 tipos de PII com >95% precisão
   - Audit logging de todas as operações
   - Testes de segurança passando

4. **Approval Core Package publicado**
   - Instalável via pip
   - approval-service usando o package
   - approval-gateway deprecated

5. **Serviços refatorados**
   - gateway-intencoes: -1.453 LOC (1.303 NLU + 150 PII removidos)
   - requirements-engineering: 0 LOC (sem NLU - já alinhado)
   - doc-ingestion: 0 LOC (sem PII - já alinhado)
   - approval-service: ~2.000 LOC extraídos para Approval Core Package
   - Total: ~3.453 LOC de duplicação removidos

6. **Documentação completa**
   - API docs (OpenAPI 3.0)
   - Guia de migração para clientes
   - Runbooks operacionais

---

## Technical Constraints

1. **Performance**
   - Latência adicional do Unified Gateway <20ms (p95)
   - NLU Service <50ms (p95)
   - PII Service <30ms (p95)
   - Não degradar performance dos fluxos existentes

2. **Compatibilidade**
   - Manter compatibilidade com clientes existentes durante migração
   - Suportar ambas as interfaces (nova e velha) durante período de transição

3. **Segurança**
   - PII Service deve ter autenticação obrigatória
   - Audit logging para todas as operações sensíveis
   - Rate limiting não pode ser bypassado

4. **Disponibilidade**
   - Unified Gateway: >99.9% SLA
   - Services compartilhados: >99.9% SLA
   - Graceful degradation se shared services estiverem down

---

## Dependencies

### Serviços Existentes
- `gateway-intencoes` :8000 - Fonte de NLU pipeline
- `requirements-engineering` :8010 - Fonte de NLU secundário
- `doc-ingestion` :8018 - Fonte de PII
- `approval-service` :8004 - Approval principal
- `neural_hive_specialists` - PII detector
- `neural_hive_context` - Context Manager
- `neural_hive_security` - JWT verifier

### Infraestrutura
- Kafka (event bus)
- MongoDB (persistência)
- Redis (cache + rate limiting)
- Temporal (workflows)
- Kubernetes (deploy)

### Bibliotecas
- FastAPI
- gRPC
- spaCy (NLU)
- Redis-py
- PyJWT
---

## Success Criteria

1. **Funcionalidade**
   - ✅ Unified Gateway classifica corretamente >90% das intençãoes
   - ✅ Rate limiting bloqueia excesso de requests
   - ✅ PII detection funciona em todos os fluxos

2. **Performance**
   - ✅ Latência adicional <20ms (p95)
   - ✅ Throughput >200 req/s por instância
   - ✅ Cache hit rate >70%

3. **Código**
   - ✅ >3.000 LOC de duplicação removidos
   - ✅ Test coverage >80% para novos serviços
   - ✅ Zero vulnerabilidades críticas

4. **Operação**
   - ✅ Deploy sem downtime
   - ✅ Rollback funcional
   - ✅ Observabilidade completa

---

## Risk Assessment

| Risco | Impacto | Probabilidade | Mitigação |
|-------|---------|---------------|-----------|
| Unified Gateway SPOF | Alto | Médio | Multi-instance + health checks |
| NLU Service downtime | Alto | Baixo | Fallback para NLU local em gateways |
| Classificação errada | Médio | Médio | Manual override + feedback loop |
| Performance degradation | Alto | Médio | Load testing + cache agressivo |
| Breaking change clientes | Alto | Baixa | Período de grace + backward compat |
| **Unmask reversível não implementado** | Alto | Médio | Criar sistema de tokens AES-256-GCM (5-7 dias) |

---

## Timeline Estimada

- **Sprint 1 (2 semanas):** Unified Gateway MVP + NLU Service (:8020)
- **Sprint 2 (2 semanas):** PII Service (:8021) + refatoração gateway-intencoes
- **Sprint 3 (2 semanas):** Approval Core Package + refatoração approval-service
- **Sprint 4 (2 semanas):** Migrar approval-gateway + testes E2E
- **Sprint 5 (1 semana):** Hardening + documentação
- **Sprint 6 (1 semana):** Deploy + migração clientes

**Total:** 10 semanas (~2.5 meses)

**Nota:** requirements-engineering e doc-ingestion não precisam de refatoração (já alinhados).

---

## References

- Documento de arquitetura: `docs/ARQUITETURA_COEXISTENCIA_FLUXOS_2026-05-01.md`
- Mapeamento codebase: `docs/MAPEAMENTO_COMPLETO_CODEBASE_2026-05-01.md`
- Context Manager: `libs/neural_hive_context/`
- NLU Pipeline: `services/gateway-intencoes/src/pipelines/nlu_pipeline.py`
- PII Detector: `libraries/python/neural_hive_specialists/compliance/pii_detector.py`

---

## Codebase Review (2026-05-04)

**Status:** ✅ Revisão Completa via feature-dev:code-explorer agents

### Descobertas Críticas

| Serviço | LOC Original | LOC Real | Status |
|---------|-------------|----------|--------|
| gateway-intencoes | 800 | 1.453 (1.303 NLU + 150 PII) | ✅ Confirmado |
| requirements-engineering | 300 | 0 | ⚠️ Spec corrigido |
| doc-ingestion | 150 | 0 | ⚠️ Spec corrigido |
| approval-service | - | 2.000 (para Approval Core) | ✅ Confirmado |

### Gaps Identificados no PII Module

- **Unmask reversível:** Não implementado (necessário 5-7 dias)
- **Audit logging persistente:** Apenas logs em memória (necessário 3-4 dias)
- **gRPC service:** Protobuf não definido

**Relatório completo:** `RELATORIO_REVISAO_CODEBASE.md`
