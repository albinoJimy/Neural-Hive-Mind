# Spec Summary (Lite)

Corrigir 3 gaps validados na Fase 1 Cognitiva: CONSENSUS-002 (correlation_id ausente), MEMORY-001 (ClickHouse sem fallback), SPECIALIST-002 (sem indicador ML vs heurística).

---

## Overview

Após validação profunda do codebase, 3 gaps reais foram confirmados e precisam de correção: validação de correlation_id no ConsensusOrchestrator, implementação de fallback para ClickHouse e adição de indicador de método de decisão (ML vs heurística) nos votos dos especialistas.

---

## Spec Scope

### CONSENSUS-002: correlation_id Ausente
1. Configuração `fail_on_missing_correlation_id` no settings
2. Validação estrita quando config=True (exceção se ausente)
3. Exceção customizada ConsensusValidationError
4. Testes unitários (5 cenários)

### MEMORY-001: ClickHouse Sem Fallback
1. ClickHouseFallbackBuffer (buffer circular thread-safe)
2. Integração no UnifiedMemoryClient (auto-fallback)
3. FallbackDrainer (worker background para drenagem MongoDB)
4. Testes de integração (4 cenários)

### SPECIALIST-002: Indicador ML vs Heurística
1. Campo `decision_method` no SpecialistVote
2. Enum DecisionMethod (ML/HEURISTIC/HYBRID)
3. Detecção automática baseada em campos da opinião
4. Testes unitários (4 cenários)

---

## Expected Deliverable

1. correlation_id validado corretamente no ConsensusOrchestrator
2. ClickHouse com fallback funcional para MongoDB
3. Indicador de método de decisão exposto nas decisões consolidadas
4. Todos os testes passando (13 novos testes)
