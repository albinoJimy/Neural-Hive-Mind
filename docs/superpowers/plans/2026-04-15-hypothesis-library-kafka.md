# Hypothesis Library - Kafka Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrar a Hypothesis Library para consumir eventos `hypotheses.created` e persistir hipóteses automaticamente.

**Architecture:** Consumer Kafka assíncrono que consome eventos de hipóteses criadas, persiste no MongoDB usando HypothesisService existente, e versiona automaticamente.

**Tech Stack:** Python 3.12+, aiokafka 0.9.0+, FastAPI, MongoDB, Prometheus

---

## Task 1: Adicionar dependência aiokafka

**Files:**
- Modify: `services/hypothesis-library/requirements.txt`

- [ ] **Step 1: Adicionar aiokafka**

```bash
echo "aiokafka>=0.9.0" >> services/hypothesis-library/requirements.txt
```

- [ ] **Step 2: Commit**

```bash
git add services/hypothesis-library/requirements.txt
git commit -m "deps(hypothesis): add aiokafka for kafka integration"
```

---

## Task 2: Adicionar configurações Kafka

**Files:**
- Modify: `services/hypothesis-library/src/config/settings.py`

- [ ] **Step 1: Adicionar campos Kafka**

```python
# Kafka Configuration
kafka_bootstrap_servers: str = Field(default="kafka.kafka.svc.cluster.local:9092")
kafka_hypotheses_topic: str = Field(default="hypotheses.created")
kafka_consumer_group: str = Field(default="hypothesis-library-consumers")
kafka_consumer_enabled: bool = Field(default=False)
```

- [ ] **Step 2: Commit**

```bash
git add services/hypothesis-library/src/config/settings.py
git commit -m "feat(hypothesis): add kafka configuration"
```

---

## Task 3: Criar estrutura consumers

**Files:**
- Create: `services/hypothesis-library/src/consumers/__init__.py`
- Create: `services/hypothesis-library/src/consumers/base.py`
- Create: `services/hypothesis-library/src/consumers/hypothesis_consumer.py`

- [ ] **Step 1: Criar base consumer**

Criar `src/consumers/base.py`:
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
                        await self.process_message({"key": msg.key, "value": msg.value})
                    except Exception as e:
                        logger.error("kafka_message_error", error=str(e))
        finally:
            await consumer.stop()

    async def stop(self) -> None:
        self._running = False
```

- [ ] **Step 2: Criar hypothesis consumer**

Criar `src/consumers/hypothesis_consumer.py`:
```python
import json
import structlog
from src.consumers.base import BaseKafkaConsumer
from src.models.hypothesis import Hypothesis, HypothesisStatus
from src.services.hypothesis_service import HypothesisService

logger = structlog.get_logger(__name__)

class HypothesisCreatedConsumer(BaseKafkaConsumer):
    def __init__(self, hypothesis_service: HypothesisService):
        super().__init__()
        self.hypothesis_service = hypothesis_service

    def get_topic(self) -> str:
        from src.config.settings import get_settings
        return get_settings().kafka_hypotheses_topic

    async def process_message(self, message: dict) -> None:
        try:
            value = json.loads(message.get("value", "{}"))
            hypothesis_id = value.get("hypothesis_id", "")
            title = value.get("title", "")
            description = value.get("description", "")
            category = value.get("category", "general")

            logger.info("hypothesis_received", hypothesis_id=hypothesis_id, title=title)

            # Create hypothesis using existing service
            hypothesis = Hypothesis(
                hypothesis_id=hypothesis_id,
                title=title,
                description=description,
                category=category,
                status=HypothesisStatus.PROPOSED
            )

            await self.hypothesis_service.create_hypothesis(hypothesis)
            logger.info("hypothesis_saved", hypothesis_id=hypothesis_id)

        except json.JSONDecodeError as e:
            logger.error("invalid_json", error=str(e))
        except Exception as e:
            logger.error("processing_error", error=str(e))
```

- [ ] **Step 3: Commit**

```bash
git add services/hypothesis-library/src/consumers/
git commit -m "feat(hypothesis): create kafka consumers"
```

---

## Task 4: Atualizar main.py

**Files:**
- Modify: `services/hypothesis-library/main.py`

- [ ] **Step 1: Atualizar startup**

No `@app.on_event("startup")`, após inicializar `hypothesis_service`:

```python
# Initialize Kafka Consumer (if enabled)
consumer_task = None
if settings.kafka_consumer_enabled:
    from src.consumers.hypothesis_consumer import HypothesisCreatedConsumer

    consumer = HypothesisCreatedConsumer(hypothesis_service=hypothesis_service)
    consumer_task = asyncio.create_task(consumer.start())
    logger.info("kafka_consumer_started")
```

- [ ] **Step 2: Atualizar shutdown**

No `@app.on_event("shutdown")`:

```python
if consumer_task:
    consumer_task.cancel()
```

- [ ] **Step 3: Commit**

```bash
git add services/hypothesis-library/main.py
git commit -m "feat(hypothesis): integrate kafka consumer in lifecycle"
```

---

## Task 5: Testes

**Files:**
- Create: `services/hypothesis-library/tests/unit/test_consumers.py`

- [ ] **Step 1: Criar testes**

```python
import pytest
from src.consumers.hypothesis_consumer import HypothesisCreatedConsumer
from src.services.hypothesis_service import HypothesisService

@pytest.fixture
def consumer(mock_service):
    return HypothesisCreatedConsumer(hypothesis_service=mock_service)

def test_consumer_get_topic(consumer):
    assert consumer.get_topic() == "hypotheses.created"

def test_process_message(consumer, mocker):
    message = {"value": '{"hypothesis_id": "hyp-123", "title": "Test", "description": "Test desc"}'}
    await consumer.process_message(message)
```

- [ ] **Step 2: Commit**

```bash
git add services/hypothesis-library/tests/unit/test_consumers.py
git commit -m "test(hypothesis): add consumer tests"
```

---

## Task 6: Documentação

**Files:**
- Create: `services/hypothesis-library/docs/KAFKA_INTEGRATION.md`

- [ ] **Step 1: Criar docs**

```markdown
# Kafka Integration - Hypothesis Library

## Configuração
```yaml
kafka_consumer_enabled: true
kafka_hypotheses_topic: "hypotheses.created"
```
```

- [ ] **Step 2: Commit**

```bash
git add services/hypothesis-library/docs/KAFKA_INTEGRATION.md
git commit -m "docs(hypothesis): add kafka integration docs"
```

---

## Self-Review Checklist

- [x] Consumer implementado
- [x] Service integration
- [x] Lifecycle management
- [x] Testes criados
- [x] Documentação
