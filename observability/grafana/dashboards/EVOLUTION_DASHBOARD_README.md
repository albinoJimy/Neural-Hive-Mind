# Evolution Executive Overview Dashboard

**UID:** `evolution-executive-overview`
**Versão:** 1.0
**Fase:** Fase 4 - Aprendizado e Evolução
**Última Atualização:** 2026-04-08

---

## Propósito

Dashboard executivo consolidado para monitorização da evolução do sistema Neural Hive Mind. Foca em hipóteses testadas, taxa de sucesso de experimentos, impacto de mudanças e status dos componentes evolutivos.

---

## Layout do Dashboard

### Row 1: KPIs Executivos
- **Hypotheses Tested:** Total de hipóteses testadas no período
- **Success Rate:** Taxa de sucesso agregada (gauge com thresholds)
- **Total Experiments:** Contador total de experimentos submetidos
- **Active Experiments:** Número de experimentos ativos

### Row 2: Success Rate Over Time
Gráfico temporal da taxa de sucesso de experimentos e hipóteses.

### Row 3: Hypotheses Breakdown
- **Hypotheses by Status:** Pie chart com distribuição (success/failed/pending)
- **Successful Hypotheses:** Contador com cor verde
- **Failed Hypotheses:** Contador com alerta visual

### Row 4: Metrics Over Time
- **Model Performance Metrics:** F1-score, Accuracy, Precision, Recall ao longo do tempo
- **System Latency & Throughput:** p95/p99 latency e throughput do sistema

### Row 5: Impact & Components
- **Top Experiments by Impact:** Tabela dos top 10 experimentos por impacto score
- **Component Status:** Status dos componentes evolutivos (ML Ops, GitOps, etc.)

### Row 6: Recent Alerts & Anomalies
Tabela de alertas recentes com severidade e componente afetado.

### Row 7: Change Impact Analysis
Gráfico temporal de impacto de mudanças em performance.

---

## Variáveis de Template

| Variável | Descrição | Valores |
|----------|-----------|---------|
| `environment` | Filtra por ambiente | All, production, staging, development |
| `time_range` | Range temporal predefinido | 1h, 6h, 24h, 7d, 30d, 90d |
| `experiment_type` | Filtra por tipo de experimento | All, ml, config, algorithm |

---

## Métricas Prometheus Utilizadas

### Métricas Existentes
- `experiments_submitted_total` - Contador de experimentos submetidos
- `ab_test_assignments_total` - Assignments de A/B tests
- `rollback_total` - Contador de rollbacks executados
- `degradation_detected_total` - Degradações detetadas
- `approval_model_f1_score` - F1 score do modelo de aprovação
- `approval_model_accuracy` - Accuracy do modelo
- `http_request_duration_seconds_bucket` - Latency HTTP
- `http_requests_total` - Requests totais

### Métricas a Implementar (Gaps)
- `evolution_hypotheses_total{status}` - Total de hipóteses por status
- `evolution_success_rate{type}` - Taxa de sucesso por tipo
- `evolution_impact_score{experiment_id}` - Impacto score por experimento
- `evolution_component_status{name}` - Status dos componentes
- `evolution_alerts` - Alertas de evolução
- `evolution_performance_impact` - Impacto em performance
- `experiments_active{status}` - Experimentos ativos

---

## Interpretação das Métricas

### Success Rate
- **< 50% (Vermelho):** Sistema evoluindo de forma ineficiente
- **50-80% (Amarelo):** Aceitável, mas requer atenção
- **> 80% (Verde):** Sistema evoluindo de forma saudável

### Impact Score
- **Positivo (> 5%):** Melhoria significativa
- **Negativo (< -5%):** Degradação que pode requerer rollback

### Component Status
- **UP (Verde):** Componente operacional
- **DOWN (Vermelho):** Componente indisponível - ação requerida

---

## SLA de Atualização

| Componente | Frequência | Nota |
|------------|------------|------|
| Dashboard Refresh | 5 minutos | Configurável |
| Dados Prometheus | 15 segundos | Scrape default |
| Métricas de Modelo | 1 hora | Após retrain |
| Status de Componentes | 30 segundos | Health checks |

---

## Links para Dashboards Relacionados

### Fase 4 Dashboards
- Evolution Executive Overview: `evolution-executive-overview` (este dashboard)
- A/B Testing Dashboard: `ab-testing-dashboard`
- Drift Detection Dashboard: `drift-detection-dashboard`
- Meta-Learning Dashboard: `meta-learning-dashboard`
- Active Learning Dashboard: `active-learning-dashboard`
- MLflow Dashboard: `mlflow-dashboard`

### Outros Dashboards
- Queen Agent Strategic: `queen-agent-strategic`
- Worker Agents Execution: `worker-agents-execution`
- Scout Agents: `scout-agents`
- Guard Agents: `guard-agents`

---

## Troubleshooting

### Sem dados a aparecer
1. Verificar datasource Prometheus está configurado
2. Confirmar métricas estão a ser exportadas
3. Verificar variáveis de template (environment)

### Success Rate a 0%
- Normal em arranque inicial
- Verificar se experimentos foram submetidos

### Alertas constantes de degraded
- Analisar Component Status row
- Verificar logs dos componentes down

---

## Tickets Relacionados

- DASH-001-01: Dashboard criado ✅
- DASH-001-02: Painel hipóteses testadas ✅
- DASH-001-03: Painel success rate ✅
- DASH-001-04: Painel métricas over time ✅
- DASH-001-05: Painel impacto mudanças ✅
- DASH-001-06: Painel status componentes ✅
- DASH-001-07: Painel top experimentos ✅
- DASH-001-08: Painel alertas recentes ✅

---

## Melhorias Futuras

- [ ] Integração com datasource MLflow para resultados detalhados
- [ ] Drill-down para dashboards de experimentos específicos
- [ ] Exportação de relatórios em PDF
- [ ] Comparação side-by-side de experimentos
- [ ] Previsões de tendência com ML
