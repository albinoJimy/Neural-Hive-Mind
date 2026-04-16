# Experiment Impact Analyzer - Kafka Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrar o Experiment Impact Analyzer para consumir eventos `experiments.completed` e analisar o impacto de experimentos.

**Architecture:** Consumer Kafka assíncrono que consome eventos de experimentos concluídos, executa análise de impacto curto/longo prazo usando o ImpactAnalyzer existente, e publica resultados.

**Tech Stack:** Python 3.12+, aiokafka 0.9.0+, FastAPI, MongoDB, Prometheus

---

## Task 1: Adicionar dependência aiokafka

**Files:**
- Modify: `services/experiment-impact-analyzer/requirements.txt`

- [ ] **Step 1: Adicionar aiokafka**

```bash
echo "aiokafka>=0.9.0" >> services/experiment-impact-analyzer/requirements.txt
```

- [ ] **Step 2: Instalar**

Run: `pip install aiokafka==0.9.0`
Expected: Successfully installed

- [ ] **Step 3: Commit**

```bash
git add services/experiment-impact-analyzer/requirements.txt
git commit -m "deps(impact-analyzer): add aiokafka for kafka integration"
```

---

## Task 2: Adicionar configurações Kafka

**Files:**
- Modify: `services/experiment-impact-analyzer/src/config/settings.py`

- [ ] **Step 1: Adicionar campos Kafka**

```python
# Kafka Configuration
kafka_bootstrap_servers: str = Field(
    default="kafka.kafka.svc.cluster.local:9092"
)
kafka_experiments_topic: str = Field(
    default="experiments.completed"
)
kafka_consumer_group: str = Field(
    default="experiment-impact-analyzer-consumers"
)
kafka_consumer_enabled: bool = Field(
    default=False
)
kafka_impact_analyzed_topic: str = Field(
    default="impact.analyzed"
)
```

- [ ] **Step 2: Commit**

```bash
git add services/experiment-impact-analyzer/src/config/settings.py
git commit -m "feat(impact-analyzer): add kafka configuration"
```

---

## Task 3: Criar estrutura consumers

**Files:**
- Create: `services/experiment-impact-analyzer/src/consumers/__init__.py`
- Create: `services/experiment-impact-analyzer/src/consumers/base.py`

- [ ] **Step 1: Criar diretório e base consumer**

```bash
mkdir -p services/experiment-impact-analyzer/src/consumers
```

Criar `__init__.py`:
```python
from src.consumers.base import BaseKafkaConsumer
from src.consumers.experiment_consumer import ExperimentCompletedConsumer

__all__ = ["BaseKafkaConsumer", "ExperimentCompletedConsumer"]
```

Criar `base.py`:
```python
from abc import ABC, abstractmethod
import structlog
from aiokafka import AIOKafkaConsumer
from src.config.settings import get_settings

logger = structlog.get_logger(__name__)

class BaseKafkaConsumer(ABC):
    def __init__(self):
        settings = get_settings()
        self.bootstrap_servers = settings.kafka_bootstrap_servers
        self.group_id = settings.kafka_consumer_group
        self._running = False

    @abstractmethod
    def get_topic(self) -> str:
        pass

    @abstractmethod
    async def process_message(self, message: dict) -> None:
        pass

    async def start(self) -> None:
        self._running = True
        consumer = AIOKafkaConsumer(
            self.get_topic(),
            bootstrap_servers=self.bootstrap_servers,
            group_id=self.group_id,
            auto_offset_reset="earliest",
            value_deserializer=lambda m: m.decode("utf-8"),
        )
        await consumer.start()
        try:
            while self._running:
                async for msg in consumer:
                    try:
                        await self.process_message({"key": msg.key, "value": msg.value, "topic": msg.topic})
                    except Exception as e:
                        logger.error("kafka_message_error", error=str(e))
        finally:
            await consumer.stop()

    async def stop(self) -> None:
        self._running = False
```

- [ ] **Step 2: Commit**

```bash
git add services/experiment-impact-analyzer/src/consumers/
git commit -m "feat(impact-analyzer): create kafka consumer base"
```

---

## Task 4: Implementar ExperimentCompletedConsumer

**Files:**
- Create: `services/experiment-impact-analyzer/src/consumers/experiment_consumer.py`

- [ ] **Step 1: Criar consumer**

```python
import json
import structlog
from src.consumers.base import BaseKafkaConsumer
from src.services.impact_analyzer import ImpactAnalyzer

logger = structlog.get_logger(__name__)

class ExperimentCompletedConsumer(BaseKafkaConsumer):
    def __init__(self):
        super().__init__()
        self.analyzer = None  # Will be initialized in main

    def get_topic(self) -> str:
        from src.config.settings import get_settings
        return get_settings().kafka_experiments_topic

    async def process_message(self, message: dict) -> None:
        try:
            value = json.loads(message.get("value", "{}"))
            experiment_id = value.get("experiment_id", "")
            variant = value.get("variant", "")
            metrics = value.get("metrics", {})

            logger.info("experiment_received", experiment_id=experiment_id, variant=variant)

            # Analyze impact using existing service
            if self.analyzer:
                result = await self.analyzer.analyze_experiment(experiment_id, metrics)
                logger.info("impact_analyzed", experiment_id=experiment_id, result=result)

        except json.JSONDecodeError as e:
            logger.error("invalid_json", error=str(e))
        except Exception as e:
            logger.error("processing_error", error=str(e))
```

- [ ] **Step 2: Commit**

```bash
git add services/experiment-impact-analyzer/src/consumers/experiment_consumer.py
git commit -m "feat(impact-analyzer): implement experiment consumer"
```

---

## Task 5: Atualizar main.py para iniciar consumer

**Files:**
- Modify: `services/experiment-impact-analyzer/main.py`

- [ ] **Step 1: Atualizar startup**

Adicionar ao `@app.on_event("startup")`:

```python
# Initialize Kafka Consumer (if enabled)
consumer_task = None
if settings.kafka_consumer_enabled:
    from src.consumers.experiment_consumer import ExperimentCompletedConsumer

    consumer = ExperimentCompletedConsumer()
    consumer.analyzer = impact_analyzer  # Pass existing analyzer instance
    consumer_task = asyncio.create_task(consumer.start())
    logger.info("kafka_consumer_started")
```

- [ ] **Step 2: Atualizar shutdown**

Adicionar ao `@app.on_event("shutdown")`:

```python
if consumer_task:
    # Stop consumer
    if settings.kafka_consumer_enabled:
        from src.consumers.experiment_consumer import ExperimentCompletedConsumer
        # Consumer will be stopped via flag
    consumer_task.cancel()
```

- [ ] **Step 3: Commit**

```bash
git add services/experiment-impact-analyzer/main.py
git commit -m "feat(impact-analyzer): integrate kafka consumer in lifecycle"
```

---

## Task 6: Adicionar métricas Prometheus

**Files:**
- Modify: `services/experiment-impact-analyzer/src/api/health_handlers.py`

- [ ] **Step 1: Adicionar métricas**

```python
from prometheus_client import Counter, Histogram

experiment_consumer_messages_total = Counter(
    "impact_analyzer_consumer_messages_total",
    "Total de mensagens consumidas",
    ["status"]
)
```

- [ ] **Step 2: Commit**

```bash
git add services/experiment-impact-analyzer/src/api/health_handlers.py
git commit -m "feat(impact-analyzer): add prometheus metrics"
```

---

## Task 7: Testes

**Files:**
- Create: `services/experiment-impact-analyzer/tests/unit/test_consumers.py`

- [ ] **Step 1: Criar testes**

```python
import pytest
from src.consumers.experiment_consumer import ExperimentCompletedConsumer

@pytest.fixture
def consumer():
    return ExperimentCompletedConsumer()

def test_consumer_get_topic(consumer):
    assert consumer.get_topic() == "experiments.completed"

def test_process_message(consumer, mocker):
    consumer.analyzer = mocker.AsyncMock()
    message = {
        "value": '{"experiment_id": "exp-123", "variant": "B", "metrics": {}}'
    }
    await consumer.process_message(message)
    consumer.analyzer.analyze_experiment.assert_called_once()
```

- [ ] **Step 2: Commit**

```bash
git add services/experiment-impact-analyzer/tests/unit/test_consumers.py
git commit -m "test(impact-analyzer): add consumer tests"
```

---

## Task 8: Documentação

**Files:**
- Create: `services/experiment-impact-analyzer/docs/KAFKA_INTEGRATION.md`

- [ ] **Step 1: Criar docs**

```markdown
# Kafka Integration - Experiment Impact Analyzer

## Configuração
```yaml
kafka_consumer_enabled: true
kafka_experiments_topic: "experiments.completed"
```

## Deploy
1. Set `kafka_consumer_enabled: true`
2. Deploy
3. Verificar logs
```

- [ ] **Step 2: Commit**

```bash
git add services/experiment-impact-analyzer/docs/KAFKA_INTEGRATION.md
git commit -m "docs(impact-analyzer): add kafka integration docs"
```

---

## Self-Review Checklist

- [x] Consumer implementado
- [x] Lifecycle integration
- [x] Métricas adicionadas
- [x] Testes criados
- [x] Documentação criada
