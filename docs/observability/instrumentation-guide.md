# Guia de Instrumentação Neural Hive-Mind

## Visão Geral

Este guia detalha como instrumentar serviços no Neural Hive-Mind usando a biblioteca `libraries/python/neural_hive_observability`, garantindo telemetria consistente e correlação completa através dos fluxos operacionais.

## Instalação e Configuração

### Instalação da Biblioteca
```python
# requirements.txt
neural-hive-observability>=1.0.0

# ou via pip
pip install neural-hive-observability
```

### Configuração Base
```python
# app/config.py
from neural_hive_observability import configure_observability

# Configuração automática baseada em variáveis de ambiente
configure_observability(
    service_name="neural-hive-gateway",
    service_version="1.0.0",
    environment="production",
    otlp_endpoint="http://opentelemetry-collector:4318",
    sample_rate=0.1,  # 10% sampling rate
    correlation_headers=["x-neural-hive-intent-id", "x-neural-hive-plan-id"]
)
```

### Variáveis de Ambiente
```bash
# OpenTelemetry
OTEL_SERVICE_NAME=neural-hive-gateway
OTEL_SERVICE_VERSION=1.0.0
OTEL_EXPORTER_OTLP_ENDPOINT=http://opentelemetry-collector:4318
OTEL_RESOURCE_ATTRIBUTES=neural.hive.component=gateway,neural.hive.layer=experiencia

# Neural Hive específico
NEURAL_HIVE_CORRELATION_ENABLED=true
NEURAL_HIVE_METRICS_ENABLED=true
NEURAL_HIVE_TRACES_ENABLED=true
NEURAL_HIVE_LOGS_ENABLED=true
```

## Decoradores de Tracing

### @trace_operation - Operações de Negócio
```python
from neural_hive_observability import trace_operation, get_correlation_context

class IntentCaptureService:
    @trace_operation(
        operation_name="capture_intent",
        layer="experiencia",
        component="intent-capture"
    )
    async def capture_user_intent(self, user_input: str, context: dict):
        # Correlação automática via baggage
        correlation = get_correlation_context()

        # Span attributes automáticos
        # - neural.hive.operation = "capture_intent"
        # - neural.hive.layer = "experiencia"
        # - neural.hive.component = "intent-capture"
        # - neural.hive.intent_id = uuid (se novo)

        try:
            intent = await self._process_intent(user_input)

            # Métricas automáticas
            # neural_hive_operation_duration_seconds{operation="capture_intent"}
            # neural_hive_operation_total{operation="capture_intent",status="success"}

            return intent
        except Exception as e:
            # Error tracking automático
            # neural_hive_operation_total{operation="capture_intent",status="error"}
            # neural_hive_operation_errors_total{operation="capture_intent",error_type="ValidationError"}
            raise
```

### @trace_external_call - Chamadas Externas
```python
from neural_hive_observability import trace_external_call

class LLMService:
    @trace_external_call(
        service_name="openai-gpt4",
        operation="text_generation"
    )
    async def generate_plan(self, prompt: str):
        # Span attributes automáticos
        # - neural.hive.external.service = "openai-gpt4"
        # - neural.hive.external.operation = "text_generation"
        # - http.method = "POST" (se HTTP)
        # - http.status_code = 200 (automático)

        response = await openai_client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}]
        )

        # Métricas automáticas
        # neural_hive_external_duration_seconds{service="openai-gpt4"}
        # neural_hive_external_total{service="openai-gpt4",status="success"}

        return response
```

### @trace_database - Operações de Banco
```python
from neural_hive_observability import trace_database

class PlanRepository:
    @trace_database(
        database_name="postgresql",
        table_name="plans",
        operation="select"
    )
    async def get_plan_by_id(self, plan_id: str):
        # Span attributes automáticos
        # - db.system = "postgresql"
        # - db.name = "neural_hive"
        # - db.operation = "select"
        # - db.statement = SQL (sanitizado)

        async with self.connection.cursor() as cursor:
            await cursor.execute(
                "SELECT * FROM plans WHERE id = %s",
                (plan_id,)
            )

            # Métricas automáticas
            # neural_hive_database_duration_seconds{table="plans",operation="select"}
            # neural_hive_database_total{table="plans",operation="select"}

            return await cursor.fetchone()
```

## Propagação de Contexto

### Headers HTTP
```python
from neural_hive_observability import inject_correlation_headers, extract_correlation_headers
import httpx

# Client - Injeção automática
class ExternalAPIClient:
    async def call_downstream_service(self, data: dict):
        headers = {}
        inject_correlation_headers(headers)
        # headers agora contém:
        # X-Neural-Hive-Intent-ID: <uuid>
        # X-Neural-Hive-Plan-ID: <uuid>
        # X-Neural-Hive-Domain: <domain>
        # traceparent: 00-<trace_id>-<span_id>-01

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "http://downstream-service/api/process",
                json=data,
                headers=headers
            )
        return response

# Server - Extração automática
from fastapi import FastAPI, Request
from neural_hive_observability import FastAPIInstrumentation

app = FastAPI()
FastAPIInstrumentation.instrument_app(app)

@app.post("/api/process")
async def process_request(request: Request, data: dict):
    # Contexto extraído automaticamente dos headers
    correlation = extract_correlation_headers(request.headers)

    # Baggage automaticamente configurado:
    # - neural.hive.intent_id
    # - neural.hive.plan_id
    # - neural.hive.domain

    return {"status": "processed"}
```

### Message Queues
```python
from neural_hive_observability import inject_trace_context, extract_trace_context
import json

# Producer
class EventPublisher:
    async def publish_event(self, event_type: str, payload: dict):
        # Injeção de contexto em message properties
        message = {
            "event_type": event_type,
            "payload": payload,
            "metadata": {}
        }

        inject_trace_context(message["metadata"])

        await self.queue.publish(
            json.dumps(message),
            routing_key=event_type
        )

# Consumer
class EventProcessor:
    async def process_event(self, message: str):
        data = json.loads(message)

        # Extração e continuação do contexto
        with extract_trace_context(data.get("metadata", {})):
            await self.handle_event(data["event_type"], data["payload"])
```

## Métricas Customizadas

### Contadores de Negócio
```python
from neural_hive_observability import get_metrics_client

metrics = get_metrics_client()

class BusinessMetrics:
    def __init__(self):
        # Contadores
        self.plans_generated = metrics.Counter(
            name="neural_hive_plans_generated_total",
            description="Total de planos gerados",
            labels=["domain", "model_version", "success"]
        )

        # Histogramas para latência
        self.plan_generation_duration = metrics.Histogram(
            name="neural_hive_plan_generation_duration_seconds",
            description="Duração da geração de planos",
            labels=["domain", "complexity"],
            buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
        )

        # Gauges para estado
        self.active_plans = metrics.Gauge(
            name="neural_hive_active_plans",
            description="Número de planos ativos",
            labels=["status"]
        )

    def record_plan_generation(self, domain: str, duration: float, success: bool):
        self.plans_generated.inc({
            "domain": domain,
            "model_version": "gpt-4",
            "success": str(success).lower()
        })

        self.plan_generation_duration.record(duration, {
            "domain": domain,
            "complexity": "medium"  # lógica de classificação
        })

# Uso em serviço
class PlanGeneratorService:
    def __init__(self):
        self.metrics = BusinessMetrics()

    @trace_operation("generate_plan")
    async def generate_plan(self, intent: dict):
        start_time = time.time()
        try:
            plan = await self._generate_plan_logic(intent)
            self.metrics.record_plan_generation(
                domain=intent["domain"],
                duration=time.time() - start_time,
                success=True
            )
            return plan
        except Exception as e:
            self.metrics.record_plan_generation(
                domain=intent.get("domain", "unknown"),
                duration=time.time() - start_time,
                success=False
            )
            raise
```

### Anti-Patterns para Métricas

❌ **Evitar: High-cardinality labels**
```python
# NUNCA fazer isso - cardinality explode
metrics.Counter(
    name="requests_total",
    labels=["user_id", "session_id", "request_id"]  # ❌ Milhões de combinações
)

# NUNCA incluir dados sensíveis
metrics.Counter(
    name="auth_attempts_total",
    labels=["username", "password"]  # ❌ Dados sensíveis
)
```

✅ **Correto: Low-cardinality labels**
```python
# Usar categorias ao invés de IDs únicos
metrics.Counter(
    name="neural_hive_requests_total",
    labels=["component", "layer", "status", "domain"]  # ✅ Limitado
)

# Agrupar valores similares
metrics.Histogram(
    name="neural_hive_plan_cost_dollars",
    labels=["cost_tier"]  # "low", "medium", "high" ao invés de valores exatos
)
```

## Logging Estruturado

### Configuração Base
```python
from neural_hive_observability import get_logger

# Logger com correlação automática
logger = get_logger(__name__)

class ServiceBase:
    def __init__(self):
        self.logger = logger

    async def process_request(self, data: dict):
        # Logs automáticos incluem:
        # - timestamp (ISO8601)
        # - level
        # - message
        # - neural.hive.intent_id (do baggage)
        # - neural.hive.plan_id (do baggage)
        # - neural.hive.trace_id
        # - neural.hive.span_id

        self.logger.info(
            "Processing request",
            extra={
                "event_type": "request_processing_started",
                "data_size": len(json.dumps(data)),
                "correlation": get_correlation_context()
            }
        )
```

### Structured Logging Examples
```python
class IntentProcessor:
    async def validate_intent(self, intent: dict):
        try:
            # Informational logging
            logger.info(
                "Intent validation started",
                extra={
                    "intent_type": intent.get("type"),
                    "domain": intent.get("domain"),
                    "validation_rules": len(self.rules)
                }
            )

            result = await self._validate(intent)

            # Success logging
            logger.info(
                "Intent validation completed",
                extra={
                    "validation_result": "success",
                    "execution_time_ms": result.duration,
                    "rules_applied": result.rules_count
                }
            )

        except ValidationError as e:
            # Error logging com contexto
            logger.error(
                "Intent validation failed",
                extra={
                    "error_type": "ValidationError",
                    "error_code": e.code,
                    "failed_rules": e.failed_rules,
                    "user_message": e.user_message
                },
                exc_info=True  # Stack trace
            )

            # Métricas de erro automáticas via decorador
            raise

# Logs de auditoria para operações críticas
class PlanExecutor:
    async def execute_plan(self, plan: dict):
        # Audit log - sempre registrado independente de log level
        logger.info(
            "Plan execution initiated",
            extra={
                "audit": True,  # Flag para audit trails
                "plan_id": plan["id"],
                "estimated_cost": plan["cost"],
                "user_approval": plan.get("approved", False),
                "execution_mode": plan.get("mode", "automatic")
            }
        )
```

## Baggage e Contexto

### Definição de Baggage
```python
from neural_hive_observability import set_baggage, get_baggage

class ContextManager:
    @staticmethod
    def set_business_context(intent_id: str, domain: str, high_value: bool = False):
        """Define contexto de negócio propagado automaticamente"""
        set_baggage({
            "neural.hive.intent_id": intent_id,
            "neural.hive.domain": domain,
            "neural.hive.high_value": str(high_value).lower(),
            "neural.hive.user_tier": "premium" if high_value else "standard"
        })

    @staticmethod
    def get_current_context() -> dict:
        """Recupera contexto atual do baggage"""
        return {
            "intent_id": get_baggage("neural.hive.intent_id"),
            "plan_id": get_baggage("neural.hive.plan_id"),
            "domain": get_baggage("neural.hive.domain"),
            "high_value": get_baggage("neural.hive.high_value") == "true"
        }

# Uso em diferentes camadas
class LayeredService:
    def __init__(self, layer: str):
        self.layer = layer

    async def process_in_layer(self, data: dict):
        # Contexto automaticamente disponível
        context = ContextManager.get_current_context()

        # Sampling decision baseado em contexto
        if context["high_value"]:
            # Force sampling para clientes premium
            from opentelemetry.trace import get_current_span
            get_current_span().set_attribute("sampling.priority", 1)

        logger.info(f"Processing in {self.layer} layer", extra=context)
```

## Exemplos por Fluxo Operacional

### Fluxo A - Captura de Intenções
```python
# services/intent_capture.py
from neural_hive_observability import trace_operation

class IntentCaptureService:
    @trace_operation(
        operation_name="capture_user_intent",
        layer="experiencia",
        component="gateway"
    )
    async def capture_intent(self, user_input: str, session_id: str):
        # 1. Criar novo intent_id para o fluxo
        intent_id = str(uuid.uuid4())

        # 2. Definir contexto inicial
        ContextManager.set_business_context(
            intent_id=intent_id,
            domain=self._detect_domain(user_input),
            high_value=await self._is_premium_user(session_id)
        )

        # 3. Processar com telemetria automática
        intent = await self._nlp_processor.extract_intent(user_input)

        # 4. Métricas de negócio
        self.metrics.capture_latency.record(
            get_current_span().end_time - get_current_span().start_time
        )

        return {
            "intent_id": intent_id,
            "intent": intent,
            "metadata": ContextManager.get_current_context()
        }
```

### Fluxo B - Geração de Planos
```python
# services/plan_generation.py
class PlanGenerationService:
    @trace_operation(
        operation_name="generate_execution_plan",
        layer="cognicao",
        component="plan-generator"
    )
    async def generate_plan(self, intent: dict):
        # 1. Propagar contexto do intent
        intent_id = intent["intent_id"]
        plan_id = str(uuid.uuid4())

        # 2. Estender baggage com plan_id
        set_baggage({"neural.hive.plan_id": plan_id})

        # 3. Geração com rastreamento de dependências
        with trace_external_call("openai-gpt4", "plan_generation"):
            raw_plan = await self.llm_client.generate(intent["description"])

        with trace_database("postgresql", "plans", "insert"):
            await self.repository.save_plan(plan_id, raw_plan)

        # 4. Métricas específicas
        self.metrics.plan_generation_cost.record(
            value=raw_plan.estimated_cost,
            labels={"domain": intent["domain"]}
        )

        return {"plan_id": plan_id, "plan": raw_plan}
```

## Debugging e Troubleshooting

### Verificação de Instrumentação
```python
# utils/observability_check.py
from neural_hive_observability import is_tracing_enabled, get_tracer_info

def check_observability_status():
    """Debug helper para verificar configuração"""
    status = {
        "tracing_enabled": is_tracing_enabled(),
        "tracer_info": get_tracer_info(),
        "baggage_keys": list(get_baggage().keys()),
        "current_span_id": get_current_span().get_span_context().span_id
    }

    logger.debug("Observability status", extra=status)
    return status

# Middleware para desenvolvimento
class ObservabilityDebugMiddleware:
    async def __call__(self, request, call_next):
        if request.headers.get("X-Debug-Observability"):
            status = check_observability_status()
            response = await call_next(request)
            response.headers["X-Observability-Status"] = json.dumps(status)
            return response

        return await call_next(request)
```

### Testes de Instrumentação
```python
# tests/test_observability.py
import pytest
from neural_hive_observability.testing import MockTracer, assert_span_exists

@pytest.fixture
def mock_tracer():
    return MockTracer()

def test_intent_capture_instrumentation(mock_tracer):
    service = IntentCaptureService()

    with mock_tracer:
        result = await service.capture_intent("Hello", "session-123")

    # Verificar spans criados
    assert_span_exists(
        mock_tracer,
        name="capture_user_intent",
        attributes={
            "neural.hive.layer": "experiencia",
            "neural.hive.component": "gateway"
        }
    )

    # Verificar métricas
    assert mock_tracer.get_metric("neural_hive_operation_total") > 0

    # Verificar baggage
    baggage = mock_tracer.get_baggage()
    assert "neural.hive.intent_id" in baggage
    assert baggage["neural.hive.intent_id"] == result["intent_id"]
```

## Configurações Avançadas

### Sampling Strategies
```python
# config/sampling.py
SAMPLING_RULES = {
    "default_rate": 0.1,  # 10% de todas as operações
    "high_value_rate": 1.0,  # 100% para clientes premium
    "error_rate": 1.0,  # 100% de operações com erro
    "operation_overrides": {
        "capture_user_intent": 0.2,  # 20% - entrada crítica
        "execute_plan": 0.5,  # 50% - operação cara
        "health_check": 0.01  # 1% - muito frequente
    }
}

def get_sampling_rate(operation: str, context: dict) -> float:
    """Determina taxa de sampling baseada em contexto"""

    # High-value sempre amostrado
    if context.get("high_value"):
        return SAMPLING_RULES["high_value_rate"]

    # Override por operação
    if operation in SAMPLING_RULES["operation_overrides"]:
        return SAMPLING_RULES["operation_overrides"][operation]

    return SAMPLING_RULES["default_rate"]
```

### Performance Tuning
```python
# Batch export para reduzir overhead
OTEL_BSP_MAX_EXPORT_BATCH_SIZE=512
OTEL_BSP_EXPORT_TIMEOUT=30000  # 30s

# Resource detection otimizada
OTEL_RESOURCE_DETECTORS="env,process,docker,k8s"

# Compression para reduzir network
OTEL_EXPORTER_OTLP_COMPRESSION=gzip
```

## Checklist de Implementação

### ✅ Setup Básico
- [ ] Biblioteca `neural_hive_observability` instalada
- [ ] Configuração de ambiente (OTEL_* vars)
- [ ] Service name e version definidos
- [ ] OTLP endpoint configurado

### ✅ Instrumentação de Código
- [ ] Decoradores `@trace_operation` em operações críticas
- [ ] `@trace_external_call` para chamadas externas
- [ ] `@trace_database` para operações de banco
- [ ] Métricas de negócio implementadas
- [ ] Logging estruturado configurado

### ✅ Correlação e Contexto
- [ ] Headers de correlação propagados
- [ ] Baggage configurado corretamente
- [ ] Context extraction em entry points
- [ ] Context injection em calls externos

### ✅ Observabilidade de Produção
- [ ] Sampling adequado para volume
- [ ] Labels com baixa cardinalidade
- [ ] Métricas de SLO implementadas
- [ ] Error tracking completo
- [ ] Performance overhead < 5%

### ✅ Troubleshooting
- [ ] Debug helpers implementados
- [ ] Testes de instrumentação
- [ ] Dashboards de observabilidade da observabilidade
- [ ] Runbooks para problemas comuns

## Debugging com Jaeger - Casos Práticos

### Caso 1: Identificar Gargalo de Performance

**Problema:** Usuário reporta lentidão ao processar intenção.

**Passos para Diagnóstico:**

1. **Obter intent_id** do usuário (via logs, suporte, ou header de resposta)

2. **Buscar trace no Jaeger:**
   ```
   Service: *
   Tags: neural.hive.intent.id=<intent-id>
   Lookback: 1h
   ```

3. **Analisar duração de cada span** no trace:
   ```
   Gateway: 50ms ✓
   Kafka produce: 5ms ✓
   Orchestrator workflow: 8s ⚠️ LENTO
   Specialist evaluate: 7.5s ⚠️ GARGALO
   ```

4. **Drill-down** no span problemático (`specialist-business.Evaluate`):
   ```
   model.load: 6s ❌ PROBLEMA
   model.predict: 1.5s ✓
   ```

5. **Solução identificada:** Modelo não está em cache, implementar warmup no startup do specialist.

**Comando para análise automatizada:**
```bash
# Analisar latência por fase
curl -s "http://jaeger-query:16686/api/traces/<trace-id>" | \
  jq -r '.data[0].spans | sort_by(-.duration) | .[0:5][] |
    "\(.operationName): \((.duration / 1000) | round)ms"'
```

### Caso 2: Rastrear Falha em Fluxo Distribuído

**Problema:** Plan não foi executado, mas gateway retornou sucesso.

**Passos para Diagnóstico:**

1. **Buscar trace por plan_id:**
   ```bash
   curl "http://jaeger-query:16686/api/traces?tag=neural.hive.plan.id:<plan-id>" | jq
   ```

2. **Identificar span com erro:**
   ```json
   {
     "operationName": "allocate_resources",
     "tags": [
       {"key": "error", "value": true},
       {"key": "error.message", "value": "ServiceRegistry unavailable"}
     ]
   }
   ```

3. **Correlacionar com logs** no timestamp do span:
   ```bash
   kubectl logs -n neural-hive deployment/service-registry \
     --since-time=<span-start-time>
   ```

4. **Verificar estado do serviço:**
   ```bash
   kubectl get pods -n neural-hive -l app=service-registry
   kubectl describe pod -n neural-hive <service-registry-pod>
   ```

**Solução:** Service-registry estava em restart, implementar retry com backoff exponencial no orchestrator.

### Caso 3: Validar Propagação de Contexto

**Problema:** Specialist não recebe `intent_id` em metadata gRPC.

**Passos para Diagnóstico:**

1. **Buscar trace completo** do gateway até specialist:
   ```
   Service: gateway-intencoes
   Tags: neural.hive.intent.id=<intent-id>
   ```

2. **Verificar baggage em cada span:**
   - Gateway: `baggage.neural.hive.intent.id = <intent-id>` ✓
   - Orchestrator: `baggage.neural.hive.intent.id = <intent-id>` ✓
   - Specialist: `baggage.neural.hive.intent.id = null` ❌

3. **Verificar span de gRPC call** no orchestrator:
   ```bash
   curl -s "http://jaeger-query:16686/api/traces/<trace-id>" | \
     jq '.data[0].spans[] | select(.operationName | contains("grpc")) |
       .tags[] | select(.key | contains("metadata"))'
   ```
   - Se `rpc.grpc.request.metadata` não contém `x-neural-hive-intent-id`, há problema na injeção.

4. **Verificar código do gRPC client:**
   ```python
   # Deve haver algo como:
   inject_context_to_metadata(metadata)
   # antes de:
   stub.Evaluate(request, metadata=metadata)
   ```

**Solução:** Adicionar `inject_context_to_metadata()` antes da chamada gRPC no optimizer_grpc_client.py.

### Caso 4: Diagnosticar Sampling Issues

**Problema:** Traces importantes não aparecem no Jaeger.

**Passos para Diagnóstico:**

1. **Verificar métricas de tail sampling:**
   ```bash
   kubectl exec -n observability deployment/neural-hive-otel-collector -- \
     curl -s http://localhost:8888/metrics | \
     grep "otelcol_processor_tail_sampling"
   ```

2. **Verificar decisões de sampling:**
   ```bash
   kubectl exec -n observability deployment/neural-hive-otel-collector -- \
     curl -s http://localhost:8888/metrics | \
     grep "sampling_decision" | grep "sampled"
   ```

3. **Verificar política de sampling específica:**
   ```bash
   kubectl get configmap -n observability neural-hive-otel-collector -o yaml | \
     grep -A 30 "tail_sampling"
   ```

4. **Testar com trace forçado:**
   ```bash
   # Enviar request com flag de sampling forçado
   curl -H "traceparent: 00-$(openssl rand -hex 16)-$(openssl rand -hex 8)-01" \
        -H "Content-Type: application/json" \
        -d '{"text":"test forced sampling"}' \
        http://gateway-intencoes:8000/intents/text
   ```

**Solução:** Aumentar `sampling_percentage` para policies de alta prioridade ou adicionar tag específica para sempre amostrar (`neural.hive.force_sample=true`).

### Caso 5: Debug de Traces Fragmentados

**Problema:** Spans de diferentes serviços não formam uma árvore conectada.

**Diagnóstico via código:**
```python
# Script de diagnóstico
import requests

def check_trace_continuity(trace_id: str, jaeger_url: str):
    """Verifica se todos os spans compartilham o mesmo trace_id"""
    response = requests.get(f"{jaeger_url}/api/traces/{trace_id}")
    trace = response.json()["data"][0]

    parent_ids = set()
    span_ids = set()

    for span in trace["spans"]:
        span_ids.add(span["spanID"])
        for ref in span.get("references", []):
            if ref["refType"] == "CHILD_OF":
                parent_ids.add(ref["spanID"])

    # Spans órfãos (exceto root)
    orphan_spans = parent_ids - span_ids - {None}

    if orphan_spans:
        print(f"⚠️  Encontrados {len(orphan_spans)} spans com parent faltando")
        return False

    print("✓ Trace está íntegro")
    return True

# Uso
check_trace_continuity("abc123...", "http://jaeger-query:16686")
```

**Causas comuns:**
1. Context não propagado entre Kafka producer/consumer
2. gRPC metadata não injected corretamente
3. Async operations perdendo context

**Solução:** Garantir uso consistente de `with tracer.start_as_current_span()` e propagação via `inject()`/`extract()`.

## Exemplos de Queries por Cenário

### Cenário: Análise de SLA

```bash
# Traces que violaram SLA (>5s)
curl "http://jaeger-query:16686/api/traces?\
service=gateway-intencoes&\
minDuration=5s&\
lookback=24h&\
limit=100" | jq '.data | length'
```

### Cenário: Análise de Erros por Período

```bash
# Taxa de erro por hora nas últimas 24h
for h in $(seq 0 23); do
  START=$(($(date +%s) - (h+1)*3600))000000
  END=$(($(date +%s) - h*3600))000000

  TOTAL=$(curl -s "http://jaeger-query:16686/api/traces?service=gateway-intencoes&start=$START&end=$END&limit=1000" | jq '.data | length')
  ERRORS=$(curl -s "http://jaeger-query:16686/api/traces?service=gateway-intencoes&tag=error:true&start=$START&end=$END&limit=1000" | jq '.data | length')

  echo "Hora -$h: $ERRORS/$TOTAL erros"
done
```

### Cenário: Mapa de Dependências

```bash
# Extrair dependências de um trace
curl -s "http://jaeger-query:16686/api/traces/<trace-id>" | \
  jq -r '.data[0] |
    .spans as $spans |
    .processes as $procs |
    $spans[] |
    ($procs[.processID].serviceName) as $svc |
    (.references[]? | select(.refType=="CHILD_OF") | .spanID) as $parent |
    ($spans[] | select(.spanID==$parent) | $procs[.processID].serviceName) as $parent_svc |
    select($parent_svc != null) |
    "\($parent_svc) -> \($svc)"' | sort -u
```

## Referências

- **Documentação OpenTelemetry**: https://opentelemetry.io/docs/
- **Jaeger Documentation**: https://www.jaegertracing.io/docs/
- **Neural Hive Troubleshooting**: [jaeger-troubleshooting.md](./jaeger-troubleshooting.md)
- **Queries Customizadas**: [jaeger-queries-neural-hive.md](./jaeger-queries-neural-hive.md)