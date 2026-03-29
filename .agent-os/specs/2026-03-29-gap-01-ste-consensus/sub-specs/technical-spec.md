# Technical Specification

## Technical Requirements

### 1. Alteração de Configuração

**Arquivo:** `services/semantic-translation-engine/src/config/settings.py`

**Linha 51 - ANTES:**
```python
kafka_plans_topic: str = Field(default='cognitive-plans', description='Plans output topic')
```

**Linha 51 - DEPOIS:**
```python
kafka_plans_topic: str = Field(default='plans.ready', description='Plans output topic for Consensus Engine')
```

### 2. Atualização de Testes

**Arquivo:** `services/semantic-translation-engine/tests/conftest.py`

**Linha 127 - ANTES:**
```python
settings.kafka_plans_topic = 'cognitive-plans'
```

**Linha 127 - DEPOIS:**
```python
settings.kafka_plans_topic = 'plans.ready'
```

### 3. Validação de Infraestrutura

Verificar que Helm charts já estão configurados para `plans.ready`:

**Arquivo:** `helm-charts/semantic-translation-engine/values.yaml`
```yaml
kafka:
  plansTopic: "plans.ready"  # Já deve estar correto
```

**Arquivo:** `helm-charts/kafka-topics/values.yaml`
```yaml
plans-ready:
  name: "plans.ready"
  partitions: 6
  replication-factor: 3
```

### 4. Comandos de Validação

```bash
# Verificar configuração carregada
cd services/semantic-translation-engine
python -c "from src.config.settings import Settings; s=Settings(); print(s.kafka_plans_topic)"
# Output esperado: plans.ready

# Rodar testes
pytest tests/unit/ -v -m "not e2e"
pytest tests/integration/ -v

# Verificar não há mais referências ao tópico antigo
! grep -r "cognitive-plans" tests/ 2>/dev/null
```

## External Dependencies

Nenhuma nova dependência necessária. Mudança puramente de configuração.
