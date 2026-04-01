# Test Coverage Improvement Plan - Neural Hive-Mind

## Objetivo

Aumentar cobertura de testes de 40-50% para 70% mínimo para produção.

## Análise Atual

### Testes Existentes (1622+ testes coletados)

**Por tipo:**
- Unit tests: ~1200 (gateway, consensus, specialists)
- Integration tests: ~300 (E2E com Docker Compose)
- Contract tests: ~100 (gRPC)

**Por serviço:**

| Serviço | Testes Unitários | Cobertura Estimada | Status |
|---------|-----------------|-------------------|--------|
| gateway-intencoes | 50+ | 60% | ✅ |
| semantic-translation-engine | 80+ | 65% | ✅ |
| consensus-engine | 150+ | 70% | ✅ |
| orchestrator-dynamic | 100+ | 55% | ⚠️ |
| approval-service | 120+ | 60% | ⚠️ |
| worker-agents | 200+ | 50% | ⚠️ |
| specialist-business | 80+ | 65% | ✅ |
| specialist-technical | 80+ | 65% | ✅ |
| specialist-architecture | 60+ | 60% | ⚠️ |
| specialist-behavior | 60+ | 55% | ⚠️ |
| specialist-evolution | 60+ | 55% | ⚠️ |
| queen-agent | 100+ | 70% | ✅ |
| service-registry | 40+ | 50% | ⚠️ |

**Bibliotecas Python:**

| Biblioteca | Testes | Cobertura | Status |
|-----------|--------|-----------|--------|
| neural_hive_domain | 50+ | 80% | ✅ |
| neural_hive_specialists | 68+ | 75% | ✅ |
| neural_hive_agent_sdk | 32+ | 70% | ✅ |
| neural_hive_resilience | 123+ | 85% | ✅ |
| neural_hive_risk_scoring | 98+ | 80% | ✅ |
| neural_hive_observability | 40+ | 60% | ⚠️ |
| neural_hive_ml | 20+ | 40% | ❌ |

## Gaps Identificados

### 1. Integração Fluxo C (Orchestration)

**Cobertura atual:** 30%
**Gap:** Workflows Temporal, atividades, compensação

**Testes necessários:**
- [ ] Teste de criação de workflow com decisão aprovada
- [ ] Teste de criação de workflow com decisão rejeitada
- [ ] Teste de compensação quando activity falha
- [ ] Teste de SLA breach e auto-correct
- [ ] Teste de timeout em atividades
- [ ] Teste de retry com backoff exponencial

### 2. ML Pipelines

**Cobertura atual:** 20%
**Gap:** Treinamento, validação, feature engineering

**Testes necessários:**
- [ ] Teste de pipeline de treino completo
- [ ] Teste de validação de modelo
- [ ] Teste de feature extraction
- [ ] Teste de drift detection
- [ ] Teste de rollback de modelo

### 3. Multi-Language SDK

**Cobertura atual:** 40%
**Gap:** Go SDK (novo), Java SDK (pendente)

**Testes necessários:**
- [ ] Testes unitários Go SDK (AgentClient)
- [ ] Testes de integração Go SDK
- [ ] Mock do servidor gRPC para testes

### 4. Resilience Library

**Cobertura atual:** 85%
**Status:** BOM, mas falta coverage de edge cases

**Testes adicionais:**
- [ ] Teste de circuit breaker com half-open timeout
- [ ] Teste de retry com jitter customizado
- [ ] Teste de fallback chain múltipla

## Plano de Ação

### Fase 1: Serviços Críticos (Week 1-2)

**Prioridade Alta:** Serviços que processam tráfego de usuário

1. **gateway-intencoes** (atual 60% → 80%)
   - [ ] Testes de rate limiting distribuído
   - [ ] Testes de cache invalidation
   - [ ] Testes de circuit breaker NLU
   - [ ] Testes de fallback specialist

2. **consensus-engine** (atual 70% → 85%)
   - [ ] Testes de deadlock detection
   - [ ] Testes de consensus com quorum customizado
   - [ ] Testes de hierarchical weights edge cases
   - [ ] Testes de timeout voting

3. **orchestrator-dynamic** (atual 55% → 75%)
   - [ ] Testes de workflow state machine
   - [ ] Testes de activity retry policies
   - [ ] Testes de saga compensation
   - [ ] Testes de SLA monitoring

### Fase 2: Especialistas (Week 3-4)

1. **specialist-architecture** (atual 60% → 75%)
   - [ ] Testes de SOLID principles validation
   - [ ] Testes de design pattern detection
   - [ ] Testes de architectural decision recording

2. **specialist-behavior** (atual 55% → 70%)
   - [ ] Testes de accessibility validation
   - [ ] Testes de usability heuristics
   - [ ] Testes de A/B testing framework

3. **specialist-evolution** (atual 55% → 70%)
   - [ ] Testes de maintainability metrics
   - [ ] Testes de technical debt tracking
   - [ ] Testes de refactoring suggestions

### Fase 3: Infraestrutura (Week 5-6)

1. **worker-agents** (atual 50% → 70%)
   - [ ] Testes de executor selection
   - [ ] Testes de task queue management
   - [ ] Testes de worker lifecycle

2. **service-registry** (atual 50% → 70%)
   - [ ] Testes de service discovery
   - [ ] Testes de health check aggregation
   - [ ] Testes de registry persistence

### Fase 4: ML e Observabilidade (Week 7-8)

1. **neural_hive_ml** (atual 40% → 70%)
   - [ ] Testes de model training pipeline
   - [ ] Testes de feature engineering
   - [ ] Testes de model validation
   - [ ] Testes de prediction serving

2. **neural_hive_observability** (atual 60% → 80%)
   - [ ] Testes de tracing context propagation
   - [ ] Testes de metrics aggregation
   - [ ] Testes of log sampling strategies

## Estratégia de Testes

### Test Pyramid

```
        /\
       /  \      E2E Tests (10%)
      /____\     - Fluxos completos críticos
     /      \    - 2-3 testes por fluxo principal
    /        \
   /  Unit     \  Unit Tests (70%)
  /____________\ - Funções individuais
                - Classes
                - Módulos
                - Mock de dependências externas
```

### Cobertura por Tipo

| Tipo | % Total | Critério de Sucesso |
|------|---------|---------------------|
| Unitários | 70% | > 80% cobertura |
| Integração | 20% | > 60% cobertura |
| E2E | 10% | Fluxos principais cobertos |

### Tools

- **pytest**: Test runner
- **pytest-cov**: Cobertura de código
- **pytest-asyncio**: Testes async
- **pytest-mock**: Mock de dependências
- **pytest-aiohttp**: Testes de APIs HTTP
- **pytest-grpc**: Testes de serviços gRPC

## CI/CD Gate

### Configuração GitHub Actions

```yaml
# .github/workflows/test-coverage.yml
name: Test Coverage Check

on:
  pull_request:
  push:
    branches: [main, develop]

jobs:
  coverage:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run tests with coverage
        run: |
          pytest --cov=services --cov=libraries \
                 --cov-report=xml \
                 --cov-report=term-missing \
                 --cov-fail-under=70
      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

### Critérios de Aceite

- ✅ Cobertura mínima: 70%
- ✅ Nenhum teste novo sem mock de dependências externas
- ✅ Todo bug fix deve incluir teste de regressão
- ✅ Toda feature nova deve ter > 80% cobertura

## Métricas de Sucesso

### Objetivos Quantitativos

| Métrica | Atual | Alvo | Deadline |
|---------|-------|------|----------|
| Cobertura global | 45% | 70% | Week 8 |
| Serviços com >70% | 4/15 | 15/15 | Week 8 |
| Bibliotecas com >70% | 4/7 | 7/7 | Week 6 |
| Testes E2E automatizados | 20 | 50 | Week 8 |

### Objetivos Qualitativos

- Testes rápidos (< 5 min para suite completa)
- Testes determinísticos (sem flaky tests)
- Testes legíveis e mantíveis
- Documentação de testes complexos

## Templates de Testes

### Template Teste Unitário

```python
import pytest
from unittest.mock import Mock, patch
from mymodule import MyClass

class TestMyClass:
    """Testes para MyClass"""

    @pytest.fixture
    def setup_mocks(self, mocker):
        """Configura mocks comuns"""
        mock_dep = mocker.patch('mymodule.dependency')
        mock_dep.return_value = Mock()
        return mock_dep

    def test_method_success_case(self, setup_mocks):
        """Testa caminho feliz"""
        # Arrange
        instance = MyClass()
        # Act
        result = instance.method(input_data)
        # Assert
        assert result == expected_value
        setup_mocks.assert_called_once()

    def test_method_error_case(self, setup_mocks):
        """Testa tratamento de erro"""
        # Arrange
        setup_mocks.side_effect = Exception("Test error")
        instance = MyClass()
        # Act & Assert
        with pytest.raises(MyCustomException):
            instance.method(input_data)
```

### Template Teste Integração

```python
import pytest
from testcontainers.kafka import KafkaContainer
from testcontainers.mongodb import MongoDbContainer

@pytest.fixture(scope="module")
def infrastructure():
    """Setup infraestrutura de testes"""
    kafka = KafkaContainer("confluentinc/cp-kafka:latest")
    mongo = MongoDbContainer("mongo:6.0")
    kafka.start()
    mongo.start()
    yield {"kafka": kafka.get_connection_url(),
           "mongo": mongo.get_connection_url()}
    kafka.stop()
    mongo.stop()

def test_integration_flow(infrastructure):
    """Testa fluxo completo"""
    # Arrange
    client = MyService(infrastructure["kafka"],
                       infrastructure["mongo"])
    # Act
    result = client.process(data)
    # Assert
    assert result.status == "completed"
```

## Referências

- [Pytest Documentation](https://docs.pytest.org/)
- [Python Testing Best Practices](https://docs.python-guide.org/writing/tests/)
- [Test Coverage Guidelines](https://coverage.readthedocs.io/)
