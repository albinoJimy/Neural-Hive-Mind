# Epic: Unified Gateway e Arquitetura Compartilhada

**Epic ID:** EPIC-2026-05-01-001
**Priority:** P0 - Crítica
**Timeline:** 10 semanas
**Status:** Planning

---

## Resumo do Epic

Implementar arquitetura unificada com Unified Gateway (:7999) como ponto único de entrada, serviços compartilhados (NLU :8020, PII :8021) e eliminação de >3.000 LOC de duplicações em toda a codebase.

---

## Tickets (Decomposição Completa)

### FASE 1: Fundação e Infraestrutura (Sprint 1 - 2 semanas)

#### [TICKET-001] Criar estrutura do projeto Unified Gateway
- **Tipo:** Feature
- **Prioridade:** P0
- **Estimativa:** 1 dia
- **Responsável:** Backend Team
- **Dependências:** Nenhuma
- **Descrição:**
  - Criar diretório `services/unified-gateway/`
  - Setup FastAPI structure
  - Configurar Dockerfile
  - Configurar Helm charts
  - Setup test structure
- **Acceptance Criteria:**
  - ✅ Estrutura de projeto criada
  - ✅ Docker build funcionando
  - ✅ Tests unitários executando
- **Arquivos:**
  - `services/unified-gateway/src/main.py`
  - `services/unified-gateway/Dockerfile`
  - `services/unified-gateway/pyproject.toml`

#### [TICKET-002] Implementar Authentication Middleware
- **Tipo:** Feature
- **Prioridade:** P0
- **Estimativa:** 2 dias
- **Responsável:** Backend Team
- **Dependências:** TICKET-001
- **Descrição:**
  - JWT verification (usar `neural_hive_security`)
  - API Key validation
  - OAuth2/OIDC support (opcional)
  - Security headers (consolidar `SecurityHeadersMiddleware`)
  - User context extraction
- **Acceptance Criteria:**
  - ✅ JWT tokens validados corretamente
  - ✅ API keys validadas
  - ✅ Security headers aplicados
  - ✅ User context extraído e disponível
  - ✅ Testes unitários + integração
- **Arquivos:**
  - `services/unified-gateway/src/middleware/auth.py`
  - `services/unified-gateway/src/security/jwt_verifier.py`
  - `services/unified-gateway/tests/test_auth.py`

#### [TICKET-003] Implementar Rate Limiting Middleware
- **Tipo:** Feature
- **Prioridade:** P0
- **Estimativa:** 2 dias
- **Responsável:** Backend Team
- **Dependências:** TICKET-001
- **Descrição:**
  - Token bucket algorithm
  - Redis-backed state
  - Configuração por tenant
  - IP-based + API key-based limiting
  - Response headers (X-RateLimit-*)
- **Acceptance Criteria:**
  - ✅ Rate limiting ativo e funcionando
  - ✅ Redis state persistente
  - ✅ Headers de rate limit nas respostas
  - ✅ Testes de carga
- **Arquivos:**
  - `services/unified-gateway/src/middleware/rate_limit.py`
  - `services/unified-gateway/src/redis_client.py`
  - `services/unified-gateway/tests/test_rate_limit.py`

#### [TICKET-004] Implementar Context Builder
- **Tipo:** Feature
- **Prioridade:** P0
- **Estimativa:** 2 dias
- **Responsável:** Backend Team
- **Dependências:** TICKET-002
- **Descrição:**
  - Integrar `neural_hive_context.services.ContextManager`
  - Tenant context loading
  - Session context building
  - Request context enrichment
  - Cache de contextos (Redis)
- **Acceptance Criteria:**
  - ✅ Contexto rico construído para cada request
  - ✅ Cache funcionando (TTL 300s)
  - ✅ Tenant settings aplicados
  - ✅ Testes unitários
- **Arquivos:**
  - `services/unified-gateway/src/services/context_builder.py`
  - `services/unified-gateway/src/services/tenant_loader.py`

#### [TICKET-005] Setup Observabilidade (Tracing, Metrics, Logs)
- **Tipo:** Feature
- **Prioridade:** P0
- **Estimativa:** 1 dia
- **Responsável:** DevOps Team
- **Dependências:** TICKET-001
- **Descrição:**
  - OpenTelemetry tracing
  - Prometheus metrics
  - Structured logging (structlog)
  - Trace propagation para downstream
- **Acceptance Criteria:**
  - ✅ Traces visíveis no Jaeger/Tempo
  - ✅ Metrics no Prometheus
  - ✅ Logs estruturados no Loki/ELK
  - ✅ Trace propagation funcionando
- **Arquivos:**
  - `services/unified-gateway/src/observability/tracing.py`
  - `services/unified-gateway/src/observability/metrics.py`
  - `services/unified-gateway/src/observability/logging.py`

---

### FASE 2: NLU Service (Sprint 1-2 - 2 semanas)

#### [TICKET-006] Criar NLU Service estrutura
- **Tipo:** Feature
- **Prioridade:** P0
- **Estimativa:** 1 dia
- **Responsável:** Backend Team
- **Descrição:**
  - Criar `services/nlu-service/`
  - Setup FastAPI + gRPC server
  - Dockerfile + Helm charts
  - Test structure
- **Acceptance Criteria:**
  - ✅ Serviço criado com HTTP + gRPC
  - ✅ Health check funcionando
  - ✅ Tests executando
- **Arquivos:**
  - `services/nlu-service/src/main.py`
  - `services/nlu-service/src/grpc/nlu_pb2.py`
  - `services/nlu-service/proto/nlu.proto`

#### [TICKET-007] Extrair NLU Pipeline do gateway-intencoes
- **Tipo:** Refactor
- **Prioridade:** P0
- **Estimativa:** 3 dias
- **Responsável:** Backend Team
- **Dependências:** TICKET-006
- **Descrição:**
  - Mover `nlu_pipeline.py` (1.302 LOC) para NLU Service
  - Limpar dependências do gateway
  - Criar interface limpa
  - Adapter para gRPC
- **Acceptance Criteria:**
  - ✅ NLU pipeline movido sem quebras
  - ✅ gRPC service funcionando
  - ✅ Tests migrados e passando
  - ✅ gateway-intencoes ainda funciona (usa NLU Service)
- **Arquivos:**
  - `services/nlu-service/src/services/nlu_pipeline.py`
  - `services/nlu-service/src/grpc/nlu_servicer.py`

#### [TICKET-008] Implementar NLU API endpoints
- **Tipo:** Feature
- **Prioridade:** P0
- **Estimativa:** 2 dias
- **Responsável:** Backend Team
- **Dependências:** TICKET-007
- **Descrição:**
  - `POST /api/v1/nlu/parse`
  - `POST /api/v1/nlu/classify-domain`
  - `POST /api/v1/nlu/extract-entities`
  - `POST /api/v1/nlu/calculate-confidence`
  - gRPC equivalents
- **Acceptance Criteria:**
  - ✅ Todos endpoints funcionando
  - ✅ gRPC server respondendo
  - ✅ OpenAPI docs geradas
  - ✅ Testes de integração
- **Arquivos:**
  - `services/nlu-service/src/api/routes/nlu.py`
  - `services/nlu-service/src/grpc/nlu_servicer.py`

#### [TICKET-009] Implementar Cache Redis no NLU Service
- **Tipo:** Feature
- **Prioridade:** P1
- **Estimativa:** 1 dia
- **Responsável:** Backend Team
- **Dependências:** TICKET-008
- **Descrição:**
  - Cache de resultados NLU
  - TTL configurável (default 3600s)
  - Cache key hash do input
  - Invalidation strategy
- **Acceptance Criteria:**
  - ✅ Cache funcionando
  - ✅ Hit rate >70% em testes
  - ✅ Invalidation funcionando
- **Arquivos:**
  - `services/nlu-service/src/cache/nlu_cache.py`

#### [TICKET-010] Atualizar gateway-intencoes para usar NLU Service
- **Tipo:** Refactor
- **Prioridade:** P0
- **Estimativa:** 2 dias
- **Responsável:** Backend Team
- **Dependências:** TICKET-008
- **Descrição:**
  - Remover NLU interno (1.302 LOC)
  - Chamar NLU Service via gRPC
  - Fallback para NLU local se service down
  - Tests de integração
- **Acceptance Criteria:**
  - ✅ gateway-intencoes usando NLU Service
  - ✅ ~800 LOC removidos
  - ✅ Fallback funcionando
  - ✅ Tests E2E passando
- **Arquivos:**
  - `services/gateway-intencoes/src/services/nlu_client.py` (NOVO)
  - `services/gateway-intencoes/src/pipelines/nlu_pipeline.py` (REMOVIDO)

#### [TICKET-011] Atualizar requirements-engineering para usar NLU Service
- **Status:** ✅ Concluído por design (N/A) — 2026-05-10
- **Tipo:** Refactor
- **Prioridade:** P0
- **Estimativa:** 1 dia
- **Responsável:** Backend Team
- **Dependências:** TICKET-008
- **Descrição:**
  - Remover NLU interno
  - Chamar NLU Service via gRPC
  - Tests
- **Acceptance Criteria:**
  - ✅ requirements-engineering usando NLU Service
  - ✅ ~300 LOC removidos
  - ✅ Tests passando
- **Nota de Fecho (Codebase Review 2026-05-04 + verificação 2026-05-10):**
  O serviço `requirements-engineering` não usa nenhum pipeline NLU local
  (zero referências a spaCy, classificação de domínio ou NER em `src/`).
  O processamento é integralmente feito via LLM em `services/requirements_engineer.py`
  sobre planos cognitivos já estruturados — não há texto bruto para classificar.
  Criar um cliente NLU sem consumidor seria over-engineering. Ticket fechado
  como não aplicável; a spec já reflete `0 LOC` no Expected Deliverable.
- **Arquivos:**
  - `services/requirements-engineering/src/clients/nlu_client.py`

---

### FASE 3: PII Service (Sprint 2-3 - 2 semanas)

#### [TICKET-012] Criar PII Service estrutura
- **Tipo:** Feature
- **Prioridade:** P0
- **Estimativa:** 1 dia
- **Responsável:** Backend Team
- **Descrição:**
  - Criar `services/pii-service/`
  - FastAPI + gRPC server
  - Dockerfile + Helm charts
  - Auth requirement (todos endpoints)
- **Acceptance Criteria:**
  - ✅ Serviço criado
  - ✅ Auth obrigatório funcionando
  - ✅ Tests structure
- **Arquivos:**
  - `services/pii-service/src/main.py`

#### [TICKET-013] Consolidar PII implementations
- **Tipo:** Refactor
- **Prioridade:** P0
- **Estimativa:** 3 dias
- **Responsável:** Backend Team
- **Dependências:** TICKET-012
- **Descrição:**
  - Mover PII de `neural_hive_specialists` (447 LOC)
  - Consolidar com `neural_hive_context` (395 LOC)
  - Criar implementação unificada
  - Suportar variações (angolan, etc)
- **Acceptance Criteria:**
  - ✅ PII unificado criado
  - ✅ 7 tipos de PII detectados
  - ✅ Testes consolidados
- **Arquivos:**
  - `services/pii-service/src/services/pii_detector.py`
  - `services/pii-service/src/services/pii_masker.py`

#### [TICKET-014] Implementar PII API endpoints
- **Tipo:** Feature
- **Prioridade:** P0
- **Estimativa:** 2 dias
- **Responsável:** Backend Team
- **Dependências:** TICKET-013
- **Descrição:**
  - `POST /api/v1/pii/detect`
  - `POST /api/v1/pii/mask`
  - `POST /api/v1/pii/unmask` (auth required)
  - `GET /api/v1/pii/health`
  - gRPC equivalents
  - Audit logging para todas as operações
- **Acceptance Criteria:**
  - ✅ Endpoints funcionando
  - ✅ Audit logging ativo
  - ✅ >95% precisão detecção
  - ✅ Tests de segurança
- **Arquivos:**
  - `services/pii-service/src/api/routes/pii.py`
  - `services/pii-service/src/audit/logger.py`

#### [TICKET-015] Atualizar gateway-intencoes para usar PII Service
- **Tipo:** Refactor
- **Prioridade:** P0
- **Estimativa:** 1 dia
- **Responsável:** Backend Team
- **Dependências:** TICKET-014
- **Descrição:**
  - Remover PII interno
  - Chamar PII Service via gRPC
  - Tests
- **Acceptance Criteria:**
  - ✅ gateway-intencoes usando PII Service
  - ✅ ~150 LOC removidos
- **Arquivos:**
  - `services/gateway-intencoes/src/clients/pii_client.py`

#### [TICKET-016] Atualizar doc-ingestion para usar PII Service
- **Tipo:** Refactor
- **Prioridade:** P0
- **Estimativa:** 1 dia
- **Responsável:** Backend Team
- **Dependências:** TICKET-014
- **Descrição:**
  - Remover PII interno
  - Chamar PII Service via gRPC
  - Tests
- **Acceptance Criteria:**
  - ✅ doc-ingestion usando PII Service
  - ✅ LOC reduzidos
- **Arquivos:**
  - `services/doc-ingestion/src/clients/pii_client.py`

---

### FASE 4: Approval Core Package (Sprint 3-4 - 2 semanas)

#### [TICKET-017] Criar neural_hive_approval_common package
- **Tipo:** Feature
- **Prioridade:** P0
- **Estimativa:** 1 dia
- **Responsável:** Backend Team
- **Descrição:**
  - Criar `libraries/python/neural_hive_approval_common/`
  - Setup package structure
  - pyproject.toml
  - Test structure
  - Publish pipeline (pypi interno)
- **Acceptance Criteria:**
  - ✅ Package criado
  - ✅ Instalável via pip
  - ✅ Tests structure
- **Arquivos:**
  - `libraries/python/neural_hive_approval_common/pyproject.toml`
  - `libraries/python/neural_hive_approval_common/neural_hive_approval_common/__init__.py`

#### [TICKET-018] Criar modelos unificados de Approval
- **Status:** ✅ Concluído — 2026-05-10
- **Tipo:** Feature
- **Prioridade:** P0
- **Estimativa:** 2 dias
- **Responsável:** Backend Team
- **Dependências:** TICKET-017
- **Descrição:**
  - UnifiedApprovalRequest (combina approval-service + approval-gateway)
  - UnifiedApprovalDecision
  - CommonStatus (PENDING, APPROVED, REJECTED, CANCELLED, EXPIRED)
  - RiskBand (LOW, MEDIUM, HIGH, CRITICAL)
  - Pydantic models + Protobuf
- **Acceptance Criteria:**
  - ✅ Modelos unificados criados
  - ✅ Pydantic + Protobuf sync
  - ✅ Tests de validação
- **Nota de Fecho (2026-05-10):**
  - `proto/approval.proto` criado com mensagens `UnifiedApprovalRequest`,
    `UnifiedApprovalDecision`, `ApprovalResponse` e enums `RiskBand`,
    `ApprovalStatus`, `Decision`.
  - `neural_hive_approval_common/proto/approval_pb2.py` gerado via
    `grpc_tools.protoc`.
  - `tests/test_proto_sync.py` (5 testes) garante paridade dos enums entre
    Pydantic e proto — falha se um lado adicionar/renomear valor sem o outro.
  - `CommonStatus` (alias de `ApprovalStatus`) já incluía `CANCELLED` e
    `EXPIRED` no commit `41bf9876`.
- **Arquivos:**
  - `libraries/python/neural_hive_approval_common/proto/approval.proto`
  - `libraries/python/neural_hive_approval_common/neural_hive_approval_common/proto/approval_pb2.py`
  - `libraries/python/neural_hive_approval_common/neural_hive_approval_common/proto/approval_pb2.pyi`
  - `libraries/python/neural_hive_approval_common/neural_hive_approval_common/models.py`
  - `libraries/python/neural_hive_approval_common/tests/test_proto_sync.py`

#### [TICKET-019] Extrair lógica de decisão central
- **Tipo:** Refactor
- **Prioridade:** P0
- **Estimativa:** 3 dias
- **Responsável:** Backend Team
- **Dependências:** TICKET-018
- **Descrição:**
  - ApprovalDecisionEngine (abstrair lógica comum)
  - ThresholdEvaluator
  - RiskAssessor
  - CommonRules (critical items, destructive ops)
  - Separar ML vs LLM vs rule-based
- **Acceptance Criteria:**
  - ✅ Lógica central extraída
  - ✅ ~500 LOC consolidados
  - ✅ Tests unificados
- **Arquivos:**
  - `libraries/python/neural_hive_approval_common/core/engine.py`
  - `libraries/python/neural_hive_approval_common/core/thresholds.py`
  - `libraries/python/neural_hive_approval_common/core/rules.py`

#### [TICKET-020] Atualizar approval-service para usar Approval Core
- **Tipo:** Refactor
- **Prioridade:** P0
- **Estimativa:** 3 dias
- **Responsável:** Backend Team
- **Dependências:** TICKET-019
- **Descrição:**
  - Migrar para UnifiedApprovalRequest/Decision
  - Usar ApprovalDecisionEngine
  - Remover código duplicado
  - Tests de regressão
- **Acceptance Criteria:**
  - ✅ approval-service usando Approval Core
  - ✅ ~1.000 LOC removidos
  - ✅ Tests E2E passando
- **Arquivos:**
  - `services/approval-service/src/services/approval_service.py` (REFACTOR)

#### [TICKET-021] Deprecar approval-gateway
- **Tipo:** Refactor
- **Prioridade:** P1
- **Estimativa:** 2 dias
- **Responsável:** Backend Team
- **Dependências:** TICKET-020
- **Descrição:**
  - Migrar clientes para approval-service
  - Configurar redirect temporário
  - Marcar como DEPRECATED
  - Documentar migração
- **Acceptance Criteria:**
  - ✅ approval-gateway deprecated
  - ✅ Clients migrados
  - ✅ Documentação atualizada
- **Arquivos:**
  - `services/approval-gateway/README.md` (DEPRECATION NOTICE)

---

### FASE 5: Intent Classifier e Flow Router (Sprint 4 - 2 semanas)

#### [TICKET-022] Implementar Intent Classifier
- **Tipo:** Feature
- **Prioridade:** P0
- **Estimativa:** 4 dias
- **Responsável:** Backend Team
- **Dependências:** TICKET-004, TICKET-009
- **Descrição:**
  - Integrar NLU Service via gRPC
  - Workflow classification (A-F vs G vs H)
  - Multi-signal classifier (keywords, entities, context)
  - Confidence calculation
  - Reasoning generation
- **Acceptance Criteria:**
  - ✅ Classifier funcionando
  - ✅ >90% precisão em testes
  - ✅ Reasoning explicado
  - ✅ Tests unitários + integração
- **Arquivos:**
  - `services/unified-gateway/src/classifiers/intent_classifier.py`
  - `services/unified-gateway/src/classifiers/flow_router.py`

#### [TICKET-023] Implementar Flow Router (Proxy Layer)
- **Tipo:** Feature
- **Prioridade:** P0
- **Estimativa:** 3 dias
- **Responsável:** Backend Team
- **Dependências:** TICKET-022
- **Descrição:**
  - HTTP/gRPC proxy para gateways específicos
  - Roteamento:
    - A-F → gateway-intencoes :8000
    - G → requirements-engineering :8010
    - H → doc-ingestion :8018
  - Timeout management
  - Retry logic
  - Circuit breaker
  - Response aggregation
- **Acceptance Criteria:**
  - ✅ Proxy funcionando para todos os fluxos
  - ✅ Circuit breaker ativo
  - ✅ Retry logic funcionando
  - ✅ Tests de falha
- **Arquivos:**
  - `services/unified-gateway/src/proxy/flow_router.py`
  - `services/unified-gateway/src/resilience/circuit_breaker.py`

#### [TICKET-024] Implementar Response Processor
- **Tipo:** Feature
- **Prioridade:** P0
- **Estimativa:** 2 dias
- **Responsável:** Backend Team
- **Dependências:** TICKET-023
- **Descrição:**
  - Formatar resposta para cliente
  - Adicionar metadata (execution_time, request_id)
  - Publicar evento Kafka (request.completed)
  - Suportar HTTP + SSE
- **Acceptance Criteria:**
  - ✅ Resposta formatada consistentemente
  - ✅ Eventos Kafka publicados
  - ✅ SSE funcionando
  - ✅ Tests
- **Arquivos:**
  - `services/unified-gateway/src/processors/response.py`
  - `services/unified-gateway/src/processors/sse.py`

#### [TICKET-025] Implementar endpoint principal /api/v1/nhm/request
- **Tipo:** Feature
- **Prioridade:** P0
- **Estimativa:** 2 dias
- **Responsável:** Backend Team
- **Dependências:** TICKET-024
- **Descrição:**
  - POST /api/v1/nhm/request
  - GET /api/v1/nhm/status/{request_id}
  - GET /api/v1/nhm/stream/{request_id} (SSE)
  - Webhook support
  - Async response handling
- **Acceptance Criteria:**
  - ✅ Endpoint principal funcionando
  - ✅ SSE streaming funcionando
  - ✅ Webhooks funcionando
  - ✅ OpenAPI docs
- **Arquivos:**
  - `services/unified-gateway/src/api/routes/nhm.py`

---

### FASE 6: Testes E2E e Hardening (Sprint 5 - 1 semana)

#### [TICKET-026] Testes E2E - Fluxo A-F
- **Tipo:** Test
- **Prioridade:** P0
- **Estimativa:** 2 dias
- **Responsável:** QA Team
- **Dependências:** TICKET-025
- **Descrição:**
  - Teste E2E completo: Request → Unified Gateway → gateway-intencoes → ... → Response
  - Validar classificação correta
  - Validar roteamento correto
  - Validar resposta formatada
- **Acceptance Criteria:**
  - ✅ Teste E2E passando
  - ✅ Coverage >80%
- **Arquivos:**
  - `tests/e2e/test_flow_af.py`

#### [TICKET-027] Testes E2E - Fluxo G
- **Tipo:** Test
- **Prioridade:** P0
- **Estimativa:** 2 dias
- **Responsável:** QA Team
- **Dependências:** TICKET-025
- **Descrição:**
  - Teste E2E completo: Request → Unified Gateway → requirements-engineering → ...
- **Acceptance Criteria:**
  - ✅ Teste E2E passando
- **Arquivos:**
  - `tests/e2e/test_flow_g.py`

#### [TICKET-028] Testes E2E - Fluxo H
- **Tipo:** Test
- **Prioridade:** P0
- **Estimativa:** 2 dias
- **Responsável:** QA Team
- **Dependências:** TICKET-025
- **Descrição:**
  - Teste E2E completo: Request → Unified Gateway → doc-ingestion → ...
- **Acceptance Criteria:**
  - ✅ Teste E2E passando
- **Arquivos:**
  - `tests/e2e/test_flow_h.py`

#### [TICKET-029] Testes de carga e performance
- **Tipo:** Test
- **Prioridade:** P0
- **Estimativa:** 2 dias
- **Responsável:** QA Team
- **Dependências:** TICKET-025
- **Descrição:**
  - Load test (200 req/s)
  - Latência test (<20ms adicional p95)
  - Stress test (falhas graciosas)
  - Sustained load test (1 hora)
- **Acceptance Criteria:**
  - ✅ <20ms latência adicional
  - ✅ >200 req/s sustentados
  - ✅ Falhas graciosas funcionando
- **Arquivos:**
  - `tests/performance/load_test.py`

#### [TICKET-030] Testes de segurança
- **Tipo:** Test
- **Prioridade:** P0
- **Estimativa:** 2 dias
- **Responsável:** Security Team
- **Dependências:** TICKET-025
- **Descrição:**
  - Auth bypass tests
  - Rate limit bypass tests
  - PII leakage tests
  - Injection attacks
  - DoS tests
- **Acceptance Criteria:**
  - ✅ Zero vulnerabilidades críticas
  - ✅ Rate limit não bypassável
  - ✅ PII protegido
- **Arquivos:**
  - `tests/security/test_auth.py`
  - `tests/security/test_rate_limit.py`
  - `tests/security/test_pii.py`

---

### FASE 7: Documentação e Deploy (Sprint 6 - 1 semana)

#### [TICKET-031] Documentação de API
- **Tipo:** Docs
- **Prioridade:** P0
- **Estimativa:** 2 dias
- **Responsável:** Tech Writer
- **Dependências:** TICKET-025
- **Descrição:**
  - OpenAPI 3.0 specs
  - Exemplos de requests/responses
  - Guia de autenticação
  - Guia de rate limiting
  - Error codes
- **Acceptance Criteria:**
  - ✅ OpenAPI specs completas
  - ✅ Documentação publicada
- **Arquivos:**
  - `services/unified-gateway/docs/openapi.yaml`
  - `docs/API_UNIFIED_GATEWAY.md`

#### [TICKET-032] Guia de migração para clientes
- **Tipo:** Docs
- **Prioridade:** P0
- **Estimativa:** 1 dia
- **Responsável:** Tech Writer
- **Descrição:**
  - Como migrar da interface antiga
  - Exemplos de código
  - Backward compatibility
  - Timeline de deprecamento
- **Acceptance Criteria:**
  - ✅ Guia publicado
  - ✅ Exemplos funcionando
- **Arquivos:**
  - `docs/MIGRATION_GUIDE_CLIENTS.md`

#### [TICKET-033] Runbooks operacionais
- **Tipo:** Docs
- **Prioridade:** P1
- **Estimativa:** 1 dia
- **Responsável:** DevOps Team
- **Descrição:**
  - Deploy runbook
  - Rollback runbook
  - Troubleshooting guide
  - Alerting setup
- **Acceptance Criteria:**
  - ✅ Runbooks criados
  - ✅ Alerts configurados
- **Arquivos:**
  - `docs/runbooks/DEPLOY_UNIFIED_GATEWAY.md`
  - `docs/runbooks/TROUBLESHOOTING.md`

#### [TICKET-034] Deploy staging
- **Tipo:** Deploy
- **Prioridade:** P0
- **Estimativa:** 1 dia
- **Responsável:** DevOps Team
- **Dependências:** TICKET-030
- **Descrição:**
  - Deploy de todos os serviços em staging
  - Smoke tests
  - Monitorização por 48h
- **Acceptance Criteria:**
  - ✅ Deploy staging funcionando
  - ✅ Smoke tests passando
  - ✅ 48h stable
- **Arquivos:**
  - `helm/unified-gateway/`
  - `helm/nlu-service/`
  - `helm/pii-service/`

#### [TICKET-035] Deploy produção (Blue-Green)
- **Tipo:** Deploy
- **Prioridade:** P0
- **Estimativa:** 1 dia
- **Responsável:** DevOps Team
- **Dependências:** TICKET-034
- **Descrição:**
  - Blue-Green deploy
  - Gradual traffic shift (10% → 50% → 100%)
  - Monitorização contínua
  - Rollback plan pronto
- **Acceptance Criteria:**
  - ✅ Deploy produção funcionando
  - ✅ Zero downtime
  - ✅ Rollback testado
- **Arquivos:**
  - `helm/production/`

---

## Métricas de Sucesso do Epic

| Métrica | Meta | Como Medir |
|---------|------|------------|
| LOC duplicação removida | >3.000 | SonarQube / git diff |
| Latência adicional | <20ms p95 | Load tests |
| Precisão classificação | >90% | Testes de classificação |
| Test coverage | >80% | pytest-cov |
| Zero vuln críticas | 100% | Security scans |
| Uptime após deploy | >99.9% | Uptime monitoring |

---

## Timeline Visual

```
Sprint 1 (Sem 1-2):  ████████████░░░░░░░░░░░░░░░░░░░░░░░░░░
Sprint 2 (Sem 3-4):  ░░░░░░░░░░░░░░████████████░░░░░░░░░░░░░░
Sprint 3 (Sem 5-6):  ░░░░░░░░░░░░░░░░░░░░░░████████████░░░░░░░
Sprint 4 (Sem 7-8):  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░████████░░
Sprint 5 (Sem 9):    ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░██
Sprint 6 (Sem 10):   ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░

Sem: 1    2    3    4    5    6    7    8    9    10
```

---

## Riscos e Bloqueadores

| Risco | Impacto | Mitigação | Responsável |
|-------|---------|-----------|-------------|
| NLU Service downtime | Alto | Fallback para NLU local | Backend |
| Performance degradation | Alto | Load testing agressivo | QA |
| Breaking change clientes | Alto | Período de grace + compatibilidade | Backend |
| Deploy complexo | Médio | Blue-Green + rollback | DevOps |

---

## References

- Spec completo: `.agent-os/specs/2026-05-01-unified-gateway-architecture/spec.md`
- Arquitetura: `docs/ARQUITETURA_COEXISTENCIA_FLUXOS_2026-05-01.md`
- Mapeamento: `docs/MAPEAMENTO_COMPLETO_CODEBASE_2026-05-01.md`
