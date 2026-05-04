# Technical Specification

## Technical Requirements

### 1. Unified Gateway (:7999)

**Stack:**
- Python 3.12+
- FastAPI 0.104+
- gRPC (grpcio, grpcio-health-checking)
- Redis (rate limiting + cache)
- Kafka (event publishing)
- OpenTelemetry (tracing + metrics)

**Endpoints:**
```
POST /api/v1/nhm/request
  - Request body:
    {
      "input": { "text": "...", "files": [...] },
      "context": { "tenant_id": "...", "project_id": "...", "session_id": "..." },
      "preferences": { "response_type": "async|sync", "webhook_url": "..." }
    }
  - Response:
    {
      "request_id": "req-YYYYMMDD-NNN",
      "status": "processing|completed|failed",
      "flow_type": "A-F|G|H",
      "flow_name": "cognitive|code_generation|migration",
      "routed_to": "service:port",
      "estimated_duration_ms": N,
      "result": { ... }  // se sync
    }

GET /api/v1/nhm/status/{request_id}
  - Query status de request assíncrono

GET /api/v1/nhm/stream/{request_id}
  - SSE stream de updates em tempo real
```

**Classificação de Fluxo:**
```python
class FlowClassifier:
    """
    Regras de classificação (ordem de precedência):
    1. Palavras-chave explícitas (maior peso)
    2. Entidades detectadas pelo NLU
    3. Complexidade inferida
    4. Contexto do tenant
    """

    FLOW_AF_KEYWORDS = ["consultar", "buscar", "analisar", "dashboard", "relatório"]
    FLOW_G_KEYWORDS = ["gerar", "criar sistema", "build app", "desenvolver software"]
    FLOW_H_KEYWORDS = ["migrar", "migration", "legado", "sistema antigo"]

    def classify(self, context: RichContext, nlu_result: NLUResult) -> FlowType:
        # Keyword matching (peso 4.0)
        keyword_score = self._match_keywords(nlu_result.text)

        # Entity-based (peso 3.0)
        entity_score = self._match_entities(nlu_result.entities)

        # Complexity-based (peso 2.0)
        complexity_score = self._assess_complexity(nlu_result)

        # Context-based (peso 1.0)
        context_score = self._check_context(context)

        # Weighted sum
        scores = {
            FlowType.AF: keyword_score.af + entity_score.af + complexity_score.af + context_score.af,
            FlowType.G: keyword_score.g + entity_score.g + complexity_score.g + context_score.g,
            FlowType.H: keyword_score.h + entity_score.h + complexity_score.h + context_score.h,
        }

        # Max score wins (se > threshold)
        max_score = max(scores.values())
        if max_score > 0.7:  # confidence threshold
            return max(scores, key=scores.get)

        # Default: Flow A-F
        return FlowType.AF
```

**Rate Limiting:**
```python
class RateLimiter:
    """
    Token bucket algorithm com Redis backend
    Configuração por tenant:
    - Default: 100 req/min
    - Enterprise: 1000 req/min
    - Trial: 10 req/min
    """

    async def check_limit(self, tenant_id: str, api_key: str) -> RateLimitResult:
        key = f"ratelimit:{tenant_id}:{api_key}"
        bucket = await redis.get(key)

        if bucket.tokens > 0:
            bucket.tokens -= 1
            await redis.set(key, bucket, ex=60)
            return RateLimitResult(allowed=True, remaining=bucket.tokens)

        return RateLimitResult(allowed=False, retry_after=60)
```

**Proxy Layer:**
```python
class FlowRouter:
    """
    Proxy para gateways específicos com:
    - HTTP/gRPC support
    - Timeout: 30s (configurável)
    - Retry: 3 tentativas com exponential backoff
    - Circuit Breaker: abre após 5 falhas consecutivas
    """

    GATEWAYS = {
        FlowType.AF: "http://gateway-intencoes:8000",
        FlowType.G: "http://requirements-engineering:8010",
        FlowType.H: "http://doc-ingestion:8018",
    }

    async def route(self, flow_type: FlowType, request: Request) -> Response:
        gateway_url = self.GATEWAYS[flow_type]

        # Circuit breaker check
        if self.circuit_breaker.is_open(gateway_url):
            raise ServiceUnavailableError(f"Gateway {flow_type} is down")

        # Proxy request
        try:
            response = await self._proxy_request(gateway_url, request)
            self.circuit_breaker.record_success(gateway_url)
            return response
        except Exception as e:
            self.circuit_breaker.record_failure(gateway_url)
            raise
```

### 2. NLU Service (:8020)

**gRPC Service Definition:**
```protobuf
syntax = "proto3";

package nlu.v1;

service NLUService {
  rpc Parse(ParseRequest) returns (ParseResponse);
  rpc ClassifyDomain(ClassifyRequest) returns (DomainResponse);
  rpc ExtractEntities(EntityRequest) returns (EntityResponse);
  rpc CalculateConfidence(ConfidenceRequest) returns (ConfidenceResponse);
  rpc HealthCheck(HealthCheckRequest) returns (HealthCheckResponse);
}

message ParseRequest {
  string text = 1;
  string language = 2;  // default: "pt-BR"
  map<string, string> context = 3;
}

message ParseResponse {
  DomainClassification domain = 1;
  repeated Entity entities = 2;
  double confidence = 3;
  repeated Keyword keywords = 4;
  string reasoning = 5;
}

message DomainClassification {
  Domain domain = 1;
  double confidence = 2;
}

enum Domain {
  DOMAIN_UNKNOWN = 0;
  BUSINESS = 1;
  TECHNICAL = 2;
  INFRASTRUCTURE = 3;
  SECURITY = 4;
}

message Entity {
  string text = 1;
  string label = 2;
  double confidence = 3;
  int32 start = 4;
  int32 end = 5;
}
```

**Performance Requirements:**
- Parse: <50ms p95
- Cache hit rate: >70%
- Concurrent requests: >100/sec

### 3. PII Service (:8021)

**gRPC Service Definition:**
```protobuf
syntax = "proto3";

package pii.v1;

service PIIService {
  rpc Detect(DetectRequest) returns (DetectResponse);
  rpc Mask(MaskRequest) returns (MaskResponse);
  rpc Unmask(UnmaskRequest) returns (UnmaskResponse);
  rpc HealthCheck(HealthCheckRequest) returns (HealthCheckResponse);
}

message DetectRequest {
  string text = 1;
  repeated PIIType types = 2;  // empty = all types
}

message DetectResponse {
  repeated PIIFound found = 1;
  bool has_pii = 2;
}

message PIIFound {
  PIIType type = 1;
  string text = 2;
  int32 start = 3;
  int32 end = 4;
  double confidence = 5;
}

enum PIIType {
  PII_TYPE_UNKNOWN = 0;
  EMAIL = 1;
  PHONE = 2;
  CPF = 3;
  CNPJ = 4;
  CREDIT_CARD = 5;
  SSN = 6;
  ADDRESS = 7;
}

message MaskRequest {
  string text = 1;
  MaskStrategy strategy = 2;
}

enum MaskStrategy {
  MASK_FULL = 0;      // "joao@exemplo.com" -> "*************"
  MASK_PARTIAL = 1;   // "joao@exemplo.com" -> "j***@e******.com"
  MASK_REDACT = 2;    // "joao@exemplo.com" -> "[EMAIL]"
}

message MaskResponse {
  string masked_text = 1;
  string mask_id = 2;  // para unmask reversível
  repeated PIIType types_found = 3;
}
```

**Security Requirements:**
- Todos endpoints requerem autenticação
- Audit logging de todas as operações
- Mask ID usa criptografia AES-256-GCM
- Keys armazenadas no Vault

### 4. Approval Core Package

**Package Structure:**
```
neural_hive_approval_common/
├── neural_hive_approval_common/
│   ├── __init__.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── request.py      # UnifiedApprovalRequest
│   │   ├── decision.py     # UnifiedApprovalDecision
│   │   └── common.py       # Enums, Base models
│   ├── core/
│   │   ├── __init__.py
│   │   ├── engine.py       # ApprovalDecisionEngine
│   │   ├── thresholds.py   # ThresholdEvaluator
│   │   ├── risk.py         # RiskAssessor
│   │   └── rules.py        # CommonRules
│   ├── config/
│   │   ├── __init__.py
│   │   ├── policies.py     # PolicyTemplates
│   │   └── defaults.py     # DefaultThresholds
│   └── utils/
│       ├── __init__.py
│       └── helpers.py
├── tests/
│   ├── test_models.py
│   ├── test_engine.py
│   └── test_rules.py
├── pyproject.toml
├── README.md
└── proto/
    └── approval.proto
```

**Core Engine:**
```python
class ApprovalDecisionEngine:
    """
    Motor de decisão de aprovação unificado.
    Suporta 3 estratégias:
    1. Rule-based (thresholds fixos)
    2. ML-based (modelos treinados)
    3. LLM-based (GPT-4 para casos complexos)
    """

    def decide(self, request: UnifiedApprovalRequest) -> UnifiedApprovalDecision:
        # 1. Check common rules (critical items, destructive ops)
        rule_result = self.rules.evaluate(request)
        if rule_result.override is not None:
            return self._decision_from_rule(rule_result)

        # 2. Calculate risk score
        risk_score = self.risk_assessor.assess(request)

        # 3. Get strategy
        strategy = self.config.get_strategy(request.tenant_id)

        if strategy == "rule_based":
            return self._rule_based_decision(request, risk_score)
        elif strategy == "ml_based":
            return self._ml_based_decision(request, risk_score)
        elif strategy == "llm_based":
            return self._llm_based_decision(request, risk_score)
        else:
            raise ValueError(f"Unknown strategy: {strategy}")

    def _rule_based_decision(self, request, risk_score):
        threshold = self.thresholds.get_threshold(request.tenant_id)

        if risk_score >= threshold.auto_approve:
            return UnifiedApprovalDecision(
                status=ApprovalStatus.APPROVED,
                method="rule_based",
                confidence=min(risk_score / threshold.auto_approve, 1.0),
            )
        elif risk_score <= threshold.auto_reject:
            return UnifiedApprovalDecision(
                status=ApprovalStatus.REJECTED,
                method="rule_based",
                confidence=1.0 - (risk_score / threshold.auto_reject),
            )
        else:
            return UnifiedApprovalDecision(
                status=ApprovalStatus.PENDING,
                method="rule_based",
                confidence=0.5,
            )
```

### 5. External Dependencies

**New Dependencies to Add:**
```toml
# pyproject.toml for unified-gateway
[dependencies]
fastapi = "^0.104.0"
grpcio = "^1.60.0"
grpcio-health-checking = "^1.67.1"
redis = "^5.0.0"
aiokafka = "^0.9.0"
opentelemetry-api = "^1.22.0"
opentelemetry-sdk = "^1.22.0"
opentelemetry-instrumentation-fastapi = "^0.43b0"
opentelemetry-instrumentation-grpc = "^0.43b0"
pyjwt = "^2.8.0"
python-multipart = "^0.0.6"
structlog = "^24.1.0"

# For NLU Service
spacy = "^3.7.0"
spacy-model-pt-core-news-lg = {version = "^3.7.0", source = "spacy"}

# For PII Service
phonenumbers = "^8.13.0"
python-dateutil = "^2.8.0"

# Common
pydantic = "^2.5.0"
pydantic-settings = "^2.1.0"
```

### 6. Database Schemas

**Nenhuma mudança de schema necessária.**
- MongoDB: Usado por serviços existentes (sem mudança)
- Redis: Adicionar keys para rate limiting e cache
- Kafka: Adicionar tópicos para unified gateway events

**New Redis Keys:**
```
# Rate Limiting
ratelimit:{tenant_id}:{api_key} -> TokenBucket (TTL 60s)

# NLU Cache
nlu:cache:{hash(text)} -> NLUResult (TTL 3600s)

# Request Status
request:{request_id} -> RequestStatus (TTL 86400s)
```

**New Kafka Topics:**
```
# Unified Gateway Events
unified.request.received    - Request recebida
unified.request.routed      - Request roteada
unified.request.completed   - Request completada
unified.request.failed      - Request falhou
```

### 7. Configuration

**Unified Gateway Configuration:**
```yaml
# config/production.yaml
server:
  host: 0.0.0.0
  port: 7999
  workers: 4

auth:
  jwt_secret: ${JWT_SECRET}
  jwt_algorithm: RS256
  jwks_url: https://auth.example.com/.well-known/jwks.json
  api_key_header: X-API-Key

rate_limit:
  default: 100  # requests per minute
  enterprise: 1000
  trial: 10
  redis_url: redis://redis:6379/0

nlu_service:
  address: nlu-service:8020
  timeout: 5  # seconds
  retry: 3

pii_service:
  address: pii-service:8021
  timeout: 3  # seconds
  retry: 3

flow_router:
  flow_af: http://gateway-intencoes:8000
  flow_g: http://requirements-engineering:8010
  flow_h: http://doc-ingestion:8018
  timeout: 30
  circuit_breaker:
    failure_threshold: 5
    recovery_timeout: 60
    half_open_max_calls: 3

kafka:
  bootstrap_servers: kafka:9092
  topic_prefix: unified

tracing:
  exporter: otlp
  endpoint: http://jaeger:4317
  sample_rate: 0.1
```

---

## Integration Points

### With Existing Services

| Service | Integration Type | Notes |
|---------|------------------|-------|
| gateway-intencoes | HTTP/gRPC proxy | Remover NLU/PII internos |
| requirements-engineering | HTTP/gRPC proxy | Remover NLU interno |
| doc-ingestion | HTTP/gRPC proxy | Remover PII interno |
| approval-service | Package dependency | Usar neural_hive_approval_common |
| neural_hive_context | Library import | Usar ContextManager |
| neural_hive_security | Library import | Usar JWT verifier |

### Migration Strategy

**Phase 1: Deploy New Services Alongside**
- Deploy unified-gateway :7999 (não rotear tráfego)
- Deploy nlu-service :8020 (usado internamente)
- Deploy pii-service :8021 (usado internamente)

**Phase 2: Refactor Existing Services**
- gateway-intencoes → usar NLU/PII services
- requirements-engineering → usar NLU service
- doc-ingestion → usar PII service

**Phase 3: Gradual Traffic Shift**
- 10% → unified-gateway
- Monitorar por 24h
- 50% → unified-gateway
- Monitorar por 48h
- 100% → unified-gateway

**Phase 4: Deprecate Old Endpoints**
- Marcar endpoints antigos como deprecated
- Manter por 30 dias
- Remover após período de grace
