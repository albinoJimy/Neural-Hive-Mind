# OpenTelemetry Tracing Guide

Este guia documenta a configuração de tracing distribuído via OpenTelemetry no Neural-Hive-Mind.

## Visão Geral

O Neural-Hive-Mind utiliza OpenTelemetry para tracing distribuído, permitindo rastrear requisições através de todos os componentes do sistema. A biblioteca `neural_hive_observability` fornece a implementação base que é utilizada por todos os serviços.

### Fluxo de Traces

```
User Request
     │
     ▼
┌─────────────────────┐
│  Gateway Intencoes  │  ← Cria span raiz com trace_id
└─────────┬───────────┘
          │ Kafka (trace_id no header)
          ▼
┌─────────────────────────────┐
│ Semantic Translation Engine │  ← Extrai trace_id, cria spans filhos
└─────────┬───────────────────┘
          │ Kafka + gRPC
          ▼
┌─────────────────────┐
│    Specialists      │  ← Propagam trace_id via gRPC metadata
│ (business, tech,    │
│  architecture,      │
│  behavior,          │
│  evolution)         │
└─────────┬───────────┘
          │ gRPC
          ▼
┌─────────────────────┐
│  Consensus Engine   │  ← Agrega traces, finaliza span
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  OTLP Collector     │  → Jaeger UI
└─────────────────────┘
```

## Configuração por Serviço

### Specialists (business, technical, architecture, behavior, evolution)

Os specialists usam variáveis de ambiente diretas no deployment:

```yaml
# values.yaml
config:
  features:
    enableTracing: true  # Produção
    # enableTracing: false  # Local (values-local.yaml)
```

A variável é injetada no container via `ENABLE_TRACING` no deployment.yaml.

### Consensus Engine

O consensus-engine usa ConfigMap para configuração:

```yaml
# values.yaml
config:
  features:
    enableTracing: true
```

A variável `ENABLE_TRACING` é incluída no ConfigMap.

### Semantic Translation Engine

Similar ao consensus-engine, usa ConfigMap:

```yaml
# values.yaml
config:
  features:
    enableTracing: true
```

### Gateway Intencoes

O gateway usa a seção `observability`:

```yaml
# values.yaml
observability:
  tracing:
    enabled: true
```

## Variáveis de Ambiente

| Variável | Descrição | Valor Padrão |
|----------|-----------|--------------|
| `ENABLE_TRACING` | Feature flag principal (true/false) | `true` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Endpoint do OTLP Collector | `http://opentelemetry-collector.observability.svc.cluster.local:4317` |
| `OTEL_SAMPLING_RATE` | Taxa de amostragem (0.0 a 1.0) | `1.0` |
| `TRACE_BATCH_SIZE` | Tamanho do batch de exportação | `512` |
| `TRACE_EXPORT_TIMEOUT_MS` | Timeout de exportação (ms) | `30000` |

## Validação

### Verificar Logs de Inicialização

```bash
# Verificar se tracing foi inicializado
kubectl logs -n neural-hive deployment/semantic-translation-engine | grep -i "tracing"

# Verificar em specialist
kubectl logs -n neural-hive deployment/specialist-business | grep -i "Tracing inicializado"
```

### Acessar Jaeger UI

```bash
# Port-forward para Jaeger
kubectl port-forward -n observability svc/jaeger-query 16686:16686

# Acessar http://localhost:16686
```

### Buscar Traces

No Jaeger UI, você pode buscar traces por:

- **Service**: Selecione o serviço (semantic-translation-engine, specialist-business, etc.)
- **Tags**: Use tags específicas do Neural Hive Mind:
  - `neural.hive.intent.id=<intent_id>`
  - `neural.hive.plan.id=<plan_id>`
  - `neural.hive.component=business-specialist`

## Atributos Customizados

Os serviços do Neural Hive Mind adicionam atributos específicos aos spans:

| Atributo | Descrição | Exemplo |
|----------|-----------|---------|
| `neural.hive.intent.id` | ID da intenção | `int_abc123` |
| `neural.hive.plan.id` | ID do plano cognitivo | `plan_xyz789` |
| `neural.hive.component` | Componente do sistema | `business-specialist`, `consensus-aggregator` |
| `neural.hive.layer` | Camada da arquitetura | `cognitiva` |
| `neural.hive.domain` | Domínio de negócio | `business-analysis`, `consensus` |
| `neural.hive.correlation.id` | ID de correlação | `corr_123456` |

## Exemplos de Queries no Jaeger

### Buscar todos os traces de uma intenção

```
Tags: neural.hive.intent.id=<intent_id>
```

### Buscar traces de um specialist específico

```
Service: specialist-business
Tags: neural.hive.component=business-specialist
```

### Buscar traces com erros

```
Tags: error=true
```

### Buscar traces por plan_id

```
Tags: neural.hive.plan.id=<plan_id>
```

### Buscar traces lentos (>5s)

```
Min Duration: 5s
Service: semantic-translation-engine
```

## Troubleshooting

### Traces não aparecem no Jaeger

1. **Verificar se ENABLE_TRACING está ativo:**
   ```bash
   kubectl get configmap semantic-translation-engine-config -o yaml | grep ENABLE_TRACING
   ```

2. **Verificar se o collector está rodando:**
   ```bash
   kubectl get pods -n observability -l app=opentelemetry-collector
   ```

3. **Verificar logs do exporter:**
   ```bash
   kubectl logs -n neural-hive deployment/semantic-translation-engine | grep -i "otel\|export"
   ```

4. **Verificar conectividade com o collector:**
   ```bash
   kubectl exec -it -n neural-hive deployment/semantic-translation-engine -- curl -s http://opentelemetry-collector.observability.svc.cluster.local:4317
   ```

### Performance degradada

Se o tracing está impactando performance:

1. **Reduzir taxa de amostragem:**
   ```yaml
   config:
     openTelemetry:
       samplingRate: 0.1  # 10% dos traces
   ```

2. **Aumentar batch size:**
   ```yaml
   config:
     openTelemetry:
       batchSize: 1024
   ```

3. **Desabilitar em ambiente local:**
   ```yaml
   # values-local.yaml
   config:
     features:
       enableTracing: false
   ```

### Timeout de exportação

Se traces estão sendo perdidos por timeout:

1. **Aumentar timeout de exportação:**
   ```yaml
   config:
     openTelemetry:
       exportTimeoutMs: 60000  # 60 segundos
   ```

2. **Verificar latência para o collector:**
   ```bash
   kubectl exec -it -n neural-hive deployment/semantic-translation-engine -- time curl http://opentelemetry-collector.observability.svc.cluster.local:4317
   ```

## Recomendações por Ambiente

### Desenvolvimento/Local

```yaml
# values-local.yaml
config:
  features:
    enableTracing: false  # Desabilitado para reduzir overhead
```

### Staging

```yaml
# values-staging.yaml
config:
  features:
    enableTracing: true
  openTelemetry:
    samplingRate: 0.1  # 10% dos traces
```

### Produção

```yaml
# values.yaml (default)
config:
  features:
    enableTracing: true
  openTelemetry:
    samplingRate: 1.0  # 100% inicialmente para debugging
    # Após estabilização, reduzir para 0.01-0.1
```

## Integração com Jaeger

Os traces são enviados via protocolo OTLP para o OpenTelemetry Collector, que então exporta para o Jaeger:

```
┌─────────────┐     OTLP/gRPC     ┌────────────────────┐     Jaeger     ┌─────────┐
│   Serviço   │  ───────────────► │  OTEL Collector    │  ───────────► │  Jaeger │
│ (specialist,│                   │  (observability)   │                │   UI    │
│  consensus, │                   └────────────────────┘                └─────────┘
│  ste, etc)  │
└─────────────┘
```

### Configuração do Collector

O OpenTelemetry Collector está configurado com:

- **Receivers**: OTLP (gRPC porta 4317, HTTP porta 4318)
- **Processors**: batch, memory_limiter
- **Exporters**: Jaeger (thrift_http)

## Referências

- [OpenTelemetry Python SDK](https://opentelemetry.io/docs/instrumentation/python/)
- [Jaeger Documentation](https://www.jaegertracing.io/docs/)
- [OpenTelemetry Collector](https://opentelemetry.io/docs/collector/)
- [libraries/python/neural_hive_observability/tracing.py](../libraries/python/neural_hive_observability/tracing.py)
- [libraries/python/neural_hive_specialists/config.py](../libraries/python/neural_hive_specialists/config.py)
