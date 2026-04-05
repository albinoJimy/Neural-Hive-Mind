# Spec Summary (Lite)

Corrigir 45 issues críticos identificados na análise completa dos 26 serviços do Neural-Hive-Mind. O sprint é dividido em 4 epics principais: Fix Test Críticos (91 testes), Pydantic V2 Migration (34 decorators), datetime.utcnow() Migration (1,547 ocorrências), e FastMCP API Fix (4 servidores).

## 4 Epics

### EPIC-001: Fix Test Críticos (4 semanas)
Corrigir 30+ testes falhando em worker-agents (12 import errors), semantic-translation-engine (18 NLP numpy/spaCy), e specialist-behavior (61 testes sem coverage real).

### EPIC-002: Pydantic V2 Migration (2 semanas)
Migrar 34 decorators @validator para @field_validator/@model_validator em 6 serviços já usando Pydantic V2.10.4.

### EPIC-003: datetime.utcnow() Migration (2 semanas)
Migrar 1,547 ocorrências de datetime.utcnow() para datetime.now(timezone.utc) em 21 serviços para compatibilidade Python 3.12+.

### EPIC-004: FastMCP API Fix (2 dias)
Corrigir 4 MCP servers substituindo argumento 'description' por 'instructions' no FastMCP.

## Ordem Recomendada

1. EPIC-004 (2 dias) - Quick win, desbloqueia MCP servers
2. EPIC-001-01 + EPIC-001-02 (1 semana, paralelo) - Testes críticos
3. EPIC-002 (2 semanas) - Pydantic migration
4. EPIC-003-01 + EPIC-003-02 (1 semana) - datetime P0/P1
5. EPIC-001-03 (2 semanas) - Refactor specialist-behavior
6. EPIC-003-03 (2 dias) - datetime P2/P3

Total: 8 semanas até 100% dos issues críticos resolvidos.
