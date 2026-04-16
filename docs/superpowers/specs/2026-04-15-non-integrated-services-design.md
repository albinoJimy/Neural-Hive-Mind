# Design: Integração Kafka dos 5 Serviços Não Integrados

> **Data:** 2026-04-15
> **Autor:** Claude (Brainstorming Design)
> **Status:** Approved for Implementation

---

## Sumário Executivo

Este documento descreve o design para integração Kafka de 5 serviços do Neural-Hive-Mind que atualmente operam apenas via API REST ou têm consumidores não utilizados.

**Serviços Alvo:**
1. **Software Engineering Pipeline** - Geração de CI/CD pipelines
2. **Architect Agent** - Planejamento de arquitetura
3. **Experiment Impact Analyzer** - Análise de impacto de experimentos
4. **Hypothesis Library** - Biblioteca de hipóteses
5. **ML Inference API** - API de predição ML

---

## 1. Software Engineering Pipeline

### 1.1 Fluxo Atual vs. Proposto

**Atual:**
```
[Manual] → POST /api/v1/manifests → [Software Engineering Pipeline]
                                      ↓
                                   [Gera Manifest]
```

**Proposto:**
```
[STE] → cognitive.plans.created → [Software Engineering Pipeline]
             │                              ↓
             │                    (Filtra domain_devops > 0)
             │                              ↓
             └────────────────────────→ [Gera Manifest Automaticamente]
```

### 1.2 Componentes

| Componente | Tipo | Descrição |
|-----------|------|------------|
| `CognitivePlanConsumer` | Consumer | Consome `cognitive.plans.created` |
| `PipelineGeneratorService` | Service | Gera manifests baseado no plano |
| `PipelineProducer` | Producer | Publica `pipelines.generated` |

### 1.3 Schema do Evento

**Input:** `cognitive.plans.created`
```json
{
  "plan_id": "plan-123",
  "intent": "Create CI/CD pipeline for microservice",
  "nlp_features": {
    "domain_devops": 0.95,
    "action_create": 1.0
  }
}
```

**Output:** `pipelines.generated`
```json
{
  "plan_id": "plan-123",
  "manifest_id": "manifest-456",
  "provider": "github_actions",
  "repo_url": "https://github.com/org/repo"
}
```

---

## 2. Architect Agent

### 2.1 Estado Atual

O Architect Agent **JÁ TEM** `CognitivePlanConsumer` implementado, mas **NÃO está sendo usado** no `main.py`.

### 2.2 Alteração Necessária

**Arquivo:** `services/architect-agent/src/main.py`

**Adicionar ao lifespan:**
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    # Inicializar ConsumerManager
    consumer_manager = ConsumerManager()

    # Registrar consumidores
    cognitive_plan_consumer = CognitivePlanConsumer()
    consumer_manager.register(cognitive_plan_consumer)

    # Criar task para consumidores
    consumer_task = asyncio.create_task(consumer_manager.start_all())

    yield

    # Shutdown
    await cognitive_plan_consumer.stop()
    consumer_task.cancel()
```

### 2.3 Tópicos Kafka

| Tópico | Direção | Descrição |
|--------|---------|-----------|
| `cognitive.plans.created` | Input | Planos cognitivos criados |
| `architecture.plans.generated` | Output | Planos de arquitetura gerados |

---

## 3. Experiment Impact Analyzer

### 3.1 Fluxo Proposto

```
[Optimizer Agents] → experiments.completed → [Experiment Impact Analyzer]
                                             ↓
                                         [Analisa Impacto]
                                             ↓
                                    [Persiste no MongoDB]
                                             ↓
                                    [Publica impact.analyzed]
```

### 3.2 Componentes

| Componente | Tipo | Descrição |
|-----------|------|------------|
| `ExperimentCompletedConsumer` | Consumer | Consome `experiments.completed` |
| `ImpactAnalysisService` | Service | Analisa impacto curto/longo prazo |
| `ImpactProducer` | Producer | Publica `impact.analyzed` |

### 3.3 Schema do Evento

**Input:** `experiments.completed`
```json
{
  "experiment_id": "exp-123",
  "variant": "B",
  "metrics": {
    "conversion_rate": 0.15,
    "sample_size": 1000
  },
  "status": "completed"
}
```

**Output:** `impact.analyzed`
```json
{
  "experiment_id": "exp-123",
  "short_term_impact": {
    "lift": "+5%",
    "significance": 0.95
  },
  "long_term_projection": {
    "expected_roi": "+12%",
    "confidence_interval": [8, 16]
  }
}
```

---

## 4. Hypothesis Library

### 4.1 Fluxo Proposto

```
[Optimizer/Analyst] → hypotheses.created → [Hypothesis Library]
                                           ↓
                                      [Persiste Hipótese]
                                           ↓
                                      [Versiona]
```

### 4.2 Componentes

| Componente | Tipo | Descrição |
|-----------|------|------------|
| `HypothesisConsumer` | Consumer | Consome `hypotheses.created` |
| `HypothesisService` | Service | Gerencia hipóteses e versionamento |

### 4.3 Schema do Evento

**Input:** `hypotheses.created`
```json
{
  "hypothesis_id": "hyp-123",
  "title": "Increasing cache TTL reduces latency",
  "description": "By increasing cache TTL from 5min to 15min...",
  "category": "performance",
  "priority": "high"
}
```

---

## 5. ML Inference API

### 5.1 Estado Atual

O `approval_predictor.py` é um script standalone. Precisa ser convertido em serviço FastAPI.

### 5.2 Arquitectura Proposta

```
[FastAPI] → /api/v1/predict → [ML Inference Service]
                            ↓
                       [ApprovalPredictor]
                            ↓
                       [Returns Decision]
```

### 5.3 Componentes

| Componente | Descrição |
|-----------|-----------|
| `src/main.py` | FastAPI application |
| `src/services/prediction_service.py` | Wrapper para ApprovalPredictor |
| `src/api/routes/predictions.py` | REST endpoints |
| `src/consumers/prediction_consumer.py` | Kafka consumer opcional |

### 5.4 API Endpoints

| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/api/v1/predict` | POST | Prediz aprovação de plano |
| `/api/v1/predict/batch` | POST | Predição em lote |
| `/api/v1/model/info` | GET | Informações do modelo |

---

## 6. Padrões Comuns

### 6.1 Base Kafka Consumer

Todos os serviços usarão o mesmo padrão do Architect Agent:

```python
class BaseKafkaConsumer(ABC):
    def __init__(self):
        self._running = False

    @abstractmethod
    async def process_message(self, message: dict) -> None:
        pass

    async def start(self) -> None:
        self._running = True
        consumer = AIOKafkaConsumer(...)
        await consumer.start()

        while self._running:
            async for msg in consumer:
                await self.process_message(msg)

    async def stop(self) -> None:
        self._running = False
```

### 6.2 Error Handling

| Tipo de Erro | Acção |
|--------------|-------|
| Validação | DLQ (sem retry) |
| Processamento | Retry 3x → DLQ |
| Persistência | Retry infinito |
| Rede | Exponential backoff |

### 6.3 Métricas Prometheus

Todas as integrações terão:
- `*_consumer_messages_total` - Counter
- `*_consumer_processing_duration_seconds` - Histogram
- `*_consumer_failures_total` - Counter

---

## 7. Implementação

### 7.1 Estrutura de Ficheiros

**Software Engineering Pipeline:**
```
src/consumers/
├── __init__.py
├── base.py
└── cognitive_plan_consumer.py
src/producers/
├── __init__.py
└── pipeline_producer.py
```

**Architect Agent:**
```
src/main.py - ATUALIZAR (ativar consumer no lifespan)
```

**Experiment Impact Analyzer:**
```
src/consumers/
├── __init__.py
├── base.py
└── experiment_consumer.py
```

**Hypothesis Library:**
```
src/consumers/
├── __init__.py
├── base.py
└── hypothesis_consumer.py
```

**ML Inference API:**
```
services/ml-inference-api/
├── src/
│   ├── main.py
│   ├── api/
│   │   └── routes/
│   │       └── predictions.py
│   └── services/
│       └── prediction_service.py
├── tests/
└── requirements.txt
```

### 7.2 Dependências

```python
# requirements.txt - adições para todos os serviços
aiokafka>=0.9.0
avro-python3>=1.10.0
```

---

## 8. Rollback Plan

Cada serviço pode desabilitar o consumer via configuração:

```python
KAFKA_CONSUMER_ENABLED: bool = Field(default=False)
```

---

## 9. Próximos Passos

1. Criar implementation plans detalhados para cada serviço
2. Implementar componentes seguindo padrão TDD
3. Escrever testes unitários e integração
4. Deploy em staging sequencialmente
5. Monitorizar métricas

---

**Aprovação:** Design aprovado para implementação.
**Próximo Skill:** `superpowers:writing-plans`
