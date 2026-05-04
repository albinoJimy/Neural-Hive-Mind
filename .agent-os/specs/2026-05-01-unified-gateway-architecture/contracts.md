# Contract Pin — Unified Gateway Architecture

Preserve the surface below across the refactor. Callers must not notice behavioral changes.

## Frozen Public API

### NLUPipeline Interface (gateway-intencoes/src/pipelines/nlu_pipeline.py)

- `async def parse(text: str, context: dict) -> NLUResult` — returns domain classification + entities + confidence *— fulfills R-NLU.1, R-NLU.2*
- `async def classify_domain(text: str) -> UnifiedDomain` — returns BUSINESS/TECHNICAL/INFRASTRUCTURE/SECURITY *— fulfills R-NLU.3*
- `async def extract_entities(text: str) -> list[Entity]` — returns named entities with positions *— fulfills R-NLU.4*
- `async def calculate_confidence(nlu_result: NLUResult) -> float` — returns confidence score 0-1 *— fulfills R-NLU.5*
- NLUResult model with fields: `domain: UnifiedDomain`, `entities: list[Entity]`, `confidence: float`, `keywords: list[str]` *— fulfills R-NLU.6*

### PIIDetectorLite Interface (neural_hive_specialists/compliance/pii_detector.py)

- `def detect(text: str, types: list[PIIType]) -> list[PIIFound]` — returns detected PII with positions *— fulfills R-PII.1*
- `def mask(text: str, strategy: MaskStrategy) -> tuple[str, list[PIIType]]` — returns masked text + types found *— fulfills R-PII.2*
- PIIType enum: EMAIL, PHONE, CPF, CNPJ, CREDIT_CARD, SSN, ADDRESS (7 types) *— fulfills R-PII.3*
- MaskStrategy enum: MASK_FULL, MASK_PARTIAL, MASK_REDACT (3 strategies) *— fulfills R-PII.4*

### ApprovalService Interface (approval-service/src/services/approval_service.py)

- `async def create_approval_request(plan_id: str, intent_id: str, risk_score: float, cognitive_plan: dict) -> ApprovalRequest` — returns created request *— fulfills R-APP.1*
- `async def approve(request_id: str, approved_by: str, comments: str) -> ApprovalDecision` — approves request *— fulfills R-APP.2*
- `async def reject(request_id: str, rejected_by: str, reason: str) -> ApprovalDecision` — rejects request *— fulfills R-APP.3*
- `async def get_request(request_id: str) -> ApprovalRequest | None` — retrieves request *— fulfills R-APP.4*
- ApprovalRequest model with fields: `approval_id`, `plan_id`, `intent_id`, `risk_score`, `risk_band`, `status`, `cognitive_plan` *— fulfills R-APP.5*
- ApprovalDecision model with fields: `decision: Literal["approved", "rejected"]`, `approved_by`, `approved_at`, `rejection_reason` *— fulfills R-APP.6*

### Intent Envelope Models (gateway-intencoes/src/models/intent_envelope.py)

- `Intent` model with fields: `text`, `domain: UnifiedDomain`, `entities`, `keywords` *— fulfills R-INT.1*
- `Context` model with fields: `session_id`, `user_id`, `tenant_id`, `channel`, `client_ip` *— fulfills R-INT.2*
- `Entity` model with fields: `type`, `value`, `confidence`, `start`, `end` *— fulfills R-INT.3*
- UnifiedDomain enum: BUSINESS, TECHNICAL, INFRASTRUCTURE, SECURITY *— fulfills R-INT.4*

### Kafka Topic Contracts (Event Bus)

- Topic: `plan_approvals` — ApprovalRequest messages (approval → orchestrator) *— fulfills R-KAFKA.1*
- Topic: `plan_approvals_responses` — ApprovalResponse messages (orchestrator → approval) *— fulfills R-KAFKA.2*
- Topic: `specialist_feedback` — NLPFeatureExtractor feedback for ML *— fulfills R-KAFKA.3*
- Message format: JSON with Avro schema validation *— fulfills R-KAFKA.4*
- Key format: `plan_id` for partitioning *— fulfills R-KAFKA.5*

### Gateway HTTP Endpoints (Backward Compatibility)

**gateway-intencoes (:8000)**
- `POST /api/v1/nlu/parse` — NLU parsing (MUST remain functional during transition) *— fulfills R-HTTP.1*
- `POST /api/v1/nlu/classify` — Domain classification (MUST remain functional during transition) *— fulfills R-HTTP.2*
- `GET /health` — Health check (MUST remain functional) *— fulfills R-HTTP.3*

**requirements-engineering (:8010)**
- `POST /api/v1/requirements/extract` — Requirements extraction (MUST remain functional during transition) *— fulfills R-HTTP.4*
- `GET /health` — Health check (MUST remain functional) *— fulfills R-HTTP.5*

**doc-ingestion (:8018)**
- `POST /api/v1/docs/ingest` — Document ingestion (MUST remain functional during transition) *— fulfills R-HTTP.6*
- `GET /health` — Health check (MUST remain functional) *— fulfills R-HTTP.7*

**approval-service (:8004)**
- `POST /api/v1/approvals/{approval_id}/approve` — Approve request (MUST remain functional) *— fulfills R-HTTP.8*
- `POST /api/v1/approvals/{approval_id}/reject` — Reject request (MUST remain functional) *— fulfills R-HTTP.9*
- `GET /api/v1/approvals/{approval_id}` — Get request (MUST remain functional) *— fulfills R-HTTP.10*
- `GET /health` — Health check (MUST remain functional) *— fulfills R-HTTP.11*

## Allowed Internal Churn

### Can Be Removed

- **NLU Pipeline Implementation** in gateway-intencoes (1.303 LOC) — can be deleted after NLU Service deployment *— fulfills R-REMOVE.1*
- **PII Detection Implementation** in gateway-intencoes (~150 LOC) — can be deleted after PII Service deployment *— fulfills R-REMOVE.2*
- **SecurityHeadersMiddleware** in each service — can be removed after Unified Gateway auth centralization *— fulfills R-REMOVE.3*
- **approval-gateway** (:8017) entire service — can be deprecated after approval-service migration *— fulfills R-REMOVE.4*

### Can Be Refactored

- **gateway-intencoes** — can proxy to NLU/PII services instead of local implementation *— fulfills R-REFACTOR.1*
- **approval-service** — can extract ~2.000 LOC to neural_hive_approval_common package *— fulfills R-REFACTOR.2*
- **requirements-engineering** — can use NLU service instead of local NLU (currently 0 LOC to remove) *— fulfills R-REFACTOR.3*
- **doc-ingestion** — can use PII service instead of local PII (currently 0 LOC to remove) *— fulfills R-REFACTOR.4*

### Can Be Added

- **unified-gateway** (:7999) — new service for routing and auth *— fulfills R-ADD.1*
- **nlu-service** (:8020) — centralized NLU with gRPC + REST *— fulfills R-ADD.2*
- **pii-service** (:8021) — centralized PII with gRPC + REST + audit logging *— fulfills R-ADD.3*
- **neural_hive_approval_common** — shared approval models and logic *— fulfills R-ADD.4*

## Invariants (MUST preserve)

### INV-1: NLU Result Compatibility
NLU Result structure from NLU Service MUST be compatible with existing NLUResult model *— fulfills R-INV.1*
- `domain: UnifiedDomain` field must exist with same enum values
- `entities: list[Entity]` field must exist with same structure (type, value, confidence, start, end)
- `confidence: float` field must exist in range [0, 1]
- `keywords: list[str]` field must exist

### INV-2: PII Detection Types
PII Service MUST detect at least the same 7 PII types as PIIDetectorLite *— fulfills R-INV.2*
- EMAIL, PHONE, CPF, CNPJ, CREDIT_CARD, SSN, ADDRESS
- Detection MUST return positions (start, end) for each found PII
- Masking MUST support MASK_FULL, MASK_PARTIAL, MASK_REDACT strategies

### INV-3: Approval Decision Format
Approval Core Package MUST produce same ApprovalDecision format as existing approval-service *— fulfills R-INV.3*
- `decision: Literal["approved", "rejected"]`
- `approved_by: str`
- `approved_at: datetime`
- `rejection_reason: str | None`
- Kafka message format must remain compatible

### INV-4: Kafka Topic Contracts
Kafka topic names and message formats MUST NOT change *— fulfills R-INV.4*
- `plan_approvals` topic must exist with same schema
- `plan_approvals_responses` topic must exist with same schema
- `specialist_feedback` topic must exist with same schema
- Message keys must use `plan_id` for partitioning

### INV-5: Intent Envelope Structure
Intent envelope sent to downstream services MUST preserve existing fields *— fulfills R-INV.5*
- `text: str` — original intent text
- `domain: UnifiedDomain` — classified domain
- `entities: list[Entity]` — extracted entities
- `context: Context` — request context (tenant_id, session_id, user_id)
- Adding new fields is allowed, but removing fields is forbidden

### INV-6: Approval Request Lifecycle
Approval request lifecycle MUST remain consistent *— fulfills R-INV.6*
- Status transitions: PENDING → APPROVED or PENDING → REJECTED
- Once APPROVED or REJECTED, status cannot change (no reverting via normal flow)
- Revert is only allowed via Saga compensation (separate flow)
- All status changes must be published to Kafka

### INV-7: Authentication Context
JWT tokens validated by Unified Gateway MUST pass same context to downstream services *— fulfills R-INV.7*
- `user_id` extracted from token subject
- `tenant_id` extracted from token claims
- Downstream services must receive validated user_id and tenant_id in headers
- No re-validation needed in downstream services (trust Unified Gateway)

### INV-8: Rate Limiting Behavior
Rate limiting MUST be applied per-tenant before request reaches downstream services *— fulfills R-INV.8*
- Default: 100 req/min per tenant
- Enterprise: 1000 req/min per tenant
- Trial: 10 req/min per tenant
- Rate limit errors must return HTTP 429 with `Retry-After` header
- Rate limiting state must be stored in Redis with TTL 60s

### INV-9: Original Intent Text Preservation
Original intent text MUST be preserved through the entire pipeline *— fulfills R-INV.9*
- Gateway → NLU Service: original text passed
- NLU Service → Approval: `original_intent_text` field included in ApprovalRequest
- Approval → Feedback: `original_intent_text` included in feedback for ML
- This invariant enables Active Learning and NLP feature extraction

### INV-10: Health Check Compatibility
All services MUST respond to GET /health with format: `{"status": "healthy" | "unhealthy", "version": "str"}` *— fulfills R-INV.10*
- Existing health check monitors must continue working
- Response format must be JSON
- Status field must be "healthy" or "unhealthy"
- Version field must be present

### INV-11: Observability Context
All requests must have distributed tracing context *— fulfills R-INV.11*
- `traceparent` header must be propagated from Unified Gateway to all downstream services
- Span IDs must be recorded for each service call
- Tracing must work across HTTP and gRPC boundaries
- OpenTelemetry format must be used

### INV-12: Graceful Degradation
If shared services (NLU, PII) are down, gateways MUST fall back to local implementations *— fulfills R-INV.12*
- During transition period (Phase 1-3), keep local implementations as fallback
- After transition period (Phase 4+), return 503 Service Unavailable if shared services are down
- Circuit breaker must open after 5 consecutive failures
- Half-open state must allow 3 test requests before closing again

### INV-13: PII Audit Logging
All PII masking operations MUST be logged to MongoDB *— fulfills R-INV.13*
- Collection: `pii_audit_log`
- Fields: `operation`, `text_hash`, `pii_types_found`, `masked_text_hash`, `timestamp`, `user_id`, `tenant_id`
- Logs must be immutable (no updates, no deletes)
- Logs must be retained for 90 days minimum
- This is a NEW invariant (gap identified in codebase review)

### INV-14: PII Unmask Reversibility
PII masking with MASK_REDACT MUST support reversible unmasking *— fulfills R-INV.14*
- Mask ID must be encrypted token containing original PII
- Encryption algorithm: AES-256-GCM
- Key must be stored in Vault (not in code or env vars)
- Unmasking must be audited (log to pii_audit_log)
- This is a NEW invariant (gap identified: unmask reversível not implemented)

## Migration Phases (Timeline)

### Phase 1: Deploy New Services Alongside (Week 1-2)
- Deploy unified-gateway :7999 (no traffic yet)
- Deploy nlu-service :8020 (internal use only)
- Deploy pii-service :8021 (internal use only)
- **Invariants activated:** INV-10, INV-11

### Phase 2: Refactor Existing Services (Week 3-4)
- gateway-intencoes → proxy to NLU/PII services (keep local as fallback)
- requirements-engineering → use NLU service
- doc-ingestion → use PII service
- **Invariants activated:** INV-1, INV-2, INV-12

### Phase 3: Extract Approval Core (Week 5-6)
- Create neural_hive_approval_common package
- Refactor approval-service to use package
- **Invariants activated:** INV-3, INV-6

### Phase 4: Gradual Traffic Shift (Week 7-8)
- 10% → unified-gateway, monitor 24h
- 50% → unified-gateway, monitor 48h
- 100% → unified-gateway
- **Invariants activated:** INV-4, INV-5, INV-7, INV-8

### Phase 5: Deprecate Old Components (Week 9-10)
- Remove local NLU/PII implementations
- Deprecate approval-gateway
- Mark old HTTP endpoints as deprecated
- **Invariants activated:** INV-9, INV-13, INV-14

### Phase 6: Cleanup (Week 11+)
- Remove deprecated endpoints after 30-day grace period
- Remove fallback code from gateways
- **All invariants fully enforced**

## Critical Gaps Identified

1. **PII Unmask Reversível** — Não implementado (5-7 dias de desenvolvimento necessários) *— affects INV-14*
2. **PII Audit Logging Persistente** — Apenas logs em memória (3-4 dias necessários) *— affects INV-13*
3. **gRPC Service Definition for PII** — Protobuf não definido (1-2 dias necessários) *— affects R-PII.5*
4. **Circuit Breaker Implementation** — Stub atual, needs real implementation (2-3 dias) *— affects INV-12*

## Rollback Strategy

If any invariant is violated during migration:
1. Stop traffic shift to unified-gateway
2. Revert to previous stable state (10%, 50%, or 0%)
3. Fix invariant violation
4. Resume migration from last stable state

Rollback must complete within 15 minutes of detecting invariant violation.
