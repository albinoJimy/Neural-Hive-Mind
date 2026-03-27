# Architect Agent

Sistema de arquitetura de software do Neural Hive-Mind - responsável por planejamento, validação e tracking evolutivo de arquiteturas.

## Visão Geral

O Architect Agent é um microserviço especializado em:

- **Planejamento de Arquitetura**: Gera planos de arquitetura baseados em requisitos funcionais e não-funcionais
- **Validação de Repositórios**: Analisa código existente e identifica violações de padrões arquiteturais
- **Tracking Evolutivo**: Detecta drifts entre arquitetura planejada e implementada

## Stack Tecnológica

- **Python 3.12+**
- **FastAPI**: Framework web assíncrono
- **MongoDB**: Persistência de planos e relatórios
- **Kafka**: Mensageria para consumo de planos cognitivos
- **OPA**: Open Policy Agent para validação de políticas
- **Prometheus**: Métricas e observabilidade

## Estrutura do Projeto

```
architect-agent/
├── src/
│   ├── api/              # Endpoints REST
│   ├── config/           # Configurações (Pydantic Settings)
│   ├── consumers/        # Kafka consumers
│   ├── evolution/        # Tracking evolutivo
│   ├── models/           # Modelos de domínio
│   ├── observability/    # Métricas e tracing
│   ├── planners/         # Planejadores de arquitetura
│   ├── repositories/     # Repositórios MongoDB
│   └── validators/       # Motores de validação
├── tests/
│   ├── unit/            # Testes unitários
│   ├── integration/     # Testes de integração
│   └── e2e/             # Testes E2E
├── helm/                # Kubernetes Helm chart
└── Dockerfile           # Imagem container
```

## Configuração

O serviço utiliza Pydantic Settings para configuração via variáveis de ambiente:

```bash
# Configurações básicas
SERVICE__ENVIRONMENT=production
SERVICE__LOG_LEVEL=INFO
SERVICE__HTTP_PORT=8008

# MongoDB
MONGODB_URL=mongodb://mongodb:27017
MONGODB_DATABASE=architect_agent

# Kafka
KAFKA_BOOTSTRAP_SERVERS=kafka:9092
KAFKA_COGNITIVE_PLANS_TOPIC=cognitive.plans.created

# Scout Agents
SCOUT_AGENTS_URL=http://scout-agents:8000

# OPA
OPA_URL=http://opa:8181
OPA_POLICY_PATH=architecture/rules

# LLM (opcional)
LLM_PROVIDER=openai
LLM_API_KEY=sk-...
```

## Desenvolvimento Local

### Pré-requisitos

- Python 3.12+
- MongoDB 7.0+
- Kafka 3.5+
- Docker Compose (para testes de integração)

### Instalação

```bash
# Clonar o repositório
git clone https://github.com/albinoJimy/Neural-Hive-Mind.git
cd Neural-Hive-Mind/services/architect-agent

# Criar ambiente virtual
python -m venv .venv
source .venv/bin/activate

# Instalar dependências
pip install -r requirements.txt
```

### Executar Localmente

```bash
# Configurar variáveis de ambiente
export SERVICE__ENVIRONMENT=development
export MONGODB_URL=mongodb://localhost:27017
export KAFKA_BOOTSTRAP_SERVERS=localhost:9092

# Executar serviço
python -m src.main
```

### Testes

```bash
# Testes unitários
pytest tests/unit/ -v

# Testes de integração (requer Docker Compose)
pytest tests/integration/ -v --manage-docker

# Testes com cobertura
pytest --cov=src tests/ -v

# Linting
ruff check src/
black --check src/

# Type checking
mypy src/
```

### Docker Compose para Desenvolvimento

```bash
# Subir serviços de dependência
docker-compose -f tests/integration/docker-compose.integration.yml up -d

# Executar testes de integração
pytest tests/integration/ -v

# Derrubar serviços
docker-compose -f tests/integration/docker-compose.integration.yml down -v
```

## API REST

### Planejamento de Arquitetura

#### Criar Plano de Arquitetura

```http
POST /api/v1/architecture
Content-Type: application/json

{
  "intent": "design user management api",
  "context": {
    "requirements": ["rest", "authentication", "crud"]
  },
  "cognitive_plan_id": "plan-123"
}
```

#### Buscar Plano por ID

```http
GET /api/v1/architecture/{plan_id}
```

#### Listar Planos

```http
GET /api/v1/architecture?limit=50&architecture_type=microservices
```

### Validação de Repositórios

#### Validar Repositório

```http
POST /api/v1/validation
Content-Type: application/json

{
  "repo_url": "https://github.com/example/repo",
  "branch": "main"
}
```

#### Buscar Relatório de Validação

```http
GET /api/v1/validation/{report_id}
```

#### Listar Validações por Repositório

```http
GET /api/v1/validation/repo/{repo_url}?limit=10
```

### Health Checks

```http
GET /health/live   # Liveness probe
GET /health/ready  # Readiness probe
GET /metrics       # Prometheus metrics
```

## Deploy no Kubernetes

### Via Helm Chart

```bash
# Adicionar repositório Helm (se aplicável)
helm repo add neural-hive-mind https://albinojimy.github.io/Neural-Hive-Mind

# Instalar chart
helm install architect-agent helm/architect-agent \
  --namespace neural-hive-mind \
  --create-namespace \
  --set config.mongodb.url=mongodb://mongodb:27017 \
  --set config.kafka.bootstrapServers=kafka:9092

# Upgrade
helm upgrade architect-agent helm/architect-agent

# Uninstall
helm uninstall architect-agent
```

### Configuração via Values

```yaml
# values-custom.yaml
config:
  mongodb:
    url: "mongodb://mongodb-service:27017"
  kafka:
    bootstrapServers: "kafka-service:9092"
  llm:
    enabled: true
    provider: "openai"
```

```bash
helm install architect-agent helm/architect-agent -f values-custom.yaml
```

## Modelos de Dados

### ArchitecturePlan

```python
{
  "plan_id": "arch-123",
  "cognitive_plan_id": "cp-456",
  "architecture_type": "microservices",
  "components": [
    {
      "name": "api-gateway",
      "stack": "python/fastapi",
      "replicas": 2,
      "ha": true
    }
  ],
  "patterns": ["api_gateway", "circuit_breaker"],
  "rationale": "Microservices para escala independente",
  "requirements": {
    "scalability": "high",
    "availability": "99.9%"
  }
}
```

### ValidationReport

```python
{
  "report_id": "validation-123",
  "repo_url": "https://github.com/example/repo",
  "branch": "main",
  "health_score": 85,
  "trend": "stable",
  "violations": [
    {
      "type": "security",
      "severity": "high",
      "location": "src/auth.py:45",
      "description": "Hardcoded API key"
    }
  ],
  "suggestions": [
    {
      "priority": 1,
      "description": "Add input validation",
      "effort": "low",
      "affected_files": ["src/api/handlers.py"]
    }
  ]
}
```

## Observabilidade

### Métricas Prometheus

O serviço expõe métricas em `/metrics`:

- `architect_planning_duration_seconds`: Duração do planejamento
- `architect_validation_duration_seconds`: Duração da validação
- `architect_drift_detected_total`: Contagem de drifts detectados
- `process_cpu_usage`, `process_memory_usage`: Métricas de infraestrutura

### Tracing

OpenTelemetry tracing configurado para enviar para Jaeger:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317
export OTEL_TRACES_SAMPLER=traceidratio
export OTEL_TRACES_SAMPLER_ARG=0.1
```

## Arquitetura Interna

```
┌─────────────────────────────────────────────────────────────┐
│                     Architect Agent                          │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   API REST   │  │ Kafka        │  │              │      │
│  │   (FastAPI)  │  │ Consumer     │  │              │      │
│  └──────┬───────┘  └──────┬───────┘  │              │      │
│         │                  │          │              │      │
│         ▼                  ▼          ▼              │      │
│  ┌──────────────────────────────────────────────────┐     │
│  │              Service Layer                         │     │
│  │  ┌──────────────┐ ┌──────────────┐               │     │
│  │  │DesignPlanner │ │ValidateEngine│               │     │
│  │  └──────┬───────┘ └──────┬───────┘               │     │
│  └─────────┼────────────────┼───────────────────────┘     │
│            │                │                              │
│  ┌─────────▼────────────────▼───────────────────────┐     │
│  │              Repository Layer                      │     │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────────────┐  │     │
│  │  │Architecture│Validation│ │ Evolution        │  │     │
│  │  │Repository │Repository │ │ Repository        │  │     │
│  │  └──────────┘ └──────────┘ └──────────────────┘  │     │
│  └──────────────────────────────────────────────────┘     │
│                          │                                  │
└──────────────────────────┼──────────────────────────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │   MongoDB   │
                    └─────────────┘
```

## Troubleshooting

### Problemas Comuns

**1. MongoDB Connection Error**

```bash
# Verificar se MongoDB está acessível
mongosh mongodb://localhost:27017

# Verificar variáveis de ambiente
echo $MONGODB_URL
```

**2. Kafka Consumer não inicia**

```bash
# Verificar se tópico existe
kafka-topics --list --bootstrap-server localhost:9092

# Criar tópico se necessário
kafka-topics --create --topic cognitive.plans.created \
  --bootstrap-server localhost:9092
```

**3. OPA Policy não carrega**

```bash
# Verificar health check do OPA
curl http://localhost:8181/health

# Verificar se política existe
curl http://localhost:8181/v1/policies
```

## Contribuindo

Ver `CLAUDE.md` para diretrizes de desenvolvimento.

## Licença

MIT License - ver LICENSE para detalhes.
