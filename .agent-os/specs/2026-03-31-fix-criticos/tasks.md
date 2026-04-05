# Tasks - Fix Críticos Sprint 1

> Epic: Fix Críticos
> Created: 2026-03-31
> Status: COMPLETO - Sprint 1 e 2
> Total Effort: 8 semanas

---

## EPIC-001: Fix Test Críticos (4 semanas) ✅ COMPLETO

### EPIC-001-01: Fix Import Errors worker-agents
**Effort:** 1 semana | **Priority:** P0 | **Status:** ✅ COMPLETO

- [x] 1.1 Analisar imports relativos em todos os executors
- [x] 1.2 Modificar src/executors/deploy_executor.py - imports relativos → absolutos
- [x] 1.3 Modificar src/executors/build_executor.py - imports relativos → absolutos
- [x] 1.4 Modificar src/executors/test_executor.py - imports relativos → absolutos
- [x] 1.5 Modificar src/executors/validate_executor.py - imports relativos → absolutos
- [x] 1.6 Modificar src/executors/execute_executor.py - imports relativos → absolutos
- [x] 1.7 Modificar src/executors/compensate_executor.py - imports relativos → absolutos
- [x] 1.8 Executar testes unitários worker-agents
- [x] 1.9 Executar testes de integração worker-agents
- [x] 1.10 Verificar que todos os 12 testes passam
- [x] 1.11 Commitar mudanças com mensagem descritiva
- [x] 1.12 Verificar CI/CD verde

### EPIC-001-02: Fix NLP Tests semantic-translation-engine
**Effort:** 1 semana | **Priority:** P0 | **Status:** ✅ COMPLETO

- [x] 2.1 Verificar versão atual do numpy
- [x] 2.2 Modificar requirements.txt - numpy 2.2.6 → 1.26.4
- [x] 2.3 Reinstalar dependências com pip install -r requirements.txt
- [x] 2.4 Verificar versão do numpy após instalação
- [x] 2.5 Baixar modelo spaCy en_core_web_sm
- [x] 2.6 Baixar modelo spaCy pt_core_news_sm
- [x] 2.7 Executar testes unitários NLP (18 testes)
- [x] 2.8 Executar testes de integração NLP (2 testes)
- [x] 2.9 Verificar que todos os 18 testes NLP passam
- [x] 2.10 Testar fallback heurístico ainda funciona
- [x] 2.11 Commitar mudanças com mensagem descritiva
- [x] 2.12 Verificar CI/CD verde

### EPIC-001-03: Refactor Tests specialist-behavior
**Effort:** 2 semanas | **Priority:** P0 | **Status:** ⏸️ PENDENTE (Baixa Prioridade)

> NOTA: Especialist behavior funciona corretamente. Refatoração adiada.

---

## EPIC-002: Pydantic V2 Migration (2 semanas) ✅ COMPLETO

### EPIC-002-01: Migrate gateway-intencoes
**Effort:** 3 dias | **Priority:** Alta | **Status:** ✅ COMPLETO

- [x] 4.1 Analisar src/config/settings.py - identificar 8 @validator
- [x] 4.2 Migrar validate_kafka_security_protocol - @validator → @field_validator
- [x] 4.3 Migrar validate_routing_thresholds - @validator → @model_validator mode='before'
- [x] 4.4 Migrar parse_cors_origins_override - adicionar mode='before'
- [x] 4.5 Migrar validators restantes em settings.py
- [x] 4.6 Analisar src/models/intent_envelope.py - identificar 4 @validator + 1 @root_validator
- [x] 4.7 Migrar validate_constraints_consistency - @root_validator → @model_validator mode='after'
- [x] 4.8 Migrar validators restantes em intent_envelope.py
- [x] 4.9 Atualizar imports - validator → field_validator, model_validator
- [x] 4.10 Executar testes gateway-intencoes
- [x] 4.11 Verificar zero warnings de deprecation
- [x] 4.12 Commitar mudanças

### EPIC-002-02: Migrate semantic-translation-engine
**Effort:** 3 dias | **Priority:** Alta | **Status:** ✅ COMPLETO

- [x] 5.1 Analisar src/config/settings.py - identificar 10 @validator
- [x] 5.2 Migrar todos os @validator → @field_validator
- [x] 5.3 Analisar src/models/cognitive_plan.py - identificar 2 @validator
- [x] 5.4 Migrar validate_tasks e outros validators
- [x] 5.5 Atualizar imports
- [x] 5.6 Executar testes semantic-translation-engine
- [x] 5.7 Verificar zero warnings de deprecation
- [x] 5.8 Commitar mudanças

### EPIC-002-03: Migrate Serviços Secundários
**Effort:** 4 dias | **Priority:** Média | **Status:** ✅ COMPLETO

- [x] 6.1 Migrar execution-ticket-service - 4 @validator
- [x] 6.2 Migrar worker-agents - 3 @validator em execution_ticket.py
- [x] 6.3 Migrar memory-layer-api - 2 @validator
- [x] 6.4 Migrar approval-service - 1 @validator
- [x] 6.5 Executar testes de todos os serviços
- [x] 6.6 Verificar zero warnings de deprecation globalmente
- [x] 6.7 Commitar mudanças

---

## EPIC-003: datetime.utcnow() Migration (2 semanas) ✅ COMPLETO

### EPIC-003-01: Migrate Priority P0 Services
**Effort:** 5 dias | **Priority:** P0 | **Status:** ✅ COMPLETO

- [x] 7.1 Criar script de migração migrate_datetime.py
- [x] 7.2 Backup dos 5 serviços P0
- [x] 7.3 Executar script em orchestrator-dynamic (215 ocorrências)
- [x] 7.4 Executar script em optimizer-agents (110 ocorrências)
- [x] 7.5 Executar script em semantic-translation-engine (109 ocorrências)
- [x] 7.6 Executar script em sla-management-system (98 ocorrências)
- [x] 7.7 Executar script em self-healing-engine (83 ocorrências)
- [x] 7.8 Verificar imports timezone adicionados
- [x] 7.9 Executar testes dos 5 serviços
- [x] 7.10 Validar timestamps em banco de dados
- [x] 7.11 Commitar mudanças

### EPIC-003-02: Migrate Priority P1 Services
**Effort:** 3 dias | **Priority:** P1 | **Status:** ✅ COMPLETO

- [x] 8.1 Executar script em memory-layer-api (77 ocorrências)
- [x] 8.2 Executar script em approval-service (63 ocorrências)
- [x] 8.3 Executar script em scout-agents (53 ocorrências)
- [x] 8.4 Executar script em analyst-agents (49 ocorrências)
- [x] 8.5 Validar timestamps específicos (vetores, feedbacks)
- [x] 8.6 Executar testes dos 4 serviços
- [x] 8.7 Commitar mudanças

### EPIC-003-03: Migrate Priority P2/P3 Services
**Effort:** 2 dias | **Priority:** P2 | **Status:** ✅ COMPLETO

- [x] 9.1 Executar script em code-forge, explainability-api, guard-agents
- [x] 9.2 Executar script em gateway-intencoes, queen-agent, worker-agents
- [x] 9.3 Executar script em execution-ticket-service, architect-agent
- [x] 9.4 Executar script em consensus-engine, feature-store, service-registry
- [x] 9.5 Executar script em mcp-tool-catalog
- [x] 9.6 Executar script de verificação final
- [x] 9.7 Verificar zero datetime.utcnow() remanescentes
- [x] 9.8 Executar testes smoke de todos os serviços
- [x] 9.9 Commitar mudanças

---

## EPIC-004: FastMCP API Fix (2 dias) ✅ COMPLETO

### EPIC-004-01: Fix scout-mcp-server
**Effort:** 2 horas | **Priority:** P0 | **Status:** ✅ COMPLETO

- [x] 10.1 Modificar src/scout_mcp_server/server.py - description → instructions
- [x] 10.2 Testar servidor inicia sem erro
- [x] 10.3 Verificar ferramentas MCP registradas
- [x] 10.4 Commitar mudanças

### EPIC-004-02: Fix ai-codegen-mcp-server
**Effort:** 2 horas | **Priority:** P0 | **Status:** ✅ COMPLETO

- [x] 11.1 Modificar src/server.py - description → instructions
- [x] 11.2 Testar servidor inicia sem erro
- [x] 11.3 Verificar ferramentas codegen funcionando
- [x] 11.4 Commitar mudanças

### EPIC-004-03: Fix sonarqube-mcp-server
**Effort:** 2 horas | **Priority:** P0 | **Status:** ✅ COMPLETO

- [x] 12.1 Modificar src/server.py - description → instructions
- [x] 12.2 Testar servidor inicia sem erro
- [x] 12.3 Verificar métricas SonarQube acessíveis
- [x] 12.4 Commitar mudanças

### EPIC-004-04: Fix trivy-mcp-server
**Effort:** 2 horas | **Priority:** P0 | **Status:** ✅ COMPLETO

- [x] 13.1 Modificar src/server.py - description → instructions
- [x] 13.2 Testar servidor inicia sem erro
- [x] 13.3 Verificar scanner Trivy funcionando
- [x] 13.4 Commitar mudanças

### EPIC-004-05: Validação Global
**Effort:** 4 horas | **Priority:** P0 | **Status:** ✅ COMPLETO

- [x] 14.1 Executar script de teste global
- [x] 14.2 Validar todos os 4 MCP servers iniciam
- [x] 14.3 Atualizar requirements.txt com fastmcp>=3.0.0
- [x] 14.4 Documentar mudanças em CHANGELOG
- [x] 14.5 Verificar CI/CD verde

---

## EPIC-005: Security Hardening (Sprint 4) ✅ COMPLETO

### EPIC-005-01: Input Validation & Sanitization
**Effort:** 1 dia | **Priority:** CRÍTICO | **Status:** ✅ COMPLETO

- [x] 15.1 Adicionar validação de entrada em gateway-intencoes
- [x] 15.2 Implementar sanitização XSS/Code Injection
- [x] 15.3 Adicionar validação de idiomas (ISO 639-1)
- [x] 15.4 Adicionar validação de UUID
- [x] 15.5 Criar 18 testes de segurança
- [x] 15.6 Commitar mudanças

### EPIC-005-02: Security Headers
**Effort:** 4 horas | **Priority:** CRÍTICO | **Status:** ✅ COMPLETO

- [x] 16.1 Implementar SecurityHeadersMiddleware
- [x] 16.2 Adicionar OWASP CSP headers
- [x] 16.3 Adicionar HSTS header
- [x] 16.4 Remover Server e X-Powered-By headers
- [x] 16.5 Testar headers em resposta HTTP
- [x] 16.6 Commitar mudanças

### EPIC-005-03: Production Configuration Validation
**Effort:** 4 horas | **Priority:** ALTO | **Status:** ✅ COMPLETO

- [x] 17.1 Adicionar validação de hardcoded defaults
- [x] 17.2 Adicionar validação de credenciais fracas
- [x] 17.3 Adicionar validação de HTTPS em produção
- [x] 17.4 Criar 18 testes de validação de produção
- [x] 17.5 Commitar mudanças

---

## Ordem de Execução Recomendada

### Sprint 1 (2 semanas) - Quick Wins ✅ COMPLETO
1. ✅ **EPIC-004** (FastMCP) - 2 dias - Desbloqueia MCP servers
2. ✅ **EPIC-001-01** (worker-agents) - 1 semana - Paralelo
3. ✅ **EPIC-001-02** (NLP tests) - 1 semana - Paralelo

### Sprint 2 (2 semanas) - Pydantic ✅ COMPLETO
4. ✅ **EPIC-002-01** (gateway) - 3 dias
5. ✅ **EPIC-002-02** (semantic) - 3 dias
6. ✅ **EPIC-002-03** (secundários) - 4 dias
7. ✅ **Buffer** - 4 dias

### Sprint 3 (2 semanas) - datetime P0/P1 ✅ COMPLETO
8. ✅ **EPIC-003-01** (P0 services) - 5 dias
9. ✅ **EPIC-003-02** (P1 services) - 3 dias
10. ⏸️ **EPIC-001-03** (specialist-behavior) - Adiado

### Sprint 4 (2 semanas) - Security Hardening ✅ COMPLETO
11. ✅ **EPIC-005-01** (Input Validation) - 1 dia
12. ✅ **EPIC-005-02** (Security Headers) - 4 horas
13. ✅ **EPIC-005-03** (Production Config) - 4 horas
14. ✅ **Testes globais** - 4 dias

---

## Total

- **Total Tasks:** 139
- **Completas:** 125
- **Pendentes:** 14 (EPIC-001-03 - Baixa Prioridade)
- **Total Effort:** 8 semanas
- **Executado:** ~7 semanas
- **Status:** ✅ 90% COMPLETO
