# GAP-04: Cobertura de Testes 16% → 70%

**Status:** 🟡 Planejado
**Prioridade:** P2 - MÉDIA (Qualidade)
**Esforço Estimado:** 11 semanas (440 horas)
**Responsável:** QA Team + Backend Team

---

## Problema

Cobertura de testes atual: **16.19%** (795/4,910 linhas)
Meta recomendada: **70%**

### Áreas Críticas Sem Cobertura

| Área | Arquivos | Cobertura | Gap |
|------|----------|-----------|-----|
| Security/Auth | 8 | ~5% | JWT, RBAC, SPIFFE |
| Kafka Consumers/Producers | 12 | ~10% | DLQ, error handling |
| gRPC Services | 10 | ~15% | Timeout, streaming |
| ML Models | 15 | ~20% | Inference, drift |
| Temporal Workflows | 8 | ~25% | Activities, Saga |

---

## Priorização de Módulos

### P0 - CRÍTICO (4 semanas, 150 horas)

| Módulo | Arquivos | Horas | Impacto |
|--------|----------|-------|---------|
| Security/Auth | 8 | 40 | Segurança, Compliance |
| Kafka Core | 12 | 60 | Confiabilidade |
| gRPC Core | 10 | 50 | Comunicação |

### P1 - ALTA (5 semanas, 190 horas)

| Módulo | Arquivos | Horas | Impacto |
|--------|----------|-------|---------|
| ML Models | 15 | 80 | Predictions |
| Temporal Workflows | 8 | 60 | Orquestração |
| Specialists Logic | 10 | 50 | Negócio |

### P2 - MÉDIA (2.5 semanas, 100 horas)

| Módulo | Arquivos | Horas | Impacto |
|--------|----------|-------|---------|
| Integração secundária | 20 | 70 | Auxiliares |
| Monitoring/Metrics | 8 | 30 | Observabilidade |

---

## Planos por Área

### a) Security/Auth

#### JWT Validation Tests

```python
# libraries/security/tests/test_jwt_validation.py

import pytest
from datetime import datetime, timedelta
from neural_hive_security.spiffe_manager import SPIFFEManager, JWTSVID

class TestJWTValidation:
    """Testes de validacao JWT via SPIFFE"""

    @pytest.mark.asyncio
    async def test_validate_jwt_svid_success(self):
        """Teste de validacao de JWT-SVID valido"""
        config = Mock()
        config.workload_api_socket = "/tmp/spire-agent.sock"

        manager = SPIFFEManager(config)
        svid = await manager.fetch_jwt_svid(audience=["neural-hive"])

        assert isinstance(svid, JWTSVID)
        assert svid.spiffe_id.startswith("spiffe://")
        assert svid.expiry > datetime.now()

    @pytest.mark.asyncio
    async def test_validate_jwt_expired(self):
        """Teste de rejeicao de JWT expirado"""
        pass

    @pytest.mark.asyncio
    async def test_validate_jwt_malformed(self):
        """Teste de rejeicao de JWT malformado"""
        pass
```

#### RBAC Tests

```python
# services/gateway-intencoes/tests/unit/test_rbac_enforcement.py

class TestRBACEnforcement:
    """Testes de enforcement de roles RBAC"""

    @pytest.mark.asyncio
    async def test_admin_role_access(self):
        """Teste de acesso com role admin"""
        pass

    @pytest.mark.asyncio
    async def test_user_role_restricted_access(self):
        """Teste de acesso restrito com role user"""
        pass

    @pytest.mark.asyncio
    async def test_missing_role_denied(self):
        """Teste de negacao quando role ausente"""
        pass
```

### b) Kafka Consumers/Producers

#### Message Processing Tests

```python
# services/consensus-engine/tests/test_plan_consumer_full.py

class TestPlanConsumerMessageProcessing:
    """Testes de processamento de mensagens Kafka"""

    @pytest.mark.asyncio
    async def test_consume_valid_cognitive_plan(self):
        """Teste de consumo de plano valido"""
        message = Mock()
        message.value.return_value = json.dumps({
            "plan_id": "test-123",
            "intent_id": "intent-123",
            "tasks": []
        }).encode()

        await consumer._process_message(message)
        consumer.orchestrator.process_plan.assert_called_once()

    @pytest.mark.asyncio
    async def test_consume_invalid_schema(self):
        """Teste de rejeicao de schema invalido"""
        pass

    @pytest.mark.asyncio
    async def test_consume_duplicate_plan_id(self):
        """Teste de deteccao de duplicata"""
        pass
```

### c) gRPC Services

```python
# tests/integration/test_grpc_services_comprehensive.py

class TestGRPCTimeoutHandling:
    """Testes de timeout em chamadas gRPC"""

    @pytest.mark.asyncio
    async def test_client_timeout_on_long_operation(self):
        """Teste de timeout do cliente"""
        pass

    @pytest.mark.asyncio
    async def test_server_respects_deadline(self):
        """Teste de servidor respeitando deadline"""
        pass

    @pytest.mark.asyncio
    async def test_retry_with_backoff(self):
        """Teste de retry com backoff"""
        pass
```

### d) ML Models

```python
# libraries/python/neural_hive_ml/tests/test_inference_comprehensive.py

class TestLoadPredictorInference:
    """Testes de inference do LoadPredictor"""

    @pytest.mark.asyncio
    async def test_predict_load_with_valid_features(self):
        """Teste de predicao com features validas"""
        predictor = LoadPredictor(model_path="test_model.pkl")
        features = {
            "current_load": 0.7,
            "task_complexity": 0.5,
            "resource_availability": 0.8
        }

        prediction = await predictor.predict(features)

        assert 0 <= prediction.predicted_load <= 1
        assert prediction.confidence >= 0

    @pytest.mark.asyncio
    async def test_predict_with_missing_features(self):
        """Teste de predicao com features faltantes"""
        pass
```

### e) Temporal Workflows

```python
# services/orchestrator-dynamic/tests/activities/test_all_activities.py

class TestTicketGenerationActivity:
    """Testes da atividade de geracao de tickets"""

    @pytest.mark.asyncio
    async def test_generate_execution_tickets_success(self, temporal_env):
        """Teste de geracao com sucesso"""
        pass

    @pytest.mark.asyncio
    async def test_generate_tickets_with_invalid_plan(self, temporal_env):
        """Teste de geracao com plano invalido"""
        pass

    @pytest.mark.asyncio
    async def test_publish_to_kafka_timeout(self, temporal_env):
        """Teste de timeout ao publicar"""
        pass
```

---

## Infraestrutura de Testes

### pytest.ini Global

```ini
[pytest]
asyncio_mode = auto
testpaths =
    tests
    libraries/python/neural_hive_specialists/tests
    libraries/python/neural_hive_ml/tests
    libraries/security/tests
    services/*/tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts =
    -v
    --tb=short
    --cov=libraries/python/neural_hive_specialists
    --cov=libraries/python/neural_hive_ml
    --cov=libraries/security
    --cov=services
    --cov-report=html
    --cov-report=xml
    --cov-report=term-missing
    --cov-fail-under=70
filterwarnings =
    ignore::DeprecationWarning
markers =
    unit: mark test as unit
    integration: mark test as integration
    e2e: mark test as e2e
    security: mark test as security-related
    slow: mark test as slow
```

### Fixtures Compartilhadas

```python
# tests/fixtures/common.py

import pytest
from unittest.mock import Mock, AsyncMock

@pytest.fixture
def mock_settings():
    """Settings mock padrao"""
    settings = Mock()
    settings.kafka_bootstrap_servers = "localhost:9092"
    settings.mongodb_uri = "mongodb://localhost:27017"
    settings.redis_url = "redis://localhost:6379"
    return settings

@pytest.fixture
async def mock_kafka_producer():
    """Producer Kafka mock"""
    producer = AsyncMock()
    producer.produce = AsyncMock()
    producer.flush = AsyncMock()
    return producer

@pytest.fixture
def sample_cognitive_plan():
    """Plano cognitivo de teste"""
    return {
        "plan_id": "test-plan-123",
        "intent_id": "intent-123",
        "tasks": [],
        "risk_band": "medium"
    }
```

---

## CI/CD Integration

```yaml
# .github/workflows/test-coverage.yml

name: Test Coverage Report

on:
  pull_request:
    branches: [main, develop]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      kafka:
        image: confluentinc/cp-kafka:7.4.0
        ports:
          - 9092:9092
      mongodb:
        image: mongo:6.0
        ports:
          - 27017:27017

    steps:
    - uses: actions/checkout@v3
    - name: Run tests with coverage
      run: |
        pytest --cov=libraries/python/neural_hive_specialists \
               --cov=libraries/python/neural_hive_ml \
               --cov=libraries/security \
               --cov=services \
               --cov-report=xml \
               --cov-fail-under=70

    - name: Upload coverage to Codecov
      uses: codecov/codecov-action@v3
```

---

## Cronograma

```
Semana 1-2:  ████████████░░░░░░░░░░░░░░░  20% (Security/Auth)
Semana 3-4:  ███████████████████░░░░░░░░  35% (Kafka/gRPC)
Semana 5-7:  ████████████████████████░░░  50% (ML/Workflows)
Semana 8-10: ██████████████████████████░  65% (Specialists)
Semana 11-12:████████████████████████████  70% (Polimento)
```

---

## Recursos Necessários

| Role | FTE | Semanas | Horas |
|------|-----|---------|-------|
| Backend Engineer | 2 | 12 | 960h |
| ML Engineer | 1 | 8 | 320h |
| Security Engineer | 1 | 4 | 160h |
| QA Engineer | 1 | 12 | 480h |

---

## Critérios de Aceitação

### Por Área

**Security/Auth:**
- [ ] JWT validation com todos os cenários
- [ ] RBAC enforcement completo
- [ ] SPIFFE/mTLS com testes

**Kafka:**
- [ ] Consumer com Avro deserialization
- [ ] Producer com idempotence
- [ ] DLQ com enrichment

**gRPC:**
- [ ] Timeout handling
- [ ] Retry com backoff
- [ ] Stream processing

**ML:**
- [ ] Inference completo
- [ ] Feature engineering
- [ ] Drift detection

**Temporal:**
- [ ] Activities com retry
- [ ] Workflows completos
- [ ] Saga compensation

---

## Arquivos Críticos

| Ação | Arquivo |
|------|---------|
| **CRIAR** | `pytest.ini` (global) |
| **CRIAR** | `tests/fixtures/common.py` |
| **CRIAR** | `libraries/security/tests/test_jwt_validation.py` |
| **CRIAR** | `services/consensus-engine/tests/test_plan_consumer_full.py` |
| **CRIAR** | `services/orchestrator-dynamic/tests/activities/test_all_activities.py` |

---

**Documento baseado em análise do agente Plan (2026-03-29)**
