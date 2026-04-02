# Guia de Migracao para Padrao de Plataforma - Neural-Hive-Mind

## Visao Geral

Este guia fornece instrucoes passo-a-passo para migrar um servico existente para os padroes de plataforma definidos no Neural-Hive-Mind.

## Pré-requisitos

- Servico usando FastAPI
- Python 3.12+
- Acesso ao cluster Kafka
- Acesso ao MongoDB

## Passo 1: Adicionar Dependencia

### pyproject.toml

```toml
[project]
dependencies = [
    "neural-hive-api>=0.1.0",
    # ... outras dependencias
]
```

### Instalar

```bash
pip install neural-hive-api
```

## Passo 2: Migrar Health Check

### 2.1 Remover Implementacao Antiga

```python
# REMOVER este codigo do seu main.py ou routers/health.py

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.get("/health/live")
async def liveness():
    return {"status": "alive"}

@app.get("/health/ready")
async def readiness():
    return {"status": "ready"}
```

### 2.2 Adicionar Health Router Padrao

```python
# NOVO: src/api/health.py (ou adicionar ao main.py)

from neural_hive_api.health import HealthRouter, HealthCheckResult
from .database import get_database
from .kafka import get_kafka_producer

# Criar router
health_router = HealthRouter(
    service_name="meu-servico",
    version="1.0.0"
)

# Adicionar checks
async def check_database() -> HealthCheckResult:
    """Check de conexao com MongoDB"""
    try:
        db = get_database()
        await db.command("ping")
        return HealthCheckResult(status="healthy")
    except Exception as e:
        return HealthCheckResult(
            status="unhealthy",
            message=str(e)
        )

async def check_kafka() -> HealthCheckResult:
    """Check de conexao com Kafka"""
    try:
        producer = get_kafka_producer()
        # Verifica se producer esta conectado
        if producer and producer._producer:
            return HealthCheckResult(status="healthy")
        return HealthCheckResult(status="unhealthy", message="Producer not connected")
    except Exception as e:
        return HealthCheckResult(
            status="unhealthy",
            message=str(e)
        )

# Registrar checks
health_router.add_check("database", check_database, critical=True)
health_router.add_check("kafka", check_kafka, critical=True)
```

### 2.3 Registrar no FastAPI

```python
# main.py

from fastapi import FastAPI
from .api.health import health_router

app = FastAPI()

# Substituir antigo router pelo novo
app.include_router(
    health_router.router,
    prefix="/health",
    tags=["health"]
)
```

### 2.4 Testar

```bash
# Testar endpoints
curl http://localhost:8000/health
curl http://localhost:8000/health/live
curl http://localhost:8000/health/ready
```

## Passo 3: Migrar Topicos Kafka

### 3.1 Remover Definicoes Antigas

```python
# REMOVER: src/kafka/topics.py

TOPIC_EXECUTION_RESULTS = "execution-results"
TOPIC_INSIGHTS_CREATED = "insights-created"
```

### 3.2 Adicionar Configuracao Padrao

```python
# NOVO: src/kafka/topics.py

from neural_hive_api.kafka import KafkaTopicsConfig, get_topic

class MeuServicoTopics(KafkaTopicsConfig):
    PREFIX = "meu-servico"

    # Eventos de execucao
    EXECUTION_STARTED = get_topic("execution", "started")
    EXECUTION_RESULTS = get_topic("execution", "results")
    EXECUTION_FAILED = get_topic("execution", "failed")

    # Eventos de insights
    INSIGHT_CREATED = get_topic("insights", "created")
    INSIGHT_VALIDATED = get_topic("insights", "validated")

# Instancia para uso
topics = MeuServicoTopics()
```

### 3.3 Atualizar Produtores

```python
# ANTES
from .kafka.topics import TOPIC_EXECUTION_RESULTS

async def publish_result(result: ExecutionResult):
    await producer.produce(
        topic=TOPIC_EXECUTION_RESULTS,
        value=result.json()
    )

# DEPOIS
from .kafka.topics import topics

async def publish_result(result: ExecutionResult):
    await producer.produce(
        topic=topics.EXECUTION_RESULTS,
        key=str(result.agent_id).encode(),  # Importante: adicionar chave
        value=create_event_envelope(
            event_type="execution.results",
            producer="meu-servico",
            data=result.dict()
        )
    )
```

### 3.4 Atualizar Consumidores

```python
# ANTES
from .kafka.topics import TOPIC_INSIGHT_CREATED

consumer.subscribe([TOPIC_INSIGHT_CREATED])

# DEPOIS
from .kafka.topics import topics

consumer.subscribe([topics.INSIGHT_CREATED])
```

## Passo 4: Criar Topicos no Startup

```python
# main.py

@app.on_event("startup")
async def startup():
    # Criar topicos Kafka
    from .kafka.topics import MeuServicoTopics
    await MeuServicoTopics.create_topics()

    # Outras inicializacoes...
```

## Passo 5: Atualizar Configuracao Kubernetes

```yaml
# deployment.yaml

livenessProbe:
  httpGet:
    path: /health/live
    port: 8000
  initialDelaySeconds: 30
  periodSeconds: 10
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /health/ready
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 5
  failureThreshold: 2
```

## Passo 6: Atualizar Testes

```python
# tests/test_health.py

import pytest
from httpx import AsyncClient

async def test_health_endpoint(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "service" in data
    assert data["service"] == "meu-servico"

async def test_health_live(client: AsyncClient):
    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}

async def test_health_ready(client: AsyncClient):
    response = await client.get("/health/ready")
    assert response.status_code == 200
    assert "status" in response.json()
```

## Checklist de Migracao

- [ ] Dependencia `neural-hive-api` adicionada
- [ ] Health check antigo removido
- [ ] `HealthRouter` implementado com checks criticos
- [ ] Health endpoints registrados no FastAPI
- [ ] Topic definitions migradas para `KafkaTopicsConfig`
- [ ] Produtores atualizados com topicos padrao
- [ ] Consumidores atualizados com topicos padrao
- [ ] Chaves de particao adicionadas aos produtores
- [ ] Event envelopes implementados
- [ ] Topicos criados no startup
- [ ] Configuracao Kubernetes atualizada
- [ ] Testes atualizados
- [ ] Documentacao atualizada

## Rollback

Se algo der errado, reverter para versao anterior:

```bash
git revert <commit-hash>
kubectl rollout undo deployment/meu-servico
```

## Suporte

Para duvidas ou problemas:
- Consultar `HEALTH_CHECK_STANDARD.md`
- Consultar `KAFKA_TOPICS_STANDARD.md`
- Abrir issue no repositorio
