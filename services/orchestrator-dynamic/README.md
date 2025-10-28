# Orchestrator Dynamic - Orquestrador Dinâmico

**Versão**: 1.0.0
**Fase**: 2.1 - Fundação do Orquestrador
**Status**: Implementação Base Completa (85%)

## Visão Geral

O **Orchestrator Dynamic** é o componente central da Fase 2 do Neural Hive-Mind, responsável por implementar o **Fluxo C - Orquestração de Execução Adaptativa** conforme descrito no `documento-06-fluxos-processos-neural-hive-mind.md`.

Este serviço consome **Consolidated Decisions** do Consensus Engine, converte **Cognitive Plans** em **Execution Tickets**, e orquestra a execução distribuída seguindo políticas de SLA, QoS e priorização baseada em risk bands.

## Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│                   Orchestrator Dynamic                       │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐    ┌──────────────────────────────────┐  │
│  │ FastAPI      │    │ Temporal Worker                  │  │
│  │              │    │                                  │  │
│  │ /health      │    │  ┌────────────────────────────┐ │  │
│  │ /ready       │    │  │ OrchestrationWorkflow      │ │  │
│  │ /metrics     │    │  │  • C1: Validate Plan       │ │  │
│  │ /api/v1/...  │    │  │  • C2: Generate Tickets    │ │  │
│  └──────────────┘    │  │  • C3: Allocate Resources  │ │  │
│                       │  │  • C4: Publish Tickets     │ │  │
│  ┌──────────────┐    │  │  • C5: Consolidate Results │ │  │
│  │ Kafka        │    │  │  • C6: Publish Telemetry   │ │  │
│  │ Consumer     │───→│  └────────────────────────────┘ │  │
│  │              │    │                                  │  │
│  │ plans.       │    │  Activities:                     │  │
│  │ consensus    │    │  • plan_validation               │  │
│  └──────────────┘    │  • ticket_generation             │  │
│                       │  • result_consolidation          │  │
│                       └──────────────────────────────────┘  │
│                                                               │
│  Observability:                                              │
│  • Prometheus Metrics (20+ métricas)                        │
│  • OpenTelemetry Tracing                                    │
│  • Structured Logging (structlog)                           │
└─────────────────────────────────────────────────────────────┘
         │                        │                   │
         ↓                        ↓                   ↓
    Kafka Topics            PostgreSQL          MongoDB
    • execution.tickets     (Temporal State)   (Auditoria)
    • orchestration.incidents
    • telemetry.orchestration
```

## Tecnologias

- **Framework**: FastAPI 0.104+
- **Workflow Engine**: Temporal 1.5+ (Python SDK)
- **Messaging**: Kafka (aiokafka)
- **State Store**: PostgreSQL 15 (Temporal)
- **Auditoria**: MongoDB 6+
- **Cache**: Redis Cluster
- **Observabilidade**: Prometheus + OpenTelemetry + Jaeger
- **Logging**: structlog

## Estrutura do Projeto

```
services/orchestrator-dynamic/
├── Dockerfile                 # Multi-stage Docker build
├── requirements.txt           # Dependências Python
├── src/
│   ├── main.py               # Entry point FastAPI + lifecycle
│   ├── config/
│   │   └── settings.py       # Pydantic Settings (Temporal, Kafka, DB)
│   ├── workflows/
│   │   └── orchestration_workflow.py  # Workflow principal Fluxo C
│   ├── activities/
│   │   ├── plan_validation.py         # C1: Validação
│   │   ├── ticket_generation.py       # C2: Geração de tickets
│   │   └── result_consolidation.py    # C5-C6: Consolidação e telemetria
│   ├── consumers/
│   │   └── decision_consumer.py       # Consumer plans.consensus
│   ├── workers/
│   │   └── temporal_worker.py         # Temporal Worker Manager
│   ├── models/
│   │   └── execution_ticket.py        # Pydantic model ExecutionTicket
│   └── observability/
│       └── metrics.py                 # Métricas Prometheus
└── README.md (este arquivo)
```

## Fluxo de Execução (Fluxo C)

### Etapa C1: Validar Plano Cognitivo
- Verifica schema Avro do Cognitive Plan
- Valida campos obrigatórios, versão, expiração
- Detecta ciclos no DAG de dependências
- Audita resultado no MongoDB

### Etapa C2: Quebrar Plano em Tickets
- Gera um `ExecutionTicket` para cada task do plano
- Calcula SLA baseado em `risk_band` e `estimated_duration_ms`
- Define QoS (delivery_mode, consistency, durability)
- Mapeia dependencies (task_ids → ticket_ids)
- Ordena tickets topologicamente

### Etapa C3: Alocar Recursos
- Verifica `required_capabilities` (stub para MVP)
- Aplica priorização baseada em `risk_band` e `priority`
- Calcula `priority_score` para scheduler

### Etapa C4: Executar Tarefas
- Publica cada ticket no Kafka `execution.tickets`
- Aguarda confirmação de publicação
- Atualiza status do ticket para `RUNNING`
- Persiste ticket no MongoDB para auditoria

### Etapa C5: Consolidar Resultado
- Agrega resultados de todos os tickets
- Calcula métricas (duração, sucesso/falha, retries, SLA violations)
- Valida integridade (verifica inconsistências)
- Aciona autocura (Fluxo E) se necessário

### Etapa C6: Publicar Telemetria
- Cria Telemetry Frame com correlação completa
- Publica no Kafka `telemetry.orchestration`
- Exporta métricas para Prometheus
- Cria span OpenTelemetry para o workflow
- Buffer local em caso de falha

## Schemas

### Execution Ticket (Avro)
Ver: `schemas/execution-ticket/execution-ticket.avsc`

**Campos principais**:
- `ticket_id`, `plan_id`, `intent_id`, `decision_id`
- `task_id`, `task_type`, `description`, `dependencies`
- `status`, `priority`, `risk_band`
- `sla` (deadline, timeout_ms, max_retries)
- `qos` (delivery_mode, consistency, durability)
- `created_at`, `started_at`, `completed_at`
- `retry_count`, `error_message`, `compensation_ticket_id`

## Configuração

Todas as configurações são gerenciadas via variáveis de ambiente ou arquivo `.env`:

```bash
# Temporal
TEMPORAL_HOST=temporal-frontend.temporal.svc.cluster.local
TEMPORAL_PORT=7233
TEMPORAL_NAMESPACE=neural-hive-mind
TEMPORAL_TASK_QUEUE=orchestration-tasks

# Kafka
KAFKA_BOOTSTRAP_SERVERS=kafka-bootstrap.kafka.svc.cluster.local:9092
KAFKA_CONSENSUS_TOPIC=plans.consensus
KAFKA_TICKETS_TOPIC=execution.tickets
KAFKA_CONSUMER_GROUP_ID=orchestrator-dynamic

# PostgreSQL (Temporal State)
POSTGRES_HOST=postgres-temporal-headless.temporal-postgres.svc.cluster.local
POSTGRES_PORT=5432
POSTGRES_DATABASE=temporal
POSTGRES_USER=temporal
POSTGRES_PASSWORD=<secret>

# MongoDB (Auditoria)
MONGODB_URI=mongodb://mongodb-0.mongodb-headless:27017,.../?replicaSet=rs0
MONGODB_DATABASE=neural_hive_orchestration

# Redis (Cache)
REDIS_CLUSTER_NODES=redis-cluster.redis-cluster.svc.cluster.local:6379

# SLA e Scheduler
SLA_DEFAULT_TIMEOUT_MS=3600000
SCHEDULER_MAX_PARALLEL_TICKETS=100

# Observabilidade
OTEL_EXPORTER_ENDPOINT=http://otel-collector:4317
LOG_LEVEL=INFO
```

## Métricas Prometheus

O serviço exporta 20+ métricas em `/metrics`:

**Workflows**:
- `orchestration_workflows_started_total`
- `orchestration_workflows_completed_total`
- `orchestration_workflow_duration_seconds`
- `orchestration_workflows_active`

**Tickets**:
- `orchestration_tickets_generated_total`
- `orchestration_tickets_published_total`
- `orchestration_tickets_completed_total`
- `orchestration_ticket_generation_duration_seconds`

**SLA**:
- `orchestration_sla_violations_total`
- `orchestration_sla_remaining_seconds`
- `orchestration_deadline_approaching_total`

**Kafka**:
- `orchestration_kafka_messages_consumed_total`
- `orchestration_kafka_messages_produced_total`
- `orchestration_kafka_consumer_lag`
- `orchestration_kafka_errors_total`

**Outros**: retries, compensations, validations, resources

## Deployment

### Via Script (Recomendado)
```bash
cd /path/to/Neural-Hive-Mind

# Deploy completo (build, push, secrets, helm)
./scripts/deploy/deploy-orchestrator-dynamic.sh

# Validação completa
./scripts/validation/validate-orchestrator-dynamic.sh
```

### Via Helm Manual
```bash
cd helm-charts/orchestrator-dynamic

# Lint
helm lint .

# Install/Upgrade
helm upgrade --install orchestrator-dynamic . \
  --namespace neural-hive-orchestration \
  --create-namespace \
  --values values.yaml \
  --set image.tag=1.0.0 \
  --wait
```

## Desenvolvimento Local

### Prerequisites
- Python 3.11+
- Docker
- Temporal CLI (opcional, para debugging)
- Kafka running
- PostgreSQL running
- MongoDB running

### Setup
```bash
cd services/orchestrator-dynamic

# Criar virtualenv
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# Instalar dependências
pip install -r requirements.txt

# Configurar .env
cp .env.example .env
# Editar .env com credenciais locais

# Run
python -m src.main
```

### Testes
```bash
# Unit tests
pytest tests/

# Linting
black src/
flake8 src/
mypy src/

# Integration test
./tests/phase2-orchestrator-test.sh
```

## Monitoramento

### Grafana Dashboard
Ver: `docs/observability/dashboards/orchestration-flow-c.json`

**Rows**:
1. Overview (workflows started/completed, success rate)
2. Workflow Duration (P50/P95/P99)
3. Tickets (generated, published, completed)
4. SLA Tracking (violations, remaining time, compliance)
5. Retry and Compensation
6. Kafka Integration
7. Validations and Optimizations
8. Resources (CPU, Memory, Pods)
9. Logs and Traces

### Jaeger
Traces disponíveis em: `http://jaeger-query:16686`
- Filtrar por service: `orchestrator-dynamic`
- Buscar por workflow_id ou plan_id
- Visualizar correlação intent_id → plan_id → workflow_id → ticket_ids

## Troubleshooting

### Workflow não inicia
```bash
# Verificar consumer Kafka
kubectl logs -n neural-hive-orchestration -l app.kubernetes.io/name=orchestrator-dynamic | grep "Consumer"

# Verificar mensagens no tópico
kubectl exec -n kafka kafka-0 -- kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic plans.consensus \
  --from-beginning --max-messages 10
```

### Tickets não são publicados
```bash
# Verificar logs de activities
kubectl logs -n neural-hive-orchestration -l app.kubernetes.io/name=orchestrator-dynamic | grep "publish_ticket"

# Verificar tópico execution.tickets
kubectl exec -n kafka kafka-0 -- kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe --topic execution.tickets
```

### SLA violations altos
```bash
# Verificar métricas
curl http://<pod-ip>:9090/metrics | grep sla_violations

# Ajustar timeouts em values.yaml
helm upgrade orchestrator-dynamic . \
  --set config.sla.defaultTimeoutMs=7200000  # 2 horas
```

## Roadmap

### Fase 2.2 - QoS e Políticas (Próximo)
- [ ] Scheduler Inteligente com balanceamento de carga
- [ ] Integração OPA para validação de políticas
- [ ] Alertas automáticos para SLA violations
- [ ] Modelos preditivos para estimativa de duração

### Fase 2.3 - Integrações Avançadas
- [ ] Service Registry para discovery de Worker Agents
- [ ] Tokens efêmeros via Vault/SPIFFE
- [ ] Feromônios digitais para ajuste dinâmico
- [ ] Replay de workflows para debugging

## Referências

- [Documento 06 - Fluxos e Processos](../../documento-06-fluxos-processos-neural-hive-mind.md)
- [Orquestração - Visão Detalhada](../../docs/observability/services/orquestracao.md)
- [Execution Ticket Schema](../../schemas/execution-ticket/execution-ticket.avsc)
- [Temporal Documentation](https://docs.temporal.io/)
- [PHASE2_IMPLEMENTATION_STATUS.md](../../PHASE2_IMPLEMENTATION_STATUS.md)

---

**Mantenedores**: Neural Hive-Mind Team
**Última atualização**: 2025-10-03
**Licença**: Proprietária
