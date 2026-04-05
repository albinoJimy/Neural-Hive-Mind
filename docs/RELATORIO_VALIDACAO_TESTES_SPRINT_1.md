# Relatório de Validação de Testes - Sprint 1
**Data:** 2026-03-31
**Objetivo:** Validar que as migrações (Pydantic v2, datetime) não quebraram funcionalidade

---

## Resumo Executivo

| Serviço | Passando | Falhando | Erros | Status |
|---------|----------|----------|-------|--------|
| gateway-intencoes | 89 | 35 | 91 | ⚠️ |
| semantic-translation-engine | - | - | - | ⏳ (timeout/collection) |
| consensus-engine | 229 | 20 | 17 | ⚠️ |
| orchestrator-dynamic | 226 | 11 | 70 | ⚠️ |
| worker-agents | 293 | 328 | 16 | ❌ |
| scout-mcp-server | 16 | 0 | 0 | ✅ |
| optimizer-mcp-server | 17 | 0 | 0 | ✅ **(FIXED)** |
| **TOTAL** | **870** | **394** | **194** | **52% passando** |

**Fixes Aplicados Durante Validação:**
1. ✅ optimizer-mcp-server: `sse_app()` -> `http_app()` (FastMCP API update)
2. ✅ semantic-translation-engine: `field_validator.Info` -> `ValidationInfo`
3. ✅ consensus-engine: Adicionado mock de `specialist_seniority` e `neural_hive_observability`

---

## Detalhes por Serviço

### 1. gateway-intencoes
- **Status:** 89 passed, 35 failed, 91 errors
- **Problemas Críticos:**
  - Erros de permissão: `FileNotFoundError: /app/models/whisper` - testes ASR tentam criar diretórios sem permissão
  - DeprecationWarnings: `class-based config` deve virar `ConfigDict` (Pydantic v2)
  - `Field(env=...)` deprecated - usar `json_schema_extra`

- **Ações Necessárias:**
  1. Mock de filesystem para testes ASR
  2. Migrar `class Config` para `ConfigDict`
  3. Substituir `env=` por `Field(default=..., validation_alias=...)`

### 2. semantic-translation-engine
- **Status:** ❌ Collection error + Timeout
- **Problemas Críticos:**
  - ✅ CORRIGIDO: `field_validator.Info` -> `ValidationInfo` em `src/config/settings.py`
  - Timeout em testes E2E (dependência de serviços externos)
  - Collection error em testes

- **Fixes Aplicados:**
  1. ✅ Import `ValidationInfo` e correção do validator

- **Ações Necessárias:**
  1. Executar apenas testes unitários para evitar timeout
  2. Verificar mocks de Kafka/MongoDB em testes E2E

### 3. consensus-engine
- **Status:** 229 passed, 20 failed, 17 errors
- **Problemas Críticos:**
  - 20 testes de correlation_id falhando: **TypeError: Axis must be specified when shapes differ** (erro em `np.average` no código de consenso, não teste)
  - 18 testes de QueenAgentGrpcClient falhando (gRPC client issue)
  - 7 errors em plan_consumer_resilience (import/setup errors)

- **Fixes Aplicados:**
  1. ✅ Adicionado mock de `specialist_seniority` em `mock_consensus_orchestrator_config`
  2. ✅ Adicionado mock de `neural_hive_observability` com `get_tracer()` no conftest.py

- **Problema Restante:**
  - `np.average` recebe arrays de shapes diferentes - possível bug no cálculo de pesos bayesianos

### 4. orchestrator-dynamic
- **Status:** 226 passed, 11 failed, 70 errors
- **Problemas Críticos:**
  - 70 errors em testes de approval_processor (collection error)
  - 11 failures em testes de saga/orchestrator

- **Ações Necessárias:**
  1. Investigar erro de coleta em approval_processor
  2. Verificar se há problema de import circular

### 5. worker-agents
- **Status:** 293 passed, 328 failed, 16 errors
- **Problemas Críticos:**
  - MAIORIA dos testes falhando (328 falhas vs 293 passando)
  - Problemas em test_executor_refactored (5 falhas)
  - Problemas em test_report_parser (15 falhas)
  - Problemas em validate_executor_opa (10 falhas)
  - 16 errors em integration tests (MongoDB connection)

- **Ações Necessárias:**
  1. Prioridade ALTA - investigar por que maioria dos testes falha
  2. Verificar se há problema de setup/fixture
  3. Mock de MongoDB para integration tests

### 6. scout-mcp-server
- **Status:** ✅ 16 passed
- **Observações:**
  - Todos os testes passam
  - Coverage warning: 0% (configuração de coverage incorreta)

### 7. optimizer-mcp-server
- **Status:** ✅ **FIXED** - 17 passed (anterior: 1 error)
- **Problema Resolvido:**
  - `AttributeError: 'FastMCP' object has no attribute 'sse_app'`
  - **Fix aplicado:** Mudança de API `sse_app()` -> `http_app()` (FastMCP atualizado)

- **Observações:**
  - Todos os 17 testes passando após correção
  - Coverage warning: 0% (configuração de coverage incorreta, não funcional)

---

## Issues Críticos Remanescentes

### Prioridade 1 (Bloqueiam Deploy)
1. **worker-agents:** 328 testes falhando - mais de 50% da suíte
2. **gateway-intencoes:** Permissões de filesystem em testes ASR
3. **consensus-engine:** TypeError no cálculo de pesos (np.average shapes mismatch)
4. **semantic-translation-engine:** Collection error e timeout

### Prioridade 2 (Impactam Funcionalidade)
5. **consensus-engine:** 18 testes de QueenAgentGrpcClient falhando (gRPC mock)
6. **orchestrator-dynamic:** 70 errors em approval_processor (collection)
7. **consensus-engine:** 7 errors em plan_consumer_resilience

### Prioridade 3 (Warnings/Deprecation)
8. **Pydantic v2 migration:** Múltiplos serviços com deprecation warnings
9. **Field(env=...):** Substituir por `validation_alias` em todos os serviços

---

## Recomendações Imediatas

1. **Focar em worker-agents primeiro** - tem mais testes falhando que passando
2. **Criar fixtures padrão** para filesystem, MongoDB, gRPC (evitar duplicação)
3. **Separar testes unitários de integração** - usar marcadores pytest
4. **Mock de dependências externas** - Kafka, Redis, MongoDB devem ser mockados em testes unitários
5. **Revisar coverage configuration** - muitos serviços com 0% reportado

---

## Próximos Passos

1. Corrigir worker-agents (investigar causa raiz das falhas)
2. Fix optimizer-mcp-server (FastMCP version)
3. Criar script de testes em CI/CD que falha fast em erros de coleção
4. Documentar padrões de mocks para reuse entre serviços
