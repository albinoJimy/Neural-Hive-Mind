# Tickets Accionáveis — Top-10 Riscos NHM

> **Task:** T15 - Traduzir riscos em tickets accionáveis para JIRA/GitHub Issues
> **Data:** 2026-04-27
> **Formato:** Estrutura compatível com JIRA e GitHub Issues

---

## Template de Ticket

```markdown
## [TITLE]
**Tipo:** [Bug/Tech Debt/Feature/Compliance]
**Prioridade:** [P0/P1/P2/P3]
**Score:** [Priority Score]
**Esforço Estimado:** [dias]
**Team:** [Responsible Team]

### Descrição
[Descrição detalhada do problema]

### Impacto
- [Impacto no negócio]
- [Impacto técnico]
- [Risco se não resolvido]

### Critérios de Aceite
- [ ] [Critério 1]
- [ ] [Critério 2]
- [ ] [Critério 3]

### Dependencies
- [Ticket ou sistema dependente]

### Referências
- [Link para documentação]
- [Link para gap analysis]
```

---

## Tickets por Risco

### NHM-001: Implementar DLQ no Consensus Engine

**Tipo:** Tech Debt / Bug
**Prioridade:** P0
**Score:** 162/180
**Esforço Estimado:** 3-5 dias
**Team:** Consensus Engine Team
**Epic:** AUDITORIA-FLUXOS-P0
**Sprint:** Sprint 1 (Quick Wins)

#### Descrição
O consensus-engine possui configuração DLQ reservada mas não está funcional. Mensagens com schema inválido ou business error ficam presas no consumer indefinidamente, causando congestionamento e potential data loss.

#### Impacto
- Mensagens com schema inválido bloqueiam o consumer indefinidamente
- Congestionamento do tópico `nhm.decisions`
- Violação de INV-4 (ordem estrita) e INV-8 (non-blocking)
- Impossibilidade de recuperar mensagens falhadas

#### Critérios de Aceite
- [ ] DLQ topic `nhm.decisions.dlq` criado e configurado
- [ ] Consumer envia mensagens inválidas para DLQ com metadata (error, timestamp, retry_count)
- [ ] Métricas de DLQ depth publishadas no Prometheus
- [ ] Alerta configurado para DLQ depth > 100
- [ ] Teste E2E: mensagem inválida é roteada para DLQ
- [ ] Documentação de operação de DLQ recovery

#### Dependencies
- Kafka Team (criar topic DLQ)
- Observability Team (métricas e alertas)

#### Código Reference
```python
# File: consensus-engine/src/consumers/plan_consumer.py
# Adicionar handler de erro:
DLQ_TOPIC = "nhm.decisions.dlq"

async def handle_invalid_message(msg, error):
    await producer.send(DLQ_TOPIC, value={
        "original_message": msg.value,
        "error": str(error),
        "error_type": type(error).__name__,
        "timestamp": datetime.utcnow().isoformat(),
        "retry_count": msg.headers.get("retry_count", 0),
        "original_topic": msg.topic
    })
```

#### Sub-tasks
- [ ] NHM-001-1: Criar DLQ topic configuration
- [ ] NHM-001-2: Implementar DLQ handler no consumer
- [ ] NHM-001-3: Adicionar métricas de DLQ depth
- [ ] NHM-001-4: Configurar alerta Prometheus
- [ ] NHM-001-5: Escrever testes E2E
- [ ] NHM-001-6: Documentar processo de recovery

---

### NHM-002: Integrar PIIMasker no Structlog

**Tipo:** Compliance / Bug
**Prioridade:** P0
**Score:** 151.2/180
**Esforço Estimado:** 2-3 dias
**Team:** Observability Team
**Epic:** AUDITORIA-FLUXOS-P0
**Sprint:** Sprint 2 (GDPR Compliance)

#### Descrição
PII (user_id, email) está a ser logado em plaintext em 11+ endpoints. O componente PIIMasker já existe em `neural_hive_observability` mas não está integrado no structlog configuration.

#### Impacto
- Violação GDPR/LGPD Artigo 32 (Security of Processing)
- Dados pessoais expostos em logs centralizados
- Risco de exposição acidental em dashboards/alerts
- Multas regulatórias até 4% do faturamento

#### Critérios de Aceite
- [ ] PIIMasker integrado em todos os 8 serviços
- [ ] Campos PII mascarados por default (user_id → u***@***, email → e***@***.***)
- [ ] Opção de unmask para debug (flag ENABLE_PII_LOGGING)
- [ ] Teste: log com PII aparece mascarado
- [ ] Documentação de campos PII identificados

#### Dependencies
- Compliance Team (validar campos PII)

#### Código Reference
```python
# File: neural_hive_observability/masking.py (já existe)
# Integrar em cada serviço:

from neural_hive_observability.masking import PIIMasker

PII_FIELDS = ["user_id", "email", "phone", "cpf", "nome"]

masker = PIIMasker(
    fields=PII_FIELDS,
    mask_char="*",
    show_first_n=1,
    show_last_n=3
)

structlog.configure(
    processors=[
        masker.mask_pii,
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer()
    ]
)
```

#### Sub-tasks
- [ ] NHM-002-1: Auditoria de campos PII em todos os logs
- [ ] NHM-002-2: Integrar PIIMasker no gateway-intencoes
- [ ] NHM-002-3: Integrar PIIMasker no consensus-engine
- [ ] NHM-002-4: Integrar PIIMasker no approval-service
- [ ] NHM-002-5: Integrar PIIMasker nos restantes 5 serviços
- [ ] NHM-002-6: Testes unitários de masking
- [ ] NHM-002-7: Documentar flag ENABLE_PII_LOGGING

---

### NHM-003: Implementar Cache-Aside Pattern

**Tipo:** Bug / Tech Debt
**Prioridade:** P0
**Score:** 144/180
**Esforço Estimado:** 3-5 dias
**Team:** Consensus Engine Team
**Epic:** AUDITORIA-FLUXOS-P0
**Sprint:** Sprint 3 (Resiliência)

#### Descrição
consensus-engine e service-registry usam Redis como fonte primária sem fallback MongoDB, violando INV-6 (MongoDB autoritativo, Redis cache).

#### Impacto
- State divergence entre Redis e MongoDB
- Decisões baseadas em dados stale
- Cache hit ratio não monitorado
- Dados inconsistentes em caso de Redis flush

#### Critérios de Aceite
- [ ] Cache-aside pattern implementado em consensus-engine
- [ ] Cache-aside pattern implementado em service-registry
- [ ] Cache invalidation events configurados
- [ ] Métrica de cache hit/miss ratio
- [ ] Teste: fallback para MongoDB funciona
- [ ] Documentação de cache strategy

#### Dependencies
- Data Team (validar schema MongoDB)

#### Código Reference
```python
# File: consensus-engine/src/services/plan_cache.py (NOVO)
class PlanCache:
    def __init__(self, redis, mongo, ttl=300):
        self.redis = redis
        self.mongo = mongo
        self.ttl = ttl

    async def get(self, plan_id: str):
        # Try cache first
        cached = await self.redis.get(f"plan:{plan_id}")
        if cached:
            metrics.cache_hit_counter.inc()
            return json.loads(cached)

        # Fallback to MongoDB (authoritative)
        plan = await self.mongo.plans.find_one({"plan_id": plan_id})
        if plan:
            await self.redis.setex(f"plan:{plan_id}", self.ttl, json.dumps(plan))
        metrics.cache_miss_counter.inc()
        return plan

    async def invalidate(self, plan_id: str):
        await self.redis.delete(f"plan:{plan_id}")
```

#### Sub-tasks
- [ ] NHM-003-1: Criar PlanCache class
- [ ] NHM-003-2: Refactor consensus-engine para usar cache-aside
- [ ] NHM-003-3: Refactor service-registry para usar cache-aside
- [ ] NHM-003-4: Adicionar cache invalidation events
- [ ] NHM-003-5: Métricas de cache hit/miss ratio
- [ ] NHM-003-6: Testes de integração cache/MongoDB

---

### NHM-004: Sincronizar Versões OpenTelemetry

**Tipo:** Bug
**Prioridade:** P0
**Score:** 129.6/180
**Esforço Estimado:** 1 dia
**Team:** Platform Team
**Epic:** AUDITORIA-FLUXOS-P0
**Sprint:** Sprint 1 (Quick Wins)

#### Descrição
libs/python usa OpenTelemetry 1.39.1 mas requirements-base.txt define 1.29.0. Incompatibilidade de tipos em runtime.

#### Impacto
- Type errors em runtime
- Tracing inoperacional
- Impossível debuggar issues

#### Critérios de Aceite
- [ ] Versão sincronizada em 1.39.1 em todos os requirements
- [ ] Teste: import de opentelemetry sem errors
- [ ] CI/CD verifica version consistency

#### Dependencies
- Nenhuma

#### Código Reference
```bash
# File: libs/python/requirements-base.txt
opentelemetry-api==1.39.1
opentelemetry-sdk==1.39.1
opentelemetry-instrumentation-fastapi==0.46b0
opentelemetry-instrumentation-grpc==0.46b0
opentelemetry-exporter-otlp==1.39.1
```

#### Sub-tasks
- [ ] NHM-004-1: Atualizar requirements-base.txt
- [ ] NHM-004-2: Atualizar requirements dos 8 serviços
- [ ] NHM-004-3: Testar imports em dev environment
- [ ] NHM-004-4: Commit e push

---

### NHM-005: Remover time.sleep() em Async Context

**Tipo:** Bug
**Prioridade:** P0
**Score:** 129.6/180
**Esforço Estimado:** 1 dia
**Team:** Consensus Engine Team
**Epic:** AUDITORIA-FLUXOS-P0
**Sprint:** Sprint 1 (Quick Wins)

#### Descrição
3 ocorrências de `time.sleep()` em async context no consensus-engine/src/consumers/plan_consumer.py bloqueiam o event loop.

#### Impacto
- Event loop bloqueado
- Degradation de performance
- Timeouts cascata

#### Critérios de Aceite
- [ ] Todas as ocorrências de time.sleep() substituídas por await asyncio.sleep()
- [ ] Teste: consumer não bloqueia event loop
- [ ] Lint rule adicionada para prevenir futuras ocorrências

#### Dependencies
- Nenhuma

#### Código Reference
```python
# File: consensus-engine/src/consumers/plan_consumer.py
# Antes:
time.sleep(5)

# Depois:
await asyncio.sleep(5)
```

#### Sub-tasks
- [ ] NHM-005-1: Substituir time.sleep() por asyncio.sleep()
- [ ] NHM-005-2: Adicionar lint rule no ruff
- [ ] NHM-005-3: Testes unitários
- [ ] NHM-005-4: Commit

---

### NHM-006: Criar Índices TTL para Dados PII

**Tipo:** Compliance
**Prioridade:** P0
**Score:** 129.6/180
**Esforço Estimado:** 1-2 dias
**Team:** Data Team
**Epic:** AUDITORIA-FLUXOS-P0
**Sprint:** Sprint 1 (Quick Wins)

#### Descrição
Coleções plan_approvals e specialist_feedback não têm índices TTL. RetentionManager existe mas não integrado.

#### Impacto
- Violação GDPR/LGPD retention max 2 anos
- Retenção indevida de dados pessoais
- Multas regulatórias

#### Critérios de Aceite
- [ ] Índice TTL criado em plan_approvals (2 anos)
- [ ] Índice TTL criado em specialist_feedback (2 anos)
- [ ] Migration script validado
- [ ] Teste: documentos expiram após TTL
- [ ] Documentação de retention policy

#### Dependencies
- DBA Team (revisar migration)

#### Código Reference
```python
# File: services/approval-service/src/database/migrations/m002_ttl_indexes.py (NOVO)
async def upgrade():
    # Plan approvals - 2 anos
    await db.plan_approvals.create_index(
        "created_at",
        expireAfterSeconds=63072000,  # 2 * 365 * 24 * 60 * 60
        name="ttl_created_at"
    )

    # Specialist feedback - 2 anos
    await db.specialist_feedback.create_index(
        "created_at",
        expireAfterSeconds=63072000,
        name="ttl_created_at"
    )
```

#### Sub-tasks
- [ ] NHM-006-1: Criar migration m002_ttl_indexes.py
- [ ] NHM-006-2: Testar migration em staging
- [ ] NHM-006-3: Executar migration em produção
- [ ] NHM-006-4: Documentar retention policy

---

### NHM-007: Implementar Correlation ID Middleware

**Tipo:** Tech Debt
**Prioridade:** P0
**Score:** 100.8/180
**Esforço Estimado:** 5-7 dias
**Team:** Observability Team
**Epic:** AUDITORIA-FLUXOS-P0
**Sprint:** Sprint 4 (Observabilidade)

#### Descrição
gRPC calls não propagam correlation_id. worker-agents não geram para tarefas internas.

#### Impacto
- Impossível rastrear requests end-to-end
- Debugging ineficiente
- Violação R-T9.1

#### Critérios de Aceite
- [ ] Middleware gRPC inject correlation_id
- [ ] Worker agents geram correlation_id para tarefas internas
- [ ] Service registry participa da tracing chain
- [ ] Teste E2E: correlation_id propagado através de 3 serviços
- [ ] Documentação de tracing strategy

#### Dependencies
- gRPC Team (revisar interceptor)

#### Código Reference
```python
# File: libs/python/neural_hive_observability/tracing.py (NOVO)
class CorrelationIdInterceptor(grpc.ServerInterceptor):
    def intercept(self, request, context, method_info):
        metadata = dict(context.invocation_metadata())
        correlation_id = metadata.get("correlation-id") or str(uuid4())

        # Inject no context
        context.set_code(grpc.StatusCode.OK)

        # Propagar para downstream
        return self._inject_into_context(request, correlation_id)
```

#### Sub-tasks
- [ ] NHM-007-1: Criar CorrelationIdInterceptor
- [ ] NHM-007-2: Integrar em consensus-engine gRPC server
- [ ] NHM-007-3: Integrar em orchestrator-dynamic gRPC client
- [ ] NHM-007-4: Worker agents geram correlation_id
- [ ] NHM-007-5: Service registry participation
- [ ] NHM-007-6: Testes E2E de tracing
- [ ] NHM-007-7: Documentação

---

### NHM-008: Implementar Circuit Breaker em gRPC

**Tipo:** Tech Debt
**Prioridade:** P0
**Score:** 86.4/180
**Esforço Estimado:** 2-3 dias
**Team:** Resilience Team
**Epic:** AUDITORIA-FLUXOS-P0
**Sprint:** Sprint 3 (Resiliência)

#### Descrição
Chamadas gRPC para especialistas sem circuit breaker. Specialist lento/falhando bloqueia consensus.

#### Impacto
- Cascade failures
- Sistema bloqueado por serviço falhado
- Violação INV-3

#### Critérios de Aceite
- [ ] CircuitBreaker implementado em SpecialistClient
- [ ] Configuração: failure_threshold=5, recovery_timeout=60s
- [ ] Métricas de circuit state (closed/open/half-open)
- [ ] Teste: specialist falhando abre circuit
- [ ] Teste: specialist recuperação fecha circuit

#### Dependencies
- neural_hive_resilience library

#### Código Reference
```python
# File: consensus-engine/src/clients/specialist_client.py
from neural_hive_resilience.circuit_breaker import CircuitBreaker

class SpecialistClient:
    def __init__(self):
        self.cb = CircuitBreaker(
            name="specialist_cb",
            failure_threshold=5,
            recovery_timeout=60,
            expected_exception=grpc.RpcError
        )

    async def call_specialist(self, request):
        try:
            return await self.cb.call(self._grpc_call, request)
        except CircuitOpenError:
            # Fallback ou rejeição graciosa
            return FallbackResponse()
```

#### Sub-tasks
- [ ] NHM-008-1: Implementar CircuitBreaker wrapper
- [ ] NHM-008-2: Integrar em SpecialistClient
- [ ] NHM-008-3: Métricas de circuit state
- [ ] NHM-008-4: Testes de circuit open/close
- [ ] NHM-008-5: Documentação

---

### NHM-009: Configurar Health Checks

**Tipo:** Tech Debt
**Prioridade:** P0
**Score:** 72/180
**Esforço Estimado:** 2 dias
**Team:** Platform Team
**Epic:** AUDITORIA-FLUXOS-P0
**Sprint:** Sprint 1 (Quick Wins)

#### Descrição
0 de 8 serviços com liveness/readiness probes. Kubernetes não detecta pods mortos.

#### Impacto
- Traffic roteado para pods não prontos
- Downtime não detectado
- Violação R-B6.3

#### Critérios de Aceite
- [ ] /health endpoint em todos os 8 serviços
- [ ] /ready endpoint em todos os 8 serviços (verifica DB, Kafka, Redis)
- [ ] Liveness probe configurado em Helm charts
- [ ] Readiness probe configurado em Helm charts
- [ ] Teste: pod não pronto não recebe traffic

#### Dependencies
- K8s Team (Helm charts)

#### Código Reference
```python
# File: services/<service>/src/api/health.py (NOVO)
from fastapi import FastAPI

router = APIRouter()

@router.get("/health")
async def liveness():
    return {"status": "ok"}

@router.get("/ready")
async def readiness(db: MongoClient = Depends(get_db)):
    # Verificar dependências
    try:
        await db.command("ping")
        return {"status": "ready", "dependencies": {"mongodb": "ok"}}
    except Exception:
        raise HTTPException(status_code=503, detail="Not ready")
```

```yaml
# File: helm/<service>/templates/deployment.yaml
livenessProbe:
  httpGet:
    path: /health
    port: http
  initialDelaySeconds: 30
  periodSeconds: 10

readinessProbe:
  httpGet:
    path: /ready
    port: http
  initialDelaySeconds: 10
  periodSeconds: 5
```

#### Sub-tasks
- [ ] NHM-009-1: Criar health.py router
- [ ] NHM-009-2: Integrar nos 8 serviços
- [ ] NHM-009-3: Atualizar Helm charts
- [ ] NHM-009-4: Testar em staging
- [ ] NHM-009-5: Deploy produção

---

### NHM-010: Implementar Right to Erasure

**Tipo:** Compliance / Feature
**Prioridade:** P0
**Score:** 64/180
**Esforço Estimado:** 3-5 dias
**Team:** Compliance Team
**Epic:** AUDITORIA-FLUXOS-P0
**Sprint:** Sprint 2 (GDPR Compliance)

#### Descrição
Endpoint para deleção GDPR/LGPD Article 17 não existe. Usuário não pode solicitar exclusão.

#### Impacto
- Violação GDPR/LGPD Artigo 17
- Multas até 4% do faturamento
- Ações judiciais

#### Critérios de Aceite
- [ ] POST /api/v1/gdpr/erasure-request
- [ ] GET /api/v1/gdpr/erasure-request/{id}
- [ ] Processamento assíncrono via Kafka
- [ ] Notificação do usuário por email
- [ ] Relatório de deleção gerado
- [ ] Teste E2E: request → processamento → confirmação

#### Dependencies
- Data Team (deleção MongoDB)
- API Team (endpoint)
- Notification Team (email)

#### Código Reference
```python
# File: services/approval-service/src/api/routers/gdpr.py (NOVO)
@router.post("/erasure-request")
async def request_erasure(
    user_id: str,
    reason: str,
    db: MongoClient = Depends(get_db)
):
    # Validar identidade
    if not await _verify_user_identity(user_id):
        raise HTTPException(401, "Unauthorized")

    # Criar ticket de deleção
    ticket = await db.erasure_requests.insert_one({
        "user_id": user_id,
        "reason": reason,
        "status": "pending",
        "created_at": datetime.utcnow(),
        "request_id": str(uuid4())
    })

    # Enfileirar para processamento
    await kafka.send("nhm.gdpr.erasure", value={
        "request_id": ticket.inserted_id,
        "user_id": user_id
    })

    return {"request_id": str(ticket.inserted_id)}
```

#### Sub-tasks
- [ ] NHM-010-1: Criar modelo ErasureRequest
- [ ] NHM-010-2: Implementar POST /erasure-request
- [ ] NHM-010-3: Implementar GET /erasure-request/{id}
- [ ] NHM-010-4: Consumer Kafka para processamento
- [ ] NHM-010-5: Deleção de dados em MongoDB
- [ ] NHM-010-6: Notificação por email
- [ ] NHM-010-7: Testes E2E
- [ ] NHM-010-8: Documentação GDPR

---

## Tabela Consolidada

| ID | Ticket | Prioridade | Score | Esforço | Sprint | Team |
|----|--------|------------|-------|---------|--------|------|
| NHM-001 | DLQ Consensus Engine | P0 | 162 | 3-5d | Sprint 3 | Consensus Engine |
| NHM-002 | PII Masking | P0 | 151.2 | 2-3d | Sprint 2 | Observability |
| NHM-003 | Cache-Aside Pattern | P0 | 144 | 3-5d | Sprint 3 | Consensus Engine |
| NHM-004 | OpenTelemetry Sync | P0 | 129.6 | 1d | Sprint 1 | Platform |
| NHM-005 | time.sleep() Fix | P0 | 129.6 | 1d | Sprint 1 | Consensus Engine |
| NHM-006 | TTL PII Indexes | P0 | 129.6 | 1-2d | Sprint 1 | Data |
| NHM-007 | Correlation ID | P0 | 100.8 | 5-7d | Sprint 4 | Observability |
| NHM-008 | Circuit Breaker | P0 | 86.4 | 2-3d | Sprint 3 | Resilience |
| NHM-009 | Health Checks | P0 | 72 | 2d | Sprint 1 | Platform |
| NHM-010 | Right to Erasure | P0 | 64 | 3-5d | Sprint 2 | Compliance |

---

## Sprint Planning

### Sprint 1: Quick Wins (Semana 1-2)
- NHM-004: OpenTelemetry Sync (1d)
- NHM-005: time.sleep() Fix (1d)
- NHM-006: TTL PII Indexes (1-2d)
- NHM-009: Health Checks (2d)

**Total:** 5-6 dias
**Capacity:** 2 engineers

### Sprint 2: GDPR Compliance (Semana 3-4)
- NHM-002: PII Masking (2-3d)
- NHM-010: Right to Erasure (3-5d)

**Total:** 5-8 dias
**Capacity:** 2 engineers

### Sprint 3: Resiliência (Semana 5-7)
- NHM-008: Circuit Breaker (2-3d)
- NHM-001: DLQ (3-5d)
- NHM-003: Cache-Aside (3-5d)

**Total:** 8-13 dias
**Capacity:** 3 engineers

### Sprint 4: Observabilidade (Semana 8-9)
- NHM-007: Correlation ID (5-7d)

**Total:** 5-7 dias
**Capacity:** 2 engineers

---

**Documento compilado por:** Orchestrator (Round 2, Task T15)
**Data:** 2026-04-27
**Próxima tarefa:** T16 - Estruturar relatório para tech lead
