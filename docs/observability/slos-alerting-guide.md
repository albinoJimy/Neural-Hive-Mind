# SLOs e Alertas Neural Hive-Mind

## Visão Geral

Este documento define os Service Level Objectives (SLOs), estratégias de alertas e error budgets para o Neural Hive-Mind, garantindo disponibilidade e performance adequadas para experiência do usuário e contratos comerciais.

## SLOs Principais

### 1. SLO Crítico: Latência do Barramento <150ms P95

**Definição**: 95% das operações no barramento neural devem completar em menos de 150ms.

**Métrica Base**:
```promql
histogram_quantile(0.95,
  sum(rate(neural_hive_barramento_duration_seconds_bucket[5m])) by (le)
) * 1000
```

**Justificativa**: Latência do barramento impacta diretamente a experiência do usuário e é crítica para SLAs comerciais.

**Error Budget**: 0.1% (36 segundos por hora acima de 150ms)

### 2. SLO Crítico: Disponibilidade ≥99.9%

**Definição**: Sistema deve estar disponível para 99.9% das requisições.

**Métrica Base**:
```promql
(
  sum(rate(neural_hive_requests_total{status!~"error|failed|5.*"}[5m])) /
  sum(rate(neural_hive_requests_total[5m]))
) * 100
```

**Error Budget**: 0.1% (43.2 minutos de indisponibilidade por mês)

### 3. SLOs por Fluxo Operacional

#### Fluxo A - Captura de Intenções
- **Latência**: <200ms P95
- **Taxa de Sucesso**: >99.5%
- **Métrica**:
```promql
histogram_quantile(0.95,
  sum(rate(neural_hive_captura_duration_seconds_bucket{neural_hive_component="gateway"}[5m])) by (le)
)
```

#### Fluxo B - Geração de Planos
- **Latência**: <120ms P95
- **Taxa de Aprovação**: >97%
- **Divergência de Custo**: <8%
- **Métricas**:
```promql
# Latência
histogram_quantile(0.95,
  sum(rate(neural_hive_plan_generation_duration_seconds_bucket[5m])) by (le)
)

# Taxa de aprovação
rate(neural_hive_plan_generation_success_total[5m]) /
rate(neural_hive_plan_generation_total[5m])

# Divergência de custo
sum(rate(neural_hive_plan_cost_divergence_total[5m])) /
sum(rate(neural_hive_plan_generation_total[5m]))
```

#### Fluxo C - Orquestração
- **Cumprimento de SLA**: >99% P99
- **Métrica**:
```promql
histogram_quantile(0.99,
  sum(rate(neural_hive_sla_compliance_bucket[5m])) by (le)
)
```

#### Fluxo D - Observabilidade
- **Cobertura de Telemetria**: >99.7%
- **Métrica**:
```promql
(
  count(up{neural_hive_component!="",neural_hive_component!~"test.*|mock.*"} == 1) /
  count(up{neural_hive_component!="",neural_hive_component!~"test.*|mock.*"})
) * 100
```

#### Fluxo E - Autocura
- **MTTD (Mean Time To Detection)**: <15s P95
- **MTTR (Mean Time To Recovery)**: <90s P95
- **Taxa de Automação**: >85%
- **Taxa de Reincidência**: <1% semanal
- **Métricas**:
```promql
# MTTD
quantile(0.95,
  avg_over_time(neural_hive_detection_time_seconds{neural_hive_component="self-healing"}[5m])
)

# MTTR
quantile(0.95,
  avg_over_time(neural_hive_recovery_time_seconds{neural_hive_component="self-healing",status="success"}[10m])
)

# Taxa de automação
(
  sum(rate(neural_hive_automated_actions_total{neural_hive_component="self-healing"}[5m])) /
  sum(rate(neural_hive_total_actions_total{neural_hive_component="self-healing"}[5m]))
) * 100

# Taxa de reincidência
(
  sum(rate(neural_hive_incident_recurrence_total{neural_hive_component="self-healing",recurrence_type!="false_positive"}[7d])) /
  sum(rate(neural_hive_incidents_total{neural_hive_component="self-healing"}[7d]))
) * 100
```

## Error Budgets

### Definição de Error Budget
Error Budget = (1 - SLO) × Total Volume

### Estratégias de Burn Rate

#### Fast Burn (1 hora)
- **Threshold**: 14.4x taxa normal
- **Ação**: Alerta crítico imediato
- **Estimativa**: Error budget esgotado em ~2.5 horas

```promql
(
  (
    sum(rate(neural_hive_request_errors_total{neural_hive_component!=""}[1h])) /
    sum(rate(neural_hive_requests_total{neural_hive_component!=""}[1h]))
  ) - (
    sum(rate(neural_hive_request_errors_total{neural_hive_component!=""}[30d])) /
    sum(rate(neural_hive_requests_total{neural_hive_component!=""}[30d]))
  )
) * (24 * 30) > 14.4 * (
  sum(rate(neural_hive_request_errors_total{neural_hive_component!=""}[30d])) /
  sum(rate(neural_hive_requests_total{neural_hive_component!=""}[30d]))
)
```

#### Slow Burn (6 horas)
- **Threshold**: 6x taxa normal
- **Ação**: Alerta de warning
- **Estimativa**: Error budget esgotado em ~5 dias

```promql
(
  (
    sum(rate(neural_hive_request_errors_total{neural_hive_component!=""}[6h])) /
    sum(rate(neural_hive_requests_total{neural_hive_component!=""}[6h]))
  ) - (
    sum(rate(neural_hive_request_errors_total{neural_hive_component!=""}[30d])) /
    sum(rate(neural_hive_requests_total{neural_hive_component!=""}[30d]))
  )
) * (4 * 30) > 6 * (
  sum(rate(neural_hive_request_errors_total{neural_hive_component!=""}[30d])) /
  sum(rate(neural_hive_requests_total{neural_hive_component!=""}[30d]))
)
```

## Alertmanager - Routing e Configuração

### Hierarquia de Routing

```yaml
route:
  group_by: ['neural_hive_component', 'neural_hive_layer', 'alertname', 'cluster']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 12h
  receiver: 'neural-hive-default'
  routes:

  # 1. Alertas críticos - notificação imediata
  - match:
      severity: critical
    receiver: 'neural-hive-critical'
    group_wait: 0s
    repeat_interval: 5m
    continue: true

  # 2. Alertas de SLO - equipe SRE
  - match_re:
      slo: ".*"
    receiver: 'neural-hive-slo'
    group_wait: 30s
    repeat_interval: 30m
    continue: true

  # 3. Routing por camada arquitetural
  - match:
      neural_hive_layer: experiencia
    receiver: 'neural-hive-experiencia'
  - match:
      neural_hive_layer: cognicao
    receiver: 'neural-hive-cognicao'
  - match:
      neural_hive_layer: orquestracao
    receiver: 'neural-hive-orquestracao'
  - match:
      neural_hive_layer: execucao
    receiver: 'neural-hive-execucao'
  - match:
      neural_hive_layer: resiliencia
    receiver: 'neural-hive-resiliencia'
  - match:
      neural_hive_layer: observabilidade
    receiver: 'neural-hive-observabilidade'

  # 4. Alertas de segurança
  - match_re:
      alertname: ".*Security.*|.*Auth.*|.*Certificate.*"
    receiver: 'neural-hive-security'
    group_wait: 0s
    repeat_interval: 15m
```

### Receivers por Severidade

#### Critical Alerts
```yaml
- name: 'neural-hive-critical'
  slack_configs:
  - channel: '#neural-hive-critical'
    color: 'danger'
    title: '🚨 CRÍTICO - Neural Hive-Mind'
    text: |
      *⚠️ ALERTA CRÍTICO DETECTADO ⚠️*

      *Alerta:* {{ .GroupLabels.alertname }}
      *Ambiente:* {{ .CommonLabels.environment }}
      *Componente:* {{ .GroupLabels.neural_hive_component }}
      *Camada:* {{ .GroupLabels.neural_hive_layer }}

      {{ range .Alerts }}
      *Descrição:* {{ .Annotations.description }}
      *Valor Atual:* {{ .Annotations.current_value | default "N/A" }}
      *Threshold:* {{ .Annotations.threshold | default "N/A" }}
      {{ if .Annotations.runbook_url }}*Runbook:* {{ .Annotations.runbook_url }}{{ end }}
      {{ end }}
    actions:
    - type: button
      text: '📊 Ver Grafana'
      url: 'https://grafana.neural-hive.local'
    - type: button
      text: '📖 Ver Runbook'
      url: '{{ .CommonAnnotations.runbook_url }}'
```

#### SLO Violations
```yaml
- name: 'neural-hive-slo'
  slack_configs:
  - channel: '#neural-hive-slo'
    color: 'warning'
    title: '📊 Violação de SLO - Neural Hive-Mind'
    text: |
      *SLO Violado:* {{ .GroupLabels.slo }}
      *Ambiente:* {{ .CommonLabels.environment }}

      {{ range .Alerts }}
      *Métrica:* {{ .Annotations.summary }}
      *Valor Atual:* {{ .Annotations.current_value }}
      *SLO Target:* {{ .Annotations.slo_target }}
      *Error Budget Burn Rate:* {{ .Annotations.burn_rate | default "N/A" }}

      *Impact Assessment:*
      • Componente: {{ .Labels.neural_hive_component }}
      • Camada: {{ .Labels.neural_hive_layer }}
      {{ end }}
    actions:
    - type: button
      text: '📊 SLO Dashboard'
      url: 'https://grafana.neural-hive.local/d/slos-eb/slos-error-budgets'
```

### Inhibit Rules

```yaml
inhibit_rules:
# Crítico inibe warning para o mesmo componente
- source_match:
    severity: 'critical'
  target_match:
    severity: 'warning'
  equal: ['neural_hive_component', 'alertname', 'instance']

# Node down inibe todos os alertas do node
- source_match:
    alertname: 'KubernetesNodeNotReady'
  target_match_re:
    alertname: '.*'
  equal: ['instance']

# SLO violation inibe métricas individuais
- source_match_re:
    slo: '.*'
  target_match_re:
    alertname: 'Neural.*High.*|Neural.*Low.*'
  equal: ['neural_hive_component']
```

## Runbooks de Incidentes

### Runbook: Violação de SLO de Latência do Barramento

**URL**: `https://docs.neural-hive.local/runbooks/bus-latency-slo`

#### Sintomas
- Alertmanager: `NeuralHiveBusLatencyHigh`
- Latência P95 > 150ms por mais de 2 minutos
- Usuários reportam lentidão no sistema

#### Investigação Inicial
1. **Verificar Dashboard Principal**
   ```
   https://grafana.neural-hive.local/d/neural-hive-overview/neural-hive-overview
   ```

2. **Query para Análise de Latência**
   ```promql
   # Latência por componente
   histogram_quantile(0.95,
     sum(rate(neural_hive_barramento_duration_seconds_bucket[5m]))
     by (le, neural_hive_component)
   ) * 1000

   # Top componentes com maior latência
   topk(5,
     histogram_quantile(0.95,
       sum(rate(neural_hive_barramento_duration_seconds_bucket[5m]))
       by (le, neural_hive_component)
     )
   ) * 1000
   ```

3. **Verificar Dependências Externas**
   ```promql
   # Latência de chamadas externas
   histogram_quantile(0.95,
     sum(rate(neural_hive_external_duration_seconds_bucket[5m]))
     by (le, service)
   )
   ```

#### Ações de Mitigação

**Imediato (0-5 minutos)**:
1. Verificar se há deploy recente
2. Checar resource utilization dos pods
3. Verificar se Istio está funcionando corretamente

**Curto prazo (5-15 minutos)**:
1. Scale horizontal se CPU/Memory alto
2. Restart de componentes com alta latência
3. Bypass de componentes não-críticos se possível

**Escalação**:
- Se latência > 300ms por > 10 minutos: Escalar para Engineering Lead
- Se impacto em clientes premium: Escalar para Customer Success

#### Queries de Diagnóstico
```promql
# Resource utilization
rate(container_cpu_usage_seconds_total{pod=~"neural-hive.*"}[5m]) * 100

# Memory pressure
container_memory_usage_bytes{pod=~"neural-hive.*"} /
container_spec_memory_limit_bytes{pod=~"neural-hive.*"} * 100

# Request rate
sum(rate(neural_hive_requests_total[5m])) by (neural_hive_component)

# Error rate by component
sum(rate(neural_hive_requests_total{status=~"error|5.*"}[5m])) by (neural_hive_component) /
sum(rate(neural_hive_requests_total[5m])) by (neural_hive_component) * 100
```

### Runbook: Error Budget Fast Burn

**URL**: `https://docs.neural-hive.local/runbooks/error-budget-burn`

#### Sintomas
- Alertmanager: `ErrorBudgetFastBurn`
- Taxa de erro 14.4x acima do normal
- Error budget será esgotado em ~2.5 horas

#### Investigação
1. **Identificar Componentes com Maior Error Rate**
   ```promql
   topk(10,
     sum(rate(neural_hive_request_errors_total[1h])) by (neural_hive_component) /
     sum(rate(neural_hive_requests_total[1h])) by (neural_hive_component)
   ) * 100
   ```

2. **Análise de Trend**
   ```promql
   # Error rate nas últimas 2 horas vs baseline
   (
     sum(rate(neural_hive_request_errors_total[2h])) /
     sum(rate(neural_hive_requests_total[2h]))
   ) - (
     sum(rate(neural_hive_request_errors_total[7d])) /
     sum(rate(neural_hive_requests_total[7d]))
   )
   ```

#### Ações de Emergência
1. **Proteção de Error Budget**
   - Implementar circuit breakers
   - Reduzir timeout de operações não-críticas
   - Ativar mode degradado se disponível

2. **Identificação de Root Cause**
   - Correlacionar com traces de alta latência
   - Verificar logs estruturados por erro type
   - Analisar mudanças recentes no sistema

### Runbook: Disponibilidade Baixa

**URL**: `https://docs.neural-hive.local/runbooks/availability-slo-critical`

#### Sintomas
- Alertmanager: `NeuralHiveAvailabilitySLOBreach`
- Disponibilidade < 99.9%
- Usuários não conseguem usar o sistema

#### Ações Críticas (War Room)
1. **Status Imediato**
   ```bash
   kubectl get pods -n neural-hive | grep -v Running
   kubectl get svc -n neural-hive
   kubectl get ingress -n neural-hive
   ```

2. **Health Checks Manuais**
   ```bash
   # Gateway health
   curl -f https://api.neural-hive.local/health

   # Internal services health
   kubectl port-forward -n neural-hive svc/neural-hive-gateway 8080:80 &
   curl -f http://localhost:8080/health
   ```

3. **Traffic Split Investigation**
   ```promql
   # Request distribution
   sum(rate(neural_hive_requests_total[5m])) by (neural_hive_component, status)

   # Success rate by component
   sum(rate(neural_hive_requests_total{status!~"error|5.*"}[5m])) /
   sum(rate(neural_hive_requests_total[5m]))
   ```

## Dashboards de SLO

### Neural Hive SLOs Overview
**URL**: `https://grafana.neural-hive.local/d/slos-eb/slos-error-budgets`

#### Painéis Principais
1. **SLO Status Board** - Status atual de todos os SLOs
2. **Error Budget Burn Rate** - Velocidade de consumo do error budget
3. **SLO Trends** - Histórico de 30 dias dos SLOs
4. **Alerts Summary** - Alertas ativos por severidade

#### Queries dos Painéis
```promql
# SLO Compliance Rate (single stat)
(
  sum(rate(neural_hive_requests_total{status!~"error|failed|5.*"}[30d])) /
  sum(rate(neural_hive_requests_total[30d]))
) * 100

# Error Budget Remaining (gauge)
100 - (
  sum(rate(neural_hive_request_errors_total[30d])) /
  sum(rate(neural_hive_requests_total[30d])) / 0.001 * 100
)

# Latency SLO Compliance (graph)
(
  histogram_quantile(0.95,
    sum(rate(neural_hive_barramento_duration_seconds_bucket[5m])) by (le)
  ) * 1000 < 150
) * 100
```

### Per-Component SLO Dashboard
**URL**: `https://grafana.neural-hive.local/d/component-slos/component-slos`

Template variables:
- `$component`: neural_hive_component label values
- `$layer`: neural_hive_layer label values
- `$environment`: environment label values

## Configuração de Alertas Preditivos

### Machine Learning para Anomaly Detection
```promql
# Trend detection para latência
predict_linear(
  neural_hive_barramento_duration_seconds_bucket{le="0.15"}[30m],
  3600
) > 0.8

# Seasonal anomaly detection
(
  avg_over_time(neural_hive_requests_total[1h]) -
  avg_over_time(neural_hive_requests_total[1h] offset 7d)
) / avg_over_time(neural_hive_requests_total[1h] offset 7d) > 0.5
```

### Capacity Planning Alerts
```promql
# CPU trend indicating need for scaling
predict_linear(
  avg(rate(container_cpu_usage_seconds_total{pod=~"neural-hive.*"}[5m]))[30m:5m],
  3600
) > 0.8

# Memory trend
predict_linear(
  avg(container_memory_usage_bytes{pod=~"neural-hive.*"})[30m:5m],
  3600
) / avg(container_spec_memory_limit_bytes{pod=~"neural-hive.*"}) > 0.9
```

## Processo de Revisão de SLOs

### Reunião Mensal de SLO Review
**Agenda**:
1. **Performance vs SLOs** - Métricas do mês anterior
2. **Error Budget Analysis** - Consumo e principais causas
3. **Alert Fatigue Review** - Alertas frequentes e precisão
4. **SLO Adjustments** - Propostas de mudança baseadas em dados

### Métricas de Qualidade dos SLOs
```promql
# Alert precision (% de alertas que foram verdadeiros positivos)
sum(increase(alertmanager_notifications_total{state="firing"}[30d])) /
sum(increase(alertmanager_alerts_received_total[30d])) * 100

# MTTB (Mean Time to Burn) - tempo médio para esgotar error budget
avg(
  increase(neural_hive_error_budget_consumed[30d]) /
  increase(neural_hive_error_budget_total[30d])
) * 30 * 24 * 3600  # em segundos

# SLO reliability (% do tempo que SLO foi atendido)
avg_over_time(
  (neural_hive_slo_compliance > 0)[30d:1h]
) * 100
```

### Criteria para Ajuste de SLOs

**Relaxar SLO** (tornar menos restritivo):
- SLO atendido > 99.9% do tempo por 3 meses consecutivos
- Error budget não consumido > 90% por 3 meses
- Alertas com <80% de precision

**Apertar SLO** (tornar mais restritivo):
- Reclamações de usuários sobre performance
- Contratos comerciais exigem melhor SLA
- Capacidade técnica comprovada por 2+ meses

**Exemplo de Proposta de Mudança**:
```yaml
slo_change_proposal:
  slo_name: "neural_hive_bus_latency"
  current_threshold: 150  # ms
  proposed_threshold: 120  # ms
  justification: |
    - Latência média nos últimos 3 meses: 85ms (43% abaixo do SLO)
    - Error budget utilizado: <20% mensalmente
    - Novos contratos enterprise exigem <120ms
  risk_assessment: "LOW - sistema demonstra capacidade consistente"
  rollout_plan:
    - phase_1: "Alertas em warning por 2 semanas"
    - phase_2: "SLO oficial se sem impacto"
```

## Integração com Chaos Engineering

### Chaos Testing de SLOs
```yaml
chaos_experiments:
  - name: "latency_injection_bus"
    target: "neural-hive-gateway"
    fault: "latency_injection"
    duration: "10m"
    parameters:
      delay: "200ms"
      percentage: "10%"
    success_criteria:
      - "availability_slo >= 99.9%"
      - "error_budget_burn_rate < 5x"

  - name: "pod_failure_resilience"
    target: "neural-hive-orquestrador"
    fault: "pod_kill"
    duration: "5m"
    parameters:
      replicas_to_kill: 1
    success_criteria:
      - "mttr < 60s"
      - "no_user_impact"
```

### SLO-Aware Chaos
- Executar chaos apenas quando error budget > 50%
- Parar experimentos se SLO breached
- Correlacionar resultados com métricas de negócio

## Ferramentas e Integrações

### Sloth (SLO Generator)
```yaml
# sloth-config.yaml
slos:
  - name: "neural-hive-bus-latency"
    objective: 99.9
    sli:
      events:
        error_query: |
          histogram_quantile(0.95,
            sum(rate(neural_hive_barramento_duration_seconds_bucket[5m])) by (le)
          ) * 1000 > 150
        total_query: |
          sum(rate(neural_hive_barramento_duration_seconds_total[5m]))
    alerting:
      page_alert: true
      ticket_alert: false
```

### Pyrra (SLO Dashboard Generator)
```bash
# Auto-generate dashboards from SLO configs
pyrra generate --config-file=slos.yaml --output-dir=dashboards/
```

### Custom SLO Calculator
```python
# tools/slo_calculator.py
def calculate_error_budget_remaining(error_rate_30d: float, slo: float) -> float:
    """Calculate remaining error budget percentage"""
    allowed_error_rate = 1 - slo
    consumed_budget = error_rate_30d / allowed_error_rate
    return max(0, (1 - consumed_budget) * 100)

def time_to_budget_exhaustion(current_burn_rate: float, remaining_budget: float) -> str:
    """Estimate time until error budget exhaustion"""
    if current_burn_rate <= 0:
        return "Never (no burn)"

    hours_remaining = remaining_budget / current_burn_rate
    if hours_remaining < 1:
        return f"{int(hours_remaining * 60)}m"
    elif hours_remaining < 24:
        return f"{int(hours_remaining)}h"
    else:
        return f"{int(hours_remaining / 24)}d"
```

## Checklist de Implementação

### ✅ SLOs Definidos
- [ ] SLOs críticos identificados e documentados
- [ ] Métricas base implementadas e testadas
- [ ] Error budgets calculados e monitorados
- [ ] Dashboards de SLO criados

### ✅ Alertas Configurados
- [ ] Alertas de SLO com thresholds corretos
- [ ] Alertas de error budget burn implementados
- [ ] Routing por severidade e componente
- [ ] Runbooks criados para cada alerta crítico

### ✅ Processo Operacional
- [ ] War room procedures documentados
- [ ] Escalation matrix definido
- [ ] SLO review meetings agendados
- [ ] Métricas de qualidade dos alertas implementadas

### ✅ Ferramentas e Automação
- [ ] Sloth/Pyrra configurado (opcional)
- [ ] Custom tooling para SLO management
- [ ] Integration com chaos engineering
- [ ] Alertas preditivos implementados

Este guia garante que o Neural Hive-Mind tenha SLOs robustos, alertas precisos e processos operacionais bem definidos para manter alta disponibilidade e performance.