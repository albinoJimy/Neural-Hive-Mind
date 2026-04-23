# neural_hive_context

> **Version:** 1.0.0
> **Python:** 3.10+
> **Status:** Production Ready

Context Layer library for Neural Hive Mind - Provides rich context aggregation, workflow classification, and PII detection for intelligent routing decisions.

---

## Features

- **Multi-Signal Workflow Classification** - Classify intents between ORCHESTRATION and GENERATION workflows
- **PII Detection** - Detect 14 types of personally identifiable information (Brazilian + Angolan)
- **Context Management** - Aggregate intent, system, temporal, security, and conversational context
- **Active Learning** - Signal extraction for continuous learning
- **High Performance** - <50ms p95 (actual: 0.02-0.03ms)

---

## Installation

```bash
pip install git+https://github.com/albinojimy/Neural-Hive-Mind.git@main#subdirectory=libs/neural_hive_context
```

Or add to `requirements.txt`:

```
git+https://github.com/albinojimy/Neural-Hive-Mind.git@main#subdirectory=libs/neural_hive_context
```

---

## Quick Start

### Workflow Classification

```python
from neural_hive_context.services import MultiSignalWorkflowClassifier
from neural_hive_context.models import RichContext, IntentContext, SystemContext, TemporalContext, SecurityContext, ConversationContext

# Create classifier
classifier = MultiSignalWorkflowClassifier()

# Build context
context = RichContext(
    intent=IntentContext(
        raw_text="gere um relatório de vendas",
        intent_id="intent-001",
    ),
    system=SystemContext(
        affected_services=[],
        active_workflows=0,
    ),
    temporal=TemporalContext(
        current_time="2024-01-01T00:00:00Z",
        time_of_day="morning",
        day_of_week="Monday",
        is_business_hours=True,
    ),
    security=SecurityContext(),
    conversation=ConversationContext(),
    context_id="ctx-001",
    created_at="2024-01-01T00:00:00Z",
)

# Classify workflow
result = await classifier.classify(context)
print(f"Workflow: {result.workflow_type}")  # WorkflowType.GENERATION
print(f"Confidence: {result.confidence}")    # 0.85
print(f"Reasoning: {result.reasoning}")      # "Workflow de geração selecionado..."
```

### PII Detection (Brazilian)

```python
from neural_hive_context.services import RegexPIIDetector

detector = RegexPIIDetector()
result = detector.detect("Meu email é joao@exemplo.com e CPF 123.456.789-09")

if result.has_pii:
    for entity in result.entities:
        print(f"Type: {entity.type}")
        print(f"Value: {entity.masked_value}")
```

### PII Detection (Angolan)

```python
from neural_hive_context.services import AngolanPIIDetector

detector = AngolanPIIDetector()
result = detector.detect("NIF: 005123456, BI: 001234567891LA")

# Detects Angolan PII types
types = {e.type for e in result.entities}
```

### Context Manager

```python
from neural_hive_context.services import ContextManagerService, MultiSignalWorkflowClassifier

classifier = MultiSignalWorkflowClassifier()
context_manager = ContextManagerService(workflow_classifier=classifier)

# Create context and classify in one call
context, classification = await context_manager.create_and_classify(
    intent_text="gere um dashboard",
    intent_id="intent-001",
)

# Enrich Cognitive Plan with workflow fields
enriched_plan = await context_manager.enrich_cognitive_plan(
    cognitive_plan={"plan_id": "plan-001"},
    context=context,
    classification=classification,
)
```

---

## Supported PII Types

| Type | Description | Risk Level |
|------|-------------|------------|
| EMAIL | Email address | MEDIUM |
| PHONE | Phone number (BR + AO) | MEDIUM |
| CPF | Brazilian tax ID | HIGH |
| CNH | Brazilian driver's license | HIGH |
| CREDIT_CARD | Credit card number (Luhn validated) | CRITICAL |
| PASSPORT | Passport number | HIGH |
| SSN | US Social Security Number | CRITICAL |
| IP_ADDRESS | IP address | LOW |
| URL | HTTP/HTTPS URL | LOW |
| BANK_ACCOUNT | Bank account (BR format) | HIGH |
| ADDRESS | Street address | MEDIUM |
| **NIF** | Angolan tax ID | HIGH |
| **BI** | Angolan ID card | CRITICAL |
| **NUIT** | Angolan tax number | HIGH |

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CONTEXT_CACHE_ENABLED` | true | Enable LRU cache |
| `CONTEXT_CACHE_TTL_SECONDS` | 300 | Cache TTL in seconds |
| `CONTEXT_CACHE_MAX_SIZE` | 1000 | Max cache entries |
| `PII_DETECTOR_MIN_CONFIDENCE` | 0.7 | Min confidence for PII detection |
| `WORKFLOW_CLASSIFIER_THRESHOLD` | 0.45 | Threshold for workflow decision |

---

## Testing

```bash
# Run all tests
pytest tests/

# Run specific test suite
pytest tests/unit/services/test_workflow_classifier.py
pytest tests/unit/services/test_pii_detector.py
pytest tests/unit/services/test_angolan_pii_detector.py

# Run performance tests
pytest tests/performance/test_performance.py
```

---

## Performance

| Operation | Target | Actual | Status |
|-----------|--------|--------|--------|
| Workflow Classification | <20ms p95 | 0.02ms | ✅ 1000x |
| PII Detection | <15ms p95 | 0.03ms | ✅ 500x |
| Context Building | <50ms p95 | <0.05ms | ✅ 1000x |

---

## License

MIT

---

**neural_hive_context v1.0.0 - Context Layer Library for Neural Hive Mind**
