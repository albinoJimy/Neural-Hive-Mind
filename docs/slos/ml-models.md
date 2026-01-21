# SLOs para Modelos ML

Este documento define os Service Level Objectives (SLOs) para os modelos de Machine Learning do Neural Hive Mind.

## Visao Geral

Os modelos ML sao componentes criticos da camada cognitiva do Neural Hive Mind, responsaveis por decisoes de aprovacao e predicoes. Os SLOs definidos garantem qualidade, desempenho e disponibilidade adequados.

## SLOs Definidos

### 1. F1 Score (Qualidade do Modelo)

| Atributo | Valor |
|----------|-------|
| **Metrica** | `neural_hive_mlflow_model_f1` |
| **Target** | >= 0.75 (75%) |
| **Janela** | 7 dias (rolling) |
| **Recording Rule** | `neural_hive:slo:ml_f1_score:7d` |

**Justificativa:** O F1 Score equilibra precision e recall, sendo critico para decisoes de aprovacao/rejeicao. Um threshold de 75% garante que o modelo tenha performance aceitavel em ambas as metricas.

**Acoes em caso de violacao:**
1. Verificar qualidade dos dados de treinamento
2. Analisar drift de distribuicao de dados
3. Considerar retreinamento do modelo
4. Ativar fallback para heuristicas se critico (< 70%)

### 2. Latencia P95 (Desempenho)

| Atributo | Valor |
|----------|-------|
| **Metrica** | `neural_hive_specialist_evaluation_duration_seconds` |
| **Target** | < 100ms (P95) |
| **Janela** | 24 horas (5m windows) |
| **Recording Rule** | `neural_hive:slo:ml_latency_p95_total:5m` |

**Justificativa:** Latencia baixa e essencial para experiencia do usuario no fluxo de aprovacao. 100ms P95 garante responsividade adequada sem impactar negativamente o UX.

**Acoes em caso de violacao:**
1. Verificar carga do sistema e recursos (CPU/GPU)
2. Analisar complexidade do modelo
3. Escalar horizontalmente se necessario
4. Ativar rate limiting em casos criticos (> 200ms)

### 3. Taxa de Coleta de Feedback (Melhoria Continua)

| Atributo | Valor |
|----------|-------|
| **Metrica** | `neural_hive_feedback_submissions_total` / `neural_hive_specialist_evaluations_total` |
| **Target** | >= 10% |
| **Janela** | 7 dias |
| **Recording Rule** | `neural_hive:slo:ml_feedback_rate:7d` |

**Justificativa:** Feedback minimo necessario para retreinamento efetivo. Com menos de 10% de feedback, a qualidade do retreinamento e comprometida (threshold minimo: ~100 feedbacks por ciclo).

**Acoes em caso de violacao:**
1. Verificar UI de coleta de feedback
2. Incentivar usuarios a fornecer feedback
3. Revisar UX do fluxo de feedback
4. Alertar equipe de produto se critico (< 5%)

### 4. Disponibilidade do Modelo (Uptime)

| Atributo | Valor |
|----------|-------|
| **Metrica** | Taxa de sucesso de `neural_hive_specialist_evaluations_total` |
| **Target** | >= 99.5% |
| **Janela** | 30 dias |
| **Recording Rule** | `neural_hive:slo:ml_availability:30d` |

**Justificativa:** Alta disponibilidade garante que o sistema nao dependa excessivamente de fallbacks heuristicos. 99.5% permite ~3.6h de downtime por mes.

**Acoes em caso de violacao:**
1. Verificar logs de erro dos servicos ML
2. Analisar padrao de falhas
3. Revisar health checks
4. Considerar rollback se critico (< 99%)

## Error Budgets

Cada SLO tem um error budget associado calculado como:

```
Error Budget Remaining = ((current - target) / (1 - target)) * 100
```

Recording rules para error budgets:
- `neural_hive:slo:ml_error_budget_remaining:f1_score`
- `neural_hive:slo:ml_error_budget_remaining:latency`
- `neural_hive:slo:ml_error_budget_remaining:feedback_rate`
- `neural_hive:slo:ml_error_budget_remaining:availability`

### Burn Rate Alerting

Alertas de burn rate sao configurados para deteccao precoce:

| Tipo | Janela | Threshold | Severidade |
|------|--------|-----------|------------|
| Fast Burn | 1h + 6h | Alto | Critical |
| Slow Burn | 6h + 24h | Moderado | Warning |

## Processo de Revisao

### Frequencia

| SLO | Frequencia de Revisao |
|-----|----------------------|
| F1 Score | Semanal |
| Latencia P95 | Diaria |
| Feedback Rate | Semanal |
| Uptime | Mensal |

### Responsabilidades

- **ML Platform Team:** Monitoramento e manutencao dos modelos
- **SRE Team:** Infraestrutura e disponibilidade
- **Product Team:** Taxa de feedback e UX

### Criterios para Ajuste de SLOs

1. **Historico:** Avaliar 3+ meses de dados
2. **Impacto no Negocio:** Considerar custo vs beneficio
3. **Capacidade Tecnica:** Verificar viabilidade
4. **Stakeholder Agreement:** Aprovacao das partes interessadas

## Arquivos Relacionados

| Arquivo | Descricao |
|---------|-----------|
| `monitoring/slos/ml-model-slos.yaml` | Definicoes SLO (CRD) |
| `monitoring/slos/ml-slo-recording-rules.yaml` | Recording rules Prometheus |
| `monitoring/dashboards/ml-slos-dashboard.json` | Dashboard Grafana |
| `prometheus-rules/ml-slo-alerts.yaml` | Alertas de violacao |

## Dashboard

O dashboard "Neural Hive-Mind ML Model SLOs" (`ml-slos-dashboard`) fornece visualizacao de:

1. **Compliance Gauges:** Status atual de cada SLO
2. **Error Budget Status:** Budget restante por SLO
3. **Burn Rate Charts:** Taxa de consumo de budget
4. **Compliance History:** Historico de conformidade

Acesso: `https://grafana.neural-hive.local/d/ml-slos-dashboard/ml-slos`

## Referencias

- [Google SRE Book - SLOs](https://sre.google/sre-book/service-level-objectives/)
- [Prometheus Recording Rules](https://prometheus.io/docs/prometheus/latest/configuration/recording_rules/)
- [Neural Hive Mind - Observability Architecture](../architecture/observability.md)
