# Neural Hive Integration Library

Biblioteca Python para integração com Neural Hive Mind Phase 2 - Flow C.

## Visão Geral

A `neural_hive_integration` fornece clientes, orchestração e telemetria para o Flow C completo (Intent → Deploy), implementando:

- **Service Discovery**: Descoberta de workers via Service Registry gRPC
- **Orchestration**: FlowCOrchestrator para coordenação de steps C1-C6
- **Ticket Management**: Clientes para ExecutionTicketService
- **Telemetry**: Publisher Kafka com buffer Redis
- **Worker Communication**: Clientes HTTP/gRPC para workers e Code Forge

## Instalação

### Desenvolvimento (Editable)

```bash
pip install -e .
```

### Produção

```bash
# Via PyPI registry privado
pip install neural_hive_integration>=1.0.0

# Ou via wheel local
pip install dist/neural_hive_integration-1.0.0-py3-none-any.whl
```

### Build

```bash
./build.sh
```

## Componentes

### 1. FlowCOrchestrator

Orquestra o fluxo completo C1-C6:

```python
from neural_hive_integration import FlowCOrchestrator

orchestrator = FlowCOrchestrator()
await orchestrator.initialize()

decision = {
    "intent_id": "intent-123",
    "plan_id": "plan-456",
    "decision_id": "decision-789",
    "cognitive_plan": {...}
}

result = await orchestrator.execute_flow_c(decision)

if result.success:
    print(f"Flow C completo! Tickets: {result.tickets_generated}")
```

**Steps executados:**
- **C1**: Validate Decision
- **C2**: Generate Tickets (Temporal workflow)
- **C3**: Discover Workers (Service Registry)
- **C4**: Assign Tickets (HTTP direto)
- **C5**: Monitor Execution (polling com SLA)
- **C6**: Publish Telemetry (Kafka)

### 2. ServiceRegistryClient

Cliente gRPC para Service Registry:

```python
from neural_hive_integration import ServiceRegistryClient, AgentInfo

registry = ServiceRegistryClient(
    host="service-registry.neural-hive-orchestration",
    port=50051
)

# Registrar worker
agent = AgentInfo(
    agent_id="worker-1",
    agent_type="worker",
    capabilities=["python", "terraform"],
    endpoint="http://worker-1:8000",
    metadata={"version": "1.0.0"}
)
await registry.register_agent(agent)

# Descobrir workers (apenas healthy)
workers = await registry.discover_agents(
    capabilities=["python"],
    filters={"status": "healthy"}
)

# Heartbeat
from neural_hive_integration import HealthStatus
await registry.update_health(
    agent_id="worker-1",
    health_status=HealthStatus(
        status="healthy",
        last_heartbeat="2024-01-01T12:00:00Z",
        metrics={"success_rate": 0.95}
    )
)
```

### 3. ExecutionTicketClient

Cliente para Execution Ticket Service:

```python
from neural_hive_integration import ExecutionTicketClient

ticket_client = ExecutionTicketClient(
    base_url="http://execution-ticket-service:8000"
)

# Criar ticket
ticket_data = {
    "plan_id": "plan-123",
    "task_type": "code_generation",
    "required_capabilities": ["python"],
    "payload": {
        "template_id": "microservice",
        "parameters": {"language": "python"}
    }
}
ticket = await ticket_client.create_ticket(ticket_data)

# Atualizar status
await ticket_client.update_status(
    ticket_id=ticket.ticket_id,
    status="assigned",
    metadata={"worker_id": "worker-1"}
)

# Consultar
ticket = await ticket_client.get_ticket(ticket.ticket_id)
```

### 4. WorkerAgentClient

Cliente para comunicação com Workers:

```python
from neural_hive_integration import WorkerAgentClient, TaskAssignment

worker = WorkerAgentClient(base_url="http://worker-1:8000")

# Atribuir tarefa
task = TaskAssignment(
    task_id="task-001",
    ticket_id="ticket-001",
    task_type="code_generation",
    payload={"template_id": "microservice"},
    sla_deadline="2024-01-01T16:00:00Z"
)
await worker.assign_task(task)

# Status
status = await worker.get_task_status("task-001")
print(f"Status: {status.status}, Progress: {status.progress}%")
```

### 5. CodeForgeClient

Cliente para Code Forge pipelines:

```python
from neural_hive_integration import CodeForgeClient

forge = CodeForgeClient(base_url="http://code-forge:8000")

# Trigger pipeline
pipeline = await forge.trigger_pipeline(
    ticket_id="ticket-001",
    template_id="microservice",
    parameters={"language": "python"}
)

# Status
status = await forge.get_pipeline_status(pipeline.pipeline_id)
```

### 6. OrchestratorClient - Workflow State Queries

Cliente para Orchestrator Dynamic com suporte a queries de workflow state:

```python
from neural_hive_integration import OrchestratorClient

orchestrator = OrchestratorClient(
    base_url="http://orchestrator-dynamic:8000"
)

# Iniciar workflow
workflow_id = await orchestrator.start_workflow(
    cognitive_plan={"tasks": [...]},
    correlation_id="corr-123",
    priority=5,
    sla_deadline_seconds=14400  # 4h
)

# Consultar tickets gerados pelo workflow
tickets_result = await orchestrator.query_workflow(
    workflow_id=workflow_id,
    query_name="get_tickets"
)
tickets = tickets_result.get("tickets", [])

# Consultar status do workflow
status_result = await orchestrator.query_workflow(
    workflow_id=workflow_id,
    query_name="get_status"
)
print(f"Status: {status_result['status']}")
print(f"Tickets gerados: {status_result['tickets_generated']}")
```

**Queries disponíveis:**

| Query Name | Descrição | Retorno |
|------------|-----------|---------|
| `get_tickets` | Lista tickets gerados | `{"tickets": [...]}` |
| `get_status` | Status atual do workflow | `{"status": "...", "tickets_generated": N}` |

### 7. FlowCTelemetryPublisher

Publisher de telemetria com buffer Redis:

```python
from neural_hive_integration import FlowCTelemetryPublisher

telemetry = FlowCTelemetryPublisher(
    kafka_bootstrap_servers="kafka:9092",
    topic="telemetry-flow-c",
    redis_url="redis://redis:6379"
)
await telemetry.initialize()

# Publicar evento
await telemetry.publish_event(
    event_type="step_completed",
    step="C3",
    intent_id="intent-123",
    plan_id="plan-456",
    decision_id="decision-789",
    workflow_id="workflow-abc",
    ticket_ids=["ticket-001"],
    duration_ms=1500,
    status="completed",
    metadata={"workers_found": 3}
)

# Buffer automático se Kafka indisponível
# Flush manual
await telemetry.flush_buffer("intent-123")
```

## Modelos de Dados

### FlowCContext

```python
from neural_hive_integration.models import FlowCContext

context = FlowCContext(
    intent_id="intent-123",
    plan_id="plan-456",
    decision_id="decision-789",
    correlation_id="corr-abc",
    trace_id="trace-xyz",
    span_id="span-def",
    started_at=datetime.utcnow(),
    sla_deadline=datetime.utcnow() + timedelta(hours=4),
    priority=5,
    risk_band="medium"
)
```

### FlowCResult

```python
result = FlowCResult(
    success=True,
    steps=[...],                    # List[FlowCStep]
    total_duration_ms=3600000,      # 1h
    tickets_generated=5,
    tickets_completed=5,
    tickets_failed=0,
    telemetry_published=True,
    error=None
)
```

## Métricas Prometheus

A biblioteca expõe métricas Prometheus:

```python
# Flow C - Execução
neural_hive_flow_c_duration_seconds          # Histogram
neural_hive_flow_c_steps_duration_seconds    # Histogram per step
neural_hive_flow_c_success_total             # Counter
neural_hive_flow_c_failures_total            # Counter per reason
neural_hive_flow_c_sla_violations_total      # Counter

# Flow C - Workflow Queries
neural_hive_flow_c_workflow_query_duration_seconds  # Histogram per query_name
neural_hive_flow_c_workflow_query_failures_total    # Counter per query_name, reason
neural_hive_flow_c_ticket_validation_failures_total # Counter

# Service Registry
neural_hive_service_registry_calls_total     # Counter per operation
neural_hive_service_registry_latency_seconds # Histogram

# Telemetria
neural_hive_flow_c_telemetry_published_total # Counter per step
neural_hive_flow_c_telemetry_buffer_size     # Gauge
```

## Configuração

### Variáveis de Ambiente

```bash
# Service Registry
SERVICE_REGISTRY_HOST=service-registry.neural-hive-orchestration
SERVICE_REGISTRY_PORT=50051

# Kafka
KAFKA_BOOTSTRAP_SERVERS=kafka:9092
TELEMETRY_TOPIC=telemetry-flow-c

# Redis
REDIS_URL=redis://redis:6379

# Execution Tickets
EXECUTION_TICKET_SERVICE_URL=http://execution-ticket-service:8000

# Code Forge
CODE_FORGE_URL=http://code-forge:8000
```

### Logging

A biblioteca usa `structlog`:

```python
import structlog

# Configurar
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt='iso'),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer()
    ]
)
```

## Testes

### Unitários

```bash
pytest tests/test_flow_c_orchestrator.py -v
```

### Cobertura

```bash
pytest tests/ --cov=neural_hive_integration --cov-report=html
open htmlcov/index.html
```

### E2E

```bash
# Requer cluster Kubernetes
./tests/phase2-flow-c-integration-test.sh
```

## Desenvolvimento

### Setup

```bash
# Clone
git clone https://github.com/your-org/neural-hive-mind
cd neural-hive-mind/libraries/neural_hive_integration

# Install dev dependencies
pip install -e .[dev]

# Pre-commit hooks
pre-commit install
```

### Lint

```bash
black .
mypy neural_hive_integration
```

### Build

```bash
./build.sh
```

## Troubleshooting

### ServiceRegistryClient retorna lista vazia

**Causa:** Workers não registrados ou unhealthy

**Solução:**
```python
# Verificar workers registrados (sem filtro healthy)
workers = await registry.discover_agents(
    capabilities=["python"],
    filters={}  # Sem filtro
)
```

### Telemetria não publicada

**Causa:** Kafka indisponível ou tópico não existe

**Solução:**
```bash
# Verificar tópico
kubectl get kafkatopic telemetry-flow-c -n neural-hive-messaging

# Verificar buffer Redis
redis-cli get "telemetry:buffer:intent-123"
```

### HMAC validation failed

**Causa:** Secret divergente ou formato incorreto

**Solução:**
```python
# Verificar formato
signature = f"sha256={hmac_hash}"  # Correto
signature = hmac_hash              # Incorreto
```

## Documentação

- [Phase 2 Flow C Integration](../../docs/PHASE2_FLOW_C_INTEGRATION.md)
- [Service Registry Proto](../../services/service-registry/src/proto/service_registry.proto)
- [Prometheus Alerts](../../monitoring/alerts/flow-c-integration-alerts.yaml)

## Licença

Proprietary - Neural Hive Team

## Suporte

- Issues: https://github.com/your-org/neural-hive-mind/issues
- Slack: #neural-hive-integration
