# HANDOFF - Correção de Gaps Fase 1 Cognitiva

**Data:** 2026-04-05
**Epic:** GAPS-001 to GAPS-003 - Correção de Gaps Críticos Fase 1
**Status:** Ready for Implementation
**Estimativa Total:** 34 story points (~10-12 dias)

---

## Resumo Executivo

Após validação profunda do codebase, foram identificados **3 gaps reais** que precisam de correção na Fase 1 Cognitiva:

| Gap | Prioridade | Complexidade | Tickets | SP |
|-----|------------|--------------|---------|----|
| CONSENSUS-002 | High | S | 4 | 8 |
| MEMORY-001 | Critical | M | 4 | 18 |
| SPECIALIST-002 | Medium | M | 4 | 8 |

**5 falsos positivos** foram descartados após análise detalhada do código.

---

## Gaps Confirmados

### Gap 1: CONSENSUS-002 - correlation_id Ausente (High)

**Problema:** O ConsensusOrchestrator gera UUID quando correlation_id está ausente, mascarando problemas upstream e comprometendo a rastreabilidade end-to-end.

**Arquivo:** `services/consensus-engine/src/services/consensus_orchestrator.py:142-161`

**Solução:** Implementar validação estrita configurável.

---

### Gap 2: MEMORY-001 - ClickHouse Sem Fallback (Critical)

**Problema:** ClickHouse é opcional mas não há fallback quando indisponível, causando perda de histórico de dados.

**Arquivo:** `services/memory-layer-api/src/main.py:92-101`

**Solução:** Implementar ClickHouseFallbackBuffer com drenagem para MongoDB.

---

### Gap 3: SPECIALIST-002 - Sem Indicador ML vs Heurística (Medium)

**Problema:** Não há campo para indicar quais especialistas usaram ML vs heurística em cada decisão.

**Arquivo:** `services/consensus-engine/src/models/consolidated_decision.py`

**Solução:** Adicionar campo `decision_method` no SpecialistVote.

---

## Tickets Decompostos

### Epic GAPS-02: CONSENSUS-002 (4 tickets, 8 SP)

#### GAPS-02-01: Configurar fail_on_missing_correlation_id
- **Tipo:** Feature | **Prioridade:** High | **SP:** 2
- **Descrição:** Adicionar configuração `fail_on_missing_correlation_id` no settings
- **Arquivos:** `services/consensus-engine/src/config/settings.py`
- **Aceite:** Config adicionada, default=False, documentada

#### GAPS-02-02: Implementar Validação Estrita
- **Tipo:** Feature | **Prioridade:** High | **SP:** 3
- **Descrição:** Lógica de validação quando config=True
- **Arquivos:** `services/consensus-engine/src/services/consensus_orchestrator.py:142-162`
- **Aceite:** Exceção se config=True e correlation_id ausente

#### GAPS-02-03: Criar Exceção Customizada
- **Tipo:** Feature | **Prioridade:** Medium | **SP:** 1
- **Descrição:** Criar ConsensusValidationError
- **Arquivos:** `services/consensus-engine/src/exceptions.py` (NOVO)
- **Aceite:** Herda ValueError, campos: field_name, expected, actual

#### GAPS-02-04: Testes Unitários
- **Tipo:** Test | **Prioridade:** High | **SP:** 2
- **Descrição:** Testes para validação de correlation_id
- **Arquivos:** `services/consensus-engine/tests/test_consensus_orchestrator_validation.py` (NOVO)
- **Aceite:** 5 cenários de teste cobertos

---

### Epic GAPS-01: MEMORY-001 (4 tickets, 18 SP)

#### GAPS-01-01: Criar ClickHouseFallbackBuffer
- **Tipo:** Feature | **Prioridade:** Critical | **SP:** 5
- **Descrição:** Buffer circular para eventos quando ClickHouse down
- **Arquivos:** `services/memory-layer-api/src/services/clickhouse_fallback_buffer.py` (NOVO)
- **Aceite:** Thread-safe, métrica Prometheus, persistência Redis

#### GAPS-01-02: Integrar Fallback no UnifiedMemoryClient
- **Tipo:** Feature | **Prioridade:** Critical | **SP:** 5
- **Descrição:** Modificar cliente para usar fallback automaticamente
- **Arquivos:** `services/memory-layer-api/src/clients/unified_memory_client.py`
- **Aceite:** Catch exceções, redirecionar para buffer, métricas

#### GAPS-01-03: Implementar Drenagem para MongoDB
- **Tipo:** Feature | **Prioridade:** High | **SP:** 5
- **Descrição:** Worker background para drenar buffer
- **Arquivos:** `services/memory-layer-api/src/services/fallback_drainer.py` (NOVO)
- **Aceite:** Task periódica, batch insert, remove drenados

#### GAPS-01-04: Testes Integração
- **Tipo:** Test | **Prioridade:** High | **SP:** 3
- **Descrição:** Testes E2E do fluxo de fallback
- **Arquivos:** `services/memory-layer-api/tests/test_fallback_integration.py` (NOVO)
- **Aceite:** 4 cenários de teste cobertos

---

### Epic GAPS-03: SPECIALIST-002 (4 tickets, 8 SP)

#### GAPS-03-01: Adicionar Campo decision_method
- **Tipo:** Feature | **Prioridade:** Medium | **SP:** 2
- **Descrição:** Estender SpecialistVote com campo decision_method
- **Arquivos:** `services/consensus-engine/src/models/consolidated_decision.py:32-56`
- **Aceite:** Campo Optional[str], valores: ml/heuristic/hybrid

#### GAPS-03-02: Enum DecisionMethod
- **Tipo:** Feature | **Prioridade:** Medium | **SP:** 1
- **Descrição:** Criar enum e constantes para métodos de decisão
- **Arquivos:** `services/consensus-engine/src/models/decision_method.py` (NOVO)
- **Aceite:** Enum ML/HEURISTIC/HYBRID, função infer()

#### GAPS-03-03: Populamento Automático
- **Tipo:** Feature | **Prioridade:** Medium | **SP:** 3
- **Descrição:** Detectar automaticamente ML vs heurística
- **Arquivos:** `services/consensus-engine/src/services/consensus_orchestrator.py`
- **Aceite:** Detecção baseada em campos ml_confidence, model_version

#### GAPS-03-04: Testes Unitários
- **Tipo:** Test | **Prioridade:** Medium | **SP:** 2
- **Descrição:** Testes para detecção de decision_method
- **Arquivos:** `services/consensus-engine/tests/test_decision_method_detection.py` (NOVO)
- **Aceite:** 4 cenários de teste cobertos

---

## Ordem de Implementação Sugerida

### Sprint 1 (Semana 1-2) - Críticos
1. **GAPS-01-01**: ClickHouseFallbackBuffer (5 SP)
2. **GAPS-01-02**: Integrar Fallback (5 SP)
3. **GAPS-01-03**: Drenagem para MongoDB (5 SP)
4. **GAPS-01-04**: Testes Integração (3 SP)

**Entrega:** ClickHouse com fallback funcional

### Sprint 2 (Semana 3-4) - Alta Prioridade
1. **GAPS-02-01**: Config fail_on_missing_correlation_id (2 SP)
2. **GAPS-02-02**: Validação Estrita (3 SP)
3. **GAPS-02-03**: Exceção Customizada (1 SP)
4. **GAPS-02-04**: Testes (2 SP)

**Entrega:** correlation_id validado corretamente

### Sprint 3 (Semana 5) - Média Prioridade
1. **GAPS-03-01**: Campo decision_method (2 SP)
2. **GAPS-03-02**: Enum DecisionMethod (1 SP)
3. **GAPS-03-03**: Populamento Automático (3 SP)
4. **GAPS-03-04**: Testes (2 SP)

**Entrega:** Indicador ML vs heurística implementado

---

## Instruções para Claude Code

### Como Executar Este Epic

```bash
# 1. Navegar para o diretório do projeto
cd /home/jimy/NHM/Neural-Hive-Mind

# 2. Criar branch para o epic
git checkout -b feat/GAPS-001-fase1-corrections

# 3. Para cada ticket, seguir TDD:
#    a. Escrever teste primeiro
#    b. Implementar código
#    c. Verificar testes passando
#    d. Fazer commit

# Exemplo para GAPS-02-01:
# 1. Criar teste em services/consensus-engine/tests/test_settings_validation.py
# 2. Adicionar campo em services/consensus-engine/src/config/settings.py
# 3. Rodar: pytest services/consensus-engine/tests/test_settings_validation.py -v
# 4. Commit: git commit -m "feat(GAPS-02-01): add fail_on_missing_correlation_id config"
```

### Convenções de Commit

```
feat(GAPS-XX-YY): descrição curta

- Corrige CONSENSUS-002: correlation_id ausente
- Adiciona configuração fail_on_missing_correlation_id
- Testes: 5/5 passando

Refs: GAPS-XX-YY
```

### Testes Antes de Push

```bash
# Linting
ruff check services/

# Formatação
black services/

# Testes unitários
pytest services/ -v --tb=short

# Testes específicos do ticket
pytest services/consensus-engine/tests/test_*validation* -v
```

---

## Documentação de Referência

- **Relatório de Validação:** `docs/RELATORIO_VALIDACAO_GAPS_2026-04-05.md`
- **Spec Detalhada:** `.agent-os/specs/2026-04-05-fase1-gaps-correction/spec.md`
- **Revisão Fase 1:** `docs/RELATORIO_REVISAO_FASE1_COGNITIVA_2026-04-05.md`

---

## Checklist de Handoff

- [x] Gaps validados profundamente no codebase
- [x] Falsos positivos identificados e descartados
- [x] Specs criadas para cada gap confirmado
- [x] Tickets decompostos em tarefas executáveis
- [x] Estimativas de complexidade atribuídas
- [x] Dependências mapeadas
- [x] Ordem de implementação sugerida
- [x] Instruções para Claude Code preparadas

**Status:** ✅ READY FOR IMPLEMENTATION

---

**Handoff preparado por:** AI Agent (Feature Dev: Code Reviewer + Code Architect)
**Data:** 2026-04-05
**Próximo passo:** Executar GAPS-01-01 (ClickHouseFallbackBuffer)
