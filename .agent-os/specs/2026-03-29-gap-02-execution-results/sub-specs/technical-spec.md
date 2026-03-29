# Technical Specification

## Technical Requirements

### 1. Schema Execution Result (Avro)

**Arquivo:** `schemas/execution-result/execution-result.avsc`

**Campos a adicionar:**
```json
{
  "name": "plan_id",
  "type": "string",
  "doc": "ID do Cognitive Plan para correlação"
},
{
  "name": "workflow_id",
  "type": ["null", "string"],
  "default": null,
  "doc": "ID do workflow Temporal para signal"
},
{
  "name": "correlation_id",
  "type": ["null", "string"],
  "default": null,
  "doc": "ID de correlação para tracing distribuído"
}
```

**Schema version:** Atualizar de 1 para 2

### 2. Consumer Kafka (Novo Arquivo)

**Arquivo:** `services/orchestrator-dynamic/src/consumers/execution_result_consumer.py`

**Classe:** `ExecutionResultConsumer`

**Métodos:**
- `__init__(config, temporal_client, redis_client, metrics)`
- `async initialize()` - Inicializar AIOKafkaConsumer
- `async start()` - Loop de consumo
- `async _process_result(message)` - Processar mensagem e enviar signal
- `async _get_workflow_for_ticket(ticket_id, plan_id)` - Cache lookup Redis
- `async _send_workflow_signal(workflow_id, ticket_id, result)` - Signal Temporal
- `def _deserialize(message)` - JSON/Avro deserialização
- `async stop()` - Shutdown gracioso

**Configuração:**
- Topic: `execution.results`
- Group ID: `orchestrator-execution-results`
- Auto offset reset: `latest`
- Auto commit: `false`

### 3. Cache Redis Workflow ID

**Arquivo:** `services/orchestrator-dynamic/src/activities/ticket_generation.py`

**Função nova:**
```python
async def cache_workflow_mapping(
    ticket_id: str,
    workflow_id: str,
    redis_client
) -> None:
    """Cache mapeamento ticket_id → workflow_id"""
    cache_key = f"workflow:by:ticket:{ticket_id}"
    await redis_client.setex(cache_key, 86400, workflow_id)
```

**Chamada:** Após `publish_ticket()` em `generate_execution_ticket()`

### 4. Producer Worker Agents

**Arquivo:** `services/worker-agents/src/clients/kafka_result_producer.py`

**Método `publish_result()` - Adicionar parâmetros:**
```python
async def publish_result(
    self,
    ticket_id: str,
    status: str,
    result: Dict[str, Any],
    error_message: Optional[str] = None,
    actual_duration_ms: Optional[int] = None,
    # NOVOS PARÂMETROS
    plan_id: Optional[str] = None,
    workflow_id: Optional[str] = None,
    correlation_id: Optional[str] = None
)
```

### 5. Integração Main

**Arquivo:** `services/orchestrator-dynamic/src/main.py`

**AppState - Adicionar:**
```python
execution_result_consumer: Optional[ExecutionResultConsumer] = None
execution_result_task: Optional[asyncio.Task] = None
```

**Lifespan - Startup:**
```python
# Inicializar consumer
app_state.execution_result_consumer = ExecutionResultConsumer(...)
await app_state.execution_result_consumer.initialize()

# Iniciar task
app_state.execution_result_task = asyncio.create_task(
    app_state.execution_result_consumer.start()
)
```

**Lifespan - Shutdown:**
```python
if app_state.execution_result_consumer:
    await app_state.execution_result_consumer.stop()
if app_state.execution_result_task:
    app_state.execution_result_task.cancel()
```

## External Dependencies

Nenhuma nova dependência. Usa:
- `aiokafka` (já instalado)
- `temporalio` (já instalado)
- `redis` (já instalado)

## Configuration

**Adicionar em `services/orchestrator-dynamic/src/config/settings.py`:**
```python
# Execution Result Consumer
execution_result_consumer_enabled: bool = Field(
    default=True,
    description='Enable execution result consumer'
)
execution_result_consumer_group: str = Field(
    default='orchestrator-execution-results',
    description='Consumer group for execution results'
)
execution_result_workers: int = Field(
    default=1,
    description='Number of consumer workers'
)
```
