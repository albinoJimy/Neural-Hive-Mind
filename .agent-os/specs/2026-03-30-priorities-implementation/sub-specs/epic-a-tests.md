# Sub-Spec: Epic A - Aumentar Cobertura de Testes

## Objetivo

Aumentar cobertura de testes de 9.41% para 60% focando em 5 serviços críticos.

## Serviços Alvo

### 1. semantic-translation-engine
**Cobertura atual:** ~19 arquivos de teste
**Meta:** 50+ testes novos

**Funcionalidades a testar:**
- SemanticParser: enriquecimento de contexto
- DAGGenerator: planos executáveis
- RiskScorer: scoring de risco
- NLPProcessor: cache e processamento NLP
- DLQProcessor: Dead Letter Queue
- Integration com Neo4j, MongoDB, Redis

**Fixtures a criar:**
```python
@pytest.fixture
def sample_intent_envelope():
    return {
        "intent_id": str(uuid.uuid4()),
        "text": "Create a user in the system",
        "domain": "technical",
        "language": "en"
    }

@pytest.fixture
def mock_neo4j_client():
    with patch('neo4j.GraphDatabase.driver') as mock:
        yield mock

@pytest.fixture
def mock_mongodb_client():
    with patch('motor.motor_asyncio.AsyncIOMotorClient') as mock:
        yield mock
```

### 2. consensus-engine
**Cobertura atual:** ~7 testes (baixa)
**Meta:** 50+ testes novos

**Funcionalidades a testar:**
- HierarchicalConsensusOrchestrator: 5 níveis de senioridade
- BayesianAggregator: agregação bayesiana
- VotingEnsemble: votação ponderada
- PheromoneOrchestrator: sistema de feromônios
- Integration com especialistas via gRPC

**Fixtures a criar:**
```python
@pytest.fixture
def sample_specialist_opinions():
    return [
        {
            "opinion_id": str(uuid.uuid4()),
            "specialist_type": "business",
            "recommendation": "approve",
            "confidence_score": 0.85,
            "seniority_level": "senior"
        },
        {
            "opinion_id": str(uuid.uuid4()),
            "specialist_type": "technical",
            "recommendation": "approve",
            "confidence_score": 0.75,
            "seniority_level": "mid_level"
        }
    ]

@pytest.fixture
def mock_hierarchical_weights():
    return {
        "business_senior": 1.0,
        "technical_senior": 1.0,
        "business_mid_level": 0.75,
        "technical_mid_level": 0.75
    }
```

### 3. approval-service
**Cobertura atual:** ~4 testes (muito baixa)
**Meta:** 30+ testes novos

**Funcionalidades a testar:**
- MLPredictorService: predição de aprovação
- Active Learning API: 5 endpoints
- FeedbackCollector: coleta de feedback
- Integration com MLflow

**Fixtures a criar:**
```python
@pytest.fixture
def sample_approval_request():
    return {
        "plan_id": str(uuid.uuid4()),
        "risk_score": 0.5,
        "confidence": 0.75
    }

@pytest.fixture
def mock_ml_model():
    with patch('mlflow.pyfunc.load_model') as mock:
        mock.return_value.predict.return_value = [0.8, 0.2]
        yield mock
```

### 4. gateway-intencoes
**Cobertura atual:** ~11 testes
**Meta:** 40+ testes novos

**Funcionalidades a testar:**
- NLUPipeline: classificação de domínio
- ASRPipeline: processamento de voz
- AdaptiveRouter: roteamento adaptativo
- PIIDetectorLite: detecção de PII
- RateLimiter middleware

**Fixtures a criar:**
```python
@pytest.fixture
def sample_voice_input():
    return {
        "audio_data": b"fake_audio_bytes",
        "language": "en"
    }

@pytest.fixture
def mock_asr_engine():
    with patch('whisper.load_model') as mock:
        yield mock
```

### 5. neural_hive_domain
**Cobertura atual:** 0 testes (diretório não existe)
**Meta:** Criar diretório tests/ com 20+ testes

**Funcionalidades a testar:**
- CognitivePlan: modelo de plano cognitivo
- SpecialistOpinion: parecer de especialista
- DTOs: objetos de transferência
- Events: eventos do domínio
- Value Objects: objetos de valor

## Padrões a Seguir

### Estrutura de Teste
```python
import pytest
from unittest.mock import Mock, AsyncMock, patch

class TestComponent:
    """Testes para [Componente]"""

    def setup_method(self):
        """Setup antes de cada teste"""
        self.component = Component()

    def test_basic_functionality(self):
        """Teste funcionalidade básica"""
        result = self.component.method()
        assert result is not None

    @pytest.mark.asyncio
    async def test_async_functionality(self):
        """Teste funcionalidade assíncrona"""
        result = await self.component.async_method()
        assert result == "expected"

    def test_error_handling(self):
        """Teste tratamento de erros"""
        with pytest.raises(ValueError):
            self.component.method_error()
```

### Marcadores pytest
- `@pytest.mark.unit` - Testes unitários
- `@pytest.mark.integration` - Testes de integração
- `@pytest.mark.kafka` - Testes que requerem Kafka
- `@pytest.mark.grpc` - Testes que requerem gRPC
- `@pytest.mark.slow` - Testes lentos (>1 minuto)

## Arquivos a Criar

```
services/semantic-translation-engine/tests/
├── test_semantic_parser.py
├── test_dag_generator.py
├── test_risk_scorer.py
├── test_nlp_processor.py
├── test_dlq_processor.py
└── fixtures.py

services/consensus-engine/tests/
├── test_hierarchical_consensus.py
├── test_bayesian_aggregator.py
├── test_voting_ensemble.py
├── test_pheromone_orchestrator.py
└── fixtures.py

services/approval-service/tests/
├── test_ml_predictor_service.py
├── test_active_learning_api.py
├── test_feedback_collector.py
└── fixtures.py

services/gateway-intencoes/tests/
├── test_nlu_pipeline.py
├── test_asr_pipeline.py
├── test_adaptive_router.py
├── test_pii_detector.py
└── fixtures.py

libraries/python/neural_hive_domain/tests/
├── __init__.py
├── conftest.py
├── test_cognitive_plan.py
├── test_specialist_opinion.py
├── test_dtos.py
└── test_events.py
```

## Verificação

```bash
# Executar testes com coverage
pytest services/semantic-translation-engine/tests/ --cov=src --cov-report=term-missing
pytest services/consensus-engine/tests/ --cov=src --cov-report=term-missing
pytest services/approval-service/tests/ --cov=src --cov-report=term-missing
pytest services/gateway-intencoes/tests/ --cov=src --cov-report=term-missing
pytest libraries/python/neural_hive_domain/tests/ --cov=src --cov-report=term-missing

# Verificar cobertura agregada
pytest --cov=services/semantic-translation-engine/src \
       --cov=services/consensus-engine/src \
       --cov=services/approval-service/src \
       --cov=services/gateway-intencoes/src \
       --cov=libraries/python/neural_hive_domain/src \
       --cov-report=html

# Meta: coverage ≥ 60%
```
