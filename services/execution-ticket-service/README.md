# Execution Ticket Service

Serviço dedicado para gerenciamento do ciclo de vida completo de Execution Tickets no Neural Hive-Mind.

## Visão Geral

O **Execution Ticket Service** é responsável por:

- **Persistir** tickets em PostgreSQL (primary store) e MongoDB (audit trail)
- **Expor API REST/gRPC** para consultas e atualizações de tickets
- **Gerar tokens JWT** escopados por ticket para autorização
- **Disparar webhooks** para notificar Worker Agents quando tickets ficam prontos
- **Rastrear status** e histórico de mudanças de tickets

## Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│              Execution Ticket Service                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌────────────┐  ┌────────────┐  ┌──────────────────────┐ │
│  │ FastAPI    │  │ gRPC Server│  │ Kafka Consumer       │ │
│  │ (REST API) │  │ (port 50052│  │ (execution.tickets)  │ │
│  └─────┬──────┘  └─────┬──────┘  └──────────┬───────────┘ │
│        │               │                    │              │
│  ┌─────┴───────────────┴────────────────────┴───────────┐ │
│  │           Ticket Management Core                      │ │
│  │  • CRUD Operations                                    │ │
│  │  • Status Transitions                                 │ │
│  │  • JWT Token Generation                               │ │
│  │  • Webhook Dispatch                                   │ │
│  └───────────────────────────────────────────────────────┘ │
│        │               │                    │              │
│  ┌─────┴──────┐  ┌────┴─────┐  ┌──────────┴───────────┐ │
│  │ PostgreSQL │  │ MongoDB  │  │ Webhook Manager      │ │
│  │ (primary)  │  │ (audit)  │  │ (async queue)        │ │
│  └────────────┘  └──────────┘  └──────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Estrutura do Projeto

```
execution-ticket-service/
├── src/
│   ├── config/          # Configurações (Pydantic Settings)
│   ├── models/          # Modelos de dados (Pydantic, ORM)
│   ├── database/        # Clientes PostgreSQL e MongoDB
│   ├── api/             # Routers FastAPI
│   ├── grpc_service/    # Servidor gRPC
│   ├── consumers/       # Kafka consumers
│   ├── webhooks/        # Webhook manager
│   ├── observability/   # Métricas e tracing
│   └── main.py          # Entry point
├── alembic/             # Migrations PostgreSQL
├── protos/              # Protocol Buffers definitions
├── Dockerfile
├── requirements.txt
└── README.md
```

## Tecnologias

- **FastAPI**: Framework web assíncrono
- **gRPC**: API alternativa de alto desempenho
- **PostgreSQL 15**: Store primário de tickets
- **MongoDB 6**: Audit trail e histórico
- **Kafka**: Consumer para tópico `execution.tickets`
- **SQLAlchemy 2.0**: ORM assíncrono
- **Alembic**: Migrations
- **Motor**: Driver MongoDB assíncrono
- **PyJWT**: Geração de tokens JWT
- **Prometheus**: Métricas customizadas
- **OpenTelemetry**: Distributed tracing

## API REST

### Health & Metrics

- `GET /health` - Health check (liveness probe)
- `GET /ready` - Readiness check (dependências)
- `GET /metrics` - Métricas Prometheus

### Tickets

- `GET /api/v1/tickets/{ticket_id}` - Buscar ticket por ID
- `GET /api/v1/tickets` - Listar tickets (com filtros: plan_id, status, priority)
- `PATCH /api/v1/tickets/{ticket_id}/status` - Atualizar status
- `POST /api/v1/tickets/{ticket_id}/retry` - Retry manual (TODO)
- `GET /api/v1/tickets/{ticket_id}/token` - Gerar token JWT
- `GET /api/v1/tickets/{ticket_id}/history` - Histórico de mudanças (TODO)

## Configuração

### Variáveis de Ambiente

```bash
# Geral
SERVICE_NAME=execution-ticket-service
ENVIRONMENT=development
LOG_LEVEL=INFO

# PostgreSQL
POSTGRES_HOST=postgresql
POSTGRES_PORT=5432
POSTGRES_DATABASE=neural_hive_tickets
POSTGRES_USER=postgres
POSTGRES_PASSWORD=secret

# MongoDB
MONGODB_URI=mongodb://mongodb:27017
MONGODB_DATABASE=neural_hive_orchestration

# Kafka
KAFKA_BOOTSTRAP_SERVERS=kafka:9092
KAFKA_CONSUMER_GROUP_ID=execution-ticket-service
KAFKA_TICKETS_TOPIC=execution.tickets

# JWT
JWT_SECRET_KEY=your-secret-key
JWT_ALGORITHM=HS256
JWT_TOKEN_EXPIRATION_SECONDS=3600

# Observabilidade
OTEL_EXPORTER_ENDPOINT=http://otel-collector:4317
PROMETHEUS_PORT=9090
```

## Database Schema

### Tabela `execution_tickets`

```sql
CREATE TABLE execution_tickets (
    id BIGSERIAL PRIMARY KEY,
    ticket_id VARCHAR(36) UNIQUE NOT NULL,
    plan_id VARCHAR(36) NOT NULL,
    intent_id VARCHAR(36) NOT NULL,
    task_id VARCHAR(255) NOT NULL,
    task_type VARCHAR(20) NOT NULL,
    description TEXT NOT NULL,
    dependencies JSONB DEFAULT '[]',
    status VARCHAR(20) DEFAULT 'PENDING',
    priority VARCHAR(20) NOT NULL,
    risk_band VARCHAR(20) NOT NULL,
    sla JSONB NOT NULL,
    qos JSONB NOT NULL,
    parameters JSONB DEFAULT '{}',
    required_capabilities JSONB DEFAULT '[]',
    security_level VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    retry_count INTEGER DEFAULT 0,
    error_message TEXT,
    metadata JSONB DEFAULT '{}',
    hash VARCHAR(64),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_ticket_id ON execution_tickets(ticket_id);
CREATE INDEX idx_plan_id ON execution_tickets(plan_id);
CREATE INDEX idx_status ON execution_tickets(status);
CREATE INDEX idx_status_priority ON execution_tickets(status, priority);
```

## Observabilidade

### Métricas Prometheus

- `tickets_consumed_total` - Total de tickets consumidos do Kafka
- `tickets_persisted_total` - Total persistidos (PostgreSQL + MongoDB)
- `tickets_processing_errors_total` - Total de erros
- `api_requests_total` - Total de requests REST API
- `webhooks_sent_total` - Total de webhooks enviados
- `jwt_tokens_generated_total` - Total de tokens JWT gerados
- `postgres_queries_total` - Total de queries PostgreSQL
- `mongodb_operations_total` - Total de operações MongoDB

### Tracing

OpenTelemetry instrumentado automaticamente para:
- FastAPI requests
- SQLAlchemy queries
- gRPC calls
- HTTP webhooks

Traces exportados para Jaeger via OTLP Collector.

## Deployment

### Local Development

```bash
# Instalar dependências
pip install -r requirements.txt

# Executar migrations
alembic upgrade head

# Iniciar serviço
python -m src.main
```

### Kubernetes (via Helm)

```bash
# Deploy completo
./scripts/deploy/deploy-execution-ticket-service.sh

# Validação
./scripts/validation/validate-execution-ticket-service.sh
```

## Integração com Orchestrator

O Orchestrator Dynamic continua gerando tickets e publicando no Kafka. O Execution Ticket Service consome esses tickets e adiciona funcionalidades:

1. **Orchestrator** gera ticket → publica Kafka `execution.tickets`
2. **Ticket Service** consome → persiste PostgreSQL + MongoDB
3. **Ticket Service** gera token JWT → anexa ao metadata
4. **Ticket Service** dispara webhook → notifica Worker Agent
5. **Worker Agent** consulta ticket via API → valida token → executa
6. **Worker Agent** atualiza status via API → persiste mudanças

## Roadmap

- [ ] Implementar Kafka Consumer real (stub atual)
- [ ] Implementar Webhook Manager real (stub atual)
- [ ] Implementar gRPC Server completo
- [ ] Integrar com SPIFFE/SPIRE para tokens mTLS
- [ ] Implementar Dead Letter Queue para erros persistentes
- [ ] Adicionar rate limiting na API REST
- [ ] Dashboard Grafana customizado

## Status da Implementação

✅ **Core Completo**:
- Modelos de dados (Pydantic, ORM, migrations)
- Clientes de database (PostgreSQL async, MongoDB)
- API REST (health, tickets CRUD, token generation)
- Observabilidade (métricas, tracing, logs estruturados)
- Main application com lifecycle management

⚠️ **Componentes Stub** (implementação futura):
- Kafka Consumer (placeholder)
- Webhook Manager (placeholder)
- gRPC Server (proto definido, servicer stub)

## Contribuindo

Contribuições são bem-vindas! Por favor:

1. Siga os padrões de código existentes
2. Adicione testes para novas funcionalidades
3. Atualize a documentação
4. Execute validação completa antes de PR

## Licença

Copyright © 2025 Neural Hive-Mind Team
