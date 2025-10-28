# ADR-0007: OpenTelemetry Instrumentation Strategy

## Status
Accepted

## Context

O Neural Hive-Mind necessita de instrumentação consistente para observabilidade distribuída. Conforme documento-05-implementacao-e-operacao-neural-hive-mind.md seção 5, precisamos implementar:

- Correlação distribuída por intent_id e plan_id através de todos os serviços
- Instrumentação padronizada para métricas, logs e traces
- Coleta de telemetria com baixo overhead (<2% CPU/memoria)
- Sampling strategies otimizadas para diferentes environments
- Integração transparente com múltiplos backends

## Decision

Adotamos **OpenTelemetry como padrão unificado** para instrumentação de observabilidade, com estratégia híbrida de **instrumentação automática + manual + bibliotecas customizadas**.

### Estratégia de Instrumentação:

1. **Instrumentação Automática**: Para frameworks comuns (FastAPI, SQLAlchemy, Redis, Kafka)
2. **Instrumentação Manual**: Para lógica de negócio específica e correlação custom
3. **Bibliotecas Customizadas**: neural_hive_observability para patterns específicos do domínio

### Componentes:

- **OpenTelemetry SDK**: Core instrumentation
- **OpenTelemetry Collector**: Coleta e processamento centralizado
- **Custom Instrumentation Library**: neural_hive_observability
- **Context Propagation**: intent_id, plan_id, domain context

## Alternatives Considered

### 1. Instrumentação Nativa de Cada Backend
- **Pros**: Integração otimizada, features específicas
- **Cons**: Vendor lock-in, inconsistência, múltiplas bibliotecas
- **Decisão**: Rejeitado pela fragmentação

### 2. Jaeger Client Libraries
- **Pros**: Mature, estável, integração Jaeger nativa
- **Cons**: Tracing only, não suporta métricas/logs, migração futura difícil
- **Decisão**: Rejeitado pela limitação de escopo

### 3. Prometheus Client + Custom Tracing
- **Pros**: Controle total, otimização específica
- **Cons**: Desenvolvimento custom extenso, falta de padronização
- **Decisão**: Rejeitado pela complexidade de manutenção

### 4. Application Performance Monitoring (APM) Agents
- **Pros**: Zero-code instrumentation, AI insights
- **Cons**: Vendor lock-in, overhead, limitações de customização
- **Decisão**: Rejeitado pelos requisitos de correlação custom

## Rationale

### Fatores de Decisão:

1. **Vendor Neutrality**: OpenTelemetry é padrão da indústria, vendor-neutral
2. **Padronização**: API consistente para todos os tipos de telemetria
3. **Correlação Distribuída**: Suporte nativo para context propagation
4. **Extensibilidade**: Permite instrumentação custom para lógica específica
5. **Multi-Backend**: Single SDK, múltiplos exporters (Prometheus, Jaeger, etc)
6. **Future-Proof**: Migração de backends transparente para aplicações
7. **Performance**: Sampling, batching e filtering avançados

### Alinhamento com Requisitos:

Conforme documento-05-implementacao-e-operacao-neural-hive-mind.md:
- ✅ **Observabilidade Holística**: Métricas + Logs + Traces unificados
- ✅ **Correlação**: Context propagation para intent_id/plan_id
- ✅ **Performance**: Overhead <2% via sampling otimizado
- ✅ **Integração**: Suporte nativo para Kubernetes/Istio

## Consequences

### Positive:
- Instrumentação unificada e consistente entre serviços
- Correlação automática por intent_id/plan_id
- Flexibilidade para mudança de backends sem re-instrumentação
- Redução de overhead via sampling strategies avançadas
- Comunidade ativa e roadmap claro
- Suporte nativo para service mesh e Kubernetes

### Negative:
- Curva de aprendizado para desenvolvedores
- API ainda em evolução (algumas features experimental)
- Necessidade de configuração mais detalhada
- Debugging de instrumentação pode ser complexo

### Risks:
- **Risco de Overhead**: Instrumentação pode impactar performance
  - *Mitigação*: Sampling strategies, resource limits, profiling
- **Risco de Complexidade**: Configuração incorreta pode gerar ruído
  - *Mitigação*: Bibliotecas padronizadas, templates, validação
- **Risco de Evolução**: API changes em versões futuras
  - *Mitigação*: Versionamento cuidadoso, testing extensivo

## Implementation Strategy

### 1. Instrumentação Automática
```python
# Via auto-instrumentation packages
opentelemetry-instrumentation-fastapi
opentelemetry-instrumentation-sqlalchemy
opentelemetry-instrumentation-redis
opentelemetry-instrumentation-kafka-python
```

### 2. Instrumentação Manual
```python
# Para lógica de negócio específica
@trace_intent
def process_intention(intent_id: str):
    with tracer.start_as_current_span("process_intention") as span:
        span.set_attribute("intent.id", intent_id)
        span.set_attribute("domain", get_domain())
```

### 3. Políticas de Sampling

#### Desenvolvimento:
- **Trace Sampling**: 100% (debugging completo)
- **Metrics**: Todas as métricas
- **Logs**: DEBUG level

#### Staging:
- **Trace Sampling**: 10% (performance + debugging)
- **Metrics**: Todas as métricas
- **Logs**: INFO level

#### Produção:
- **Trace Sampling**: 1% normal, 100% para errors
- **Head-based Sampling**: Por endpoint criticality
- **Tail-based Sampling**: Por latência e errors
- **Metrics**: Otimizadas por cardinality
- **Logs**: WARN level

### 4. Context Propagation Strategy

```python
# Context keys padronizados
INTENT_ID_KEY = "neural.hive.intent.id"
PLAN_ID_KEY = "neural.hive.plan.id"
DOMAIN_KEY = "neural.hive.domain"
USER_ID_KEY = "neural.hive.user.id"

# Propagação automática via baggage
baggage.set_baggage(INTENT_ID_KEY, intent_id)
baggage.set_baggage(PLAN_ID_KEY, plan_id)
```

### 5. Resource Semantics

```yaml
# Semantic conventions customizadas
resource.attributes:
  service.name: "gateway-intencoes"
  service.version: "${APP_VERSION}"
  service.instance.id: "${HOSTNAME}"
  neural.hive.component: "captura"
  neural.hive.layer: "experiencia"
```

## Monitoring da Instrumentação

### SLOs para Instrumentação:
- **Overhead de CPU**: <2% por serviço
- **Overhead de Memória**: <100MB por serviço
- **Sampling Accuracy**: >95% de traces críticos
- **Context Propagation**: 100% para intent_id/plan_id
- **Telemetry Delivery**: >99.5% success rate

### Alertas:
- Alto overhead de instrumentação
- Context propagation failures
- Sampling bias detectado
- Telemetry delivery failures

## References

- documento-05-implementacao-e-operacao-neural-hive-mind.md - Seção 5 Observabilidade
- OpenTelemetry Specification: https://opentelemetry.io/docs/specs/
- OpenTelemetry Python: https://opentelemetry-python.readthedocs.io/
- Sampling Strategies: https://opentelemetry.io/docs/concepts/sampling/