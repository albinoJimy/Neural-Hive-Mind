# neural-hive-api

Biblioteca de padroes de plataforma para servicos Neural-Hive-Mind.

## Instalacao

```bash
pip install neural-hive-api
```

## Funcionalidades

### Health Check

Router padrao para endpoints de health check com suporte a liveness/readiness probes do Kubernetes.

#### Uso Basico

```python
from fastapi import FastAPI
from neural_hive_api.health import HealthRouter, HealthCheckResult

app = FastAPI()

# Criar router
health_router = HealthRouter(
    service_name="meu-servico",
    version="1.0.0"
)

# Adicionar checks
async def check_database() -> HealthCheckResult:
    try:
        # Seu check de database
        await database.ping()
        return HealthCheckResult(status="healthy")
    except Exception as e:
        return HealthCheckResult(
            status="unhealthy",
            message=str(e)
        )

health_router.add_check("database", check_database, critical=True)

# Registrar router
app.include_router(health_router.router, prefix="/health", tags=["health"])
```

#### Endpoints Disponiveis

- `GET /health` - Status agregado com todos os checks
- `GET /health/live` - Liveness probe (Kubernetes)
- `GET /health/ready` - Readiness probe (Kubernetes)

#### Response Format

```json
{
  "status": "healthy",
  "service": "meu-servico",
  "version": "1.0.0",
  "timestamp": "2026-04-02T12:00:00Z",
  "checks": {
    "database": {
      "status": "healthy"
    },
    "kafka": {
      "status": "degraded",
      "message": "High latency"
    }
  }
}
```

### Kafka Topics

Configuracao padrao para topicos Kafka com convencao de nomes e criacao automatica.

#### Uso Basico

```python
from neural_hive_api.kafka import KafkaTopicsConfig, get_topic

class MeusTopicos(KafkaTopicsConfig):
    PREFIX = "meu-servico"

    # Define topicos seguindo a convencao
    EXECUTION_STARTED = get_topic("execution", "started")
    EXECUTION_RESULTS = get_topic("execution", "results")
    EXECUTION_FAILED = get_topic("execution", "failed")

# Instancia
topics = MeusTopicos()

# Usar topicos
print(topics.EXECUTION_RESULTS)  # "meu-servico.execution.results"
```

#### Criar Topicos

```python
# No startup do servico
await MeusTopicos.create_topics()
```

#### Configuracao Avancada

```python
class MeusTopicos(KafkaTopicsConfig):
    PREFIX = "meu-servico"

    # Topico com configuracao customizada
    EXECUTION_RESULTS = get_topic(
        "execution",
        "results",
        partitions=12,
        replication_factor=3,
        retention_ms=7 * 24 * 60 * 60 * 1000  # 7 dias
    )
```

#### Convencao de Nomes

```
{service}.{domain}.{entity}.{event}
```

Exemplos:
- `meu-servico.execution.started`
- `meu-servico.execution.results`
- `analyst.insights.created`

## Configuracao

### Variaveis de Ambiente

| Variavel | Default | Descricao |
|----------|---------|-----------|
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | Servidores Kafka |
| `KAFKA_DEFAULT_PARTITIONS` | `12` | Numero padrao de particoes |
| `KAFKA_DEFAULT_REPLICATION` | `3` | Fator de replicacao padrao |
| `HEALTH_CHECK_CACHE_TTL` | `5` | Cache TTL para checks (segundos) |

## Desenvolvimento

### Setup

```bash
# Clonar repositorio
git clone https://github.com/albinoJimy/Neural-Hive-Mind.git

# Instalar dependencias de desenvolvimento
cd libraries/python/neural_hive_api
pip install -e ".[dev]"

# Rodar testes
pytest
```

### Estrutura

```
neural_hive_api/
├── __init__.py
├── health/
│   ├── __init__.py
│   ├── router.py      # HealthRouter
│   └── models.py      # HealthCheckResult
└── kafka/
    ├── __init__.py
    ├── topics.py      # KafkaTopicsConfig, get_topic
    └── producer.py    # Producer wrapper (futuro)
```

## Contribuindo

1. Fork o repositorio
2. Criar branch para feature (`git checkout -b feature/nova-feature`)
3. Commit mudancas (`git commit -m 'Add nova feature'`)
4. Push para branch (`git push origin feature/nova-feature`)
5. Abrir Pull Request

## Licenca

MIT License - ver arquivo LICENSE

## Suporte

Para duvidas e problemas:
- Issues: https://github.com/albinoJimy/Neural-Hive-Mind/issues
- Documentacao: https://github.com/albinoJimy/Neural-Hive-Mind/tree/main/docs/platform-standardization
