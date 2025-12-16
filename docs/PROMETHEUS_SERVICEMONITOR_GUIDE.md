# Prometheus ServiceMonitor Guide

Este guia documenta a configuração dos ServiceMonitors para descoberta automática de métricas no Neural-Hive-Mind.

## Visão Geral

O Prometheus Operator utiliza ServiceMonitors para descobrir automaticamente endpoints de métricas em serviços Kubernetes. Para garantir a descoberta correta, os ServiceMonitors e Services devem ter labels específicos que correspondam ao selector do Prometheus.

## Labels Obrigatórios

Todos os serviços da camada cognitiva do Neural-Hive-Mind devem incluir os seguintes labels:

```yaml
labels:
  neural.hive/metrics: "enabled"
  neural.hive/component: "<nome-do-componente>"
  neural.hive/layer: "cognitiva"
```

### Mapeamento de Componentes

| Serviço | component label |
|---------|-----------------|
| semantic-translation-engine | semantic-translator |
| consensus-engine | consensus-aggregator |
| specialist-business | business-specialist |
| specialist-technical | technical-specialist |
| specialist-architecture | architecture-specialist |
| specialist-behavior | behavior-specialist |
| specialist-evolution | evolution-specialist |

## Configuração do ServiceMonitor

Cada ServiceMonitor deve seguir este padrão:

```yaml
{{- if .Values.serviceMonitor.enabled }}
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: {{ include "<chart-name>.fullname" . }}
  labels:
    {{- include "<chart-name>.labels" . | nindent 4 }}
    # Labels para descoberta do Prometheus Operator
    neural.hive/metrics: "enabled"
    neural.hive/component: "<component-name>"
    neural.hive/layer: "cognitiva"
    {{- with .Values.serviceMonitor.labels }}
    {{- toYaml . | nindent 4 }}
    {{- end }}
spec:
  selector:
    matchLabels:
      {{- include "<chart-name>.selectorLabels" . | nindent 6 }}
  endpoints:
  - port: metrics
    path: /metrics
    interval: {{ .Values.serviceMonitor.interval }}
    scrapeTimeout: {{ .Values.serviceMonitor.scrapeTimeout }}
{{- end }}
```

## Configuração do Service

O Service correspondente deve incluir os mesmos labels:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: {{ include "<chart-name>.fullname" . }}
  labels:
    {{- include "<chart-name>.labels" . | nindent 4 }}
    neural.hive/metrics: "enabled"
    neural.hive/component: "<component-name>"
    neural.hive/layer: "cognitiva"
  annotations:
    neural-hive.io/component: <component-name>
spec:
  type: {{ .Values.service.type }}
  ports:
    - port: {{ .Values.service.ports.metrics.port }}
      targetPort: metrics
      protocol: TCP
      name: metrics
  selector:
    {{- include "<chart-name>.selectorLabels" . | nindent 4 }}
```

## Configuração do Prometheus Operator

O Prometheus deve estar configurado para selecionar ServiceMonitors com o label `neural.hive/metrics: "enabled"`:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: Prometheus
metadata:
  name: neural-hive-prometheus
spec:
  serviceMonitorSelector:
    matchLabels:
      neural.hive/metrics: "enabled"
  # Ou para selecionar todos os ServiceMonitors no namespace:
  serviceMonitorNamespaceSelector: {}
```

## Verificação

### Verificar ServiceMonitors Descobertos

```bash
# Listar ServiceMonitors com label de métricas
kubectl get servicemonitors -l "neural.hive/metrics=enabled" -A

# Verificar targets no Prometheus
kubectl port-forward svc/prometheus 9090:9090
# Acessar http://localhost:9090/targets
```

### Verificar Métricas Disponíveis

```bash
# Testar endpoint de métricas de um serviço específico
kubectl port-forward svc/semantic-translation-engine 8080:8080
curl http://localhost:8080/metrics
```

### Debug de Descoberta

Se os ServiceMonitors não estão sendo descobertos:

1. Verifique os labels do ServiceMonitor:
```bash
kubectl get servicemonitor <name> -o yaml | grep -A 5 labels
```

2. Verifique o selector do Prometheus:
```bash
kubectl get prometheus <name> -o yaml | grep -A 5 serviceMonitorSelector
```

3. Verifique os logs do Prometheus Operator:
```bash
kubectl logs -l app.kubernetes.io/name=prometheus-operator
```

## Métricas Expostas

Cada serviço da camada cognitiva expõe métricas padrão:

- `process_cpu_seconds_total` - Tempo de CPU consumido
- `process_resident_memory_bytes` - Memória residente
- `http_request_duration_seconds` - Duração das requisições HTTP
- `grpc_server_handled_total` - Requisições gRPC processadas
- `kafka_consumer_records_consumed_total` - Mensagens Kafka consumidas
- `cognitive_plan_duration_seconds` - Tempo de geração de planos cognitivos

## Troubleshooting

### Métricas não aparecem no Grafana

1. Verifique se o ServiceMonitor está criado: `kubectl get servicemonitor`
2. Verifique se os labels estão corretos
3. Verifique se o Prometheus está scraping o target
4. Verifique se a data source do Grafana está configurada corretamente

### ServiceMonitor existe mas não é descoberto

- O label `neural.hive/metrics: "enabled"` pode estar faltando
- O namespace do ServiceMonitor pode não estar incluído no `serviceMonitorNamespaceSelector`
- O selector do ServiceMonitor pode não corresponder ao Service

### Endpoint retorna erro 404

- Verifique se a porta `metrics` está configurada no Deployment
- Verifique se a aplicação expõe métricas em `/metrics`
- Verifique se o `targetPort` corresponde ao nome da porta no container

## Referências

- [Prometheus Operator - ServiceMonitor](https://github.com/prometheus-operator/prometheus-operator/blob/main/Documentation/user-guides/getting-started.md)
- [Kubernetes Service Labels](https://kubernetes.io/docs/concepts/overview/working-with-objects/labels/)
