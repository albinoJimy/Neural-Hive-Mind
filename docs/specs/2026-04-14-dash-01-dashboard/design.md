# Design: Executive Evolution Dashboard

**Data:** 2026-04-14
**Epic:** DASH-01
**Status:** Design Aprovado
**Autor:** Claude (superpowers:brainstorming)

---

## 1. Overview

Criar um dashboard executivo consolidado no Grafana que combina métricas de experimentação, hipóteses e impacto em um único painel, com 4 views especializadas selecionáveis via variável.

---

## 2. Público-Alvo

**Misto:** Executivos, Engenheiros ML/DevOps, Product Managers

Cada view é customizada para seu público:
- **Executive:** Métricas de negócio de alto nível
- **Technical:** Métricas técnicas detalhadas
- **Product:** Métricas de produto e validação
- **Timeline:** Histórico e tendências

---

## 3. Abordagem Escolhida

**Abordagem A:** Dashboard único com variável `$view_type` que controla visibilidade dos painéis.

**Racional:**
- Manutenção simples (um único arquivo)
- Usuário pode alternar views rapidamente
- Reaproveitamento de painéis entre views

---

## 4. Estrutura do Dashboard

### 4.1 Metadados

```json
{
  "title": "Neural Hive Mind - Executive Evolution Dashboard",
  "tags": ["evolution", "executive", "ml", "experiments", "hypotheses"],
  "timezone": "browser",
  "refresh": "30s",
  "time": {
    "from": "now-7d",
    "to": "now"
  }
}
```

### 4.2 Variáveis

| Variável | Tipo | Valores | Descrição |
|----------|------|---------|-----------|
| `$view_type` | custom | Executive, Technical, Product, Timeline | Seleciona view ativa |
| `$specialist_type` | query | label_values(...) | Filtro por tipo de especialista |
| `$priority` | query | P0, P1, P2, P3 | Filtro por prioridade |

---

## 5. Painéis por View

### 5.1 View Executive (7 painéis)

Métricas de alto nível para C-Level.

| ID | Painel | Tipo | Métrica |
|----|--------|------|---------|
| 10 | Evolution Score | Gauge | Score agregado 0-100 |
| 11 | Active Experiments | Stat | `optimizer_experiments_active` |
| 12 | Hypotheses in Pipeline | Stat | `hypothesis_status_current` |
| 13 | Avg Improvement Lift | Gauge | `optimizer_average_improvement_percentage` |
| 14 | Experiment Success Rate | Pie Chart | success/(success+failed) |
| 15 | Hypothesis Outcomes | Bar Chart | `hypothesis_outcome_total` |
| 16 | Evolution Velocity | Trend | features/hipóteses por semana |

### 5.2 View Technical (10 painéis)

Métricas detalhadas para engenheiros.

| ID | Painel | Tipo | Métrica |
|----|--------|------|---------|
| 21 | Active A/B Tests | Stat | `neural_hive_ab_test_assignments_total` |
| 22 | Sample Sizes | Stat | `neural_hive_ab_test_sample_size` |
| 23 | Statistical Significance | Gauge | `neural_hive_ab_test_statistical_significance` |
| 24 | Effect Size | Graph | `neural_hive_ab_test_effect_size` |
| 25 | Experiment Duration | Heatmap | `neural_hive_ab_test_duration_seconds` |
| 26 | Probability of Superiority | Gauge | `neural_hive_ab_test_probability_of_superiority` |
| 27 | Guardrail Violations | Stat | `neural_hive_ab_test_guardrail_violations_total` |
| 28 | Early Stops | Stat | `neural_hive_ab_test_early_stops_total` |
| 29 | Analysis Duration | Graph | `neural_hive_ab_test_analysis_duration_seconds` |

### 5.3 View Product (7 painéis)

Métricas de produto para PMs.

| ID | Painel | Tipo | Métrica |
|----|--------|------|---------|
| 30 | Hypothesis Funnel | Sankey | DRAFT → APPROVED → TESTING → COMPLETED |
| 31 | Hypotheses by Priority | Bar Chart | `hypothesis_by_priority` |
| 32 | Approval Time | Graph | `hypothesis_approval_duration_seconds` |
| 33 | Testing Duration | Graph | `hypothesis_testing_duration_seconds` |
| 34 | Outcome Distribution | Pie Chart | `hypothesis_outcome_total` |
| 35 | Validation Rate | Stat | accepted/tested |
| 36 | Experiment Association | Stat | `hypothesis_experiments_total` |

### 5.4 View Timeline (7 painéis)

Histórico e tendências.

| ID | Painel | Tipo | Métrica |
|----|--------|------|---------|
| 40 | Evolution Timeline | Timeline | Anotações de eventos |
| 41 | Hypothesis Creation Trend | Graph | `rate(hypothesis_created_total[1d])` |
| 42 | Experiment Submission Trend | Graph | `rate(optimizer_experiments_submitted_total[1d])` |
| 43 | Optimization Rollbacks | Graph | `rate(optimizer_optimizations_rolled_back_total[1d])` |
| 44 | Model Deployments | Stat | MLflow versions |
| 45 | RL Epsilon Decay | Graph | `optimizer_epsilon_value` |
| 46 | Q-Table Size | Stat | `optimizer_q_table_size` |

---

## 6. Fontes de Dados

### 6.1 Prometheus

Todas as métricas são consultadas via Prometheus:

**Hypothesis Library:**
- `hypothesis_status_current`
- `hypothesis_created_total`
- `hypothesis_outcome_total`
- `hypothesis_by_priority`
- `hypothesis_approval_duration_seconds`
- `hypothesis_testing_duration_seconds`
- `hypothesis_experiments_total`

**Optimizer Agents:**
- `optimizer_experiments_active`
- `optimizer_experiments_submitted_total`
- `optimizer_experiments_successful_total`
- `optimizer_experiments_failed_total`
- `optimizer_average_improvement_percentage`
- `neural_hive_ab_test_*` (A/B testing metrics)
- `optimizer_optimizations_rolled_back_total`
- `optimizer_epsilon_value`
- `optimizer_q_table_size`

---

## 7. Lógica de Visibilidade

Cada painel utiliza a propriedade `hide` condicional baseada em `$view_type`:

```json
{
  "hide": {
    "value": 0,
    "condition": {
      "query": "$view_type == \"executive\""
    }
  }
}
```

---

## 8. Deploy

### 8.1 Arquivos

- `/monitoring/dashboards/executive-evolution-dashboard.json`
- Atualização de `k8s/observability/grafana-dashboards-configmap.yaml`

### 8.2 Comandos

```bash
# Validar JSON
python -m json.tool monitoring/dashboards/executive-evolution-dashboard.json

# Atualizar ConfigMap
kubectl apply -f k8s/observability/grafana-dashboards-configmap.yaml

# Restart Grafana se necessário
kubectl rollout restart deployment/grafana -n observability
```

---

## 9. Testes

### 9.1 Validação de Schema

```bash
# Verificar estrutura
grep -q '"title"' monitoring/dashboards/executive-evolution-dashboard.json
grep -q '"panels"' monitoring/dashboards/executive-evolution-dashboard.json
grep -q '"templating"' monitoring/dashboards/executive-evolution-dashboard.json

# Validar JSON
python -m json.tool monitoring/dashboards/executive-evolution-dashboard.json > /dev/null
```

### 9.2 Teste Manual

```bash
# Port-forward para Grafana
kubectl port-forward -n observability svc/grafana 3000:3000

# Navegar para
# http://localhost:3000/d/executive-evolution-dashboard
```

**Checklist visual:**
- [ ] Variável `$view_type` aparece e funciona
- [ ] Cada view mostra apenas painéis corretos
- [ ] Todos os painéis carregam dados
- [ ] Alternar entre views funciona
- [ ] Filtros `$specialist_type` e `$priority` funcionam

---

## 10. Critérios de Aceite

- [ ] Dashboard criado em `/monitoring/dashboards/executive-evolution-dashboard.json`
- [ ] Variável `$view_type` implementada com 4 opções
- [ ] View Executive com 7 painéis funcionais
- [ ] View Technical com 10 painéis funcionais
- [ ] View Product com 7 painéis funcionais
- [ ] View Timeline com 7 painéis funcionais
- [ ] Validação JSON sem erros
- [ ] Dashboard carrega corretamente no Grafana
- [ ] Teste manual aprovado

---

## 11. Estimativa

- **Criação do JSON:** 1-2 horas
- **Testes e ajustes:** 1 hora
- **Total:** ~2-3 horas

---

**Design finalizado em:** 2026-04-14
**Próximo passo:** Criar plano de implementação (writing-plans)
