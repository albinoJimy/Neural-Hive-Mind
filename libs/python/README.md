# Neural Hive-Mind Metrics Library

Biblioteca Python para métricas com suporte a exemplars e correlação distribuída, especificamente projetada para o ecossistema Neural Hive-Mind.

## Características

- **Suporte a Exemplars**: Correlação automática entre métricas e traces
- **Correlação Distribuída**: Rastreamento de intenções, planos e contexto através dos componentes
- **SLOs Integrados**: Monitoramento automático de objetivos de nível de serviço
- **Métricas por Camada**: Classes especializadas para cada camada do Neural Hive-Mind
- **OpenTelemetry Ready**: Integração nativa com OpenTelemetry e Prometheus

## Instalação

```bash
pip install neural-hive-metrics
```

### Dependências Opcionais

```bash
# Para FastAPI
pip install neural-hive-metrics[fastapi]

# Para Flask
pip install neural-hive-metrics[flask]

# Para Django
pip install neural-hive-metrics[django]

# Para desenvolvimento
pip install neural-hive-metrics[dev]
```

## Uso Básico

### Configuração

```python
from neural_hive_metrics import configure_metrics, MetricsConfig

# Configuração básica
config = MetricsConfig(
    service_name="neural-hive-gateway",
    environment="production",
    enable_exemplars=True,
    enable_correlation=True,
)

configure_metrics(config)
```

### Métricas por Camada

#### Camada de Experiência

```python
from neural_hive_metrics import ExperienciaMetrics

metrics = ExperienciaMetrics()

# Registrar captura de intenção
metrics.record_intent_capture(
    channel="web",
    intent_type="search",
    success=True,
    duration=0.15,  # 150ms
    confidence_score=0.95,
    labels={"user_id": "user-123"}
)

# Usar decorator para timing automático
@metrics.time_function("process_user_input")
def process_user_input(user_input):
    # Processamento da entrada do usuário
    pass
```

#### Camada de Cognição

```python
from neural_hive_metrics import CognicaoMetrics

metrics = CognicaoMetrics()

# Context manager para operações
with metrics.time_operation("plan_generation"):
    # Gerar plano cognitivo
    plan = generate_plan(intent)

metrics.record_plan_generation(
    intent_id="intent-456",
    plan_complexity="medium",
    success=True,
    duration=0.08,  # 80ms
)
```

#### Camada de Orquestração

```python
from neural_hive_metrics import OrquestracaoMetrics

metrics = OrquestracaoMetrics()

metrics.record_workflow_execution(
    workflow_id="wf-789",
    workflow_type="data_processing",
    success=True,
    duration=2.5,
    steps_count=5,
)
```

### Correlação Distribuída

#### Configuração de Headers

```python
from neural_hive_metrics import CorrelationContext, trace_correlation

# Definir contexto manualmente
context = CorrelationContext(
    intent_id="intent-123",
    plan_id="plan-456",
    domain="experiencia",
    user_id="user-789",
)

# Usar decorator para correlação automática
@trace_correlation(domain="cognicao", intent_id="intent-123")
def cognitive_process():
    # Processamento cognitivo com correlação
    pass
```

#### Middleware para Web Frameworks

```python
# Flask
from neural_hive_metrics.correlation import create_correlation_middleware

app = Flask(__name__)
correlation_middleware = create_correlation_middleware("flask")

@app.before_request
def before_request():
    correlation_middleware()

# FastAPI
from fastapi import FastAPI
from neural_hive_metrics.correlation import create_correlation_middleware

app = FastAPI()
correlation_middleware = create_correlation_middleware("fastapi")
app.middleware("http")(correlation_middleware)
```

### Exemplars Automáticos

```python
from neural_hive_metrics import create_exemplar_from_current_context

# Criar exemplar com contexto atual de trace
exemplar = create_exemplar_from_current_context(
    metric_name="neural_hive_requests_total",
    value=1.0,
    labels={"method": "POST", "endpoint": "/api/intents"},
)
```

## Configuração Avançada

### Configuração via Variáveis de Ambiente

```bash
# Configurações básicas
export NEURAL_HIVE_SERVICE_NAME="neural-hive-gateway"
export NEURAL_HIVE_ENVIRONMENT="production"
export METRICS_PORT=8080

# Exemplars e correlação
export ENABLE_EXEMPLARS=true
export ENABLE_CORRELATION=true
export EXEMPLAR_SAMPLE_RATE=1.0

# Endpoints
export PROMETHEUS_PUSHGATEWAY_URL="http://prometheus-pushgateway:9091"
export OTEL_EXPORTER_OTLP_ENDPOINT="http://opentelemetry-collector:4317"
export JAEGER_AGENT_HOST="jaeger-agent"

# Headers customizados
export CORRELATION_HEADER_INTENT_ID="X-Neural-Hive-Intent-ID"
export CORRELATION_HEADER_PLAN_ID="X-Neural-Hive-Plan-ID"
```

### Configuração via Arquivo

```yaml
# config.yaml
service_name: "neural-hive-cognicao"
service_version: "2.1.0"
environment: "production"
enable_exemplars: true
enable_correlation: true
exemplar_sample_rate: 0.5

correlation_headers:
  intent_id: "X-Neural-Hive-Intent-ID"
  plan_id: "X-Neural-Hive-Plan-ID"
  domain: "X-Neural-Hive-Domain"
  user_id: "X-Neural-Hive-User-ID"

neural_hive_config:
  slo_targets:
    barramento_latency_ms: 150
    availability_percent: 99.9
    plan_generation_ms: 120
    capture_latency_ms: 200
```

```python
from neural_hive_metrics import MetricsConfig

config = MetricsConfig.from_file("config.yaml")
configure_metrics(config)
```

## SLOs e Alerting

### Validação Automática de SLOs

```python
from neural_hive_metrics import BarramentoMetrics

metrics = BarramentoMetrics()

# Esta métrica será automaticamente validada contra SLO de 150ms
metrics.record_message_routing(
    source_component="experiencia",
    target_component="cognicao",
    message_type="intent",
    success=True,
    duration=0.08,  # 80ms - dentro do SLO
)
```

### Métricas de SLO Geradas

A biblioteca gera automaticamente métricas para monitoramento de SLOs:

- `neural_hive_slo_latency_target`
- `neural_hive_slo_availability_target`
- `neural_hive_slo_error_budget_remaining`
- `neural_hive_slo_burn_rate`

## Integração com OpenTelemetry

### Configuração Completa

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

from neural_hive_metrics import configure_metrics, MetricsConfig

# Configurar OpenTelemetry
trace.set_tracer_provider(TracerProvider())
tracer = trace.get_tracer(__name__)

otlp_exporter = OTLPSpanExporter(endpoint="http://opentelemetry-collector:4317")
span_processor = BatchSpanProcessor(otlp_exporter)
trace.get_tracer_provider().add_span_processor(span_processor)

# Configurar métricas
config = MetricsConfig(
    service_name="neural-hive-service",
    otel_exporter_otlp_endpoint="http://opentelemetry-collector:4317",
    enable_exemplars=True,
)
configure_metrics(config)
```

### Uso com Traces

```python
from neural_hive_metrics import NeuralHiveMetrics

metrics = NeuralHiveMetrics()

with tracer.start_as_current_span("process_request") as span:
    # Métricas criadas aqui terão exemplars com trace_id/span_id
    metrics.record_request(
        method="POST",
        endpoint="/api/process",
        status_code=200,
        duration=0.25,
    )
```

## Monitoramento e Debugging

### Estatísticas do Coletor

```python
from neural_hive_metrics.exemplars import get_exemplar_collector

collector = get_exemplar_collector()
stats = collector.get_stats()
print(f"Total de exemplars: {stats['total_exemplars']}")
print(f"Métricas com exemplars: {stats['metrics_with_exemplars']}")
```

### Limpeza de Exemplars

```python
# Limpar exemplars expirados
collector.cleanup_expired()

# Limpar todos os exemplars
collector.clear_exemplars()

# Limpar exemplars de métrica específica
collector.clear_exemplars("neural_hive_requests_total")
```

## Exemplos Completos

### Serviço Neural Hive-Mind

```python
from flask import Flask, request
from neural_hive_metrics import (
    configure_metrics, MetricsConfig, ExperienciaMetrics,
    extract_correlation_from_request, with_correlation
)

app = Flask(__name__)

# Configurar métricas
config = MetricsConfig(
    service_name="neural-hive-gateway",
    environment="production",
    enable_exemplars=True,
    enable_correlation=True,
)
configure_metrics(config)

metrics = ExperienciaMetrics()

@app.before_request
def before_request():
    # Extrair correlação do request
    context = extract_correlation_from_request(request)
    if not context.is_empty():
        request.correlation_context = context

@app.route('/api/intents', methods=['POST'])
def create_intent():
    context = getattr(request, 'correlation_context', None)

    with with_correlation(context) if context else nullcontext():
        with metrics.time_operation("intent_creation"):
            # Processar intenção
            intent = process_intent(request.json)

            metrics.record_intent_capture(
                channel="api",
                intent_type=intent.type,
                success=True,
                duration=0.12,
                confidence_score=intent.confidence,
            )

            return {"intent_id": intent.id}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
```

## Contribuição

Para contribuir com a biblioteca:

1. Fork o repositório
2. Crie uma branch para sua feature (`git checkout -b feature/nova-funcionalidade`)
3. Faça commit das mudanças (`git commit -am 'Adiciona nova funcionalidade'`)
4. Push para a branch (`git push origin feature/nova-funcionalidade`)
5. Crie um Pull Request

## Licença

MIT License - veja o arquivo [LICENSE](LICENSE) para detalhes.

## Suporte

- **Documentação**: [docs.neural-hive.local/metrics](https://docs.neural-hive.local/metrics)
- **Issues**: [GitHub Issues](https://github.com/neural-hive-mind/metrics/issues)
- **Discussões**: [GitHub Discussions](https://github.com/neural-hive-mind/metrics/discussions)