# Tasks: Monitoring Stack Completo

> **Spec:** `.agent-os/specs/2026-04-04-monitoring-stack/spec.md`
> **Data Criação:** 2026-04-04
> **Estimativa Total:** 184 horas (~7 semanas)

---

## Resumo Executivo

| Epic | Tickets | Esforço | Duração |
|------|---------|---------|---------|
| Epic 1: Loki Stack | 5 | 28h | 1 semana |
| Epic 2: Thanos LTR | 4 | 24h | 1 semana |
| Epic 3: Istio Monitoring | 5 | 28h | 1 semana |
| Epic 4: Advanced Alerting | 5 | 28h | 1 semana |
| Epic 5: Unified Dashboards | 6 | 52h | 2 semanas |
| Epic 6: Runbooks | 4 | 24h | 1 semana |
| **TOTAL** | **29** | **184h** | **7 semanas** |

---

## Epic 1: Loki Stack (Logging Centralizado)

**Objetivo:** Implementar agregação de logs centralizada com Loki e Promtail.

### Ticket 1.1: Deploy Loki Helm Chart

**Descrição:** Instalar e configurar Loki para armazenamento centralizado de logs do cluster Kubernetes.

**Estimativa:** 6 horas

**Dependências:** Nenhuma

**Tarefas:**
- [ ] 1.1.1 Adicionar repo do Grafana Helm
- [ ] 1.1.2 Criar values.yaml para Loki
- [ ] 1.1.3 Configurar storage backend (S3/GCS)
- [ ] 1.1.4 Configurar retenção de logs (30d padrão, 90d arquivo)
- [ ] 1.1.5 Deploy via Helm
- [ ] 1.1.6 Verificar pods estão Running

**Critérios de Aceite:**
- [ ] Loki pods em estado Running
- [ ] Storage configurado com 50Gi mínimo
- [ ] Endpoint `/loki/api/v1/push` respondendo
- [ ] Retenção configurada para 30 dias

**Arquivos:**
- `infra/helm/loki/values.yaml`
- `infra/helm/loki/Chart.yaml`

---

### Ticket 1.2: Configurar Promtail

**Descrição:** Instalar Promtail como DaemonSet para coleta de logs de todos os nodes do cluster.

**Estimativa:** 6 horas

**Dependências:** 1.1 (Loki deploy)

**Tarefas:**
- [ ] 1.2.1 Criar values.yaml do Promtail
- [ ] 1.2.2 Configurar pipeline de parse de logs JSON
- [ ] 1.2.3 Adicionar labels dinâmicos (namespace, pod, container)
- [ ] 1.2.4 Configurar relabeling para serviços críticos
- [ ] 1.2.5 Deploy via Helm
- [ ] 1.2.6 Verificar ingesta de logs

**Critérios de Aceite:**
- [ ] Promtail DaemonSet com 1 pod por node
- [ ] Logs aparecendo no Loki UI
- [ ] Labels: `namespace`, `pod`, `container`, `app`
- [ ] Taxa de ingesta > 1MB/s

**Arquivos:**
- `infra/helm/promtail/values.yaml`
- `infra/helm/promtail/config.yaml`

---

### Ticket 1.3: Integrar Loki com Grafana

**Descrição:** Configurar Grafana como frontend de consulta ao Loki.

**Estimativa:** 4 horas

**Dependências:** 1.1 (Loki deploy)

**Tarefas:**
- [ ] 1.3.1 Adicionar Loki como datasource no Grafana
- [ ] 1.3.2 Testar query básica: `{job="var/logs/*"}`
- [ ] 1.3.3 Configurar variáveis de template
- [ ] 1.3.4 Testar LogQL com filtros

**Critérios de Aceite:**
- [ ] Datasource "Loki" configurado e Healthy
- [ ] Query básica retorna logs
- [ ] Variáveis `$namespace`, `$pod` funcionando

**Arquivos:**
- `infra/helm/grafana/datasources/loki.yaml`

---

### Ticket 1.4: Criar Dashboards de Logs

**Descrição:** Criar dashboards Grafana para visualização e busca de logs.

**Estimativa:** 8 horas

**Dependências:** 1.3 (Loki datasource)

**Tarefas:**
- [ ] 1.4.1 Dashboard "Logs - Todos os Serviços"
- [ ] 1.4.2 Dashboard "Logs - Neural Hive Services"
- [ ] 1.4.3 Dashboard "Logs - Errors & Warnings"
- [ ] 1.4.4 Dashboard "Logs - Audit Trail"
- [ ] 1.4.5 Testar filtros e buscas

**Critérios de Aceite:**
- [ ] 4 dashboards criados e importados
- [ ] Filtro por time range funcionando
- [ ] Busca por texto funcionando
- [ ] Links para traces (quando disponível)

**Arquivos:**
- `infra/dashboards/logs-all-services.json`
- `infra/dashboards/logs-neural-hive.json`
- `infra/dashboards/logs-errors.json`
- `infra/dashboards/logs-audit.json`

---

### Ticket 1.5: Criar Testes E2E do Loki Stack

**Descrição:** Garantir que logs fluem corretamente dos pods até o Loki.

**Estimativa:** 4 horas

**Dependências:** 1.4 (Dashboards criados)

**Tarefas:**
- [ ] 1.5.1 Criar teste de injecção de log
- [ ] 1.5.2 Verificar log aparece no Promtail
- [ ] 1.5.3 Verificar log chega ao Loki
- [ ] 1.5.4 Verificar log aparece no Grafana
- [ ] 1.5.5 Testar filtros de labels
- [ ] 1.5.6 Testar busca de texto

**Critérios de Aceite:**
- [ ] Teste end-to-end passando
- [ ] Latência de ingesta < 30s
- [ ] 100% dos logs de teste encontrados
- [ ] Labels corretamente aplicados

**Arquivos:**
- `tests/integration/loki/test_loki_stack.py`

---

## Epic 2: Thanos LTR (Long-Term Retention)

**Objetivo:** Implementar retenção de métricas por 1 ano com Thanos.

### Ticket 2.1: Deploy Thanos Compactor

**Descrição:** Instalar Thanos Compactor para compactação e downsampling de métricas antigas.

**Estimativa:** 6 horas

**Dependências:** Nenhuma

**Tarefas:**
- [ ] 2.1.1 Criar values.yaml do Thanos Compactor
- [ ] 2.1.2 Configurar storage S3/GCS para blocos
- [ ] 2.1.3 Configurar downsampling (5m, 1h, 6h)
- [ ] 2.1.4 Configurar retenção (raw: 30d, 5m: 90d, 1h: 1y)
- [ ] 2.1.5 Deploy via Helm
- [ ] 2.1.6 Verificar compaction job

**Critérios de Aceite:**
- [ ] Thanos Compactor pod rodando
- [ ] Bloco de armazenamento configurado
- [ ] CronJob de compactação funcionando
- [ ] Retenção configurada para 1 ano

**Arquivos:**
- `infra/helm/thanos/compactor-values.yaml`

---

### Ticket 2.2: Configurar Remote Write

**Descrição:** Configurar Prometheus para enviar métricas para o Thanos Receiver.

**Estimativa:** 6 horas

**Dependências:** Nenhuma

**Tarefas:**
- [ ] 2.2.1 Deploy Thanos Receiver
- [ ] 2.2.2 Configurar Prometheus remote_write
- [ ] 2.2.3 Configurar write relabeling
- [ ] 2.2.4 Testar envio de métricas
- [ ] 2.2.5 Verificar armazenamento no object storage

**Critérios de Aceite:**
- [ ] Prometheus remote_write configurado
- [ ] Métricas aparecendo no Thanos
- [ ] Taxa de envio > 10k samples/s
- [ ] Sem erros no Prometheus logs

**Arquivos:**
- `infra/helm/thanos/receiver-values.yaml`
- `infra/helm/kube-prometheus/prometheus-values.yaml`

---

### Ticket 2.3: Configurar Query Frontend

**Descrição:** Configurar Thanos Query e Query Frontend para consultas federadas.

**Estimativa:** 6 horas

**Dependências:** 2.1, 2.2

**Tarefas:**
- [ ] 2.3.1 Deploy Thanos Query
- [ ] 2.3.2 Deploy Thanos Query Frontend
- [ ] 2.3.3 Configurar store endpoints (Prometheus + Thanos)
- [ ] 2.3.4 Configurar cache (Redis/Memcached)
- [ ] 2.3.5 Testar queries multi-tenant
- [ ] 2.3.6 Configurar datasource no Grafana

**Critérios de Aceite:**
- [ ] Thanos Query pods rodando
- [ ] Query Frontend com cache configurado
- [ ] Queries retornam dados históricos > 30 dias
- [ ] Performance de query < 5s

**Arquivos:**
- `infra/helm/thanos/query-values.yaml`
- `infra/helm/thanos/query-frontend-values.yaml`

---

### Ticket 2.4: Criar Testes E2E do Thanos Stack

**Descrição:** Garantir que métricas fluem corretamente para long-term retention.

**Estimativa:** 6 horas

**Dependências:** 2.3 (Query configurado)

**Tarefas:**
- [ ] 2.4.1 Criar teste de métrica histórica
- [ ] 2.4.2 Verificar downsampling aplicado
- [ ] 2.4.3 Testar query de 1 ano atrás
- [ ] 2.4.4 Verificar compactação funcionando
- [ ] 2.4.5 Testar query distribuída

**Critérios de Aceite:**
- [ ] Teste E2E passando
- [ ] Métricas de 1 ano acessíveis
- [ ] Downsampling reduzindo tamanho dos blocos
- [ ] Query performance aceitável

**Arquivos:**
- `tests/integration/thanos/test_thanos_stack.py`

---

## Epic 3: Istio Monitoring

**Objetivo:** Monitorar tráfego e métricas do service mesh Istio.

### Ticket 3.1: Configurar Istio Mesh Metrics

**Descrição:** Configurar Prometheus para scraping de métricas do Istio.

**Estimativa:** 6 horas

**Dependências:** Istio instalado no cluster

**Tarefas:**
- [ ] 3.1.1 Verificar Prometheus podIstioDiscoveryEnabled
- [ ] 3.1.2 Adicionar scrape configs para Istio
- [ ] 3.1.3 Configurar relabeling para workloads Istio
- [ ] 3.1.4 Verificar métricas: `istio_requests_total`, `istio_response_duration`
- [ ] 3.1.5 Testar métricas de sidecar

**Critérios de Aceite:**
- [ ] Métricas do Istio aparecendo no Prometheus
- [ ] Labels: `source_workload`, `destination_workload`, `request_protocol`
- [ ] Taxa de scraping > 95%

**Arquivos:**
- `infra/helm/kube-prometheus/prometheus-istio-values.yaml`

---

### Ticket 3.2: Criar ServiceMesh Dashboard

**Descrição:** Dashboard completo para visualização do service mesh.

**Estimativa:** 10 horas

**Dependências:** 3.1

**Tarefas:**
- [ ] 3.2.1 Dashboard "Istio Mesh Overview"
- [ ] 3.2.2 Dashboard "Istio Services Details"
- [ ] 3.2.3 Dashboard "Istio Workloads Metrics"
- [ ] 3.2.4 Dashboard "Istio Latency & Throughput"
- [ ] 3.2.5 Dashboard "Istio Errors & Timeouts"
- [ ] 3.2.6 Testar com tráfego real

**Critérios de Aceite:**
- [ ] 5 dashboards criados
- [ ] Topologia do mesh visualizada
- [ ] Latência P50/P95/P99 visível
- [ ] Taxa de erro por serviço visível

**Arquivos:**
- `infra/dashboards/istio-mesh-overview.json`
- `infra/dashboards/istio-services.json`
- `infra/dashboards/istio-workloads.json`
- `infra/dashboards/istio-latency.json`
- `infra/dashboards/istio-errors.json`

---

### Ticket 3.3: Configurar SLOs de Mesh

**Descrição:** Definir e monitorar SLOs para comunicação via service mesh.

**Estimativa:** 6 horas

**Dependências:** 3.1

**Tarefas:**
- [ ] 3.3.1 Definir SLOs: Latência (P95 < 200ms), Disponibilidade (99.9%)
- [ ] 3.3.2 Criar regras Prometheus para SLI
- [ ] 3.3.3 Criar recording rules
- [ ] 3.3.4 Criar alertas de burn rate
- [ ] 3.3.5 Dashboard de SLOs

**Critérios de Aceite:**
- [ ] SLIs calculadas automaticamente
- [ ] Error budget tracking funcional
- [ ] Alertas de SLO configurados
- [ ] Dashboard mostra SLO attainment

**Arquivos:**
- `infra/prometheus/rules/istio-slo.yaml`
- `infra/dashboards/istio-slo.json`

---

### Ticket 3.4: Criar Testes E2E do Istio Monitoring

**Descrição:** Garantir que métricas do Istio estão sendo coletadas corretamente.

**Estimativa:** 4 horas

**Dependências:** 3.3

**Tarefas:**
- [ ] 3.4.1 Criar teste de tráfego mesh
- [ ] 3.4.2 Verificar métricas de request
- [ ] 3.4.3 Verificar métricas de latência
- [ ] 3.4.4 Verificar labels de source/destination
- [ ] 3.4.5 Testar SLO calculations

**Critérios de Aceite:**
- [ ] Teste E2E passando
- [ ] Todas as métricas esperadas presentes
- [ ] Labels corretos
- [ ] Cálculo de SLO correto

**Arquivos:**
- `tests/integration/istio/test_istio_monitoring.py`

---

### Ticket 3.5: Configurar Distributed Tracing Integration

**Descrição:** Integrar Jaeger com Istio para traces distribuídos.

**Estimativa:** 2 horas

**Dependências:** Jaeger instalado

**Tarefas:**
- [ ] 3.5.1 Configurar mesh config para tracing
- [ ] 3.5.2 Definir sampling rate (1% para prod)
- [ ] 3.5.3 Verificar traces no Jaeger
- [ ] 3.5.4 Criar dashboard de traces

**Critérios de Aceite:**
- [ ] Headers de tracing propagados
- [ ] Traces aparecem no Jaeger
- [ ] Sampling configurado corretamente

**Arquivos:**
- `infra/istio/config/tracing.yaml`

---

## Epic 4: Advanced Alerting

**Objetivo:** Implementar alertas avançados com multi-window e integração PagerDuty.

### Ticket 4.1: Implementar Multi-Window Alerting

**Descrição:** Configurar alertas Prometheus com múltiplas janelas de tempo.

**Estimativa:** 8 horas

**Dependências:** Nenhuma

**Tarefas:**
- [ ] 4.1.1 Criar regras de alerta Pyramid
- [ ] 4.1.2 Janela curta (5m) + longa (1h)
- [ ] 4.1.3 Alertas críticos: Severity=Critical
- [ ] 4.1.4 Alertas degradação: Severity=Warning
- [ ] 4.1.5 Testar falsos positivos

**Critérios de Aceite:**
- [ ] Alertas com 2 janelas funcionando
- [ ] Redução de falsos positivos > 80%
- [ ] Severidade correta atribuída

**Arquivos:**
- `infra/prometheus/rules/multi-window-alerts.yaml`

---

### Ticket 4.2: Integrar PagerDuty

**Descrição:** Configurar Alertmanager para envio de alertas ao PagerDuty.

**Estimativa:** 6 horas

**Dependências:** 4.1

**Tarefas:**
- [ ] 4.2.1 Criar integração PagerDuty no Alertmanager
- [ ] 4.2.2 Configurar routing baseado em severidade
- [ ] 4.2.3 Mapear serviços para escalation policies
- [ ] 4.2.4 Testar envio de alerta
- [ ] 4.2.5 Configurar silencing de manutenção

**Critérios de Aceite:**
- [ ] Alertas críticos chegam ao PagerDuty
- [ ] Routing correto por serviço
- [ ] Acknowledge do PagerDuty reflete no Alertmanager

**Arquivos:**
- `infra/helm/alertmanager/config-pagerduty.yaml`

---

### Ticket 4.3: Criar Alert Silences Automated

**Descrição:** Automatizar silenciamento de alertas durante janelas de manutenção.

**Estimativa:** 6 horas

**Dependências:** 4.2

**Tarefas:**
- [ ] 4.3.1 Criar API client para Alertmanager
- [ ] 4.3.2 Detectar janela de manutenção (annotations)
- [ ] 4.3.3 Criar silences automáticos
- [ ] 4.3.4 Remover silences após manutenção
- [ ] 4.3.5 Dashboard de silences ativos

**Critérios de Aceite:**
- [ ] Silences criados automaticamente
- [ ] Silences expiram corretamente
- [ ] Dashboard mostra silences ativos

**Arquivos:**
- `tools/auto-silence/main.py`
- `infra/dashboards/alertmanager-silences.json`

---

### Ticket 4.4: Criar Pyramid de Alertas

**Descrição:** Estruturar alertas em níveis de severidade com volume apropriado.

**Estimativa:** 4 horas

**Dependências:** 4.1

**Tarefas:**
- [ ] 4.4.1 P1: Site Down (0-2/dia)
- [ ] 4.4.2 P2: Service Degraded (2-5/dia)
- [ ] 4.4.3 P3: High Latency (5-10/dia)
- [ ] 4.4.4 P4: Resource Usage (10-20/dia)
- [ ] 4.4.5 P5: Info (< 50/dia)
- [ ] 4.4.6 Documentar critérios

**Critérios de Aceite:**
- [ ] 5 níveis de severidade definidos
- [ ] Volume de alertas dentro de limites
- [ ] Documentação clara

**Arquivos:**
- `docs/monitoring/alert-pyramid.md`

---

### Ticket 4.5: Criar Testes E2E do Alerting

**Descrição:** Garantir que alertas funcionam corretamente.

**Estimativa:** 4 horas

**Dependências:** 4.3

**Tarefas:**
- [ ] 4.5.1 Criar teste de gatilho de alerta
- [ ] 4.5.2 Verificar envio ao PagerDuty
- [ ] 4.5.3 Testar multi-window
- [ ] 4.5.4 Testar auto-silence
- [ ] 4.5.5 Testar rotas de alerta

**Critérios de Aceite:**
- [ ] Testes E2E passando
- [ ] Alerta chega ao PagerDuty < 30s
- [ ] Auto-silence funciona

**Arquivos:**
- `tests/integration/alerting/test_alerting.py`

---

## Epic 5: Unified Dashboards

**Objetivo:** Criar dashboards executivos e operacionais consolidados.

### Ticket 5.1: Criar Neural Hive Executive Dashboard

**Descrição:** Dashboard executivo com visão geral da saúde do sistema.

**Estimativa:** 12 horas

**Dependências:** 1.4, 2.3, 3.2

**Tarefas:**
- [ ] 5.1.1 Seção: Health Score (0-100)
- [ ] 5.1.2 Seção: SLO Attainment (3 SLOs principais)
- [ ] 5.1.3 Seção: Active Alerts (count por severidade)
- [ ] 5.1.4 Seção: Traffic Overview (RPS)
- [ ] 5.1.5 Seção: Resource Utilization
- [ ] 5.1.6 Seção: Recent Incidents
- [ ] 5.1.7 Testar com dados reais

**Critérios de Aceite:**
- [ ] 1 dashboard executivo criado
- [ ] Visão clara da saúde do sistema
- [ ] Carregamento < 2s
- [ ] Responsivo para mobile

**Arquivos:**
- `infra/dashboards/executive-overview.json`

---

### Ticket 5.2: Criar SRE Overview Dashboard

**Descrição:** Dashboard operacional detalhado para SREs.

**Estimativa:** 12 horas

**Dependências:** 1.4, 2.3, 3.2, 4.4

**Tarefas:**
- [ ] 5.2.1 Seção: Cluster Health
- [ ] 5.2.2 Seção: Services Status
- [ ] 5.2.3 Seção: Performance Metrics
- [ ] 5.2.4 Seção: Error Rates
- [ ] 5.2.5 Seção: Database Metrics
- [ ] 5.2.6 Seção: Kafka Lag
- [ ] 5.2.7 Seção: Active Alerts Panel
- [ ] 5.2.8 Links para dashboards detalhados

**Critérios de Aceite:**
- [ ] 1 dashboard SRE criado
- [ ] Todas as métricas críticas visíveis
- [ ] Drill-down funcional
- [ ] Atualização em tempo real

**Arquivos:**
- `infra/dashboards/sre-overview.json`

---

### Ticket 5.3: Criar Business Metrics Dashboard

**Descrição:** Dashboard com métricas de negócio do Neural Hive Mind.

**Estimativa:** 10 horas

**Dependências:** Nenhuma

**Tarefas:**
- [ ] 5.3.1 Seção: Intention Processing Rate
- [ ] 5.3.2 Seção: Consensus Decisions (approve/reject ratio)
- [ ] 5.3.3 Seção: Specialist Participation
- [ ] 5.3.4 Seção: Ticket Lifecycle
- [ ] 5.3.5 Seção: ML Model Performance
- [ ] 5.3.6 Seção: User Satisfaction (feedback scores)

**Critérios de Aceite:**
- [ ] 1 dashboard de negócio criado
- [ ] Métricas alinhadas com objetivos do produto
- [ ] Contexto e trendlines

**Arquivos:**
- `infra/dashboards/business-metrics.json`

---

### Ticket 5.4: Criar Neural Hive Services Detail Dashboards

**Descrição:** Dashboards detalhados para cada serviço principal.

**Estimativa:** 10 horas

**Dependências:** 5.2

**Tarefas:**
- [ ] 5.4.1 Dashboard: Gateway Intenções
- [ ] 5.4.2 Dashboard: Semantic Translation
- [ ] 5.4.3 Dashboard: Consensus Engine
- [ ] 5.4.4 Dashboard: Orchestrator Dynamic
- [ ] 5.4.5 Dashboard: Approval Service
- [ ] 5.4.6 Dashboard: Queen Agent
- [ ] 5.4.7 Template de dashboard para novos serviços

**Critérios de Aceite:**
- [ ] 6 dashboards de serviço criados
- [ ] Template reutilizável
- [ ] Métricas padronizadas por serviço

**Arquivos:**
- `infra/dashboards/services/gateway.json`
- `infra/dashboards/services/semantic-translation.json`
- `infra/dashboards/services/consensus.json`
- `infra/dashboards/services/orchestrator.json`
- `infra/dashboards/services/approval.json`
- `infra/dashboards/services/queen-agent.json`
- `infra/dashboards/services/template.json`

---

### Ticket 5.5: Criar Database & Infrastructure Dashboards

**Descrição:** Dashboards para infraestrutura de dados.

**Estimativa:** 4 horas

**Dependências:** 2.3

**Tarefas:**
- [ ] 5.5.1 Dashboard: MongoDB
- [ ] 5.5.2 Dashboard: Redis
- [ ] 5.5.3 Dashboard: Kafka
- [ ] 5.5.4 Dashboard: Neo4j
- [ ] 5.5.5 Dashboard: Kubernetes Nodes

**Critérios de Aceite:**
- [ ] 5 dashboards de infraestrutura
- [ ] Conexões, queries, latência visíveis

**Arquivos:**
- `infra/dashboards/infra/mongodb.json`
- `infra/dashboards/infra/redis.json`
- `infra/dashboards/infra/kafka.json`
- `infra/dashboards/infra/neo4j.json`
- `infra/dashboards/infra/k8s-nodes.json`

---

### Ticket 5.6: Criar Testes E2E dos Dashboards

**Descrição:** Garantir que dashboards funcionam corretamente.

**Estimativa:** 4 horas

**Dependências:** 5.1, 5.2, 5.3

**Tarefas:**
- [ ] 5.6.1 Testar carregamento de todos os dashboards
- [ ] 5.6.2 Verificar dados são retornados
- [ ] 5.6.3 Testar filtros e variáveis
- [ ] 5.6.4 Testar links de drill-down
- [ ] 5.6.5 Testar responsividade

**Critérios de Aceite:**
- [ ] Todos dashboards carregam < 2s
- [ ] Dados corretos exibidos
- [ ] Links funcionando

**Arquivos:**
- `tests/integration/dashboards/test_dashboards.py`

---

## Epic 6: Runbooks

**Objetivo:** Criar documentação operacional para todos os alertas críticos.

### Ticket 6.1: Criar Runbooks de Infraestrutura

**Descrição:** Documentar procedimentos para incidentes de infraestrutura.

**Estimativa:** 8 horas

**Dependências:** 4.4

**Tarefas:**
- [ ] 6.1.1 Runbook: High CPU Usage
- [ ] 6.1.2 Runbook: High Memory Usage
- [ ] 6.1.3 Runbook: Disk Space Running Out
- [ ] 6.1.4 Runbook: Network Latency
- [ ] 6.1.5 Runbook: Kubernetes Node Not Ready
- [ ] 6.1.6 Runbook: Pod CrashLoopBackOff
- [ ] 6.1.7 Runbook: PVC Issues

**Critérios de Aceite:**
- [ ] 7 runbooks criados
- [ ] Formato padronizado (symptom → diagnosis → action)
- [ ] Links para dashboards

**Arquivos:**
- `docs/runbooks/infra/high-cpu.md`
- `docs/runbooks/infra/high-memory.md`
- `docs/runbooks/infra/disk-space.md`
- `docs/runbooks/infra/network-latency.md`
- `docs/runbooks/infra/node-not-ready.md`
- `docs/runbooks/infra/pod-crashloop.md`
- `docs/runbooks/infra/pvc-issues.md`

---

### Ticket 6.2: Criar Runbooks de Aplicação

**Descrição:** Documentar procedimentos para incidentes de aplicação.

**Estimativa:** 8 horas

**Dependências:** 4.4

**Tarefas:**
- [ ] 6.2.1 Runbook: High Error Rate
- [ ] 6.2.2 Runbook: High Latency
- [ ] 6.2.3 Runbook: Service Unavailable
- [ ] 6.2.4 Runbook: Database Connection Issues
- [ ] 6.2.5 Runbook: Kafka Consumer Lag
- [ ] 6.2.6 Runbook: Cache Miss Storm
- [ ] 6.2.7 Runbook: Consensus Deadlock

**Critérios de Aceite:**
- [ ] 7 runbooks criados
- [ ] Comandos de diagnóstico incluídos
- [ ] Escalation path definido

**Arquivos:**
- `docs/runbooks/app/high-error-rate.md`
- `docs/runbooks/app/high-latency.md`
- `docs/runbooks/app/service-unavailable.md`
- `docs/runbooks/app/db-connection.md`
- `docs/runbooks/app/kafka-lag.md`
- `docs/runbooks/app/cache-storm.md`
- `docs/runbooks/app/consensus-deadlock.md`

---

### Ticket 6.3: Criar Runbooks de SLO

**Descrição:** Documentar procedimentos para violação de SLOs.

**Estimativa:** 4 horas

**Dependências:** 3.3

**Tarefas:**
- [ ] 6.3.1 Runbook: Latency SLO Breach
- [ ] 6.3.2 Runbook: Availability SLO Breach
- [ ] 6.3.3 Runbook: Error Budget Exhausted
- [ ] 6.3.4 Procedimento de Declaração de Incidente

**Critérios de Aceite:**
- [ ] 4 runbooks de SLO
- [ ] Matriz de responsabilidade

**Arquivos:**
- `docs/runbooks/slo/latency-breach.md`
- `docs/runbooks/slo/availability-breach.md`
- `docs/runbooks/slo/error-budget.md`
- `docs/runbooks/slo/incident-procedure.md`

---

### Ticket 6.4: Criar Índice de Runbooks

**Descrição:** Criar índice central e conectar alertas aos runbooks.

**Estimativa:** 4 horas

**Dependências:** 6.1, 6.2, 6.3

**Tarefas:**
- [ ] 6.4.1 Criar índice central de runbooks
- [ ] 6.4.2 Adicionar links nos alertas Prometheus
- [ ] 6.4.3 Adicionar links nos dashboards Grafana
- [ ] 6.4.4 Criar template de runbook

**Critérios de Aceite:**
- [ ] Índice navegável criado
- [ ] Todos os alertas com link para runbook
- [ ] Template padronizado

**Arquivos:**
- `docs/runbooks/README.md`
- `docs/runbooks/template.md`

---

## Resumo de Esforço

| Epic | Tickets | Horas | Dias (8h) |
|------|---------|-------|-----------|
| Epic 1: Loki Stack | 5 | 28h | 3.5d |
| Epic 2: Thanos LTR | 4 | 24h | 3d |
| Epic 3: Istio Monitoring | 5 | 28h | 3.5d |
| Epic 4: Advanced Alerting | 5 | 28h | 3.5d |
| Epic 5: Unified Dashboards | 6 | 52h | 6.5d |
| Epic 6: Runbooks | 4 | 24h | 3d |
| **TOTAL** | **29** | **184h** | **23d** |

---

## Ordem Sugerida de Implementação

1. **Sprint 1 (Semana 1):** Epic 1 (Loki Stack)
2. **Sprint 2 (Semana 2):** Epic 2 (Thanos LTR)
3. **Sprint 3 (Semana 3):** Epic 3 (Istio Monitoring)
4. **Sprint 4 (Semana 4):** Epic 4 (Advanced Alerting)
5. **Sprint 5-6 (Semanas 5-6):** Epic 5 (Unified Dashboards)
6. **Sprint 7 (Semana 7):** Epic 6 (Runbooks)

---

## Checklist de Completação

- [ ] Todos os 29 tickets implementados
- [ ] Todos os testes E2E passando
- [ ] Todos os dashboards criados e testados
- [ ] Todos os runbooks escritos
- [ ] Integração PagerDuty funcionando
- [ ] Loki ingestando > 10MB/s
- [ ] Thanos retendo 1 ano de métricas
- [ ] Dashboards carregando < 2s
- [ ] Alertas notificados < 30s
- [ ] MTTD < 5min
- [ ] MTTR < 20min

---

*Tasks document criado por Claude Code - 2026-04-04*
