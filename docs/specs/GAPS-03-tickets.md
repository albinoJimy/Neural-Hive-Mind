# Tickets: GAPS-03 - Consenso Hierárquico

**Epic:** GAPS-03 - Consenso Hierárquico
**Estimativa Total:** M (1 semana)
**Data Criação:** 2026-03-17

---

## Ticket 1: GAPS-03-01 - Modelo de Senioridade

**Tipo:** Feature
**Prioridade:** Alta
**Estimativa:** XS (1 dia)
**Dependências:** Nenhuma

### Descrição
Criar modelo de dados para níveis de senioridade de especialistas.

### Escopo
- Criar `src/models/seniority.py` com:
  - Enum `SeniorityLevel` (trainee, junior, mid_level, senior, expert)
  - Dicionário `SENIORITY_MULTIPLIERS`
  - Função `get_seniority_multiplier()`
- Adicionar type hints e docstrings completas
- Incluir testes unitários básicos

### Critérios de Aceite
- [ ] Enum `SeniorityLevel` criado com 5 níveis
- [ ] Multiplicadores: trainee=0.5, junior=0.75, mid_level=1.0, senior=1.5, expert=2.0
- [ ] Função `get_seniority_multiplier()` retorna valor correto
- [ ] Testes unitários passam

### Arquivos
- ✏️ `services/consensus-engine/src/models/seniority.py` (NOVO)
- ✏️ `services/consensus-engine/tests/test_seniority.py` (NOVO)

---

## Ticket 2: GAPS-03-02 - Calculadora de Pesos Hierárquicos

**Tipo:** Feature
**Prioridade:** Alta
**Estimativa:** S (2-3 dias)
**Dependências:** GAPS-03-01

### Descrição
Implementar serviço que calcula pesos hierárquicos combinando feromônios, senioridade e domínio.

### Escopo
- Criar `src/services/hierarchical_weights.py` com:
  - Classe `HierarchicalWeightCalculator`
  - Método `calculate_hierarchical_weight()`
  - Método `calculate_batch_weights()` para múltiplos especialistas
  - Normalização de pesos para [0, 1]
- Integração com `PheromoneClient` existente
- Logging estruturado (structlog)

### Critérios de Aceite
- [ ] Classe `HierarchicalWeightCalculator` criada
- [ ] `calculate_hierarchical_weight()` aplica fórmula: `weight_pheromone × multiplier_seniority × weight_domain`
- [ ] Pesos normalizados para máximo 1.0
- [ ] Suporte para cálculo em lote (batch)
- [ ] Testes unitários para todos os níveis de senioridade
- [ ] Testes de normalização de pesos

### Arquivos
- ✏️ `services/consensus-engine/src/services/hierarchical_weights.py` (NOVO)
- ✏️ `services/consensus-engine/tests/test_hierarchical_weights.py` (NOVO)

---

## Ticket 3: GAPS-03-03 - Configurações de Senioridade

**Tipo:** Feature
**Prioridade:** Alta
**Estimativa:** XS (1 dia)
**Dependências:** Nenhuma

### Descrição
Adicionar configurações de senioridade ao `Settings` do Consensus Engine.

### Escopo
- Modificar `src/config/settings.py`:
  - Adicionar `enable_hierarchical_consensus: bool` (default=True)
  - Adicionar `specialist_seniority: Dict[str, str]` com defaults
  - Adicionar `default_seniority_level: str`
  - Adicionar `domain_specialist_weights: Dict[str, float]`
- Validações Pydantic para valores válidos
- Documentação inline

### Critérios de Aceite
- [ ] `enable_hierarchical_consensus` configurável
- [ ] 5 especialistas com senioridade padrão configurada
- [ ] Validação rejeita seniorities inválidas
- [ ] Feature flag permite desabilitar funcionalidade
- [ ] Testes de validação de configuração

### Arquivos
- ✏️ `services/consensus-engine/src/config/settings.py` (ALTERAR)
- ✏️ `services/consensus-engine/tests/test_settings_hierarchical.py` (NOVO)

---

## Ticket 4: GAPS-03-04 - Atualizar Modelos de Decisão

**Tipo:** Feature
**Prioridade:** Alta
**Estimativa:** XS (1 dia)
**Dependências:** GAPS-03-01

### Descrição
Estender `SpecialistVote` e `ConsensusMetrics` com campos de senioridade.

### Escopo
- Modificar `src/models/consolidated_decision.py`:
  - Adicionar `seniority_level: Optional[str]` em `SpecialistVote`
  - Adicionar `seniority_multiplier: Optional[float]` em `SpecialistVote`
  - Adicionar `consensus_method_hierarchical: bool` em `ConsensusMetrics`
  - Adicionar `seniority_distribution: Dict[str, int]` em `ConsensusMetrics`
  - Adicionar `weighted_by_seniority: bool` em `ConsensusMetrics`
- Atualizar método `to_avro_dict()` se necessário
- Manter backward compatibility

### Critérios de Aceite
- [ ] `SpecialistVote` tem `seniority_level`
- [ ] `SpecialistVote` tem `seniority_multiplier`
- [ ] `ConsensusMetrics` tem campos de distribuição
- [ ] `to_avro_dict()` inclui novos campos
- [ ] Backward compatibility mantida (campos opcionais)

### Arquivos
- ✏️ `services/consensus-engine/src/models/consolidated_decision.py` (ALTERAR)
- ✏️ `services/consensus-engine/tests/test_consolidated_decision_hierarchical.py` (NOVO)

---

## Ticket 5: GAPS-03-05 - Integrar Consensus Orchestrator

**Tipo:** Feature
**Prioridade:** Alta
**Estimativa:** M (1 semana)
**Dependências:** GAPS-03-02, GAPS-03-03, GAPS-03-04

### Descrição
Integrar cálculo de pesos hierárquicos no `ConsensusOrchestrator`.

### Escopo
- Modificar `src/services/consensus_orchestrator.py`:
  - Importar `HierarchicalWeightCalculator`
  - Inicializar `self.hierarchical` no `__init__`
  - Modificar `_calculate_dynamic_weights()` para usar pesos hierárquicos
  - Modificar `_build_specialist_votes()` para incluir senioridade
  - Modificar `process_consensus()` para popular `seniority_distribution`
  - Adicionar métricas Prometheus para senioridade
- Respeitar feature flag `enable_hierarchical_consensus`

### Critérios de Aceite
- [ ] `ConsensusOrchestrator` usa `HierarchicalWeightCalculator`
- [ ] `_calculate_dynamic_weights()` aplica multiplicador de senioridade
- [ ] `SpecialistVote` popula `seniority_level` e `seniority_multiplier`
- [ ] `ConsensusMetrics` popula `seniority_distribution`
- [ ] Feature flag permite desabilitar (volta ao comportamento anterior)
- [ ] Métricas Prometheus registram pesos por senioridade
- [ ] Logging inclui informações de senioridade

### Arquivos
- ✏️ `services/consensus-engine/src/services/consensus_orchestrator.py` (ALTERAR)
- ✏️ `services/consensus-engine/src/observability/metrics.py` (ALTERAR)

---

## Ticket 6: GAPS-03-06 - Testes de Integração

**Tipo:** Test
**Prioridade:** Alta
**Estimativa:** S (2-3 dias)
**Dependências:** GAPS-03-05

### Descrição
Criar testes E2E para validação do consenso hierárquico.

### Escopo
- Criar `tests/test_consensus_hierarchical.py`:
  - Teste de consenso com especialistas de níveis mistos
  - Teste que opinião senior tem mais peso que junior
  - Teste de unanimidade com senioridade diferente
  - Teste de feature flag desabilitado
  - Teste de fallback para senioridade padrão
- Mock de especialistas com senioridade variada
- Validação de métricas

### Critérios de Aceite
- [ ] 5+ cenários de teste cobrem fluxos principais
- [ ] Teste valida peso de senior > 2× peso de junior
- [ ] Teste valida feature flag
- [ ] Todos os testes passam
- [ ] Cobertura ≥ 80% do código novo

### Arquivos
- ✏️ `services/consensus-engine/tests/test_consensus_hierarchical.py` (NOVO)
- ✏️ `services/consensus-engine/tests/fixtures/hierarchical_opinions.py` (NOVO)

---

## Ticket 7: GAPS-03-07 - Documentação e Deploy

**Tipo:** Documentation
**Prioridade:** Média
**Estimativa:** XS (1 dia)
**Dependências:** GAPS-03-06

### Descrição
Documentar funcionalidade e preparar deploy.

### Escopo
- Atualizar `README.md` do consensus-engine
- Atualizar `docs/feature-map.md` (Consensus 90% → 100%)
- Criar exemplos de uso em `docs/examples/`
- Preparar vars de ambiente para staging
- Checklist de deploy

### Critérios de Aceite
- [ ] README documenta consenso hierárquico
- [ ] Exemplos de configuração fornecidos
- [ ] feature-map.md atualizado
- [ ] Vars de ambiente documentadas
- [ ] Checklist de deploy completo

### Arquivos
- ✏️ `services/consensus-engine/README.md` (ATUALIZAR)
- ✏️ `docs/feature-map.md` (ATUALIZAR)
- ✏️ `docs/examples/hierarchical_consensus.md` (NOVO)
- ✏️ `services/consensus-engine/.env.staging.example` (ATUALIZAR)

---

## Matriz de Dependências

```
GAPS-03-01 (Senioridade Model)
    ↓
GAPS-03-02 (Calculadora) ← GAPS-03-03 (Config) ← GAPS-03-04 (Modelos)
    ↓                              ↓                ↓
GAPS-03-05 (Orchestrator Integration) ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ←
    ↓
GAPS-03-06 (Testes Integração)
    ↓
GAPS-03-07 (Docs + Deploy)
```

---

## Ordem de Execução Sugerida

1. **GAPS-03-01** → Modelo de Senioridade (fundação)
2. **GAPS-03-03** → Configurações (pode ser paralelo)
3. **GAPS-03-02** → Calculadora (depende de 01)
4. **GAPS-03-04** → Modelos (depende de 01)
5. **GAPS-03-05** → Integração (depende de 02, 03, 04)
6. **GAPS-03-06** → Testes (depende de 05)
7. **GAPS-03-07** → Docs/Deploy (depende de 06)

---

**Total:** 7 tickets
**Esforço Total:** ~7 dias úteis
**Bloqueio Crítico:** Caminho feliz (GAPS-03-01 → 02 → 05) é o mais curto para MVP
