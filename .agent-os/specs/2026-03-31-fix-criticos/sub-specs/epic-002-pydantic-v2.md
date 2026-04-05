# EPIC-002: Pydantic V2 Migration

**ID:** EPIC-002
**Status:** Pending
**Priority:** P1 - Alta
**Effort:** L (2 semanas)
**Related Services:** gateway-intencoes, semantic-translation-engine, memory-layer-api, execution-ticket-service, approval-service, worker-agents

---

## Resumo Executivo

Migrar 34 decorators `@validator` (Pydantic V1) para `@field_validator` e `@model_validator` (Pydantic V2) em 6 serviços. Todos os serviços já usam Pydantic V2.10.4, mas ainda utilizam sintaxe V1 depreciada.

---

## Análise Técnica

### Serviços Afetados

| Serviço | Arquivo | Count @validator | Severidade |
|--------|---------|------------------|------------|
| gateway-intencoes | src/config/settings.py | 8 | Alta |
| gateway-intencoes | src/models/intent_envelope.py | 4 | Alta |
| semantic-translation-engine | src/config/settings.py | 10 | Alta |
| semantic-translation-engine | src/models/cognitive_plan.py | 2 | Alta |
| execution-ticket-service | src/config/settings.py | 4 | Média |
| worker-agents | src/models/execution_ticket.py | 3 | Média |
| memory-layer-api | src/config/settings.py | 2 | Média |
| approval-service | src/api/routers/active_learning.py | 1 | Baixa |

### Padrões de Migração

#### Padrão 1: @validator → @field_validator

**ANTES (V1):**
```python
from pydantic import validator

@validator("field_name")
def validate_field(cls, v):
    if not valid_condition(v):
        raise ValueError('Invalid value')
    return v
```

**DEPOIS (V2):**
```python
from pydantic import field_validator

@field_validator("field_name")
@classmethod
def validate_field(cls, v):
    if not valid_condition(v):
        raise ValueError('Invalid value')
    return v
```

#### Padrão 2: @validator com pre=True → @field_validator com mode='before'

**ANTES (V1):**
```python
@validator("field_name", pre=True)
def parse_field(cls, v):
    if isinstance(v, str):
        return v.strip()
    return v
```

**DEPOIS (V2):**
```python
@field_validator("field_name", mode='before')
@classmethod
def parse_field(cls, v):
    if isinstance(v, str):
        return v.strip()
    return v
```

#### Padrão 3: @root_validator → @model_validator

**ANTES (V1):**
```python
from pydantic import root_validator

@root_validator(skip_on_failure=True)
def validate_consistency(cls, values):
    if values.get("a") > values.get("b"):
        raise ValueError("a must be <= b")
    return values
```

**DEPOIS (V2 - mode='after'):**
```python
from pydantic import model_validator

@model_validator(mode='after')
def validate_consistency(self):
    if self.a > self.b:
        raise ValueError("a must be <= b")
    return self
```

**DEPOIS (V2 - mode='before'):**
```python
@model_validator(mode='before')
@classmethod
def validate_consistency(cls, data):
    if data.get("a") > data.get("b"):
        raise ValueError("a must be <= b")
    return data
```

---

## Ticket EPIC-002-01: Migrate gateway-intencoes

**ID:** TICKET-EPIC-002-01
**Priority:** Alta
**Effort:** M (3 dias)
**Service:** gateway-intencoes

### Arquivos a Modificar

**1. src/config/settings.py (8 @validator)**

Linha 317 - Kafka security protocol:
```python
# ANTES
@validator("kafka_security_protocol")
def validate_kafka_security_protocol(cls, v):
    allowed = ["PLAINTEXT", "SASL_SSL", "SSL", "SASL_PLAINTEXT"]
    if v not in allowed:
        raise ValueError(f"kafka_security_protocol must be one of {allowed}")
    return v

# DEPOIS
@field_validator("kafka_security_protocol")
@classmethod
def validate_kafka_security_protocol(cls, v):
    allowed = ["PLAINTEXT", "SASL_SSL", "SSL", "SASL_PLAINTEXT"]
    if v not in allowed:
        raise ValueError(f"kafka_security_protocol must be one of {allowed}")
    return v
```

Linha 367 - Routing thresholds (com acesso a outros campos):
```python
# ANTES
@validator("nlu_routing_threshold_low")
def validate_routing_thresholds(cls, v, values):
    high_threshold = values.get("nlu_routing_threshold_high", 0.5)
    if v >= high_threshold:
        raise ValueError(
            f"nlu_routing_threshold_low ({v}) must be < nlu_routing_threshold_high ({high_threshold})"
        )
    return v

# DEPOIS (mode='before')
@model_validator(mode='before')
@classmethod
def validate_routing_thresholds(cls, data):
    high_threshold = data.get("nlu_routing_threshold_high", 0.5)
    low_threshold = data.get("nlu_routing_threshold_low")
    if low_threshold is not None and low_threshold >= high_threshold:
        raise ValueError(
            f"nlu_routing_threshold_low ({low_threshold}) must be < nlu_routing_threshold_high ({high_threshold})"
        )
    return data
```

Linha 376 - CORS origins (pre=True):
```python
# ANTES
@validator("cors_origins_override", pre=True)
def parse_cors_origins_override(cls, v):
    if v is None:
        return None
    if isinstance(v, str):
        return [origin.strip() for origin in v.split(",")]
    return v

# DEPOIS
@field_validator("cors_origins_override", mode='before')
@classmethod
def parse_cors_origins_override(cls, v):
    if v is None:
        return None
    if isinstance(v, str):
        return [origin.strip() for origin in v.split(",")]
    return v
```

**2. src/models/intent_envelope.py (4 @validator + 1 @root_validator)**

Linha 221 - Constraints consistency:
```python
# ANTES
@root_validator(skip_on_failure=True)
def validate_constraints_consistency(cls, values):
    constraints = values.get("constraints")
    qos = values.get("qos")
    if constraints and constraints.security_level == SecurityLevel.RESTRICTED:
        if not qos or qos.consistency != Consistency.STRONG:
            raise ValueError("RESTRICTED requires STRONG consistency")
    return values

# DEPOIS
@model_validator(mode='after')
def validate_constraints_consistency(self):
    if self.constraints and self.constraints.security_level == SecurityLevel.RESTRICTED:
        if not self.qos or self.qos.consistency != Consistency.STRONG:
            raise ValueError("RESTRICTED requires STRONG consistency")
    return self
```

### Critérios de Aceite
- [ ] Todos os @validator convertidos
- [ ] Imports atualizados
- [ ] Testes passando
- [ ] Zero warnings de deprecation

---

## Ticket EPIC-002-02: Migrate semantic-translation-engine

**ID:** TICKET-EPIC-002-02
**Priority:** Alta
**Effort:** M (3 dias)
**Service:** semantic-translation-engine

### Arquivos a Modificar

**1. src/config/settings.py (10 @validator)**

Seguir mesmo padrão de gateway-intencoes.

**2. src/models/cognitive_plan.py (2 @validator)**

Linha ~45 - Plan validation:
```python
# ANTES
@validator("tasks")
def validate_tasks(cls, v):
    if not v:
        raise ValueError("Plan must have at least one task")
    return v

# DEPOIS
@field_validator("tasks")
@classmethod
def validate_tasks(cls, v):
    if not v:
        raise ValueError("Plan must have at least one task")
    return v
```

### Critérios de Aceite
- [ ] Todos os @validator convertidos
- [ ] Testes NLP passando
- [ ] Zero warnings de deprecation

---

## Ticket EPIC-002-03: Migrate Serviços Secundários

**ID:** TICKET-EPIC-002-03
**Priority:** Média
**Effort:** M (4 dias)
**Services:** execution-ticket-service, worker-agents, memory-layer-api, approval-service

### Arquivos a Modificar

| Service | Arquivo | Count |
|---------|---------|-------|
| execution-ticket-service | src/config/settings.py | 4 |
| worker-agents | src/models/execution_ticket.py | 3 |
| memory-layer-api | src/config/settings.py | 2 |
| approval-service | src/api/routers/active_learning.py | 1 |

### Padrão Uniforme

Aplicar mesmas conversões dos tickets anteriores.

### Critérios de Aceite
- [ ] Todos os @validator convertidos
- [ ] Testes passando em todos os serviços
- [ ] Zero warnings de deprecation no CI/CD

---

## Resumo do Epic

| Ticket | Service | Effort | @validator Count |
|--------|---------|--------|------------------|
| EPIC-002-01 | gateway-intencoes | 3 dias | 12 |
| EPIC-002-02 | semantic-translation-engine | 3 dias | 12 |
| EPIC-002-03 | Secundários | 4 dias | 10 |
| **TOTAL** | | **10 dias** | **34** |

---

## Ordem de Execução

1. **Dia 1-3:** EPIC-002-01 (gateway-intencoes)
2. **Dia 4-6:** EPIC-002-02 (semantic-translation-engine)
3. **Dia 7-10:** EPIC-002-03 (secundários)

---

## Script de Validação

```bash
#!/bin/bash
# Validar migração Pydantic V2

echo "Verificando @validator remanescentes..."
grep -r "@validator" services/ --include="*.py" | grep -v "test" | grep -v "__pycache__"

echo "Verificando imports corretos..."
grep -r "from pydantic import.*field_validator" services/ --include="*.py"

echo "Executando testes..."
pytest services/gateway-intencoes/tests/ -v
pytest services/semantic-translation-engine/tests/ -v
pytest services/execution-ticket-service/tests/ -v
pytest services/worker-agents/tests/ -v
pytest services/memory-layer-api/tests/ -v
pytest services/approval-service/tests/ -v
```

---

## Handoff para Claude Code

Para executar este Epic, use:
```
@~/.agent-os/instructions/execute-tasks.md

Epic: EPIC-002 - Pydantic V2 Migration
Tickets: EPIC-002-01, EPIC-002-02, EPIC-002-03
```
