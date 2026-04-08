# Fase 4 Evolution Dashboards

**Data:** 2026-04-08
**Fase:** Fase 4 - Aprendizado e Evolução
**Total de Dashboards:** 6

---

## Visão Geral

Conjunto de dashboards Grafana para monitorização da Fase 4 do Neural Hive Mind, focada em aprendizado, evolução e experimentação. Cada dashboard cobre uma área específica do sistema de ML e experimentação.

---

## Dashboards Disponíveis

### 1. Evolution Executive Overview
**UID:** `evolution-executive-overview`
**Ficheiro:** `evolution-executive-overview.json`
**Propósito:** Visão executiva consolidada do progresso de evolução

**KPIs Principais:**
- Hypotheses Tested
- Success Rate
- Total/Active Experiments
- Model Performance (F1, Accuracy, Precision, Recall)
- Top Experiments by Impact
- Component Status

**Tags:** `evolution`, `executive`, `ml`, `meta-learning`, `fase4`

---

### 2. A/B Testing Dashboard
**UID:** `ab-testing-dashboard`
**Ficheiro:** `ab-testing-dashboard.json`
**Ticket:** AB-01-01
**Propósito:** Monitorização completa de experimentos A/B

**Painéis Principais:**
- **Overview:** Active experiments, total assignments, significant results, early stops, guardrail violations
- **Sample Size:** Distribuição de amostras entre control/treatment
- **Statistical Analysis:** P-values, effect size (Cohen's d)
- **Expected Lift:** Lift esperado do treatment vs control
- **Probability of Superiority:** Probabilidade bayesiana de superioridade
- **Duration:** Duração dos experimentos e análise estatística
- **Guardrails:** Violações e early stops

**Métricas Prometheus:**
- `neural_hive_ab_test_assignments_total{experiment_id, group}`
- `neural_hive_ab_test_sample_size{experiment_id, group}`
- `neural_hive_ab_test_statistical_significance{experiment_id, metric_name}`
- `neural_hive_ab_test_effect_size{experiment_id, metric_name}`
- `neural_hive_ab_test_probability_of_superiority{experiment_id, metric_name}`
- `neural_hive_ab_test_expected_lift{experiment_id, metric_name}`
- `neural_hive_ab_test_guardrail_violations_total{experiment_id, metric_name}`
- `neural_hive_ab_test_early_stops_total{experiment_id, reason}`

**Tags:** `ab-testing`, `fase4`, `evolution`, `experiments`

---

### 3. Drift Detection Dashboard
**UID:** `drift-detection-dashboard`
**Ficheiro:** `drift-detection-dashboard.json`
**Ticket:** DR-01-02
**Propósito:** Detecção e alerta de drift em modelos ML

**Painéis Principais:**
- **Overview:** Consolidated drift status, alertas críticos/medium
- **Feature Drift:** PSI (Population Stability Index) por feature
- **Prediction Drift:** MAE drift ratio (current/baseline)
- **Target Drift:** K-S test p-value e statistic
- **Time Windows:** Comparação 7d vs 30d
- **Methods:** Status de métodos (ADWIN, DDM, PSI)
- **Alerts:** Histórico de alertas por severidade

**Métricas Prometheus:**
- `ml_drift_consolidated_status{model_name}`
- `ml_drift_alerts_total{severity}`
- `ml_drift_psi_score{drift_type, feature_name, model_name}`
- `ml_drift_mae_ratio{model_name}`
- `ml_drift_ks_p_value{model_name, window}`
- `ml_drift_ks_statistic{model_name, window}`
- `ml_drift_score{drift_type, model_name, window}`
- `ml_drift_method_status{method}`
- `ml_drift_alerts_recent`

**Tags:** `drift`, `ml`, `fase4`, `evolution`, `monitoring`

---

### 4. Meta-Learning Dashboard
**UID:** `meta-learning-dashboard`
**Ficheiro:** `meta-learning-dashboard.json`
**Ticket:** ML-01-01
**Propósito:** Monitorização de pesos adaptativos e aprendizado por reforço

**Painéis Principais:**
- **Overview:** Active weights, total adjustments, Q-table size, epsilon (exploration rate)
- **Adaptive Weights:** Pesos dos especialistas ao longo do tempo
- **Weight Distribution:** Distribuição atual de pesos (pie + tabela)
- **Updates Activity:** Taxa de atualizações de pesos
- **RL Metrics:** Average reward, distribuição de recompensas
- **Q-Learning:** Q-value updates, adjustment magnitude
- **Rollbacks & Validations:** Taxa de rollback e validações

**Métricas Prometheus:**
- `optimizer_consensus_active_weights_count`
- `optimizer_specialist_weight{specialist_type}`
- `optimizer_weight_adjustments_total`
- `optimizer_q_table_size`
- `optimizer_epsilon_value`
- `optimizer_consensus_weight_updates_total{specialist_type, status}`
- `optimizer_scheduling_policy_average_reward`
- `optimizer_rl_reward_distribution_bucket`
- `optimizer_rl_q_value_updates_total{action}`
- `optimizer_weight_adjustment_magnitude_bucket`
- `optimizer_consensus_weight_rollbacks_total`
- `optimizer_consensus_weight_validations_total{result}`

**Tags:** `meta-learning`, `rl`, `fase4`, `evolution`, `weights`

---

### 5. Active Learning Dashboard
**UID:** `active-learning-dashboard`
**Ficheiro:** `active-learning-dashboard.json`
**Ticket:** AL-01-01
**Propósito:** Monitorização de coleta de feedback balanceado

**Painéis Principais:**
- **Overview:** Queue size, cases claimed, feedback submitted, dataset balance
- **Class Balance:** Distribuição de classes (approve/reject/review_required/conditional)
- **Confidence Distribution:** Buckets (low/medium/high)
- **Domain Distribution:** Distribuição por domínio
- **Semantic Coverage:** Cobertura de features semânticas
- **Queue Activity:** Taxa de claims, feedbacks, releases
- **Information Value:** Valor informacional médio na fila

**Métricas Prometheus:**
- `active_learning_queue_size`
- `active_learning_cases_claimed_total`
- `active_learning_feedback_submitted_total`
- `active_learning_balance_percentage`
- `active_learning_class_balance{class}`
- `active_learning_confidence_distribution{bucket}`
- `active_learning_domain_distribution{domain}`
- `active_learning_semantic_features_count`
- `active_learning_semantic_features_percentage`
- `active_learning_information_value`
- `active_learning_queue_status{status}`
- `active_learning_priority_cases`

**Tags:** `active-learning`, `ml`, `fase4`, `evolution`, `feedback`

---

### 6. MLflow Dashboard
**UID:** `mlflow-dashboard`
**Ficheiro:** `mlflow-dashboard.json`
**Ticket:** MLF-01-01
**Propósito:** Comparação de versões de modelo e registry

**Painéis Principais:**
- **Overview:** Total model loads, success rate, training runs, training success rate
- **Version Comparison:** MAPE, MAE, RMSE, R² por versão
- **Model Performance:** Métricas de erro e accuracy
- **Loading Performance:** Duração de load, idade dos modelos
- **Training Pipeline:** Duração de treino, taxa de runs
- **Prediction Performance:** Taxa de requests, latência
- **Model Registry:** Tabela de modelos registrados com stage

**Métricas Prometheus:**
- `optimizer_ml_model_loads_total{model_name, status}`
- `optimizer_ml_model_load_success_rate`
- `optimizer_ml_training_runs_total{model_type, status}`
- `optimizer_ml_training_success_rate`
- `optimizer_ml_model_mape{model_name, version}`
- `optimizer_ml_model_mae{model_name, version}`
- `optimizer_ml_model_rmse{model_name, version}`
- `optimizer_ml_model_r2_score{model_name, version}`
- `optimizer_ml_model_age_seconds{model_name}`
- `optimizer_ml_model_load_duration_seconds_bucket`
- `optimizer_ml_training_duration_seconds_bucket{model_type}`
- `optimizer_ml_prediction_duration_seconds_bucket`
- `optimizer_load_predictions_total{horizon, status}`
- `optimizer_ml_model_registry{model_name, version, stage}`

**Tags:** `mlflow`, `ml`, `fase4`, `evolution`, `experiments`

---

## Variáveis de Template Comuns

| Variável | Descrição | Dashboards |
|----------|-----------|------------|
| `model_name` | Filtro de modelo ML | Drift Detection, MLflow |
| `experiment_id` | Filtro de experimento | A/B Testing |
| `specialist_type` | Filtro de especialista | Meta-Learning |
| `domain` | Filtro de domínio | Active Learning |
| `version` | Versão do modelo | MLflow |
| `time_range` | Range temporal | Todos |

---

## Links entre Dashboards

Todos os dashboards incluem um dropdown "Fase 4 Dashboards" para navegação rápida:
```
Evolution Executive Overview
├── A/B Testing Dashboard
├── Drift Detection Dashboard
├── Meta-Learning Dashboard
├── Active Learning Dashboard
└── MLflow Dashboard
```

---

## Métricas a Implementar (Gaps)

### Métricas de Dados Externos
Algumas métricas dependem de fontes de dados externas (MongoDB, MLflow):

**A/B Testing:**
- Dados de resultados de testes no MongoDB
- Resultados de testes estatísticos

**Drift Detection:**
- Alertas de drift no MongoDB (`ml_drift_alerts`)
- Relatórios de drift (`ml_drift_reports`)

**Active Learning:**
- Métricas do balance analyzer
- Dados da fila de prioridade

**MLflow:**
- Integração com MLflow API para metadados de runs

---

## Integração com Serviços

| Serviço | Métricas Exportadas | Dashboards |
|---------|---------------------|------------|
| `optimizer-agents` | Métricas A/B, RL, weights | A/B, Meta-Learning |
| `orchestrator-dynamic` | Métricas de drift | Drift Detection |
| `approval-service` | Métricas active learning | Active Learning |
| `ml-pipelines` | Métricas de treino e registry | MLflow |

---

## Frequência de Atualização

| Dashboard | Refresh Default | Nota |
|-----------|-----------------|------|
| Evolution Executive Overview | 5m | Dados agregados |
| A/B Testing Dashboard | 30s | Experimentos em tempo real |
| Drift Detection Dashboard | 1m | Alertas críticos |
| Meta-Learning Dashboard | 30s | Pesos dinâmicos |
| Active Learning Dashboard | 30s | Fila dinâmica |
| MLflow Dashboard | 1m | Registry estático |

---

## Tickets Relacionados

| Ticket | Descrição | Status |
|--------|-----------|--------|
| AB-01-01 | Dashboard A/B Testing | ✅ |
| DR-01-02 | Dashboard Drift Detection | ✅ |
| ML-01-01 | Dashboard Meta-Learning | ✅ |
| AL-01-01 | Dashboard Active Learning | ✅ |
| MLF-01-01 | Dashboard MLflow | ✅ |

---

## Troubleshooting Comum

### Sem dados no A/B Testing Dashboard
- Verificar se o `optimizer-agents` está a exportar métricas
- Confirmar que existem experimentos ativos

### Alertas constantes de Drift
- Analisar Features Drift PSI scores
- Verificar Prediction Drift Ratio

### Active Learning com queue size = 0
- Normal se o dataset estiver balanceado
- Verificar `ENABLE_ACTIVE_LEARNING=true` no approval-service

### MLflow sem versões de modelo
- Verificar connection string do MLflow
- Confirmar que runs foram registrados

---

## Melhorias Futuras

- [ ] Dashboard de correlação entre experimentos
- [ ] Análise de impacto de longo prazo
- [ ] Exportação de relatórios consolidados
- [ ] Alertas configuráveis por dashboard
- [ ] Integração com sistema de notificações (Slack)
- [ ] Drill-down para detalhes de experimentos individuais
