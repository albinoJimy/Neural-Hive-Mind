# Technical Specification - Fase 2.4-2.13 Execution Gaps

> Este documento contém as especificações técnicas para resolver os gaps da Fase 2.4-2.13

---

## EXE-001: Analyst Agents

### Gap Analysis

**Completude Atual:** 85%
**Componentes Faltantes:**
1. Testes de integração multi-source aggregation
2. Edge cases PostgreSQL client (timeout, retry logic)
3. Documentação deployment completa
4. Metrics dashboard AnalyticsEngine

### Implementações Necessárias

#### 1.1 Testes Integração Multi-Source

**Arquivo:** `services/analyst-agents/tests/integration/test_multi_source_aggregation.py`

```python
# Testes a implementar:
- test_aggregate_mongodb_postgresql_sources()
- test_aggregate_with_source_failure()
- test_data_fusion_engine_consistency()
- test_queryengine_timeout_handling()
- test_aggregation_with_duplicate_keys()
```

#### 1.2 PostgreSQL Client Edge Cases

**Arquivo:** `services/analyst-agents/src/clients/postgresql_client.py`

```python
# Melhorias necessárias:
- Timeout configurável por query
- Retry logic com exponential backoff
- Connection pool validation
- Query timeout com cancellation
```

#### 1.3 Metrics Dashboard

**Arquivo:** `services/analyst-agents/src/api/telemetry.py`

```python
# Métricas a expor:
- analyst_processing_duration_seconds
- analyst_sources_aggregated_total
- analyst_query_latency_seconds
- analyst_fusion_engine_errors_total
```

---

## EXE-002: MCP Tool Catalog

### Gap Analysis

**Completude Atual:** 94.8%
**Componentes Faltantes:**
1. Corner cases schema validator (nested objects, recursive schemas)
2. Security validator PII patterns edge cases
3. E2E tests para catalog discovery

### Implementações Necessárias

#### 2.1 Schema Validator Corner Cases

**Arquivo:** `services/mcp-tool-catalog/src/services/schema_validator.py`

```python
# Casos a cobrir:
- Nested objects > 5 níveis de profundidade
- Recursive schema definitions
- Arrays com tipos complexos
- Union types e optional fields
- Pattern validation edge cases
```

#### 2.2 Security Validator PII Patterns

**Arquivo:** `services/mcp-tool-catalog/src/services/security_validator.py`

```python
# PII patterns a validar:
- Email (RFC 5322 completo)
- Phone numbers (internacionais)
- SSN/NIF/CPF variants
- Credit card (todos os formatos)
- API keys e tokens
```

---

## EXE-003: Self-Healing Engine

### Gap Analysis

**Completude Atual:** 94%
**Componentes Faltantes:**
1. Recovery complexos (multi-pod failure)
2. E2E tests com chaos engineering
3. Playbooks operacionais
4. Graceful degradation thresholds

### Implementações Necessárias

#### 3.1 Multi-Pod Failure Recovery

**Arquivo:** `services/self-healing-engine/src/services/recovery_orchestrator.py`

```python
# Cenários a implementar:
- Simultaneous 3+ pod failures
- Cascading failure detection
- Dependency-aware recovery
- Stateful pod recovery ordering
- Recovery priority scoring
```

#### 3.2 Chaos Engineering Tests

**Arquivo:** `services/self-healing-engine/tests/chaos/test_multi_failure_scenarios.py`

```python
# Testes chaos:
- test_random_pod_kill_sequence()
- test_network_partition_recovery()
- test_resource_exhaustion_recovery()
- test_dependency_chain_failure()
- test_graceful_shutdown_under_load()
```

#### 3.3 Graceful Degradation

**Arquivo:** `services/self-healing-engine/src/services/degradation_manager.py`

```python
# Thresholds a configurar:
- CPU > 80%: redução de pods não-críticos
- Memory > 85%: garbage collection agressiva
- Error rate > 5%: modo degradado
- Latency p99 > 1s: shedding de tráfego
```

---

## EXE-004: Worker Agents

### Gap Analysis

**Completude Atual:** 100% (refinamentos necessários)
**Componentes a Refinar:**
1. Coordenação de dependências entre executores
2. Timeout handling em execução paralela
3. Metrics por tipo de executor

### Implementações Necessárias

#### 4.1 Dependency Coordination

**Arquivo:** `services/worker-agents/src/orchestration/dependency_coordinator.py`

```python
# Refinamentos:
- Topological sorting optimizado
- Circular dependency detection
- Parallel execution max depth
- Dependency failure isolation
```

---

## EXE-005: Queen Agent

### Gap Analysis

**Completude Atual:** 100% (validação necessária)
**Componentes a Validar:
1. Election protocol em partição de rede
2. Load balancing sob stress

### Implementações Necessárias

#### 5.1 Network Partition Tests

**Arquivo:** `services/queen-agent/tests/integration/test_network_partition_election.py`

```python
# Cenários de teste:
- Split-brain com 3 nós
- Redis failure durante election
- Concurrent election attempts
- Leader heartbeat timeout
- Re-election after partition heals
```

---

## EXE-006: Scout Agent

### Gap Analysis

**Completude Atual:** 100% (edge cases linguagens)
**Edge Cases a Cobrir:**
1. Rust modern syntax (2021 edition)
2. C/C++20 features (concepts, modules)

### Implementações Necessárias

#### 6.1 Rust Modern Syntax

**Arquivo:** `services/scout-agents/src/parsers/rust_parser.py`

```python
# Features a suportar:
- async/await patterns
- trait bounds complexos
- macros declarativos
- generics com const parameters
- pattern matching avançado
```

---

## EXE-007: Optimizer Agents

### Gap Analysis

**Completude Atual:** 100% (validação produção)
**Validações Necessárias:**
1. Auto-apply mechanism em produção
2. Rollback automation tests

### Implementações Necessárias

#### 7.1 Auto-Apply Validation

**Arquivo:** `services/optimizer-agents/tests/integration/test_auto_apply_production.py`

```python
# Cenários de teste:
- test_auto_apply_with_safety_checks()
- test_rollback_on_validation_failure()
- test_apply_dry_run_mode()
- test_apply_with_manual_approval()
```

---

## EXE-008: Code Forge

### Gap Analysis

**Completude Atual:** 100% (edge cases IaC)
**Edge Cases a Cobrir:**
1. Multi-cloud IaC generation
2. Terraform state conflicts

### Implementações Necessárias

#### 8.1 Multi-Cloud Edge Cases

**Arquivo:** `services/code-forge/src/iac/multi_cloud_generator.py`

```python
# Casos a cobrir:
- Cross-cloud resource references
- Provider-specific edge cases
- Terraform state remote backend config
- Cloud-specific IAM policies
- Multi-region deployments
```

---

## EXE-009: Execution Tickets

### Gap Analysis

**Completude Atual:** 100% (race conditions)
**Refinamentos Necessários:**
1. Idempotency em race conditions
2. Webhook retry backoff otimizado

### Implementações Necessárias

#### 9.1 Race Condition Idempotency

**Arquivo:** `services/execution-ticket-service/src/services/idempotency_manager.py`

```python
# Refinamentos:
- Distributed lock para updates simultâneos
- Optimistic locking com version
- Idempotency key com TTL
- Duplicate request deduplication
```

---

## Dependências Técnicas

```
analyst-agents ──> PostgreSQL (multi-source)
                  └──> MongoDB (aggregation)

mcp-tool-catalog ──> Schema Registry
                  └──> PII Detector

self-healing ─────> Chaos Engineering tools
                  └──> Kubernetes API

queen-agent ──────> Redis (distributed lock)
                  └──> Network emulation tools

optimizer-agents ─> Git (rollback)
                  └──> CI/CD integration

code-forge ───────> Terraform CLI
                  └──> Cloud SDKs (AWS/GCP/Azure)
```

---

## Configurações de Ambiente

### Variáveis Necessárias

```bash
# Analyst Agents
ANALYST_MULTI_SOURCE_TIMEOUT=30
ANALYST_QUERY_RETRY_MAX=3
ANALYST_FUSION_ENGINE_MAX_SOURCES=10

# MCP Tool Catalog
MCP_SCHEMA_VALIDATION_STRICT=true
MCP_PII_DETECTION_ENABLED=true
MCP_CATALOG_DISCOVERY_INTERVAL=60

# Self-Healing
SELF_HEALING_CHAOS_ENABLED=false  # true apenas em testes
SELF_HEALING_DEGRADATION_CPU_THRESHOLD=80
SELF_HEALING_MULTI_POD_FAILURE_THRESHOLD=3

# Queen Agent
QUEEN_ELECTION_HEARTBEAT_INTERVAL=5
QUEEN_NETWORK_PARTITION_TIMEOUT=30
QUEEN_LOAD_BALANCING_STRATEGY=least_loaded

# Optimizer Agents
OPTIMIZER_AUTO_APPLY_DRY_RUN=true
OPTIMIZER_ROLLBACK_ENABLED=true
OPTIMIZER_SAFETY_CHECKS_STRICT=true

# Code Forge
CODE_FORGE_TERRAFORM_VERSION=1.5
CODE_FORGE_MULTI_CLOUD_ENABLED=true
CODE_FORGE_STATE_BACKEND=s3

# Execution Tickets
EXECUTION_TICKET_IDEMPOTENCY_TTL=3600
EXECUTION_TICKET_WEBHOOK_RETRY_MAX=5
EXECUTION_TICKET_WEBHOOK_BACKOFF_BASE=2
```

---

## Testes E2E

### Scenarios a Implementar

**Arquivo:** `tests/e2e/test_execution_layer_complete.py`

```python
def test_complete_execution_flow():
    """
    Flow completo: Gateway -> STE -> Consensus -> Orchestrator ->
    Queen -> Scout -> Worker -> Analyst -> Optimizer
    """
    # 1. Intenção recebida no Gateway
    # 2. Traduzida pelo STE
    # 3. Consenso gerado
    # 4. Workflow orchestrado
    # 5. Queen coordena execução
    # 6. Scout explora recursos
    # 7. Worker executa tarefas
    # 8. Analyst gera insights
    # 9. Optimizer recomenda melhorias
    # 10. Self-Healing monitora tudo
    assert decision_completed
    assert all_healthy
```

---

## Checklist de Finalização

Por componente:
- [ ] Código implementado
- [ ] Testes unitários passando
- [ ] Testes integração passando
- [ ] Testes E2E passando
- [ ] Documentação atualizada
- [ ] Métricas expostas
- [ ] Playbooks operacionais
- [ ] Handoff para operação

Por epic:
- [ ] Todos 9 componentes 100%
- [ ] E2E tests passando
- [ ] Zero bugs críticos
- [ ] Documentação consolidada
- [ ] Demo stakeholders
- [ ] Retro executada
