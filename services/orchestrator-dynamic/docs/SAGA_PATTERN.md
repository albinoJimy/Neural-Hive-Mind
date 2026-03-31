# Saga Pattern - Implementação no Orchestrator Dynamic

## Visão Geral

O Orchestrator Dynamic implementa o padrão Saga para orquestração de workflows distribuídos com transações de longa duração. O padrão Saga garante consistência eventual através de transações compensáveis.

## Arquitetura

### Componentes Principais

```
┌─────────────────────────────────────────────────────────────────┐
│                     Saga Orchestrator                           │
├─────────────────────────────────────────────────────────────────┤
│  ┌───────────────┐  ┌───────────────┐  ┌─────────────────────┐  │
│  │ Saga State    │  │ Saga Events   │  │ Saga Repository     │  │
│  │ Machine       │  │ Producer      │  │ (MongoDB)           │  │
│  └───────────────┘  └───────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Compensation Engine                          │
│  - Rollback Activities                                          │
│  - Compensation Ticket Management                               │
│  - State Recovery                                               │
└─────────────────────────────────────────────────────────────────┘
```

### Arquivos de Implementação

| Arquivo | Propósito |
|---------|-----------|
| `src/saga/saga_coordinator.py` | Core do SagaOrchestrator |
| `src/saga/saga_state.py` | SagaState e máquina de estados |
| `src/saga/saga_event_store.py` | SagaEventStore para persistência |
| `src/saga/saga_repository.py` | SagaRepository para queries |
| `src/activities/saga_activities.py` | Activities Temporal |
| `src/activities/compensation_activity.py` | Atividades de compensação |

## Máquina de Estados

### Estados do Saga

```python
class SagaState(str, Enum):
    """Estados possíveis de uma saga."""
    PENDING = 'pending'           # Criado, ainda não iniciado
    STARTED = 'started'           # Workflow iniciado
    IN_PROGRESS = 'in_progress'   # Executando steps
    COMPENSATING = 'compensating' # Executando compensação
    COMPLETED = 'completed'       # Todos os steps concluídos
    FAILED = 'failed'             # Falha não recuperável
    COMPENSATED = 'compensated'   # Compensação concluída
    TIMEOUT = 'timeout'           # Timeout excedido
```

### Transições de Estado

```
    ┌─────────┐
    │ PENDING │
    └────┬────┘
         │ on_start()
         ▼
   ┌─────────┐
   │ STARTED │◄─────────────────────────┐
   └────┬────┘                           │
        │ execute_step()                 │ retry()
        ▼                                │
  ┌─────────────┐   on_step_failed()    │
  │ IN_PROGRESS │───────────────────────┤
  └──────┬──────┘                       │
         │                              │
         │ on_all_steps_completed()     │
         │ on_step_failed()             │
         ▼                              ▼
   ┌─────────┐                    ┌─────────────┐
   │COMPLETED│                    │ COMPENSATING│
   └─────────┘                    └──────┬──────┘
                                        │ on_compensation_completed()
                                        ▼
                                   ┌─────────────┐
                                   │ COMPENSATED │
                                   └─────────────┘
```

## SagaOrchestrator

### Responsabilidades

1. **Coordenação de Steps**: Executa steps sequencialmente com rollback automático
2. **Gestão de Estado**: Mantém estado da saga em MongoDB
3. **Compensação**: Executa compensações em caso de falha
4. **Eventos**: Publica eventos Kafka para cada transição de estado
5. **Retry Configuration**: Configura retries com backoff exponencial

### API Principal

```python
class SagaOrchestrator:
    async def start_saga(
        self,
        saga_id: str,
        workflow_id: str,
        steps: List[SagaStep],
        context: Dict[str, Any]
    ) -> SagaState

    async def execute_step(
        self,
        saga_id: str,
        step_id: str,
        activity_data: Dict[str, Any]
    ) -> SagaState

    async def compensate(
        self,
        saga_id: str,
        reason: str = 'step_failed'
    ) -> SagaState

    async def get_saga_state(
        self,
        saga_id: str
    ) -> Optional[SagaState]
```

### Configuração de Retry

```python
class SagaRetryConfig:
    """Configuração de retry para steps de saga."""

    max_attempts: int = 3
    initial_delay_ms: int = 1000
    max_delay_ms: int = 30000
    backoff_multiplier: float = 2.0
    retry_on_exceptions: Tuple[Exception, ...] = (
        TemporalError,
        KafkaError,
        MongoDBError
    )
```

## SagaEventStore

### Eventos Armazenados

| Evento | Descrição | Payload |
|--------|-----------|---------|
| `saga_created` | Saga criada | saga_id, workflow_id, steps_count |
| `saga_started` | Workflow iniciado | saga_id, started_at |
| `saga_step_started` | Step iniciado | saga_id, step_id, step_name |
| `saga_step_completed` | Step completado | saga_id, step_id, result |
| `saga_step_failed` | Step falhou | saga_id, step_id, error |
| `saga_compensating` | Compensação iniciada | saga_id, reason |
| `saga_compensated` | Compensação completada | saga_id, compensated_steps |
| `saga_completed` | Saga completada | saga_id, duration_ms |
| `saga_failed` | Saga falhou | saga_id, error, failed_step |

### Schema MongoDB

```javascript
{
  _id: ObjectId,
  saga_id: "saga-12345",
  event_type: "saga_step_started",
  event_data: {
    saga_id: "saga-12345",
    step_id: "step-001",
    step_name: "allocate_resources"
  },
  timestamp: 1711920000000,
  tenant_id: "tenant-001",
  correlation_id: "corr-abc123"
}
```

### Índices

```python
indexes = [
    [('saga_id', 1), ('timestamp', -1)],  # Queries por saga
    [('event_type', 1), ('timestamp', -1)],  # Queries por tipo
    [('timestamp', -1)],  # Queries temporais
    [('tenant_id', 1), ('timestamp', -1)],  # Multi-tenant
    [('correlation_id', 1)],  # Distributed tracing
    [('ttl', 1)],  # Auto-expiração
]
```

## SagaRepository

### Operações CRUD

```python
class SagaRepository:
    async def create_saga(self, saga: SagaState) -> SagaState
    async def get_saga(self, saga_id: str) -> Optional[SagaState]
    async def update_saga(self, saga: SagaState) -> SagaState
    async def delete_saga(self, saga_id: str) -> bool
    async def list_sagas(
        self,
        filters: Dict[str, Any],
        limit: int = 100
    ) -> List[SagaState]
```

### Queries Especializadas

```python
async def get_active_sagas(
    self,
    tenant_id: str
) -> List[SagaState]:
    """Retorna sagas ativas (não terminal)."""

async def get_sagas_by_workflow(
    self,
    workflow_id: str
) -> List[SagaState]:
    """Retorna todas as sagas de um workflow."""

async def get_failed_sagas(
    self,
    since_hours: int = 24
) -> List[SagaState]:
    """Retorna sagas falhadas recentes."""
```

## Saga Metrics

### Métricas Publicadas

```python
class SagaMetrics:
    counter_saga_created: Counter
    counter_saga_completed: Counter
    counter_saga_failed: Counter
    counter_saga_compensated: Counter
    histogram_saga_duration: Histogram
    gauge_active_sagas: Gauge
    histogram_step_duration: Histogram
    counter_step_retries: Counter
```

### Tags Prometeus

```python
tags = {
    'tenant_id': saga.tenant_id,
    'workflow_type': saga.workflow_type,
    'saga_id': saga.saga_id,
    'step_name': step.name,
    'error_type': error.__class__.__name__
}
```

## Fluxo de Compensação

### Algoritmo de Compensação

1. **Identificar Steps Executados**: Buscar steps completados da saga
2. **Ordem Reversa**: Compensar do último para o primeiro
3. **Compensation Activities**: Executar atividade de compensação de cada step
4. **Track Progress**: Registrar progresso da compensação
5. **Final State**: Transitar para COMPENSATED ou FAILED

### Exemplo de Compensação

```python
# Steps executados: [A, B, C, D]
# Step D falha

# Compensação em ordem reversa:
# 1. compensate(C) - rollback do step C
# 2. compensate(B) - rollback do step B
# 3. compensate(A) - rollback do step A

# Resultado: SagaState.COMPENSATED
# compensated_steps: ['C', 'B', 'A']
```

## Publicação de Eventos Kafka

### Tópicos

| Tópico | Eventos |
|--------|---------|
| `saga.lifecycle` | created, started, completed, failed |
| `saga.steps` | step_started, step_completed, step_failed |
| `saga.compensation` | compensating, compensated |
| `saga.metrics` | duration_ms, retry_count |

### Formato do Evento

```json
{
  "event_id": "evt-12345",
  "event_type": "saga_step_completed",
  "saga_id": "saga-abc123",
  "workflow_id": "workflow-001",
  "step_id": "step-allocate-resources",
  "timestamp": 1711920000000,
  "data": {
    "result": {
      "resources_allocated": ["worker-01", "worker-02"]
    },
    "duration_ms": 1250
  },
  "metadata": {
    "tenant_id": "tenant-001",
    "correlation_id": "corr-xyz789"
  }
}
```

## Testes

### Cobertura de Testes

- **Unit Tests**: 100+ testes em `tests/unit/saga/`
- **Integration Tests**: 19 testes em `tests/integration/test_saga_events.py`
- **Cobertura**: ~95%

### Exemplo de Teste

```python
@pytest.mark.asyncio
async def test_saga_compensation_flow():
    """Testa fluxo completo de compensação."""
    orchestrator = SagaOrchestrator(config)

    # Criar saga com 3 steps
    saga = await orchestrator.start_saga(
        saga_id='test-saga-001',
        workflow_id='wf-001',
        steps=[step1, step2, step3],
        context={}
    )

    # Executar 2 steps com sucesso
    await orchestrator.execute_step('test-saga-001', 'step1', {})
    await orchestrator.execute_step('test-saga-001', 'step2', {})

    # Step 3 falha
    with pytest.raises(SagaStepError):
        await orchestrator.execute_step('test-saga-001', 'step3', {})

    # Verificar compensação
    state = await orchestrator.get_saga_state('test-saga-001')
    assert state.status == SagaState.COMPENSATED
    assert state.compensated_steps == ['step2', 'step1']
```

## Monitoramento

### SLA Proactive Monitoring

```
┌──────────────────────────────────────────────────────────────┐
│                  SLA Monitor Integration                     │
├──────────────────────────────────────────────────────────────┤
│  Checkpoint 1: Após cada step                               │
│  Checkpoint 2: Durante compensação                          │
│  Action: Alertar se duração > 80% do SLA                    │
└──────────────────────────────────────────────────────────────┘
```

### Alertas

- **Saga Duration Warning**: Saga > 80% do SLA
- **Compensation Failed**: Compensação falhou
- **High Retry Rate**: Step com muitos retries
- **Orphaned Saga**: Saga em estado não terminal por > 1h

## Boas Práticas

### Design de Steps

1. **Idempotência**: Steps devem ser idempotentes
2. **Compensatable**: Todo step deve ter compensação definida
3. **Timeout**: Definir timeout para cada step
4. **Retry**: Configurar retry apropriado
5. **Logging**: Log detalhado para debugging

### Error Handling

```python
try:
    result = await execute_step(step)
except SagaCompensationRequired:
    await compensate_saga(saga_id, 'step_failed')
except SagaTimeoutError:
    await compensate_saga(saga_id, 'timeout')
except SagaNonRecoverableError:
    await fail_saga(saga_id, 'non_recoverable')
```

## Referências

- [Saga Pattern - Microservices Patterns](https://microservices.io/patterns/data/saga.html)
- `tests/integration/test_saga_events.py` - Testes de integração
- `src/saga/saga_coordinator.py` - Implementação principal
