# Padrões de ServiceMonitor/PodMonitor - Neural Hive-Mind

## Visão Geral

Este documento define os padrões para configuração de ServiceMonitors e PodMonitors no sistema Neural Hive-Mind, garantindo consistência na coleta de métricas e descoberta de serviços pelo Prometheus.

## Labels Obrigatórios

### Labels de Metadata
Todos os ServiceMonitors/PodMonitors devem incluir os seguintes labels:

```yaml
metadata:
  labels:
    # Descoberta pelo Prometheus Operator
    neural.hive/metrics: "enabled"
    neural.hive/component: "<nome-do-componente>"
    neural.hive/layer: "<camada-arquitetural>"
    release: prometheus
```

### Labels por Camada Arquitetural

| Camada | Valor `neural.hive/layer` | Descrição |
|--------|---------------------------|-----------|
| Experiência | `experiencia` | APIs, gateways, interfaces de usuário |
| Cognição | `cognicao` | Processamento de IA, geração de planos |
| Orquestração | `orquestracao` | Coordenação de fluxos, barramento |
| Persistência | `persistencia` | Bancos de dados, storage |
| Infraestrutura | `infraestrutura` | Kubernetes, networking |
| Observabilidade | `observabilidade` | Monitoring, logging, tracing |
| Messaging | `messaging` | Kafka, message brokers |
| Resiliência | `resiliencia` | Self-healing, chaos engineering |

## Annotations Padrão

```yaml
metadata:
  annotations:
    neural.hive/scrape-config: "standard"  # ou "pod-direct"
    neural.hive/metrics-path: "/metrics"
    neural.hive/scrape-interval: "30s"
    neural.hive/component-version: "{{ .Chart.AppVersion }}"
```

## Configurações de Relabeling

### Relabeling Padrão (aplicado a todas as métricas)

```yaml
relabelings:
  # Metadados Kubernetes
  - sourceLabels: [__meta_kubernetes_service_name]
    targetLabel: service_name
  - sourceLabels: [__meta_kubernetes_namespace]
    targetLabel: kubernetes_namespace
  - sourceLabels: [__meta_kubernetes_pod_name]
    targetLabel: kubernetes_pod_name
  - sourceLabels: [__meta_kubernetes_pod_container_name]
    targetLabel: kubernetes_container_name

  # Labels padrão Neural Hive-Mind
  - targetLabel: neural_hive_component
    replacement: <component-name>
  - targetLabel: neural_hive_layer
    replacement: <layer-name>
  - targetLabel: cluster
    replacement: neural-hive-main
  - targetLabel: environment
    replacement: production
```

### Metric Relabeling Padrão

```yaml
metricRelabelings:
  # Garantir prefixo neural_hive_
  - sourceLabels: [__name__]
    regex: "neural_hive_(.+)"
    targetLabel: __name__
    replacement: "neural_hive_${1}"

  # Adicionar labels padrão às métricas
  - sourceLabels: [__name__]
    regex: "neural_hive_.*"
    targetLabel: neural_hive_component
    replacement: <component-name>
  - sourceLabels: [__name__]
    regex: "neural_hive_.*"
    targetLabel: neural_hive_layer
    replacement: <layer-name>

  # Preservar correlation IDs
  - sourceLabels: [neural_hive_intent_id]
    targetLabel: intent_id
  - sourceLabels: [neural_hive_plan_id]
    targetLabel: plan_id

  # Informações de instância
  - targetLabel: service_name
    replacement: <service-full-name>
  - targetLabel: component_version
    replacement: <version>
```

## Nomenclatura de Métricas

### Padrão de Nomenclatura
- **Prefixo obrigatório**: `neural_hive_`
- **Formato**: `neural_hive_<component>_<metric_name>_<unit>`
- **Exemplos**:
  - `neural_hive_requests_total`
  - `neural_hive_captura_duration_seconds`
  - `neural_hive_plan_generation_errors_total`

### Labels de Métricas Obrigatórios
Todas as métricas Neural Hive-Mind devem incluir:

```yaml
# Labels básicos
neural_hive_component: "gateway-intencoes"
neural_hive_layer: "experiencia"

# Labels de contexto (quando aplicável)
neural_hive_intent_id: "intent_123"
neural_hive_plan_id: "plan_456"
neural_hive_domain: "financial"
neural_hive_channel: "api"

# Labels operacionais
status: "success|error|timeout"
method: "POST|GET|PUT|DELETE"
```

## Templates de Uso

### ServiceMonitor Básico

```yaml
{{- if .Values.serviceMonitor.enabled }}
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: {{ include "myservice.fullname" . }}-metrics
  labels:
    {{- include "myservice.labels" . | nindent 4 }}
    neural.hive/metrics: "enabled"
    neural.hive/component: "myservice"
    neural.hive/layer: "experiencia"
    release: prometheus
  annotations:
    neural.hive/scrape-config: "standard"
    neural.hive/metrics-path: "/metrics"
    neural.hive/scrape-interval: "30s"
spec:
  selector:
    matchLabels:
      {{- include "myservice.selectorLabels" . | nindent 6 }}
      component: metrics
  endpoints:
  - port: http
    path: /metrics
    interval: 30s
    scrapeTimeout: 10s
    # ... configurações de relabeling padrão
{{- end }}
```

### PodMonitor para DaemonSet

```yaml
{{- if .Values.podMonitor.enabled }}
apiVersion: monitoring.coreos.com/v1
kind: PodMonitor
metadata:
  name: {{ include "mydaemon.fullname" . }}-pods
  labels:
    {{- include "mydaemon.labels" . | nindent 4 }}
    neural.hive/metrics: "enabled"
    neural.hive/component: "mydaemon"
    neural.hive/layer: "infraestrutura"
    neural.hive/monitor-type: "pod"
    release: prometheus
spec:
  selector:
    matchLabels:
      {{- include "mydaemon.selectorLabels" . | nindent 6 }}
  podMetricsEndpoints:
  - port: metrics
    path: /metrics
    interval: 30s
    # ... configurações de relabeling padrão
{{- end }}
```

## Configurações de Cardinalidade

### Limites Recomendados

```yaml
# Para serviços de alto volume
sampleLimit: 10000
targetLimit: 100

# Para serviços de baixo volume
sampleLimit: 1000
targetLimit: 10
```

### Controle de Labels Dinâmicos

Para evitar alta cardinalidade, limite labels dinâmicos:

```yaml
metricRelabelings:
  # Limitar intent_ids a apenas os últimos N
  - sourceLabels: [neural_hive_intent_id]
    regex: "^.{0,50}.*"  # Primeiros 50 caracteres apenas
    targetLabel: neural_hive_intent_id
    replacement: "${1}"

  # Remover labels problemáticos
  - regex: "high_cardinality_label"
    action: labeldrop
```

## Configurações de Segurança

### Autenticação Básica

```yaml
endpoints:
- port: metrics-secure
  basicAuth:
    username:
      name: monitoring-credentials
      key: username
    password:
      name: monitoring-credentials
      key: password
```

### TLS

```yaml
endpoints:
- port: metrics-tls
  tlsConfig:
    insecureSkipVerify: false
    ca:
      configMap:
        name: metrics-ca
        key: ca.crt
    cert:
      secret:
        name: metrics-tls
        key: tls.crt
    keySecret:
      secret:
        name: metrics-tls
        key: tls.key
```

## Validação e Testes

### Script de Validação

Use o script de validação para verificar conformidade:

```bash
./scripts/validate-observability.sh
```

### Checklist de Validação

- [ ] Labels obrigatórios presentes
- [ ] Nomenclatura de métricas seguindo padrão
- [ ] Configurações de relabeling aplicadas
- [ ] Limites de cardinalidade definidos
- [ ] Documentação atualizada

## Troubleshooting

### Métricas não aparecem no Prometheus

1. Verificar se ServiceMonitor tem label `neural.hive/metrics: "enabled"`
2. Verificar se Service correspondente tem label `component: metrics`
3. Verificar se endpoint está respondendo em `/metrics`
4. Verificar logs do Prometheus Operator

### Alta cardinalidade

1. Revisar labels dinâmicos nas métricas
2. Implementar `sampleLimit` e `targetLimit`
3. Usar `metricRelabelings` para filtrar/limitar labels
4. Monitorar uso de memória do Prometheus

### Labels ausentes

1. Verificar configurações de `metricRelabelings`
2. Verificar se aplicação está gerando labels corretos
3. Validar configurações de relabeling no ServiceMonitor

---

**Documentação atualizada**: {{ now | date "2006-01-02 15:04:05" }}
**Versão**: 1.0.0