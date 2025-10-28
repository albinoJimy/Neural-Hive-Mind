# Worker Agents

## Visão Geral

Worker Agents são executores distribuídos responsáveis por consumir Execution Tickets do Kafka, coordenar dependências, executar tarefas e reportar resultados. Implementam o lado de execução do Fluxo C da arquitetura Neural Hive-Mind.

### Responsabilidades

1. **Consumir Execution Tickets** do Kafka `execution.tickets`
2. **Registrar-se no Service Registry** com capabilities, telemetria e health status
3. **Executar tarefas** via executors específicos por task_type
4. **Coordenar dependências** verificando status de tickets predecessores
5. **Garantir SLAs** respeitando timeouts, max_retries e deadlines
6. **Acionar compensações** em caso de falha (criar compensation tickets)
7. **Reportar feedback** ao Orchestrator via Kafka `execution.results` e API
8. **Integrar com Istio** (mTLS), OpenTelemetry (tracing), Prometheus (metrics)
9. **Health checks periódicos** enviando heartbeats ao Service Registry

### Status

**MVP Completo** - Fase 2.5 implementada com executores stub para demonstração.

## Arquitetura

```
┌─────────────────────────────────────────────────────────┐
│                    Worker Agent                         │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────────┐         ┌─────────────────┐          │
│  │ Kafka        │────────→│ Execution       │          │
│  │ Consumer     │         │ Engine          │          │
│  │ (tickets)    │         └─────────────────┘          │
│  └──────────────┘                   │                   │
│                                      ↓                   │
│  ┌──────────────┐         ┌─────────────────┐          │
│  │ Service      │         │ Dependency      │          │
│  │ Registry     │←────────│ Coordinator     │          │
│  │ Client       │         └─────────────────┘          │
│  └──────────────┘                   │                   │
│                                      ↓                   │
│  ┌──────────────┐         ┌─────────────────┐          │
│  │ Execution    │←────────│ Task Executor   │          │
│  │ Ticket       │         │ Registry        │          │
│  │ Client       │         └─────────────────┘          │
│  └──────────────┘                   │                   │
│                           ┌──────────┴──────────┐       │
│  ┌──────────────┐         │                     │       │
│  │ Kafka        │         │  5 Executors:       │       │
│  │ Producer     │←────────│  - BUILD            │       │
│  │ (results)    │         │  - DEPLOY           │       │
│  └──────────────┘         │  - TEST             │       │
│                           │  - VALIDATE         │       │
│  ┌──────────────┐         │  - EXECUTE          │       │
│  │ HTTP Server  │         └─────────────────────┘       │
│  │ (health,     │                                        │
│  │  metrics)    │                                        │
│  └──────────────┘                                        │
└─────────────────────────────────────────────────────────┘
```

## Tecnologias

- **FastAPI** - REST API para health/metrics
- **aiokafka** - Consumer/Producer assíncrono
- **grpcio** - Cliente gRPC para Service Registry
- **httpx** - Cliente HTTP async para Execution Ticket Service
- **temporalio** - (Opcional) Activity workers
- **Prometheus** - Métricas
- **OpenTelemetry** - Distributed tracing
- **structlog** - Logging estruturado
- **Python 3.11+**

## Estrutura do Projeto

```
services/worker-agents/
├── Dockerfile              # Multi-stage build
├── requirements.txt        # Dependências Python
├── src/
│   ├── main.py            # Entry point principal
│   ├── config/            # Configurações
│   │   └── settings.py
│   ├── clients/           # Clientes de integração
│   │   ├── service_registry_client.py
│   │   ├── execution_ticket_client.py
│   │   ├── kafka_ticket_consumer.py
│   │   └── kafka_result_producer.py
│   ├── engine/            # Lógica de execução
│   │   ├── execution_engine.py
│   │   └── dependency_coordinator.py
│   ├── executors/         # Executores por task_type
│   │   ├── base_executor.py
│   │   ├── registry.py
│   │   ├── build_executor.py
│   │   ├── deploy_executor.py
│   │   ├── test_executor.py
│   │   ├── validate_executor.py
│   │   └── execute_executor.py
│   ├── api/               # HTTP API
│   │   └── http_server.py
│   ├── models/            # Modelos Pydantic
│   │   ├── execution_ticket.py
│   │   └── execution_result.py
│   └── observability/     # Métricas e tracing
│       └── metrics.py
```

## Configuração

### Variáveis de Ambiente

```bash
# Identificação
SERVICE_NAME=worker-agents
NAMESPACE=neural-hive-execution
CLUSTER=production

# Capabilities
SUPPORTED_TASK_TYPES=BUILD,DEPLOY,TEST,VALIDATE,EXECUTE
MAX_CONCURRENT_TASKS=5

# Kafka
KAFKA_BOOTSTRAP_SERVERS=kafka:9092
KAFKA_TICKETS_TOPIC=execution.tickets
KAFKA_RESULTS_TOPIC=execution.results
KAFKA_CONSUMER_GROUP_ID=worker-agents

# Service Registry
SERVICE_REGISTRY_HOST=service-registry
SERVICE_REGISTRY_PORT=50051
HEARTBEAT_INTERVAL_SECONDS=30

# Execution Ticket Service
EXECUTION_TICKET_SERVICE_URL=http://execution-ticket-service:8080

# Temporal (opcional)
ENABLE_TEMPORAL_ACTIVITIES=false

# Observabilidade
OTEL_EXPORTER_ENDPOINT=http://otel-collector:4317
PROMETHEUS_PORT=9090
HTTP_PORT=8080
LOG_LEVEL=INFO
```

## Deployment

### Via Script

```bash
./scripts/deploy/deploy-worker-agents.sh
```

### Via Helm

```bash
helm upgrade --install worker-agents \
  ./helm-charts/worker-agents \
  --namespace neural-hive-execution \
  --create-namespace
```

### Pré-requisitos

- Kafka cluster rodando
- Service Registry rodando
- Execution Ticket Service rodando
- Orchestrator Dynamic rodando
- Tópico `execution.tickets` criado
- Tópico `execution.results` criado

## Desenvolvimento Local

### Setup

```bash
cd services/worker-agents
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Execução

```bash
export KAFKA_BOOTSTRAP_SERVERS=localhost:9092
export SERVICE_REGISTRY_HOST=localhost
export EXECUTION_TICKET_SERVICE_URL=http://localhost:8080

python -m src.main
```

## Métricas Prometheus

### Lifecycle
- `worker_agent_startup_total` - Inicializações
- `worker_agent_registered_total` - Registros no Service Registry
- `worker_agent_heartbeat_total{status}` - Heartbeats enviados
- `worker_agent_deregistered_total` - Deregistros

### Tickets
- `worker_agent_tickets_consumed_total{task_type}` - Tickets consumidos
- `worker_agent_tickets_processing_total{task_type}` - Tickets em processamento
- `worker_agent_tickets_completed_total{task_type}` - Tickets concluídos
- `worker_agent_tickets_failed_total{task_type,error_type}` - Tickets falhados
- `worker_agent_active_tasks` - Tarefas ativas
- `worker_agent_task_duration_seconds{task_type}` - Duração de execução

### Dependencies
- `worker_agent_dependency_checks_total{result}` - Verificações de dependências
- `worker_agent_dependency_wait_duration_seconds` - Tempo de espera

### Retries
- `worker_agent_task_retries_total{task_type,attempt}` - Tentativas de retry
- `worker_agent_tasks_cancelled_total` - Tarefas canceladas

### API & Kafka
- `worker_agent_ticket_api_calls_total{method,status}` - Chamadas à API
- `worker_agent_results_published_total{status}` - Resultados publicados

## Monitoramento

### Dashboard Grafana

Dashboard disponível em `observability/grafana/dashboards/worker-agents-execution.json`

### Queries PromQL Úteis

```promql
# Taxa de sucesso
sum(rate(worker_agent_tickets_completed_total[5m]))
/
sum(rate(worker_agent_tickets_consumed_total[5m]))

# Duração P95 por task_type
histogram_quantile(0.95,
  rate(worker_agent_task_duration_seconds_bucket[5m])
)

# Tarefas ativas
sum(worker_agent_active_tasks)
```

## Troubleshooting

### Consumer não conecta ao Kafka

```bash
kubectl logs -n neural-hive-execution -l app.kubernetes.io/name=worker-agents | grep kafka
```

### Registro no Service Registry falha

```bash
kubectl logs -n neural-hive-execution -l app.kubernetes.io/name=worker-agents | grep registration
```

### Tickets não são processados

```bash
# Verificar consumer lag
kubectl exec -n kafka kafka-0 -- kafka-consumer-groups \
  --bootstrap-server localhost:9092 \
  --describe --group worker-agents
```

### Dependências não são resolvidas

```bash
kubectl logs -n neural-hive-execution -l app.kubernetes.io/name=worker-agents | grep dependency
```

## Roadmap

### Fase 2.6 - Executores Reais
- Integrar com Code Forge para BUILD executor
- Integrar com ArgoCD/Flux para DEPLOY executor
- Executar pipelines CI/CD reais (GitLab CI, Tekton)
- Validar artefatos com SBOM e Sigstore

### Fase 2.7 - Temporal Integration
- Implementar Temporal activities para workflows complexos
- Suportar execução distribuída de tarefas longas
- Integrar com compensation workflows

### Fase 3 - Edge Execution
- Suportar execução em edge nodes
- Implementar data locality para workloads edge
- Advanced retry strategies com circuit breakers

## Referências

- [Arquitetura de Orquestração](../../docs/observability/services/orquestracao.md)
- [Execution Ticket Schema](../../schemas/execution-ticket/execution-ticket.avsc)
- [Service Registry](../service-registry/README.md)
- [Execution Ticket Service](../execution-ticket-service/README.md)
