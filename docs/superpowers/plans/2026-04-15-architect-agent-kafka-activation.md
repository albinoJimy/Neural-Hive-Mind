# Architect Agent - Kafka Consumer Activation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ativar o consumidor Kafka já implementado no Architect Agent no lifespan da aplicação.

**Architecture:** O CognitivePlanConsumer já existe e está implementado. Apenas precisa ser inicializado no lifecycle da aplicação usando o ConsumerManager existente.

**Tech Stack:** Python 3.12+, aiokafka 0.9.0+, FastAPI, asyncio

---

## Task 1: Verificar dependência aiokafka

**Files:**
- Check: `services/architect-agent/requirements.txt`

- [ ] **Step 1: Verificar se aiokafka está nas dependências**

Run: `grep aiokafka services/architect-agent/requirements.txt`
Expected: aiokafka>=0.9.0

- [ ] **Step 2: Se não existir, adicionar**

```bash
echo "aiokafka>=0.9.0" >> services/architect-agent/requirements.txt
```

- [ ] **Step 3: Commit (se modificou)**

```bash
git add services/architect-agent/requirements.txt
git commit -m "deps(architect): ensure aiokafka is installed"
```

---

## Task 2: Adicionar flag de configuração para habilitar consumer

**Files:**
- Modify: `services/architect-agent/src/config/settings.py`

- [ ] **Step 1: Ler settings atual**

Run: `head -50 services/architect-agent/src/config/settings.py`

- [ ] **Step 2: Adicionar flag de enable**

Adicionar à classe KafkaSettings:

```python
kafka_consumer_enabled: bool = Field(
    default=False,
    description="Enable Kafka consumer for cognitive plans"
)
```

- [ ] **Step 3: Verificar que compila**

Run: `cd services/architect-agent && python -c "from src.config.settings import get_settings; print(get_settings().kafka.bootstrap_servers)"`
Expected: No errors, prints kafka bootstrap servers

- [ ] **Step 4: Commit**

```bash
git add services/architect-agent/src/config/settings.py
git commit -m "feat(architect): add kafka_consumer_enabled flag"
```

---

## Task 3: Atualizar main.py para iniciar consumer

**Files:**
- Modify: `services/architect-agent/src/main.py`

- [ ] **Step 1: Ler main.py atual**

Run: `cat services/architect-agent/src/main.py`

- [ ] **Step 2: Reescrever função main com consumer activation**

Substituir o conteúdo de `main()` por:

```python
async def main():
    """Main entry point"""
    settings = get_settings()

    # Configure logging
    configure_logging()

    # Get FastAPI app
    app = create_app()

    # Initialize metrics
    init_metrics(app)

    # Set up signal handlers
    shutdown_event = asyncio.Event()

    def handle_signal(signum, frame):
        logger.info("shutdown_signal_received", signal=signum)
        shutdown_event.set()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    logger.info(
        "starting_architect_agent",
        service=settings.service.service_name,
        version=settings.service.version,
        environment=settings.service.environment,
    )

    # Initialize Kafka Consumer (if enabled)
    consumer_manager = None
    consumer_task = None

    if settings.kafka.kafka_consumer_enabled:
        from src.consumers.lifecycle import ConsumerManager
        from src.consumers.cognitive_plan_consumer import CognitivePlanConsumer

        consumer_manager = ConsumerManager()
        cognitive_plan_consumer = CognitivePlanConsumer()
        consumer_manager.register(cognitive_plan_consumer)

        # Start consumer in background
        consumer_task = asyncio.create_task(consumer_manager.start_all())

        logger.info("kafka_consumer_started")

    # Start HTTP server
    config = uvicorn.Config(
        app, host="0.0.0.0", port=settings.service.http_port, log_config=None, access_log=False
    )

    server = uvicorn.Server(config)

    # Run server with shutdown handling
    try:
        await server.serve()
    except KeyboardInterrupt:
        logger.info("keyboard_interrupt_received")
    finally:
        # Stop consumers
        if consumer_manager:
            await consumer_manager.stop_all()

        if consumer_task:
            consumer_task.cancel()
            try:
                await consumer_task
            except asyncio.CancelledError:
                pass

        logger.info("architect_agent_shutdown_complete")
```

- [ ] **Step 3: Verificar que o código compila**

Run: `cd services/architect-agent && python -c "from src.main import main; print('Main loaded successfully')"`
Expected: Main loaded successfully

- [ ] **Step 4: Commit**

```bash
git add services/architect-agent/src/main.py
git commit -m "feat(architect): activate kafka consumer in main lifecycle"
```

---

## Task 4: Adicionar métricas para o consumer

**Files:**
- Modify: `services/architect-agent/src/observability/metrics.py`

- [ ] **Step 1: Ler métricas existentes**

Run: `cat services/architect-agent/src/observability/metrics.py`

- [ ] **Step 2: Adicionar métricas do consumer**

```python
from prometheus_client import Counter, Histogram

# Kafka Consumer Metrics
kafka_consumer_messages_total = Counter(
    "architect_agent_kafka_consumer_messages_total",
    "Total de mensagens consumidas do Kafka",
    ["topic", "status"]
)

kafka_consumer_processing_duration = Histogram(
    "architect_agent_kafka_consumer_processing_duration_seconds",
    "Duração do processamento de mensagens Kafka",
    ["topic"]
)
```

- [ ] **Step 3: Atualizar CognitivePlanConsumer para emitir métricas**

No ficheiro `src/consumers/cognitive_plan_consumer.py`, adicionar imports no topo:

```python
from src.observability.metrics import (
    kafka_consumer_messages_total,
    kafka_consumer_processing_duration
)
```

E atualizar `process_message`:

```python
async def process_message(self, message: dict) -> None:
    import time
    start_time = time.time()
    topic = message.get("topic", "unknown")

    try:
        # ... existing processing code ...

        kafka_consumer_messages_total.labels(topic=topic, status="success").inc()

    except Exception as e:
        logger.error("cognitive_plan_processing_error", error=str(e))
        kafka_consumer_messages_total.labels(topic=topic, status="error").inc()
        raise
    finally:
        duration = time.time() - start_time
        kafka_consumer_processing_duration.labels(topic=topic).observe(duration)
```

- [ ] **Step 4: Commit**

```bash
git add services/architect-agent/src/observability/metrics.py
git add services/architect-agent/src/consumers/cognitive_plan_consumer.py
git commit -m "feat(architect): add prometheus metrics for kafka consumer"
```

---

## Task 5: Atualizar testes existentes

**Files:**
- Modify: `services/architect-agent/tests/unit/test_consumers.py`

- [ ] **Step 1: Verificar testes existentes**

Run: `cd services/architect-agent && pytest tests/unit/test_consumers.py -v`

- [ ] **Step 2: Adicionar teste para métricas**

```python
def test_consumer_emits_metrics(consumer, mocker):
    """Testa que o consumer emite métricas Prometheus."""
    from src.observability.metrics import kafka_consumer_messages_total

    # Mock do processamento
    mocker.patch.object(consumer, "planner")
    mocker.patch.object(consumer, "repository")

    message = {
        "key": b"plan-123",
        "value": '{"plan_id": "plan-123", "intent": "Create microservice architecture"}',
        "topic": "cognitive.plans.created"
    }

    await consumer.process_message(message)

    # Verificar que métrica foi incrementada
    assert kafka_consumer_messages_total.labels(topic="cognitive.plans.created", status="success")._value.get() >= 1
```

- [ ] **Step 3: Commit**

```bash
git add services/architect-agent/tests/unit/test_consumers.py
git commit -m "test(architect): add metrics emission test"
```

---

## Task 6: Documentação de deploy

**Files:**
- Create: `services/architect-agent/docs/KAFKA_CONSUMER_ACTIVATION.md`

- [ ] **Step 1: Criar documentação**

```markdown
# Kafka Consumer Activation - Architect Agent

## Overview

O Architect Agent possui um consumidor Kafka implementado para processar `cognitive.plans.created`. Para ativar, configure a flag `kafka_consumer_enabled`.

## Configuração

No ConfigMap ou Secrets:

```yaml
kafka:
  kafka_consumer_enabled: true
  bootstrap_servers: "kafka.kafka.svc.cluster.local:9092"
  cognitive_plans_topic: "cognitive.plans.created"
  consumer_group: "architect-agent-consumers"
```

## Deploy

1. Set `kafka.kafka_consumer_enabled: true` nas configurações
2. Deploy do serviço
3. Verificar logs: "kafka_consumer_started"
4. Verificar métricas em `/metrics`

## Métricas

- `architect_agent_kafka_consumer_messages_total{topic, status}`
- `architect_agent_kafka_consumer_processing_duration_seconds{topic}`
```

- [ ] **Step 2: Commit**

```bash
git add services/architect-agent/docs/KAFKA_CONSUMER_ACTIVATION.md
git commit -m "docs(architect): add kafka consumer activation documentation"
```

---

## Task 7: Executar todos os testes

**Files:**
- All test files

- [ ] **Step 1: Run unit tests**

Run: `cd services/architect-agent && pytest tests/unit/ -v`
Expected: All tests pass

- [ ] **Step 2: Run integration tests (se disponível)**

Run: `cd services/architect-agent && pytest tests/integration/ -v`
Expected: All tests pass

- [ ] **Step 3: Run linting**

Run: `cd services/architect-agent && ruff check src/`
Expected: No errors

- [ ] **Step 4: Commit final**

```bash
git add .
git commit -m "feat(architect): complete kafka consumer activation - all tests passing"
```

---

## Self-Review Checklist

- [x] Spec coverage: Consumer ativado no lifespan
- [x] Placeholder scan: Sem "TBD", "TODO"
- [x] Type consistency: Nomes consistentes
- [x] Dependencies: aiokafka verificado
- [x] Configuration: Flag de enable adicionada
- [x] Tests: Testes atualizados
- [x] Metrics: Métricas Prometheus adicionadas
- [x] Documentation: Documento de deploy criado
