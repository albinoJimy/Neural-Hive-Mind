# Guia de Distributed Tracing - Neural Hive Mind

## Visão Geral

Este documento descreve a implementação de **distributed tracing** com OpenTelemetry nos especialistas neurais do Neural Hive Mind. O tracing distribuído permite rastreamento end-to-end de avaliações de planos cognitivos através de múltiplos serviços.

## Arquitetura

### Fluxo de Tracing

```
Gateway → Consensus Engine → gRPC Server → BaseSpecialist
    │            │                │              │
    └────────────┴────────────────┴──────────────┘
                         ↓
           OpenTelemetry Collector
                         ↓
                 Jaeger / Tempo
```

### Componentes Instrumentados

1. **gRPC Server**: Instrumentação automática via `GrpcInstrumentorServer`
2. **BaseSpecialist**: Spans manuais para cada etapa de avaliação
3. **MLflowClient**: Spans para operações de carregamento de modelo
4. **LedgerClient**: Spans para persistência de opiniões
5. **ExplainabilityGenerator**: Spans para geração de explicabilidade
6. **FeatureExtractor**: Spans para extração de features
7. **ComplianceLayer**: Spans para sanitização de PII e criptografia

## Hierarquia de Spans

```
grpc.EvaluatePlan (auto-instrumentado)
└── specialist.evaluate_plan (root span manual)
    ├── specialist.deserialize_plan
    ├── specialist.check_cache
    ├── compliance.sanitize_plan
    │   └── compliance.pii_detection
    ├── mlflow.load_model
    │   └── mlflow.get_model_metadata
    ├── feature_extraction.extract_features
    │   ├── feature_extraction.metadata
    │   ├── feature_extraction.ontology
    │   ├── feature_extraction.graph
    │   └── feature_extraction.embeddings
    ├── specialist.predict_with_model
    ├── specialist.validate_result
    ├── explainability.generate
    │   ├── explainability.extract_shap
    │   ├── explainability.extract_lime
    │   └── explainability.generate_narrative
    ├── ledger.save_opinion
    │   └── ledger.persist_document
    └── specialist.cache_result
```

## Configuração

### Variáveis de Ambiente

```bash
# Habilitar tracing
ENABLE_TRACING=true

# Endpoint do OpenTelemetry Collector
OTEL_ENDPOINT=http://opentelemetry-collector:4317

# Conexão insegura (desenvolvimento)
OTEL_INSECURE=true

# Taxa de amostragem (0.0 a 1.0)
TRACE_SAMPLING_RATE=1.0

# Configuração de batch
TRACE_BATCH_SIZE=512
TRACE_EXPORT_TIMEOUT_MS=30000

# Spans detalhados
ENABLE_DETAILED_SPANS=true
SPAN_INCLUDE_PLAN_CONTENT=false
SPAN_INCLUDE_MODEL_PREDICTIONS=true
```

### Exemplo de Configuração

```python
from neural_hive_specialists.config import SpecialistConfig

config = SpecialistConfig(
    specialist_type='technical',
    service_name='specialist-technical',
    enable_tracing=True,
    otel_endpoint='http://localhost:4317',
    trace_sampling_rate=1.0,
    enable_detailed_spans=True
)
```

## Atributos de Span

### Atributos Padrão (Resource)

| Atributo | Exemplo | Descrição |
|----------|---------|-----------|
| `service.name` | `specialist-technical` | Nome do serviço |
| `service.version` | `1.0.0` | Versão do especialista |
| `neural.hive.component` | `specialist` | Componente do Neural Hive |
| `neural.hive.layer` | `evaluation` | Camada de processamento |
| `neural.hive.domain` | `technical` | Domínio do especialista |
| `deployment.environment` | `production` | Ambiente de deployment |

### Atributos Customizados

#### Span: `specialist.evaluate_plan`

| Atributo | Tipo | Exemplo | Descrição |
|----------|------|---------|-----------|
| `specialist.type` | string | `technical` | Tipo do especialista |
| `specialist.version` | string | `1.0.0` | Versão do especialista |
| `plan.id` | string | `plan-123` | ID do plano cognitivo |
| `intent.id` | string | `intent-456` | ID da intenção original |
| `correlation.id` | string | `corr-789` | ID de correlação |
| `confidence.score` | float | `0.85` | Score de confiança |
| `risk.score` | float | `0.25` | Score de risco |
| `recommendation` | string | `approve` | Recomendação final |
| `processing.time_ms` | int | `1250` | Tempo de processamento |
| `opinion.id` | string | `op-789` | ID da opinião gerada |

#### Span: `specialist.deserialize_plan`

| Atributo | Tipo | Exemplo | Descrição |
|----------|------|---------|-----------|
| `plan.version` | string | `1.0.0` | Versão do plano |
| `plan.tasks_count` | int | `8` | Número de tarefas |

#### Span: `mlflow.load_model`

| Atributo | Tipo | Exemplo | Descrição |
|----------|------|---------|-----------|
| `mlflow.model.name` | string | `technical_classifier` | Nome do modelo |
| `mlflow.model.stage` | string | `Production` | Stage do modelo |
| `mlflow.model.version` | string | `1.2.3` | Versão do modelo |
| `mlflow.cache.hit` | bool | `false` | Cache hit/miss |

#### Span: `explainability.extract_shap`

| Atributo | Tipo | Exemplo | Descrição |
|----------|------|---------|-----------|
| `explainability.method` | string | `shap` | Método de explicabilidade |
| `shap.timeout_seconds` | float | `5.0` | Timeout configurado |
| `shap.features.count` | int | `26` | Número de features |

#### Span: `ledger.save_opinion`

| Atributo | Tipo | Exemplo | Descrição |
|----------|------|---------|-----------|
| `ledger.plan.id` | string | `plan-123` | ID do plano |
| `ledger.opinion.id` | string | `op-789` | ID da opinião |
| `ledger.buffered` | bool | `false` | Opinião bufferizada |
| `ledger.digital_signature.present` | bool | `true` | Assinatura digital presente |

## Uso

### Configurar Jaeger Local

```bash
# Via Docker
docker run -d --name jaeger \
  -p 16686:16686 \
  -p 14268:14268 \
  -p 6831:6831/udp \
  jaegertracing/all-in-one:latest

# Acessar UI
open http://localhost:16686
```

### Executar Especialista com Tracing

```bash
# Configurar variáveis
export ENABLE_TRACING=true
export OTEL_ENDPOINT=http://localhost:14268

# Executar especialista
cd services/specialist-technical
python -m src.main
```

### Buscar Traces no Jaeger

#### Por Plan ID

1. Abrir Jaeger UI: `http://localhost:16686`
2. Selecionar service: `specialist-technical`
3. Buscar por tag: `neural.hive.plan.id=plan-123`

#### Por Intent ID

1. Buscar por tag: `neural.hive.intent.id=intent-456`

#### Por Correlation ID

1. Buscar por tag: `correlation.id=corr-789`

#### Por Erro

1. Filtrar por `Status=error` na busca

### Analisar Performance

#### Identificar Gargalos

1. Ordenar traces por duração (Sort: Longest First)
2. Abrir trace e visualizar flamegraph
3. Identificar spans com maior duração
4. Exemplos comuns:
   - `explainability.extract_shap`: 2-5s (normal)
   - `mlflow.load_model`: 1-3s (primeira carga)
   - `ledger.save_opinion`: 50-200ms (normal)

#### Comparar P50/P95/P99

1. Buscar traces de um período (ex: últimas 24h)
2. Exportar métricas de duração
3. Calcular percentis:
   - P50 (mediana): tempo típico
   - P95: 95% das requisições
   - P99: outliers

## Correlação com Logs

### Adicionar trace_id aos Logs

O BaseSpecialist já extrai automaticamente `trace_id` e `span_id` do OpenTelemetry context e adiciona aos logs:

```python
logger.info(
    "Processing request",
    plan_id=plan_id,
    trace_id=context['trace_id'],
    span_id=context['span_id']
)
```

### Buscar Logs por Trace ID

```bash
# Grep em logs
grep "trace_id=abc123..." /var/log/specialist-technical.log

# Kibana/ElasticSearch
trace_id: "abc123..."

# Loki
{service="specialist-technical"} |= "trace_id=abc123..."
```

## Propagação de Contexto

### gRPC Metadata

O contexto OpenTelemetry é propagado automaticamente via gRPC metadata pelo `GrpcInstrumentorServer`. Não é necessário código manual.

### Propagação para Clientes

O contexto é extraído do OpenTelemetry context em `evaluate_plan`:

```python
if self.tracer:
    current_span = trace.get_current_span()
    if current_span and current_span.get_span_context().is_valid:
        context['trace_id'] = format(current_span.get_span_context().trace_id, "032x")
        context['span_id'] = format(current_span.get_span_context().span_id, "016x")
```

Este contexto é então passado para:
- MLflowClient
- LedgerClient
- ExplainabilityGenerator

## Métricas Derivadas de Traces

### Prometheus + Exemplars

Se configurado, o OpenTelemetry pode exportar métricas com exemplars (referências a traces):

```promql
# Duração de avaliação com exemplar
specialist_evaluation_duration_seconds{specialist_type="technical"} [5m]
```

Clicar no exemplar no Grafana leva diretamente ao trace no Jaeger.

## Performance e Overhead

### Overhead de Tracing

- **Span creation**: ~10-50µs por span
- **Atributos**: ~1-5µs por atributo
- **Exportação**: Assíncrona, não bloqueia

### Otimizações

1. **Sampling em Produção**: Reduzir `TRACE_SAMPLING_RATE` para 0.1 (10%)
2. **Desabilitar spans detalhados**: `ENABLE_DETAILED_SPANS=false`
3. **Não incluir conteúdo do plano**: `SPAN_INCLUDE_PLAN_CONTENT=false` (padrão)

## Fluxo C - Orquestração de Execução

### Arquitetura de Tracing do Fluxo C

```
Gateway → STE → Consensus → Orchestrator Dynamic → Workers
    │       │        │              │                  │
    └───────┴────────┴──────────────┴──────────────────┘
                         ↓
           OpenTelemetry Collector
                         ↓
                 Jaeger / Tempo
```

### Spans do Fluxo C

```
gateway.process_intent
└── ste.generate_plan
    └── consensus.aggregate_opinions
        └── orchestrator.flow_c.execute
            ├── C1.validate_decision
            ├── C2.generate_tickets
            │   ├── opa.validate_policy
            │   ├── ml.predict_duration
            │   └── scheduler.allocate_resources
            ├── C3.discover_workers
            │   └── service_registry.query
            ├── C4.assign_tickets
            │   └── kafka.publish_tickets
            ├── C5.monitor_execution
            │   └── sla.check_budget
            └── C6.publish_telemetry
                └── kafka.publish_telemetry
```

### Atributos Customizados - Fluxo C

| Atributo | Tipo | Exemplo | Descrição |
|----------|------|---------|-----------|
| `neural.hive.flow` | string | `flow_c` | Identificador do fluxo |
| `neural.hive.step` | string | `C2` | Etapa do fluxo (C1-C6) |
| `neural.hive.plan.id` | string | `plan-123` | ID do plano cognitivo |
| `neural.hive.decision.id` | string | `dec-456` | ID da decisão consolidada |
| `neural.hive.workflow.id` | string | `wf-789` | ID do workflow Temporal |
| `neural.hive.tickets.count` | int | `8` | Número de tickets gerados |
| `neural.hive.sla.deadline` | int | `14400000` | Deadline SLA (ms) |
| `neural.hive.sla.budget_remaining` | float | `0.75` | Budget SLA restante (0-1) |

### Configuração por Ambiente

#### Desenvolvimento
```yaml
observability:
  otelEnabled: true
  otelEndpoint: "http://localhost:4317"
  tracingSamplingRate: 1.0  # 100% dos traces
```

#### Staging
```yaml
observability:
  otelEnabled: true
  otelEndpoint: "http://otel-collector.observability.svc.cluster.local:4317"
  tracingSamplingRate: 0.5  # 50% dos traces
```

#### Produção
```yaml
observability:
  otelEnabled: true
  otelEndpoint: "http://otel-collector.observability.svc.cluster.local:4317"
  tracingSamplingRate: 0.1  # 10% dos traces (reduz overhead)
```

## Troubleshooting

### Problema: Traces do Fluxo C incompletos

**Sintomas**: Apenas alguns serviços aparecem no trace, spans C1-C6 faltando

**Verificações**:
1. Verificar que `OTEL_ENABLED=true` em todos os serviços:
   ```bash
   kubectl get pods -n neural-hive -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.containers[0].env[?(@.name=="OTEL_ENABLED")].value}{"\n"}{end}'
   ```

2. Verificar logs de inicialização:
   ```bash
   kubectl logs -n neural-hive gateway-intencoes-xxx | grep "OpenTelemetry"
   kubectl logs -n neural-hive orchestrator-dynamic-xxx | grep "OpenTelemetry"
   ```

3. Verificar propagação de headers Kafka:
   ```bash
   # Consumir mensagem do tópico e verificar headers
   kubectl exec -it kafka-0 -n kafka -- kafka-console-consumer \
     --bootstrap-server localhost:9092 \
     --topic plans.consensus \
     --property print.headers=true \
     --max-messages 1
   ```

**Solução**:
- Habilitar OTEL em todos os serviços
- Verificar que consumers extraem contexto dos headers Kafka
- Reiniciar pods após mudanças de configuração

### Problema: Propagação via Kafka headers não funciona

**Sintomas**: Cada serviço tem trace_id diferente, spans não conectados no Jaeger

**Verificações**:

1. Verificar headers nas mensagens Kafka:
   ```bash
   # Consumir mensagem do tópico intentions.captured
   kubectl exec -it kafka-0 -n kafka -- kafka-console-consumer \
     --bootstrap-server localhost:9092 \
     --topic intentions.captured \
     --property print.headers=true \
     --property print.key=true \
     --max-messages 1
   ```

2. Headers esperados:
   ```
   traceparent:00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
   x-neural-hive-intent-id:intent-123
   x-neural-hive-plan-id:plan-456
   x-neural-hive-user-id:user-789
   correlation-id:corr-abc
   ```

3. Formato W3C traceparent:
   - `00`: Versão
   - `4bf92f35...`: Trace ID (32 hex chars)
   - `00f067aa...`: Span ID (16 hex chars)
   - `01`: Flags (01 = sampled)

4. Verificar que producer injeta headers:
   ```bash
   # Verificar logs do Gateway
   kubectl logs -n neural-hive gateway-intencoes-xxx | grep "traceparent"
   ```

5. Verificar que consumer extrai headers:
   ```bash
   # Verificar logs do STE
   kubectl logs -n neural-hive semantic-translation-engine-xxx | grep "Trace context extraído"
   ```

**Solução**:
- Verificar que producers chamam `instrument_kafka_producer()`
- Verificar que consumers chamam `extract_context_from_headers()`
- Verificar que biblioteca `neural_hive_observability` está instalada
- Reiniciar pods após mudanças

**Exemplo de código correto**:
```python
# Producer
from neural_hive_observability import instrument_kafka_producer
producer = instrument_kafka_producer(producer)

# Consumer
from neural_hive_observability.context import extract_context_from_headers
headers_dict = {k: v.decode('utf-8') if isinstance(v, bytes) else v
                for k, v in (message.headers or [])}
extract_context_from_headers(headers_dict)
```

### Problema: Traces não aparecem no Jaeger

**Sintomas**: Nenhum trace visível na UI do Jaeger

**Verificações**:
1. Verificar `ENABLE_TRACING=true`
2. Verificar conectividade com Collector:
   ```bash
   curl -v http://opentelemetry-collector:4317
   ```
3. Verificar logs do collector:
   ```bash
   kubectl logs -n observability opentelemetry-collector-xxx
   ```
4. Verificar sampling rate não é 0.0

**Solução**: Ajustar configuração e reiniciar especialista

### Problema: Spans sem atributos customizados

**Sintomas**: Spans aparecem mas sem atributos como `confidence.score`

**Verificações**:
1. Verificar `ENABLE_DETAILED_SPANS=true`
2. Verificar versão do OpenTelemetry SDK >= 1.21.0

**Solução**: Atualizar dependências:
```bash
pip install --upgrade opentelemetry-api opentelemetry-sdk
```

### Problema: Contexto não propagado

**Sintomas**: Cada serviço tem trace_id diferente

**Verificações**:
1. Verificar que `GrpcInstrumentorServer` foi chamado
2. Verificar logs de instrumentação:
   ```
   gRPC server instrumented with OpenTelemetry
   ```

**Solução**: Verificar que `enable_tracing=True` antes de criar servidor gRPC

### Problema: Traces muito grandes

**Sintomas**: Exportação lenta, spans truncados

**Verificações**:
1. Verificar número de spans por trace (não deve exceder 100)
2. Verificar tamanho de atributos (evitar incluir conteúdo completo do plano)

**Solução**:
- Desabilitar `SPAN_INCLUDE_PLAN_CONTENT`
- Reduzir número de child spans

## Melhores Práticas

### 1. Sampling Estratégico

**Desenvolvimento**: 100% (todos os traces)
```bash
TRACE_SAMPLING_RATE=1.0
```

**Staging**: 50%
```bash
TRACE_SAMPLING_RATE=0.5
```

**Produção**: 10% (ou menos)
```bash
TRACE_SAMPLING_RATE=0.1
```

### 2. Atributos Customizados

**✅ Fazer**:
- Adicionar IDs relevantes (plan_id, intent_id)
- Adicionar scores e métricas numéricas
- Adicionar flags booleanos (cache.hit, buffered)

**❌ Evitar**:
- Dados sensíveis (PII, credenciais)
- Conteúdo completo do plano (muito grande)
- Dados binários

### 3. Nomenclatura de Spans

**Padrão**: `<componente>.<operação>`

Exemplos:
- `specialist.evaluate_plan`
- `mlflow.load_model`
- `ledger.save_opinion`
- `explainability.extract_shap`

### 4. Tags Padronizadas

Use sempre o prefixo `neural.hive.` para tags customizadas:
- `neural.hive.plan.id`
- `neural.hive.intent.id`
- `neural.hive.specialist.type`

### 5. Correlação com Logs

Sempre incluir `trace_id` nos logs estruturados para correlação.

### 6. Documentação de Spans

Documentar novos spans em:
- Este guia (hierarquia e atributos)
- Código (docstrings)

## Exemplos Práticos - Fluxo C

### Enviar Intenção e Rastrear Trace

```bash
# 1. Enviar intenção
curl -X POST http://gateway-intencoes/intentions \
  -H "Content-Type: application/json" \
  -d '{"text": "Deploy service to prod", "domain": "technical"}'

# Resposta:
# {"intent_id": "intent-123", "traceId": "4bf92f35...", ...}

# 2. Aguardar processamento
sleep 30

# 3. Buscar no Jaeger
open "http://jaeger-ui:16686/search?service=gateway-intencoes&tags={\"neural.hive.intent.id\":\"intent-123\"}"
```

### Verificar Headers Kafka em Mensagens

```bash
# Port-forward para Kafka
kubectl port-forward -n kafka svc/kafka 9092:9092 &

# Consumir mensagem com headers visíveis
kubectl exec -it kafka-0 -n kafka -- kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic plans.consensus \
  --property print.headers=true \
  --max-messages 1

# Output esperado:
# Headers: traceparent:00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01,
#          x-neural-hive-plan-id:plan-123,correlation-id:corr-abc
# Value: {"plan_id":"plan-123",...}
```

### Executar Teste E2E de Tracing

```bash
# Port-forward para Gateway e Jaeger
kubectl port-forward -n neural-hive svc/gateway-intencoes 8000:80 &
kubectl port-forward -n observability svc/jaeger-query 16686:16686 &

# Executar teste com URLs locais
GATEWAY_URL=http://localhost:8000 \
JAEGER_QUERY_URL=http://localhost:16686 \
pytest tests/e2e/tracing/test_flow_c_tracing_e2e.py -v
```

## Referências

### Documentação

- [OpenTelemetry Python](https://opentelemetry.io/docs/instrumentation/python/)
- [OpenTelemetry gRPC Instrumentation](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/grpc/grpc.html)
- [Jaeger](https://www.jaegertracing.io/docs/)
- [Tempo](https://grafana.com/docs/tempo/latest/)

### Código

- `/libraries/python/neural_hive_observability/tracing.py`: Biblioteca base de tracing
- `/libraries/python/neural_hive_specialists/base_specialist.py`: Integração em especialistas
- `/libraries/python/neural_hive_specialists/grpc_server.py`: Instrumentação gRPC

### Exemplos

- `/libraries/python/neural_hive_specialists/tests/test_tracing_integration.py`: Testes de integração
- `/scripts/test_tracing_e2e.py`: Teste end-to-end

## Roadmap

### Funcionalidades Futuras

1. **Trace Exemplars**: Integração com métricas Prometheus
2. **Baggage Propagation**: Propagar metadados via OpenTelemetry Baggage
3. **Tail Sampling**: Sampling inteligente baseado em erros/latência
4. **Trace Analytics**: Dashboards Grafana específicos
5. **Service Graph**: Visualização de dependências entre serviços

### Melhorias Planejadas

1. **Spans Automáticos**: Decorator `@trace_specialist_method`
2. **Context Managers**: `with trace_operation("operation_name")`
3. **Atributos Dinâmicos**: Configuração via arquivo
4. **Filtros de Spans**: Excluir spans de health checks
