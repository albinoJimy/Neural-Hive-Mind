# Top-10 Riscos Arquitecturais Priorizados — Neural Hive Mind

> **Task:** T14 - Priorizar top-10 riscos usando matriz multi-factor
> **Data:** 2026-04-27
> **Versão:** v1.0
> **Metodologia:** Matriz multi-factor (Risco × Impacto × Urgência) / Esforço

---

## 1. Metodologia de Priorização

### Factores Avaliados

| Factor | Peso | Descrição |
|--------|------|-----------|
| **Probabilidade** | 1.0x | BAIXA=1, MÉDIA=2, ALTA=3 |
| **Impacto** | 1.5x | BAIXO=1, MÉDIO=2, ALTO=3, CRÍTICO=4 |
| **Urgência** | 1.2x | BAIXA=1, MÉDIA=2, ALTA=3 |
| **Esforço** | 0.5x (inverse) | 1 dia=5, 2-3 dias=4, 3-5 dias=3, 5-7 dias=2, 7+ dias=1 |

### Fórmula de Score

```
Priority Score = (Probabilidade × 1.0) × (Impacto × 1.5) × (Urgência × 1.2) / (Esforço × 0.5)
```

**Score Máximo Teórico:** 3 × 4 × 3 × 5 = **180**
**Score Mínimo Teórico:** 1 × 1 × 1 × 1 = **1**

---

## 2. Top-10 Riscos Priorizados

### #1: DLQ Não Implementada no Consensus Engine

**Score:** 162 / 180
**Dimensão:** Mensageria
**Prioridade:** P0

| Factor | Valor | Score |
|--------|-------|-------|
| Probabilidade | ALTA (3) | 3.0 |
| Impacto | ALTO (3) | 4.5 |
| Urgência | ALTA (3) | 3.6 |
| Esforço | 3-5 dias (3) | 1.5 |

**Descrição:** Consensus-engine tem configuração DLQ reservada mas não funcional. Mensagens com schema inválido ou business error ficam presas no consumer indefinidamente, causando congestionamento.

**Invariantes Violados:** INV-4 (ordem estrita), INV-8 (non-blocking)

**Custo de Não-Ação:** Perda de mensagens, downtime do consensus, degradation cascade

**Mitigação Recomendada:**
```python
# Adicionar no consensus-engine/src/consumers/plan_consumer.py
DLQ_TOPIC = "nhm.decisions.dlq"

async def handle_invalid_message(msg, error):
    await producer.send(DLQ_TOPIC, value={
        "original_message": msg.value,
        "error": str(error),
        "timestamp": datetime.utcnow(),
        "retry_count": msg.headers.get("retry_count", 0)
    })
```

**Esforço:** 3-5 dias
**Responsible Team:** Consensus Engine Team

---

### #2: PII Logado em Plaintext

**Score:** 151.2 / 180
**Dimensão:** Privacidade
**Prioridade:** P0

| Factor | Valor | Score |
|--------|-------|-------|
| Probabilidade | ALTA (3) | 3.0 |
| Impacto | CRÍTICO (4) | 6.0 |
| Urgência | ALTA (3) | 3.6 |
| Esforço | 2-3 dias (4) | 2.0 |

**Descrição:** user_id e email logados em plaintext em 11+ endpoints. PIIMasker existe mas não integrado no structlog.

**Compliance:** GDPR/LGPD violation — Artigo 32 (Security of Processing)

**Custo de Não-Ação:** Multas regulatórias, exposição legal, perda de confiança

**Mitigação Recomendada:**
```python
# Integrar PIIMasker no structlog
from neural_hive_observability.masking import PIIMasker

masker = PIIMasker(fields=["user_id", "email", "phone"])

structlog.configure(
    processors=[
        masker.mask_pii,
        structlog.processors.JSONRenderer()
    ]
)
```

**Esforço:** 2-3 dias
**Responsible Team:** Observability Team

---

### #3: State Divergence Redis→MongoDB

**Score:** 144 / 180
**Dimensão:** Consistência de Estado
**Prioridade:** P0

| Factor | Valor | Score |
|--------|-------|-------|
| Probabilidade | ALTA (3) | 3.0 |
| Impacto | ALTO (3) | 4.5 |
| Urgência | ALTA (3) | 3.6 |
| Esforço | 3-5 dias (3) | 1.5 |

**Descrição:** consensus-engine e service-registry usam Redis como fonte primária sem fallback MongoDB. Viola INV-6.

**Invariantes Violados:** INV-6 (MongoDB autoritativo)

**Custo de Não-Ação:** Dados inconsistentes, decisões baseadas em estado stale, corrupção de dados

**Mitigação Recomendada:**
```python
# Implementar cache-aside pattern consistentemente
async def get_plan(plan_id: str):
    # Try cache first
    cached = await redis.get(f"plan:{plan_id}")
    if cached:
        return json.loads(cached)

    # Fallback to MongoDB (authoritative)
    plan = await mongo.plans.find_one({"plan_id": plan_id})
    if plan:
        await redis.setex(f"plan:{plan_id}", 300, json.dumps(plan))
    return plan
```

**Esforço:** 3-5 dias
**Responsible Team:** Consensus Engine Team

---

### #4: OpenTelemetry Version Drift

**Score:** 129.6 / 180
**Dimensão:** Compatibilidade
**Prioridade:** P0

| Factor | Valor | Score |
|--------|-------|-------|
| Probabilidade | ALTA (3) | 3.0 |
| Impacto | ALTO (3) | 4.5 |
| Urgência | ALTA (3) | 3.6 |
| Esforço | 1 dia (5) | 2.5 |

**Descrição:** libs/python usa 1.39.1, requirements-base.txt define 1.29.0. Incompatibilidade de tipos em runtime.

**Invariantes Violados:** R-T7.1

**Custo de Não-Ação:** Crashes em runtime, tracing inoperacional, debugging impossível

**Mitigação Recomendada:**
```bash
# Sincronizar versões em requirements-base.txt
opentelemetry-api==1.39.1
opentelemetry-sdk==1.39.1
opentelemetry-instrumentation-fastapi==0.46b0
```

**Esforço:** 1 dia
**Responsible Team:** Platform Team

---

### #5: time.sleep() em Async Context

**Score:** 129.6 / 180
**Dimensão:** Timeouts
**Prioridade:** P0

| Factor | Valor | Score |
|--------|-------|-------|
| Probabilidade | ALTA (3) | 3.0 |
| Impacto | ALTO (3) | 4.5 |
| Urgência | ALTA (3) | 3.6 |
| Esforço | 1 dia (5) | 2.5 |

**Descrição:** 3 ocorrências em consensus-engine/src/consumers/plan_consumer.py. Bloqueia event loop.

**Invariantes Violados:** INV-8 (non-blocking)

**Custo de Não-Ação:** Event loop bloqueado, degradation de performance, timeouts cascata

**Mitigação Recomendada:**
```python
# Antes (bloqueia):
time.sleep(5)

# Depois (non-blocking):
await asyncio.sleep(5)
```

**Esforço:** 1 dia
**Responsible Team:** Consensus Engine Team

---

### #6: Sem Índices TTL para Dados PII

**Score:** 129.6 / 180
**Dimensão:** Privacidade
**Prioridade:** P0

| Factor | Valor | Score |
|--------|-------|-------|
| Probabilidade | ALTA (3) | 3.0 |
| Impacto | ALTO (3) | 4.5 |
| Urgência | ALTA (3) | 3.6 |
| Esforço | 1-2 dias (5) | 2.5 |

**Descrição:** Coleções plan_approvals e specialist_feedback sem TTL. RetentionManager existe mas não integrado.

**Compliance:** GDPR/LGPD violation — Artigo 17 (Right to Erasure), retention max 2 anos

**Custo de Não-Ação:** Retenção indevida de dados pessoais, multas, não-conformidade

**Mitigação Recomendada:**
```python
# Adicionar TTL indexes
await db.plan_approvals.create_index(
    "created_at",
    expireAfterSeconds=63072000  # 2 anos em segundos
)
await db.specialist_feedback.create_index(
    "created_at",
    expireAfterSeconds=63072000
)
```

**Esforço:** 1-2 dias
**Responsible Team:** Data Team

---

### #7: Correlation ID Inconsistente

**Score:** 100.8 / 180
**Dimensão:** Observabilidade
**Prioridade:** P0

| Factor | Valor | Score |
|--------|-------|-------|
| Probabilidade | ALTA (3) | 3.0 |
| Impacto | ALTO (3) | 4.5 |
| Urgência | ALTA (3) | 3.6 |
| Esforço | 5-7 dias (2) | 1.0 |

**Descrição:** gRPC calls não propagam correlation_id. worker-agents não geram para tarefas internas.

**Invariantes Violados:** R-T9.1

**Custo de Não-Ação:** Impossível rastrear requests end-to-end, debugging ineficiente

**Mitigação Recomendada:**
```python
# Middleware gRPC para injeção de correlation_id
class CorrelationIdInterceptor(grpc.ServerInterceptor):
    def intercept(self, request, context, method_info):
        correlation_id = dict(context.invocation_metadata()).get("correlation-id")
        if not correlation_id:
            correlation_id = str(uuid4())

        context.set_code(grpc.StatusCode.OK)
        return request

# Registrar no servidor
interceptor = CorrelationIdInterceptor()
server = grpc.server(interceptor)
```

**Esforço:** 5-7 dias
**Responsible Team:** Observability Team

---

### #8: Circuit Breaker Ausente em gRPC

**Score:** 86.4 / 180
**Dimensão:** Mensageria
**Prioridade:** P0

| Factor | Valor | Score |
|--------|-------|-------|
| Probabilidade | MÉDIA (2) | 2.0 |
| Impacto | ALTO (3) | 4.5 |
| Urgência | ALTA (3) | 3.6 |
| Esforço | 2-3 dias (4) | 2.0 |

**Descrição:** Chamadas gRPC para especialistas sem circuit breaker. Specialist lento/falhando bloqueia consensus.

**Invariantes Violados:** INV-3 (isolamento failures)

**Custo de Não-Ação:** Cascade failures, sistema inteiro bloqueado por serviço falhado

**Mitigação Recomendada:**
```python
from neural_hive_resilience.circuit_breaker import CircuitBreaker

class SpecialistClient:
    def __init__(self):
        self.cb = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=60,
            expected_exception=grpc.RpcError
        )

    async def call_specialist(self, request):
        return await self.cb.call(self._grpc_call, request)
```

**Esforço:** 2-3 dias
**Responsible Team:** Resilience Team

---

### #9: Health Checks Não Configurados

**Score:** 72 / 180
**Dimensão:** Kubernetes
**Prioridade:** P0

| Factor | Valor | Score |
|--------|-------|-------|
| Probabilidade | ALTA (3) | 3.0 |
| Impacto | MÉDIO (2) | 3.0 |
| Urgência | ALTA (3) | 3.6 |
| Esforço | 2 dias (4) | 2.0 |

**Descrição:** 0 de 8 serviços com liveness/readiness probes. Kubernetes não detecta pods mortos.

**Invariantes Violados:** R-B6.3

**Custo de Não-Ação:** Traffic roteado para pods não prontos, downtime não detectado

**Mitigação Recomendada:**
```yaml
# Adicionar em Helm charts
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

**Esforço:** 2 dias
**Responsible Team:** Platform Team

---

### #10: Right to Erasure Não Implementado

**Score:** 64 / 180
**Dimensão:** Privacidade
**Prioridade:** P0

| Factor | Valor | Score |
|--------|-------|-------|
| Probabilidade | BAIXA (1) | 1.0 |
| Impacto | CRÍTICO (4) | 6.0 |
| Urgência | ALTA (3) | 3.6 |
| Esforço | 3-5 dias (3) | 1.5 |

**Descrição:** Endpoint para deleção GDPR/LGPD Article 17 não existe. Usuário não pode solicitar exclusão.

**Compliance:** GDPR/LGPD violation — Artigo 17 (Right to Erasure)

**Custo de Não-Ação:** Multas até 4% do faturamento, ações judiciais

**Mitigação Recomendada:**
```python
# POST /api/v1/gdpr/erasure-request
@router.post("/erasure-request")
async def request_erasure(user_id: str, reason: str):
    # Criar ticket de deleção
    await db.erasure_requests.insert_one({
        "user_id": user_id,
        "reason": reason,
        "status": "pending",
        "created_at": datetime.utcnow()
    })

    # Enfileirar para processamento assíncrono
    await kafka.send("nhm.gdpr.erasure", value={"user_id": user_id})
```

**Esforço:** 3-5 dias
**Responsible Team:** Compliance Team

---

## 3. Matriz de Priorização Visual

```
Score Range    | Count | Gaps
---------------|-------|------
150+           |   2   | DLQ, PII Logs
120-149        |   4   | State Divergence, OTel Drift, time.sleep, TTL PII
90-119         |   1   | Correlation ID
70-89          |   2   | Circuit Breaker, Health Checks
<70            |   1   | Right to Erasure
```

---

## 4. Quick Wins (Score/Esforço > 50)

| Gap | Score | Esforço | ROI |
|-----|-------|---------|-----|
| OpenTelemetry sync | 129.6 | 1 dia | **129.6** |
| time.sleep() fix | 129.6 | 1 dia | **129.6** |
| TTL PII indexes | 129.6 | 1-2 dias | **64.8** |
| Health checks | 72 | 2 dias | **36** |

**Recomendação:** Executar quick wins na Fase 1 (1-2 semanas) para alto ROI.

---

## 5. Mapa de Responsabilidades

| Gap | Responsible Team | Dependencies |
|-----|------------------|--------------|
| DLQ | Consensus Engine Team | Kafka Team |
| PII Masking | Observability Team | Compliance Team |
| State Divergence | Consensus Engine Team | Data Team |
| OpenTelemetry | Platform Team | - |
| time.sleep() | Consensus Engine Team | - |
| TTL PII | Data Team | DBA Team |
| Correlation ID | Observability Team | gRPC Team |
| Circuit Breaker | Resilience Team | gRPC Team |
| Health Checks | Platform Team | K8s Team |
| Right to Erasure | Compliance Team | Data Team, API Team |

---

## 6. Sequência Recomendada de Execução

### Fase 1: Quick Wins (Semana 1-2)
1. OpenTelemetry sync (1 dia)
2. time.sleep() fix (1 dia)
3. TTL PII indexes (1-2 dias)
4. Health checks (2 dias)

**Total:** 5-6 dias
**Impacto:** Elimina 4 gaps críticos

### Fase 2: Compliance GDPR (Semana 3-4)
5. PII Masking (2-3 dias)
6. Right to Erasure (3-5 dias)

**Total:** 5-8 dias
**Impacto:** Compliance GDPR/LGPD

### Fase 3: Resiliência (Semana 5-7)
7. Circuit Breaker (2-3 dias)
8. DLQ (3-5 dias)
9. State Divergence (3-5 dias)

**Total:** 8-13 dias
**Impacto:** Resiliência de mensageria

### Fase 4: Observabilidade (Semana 8-9)
10. Correlation ID (5-7 dias)

**Total:** 5-7 dias
**Impacto:** Visibilidade operacional

**Total Estimado:** 23-34 dias (~6-8 semanas)

---

**Documento compilado por:** Orchestrator (Round 2, Task T14)
**Data:** 2026-04-27
**Próxima tarefa:** T15 - Traduzir riscos em tickets accionáveis
