# Neural Hive Observability

Biblioteca de observabilidade padronizada para o Neural Hive-Mind.

## Recursos

- Tracing distribuído com OpenTelemetry
- Métricas Prometheus padronizadas
- Correlação automática por intent_id e plan_id
- Health checks configuráveis
- Instrumentação gRPC e Kafka

## Instalação

```bash
pip install -e libraries/python/neural_hive_observability
```

## Uso Básico

```python
from neural_hive_observability import init_observability, trace_intent

# Inicializar observabilidade
init_observability(
    service_name="meu-servico",
    service_version="1.0.0",
    neural_hive_component="gateway",
    neural_hive_layer="experiencia"
)

# Usar decorators de tracing
@trace_intent(extract_intent_id_from="intent_id")
def processar_intencao(intent_id: str, dados: dict):
    return {"status": "processado"}
```

## Problemas Conhecidos

### Bug do OpenTelemetry 1.39.1 (TypeError durante export de spans)

**Versões afetadas**: OpenTelemetry SDK 1.39.1, 1.39.0

**Sintoma**: Erro `TypeError: not all arguments converted during string formatting` nos logs durante export de spans para o OTLP collector.

**Causa**: Bug no `OTLPSpanExporter` relacionado à formatação de strings em headers customizados quando contêm caracteres especiais como `%`, `{`, `}`.

**Solução implementada**:
Esta biblioteca implementa um `ResilientOTLPSpanExporter` que:
1. Sanitiza valores de headers antes de passá-los ao exporter
2. Captura exceções durante export sem bloquear operações principais
3. Registra métricas de falhas para monitoramento

```python
# O wrapper é usado automaticamente em init_tracing()
# Nenhuma configuração adicional é necessária
```

**Referência**: https://github.com/open-telemetry/opentelemetry-python/issues/4492

### Caracteres Problemáticos em Headers

Os seguintes caracteres são automaticamente removidos dos valores de headers:
- `%` (causa formatação de string incorreta)
- `{` e `}` (podem causar problemas de parsing)
- `\n`, `\r`, `\t` (quebras de linha e tabs)
- `\x00` (caractere nulo)

## Métricas Disponíveis

### Métricas de Export de Spans

| Métrica | Tipo | Descrição |
|---------|------|-----------|
| `neural_hive_span_export_failures_total` | Counter | Total de falhas no export de spans |
| `neural_hive_span_export_success_total` | Counter | Total de exports bem-sucedidos |
| `neural_hive_span_export_duration_seconds` | Histogram | Duração do export em segundos |
| `neural_hive_span_export_queue_size` | Gauge | Tamanho da fila de spans pendentes |

### Consultas PromQL de Exemplo

```promql
# Taxa de falhas de export nos últimos 5 minutos
rate(neural_hive_span_export_failures_total[5m])

# Percentil 95 da duração de export
histogram_quantile(0.95, rate(neural_hive_span_export_duration_seconds_bucket[5m]))
```

## Configuração Recomendada

```python
from neural_hive_observability import init_observability

init_observability(
    service_name="meu-servico",
    service_version="1.0.0",
    neural_hive_component="gateway",
    neural_hive_layer="experiencia",
    otel_endpoint="http://otel-collector:4317",
    prometheus_port=8080,
    enable_health_checks=True,
    trace_batch_size=512,
    trace_export_timeout_ms=30000,
    trace_schedule_delay_ms=5000
)
```

## Plano de Atualização

Quando o bug for corrigido em uma versão futura do OpenTelemetry (provavelmente 1.40.0+):

1. Atualizar dependências para nova versão
2. Testar em ambiente de desenvolvimento
3. Remover `ResilientOTLPSpanExporter` se não mais necessário
4. Atualizar esta documentação

## Desenvolvimento

### Executar Testes

```bash
cd libraries/python/neural_hive_observability
pytest tests/ -v
```

### Estrutura do Projeto

```
neural_hive_observability/
├── __init__.py          # Exports principais
├── config.py            # Configuração
├── tracing.py           # Tracing distribuído
├── metrics.py           # Métricas Prometheus
├── exporters.py         # Exporters resilientes (NEW)
├── health.py            # Health checks
├── context.py           # Context management
├── grpc_instrumentation.py  # Instrumentação gRPC
└── kafka_instrumentation.py # Instrumentação Kafka
```
