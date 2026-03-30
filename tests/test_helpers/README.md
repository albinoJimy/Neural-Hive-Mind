# Test Helpers Package

Package de helpers para testes do Neural Hive Mind.

## Estrutura

```
tests/test_helpers/
├── __init__.py      # Exportações públicas
├── factories.py     # Factories para criar dados de teste
├── asserts.py       # Assertions customizados
├── mocks.py         # Mocks reutilizáveis
└── README.md        # Este ficheiro
```

## Factories (`factories.py`)

Classes factory para criar dados de teste consistentes.

### TestCognitivePlanFactory

```python
from tests.test_helpers import TestCognitivePlanFactory

# Criar um plano básico
plan = TestCognitivePlanFactory.create(
    intent="Analisar dados de vendas",
    domain="TECHNICAL",
    risk_band="medium"
)

# Criar múltiplos planos
plans = TestCognitivePlanFactory.create_batch(count=5)
```

### TestSpecialistOpinionFactory

```python
from tests.test_helpers import TestSpecialistOpinionFactory

opinion = TestSpecialistOpinionFactory.create(
    plan_id="plan-123",
    confidence=0.85,
    recommendation=True
)

# Criar múltiplas opiniões
opinions = TestSpecialistOpinionFactory.create_batch(
    count=5,
    confidence_min=0.7,
    confidence_max=0.95
)
```

### TestConsolidatedDecisionFactory

```python
from tests.test_helpers import TestConsolidatedDecisionFactory

decision = TestConsolidatedDecisionFactory.create(
    plan_id="plan-123",
    final_decision=True,
    consensus_score=0.85
)
```

### TestExecutionTicketFactory

```python
from tests.test_helpers import TestExecutionTicketFactory

ticket = TestExecutionTicketFactory.create(
    plan_id="plan-123",
    task_type="query"
)

# Criar múltiplos tickets
tickets = TestExecutionTicketFactory.create_batch(count=5)
```

### TestSpecialistFeedbackFactory

```python
from tests.test_helpers import TestSpecialistFeedbackFactory

# Feedback simples
feedback = TestSpecialistFeedbackFactory.create(
    human_decision=True,
    confidence=0.8
)

# Criar batch com balanceamento controlado
feedbacks = TestSpecialistFeedbackFactory.create_batch(
    count=10,
    approve_ratio=0.7  # 70% approve, 30% reject
)
```

### Funções de Conveniência

```python
from tests.test_helpers import (
    create_test_plan,
    create_test_opinion,
    create_test_decision,
    create_test_ticket,
    create_test_feedback,
)

plan = create_test_plan(intent="Test intent")
opinion = create_test_opinion(plan_id="plan-123")
decision = create_test_decision(plan_id="plan-123")
ticket = create_test_ticket(plan_id="plan-123")
feedback = create_test_feedback(human_decision=True)
```

## Assertions (`asserts.py`)

Assertions customizados para validações específicas do domínio.

### Validações de ID

```python
from tests.test_helpers import (
    assert_valid_plan_id,
    assert_valid_ticket_id,
    assert_valid_opinion_id,
    assert_valid_specialist_id,
    assert_valid_workflow_id,
)

assert_valid_plan_id("plan-123")  # OK
assert_valid_plan_id("invalid")   # Raises AssertionError
```

### Validações de Valor

```python
from tests.test_helpers import (
    assert_valid_confidence,
    assert_valid_percentage,
    assert_valid_duration_ms,
)

assert_valid_confidence(0.85)  # OK (0.0 a 1.0)
assert_valid_confidence(1.5)   # Raises AssertionError

assert_valid_percentage(75.5)  # OK (0 a 100)
assert_valid_duration_ms(5000)  # OK
```

### Validações de Domínio

```python
from tests.test_helpers import (
    assert_valid_domain,
    assert_valid_risk_band,
    assert_valid_priority,
    assert_valid_status,
)

assert_valid_domain("TECHNICAL")  # OK
assert_valid_domain("INVALID")   # Raises AssertionError

assert_valid_risk_band("medium")  # OK
assert_valid_priority("high")     # OK
assert_valid_status("COMPLETED")  # OK
```

### Validações de Tasks

```python
from tests.test_helpers import (
    assert_tasks_dependent,
    assert_no_circular_dependencies,
)

task_a = {"task_id": "task-a", "dependencies": []}
task_b = {"task_id": "task-b", "dependencies": ["task-a"]}

assert_tasks_dependent(task_a, task_b)  # OK

tasks = [task_a, task_b]
assert_no_circular_dependencies(tasks)  # OK
```

### Validações de Decisões

```python
from tests.test_helpers import (
    assert_consolidated_decision,
    assert_specialist_opinion,
    assert_approve_reject_balance,
)

decision = {
    "decision_id": "decision-123",
    "plan_id": "plan-123",
    "final_decision": True,
    "consensus_score": 0.85,
    "approval_rate": 0.8,
}

assert_consolidated_decision(decision, expected_decision=True)
assert_approve_reject_balance(approve_count=4, reject_count=1)
```

### Validações de Estruturas

```python
from tests.test_helpers import (
    assert_cognitive_plan,
    assert_specialist_opinion,
    assert_feedback_structure,
    assert_feedback_semantic_features,
)

plan = TestCognitivePlanFactory.create()
assert_cognitive_plan(plan)

opinion = TestSpecialistOpinionFactory.create()
assert_specialist_opinion(opinion, expected_recommendation=True)

feedback = TestSpecialistFeedbackFactory.create()
assert_feedback_structure(feedback)
assert_feedback_semantic_features(feedback)
```

## Mocks (`mocks.py`)

Classes mock reutilizáveis para componentes externos.

### Kafka Mocks

```python
from tests.test_helpers import MockKafkaProducer, MockKafkaConsumer, MockKafkaMessage

# Producer mock
producer = MockKafkaProducer()
await producer.produce("test-topic", {"key": "value"})
await producer.flush()

messages = producer.get_messages()

# Consumer mock
msg = MockKafkaMessage(value={"test": "data"}, topic="test-topic")
consumer = MockKafkaConsumer(messages=[msg])

async for message in consumer:
    data = message.value
```

### Database Mocks

```python
from tests.test_helpers import MockMongoDBClient, MockMongoDBCollection, MockRedisClient

# MongoDB mock
mongo_client = MockMongoDBClient()
collection = mongo_client.get_collection("test_collection")

await collection.insert_one({"_id": "123", "data": "test"})
result = await collection.find_one({"_id": "123"})

# Redis mock
redis = MockRedisClient()
await redis.set("key", "value")
value = await redis.get("key")
```

### Temporal Mocks

```python
from tests.test_helpers import MockTemporalClient, MockTemporalWorkflowHandle

temporal = MockTemporalClient()
handle = await temporal.start_workflow(
    workflow=MyWorkflow,
    args=[arg1, arg2],
    id="workflow-123"
)

# Enviar sinal
await handle.signal("my-signal", {"data": "test"})
```

### HTTP Client Mock

```python
from tests.test_helpers import MockHTTPClient, MockHTTPResponse

http_client = MockHTTPClient()
http_client.set_response(
    MockHTTPResponse(status_code=200, json_data={"result": "ok"})
)

response = await http_client.get("http://api.example.com/test")
data = await response.json()
```

## Uso em Testes

### Exemplo Completo

```python
import pytest
from tests.test_helpers import (
    TestCognitivePlanFactory,
    TestSpecialistOpinionFactory,
    assert_valid_plan_id,
    assert_valid_confidence,
    assert_cognitive_plan,
    assert_specialist_opinion,
)

class TestMyFeature:
    def test_cognitive_plan_validation(self):
        """Testa validação de plano cognitivo."""
        plan = TestCognitivePlanFactory.create(
            intent="Test intent",
            domain="TECHNICAL"
        )

        # Validar estrutura
        assert_cognitive_plan(plan)

        # Validar campos específicos
        assert_valid_plan_id(plan["plan_id"])
        assert_valid_domain(plan["domain"])

    def test_specialist_opinion_creation(self):
        """Testa criação de opinião de especialista."""
        opinion = TestSpecialistOpinionFactory.create(
            plan_id="plan-123",
            confidence=0.85
        )

        # Validar estrutura
        assert_specialist_opinion(opinion)

        # Validar campos
        assert_valid_confidence(opinion["confidence"])
        assert opinion["recommendation"] is True
```

## Constantes Úteis

```python
# Domínios válidos
VALID_DOMAINS = {
    "TECHNICAL", "BUSINESS", "ARCHITECTURE",
    "BEHAVIOR", "EVOLUTION", "SECURITY"
}

# Bandas de risco válidas
VALID_RISK_BANDS = {"low", "medium", "high", "critical"}

# Prioridades válidas
VALID_PRIORITIES = {"low", "normal", "high", "critical"}

# Status válidos
VALID_STATUSES = {
    "PENDING", "IN_PROGRESS", "COMPLETED", "FAILED",
    "CANCELLED", "APPROVED", "REJECTED", "TIMEOUT"
}
```
