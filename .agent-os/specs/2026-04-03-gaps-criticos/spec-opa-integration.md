# Spec: OPA Integration Standardization

> **Epic:** INFRA-002 - OPA Standard Integration
> **Prioridade:** 🔴 CRÍTICA (Padronização)
> **Esforço Estimado:** 6-9 semanas
> **Data:** 2026-04-03

---

## Resumo Executivo

Criar uma **biblioteca Python padronizada** para integração com Open Policy Agent (OPA). Atualmente existem 5 implementações diferentes de OPAClient nos serviços, resultando em duplicação de código e inconsistências.

---

## Contexto

### Status Atual
- **services/opa/** contém apenas Helm chart (0 arquivos Python)
- **5 serviços** têm implementações próprias de OPAClient:
  - Orchestrator-Dynamic (mais avançado: circuit breaker, cache, batch)
  - Queen-Agent (básico: httpx)
  - Worker-Agents (completo)
  - Guard-Agents (básico)
  - Architect-Agent (mínimo)

### Problemas Identificados
1. **Duplicação de código** - 5 implementações diferentes
2. **Inconsistência** - Diferentes níveis de features
3. **Manutenibilidade** - Mudanças requerem updates em 5 lugares
4. **Testabilidade** - Difícil testar consistentemente

### Soluções OPA Existentes
- **10 políticas** implementadas entre os serviços
- **Bibliotecas:** httpx, aiohttp (sem padrão)
- **Sem SDK oficial** OPA para Python

---

## User Stories

### US-001: Como desenvolvedor, quero usar uma biblioteca OPA padronizada
Para não precisar reimplementar integração OPA em cada serviço.

### US-002: como operador, quero gerir políticas centralizadamente
Para que mudanças de política sejam aplicadas consistentemente.

### US-003: Como arquiteto, quero ter visibilidade de decisões OPA
Para que possamos auditar e otimizar validações.

---

## Escopo

### IN CLUDE

#### 1. Biblioteca Python OPA (neural_hive_opa)
- **Path:** `libraries/python/neural_hive_opa/`
- **Módulos:**
  - `client.py` - Cliente unificado
  - `models.py` - Pydantic models para requests/responses
  - `exceptions.py` - Exceções customizadas
  - `middleware.py` - Middleware para FastAPI/Django
  - `cache.py` - Cache layer com TTL
  - `batch.py` - Batch evaluation
  - `metrics.py` - Prometheus metrics integration

#### 2. Features do Cliente Unificado
- Circuit breaker integrado
- Cache LRU configurável
- Retry strategies (exponential backoff)
- Health checks
- Audit logging
- Batch evaluation
- Streaming evaluation
- Policy bundle management

#### 3. Middleware Pattern
- FastAPI/Starlette middleware
- Integração com OpenTelemetry
- Context propagation
- Error handling padronizado

#### 4. Refatoração de Serviços Existentes
- Orchestrator-Dynamic (padronizar)
- Queen-Agent (refatorar para usar library)
- Worker-Agents (padronizar)
- Guard-Agents (refatorar)
- Architect-Agent (refatorar)

### OUT OF SCOPE
- Desenvolvimento de novas políticas OPA (Rego)
- OPA server deployment (já existe Helm chart)
- UI para gerenciamento de políticas

---

## Especificação Técnica

### Arquitetura Proposta

```python
# libraries/python/neural_hive_opa/
├── __init__.py
├── client.py              # Cliente unificado
├── models.py              # Pydantic models
├── exceptions.py          # Exceções customizadas
├── middleware.py          # Middleware FastAPI
├── cache.py               # Cache LRU layer
├── batch.py               # Batch processing
├── metrics.py             # Prometheus metrics
├── config.py              # Configuration
└── utils.py               # Utilities
```

### API do Cliente

```python
from neural_hive_opa import OPAClient, OPAConfig

# Configuração
config = OPAConfig(
    opa_url="http://opa:8181",
    cache_ttl=300,
    circuit_breaker_threshold=5,
    retry_attempts=3
)

# Cliente
client = OPAClient(config)

# Avaliação simples
result = await client.evaluate(
    policy="neuralhive/orchestrator/resource_limits",
    input_data={"resource": "cpu", "amount": 4}
)

# Batch evaluation
results = await client.evaluate_batch([
    {"policy": "...", "input": {...}},
    {"policy": "...", "input": {...}}
])
```

### Middleware FastAPI

```python
from fastapi import FastAPI
from neural_hive_opa.middleware import OPAAuthMiddleware

app = FastAPI()
app.add_middleware(
    OPAAuthMiddleware,
    policy="neuralhive/api/authorization",
    exclude_paths=["/health", "/metrics"]
)
```

### Requisitos Funcionais

#### RQ-001: Cliente Unificado
- Suportar avaliação síncrona e assíncrona
- Cache configurável por política
- Circuit breaker com threshold configurável
- Retry com exponential backoff

#### RQ-002: Observabilidade
- Métricas Prometheus:
  - `opa_evaluations_total` (counter)
  - `opa_evaluation_duration_ms` (histogram)
  - `opa_cache_hits_total` (counter)
  - `opa_circuit_breaker_open` (gauge)
- Structured logging com decision ID
- Distributed tracing

#### RQ-003: Performance
- Cache LRU com TTL por política
- Batch evaluation para múltiplas queries
- Connection pooling
- Keep-alive connections

#### RQ-004: Segurança
- TLS obrigatório em produção
- Authentication via mTLS ou API key
- Input validation
- Audit trail de decisões

---

## Políticas OPA Existentes

### Por Serviço
| Serviço | Políticas | Status |
|---------|-----------|--------|
| Orchestrator | 4 políticas | ✅ |
| Guard | 3 políticas | ✅ |
| Queen | 1 política | ✅ |
| Worker | 1 política | ✅ |
| Architect | 1 política | ✅ |

### Falta Adicionar
- Consensus Engine
- Self-Healing Engine
- SLA Management System
- Execution Ticket Service

---

## Testes

### Unit Tests
- Testes para cada método do cliente
- Mock de respostas OPA
- Testes de cache
- Testes de circuit breaker

### Integration Tests
- Testes com OPA real (via docker)
- Testes de políticas
- Testes de performance

### Testes de Serviços
- Verificar que serviços continuam funcionando
- Testes de migração para nova library

---

## Deliverables

### Fase 1: Library Core (2-3 semanas)
1. [ ] Implementar cliente base
2. [ ] Adicionar circuit breaker
3. [ ] Implementar cache
4. [ ] Criar exceptions
5. [ ] Escrever testes
6. [ ] Documentação API

### Fase 2: Service Integration (1-2 semanas por serviço)
1. [ ] Orchestrator-Dynamic (migração)
2. [ ] Queen-Agent (refatoração)
3. [ ] Worker-Agents (migração)
4. [ ] Guard-Agents (refatoração)
5. [ ] Architect-Agent (refatoração)

### Fase 3: Advanced Features (2-3 semanas)
1. [ ] Policy bundle management
2. [ ] Streaming evaluation
3. [ ] Metrics dashboard
4. [ ] Policy versioning
5. [ ] Audit trail UI

### Fase 4: Optimization (1 semana)
1. [ ] Performance tuning
2. [ ] Load testing
3. [ ] Documentation final

---

## Critérios de Aceite

### Library
- [ ] Cliente OPA funcional
- [ ] Cache operacional
- [ ] Circuit breaker testado
- [ ] Métricas Prometheus funcionando
- [ ] Cobertura de testes >80%

### Integração
- [ ] Todos os 5 serviços migrados
- [ ] Zero regressões em funcionalidade
- [ ] Performance melhor ou igual

### Documentação
- [ ] API docs completas
- [ ] Guia de migração
- [ ] Exemplos de uso

---

## Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Breaking changes em serviços | Alta | Alto | Testes abrangentes, rollout gradual |
| Performance degradation | Média | Alto | Benchmarks antes/depois |
| Complexidade de policies | Média | Médio | Envolvimento early das teams |

---

## Referências
- OPA Docs: https://www.openpolicyagent.org/docs/latest/
- Implementação existente: `services/orchestrator-dynamic/src/opa/`
