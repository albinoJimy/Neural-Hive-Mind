# Spec: Execution Ticket Service Test Suite

> **Epic:** TEST-001 - Critical Service Test Coverage
> **Prioridade:** 🔴 CRÍTICA (Serviço sem cobertura)
> **Esforço Estimado:** 85-125 horas (~3-4 semanas)
> **Data:** 2026-04-03

---

## Resumo Executivo

O **execution-ticket-service** tem **36 arquivos Python** mas apenas **2 testes** (~5.5% cobertura). Este é um serviço crítico que gerencia o ciclo de vida de tickets de execução. Precisamos expandir para **~275 testes** (80%+ cobertura).

---

## Contexto

### Status Atual
- **Arquivos Python:** 36
- **Testes Existentes:** 2
- **Cobertura:** ~5.5%
- **Gap:** ~275 testes faltando

### Análise dos Testes Existentes
1. **test_tickets_api.py** - Endpoints de API (retry, history, create, get, update, token)
2. **test_ticket_consumer_avro.py** - Kafka consumer com Schema Registry

### Módulos Sem Cobertura (prioridade alta)
- `main.py` - Ponto de entrada, lifecycle
- `config/settings.py` - Configurações e validações
- `database/postgres_client.py` - Cliente PostgreSQL
- `consumers/ticket_consumer.py` - Kafka consumer
- `api/tickets.py` - API endpoints
- `grpc_service/ticket_servicer.py` - gRPC service
- `kafka/producer.py` - Kafka producer
- `webhooks/webhook_manager.py` - Webhook manager
- `database/mongodb_client.py` - MongoDB client
- `database/redis_client.py` - Redis circuit breaker

---

## User Stories

### US-001: Como operador, quero confiar no execution-ticket-service
Para que tickets de execução sejam geridos corretamente.

### US-002: Como desenvolvedor, quero testes que previnam regressões
Para que possamos evoluir o serviço com confiança.

### US-003: Como QA, quero testes E2E para workflows críticos
Para que possamos validar cenários reais de uso.

---

## Escopo

### IN CLUDE

#### 1. Unit Tests (~200 testes)
**Objetivo:** Testar isoladamente cada classe/função

##### Config & Main (20 testes)
- [ ] Settings validation
- [ ] Environment variable parsing
- [ ] Feature flags
- [ ] Application lifecycle (startup/shutdown)
- [ ] Dependency initialization

##### Database Layer (50 testes)
- [ ] PostgreSQL CRUD operations
- [ ] Connection pool management
- [ ] Retry logic
- [ ] MongoDB audit operations
- [ ] Redis circuit breaker
- [ ] Idempotency checks

##### Kafka Layer (40 testes)
- [ ] Producer publishing
- [ ] Consumer processing
- [ ] Avro serialization
- [ ] Error handling
- [ ] Retry mechanisms

##### API Layer (50 testes)
- [ ] All endpoints (create, get, update, retry, history)
- [ ] Input validation
- [ ] JWT token handling
- [ ] Error responses
- [ ] Authorization

##### gRPC Layer (20 testes)
- [ ] All RPC methods
- [ ] Proto conversions
- [ ] Error handling
- [ ] Context propagation

##### Webhooks (20 testes)
- [ ] Webhook enqueueing
- [ ] Retry logic
- [ ] HMAC signatures
- [ ] Failure handling

#### 2. Integration Tests (~40 testes)
**Objetivo:** Testar integração com serviços externos

##### Database Integration (15 testes)
- [ ] PostgreSQL real connection
- [ ] MongoDB real connection
- [ ] Redis real connection
- [ ] Transaction rollback
- [ ] Connection failure handling

##### Kafka Integration (10 testes)
- [ ] Real Kafka consumer/producer
- [ ] Schema Registry integration
- [ ] Message ordering
- [ ] Consumer group management

##### gRPC Integration (10 testes)
- [ ] Real gRPC server
- [ ] Client-server communication
- [ ] Streaming RPCs

##### External Services (5 testes)
- [ ] Webhook delivery
- [ ] HTTP retries
- [ ] Timeout handling

#### 3. E2E Tests (~15 testes)
**Objetivo:** Testar workflows completos de negócio

##### Critical Workflows
- [ ] Ticket creation → Kafka publish → Worker consume
- [ ] Status update → Webhook trigger
- [ ] Retry workflow with compensation
- [ ] Failed ticket recovery
- [ ] Multi-step ticket execution
- [ ] Concurrent ticket processing
- [ ] Ticket expiration handling
- [ ] Audit trail completeness

#### 4. Performance Tests (~20 testes)
**Objetivo:** Validar performance sob carga

- [ ] API throughput
- [ ] Kafka message throughput
- [ ] Database query performance
- [ ] Concurrent request handling
- [ ] Memory usage under load

### OUT OF SCOPE
- UI tests (não aplicável)
- Load tests extremos (ferramenta separada)
- Security penetration tests

---

## Especificação Técnica

### Estrutura de Testes Proposta

```
services/execution-ticket-service/tests/
├── unit/
│   ├── test_config/
│   │   ├── __init__.py
│   │   ├── test_settings.py
│   │   └── test_feature_flags.py
│   ├── test_database/
│   │   ├── __init__.py
│   │   ├── test_postgres_client.py
│   │   ├── test_mongodb_client.py
│   │   └── test_redis_client.py
│   ├── test_kafka/
│   │   ├── __init__.py
│   │   ├── test_producer.py
│   │   └── test_consumer.py
│   ├── test_api/
│   │   ├── __init__.py
│   │   ├── test_tickets.py
│   │   ├── test_validation.py
│   │   └── test_auth.py
│   ├── test_grpc/
│   │   ├── __init__.py
│   │   ├── test_servicer.py
│   │   └── test_server.py
│   └── test_webhooks/
│       ├── __init__.py
│       └── test_webhook_manager.py
├── integration/
│   ├── test_postgres/
│   ├── test_mongodb/
│   ├── test_redis/
│   ├── test_kafka/
│   └── test_grpc_integration/
├── e2e/
│   ├── test_ticket_lifecycle/
│   ├── test_error_scenarios/
│   └── test_workflows/
├── performance/
│   ├── test_api_load.py
│   ├── test_kafka_throughput.py
│   └── test_concurrent_tickets.py
├── conftest.py
└── fixtures/
    ├── __init__.py
    ├── database_fixtures.py
    ├── kafka_fixtures.py
    └── ticket_fixtures.py
```

### Ferramentas e Frameworks

```txt
# Test Framework
pytest>=7.4.0
pytest-asyncio>=0.21.0
pytest-mock>=3.11.0
pytest-cov>=4.1.0
pytest-timeout>=2.1.0

# Test Data
factory-boy>=3.3.0
faker>=19.0.0

# Integration Testing
testcontainers>=3.7.0  # PostgreSQL, MongoDB, Redis, Kafka
pytest-docker>=2.0.0

# HTTP Testing
aioresponses>=0.7.4
pytest-httpserver>=1.0.0

# Coverage
coverage[toml]>=7.3.0
```

### Exemplo de Teste

```python
# tests/unit/test_api/test_tickets.py
import pytest
from unittest.mock import Mock, patch
from execution_ticket_service.api.tickets import create_ticket
from execution_ticket_service.models.ticket import TicketCreate

@pytest.mark.asyncio
async def test_create_ticket_success(mock_postgres_client):
    # Arrange
    ticket_data = TicketCreate(
        intent_id="test-intent-123",
        plan_id="plan-456",
        workflow_type="query"
    )
    mock_postgres_client.create_ticket.return_value = "ticket-789"

    # Act
    result = await create_ticket(ticket_data)

    # Assert
    assert result["ticket_id"] == "ticket-789"
    mock_postgres_client.create_ticket.assert_called_once()

@pytest.mark.asyncio
async def test_create_ticket_invalid_input(mock_postgres_client):
    # Arrange
    ticket_data = {"invalid": "data"}

    # Act & Assert
    with pytest.raises(ValidationError):
        await create_ticket(ticket_data)
```

### Fixtures Reutilizáveis

```python
# tests/fixtures/ticket_fixtures.py
import pytest
from execution_ticket_service.models.ticket import TicketCreate

@pytest.fixture
def sample_ticket_create():
    return TicketCreate(
        intent_id="test-intent-123",
        plan_id="plan-456",
        workflow_type="query",
        priority=1,
        metadata={"test": "data"}
    )

@pytest.fixture
def sample_ticket(sample_ticket_create):
    from execution_ticket_service.models.ticket_orm import TicketORM
    ticket = TicketORM.from_pydantic(sample_ticket_create)
    ticket.id = "ticket-789"
    ticket.status = "pending"
    return ticket

@pytest.fixture
async def clean_database(postgres_client):
    # Limpar database antes de cada teste
    await postgres_client.execute("TRUNCATE TABLE tickets CASCADE")
    yield
    await postgres_client.execute("TRUNCATE TABLE tickets CASCADE")
```

---

## Deliverables

### Test Suite
1. [ ] ~200 unit tests
2. [ ] ~40 integration tests
3. [ ] ~15 E2E tests
4. [ ] ~20 performance tests
5. [ ] Cobertura >80%

### Infraestrutura
1. [ ] Fixtures reutilizáveis
2. [ ] Test containers config
3. [ ] CI integration (GitHub Actions)
4. [ ] Coverage reporting

### Documentação
1. [ ] Guia de como executar testes
2. [ ] Guia de como adicionar novos testes
3. [ ] Documentação de fixtures

---

## Rollout Plan

### Semana 1-2: Unit Tests Críticos
- Config & Settings
- Database Layer (PostgreSQL)
- API Layer (endpoints principais)

### Semana 3: Integration Tests
- PostgreSQL integration
- Kafka integration
- gRPC integration

### Semana 4: E2E & Performance
- Critical workflows
- Performance baselines
- Documentation

---

## Critérios de Aceite

### Cobertura
- [ ] Cobertura >80% geral
- [ ] Todos os módulos críticos >90%
- [ ] Zero blocos de código sem teste

### Qualidade
- [ ] Todos os testes passam
- [ ] Zero flaky tests
- [ ] Testes executam em <5 minutos

### CI/CD
- [ ] Testes executam no PR
- [ ] Coverage report no PR
- [ ] Testes de bloqueio para merge

---

## Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Testes flaky devido a Kafka | Alta | Médio | Usar testcontainers, mocks |
| Tempo de execução alto | Média | Baixo | Paralelizar, fixtures leves |
| Cobertura difícil em alguns módulos | Média | Baixo | Aceitar <80% em casos específicos |

---

## Referências
- Testes existentes: `services/execution-ticket-service/tests/`
- Pytest docs: https://docs.pytest.org/
- Testcontainers: https://testcontainers-python.readthedocs.io/
