# Arquitetura gRPC dos Especialistas

## Visao Geral

Os especialistas do Neural Hive-Mind expõem interface gRPC para avaliação de planos cognitivos. A implementação segue padrão de **Template Method**, onde `BaseSpecialist` fornece pipeline completo e especialistas concretos implementam apenas lógica específica.

## Componentes

### 1. Protobuf Definitions

**Arquivo:** `libraries/python/neural_hive_specialists/proto/specialist.proto`

Define 3 serviços:
- `EvaluatePlan` - Avalia plano cognitivo
- `HealthCheck` - Verifica saúde do serviço
- `GetCapabilities` - Retorna capacidades e métricas

### 2. Generated Stubs

**Arquivo:** `libraries/python/neural_hive_specialists/proto_gen/specialist_pb2_grpc.py`

Gerado automaticamente pelo `protoc`. Contém:
- `SpecialistServiceStub` - Cliente gRPC
- `SpecialistServiceServicer` - Classe base com `NotImplementedError` (normal)
- `add_SpecialistServiceServicer_to_server()` - Registra servicer no servidor

**IMPORTANTE:** Este arquivo é gerado automaticamente e **não deve ser editado manualmente**. Os métodos com `NotImplementedError` são stubs - a implementação real está em `SpecialistServicer`.

### 3. Servicer Implementation

**Arquivo:** `libraries/python/neural_hive_specialists/grpc_server.py`

Classe `SpecialistServicer` implementa os 3 métodos gRPC:

```python
class SpecialistServicer:
    def __init__(self, specialist: BaseSpecialist):
        self.specialist = specialist

    def EvaluatePlan(self, request, context):
        # 1. Extrair contexto (trace_id, tenant_id, etc.)
        # 2. Chamar specialist.evaluate_plan(request)
        # 3. Converter dict → protobuf response
        # 4. Retornar EvaluatePlanResponse

    def HealthCheck(self, request, context):
        # Chamar specialist.health_check()

    def GetCapabilities(self, request, context):
        # Chamar specialist.get_capabilities()
```

### 4. Base Specialist

**Arquivo:** `libraries/python/neural_hive_specialists/base_specialist.py`

Classe abstrata que fornece:
- `evaluate_plan(request)` - Pipeline completo de avaliação
- `health_check()` - Verificação de saúde
- `get_capabilities()` - Retorno de capacidades

Pipeline de `evaluate_plan()`:
1. Deserialização do plano (JSON/Avro)
2. Validação de schema
3. Sanitização de PII (se habilitado)
4. Verificação de cache
5. Inferência ML (com fallback para heurísticas)
6. Geração de explainability
7. Persistência no ledger
8. Atualização de métricas
9. Cache do resultado

### 5. Concrete Specialists

**Arquivos:** `services/specialist-*/src/specialist.py`

Cada especialista implementa:
- `_get_specialist_type()` - Identificador único
- `_load_model()` - Carregamento de modelo ML
- `_evaluate_plan_internal(cognitive_plan, context)` - Lógica específica

## Fluxo de Dados

```
┌─────────────────┐
│  Consensus      │
│  Engine         │
└────────┬────────┘
         │ gRPC EvaluatePlanRequest
         ▼
┌─────────────────────────────────────────────────────────┐
│  SpecialistServicer (grpc_server.py)                    │
│  ┌───────────────────────────────────────────────────┐  │
│  │ 1. Extract context (trace_id, tenant_id)         │  │
│  │ 2. Call specialist.evaluate_plan(request)        │  │
│  │ 3. Convert dict → protobuf                       │  │
│  └───────────────────────────────────────────────────┘  │
└────────┬────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│  BaseSpecialist (base_specialist.py)                    │
│  ┌───────────────────────────────────────────────────┐  │
│  │ Pipeline:                                         │  │
│  │ • Deserialize plan                               │  │
│  │ • Validate schema                                │  │
│  │ • Check cache                                    │  │
│  │ • ML inference (or heuristics fallback)          │  │
│  │ • Generate explainability                        │  │
│  │ • Persist to ledger                              │  │
│  │ • Update metrics                                 │  │
│  └───────────────────────────────────────────────────┘  │
└────────┬────────────────────────────────────────────────┘
         │ Call _evaluate_plan_internal()
         ▼
┌─────────────────────────────────────────────────────────┐
│  ArchitectureSpecialist (specialist.py)                 │
│  ┌───────────────────────────────────────────────────┐  │
│  │ Specific logic:                                   │  │
│  │ • Analyze design patterns                        │  │
│  │ • Check SOLID principles                         │  │
│  │ • Evaluate coupling/cohesion                     │  │
│  │ • Return {confidence, risk, recommendation}      │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

## Diagrama de Sequência

```
┌──────────┐      ┌─────────────────┐     ┌──────────────┐     ┌───────────────────┐
│ Consensus│      │SpecialistServicer│     │BaseSpecialist │     │ArchitectureSpec.  │
│ Engine   │      │                  │     │               │     │                   │
└────┬─────┘      └────────┬─────────┘     └──────┬────────┘     └─────────┬─────────┘
     │                     │                      │                        │
     │ EvaluatePlanRequest │                      │                        │
     │────────────────────>│                      │                        │
     │                     │                      │                        │
     │                     │ evaluate_plan(req)   │                        │
     │                     │─────────────────────>│                        │
     │                     │                      │                        │
     │                     │                      │ _evaluate_plan_internal│
     │                     │                      │───────────────────────>│
     │                     │                      │                        │
     │                     │                      │  {confidence, risk,    │
     │                     │                      │   recommendation}      │
     │                     │                      │<───────────────────────│
     │                     │                      │                        │
     │                     │  dict result         │                        │
     │                     │<─────────────────────│                        │
     │                     │                      │                        │
     │                     │ _build_response()    │                        │
     │                     │─────────┐            │                        │
     │                     │         │            │                        │
     │                     │<────────┘            │                        │
     │                     │                      │                        │
     │EvaluatePlanResponse │                      │                        │
     │<────────────────────│                      │                        │
     │                     │                      │                        │
```

## Estruturas de Dados

### EvaluatePlanRequest

```protobuf
message EvaluatePlanRequest {
    string plan_id = 1;
    string intent_id = 2;
    string correlation_id = 3;
    string trace_id = 4;
    string span_id = 5;
    bytes cognitive_plan = 6;          // JSON ou Avro serializado
    string plan_version = 7;
    map<string, string> context = 8;   // Contexto adicional (tenant_id, etc.)
    int32 timeout_ms = 9;
}
```

### EvaluatePlanResponse

```protobuf
message EvaluatePlanResponse {
    string opinion_id = 1;
    string specialist_type = 2;
    string specialist_version = 3;
    SpecialistOpinion opinion = 4;
    int32 processing_time_ms = 5;
    google.protobuf.Timestamp evaluated_at = 6;
}

message SpecialistOpinion {
    double confidence_score = 1;        // 0.0 - 1.0
    double risk_score = 2;              // 0.0 - 1.0
    string recommendation = 3;           // approve, reject, review_required, conditional
    string reasoning_summary = 4;        // Narrativa explicativa
    repeated ReasoningFactor reasoning_factors = 5;
    string explainability_token = 6;     // Token para consulta posterior
    ExplainabilityMetadata explainability = 7;  // Metadados SHAP/LIME
    repeated MitigationSuggestion mitigations = 8;
    map<string, string> metadata = 9;
}

message ReasoningFactor {
    string factor_name = 1;
    double weight = 2;                  // 0.0 - 1.0
    double score = 3;                   // 0.0 - 1.0
    string description = 4;
}

message MitigationSuggestion {
    string mitigation_id = 1;
    string description = 2;
    string priority = 3;                // low, medium, high, critical
    double estimated_impact = 4;        // 0.0 - 1.0
    repeated string required_actions = 5;
}
```

## Observabilidade

### OpenTelemetry Tracing

Cada chamada gRPC é automaticamente instrumentada via `GrpcInstrumentorServer`:

```python
from opentelemetry.instrumentation.grpc import GrpcInstrumentorServer

GrpcInstrumentorServer().instrument_server(server)
```

Atributos adicionados ao span:
- `specialist.type` - Tipo do especialista
- `specialist.version` - Versão do especialista
- `plan.id` - ID do plano avaliado
- `intent.id` - ID da intent original
- `opinion.id` - ID do parecer gerado
- `opinion.confidence_score` - Score de confiança
- `opinion.risk_score` - Score de risco
- `opinion.recommendation` - Recomendação final
- `processing.time_ms` - Tempo de processamento

### Prometheus Metrics

```python
# Histograma de latência
specialist_evaluation_duration_seconds = Histogram(
    'specialist_evaluation_duration_seconds',
    'Duration of plan evaluation',
    ['specialist_type', 'recommendation']
)

# Contador de avaliações
specialist_evaluation_total = Counter(
    'specialist_evaluation_total',
    'Total number of evaluations',
    ['specialist_type', 'recommendation', 'status']
)

# Gauge de scores
specialist_confidence_score = Gauge(
    'specialist_confidence_score',
    'Current confidence score',
    ['specialist_type', 'plan_id']
)
```

### Structured Logging

Logs em formato JSON com contexto completo:

```json
{
    "timestamp": "2025-01-05T10:30:00Z",
    "level": "info",
    "message": "EvaluatePlan completed",
    "plan_id": "plan-123",
    "opinion_id": "opinion-456",
    "specialist_type": "architecture",
    "confidence_score": 0.85,
    "risk_score": 0.15,
    "recommendation": "approve",
    "processing_time_ms": 150,
    "trace_id": "abc123",
    "span_id": "def456"
}
```

## Segurança

### JWT Authentication

Via `AuthInterceptor` (opcional):

```python
class AuthInterceptor(grpc.ServerInterceptor):
    def intercept_service(self, continuation, handler_call_details):
        # 1. Extrair token do metadata
        # 2. Validar JWT
        # 3. Extrair claims (tenant_id, user_id, roles)
        # 4. Propagar para contexto
```

### mTLS

Suporte via SPIFFE/SPIRE para comunicação segura entre serviços.

### Tenant Isolation

Propagação de `x-tenant-id` via metadata gRPC:

```python
# Cliente
metadata = [('x-tenant-id', 'tenant-abc')]
response = stub.EvaluatePlan(request, metadata=metadata)

# Servidor
tenant_id = dict(context.invocation_metadata()).get('x-tenant-id')
```

### PII Sanitization

Remoção automática de dados sensíveis antes da persistência:

```python
from neural_hive_specialists.pii_detector import PIIDetector

detector = PIIDetector()
sanitized_plan = detector.sanitize(cognitive_plan)
```

## Testes

### Unitários

```bash
cd libraries/python/neural_hive_specialists
pytest tests/test_grpc_server.py -v
```

Cobertura:
- `SpecialistServicer.EvaluatePlan()`
- `SpecialistServicer.HealthCheck()`
- `SpecialistServicer.GetCapabilities()`
- `_build_evaluate_plan_response()`
- `_build_health_check_response()`
- `_build_get_capabilities_response()`
- Tratamento de erros (ValueError, RuntimeError)
- Propagação de tenant_id

### Integração

```bash
# Requer especialistas rodando
pytest tests/integration/test_grpc_integration.py -v -m integration
```

Cobertura:
- Comunicação gRPC real
- Validação de respostas estruturais
- Propagação de metadados
- Tratamento de erros gRPC
- Performance (latência)

### E2E

```bash
python scripts/debug/test-grpc-comprehensive.py --specialist architecture
```

Resultado esperado:
```
✅ Architecture Specialist - EvaluatePlan: SUCCESS
✅ Architecture Specialist - HealthCheck: SUCCESS
✅ Architecture Specialist - GetCapabilities: SUCCESS
```

## Troubleshooting

### Erro: "NotImplementedError" no specialist_pb2_grpc.py

**Causa:** Isso é comportamento normal. Os métodos no arquivo gerado `specialist_pb2_grpc.py` são stubs que lançam `NotImplementedError` se chamados diretamente.

**Solução:** A implementação real está em `SpecialistServicer` (`grpc_server.py`). Os stubs são apenas templates gerados pelo `protoc`.

### Erro: "Specialist not available at localhost:5005X"

**Causa:** O especialista não está rodando ou está em porta diferente.

**Solução:**
1. Verificar se o especialista está rodando: `kubectl get pods -n neural-hive-mind | grep specialist`
2. Verificar logs: `kubectl logs -f <pod-name>`
3. Verificar porta correta no ConfigMap

### Erro: "Tenant desconhecido"

**Causa:** O `x-tenant-id` não foi passado no metadata ou o tenant não existe.

**Solução:**
1. Verificar que metadata inclui `x-tenant-id`
2. Verificar que tenant existe no MongoDB
3. Verificar logs do especialista para mais detalhes

### Erro: "DEADLINE_EXCEEDED"

**Causa:** Timeout da chamada gRPC.

**Solução:**
1. Aumentar `timeout_ms` no request
2. Verificar carga do especialista
3. Verificar conexões com dependências (MongoDB, Redis, MLflow)
