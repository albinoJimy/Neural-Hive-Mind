# Design: Platform Health & Kafka Standardization

**Data:** 2026-04-02
**Epic:** PAD-003 (Health Checks) + PAD-004 (Kafka Topics)
**Estimativa:** 21 horas (~3 dias)

---

## Resumo Executivo

Padronizar health checks e tópicos Kafka em todos os serviços do Neural-Hive-Mind através da criação de uma biblioteca compartilhada `neural_hive_api`. Isto elimina inconsistências, reduz duplicação de código, e facilita manutenção futura.

**Scope:** 22 serviços com health endpoints, 17 serviços com Kafka topics.

---

## 1. Arquitectura

### 1.1 Nova Biblioteca

```
libraries/python/neural_hive_api/
├── neural_hive_api/
│   ├── __init__.py
│   ├── health/
│   │   ├── __init__.py
│   │   ├── router.py          # FastAPI router padronizado
│   │   ├── models.py          # HealthResponse, HealthStatus
│   │   └── checks.py          # BaseHealthCheck, CheckResult
│   └── kafka/
│       ├── __init__.py
│       ├── topics.py          # KafkaTopicsConfig base class
│       └── patterns.py        # Constantes de padrões
├── tests/
│   ├── test_health_router.py
│   └── test_kafka_topics.py
├── pyproject.toml
└── README.md
```

### 1.2 Fluxo de Dados

```
Serviço → herda KafkaTopicsConfig → define get_topic_mappings()
         ↓
      Usa service.domain.event pattern
         ↓
   Producer/Consumer → topic configurado
```

```
HTTP GET /health → HealthRouter → CheckExecutor → Response JSON
                     ↓
              /health/live → LivenessProbe
              /health/ready → ReadinessProbe
```

---

## 2. Componentes

### 2.1 Health Router

**`neural_hive_api/health/router.py`**

```python
class HealthRouter:
    """Router FastAPI padronizado com 3 endpoints."""

    def __init__(self, service_name: str):
        self.service_name = service_name
        self.checks: list[BaseHealthCheck] = []

    def register_check(self, check: BaseHealthCheck) -> None:
        """Registra um check customizado."""

    def add_route(self, app: FastAPI) -> None:
        """Adiciona /health, /health/live, /health/ready à app."""

    async def health(self) -> HealthResponse:
        """Endpoint principal - status agregado."""

    async def liveness(self) -> HealthResponse:
        """Liveness probe - processo está vivo?"""

    async def readiness(self) -> HealthResponse:
        """Readiness probe - pode receber tráfego?"""
```

**Response Format:**
```json
{
  "status": "healthy|degraded|unhealthy",
  "service": "orchestrator-dynamic",
  "timestamp": "2026-04-02T10:00:00Z",
  "checks": {
    "database": "healthy",
    "kafka": "healthy",
    "redis": "degraded"
  }
}
```

### 2.2 Kafka Topics Config

**`neural_hive_api/kafka/topics.py`**

```python
class KafkaTopicsConfig:
    """Base class para configuração de tópicos."""

    PREFIX: str = ""  # Override no serviço

    def get_topic(self, domain: str, event: str) -> str:
        """Retorna {PREFIX}.{domain}.{event}"""
        return f"{self.PREFIX}.{domain}.{event}"

    @abstractmethod
    def get_all_topics(self) -> dict[str, str]:
        """Retorna mapping nome_tópico → tópico."""
```

**Uso no serviço:**
```python
class OrchestratorTopics(KafkaTopicsConfig):
    PREFIX = "orchestrator"

    STRATEGIC = get_topic("strategic", "decisions")
    # → "orchestrator.strategic.decisions"
```

---

## 3. Migração

### 3.1 Serviços com Health Checks (22)

| Serviço | Padrão Actual | Destino |
|---------|---------------|---------|
| analyst-agents | `/health` | `/health` + sub |
| approval-service | `/health`, `/ready` | `/health` + sub |
| architect-agent | `/health/live`, `/health/ready` | `/health` + sub |
| code-forge | `/health` | `/health` + sub |
| consensus-engine | `/health`, `/ready` | `/health` + sub |
| execution-ticket-service | `/health`, `/ready`, `/grpc-health` | `/health` + sub |
| explainability-api | `/health`, `/ready` | `/health` + sub |
| feature-store | `/health`, `/ready`, `/live` | `/health` + sub |
| gateway-intencoes | `/health`, `/ready` | `/health` + sub |
| guard-agents | `/health` + `/health/liveness|readiness|startup` | `/health` + sub |
| mcp-tool-catalog | `/health`, `/ready` | `/health` + sub |
| memory-layer-api | `/health`, `/ready` | `/health` + sub |
| optimizer-agents | `/health`, `/health/ready` | `/health` + sub |
| orchestrator-dynamic | `/health` + sub-específicos | `/health` + sub |
| queen-agent | `/health`, `/ready` | `/health` + sub |
| scout-agents | `/health/live`, `/health/ready` | `/health` + sub |
| self-healing-engine | `/health`, `/health/liveness|readiness` | `/health` + sub |
| semantic-translation-engine | `/health`, `/ready` | `/health` + sub |
| service-registry | health checks internos | `/health` + sub |
| sla-management-system | `/health`, `/ready` | `/health` + sub |
| specialist-architecture | `/health`, `/ready` | `/health` + sub |
| worker-agents | health checks internos | `/health` + sub |

### 3.2 Serviços com Kafka Topics (17)

analyst-agents, queen-agent, architect-agent, code-forge, execution-ticket-service, explainability-api, guard-agents, mcp-tool-catalog, memory-layer-api, optimizer-agents, orchestrator-dynamic, scout-agents, self-healing-engine, sla-management-system, worker-agents

**Novo padrão:** `{service}.{domain}.{event}`
- Ex: `analyst.execution.results`
- Ex: `queen.telemetry.aggregated`
- Ex: `consensus.plans.decision`

### 3.3 Ordem de Migração

| Fase | Tempo | Descrição |
|------|-------|-----------|
| 1: Biblioteca Base | 3h | Criar neural_hive_api + unit tests |
| 2: Piloto | 4h | Migrar analyst-agents, optimizer-agents |
| 3: Batch Migration | 8h | 4 batches de 3-4 serviços |
| 4: E2E Tests | 4h | Testes completos da plataforma |
| 5: Cleanup | 2h | Remover legacy, docs |

**Total: 21h (~3 dias)**

---

## 4. Testes

### 4.1 Unit Tests (neural_hive_api)
- test_health_response_format
- test_liveness_always_healthy
- test_readiness_with_checks
- test_degraded_when_one_check_fails
- test_topic_format_service_domain_event
- test_get_all_topics_returns_dict

### 4.2 Integration Tests (por serviço)
- test_health_endpoint_returns_200
- test_health_ready_returns_503_when_deps_down
- test_producer_sends_to_correct_topic
- test_consumer_receives_from_new_topic
- test_end_to_end_message_flow

### 4.3 E2E Tests
- test_all_services_respond_to_health
- test_kubernetes_probes_work
- test_intent_to_orchestration_flow
- test_consent_message_flow
- test_feedback_loop_flow

---

## 5. Error Handling

### 5.1 Health Check Failures

| Check Falha | Status | HTTP Status | Acção |
|-------------|--------|-------------|-------|
| Todos passam | healthy | 200 | Nenhuma |
| Não-crítico falha | degraded | 200 | Log warning |
| Crítico falha | unhealthy | 503 | Log error + alert |

**Críticos:** database, kafka, redis
**Não-críticos:** cache externo, APIs opcionais

### 5.2 Kafka Connection Errors
- Validar conexão no startup
- Retries: 3 tentativas com 2s delay
- Falha: raise StartupError (bloqueia start)

### 5.3 Rollback Strategy
- Feature flags para toggle velho/novo
- Staging testado antes de prod
- Backup branch antes de cada migração
- Revert script automático

---

## 6. Branch Strategy

```
main
├── feat/neural-hive-api-base (Fase 1)
├── feat/pilot-migration-analyst (Fase 2)
├── feat/batch-1-core (Fase 3)
├── feat/batch-2-specialists (Fase 3)
├── feat/batch-3-supporting (Fase 3)
├── feat/batch-4-infrastructure (Fase 3)
├── test/e2e-health-kafka (Fase 4)
└── chore/cleanup-legacy-health (Fase 5)
```

---

## 7. Documentação

Arquivos a criar:
- `docs/platform-standardization/HEALTH_CHECK_STANDARD.md`
- `docs/platform-standardization/KAFKA_TOPICS_STANDARD.md`
- `docs/platform-standardization/MIGRATION_GUIDE.md`
- `libraries/python/neural_hive_api/README.md`

---

## 8. Critérios de Sucesso

- [ ] Todos os serviços com `/health`, `/health/live`, `/health/ready`
- [ ] Todos os tópicos Kafka seguem `{service}.{domain}.{event}`
- [ ] 100% dos health checks respondem em <100ms
- [ ] E2E tests passando
- [ ] Zero regressões em funcionalidade existente
- [ ] Documentação completa e atualizada

---

**Design aprovado.** Pronto para implementação.
