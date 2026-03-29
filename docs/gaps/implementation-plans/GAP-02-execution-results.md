# GAP-02: execution.results Sem Consumer

**Status:** 🔴 Planejado
**Prioridade:** P0 - CRÍTICA
**Esforço Estimado:** 3 dias (24 horas)
**Responsável:** Backend Team

---

## Problema

Worker Agents produzem resultados no tópico `execution.results`, mas **NENHUM serviço consome** este tópico. O feedback loop está incompleto.

```
┌─────────────┐    execution.tickets    ┌──────────────┐
│ Orchestrator│ ──────────────────────> │ Worker Agents│
└─────────────┘                         └──────┬───────┘
                                              │
                                              │ execution.results
                                              │ (PRODUZIDO)
                                              ▼
                                       ┌──────────────┐
                                       │   (VAZIO)     │ ❌
                                       │              │
                                       └──────────────┘
```

### Impacto

- Workflows não sabem quando tickets completam
- Consolidação de resultados não funciona
- Temporal workflows ficam esperando timeout
- Telemetria final incompleta

---

## Solução

**Implementar consumer no Orchestrator Dynamic**

**Justificativa:**
- Orchestrator é o "owner" do workflow Temporal
- Já possui signal `ticket_completed` definido
- Possui contexto completo (plan_id, workflow_id)
- Necessita feedback para continuar workflow

---

## Implementação

### Fase 1: Atualizar Schema (CRÍTICO)

**Arquivo:** `schemas/execution-result/execution-result.avsc`

Adicionar campos:
```avsc
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
  "doc": "ID de correlação para tracing"
}
```

### Fase 2: Criar Consumer

**Arquivo NOVO:** `services/orchestrator-dynamic/src/consumers/execution_result_consumer.py`

```python
"""
Consumer Kafka para execution.results - Fecha feedback loop
"""
from typing import Optional, Dict, Any
import structlog
from aiokafka import AIOKafkaConsumer
from temporalio.client import Client

logger = structlog.get_logger(__name__)


class ExecutionResultConsumer:
    """Consumer Kafka para execution.results"""

    TOPIC = "execution.results"

    def __init__(
        self,
        config,
        temporal_client: Client,
        redis_client,
        metrics
    ):
        self.config = config
        self.temporal_client = temporal_client
        self.redis_client = redis_client
        self.metrics = metrics
        self.consumer = None
        self.running = False

        # Cache de workflow_id (Redis)
        self.workflow_cache_prefix = "workflow:by:ticket:"
        self.workflow_cache_ttl = 86400  # 24h

    async def initialize(self):
        """Inicializar consumer Kafka"""
        self.consumer = AIOKafkaConsumer(
            self.TOPIC,
            bootstrap_servers=self.config.kafka_bootstrap_servers,
            group_id=self.config.execution_result_consumer_group,
            auto_offset_reset="latest",
            enable_auto_commit=False
        )
        await self.consumer.start()

    async def start(self):
        """Loop de consumo"""
        self.running = True
        logger.info("execution_result_consumer_starting", topic=self.TOPIC)

        try:
            async for message in self.consumer:
                await self._process_result(message)
        except Exception as e:
            logger.error("consumer_loop_error", error=str(e))
            raise
        finally:
            await self.consumer.stop()

    async def _process_result(self, message):
        """
        Processa ExecutionResult e envia signal para Temporal Workflow.

        Fluxo:
        1. Deserializar mensagem (Avro/JSON)
        2. Recuperar workflow_id (cache ou lookup)
        3. Enviar signal ticket_completed para workflow
        4. Atualizar métricas
        """
        try:
            result_data = self._deserialize(message)
            ticket_id = result_data['ticket_id']
            plan_id = result_data.get('plan_id')

            # Recuperar workflow_id
            workflow_id = result_data.get('workflow_id')
            if not workflow_id:
                workflow_id = await self._get_workflow_for_ticket(ticket_id, plan_id)

            if not workflow_id:
                logger.warning(
                    'workflow_id_not_found_for_result',
                    ticket_id=ticket_id,
                    plan_id=plan_id,
                    action='result_processed_but_no_signal_sent'
                )
                await self.consumer.commit()
                return

            # Enviar signal para Temporal
            await self._send_workflow_signal(
                workflow_id=workflow_id,
                ticket_id=ticket_id,
                result=result_data
            )

            # Commit offset
            await self.consumer.commit()

            logger.info(
                'execution_result_processed',
                ticket_id=ticket_id,
                workflow_id=workflow_id,
                status=result_data.get('status')
            )

        except Exception as e:
            logger.error(
                'result_processing_failed',
                ticket_id=result_data.get('ticket_id') if 'result_data' in locals() else 'unknown',
                error=str(e)
            )
            # Commit mesmo assim para não bloquear tópico
            await self.consumer.commit()

    async def _get_workflow_for_ticket(
        self,
        ticket_id: str,
        plan_id: str
    ) -> Optional[str]:
        """Recupera workflow_id do cache Redis"""
        cache_key = f"{self.workflow_cache_prefix}{ticket_id}"

        # Try Redis cache
        workflow_id = await self.redis_client.get(cache_key)
        if workflow_id:
            return workflow_id

        logger.warning(
            'workflow_id_not_cached',
            ticket_id=ticket_id,
            plan_id=plan_id
        )
        return None

    async def _send_workflow_signal(
        self,
        workflow_id: str,
        ticket_id: str,
        result: Dict[str, Any]
    ):
        """Envia signal ticket_completed para workflow Temporal"""
        try:
            handle = self.temporal_client.get_workflow_handle(workflow_id)
            await handle.signal(
                "ticket_completed",  # Nome do signal
                ticket_id=ticket_id,
                result=result
            )
            logger.info(
                'workflow_signal_sent',
                workflow_id=workflow_id,
                ticket_id=ticket_id,
                status=result.get('status')
            )
        except Exception as e:
            logger.error(
                'workflow_signal_failed',
                workflow_id=workflow_id,
                ticket_id=ticket_id,
                error=str(e)
            )
            raise

    def _deserialize(self, message) -> Dict[str, Any]:
        """Deserializa mensagem (simplificado)"""
        import json
        return json.loads(message.value)

    async def stop(self):
        """Para o consumer"""
        self.running = False
        if self.consumer:
            await self.consumer.stop()
```

### Fase 3: Cache de workflow_id

**Modificar:** `services/orchestrator-dynamic/src/activities/ticket_generation.py`

Após publicar ticket:
```python
async def cache_workflow_mapping(
    ticket_id: str,
    workflow_id: str,
    redis_client
):
    """Cache mapeamento ticket_id -> workflow_id"""
    cache_key = f"workflow:by:ticket:{ticket_id}"
    await redis_client.setex(
        cache_key,
        86400,  # 24h TTL
        workflow_id
    )
```

### Fase 4: Worker Agents Enviar Metadata

**Modificar:** `services/worker-agents/src/clients/kafka_result_producer.py`

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
) -> Dict[str, Any]:
    payload = {
        'ticket_id': ticket_id,
        'status': status,
        'result': result,
        'error_message': error_message,
        'actual_duration_ms': actual_duration_ms,
        'agent_id': self.config.agent_id,
        'timestamp': int(datetime.now().timestamp() * 1000),
        'schema_version': 2,  # Atualizar versão
        # NOVOS CAMPOS
        'plan_id': plan_id,
        'workflow_id': workflow_id,
        'correlation_id': correlation_id
    }
    # ... resto da implementação
```

### Fase 5: Integração no Main

**Modificar:** `services/orchestrator-dynamic/src/main.py`

```python
class AppState:
    # ... existente ...
    execution_result_consumer: Optional[ExecutionResultConsumer] = None
    execution_result_task: Optional[asyncio.Task] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    # ... inicialização existente ...

    # Inicializar Execution Result Consumer
    app_state.execution_result_consumer = ExecutionResultConsumer(
        config=config,
        temporal_client=app_state.temporal_client,
        redis_client=app_state.redis_client,
        metrics=app_state.metrics
    )
    await app_state.execution_result_consumer.initialize()

    # Iniciar consumer task
    app_state.execution_result_task = asyncio.create_task(
        app_state.execution_result_consumer.start()
    )

    # Shutdown
    yield

    # ... cleanup existente ...

    if app_state.execution_result_consumer:
        await app_state.execution_result_consumer.stop()
    if app_state.execution_result_task:
        app_state.execution_result_task.cancel()
```

---

## Testes

### Unit Test

```python
@pytest.mark.asyncio
async def test_process_result_sends_workflow_signal():
    """Testa que resultado processado envia signal para workflow"""
    result = {
        'ticket_id': 'ticket-123',
        'plan_id': 'plan-456',
        'workflow_id': 'workflow-789',
        'status': 'COMPLETED',
        'result': {'success': True},
        'timestamp': 1234567890
    }

    await consumer._process_result(result)

    # Verificar signal enviado
    mock_workflow_handle.signal.assert_called_once()
```

### Integration Test

```python
@pytest.mark.integration
async def test_full_feedback_loop():
    """Teste E2E: Orchestrator → Workers → Result → Signal"""
    # 1. Iniciar workflow
    workflow_id = await start_test_workflow(plan_id)

    # 2. Simular Worker publicando resultado
    await publish_execution_result(
        ticket_id='ticket-123',
        status='COMPLETED',
        plan_id=plan_id,
        workflow_id=workflow_id
    )

    # 3. Verificar signal recebido
    workflow_status = await query_workflow(workflow_id)
    assert workflow_status['tickets_completed'] >= 1
```

---

## Deploy Strategy

1. Atualizar schema (backward compatible)
2. Deploy Orchestrator com consumer (feature flag OFF)
3. Deploy Worker Agents com novos campos
4. Feature flag ON
5. Monitoramento

---

## Arquivos Críticos

| Ação | Arquivo |
|------|---------|
| **MODIFICAR** | `schemas/execution-result/execution-result.avsc` |
| **CRIAR** | `services/orchestrator-dynamic/src/consumers/execution_result_consumer.py` |
| **MODIFICAR** | `services/worker-agents/src/clients/kafka_result_producer.py` |
| **MODIFICAR** | `services/orchestrator-dynamic/src/activities/ticket_generation.py` |
| **MODIFICAR** | `services/orchestrator-dynamic/src/main.py` |

---

**Documento baseado em análise do agente Plan (2026-03-29)**
