# Spec Requirements Document

> Spec: Correção de Gaps Críticos Fase 1 Cognitiva
> Created: 2026-04-05
> Status: Planning

---

## Overview

Corrigir 3 gaps identificados e validados na Fase 1 Cognitiva do Neural-Hive-Mind após revisão independente do codebase. Estes gaps afetam rastreabilidade, resiliência e auditabilidade do sistema.

**Motivação:** Após validação profunda, 3 gaps reais foram confirmados (5 falsos positivos descartados). As correções são necessárias para garantir qualidade de produção.

---

## Gap 1: CONSENSUS-002 - correlation_id Ausente

### User Stories

**Como** Engenheiro de Observabilidade,
**Eu quero** que o sistema rejeite planos sem correlation_id em produção,
**Para que** a rastreabilidade end-to-end seja garantida.

### Spec Scope

1. **Configuração fail_on_missing_correlation_id**
   - Campo no settings.py com default=False
   - Documentação da configuração

2. **Validação estrita no ConsensusOrchestrator**
   - Se config=True e correlation_id ausente: levantar ConsensusValidationError
   - Se config=False: gerar UUID fallback (comportamento atual)
   - Métrica Prometheus incrementada

3. **Exceção customizada ConsensusValidationError**
   - Herda de ValueError
   - Campos: field_name, expected_value, actual_value
   - Método to_dict() para serialização

4. **Testes unitários**
   - 5 cenários de teste cobertos

### Out of Scope

- Modificação do Gateway ou STE para garantir correlation_id (separado)
- Alteração do schema Avro do CognitivePlan

### Expected Deliverable

1. Config `fail_on_missing_correlation_id` funcional
2. Validação estrita implementada e testada
3. Exceção ConsensusValidationError criada
4. 5 testes unitários passando

---

## Gap 2: MEMORY-001 - ClickHouse Sem Fallback

### User Stories

**Como** Engenheiro de Dados,
**Eu quero** que o sistema armazene dados históricos mesmo quando ClickHouse está indisponível,
**Para que** não haja perda de dados de observabilidade.

### Spec Scope

1. **ClickHouseFallbackBuffer**
   - Buffer circular com capacidade configurável (1000 eventos)
   - Thread-safe para escritas concorrentes
   - Persistência temporária em Redis (backup)
   - Métrica fallback_buffer_size no Prometheus

2. **Integração no UnifiedMemoryClient**
   - Catch exceções do ClickHouseClient
   - Redirecionar para ClickHouseFallbackBuffer automaticamente
   - Log estruturado do evento de fallback
   - Métrica clickhouse_fallback_triggered

3. **FallbackDrainer (worker background)**
   - Task asyncio periódica (30s)
   - Batch insert no MongoDB (100 eventos por vez)
   - Remove eventos drenados com sucesso
   - Logs de progresso

4. **Testes de integração**
   - 4 cenários E2E cobertos

### Out of Scope

- Modificação do schema ClickHouse
- Otimização de performance do MongoDB
- UI para monitoração do buffer

### Expected Deliverable

1. ClickHouseFallbackBuffer implementado
2. Integração no UnifiedMemoryClient
3. FallbackDrainer funcional
4. 4 testes de integração passando

---

## Gap 3: SPECIALIST-002 - Sem Indicador ML vs Heurística

### User Stories

**Como** Auditor de Decisões,
**Eu quero** saber quais especialistas usaram ML vs heurística em cada decisão,
**Para que** possa auditar a qualidade das decisões automatizadas.

### Spec Scope

1. **Campo decision_method no SpecialistVote**
   - Optional[str] com valores: "ml", "heuristic", "hybrid"
   - Validador Pydantic para valores inválidos
   - Default: None (backward compatibility)

2. **Enum DecisionMethod**
   - Enum com valores: ML, HEURISTIC, HYBRID
   - Constantes para detecção automática
   - Função infer_decision_method()

3. **Populamento automático**
   - Detectar se opinion tem campos ML (ml_confidence, model_version)
   - Se presente: "ml"
   - Se ausente: "heuristic"
   - Ambos: "hybrid"

4. **Testes unitários**
   - 4 cenários de teste cobertos

### Out of Scope

- Modificação dos especialistas para expor mais metadata
- Dashboard de visualização de decision_method
- Retreinamento de modelos baseado nesta métrica

### Expected Deliverable

1. Campo decision_method implementado
2. Enum DecisionMethod criado
3. Populamento automático funcional
4. 4 testes unitários passando

---

## Tasks Breakdown

### Epic GAPS-02: CONSENSUS-002

- [ ] 1. Configurar fail_on_missing_correlation_id (S)
  - [ ] 1.1 Adicionar campo no settings.py
  - [ ] 1.2 Documentar configuração
  - [ ] 1.3 Testar default value

- [ ] 2. Implementar Validação Estrita (M)
  - [ ] 2.1 Modificar consensus_orchestrator.py:142-162
  - [ ] 2.2 Adicionar lógica condicional baseada em config
  - [ ] 2.3 Adicionar métrica Prometheus
  - [ ] 2.4 Adicionar log estruturado

- [ ] 3. Criar Exceção Customizada (XS)
  - [ ] 3.1 Criar arquivo exceptions.py
  - [ ] 3.2 Implementar ConsensusValidationError
  - [ ] 3.3 Adicionar método to_dict()

- [ ] 4. Testes Unitários (S)
  - [ ] 4.1 Criar arquivo test_consensus_orchestrator_validation.py
  - [ ] 4.2 Teste: correlation_id presente ✅
  - [ ] 4.3 Teste: correlation_id ausente + config=False ✅
  - [ ] 4.4 Teste: correlation_id ausente + config=True ❌
  - [ ] 4.5 Teste: métrica Prometheus incrementada
  - [ ] 4.6 Verificar todos os testes passando

### Epic GAPS-01: MEMORY-001

- [ ] 1. Criar ClickHouseFallbackBuffer (M)
  - [ ] 1.1 Criar arquivo clickhouse_fallback_buffer.py
  - [ ] 1.2 Implementar buffer circular thread-safe
  - [ ] 1.3 Adicionar persistência Redis
  - [ ] 1.4 Expor métrica Prometheus

- [ ] 2. Integrar Fallback no UnifiedMemoryClient (M)
  - [ ] 2.1 Modificar unified_memory_client.py
  - [ ] 2.2 Adicionar try/except ao redor de chamadas ClickHouse
  - [ ] 2.3 Redirecionar para buffer em caso de falha
  - [ ] 2.4 Adicionar métrica de fallback triggered

- [ ] 3. Implementar Drenagem para MongoDB (M)
  - [ ] 3.1 Criar arquivo fallback_drainer.py
  - [ ] 3.2 Implementar task asyncio periódica
  - [ ] 3.3 Implementar batch insert no MongoDB
  - [ ] 3.4 Remover eventos drenados com sucesso

- [ ] 4. Testes Integração (S)
  - [ ] 4.1 Criar arquivo test_fallback_integration.py
  - [ ] 4.2 Teste: ClickHouse down → buffer preenchido
  - [ ] 4.3 Teste: drenagem para MongoDB
  - [ ] 4.4 Teste: recuperação após ClickHouse voltar
  - [ ] 4.5 Verificar todos os testes passando

### Epic GAPS-03: SPECIALIST-002

- [ ] 1. Adicionar Campo decision_method (S)
  - [ ] 1.1 Modificar consolidated_decision.py:32-56
  - [ ] 1.2 Adicionar campo Optional[str] decision_method
  - [ ] 1.3 Adicionar validador Pydantic

- [ ] 2. Enum DecisionMethod (XS)
  - [ ] 2.1 Criar arquivo decision_method.py
  - [ ] 2.2 Implementar enum ML/HEURISTIC/HYBRID
  - [ ] 2.3 Implementar função infer_decision_method()

- [ ] 3. Populamento Automático (S)
  - [ ] 3.1 Modificar _build_specialist_votes no consensus_orchestrator.py
  - [ ] 3.2 Adicionar lógica de detecção de campos ML
  - [ ] 3.3 Popular campo decision_method

- [ ] 4. Testes Unitários (S)
  - [ ] 4.1 Criar arquivo test_decision_method_detection.py
  - [ ] 4.2 Teste: opinião sem campos ML → "heuristic"
  - [ ] 4.3 Teste: opinião com campos ML → "ml"
  - [ ] 4.4 Teste: opinião híbrida → "hybrid"
  - [ ] 4.5 Verificar todos os testes passando

---

## Effort Scale

- XS: 0.5 dia (4 horas)
- S: 1 dia (8 horas)
- M: 2-3 dias
- L: 1 semana
- XL: 2+ semanas

**Estimativa Total:** ~34 story points (~10-12 dias)

---

## Dependencies

- **CONSENSUS-002** depende de: Nenhuma
- **MEMORY-001** depende de: Nenhuma
- **SPECIALIST-002** depende de: Nenhuma

**Epics podem ser executados em paralelo.**
