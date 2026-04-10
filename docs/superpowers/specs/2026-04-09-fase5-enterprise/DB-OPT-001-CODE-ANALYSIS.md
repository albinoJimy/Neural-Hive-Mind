# Database Optimization — Análise de Código

**Data:** 2026-04-10
**Componente:** Database Optimization
**Arquivos Principais:**
- `services/orchestrator-dynamic/src/clients/mongodb_client.py` (745 linhas)
- `services/orchestrator-dynamic/scripts/create_shadow_mode_indexes.py` (166 linhas)

**Total LOC Analisado:** ~911 linhas

---

## Resumo Executivo

Cliente MongoDB completo com circuit breaker, retry, índices otimizados, TTL, e monitoramento. **Impacto significativo** na validação da FASE 5 Enterprise.

**Principais Descobertas:**
- Circuit breaker integration (MonitoredCircuitBreaker) ✅
- Retry com tenacity (exponential backoff) ✅
- Índices compostos e unique ✅
- TTL indexes para expiração automática ✅
- Index validation no startup ✅
- Prometheus metrics de persistência ✅
- Fail-open policy para operações críticas ✅

---

## Estrutura dos Arquivos

```
services/orchestrator-dynamic/
├── src/clients/mongodb_client.py (745 linhas)
│   ├── MongoDBClient
│   │   ├── EXPECTED_INDEXES (validação)
│   │   ├── Circuit breaker integration
│   │   ├── Retry decorators
│   │   ├── Index creation/validação
│   │   └── Prometheus metrics
│   └── scripts/create_shadow_mode_indexes.py (166 linhas)
│       └── SHADOW_MODE_INDEXES (TTL, compostos)
```

---

## Funcionalidades Implementadas

### 1. MongoDBClient (~745 linhas)

**Características:**
- Async Motor (MongoDB async)
- Connection pooling (maxPoolSize, minPoolSize)
- Circuit breaker por operação
- Retry com exponential backoff
- Índices compostos e unique
- Index validation
- Prometheus metrics
- Fail-open policy

**Índices Definidos (EXPECTED_INDEXES):**
```python
EXPECTED_INDEXES = {
    "execution_tickets": [
        "ticket_id_1",           # unique
        "plan_id_1",
        "intent_id_1",
        "decision_id_1",
        "status_1",
        "plan_id_1_created_at_-1",  # composto
    ],
    "cognitive_ledger": [
        "plan_id_1",             # unique
        "intent_id_1",
        "created_at_1",
        "status_1_created_at_-1",  # composto
    ],
    "workflows": [
        "workflow_id_1",         # unique
        "plan_id_1",
        "status_1",
    ],
    "validation_audit": [
        "plan_id_1",
        "workflow_id_1",
        "timestamp_1",
        "plan_id_1_timestamp_-1",  # composto
    ],
    "workflow_results": [
        "workflow_id_1",         # unique
        "plan_id_1",
        "status_1",
        "consolidated_at_1",
        "status_1_consolidated_at_-1",  # composto
    ],
    "authorization_audit": [
        "user_id_1",
        "tenant_id_1",
        "timestamp_1",
        "decision_1",
        "policy_path_1",
        "tenant_id_1_timestamp_-1",  # composto
        "user_id_1_timestamp_-1",
        "decision_1_timestamp_-1",
    ],
}
```

---

### 2. Circuit Breaker Integration

**Características:**
- MonitoredCircuitBreaker do neural_hive_resilience
- Circuit breaker por operação (execution_ticket, validation_audit, workflow_results)
- Fail max configurável
- Timeout duration
- Recovery timeout
- Expected exception

```python
if self.circuit_breaker_enabled:
    self.execution_ticket_breaker = MonitoredCircuitBreaker(
        service_name=self.config.service_name,
        circuit_name="execution_ticket_persistence",
        fail_max=self.config.CIRCUIT_BREAKER_FAIL_MAX,
        timeout_duration=self.config.CIRCUIT_BREAKER_TIMEOUT,
        recovery_timeout=getattr(self.config, "CIRCUIT_BREAKER_RECOVERY_TIMEOUT", ...),
        expected_exception=Exception,
    )
```

---

### 3. Retry com Tenacity

**Características:**
- Exponential backoff
- Max attempts configurável
- Exclude DuplicateKeyError (para allow replace_one)
- Retry em PyMongoError

```python
@retry(
    stop=stop_after_attempt(self.config.retry_max_attempts),
    wait=wait_exponential(
        multiplier=self.config.retry_backoff_coefficient,
        min=self.config.retry_initial_interval_ms / 1000,
        max=self.config.retry_max_interval_ms / 1000,
    ),
    retry=retry_condition,  # PyMongoError exceto DuplicateKeyError
)
```

---

### 4. Prometheus Metrics

**Métricas Registradas:**
```python
# Duração de persistência
metrics.record_mongodb_persistence_duration(collection, operation, duration)

# Erros de persistência
metrics.record_mongodb_persistence_error(collection, operation, error_type)

# Index validation
metrics.record_mongodb_index_validation(collection_name, status, count)

# Fail-open
metrics.record_mongodb_persistence_fail_open(collection)
```

---

### 5. Index Validation

**Características:**
- Validar índices no startup
- Comparar com EXPECTED_INDEXES
- Log warnings para índices faltantes
- Não bloqueia startup (apenas warnings)

```python
async def validate_indexes(self) -> None:
    for collection_name, expected_indexes in self.EXPECTED_INDEXES.items():
        collection = self.db[collection_name]
        indexes = await collection.list_indexes().to_list(length=None)
        existing_names = {idx["name"] for idx in indexes}
        existing_names.discard("_id_")  # sempre existe
        
        missing = set(expected_indexes) - existing_names
        if missing:
            logger.warning("indexes_missing", collection=collection_name, 
                          missing_indexes=list(missing))
```

---

### 6. create_shadow_mode_indexes.py (166 linhas)

**Índices Shadow Mode:**
```python
SHADOW_MODE_INDEXES = [
    {
        "name": "timestamp_ttl",
        "keys": [("timestamp", 1)],
        "options": {"expireAfterSeconds": 30 * 24 * 60 * 60, "background": True},  # 30 dias
    },
    {
        "name": "model_name_timestamp",
        "keys": [("model_name", 1), ("timestamp", -1)],
        "options": {"background": True},
    },
    {
        "name": "model_name_version_agreement",
        "keys": [("model_name", 1), ("candidate_version", 1), ("agreement", 1)],
        "options": {"background": True},
    },
    {
        "name": "predictor_type_timestamp",
        "keys": [("predictor_type", 1), ("timestamp", -1)],
        "options": {"background": True},
    },
]
```

---

## Integrações

### neural_hive_resilience
```python
from neural_hive_resilience.circuit_breaker import CircuitBreakerError, MonitoredCircuitBreaker

self.execution_ticket_breaker = MonitoredCircuitBreaker(
    service_name=self.config.service_name,
    circuit_name="execution_ticket_persistence",
    ...
)
```

### Prometheus (via get_metrics)
```python
metrics = get_metrics()
metrics.record_mongodb_persistence_duration("execution_tickets", "insert", duration)
metrics.record_mongodb_persistence_error("execution_tickets", "insert", error_type)
```

### Structlog
```python
logger.info("execution_ticket_saved",
    ticket_id=ticket_id,
    plan_id=plan_id,
    duration_ms=duration * 1000,
)
```

---

## Gaps Identificados

### Funcionalidades Presentes ✅
1. Connection pooling ✅
2. Circuit breaker ✅
3. Retry com exponential backoff ✅
4. Índices compostos ✅
5. Índices unique ✅
6. TTL indexes ✅
7. Index validation ✅
8. Prometheus metrics ✅
9. Fail-open policy ✅
10. Background index creation ✅

### Funcionalidades Ausentes ❌
1. **Sharding strategies** (não implementado)
2. **Query analysis** (explain plan)
3. **Slow query monitoring**
4. **Database profiling**
5. **Collection-level optimization**
6. **Aggregation pipeline optimization**
7. **Document validation rules**
8. **Backup/restore automation** (parcial)

---

## Impacto na FASE 5 Enterprise

| Componente | Completude Anterior | Completude Nova | Delta |
|-------------|-------------------|----------------|-------|
| Database Optimization | 65% | **75%** | +10 |

**Razão:** MongoDB client tem circuit breaker, retry, índices compostos, TTL, metrics e validation já implementados.

---

## Análise Detalhada por Critério DESIGN.md

### 1. Funcionalidade (60% → 80%)

**Presente:**
- ✅ Connection pooling
- ✅ Circuit breaker
- ✅ Retry com exponential backoff
- ✅ Índices compostos e unique
- ✅ TTL indexes
- ✅ Index validation

**Ausente:**
- ❌ Sharding
- ❌ Query analysis (explain)
- ❌ Slow query monitoring
- ❌ Database profiling

### 2. Testes (50% → 55%)

**Verificado:**
- ✅ `tests/test_mongodb_persistence.py` existe
- ✅ `tests/unit/test_mongodb_client_validation.py` existe
- ⚠️ Cobertura desconhecida

**Necessário:**
- Testes de circuit breaker
- Testes de retry logic
- Testes de index validation

### 3. Integração (80% → 85%)

**Presente:**
- ✅ neural_hive_resilience (circuit breaker)
- ✅ tenacity (retry)
- ✅ Prometheus (metrics)
- ✅ Structlog (logging)

**Ausente:**
- ❌ Query analysis tools

### 4. Observabilidade (70% → 80%)

**Presente:**
- ✅ Persistence duration metrics
- ✅ Error metrics
- ✅ Index validation metrics
- ✅ Structured logging

**Ausente:**
- ❌ Slow query metrics
- ❌ Database size metrics
- ❌ Index usage statistics

### 5. Documentação (60% → 65%)

**Presente:**
- ✅ Docstrings completas
- ✅ Comentários de índices

**Ausente:**
- ❌ Query optimization guide
- ❌ Index tuning guide
- ❌ Troubleshooting guide

---

## Recomendações

### Imediatas (Alta Prioridade)
1. **Implementar slow query monitoring** - MongoDB profiler ou query analysis
2. **Query explain tool** - Para análise de performance
3. **Aggregation pipeline optimization** - Para queries complexas

### Curto Prazo (Média Prioridade)
1. **Sharding strategy** - Para escalabilidade horizontal
2. **Collection-level optimization** - Document validation, schema rules
3. **Database sizing dashboard** - Grafana

### Longo Prazo (Baixa Prioridade)
1. **Automated backup/restore** - Scripts e validação
2. **Database migration tools** - Schema changes
3. **Performance tuning guides** - Best practices

---

## Conclusão

**MongoDB client está muito bem implementado!**

**Completude Ajustada:** 65% → **75%** (+10 pontos)

**Principais Razões:**
1. Circuit breaker integration (MonitoredCircuitBreaker)
2. Retry com exponential backoff (tenacity)
3. Índices compostos e unique bem definidos
4. TTL indexes para expiração automática
5. Index validation no startup
6. Prometheus metrics completas
7. Fail-open policy para operações críticas

**Gaps Restantes:**
- Sharding (importante para escala)
- Query analysis (útil para otimização)
- Slow query monitoring (útil para debugging)

**Estimativa Ajustada:**
- Antes: 10 semanas
- Depois: **7 semanas** (-30%)

---

## Próximos Passos

1. ✅ Criar este documento de análise
2. ⏳ Atualizar DB-OPT-spec.md com novas completudes
3. ⏳ Atualizar relatório final com todos os dados
4. ⏳ Recalcular estimativas globais
