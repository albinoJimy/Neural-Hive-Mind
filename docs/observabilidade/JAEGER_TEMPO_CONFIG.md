# Configuração Jaeger/Tempo UI - Neural Hive-Mind

## Visão Geral

O Neural Hive-Mind utiliza **OpenTelemetry** para tracing distribuído, compatível com:
- **Jaeger** - UI para visualização de traces
- **Grafana Tempo** - Backend de tracing compatível com Jaeger API

## Arquitetura de Tracing

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Services      │────▶│  OpenTelemetry    │────▶│   Jaeger/Tempo  │
│  (Python SDK)   │     │   OTLP Exporter   │     │   Collector     │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                                        │
                                                        ▼
                                              ┌─────────────────┐
                                              │   Jaeger UI     │
                                              │   (Visualização)│
                                              └─────────────────┘
```

## Configuração OTLP

### Variáveis de Ambiente

```bash
# Endpoint OTLP (gRPC)
OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger-collector.observability:4317

# ou para Tempo:
# OTEL_EXPORTER_OTLP_ENDPOINT=http://tempo.observability:4317

# TLS
OTEL_EXPORTER_OTLP_PROTOCOL=grpc
OTEL_EXPORTER_OTLP_INSECURE=true
# OTEL_EXPORTER_OTLP_HEADERS=authorization=Bearer TOKEN
```

### Configuração por Serviço

```python
from neural_hive_observability import ObservabilityConfig, init_tracing

config = ObservabilityConfig(
    service_name="semantic-translation-engine",
    otel_endpoint="http://jaeger-collector.observability:4317",
    otel_tls_enabled=False,
    service_version="1.0.0",
    neural_hive_component="ste",
    neural_hive_layer="cognitive-pipeline"
)

init_tracing(config)
```

## Instalação Jaeger (Kubernetes)

### Helm Chart

```bash
helm repo add jaegertracing https://jaegertracing.github.io/helm-charts
helm repo update

helm install jaeger jaegertracing/jaeger \
  -n observability \
  --create-namespace \
  -f - <<EOF
collector:
  otlp:
    grpc:
      enabled: true
  service:
    type: ClusterIP

query:
  enabled: true
  service:
    type: LoadBalancer  # ou NodePort para kind/minikube

allInOne:
  enabled: false
EOF
```

## Instalação Grafana Tempo

### Helm Chart

```bash
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

helm install tempo grafana/tempo \
  -n observability \
  -f - <<EOF
tempo:
  repository: grafana/tempo
  tag: latest

  receiver:
    otlp:
      protocols:
        grpc:
          endpoint: 0.0.0.0:4317

  storage:
    trace:
      backend: s3  # ou local, azure, gcs
      s3:
        bucket: tempo-traces
        endpoint: minio.minio.svc:9000
        access_key: MINIO_ACCESS_KEY
        secret_key: MINIO_SECRET_KEY
        insecure: true

traces:
  otlp:
    grpc:
      enabled: true

tempoQuery:
  enabled: true
  service:
    type: LoadBalancer
EOF
```

## Acesso Jaeger UI

### Port Forward (Desenvolvimento)

```bash
# Jaeger
kubectl port-forward -n observability svc/jaeger-query 16686:16686
# Acessar: http://localhost:16686

# Tempo Query
kubectl port-forward -n observability svc/tempo-query 16686:3200
# Acessar: http://localhost:16686
```

### Service (Produção)

```bash
# Obter URL
kubectl get svc -n observability jaeger-query
# ou
kubectl get svc -n observability tempo-query
```

## Formato W3C Traceparent

### Headers de Propagação

```
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
             ^^ ^^^^^^^^^^^^^^^^^^^^^^^ ^^^^^^^^^^^^^^^ ^^
             ||         trace-id          span-id        flags
             ||-version (00 = W3C standard)
```

### Headers Neural Hive

```
x-neural-hive-intent-id: <uuid>
x-neural-hive-plan-id: <uuid>
x-neural-hive-user-id: <user_id>
x-neural-hive-component: ste|consensus|orchestrator|worker
baggage: neural.hive.intent.id=<uuid>,neural.hive.plan.id=<uuid>
```

## Busca de Traces

### Por ID de Correlação

```
1. No Jaeger UI, buscar por:
   - trace ID (W3C format)
   - intent ID (tag: neural.hive.intent.id)
   - plan ID (tag: neural.hive.plan.id)

2. Filtrar por:
   - Service: semantic-translation-engine
   - Operation: create_cognitive_plan
   - Tags: neural.hive.component=ste
```

### Por Intervalo de Tempo

```
1. Selecionar "Search"
2. Definir intervalo (Last Hour, Last Day)
3. Filtrar por operações:
   - process_intent (Gateway)
   - create_cognitive_plan (STE)
   - process_consensus (Consensus Engine)
   - generate_tickets (Orchestrator)
```

## Serviços e Operações

### Serviços Mapeados

| Service Name | Component | Layer |
|-------------|-----------|-------|
| gateway-intencoes | gateway | api |
| semantic-translation-engine | ste | cognitive-pipeline |
| consensus-engine | consensus | cognitive-pipeline |
| orchestrator-dynamic | orchestrator | orchestration |
| worker-agents | worker | execution |
| approval-service | approval | governance |

### Operações Principais

| Operação | Descrição |
|----------|-----------|
| process_intent | Processa intenção do usuário |
| create_cognitive_plan | Gera plano cognitivo |
| process_consensus | Avaliação por especialistas |
| generate_tickets | Gera tickets de execução |
| execute_ticket | Executa ticket individual |
| approve_plan | Aprovação manual |
| compensate_execution | Compensação Saga |

## Troubleshooting

### Sem Traces Aparecendo

```bash
# Verificar se collector está recebendo
kubectl logs -n observability jaeger-collector -f

# Verificar se serviços estão exportando
kubectl logs -l app=semantic-translation-engine --tail=100 | grep -i trace

# Testar conectividade
kubectl run -it --rm debug --image=curlimages/curl --restart=Never \
  -- curl -v http://jaeger-collector.observability:4317
```

### Spans Faltando

```python
# Verificar se tracing está inicializado
from neural_hive_observability.tracing import get_tracer
tracer = get_tracer()
if not tracer:
    logger.error("Tracer não inicializado!")
```

### Headers não propagados

```bash
# Verificar headers na mensagem Kafka
kubectl exec -it kafka-0 -- kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic plans.ready \
  --from-beginning \
  --property print.headers=true
```

## Métricas de Telemetria

### Taxa de Amostragem

```python
# Configurar sampling (produção)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource

# Sample 10% dos traces em produção
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
sampling_strategy = TraceIdRatioBased(0.1)

tracer_provider = TracerProvider(
    resource=Resource.create({"service.name": "my-service"}),
    sampler=sampling_strategy
)
```

## Links Úteis

- [OpenTelemetry Python](https://opentelemetry.io/docs/instrumentation/python/)
- [Jaeger Docs](https://www.jaegertracing.io/docs/)
- [Grafana Tempo](https://grafana.com/docs/tempo/)
- [W3C Trace Context](https://www.w3.org/TR/trace-context/)
