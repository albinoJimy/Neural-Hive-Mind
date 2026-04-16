# Feature Store: Integração Kafka - Design Document

> **Data:** 2026-04-15
> **Autor:** Claude (Brainstorming Design)
> **Status:** Approved for Implementation
> **Ticket:** TBD

---

## Sumário Executivo

Este documento descreve o design para integração do **Feature Store** ao fluxo Kafka principal do Neural-Hive-Mind. Actualmente, o Feature Store opera exclusivamente via API REST, computando 26 features para modelos ML. A integração Kafka permitirá a computação automática de features assim que planos cognitivos são criados, eliminando a necessidade de chamadas manuais.

**Objectivos:**
- Completude do fluxo de dados (end-to-end sem intervenção manual)
- Performance e escalabilidade (reduzir latência com processamento assíncrono)
- Desacoplamento (serviços evoluem independentemente)

---

## 1. Arquitectura

### 1.1 Fluxo Actual vs. Proposto

**Actual:**
```
[STE] → cognitive.plans.created → [Consensus] → [Orchestrator]
                                                        ↓
                                              [Chamada REST Manual]
                                                        ↓
                                                 [Feature Store]
```

**Proposto:**
```
[STE] → cognitive.plans.created ──→ [Consensus] → [Orchestrator]
             │                                        │
             └────────────────────────────────────────┘
                                    │
                                    ▼
                             [Feature Store]
                             (Consumer Kafka)
                                    │
                                    ▼
                            features.computed
```

### 1.2 Componentes

| Componente | Tipo | Descrição |
|-------------|------|------------|
| `CognitivePlanConsumer` | Consumer | Consome `cognitive.plans.created` |
| `FeaturesComputedProducer` | Producer | Publica `features.computed` (opcional) |
| `FeaturesDLQHandler` | Handler | Trata planos falhados via DLQ |
| `RetryStrategy` | Service | Retry com exponential backoff |

---

## 2. Fluxo de Dados Detalhado

### 2.1 Pipeline de Processamento

```
┌──────────────────────────────────────────────────────────────────────┐
│                     Feature Store - Pipeline de Dados                │
├──────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  [Semantic Translation Engine]                                        │
│       │                                                                │
│       │ cognitive.plans.created (Avro)                               │
│       ▼                                                                │
│  ┌──────────────────────────────────────────────┐                    │
│  │     CognitivePlanConsumer                    │                    │
│  │  ┌─────────────────────────────────────────┐  │                    │
│  │  │ 1. Deserializar mensagem Avro          │  │                    │
│  │  │ 2. Validar schema do plano             │  │                    │
│  │  │ 3. Verificar se já tem features (Redis) │  │                    │
│  │  │ 4. Computar features (se necessário)    │  │                    │
│  │  │ 5. Salvar no MongoDB                    │  │                    │
│  │  │ 6. Actualizar cache Redis               │  │                    │
│  │  │ 7. Publicar features.computed (opcional)│  │                    │
│  │  └─────────────────────────────────────────┘  │                    │
│  │                                              │                    │
│  │  ┌────────────────┐  ┌────────────────────┐ │                    │
│  │  │   Success      │  │      Failure        │ │                    │
│  │  └───────┬────────┘  └────────┬───────────┘ │                    │
│  └──────────┼──────────────────────┼─────────────┘                    │
│             │                      │                                  │
│             ▼                      ▼                                  │
│  [features.computed]         [cognitive.plans.dlq]                   │
│             │                      │                                  │
│             │                      └─→ [DLQ Handler]                   │
│             │                         → Alert + Retry                   │
│             │                                                           │
│             └──→ [Outros serviços podem consumir]                     │
│                                                                        │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.2 Idempotência

A computação de features é **idempotente**:
- Verifica Redis/MongoDB antes de computar
- Se features já existem, não recomputa
- Garante processamento seguro em caso de reprises

---

## 3. Componentes Detalhados

### 3.1 CognitivePlanConsumer

**Ficheiro:** `src/consumers/cognitive_plan_consumer.py`

**Responsabilidade:** Consumir `cognitive.plans.created` e processar planos cognitivos.

```python
class CognitivePlanConsumer:
    """Consumer de planos cognitivos para computação de features."""
    
    def __init__(
        self,
        settings: Settings,
        feature_store: FeatureStoreService,
        dlq_handler: FeaturesDLQHandler
    ):
        self.settings = settings
        self.feature_store = feature_store
        self.dlq_handler = dlq_handler
        self.consumer = None
        self.retry_strategy = RetryStrategy()
    
    async def start(self):
        """Inicia consumo de mensagens Kafka."""
        
    async def stop(self):
        """Para consumption de mensagens."""
        
    async def process_plan(self, plan: CognitivePlan):
        """Processa plano individual e computa features."""
        
    async def handle_failure(self, plan: CognitivePlan, error: Exception):
        """Envia plano falhado para DLQ."""
```

**Configuração:**
```python
KAFKA_COGNITIVE_PLANS_TOPIC = "cognitive.plans.created"
KAFKA_CONSUMER_GROUP = "feature-store-consumers"
KAFKA_AUTO_OFFSET_RESET = "earliest"
KAFKA_ENABLE_AUTO_COMMIT = False
```

### 3.2 FeaturesComputedProducer (Opcional)

**Ficheiro:** `src/producers/features_producer.py`

**Responsabilidade:** Publicar notificação de features computadas.

```python
class FeaturesComputedProducer:
    """Producer de eventos de features computadas."""
    
    async def publish_features_computed(
        self,
        plan_id: str,
        features: Features
    ):
        """Publica evento no tópico features.computed."""
```

**Schema do evento:**
```json
{
  "plan_id": "plan-123",
  "feature_count": 26,
  "computed_at": "2026-04-15T10:00:00Z",
  "computation_duration_ms": 150
}
```

### 3.3 FeaturesDLQHandler

**Ficheiro:** `src/consumers/dlq_handler.py`

**Responsabilidade:** Tratamento de planos falhados.

```python
class FeaturesDLQHandler:
    """Handler de Dead Letter Queue para planos falhados."""
    
    async def send_to_dlq(
        self,
        plan: CognitivePlan,
        error: Exception
    ):
        """Envia plano para DLQ com contexto de erro."""
```

**Schema DLQ:**
```json
{
  "original_plan": {...},
  "error": {
    "type": "FeatureComputationError",
    "message": "Timeout ao computar graph features",
    "traceback": "...",
    "timestamp": "2026-04-15T10:00:00Z"
  },
  "retry_count": 3,
  "failed_at": "2026-04-15T10:00:15Z",
  "plan_id": "plan-123"
}
```

---

## 4. Tratamento de Erros

### 4.1 Tipos de Erro

| Tipo de Erro | Acção | Exemplo |
|--------------|-------|---------|
| **Validação** | DLQ (sem retry) | Schema inválido, campos obrigatórios missing |
| **Computação** | Retry 3x → DLQ | Timeout na computação, erro de cálculo |
| **Persistência** | Retry infinito (backoff) | MongoDB connection error |
| **Cache** | Log warning (não blocking) | Redis connection error |

### 4.2 Estratégia de Retry

```python
class RetryStrategy:
    """Estratégia de retry para processamento de planos."""
    
    # Configuração
    MAX_RETRIES = 3
    RETRY_DELAYS = [1s, 5s, 15s]  # Exponential backoff
```

### 4.3 Tópicos Kafka

| Tópico | Tipo | Descrição |
|--------|------|------------|
| `cognitive.plans.created` | Input | Planos cognitivos criados |
| `features.computed` | Output | Features computadas (opcional) |
| `cognitive.plans.dlq.features` | DLQ | Planos falhados |

---

## 5. Estrutura de Ficheiros

```
feature-store/
├── src/
│   ├── consumers/              # NOVO
│   │   ├── __init__.py
│   │   ├── cognitive_plan_consumer.py
│   │   ├── dlq_handler.py
│   │   └── retry_strategy.py
│   ├── producers/              # NOVO
│   │   ├── __init__.py
│   │   └── features_producer.py
│   ├── config/
│   │   └── settings.py         # ATUALIZAR (adição kafka configs)
│   └── main.py                 # ATUALIZAR (iniciar consumer)
├── tests/
│   ├── unit/                   # NOVOS
│   │   ├── __init__.py
│   │   ├── test_cognitive_plan_consumer.py
│   │   ├── test_dlq_handler.py
│   │   └── test_retry_strategy.py
│   ├── integration/            # NOVOS
│   │   ├── __init__.py
│   │   └── test_kafka_flow.py
│   └── e2e/                    # NOVOS
│       ├── __init__.py
│       └── test_full_flow.py
└── requirements.txt            # ATUALIZAR (adição aiokafka)
```

---

## 6. Dependências

```python
# requirements.txt - adições
aiokafka>=0.9.0              # Kafka async client
avro-python3>=1.10.0        # Schema serialization
```

---

## 7. Configurações

```python
# src/config/settings.py - adições

class Settings(BaseSettings):
    # ... existentes ...
    
    # Kafka
    kafka_bootstrap_servers: str = Field(
        default="kafka.kafka.svc.cluster.local:9092"
    )
    kafka_cognitive_plans_topic: str = Field(
        default="cognitive.plans.created"
    )
    kafka_consumer_group: str = Field(
        default="feature-store-consumers"
    )
    kafka_dlq_topic: str = Field(
        default="cognitive.plans.dlq.features"
    )
    kafka_auto_offset_reset: str = Field(
        default="earliest"
    )
```

---

## 8. Estratégia de Testes

### 8.1 Testes Unitários

**Cobertura esperada:** 80%+

| Teste | Descrição |
|-------|-----------|
| `test_process_plan_success` | Processamento bem-sucedido |
| `test_process_plan_invalid_schema` | Rejeição de schema inválido |
| `test_process_plan_with_existing_features` | Idempotência |
| `test_dlq_handler_on_failure` | Envio para DLQ |
| `test_retry_exhaustion` | Exhaustão de retries |

### 8.2 Testes de Integração

| Teste | Descrição |
|-------|-----------|
| `test_consumer_receives_plan` | Consumer recebe mensagens |
| `test_features_persisted_and_cached` | Persistência e cache |
| `test_dlq_flow_on_failure` | Fluxo DLQ |

### 8.3 Testes E2E

| Teste | Descrição |
|-------|-----------|
| `test_full_pipeline_integration` | Pipeline completo |
| `test_retry_and_dlq_flow` | Retry e DLQ |

---

## 9. Monitorização

### 9.1 Métricas Prometheus

| Métrica | Tipo | Descrição |
|---------|------|------------|
| `feature_store_consumer_messages_total` | Counter | Mensagens consumidas |
| `feature_store_consumer_processing_duration_seconds` | Histogram | Tempo de processamento |
| `feature_store_consumer_failures_total` | Counter | Falhas por tipo |
| `feature_store_dlq_messages_total` | Counter | Mensagens DLQ |

### 9.2 Alerts

| Alerta | Condição |
|--------|----------|
| `FeatureStoreDLQHighRate` | DLQ > 10 msg/min |
| `FeatureStoreProcessingSlow` | P95 > 5s |
| `FeatureStoreConsumerLag` | Lag > 1000 mensagens |

---

## 10. Implementação

### 10.1 Lifespan Update

```python
# src/main.py - actualização do lifespan

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerenciamento do ciclo de vida com consumer."""
    settings = get_settings()
    
    # ... existentes (MongoDB, Redis, FeatureStore) ...
    
    # Inicializar consumer Kafka
    logger.info("Iniciando CognitivePlanConsumer...")
    consumer = CognitivePlanConsumer(settings, feature_store)
    await consumer.start()
    
    # Inicializar producer Kafka (opcional)
    producer = FeaturesComputedProducer(settings)
    await producer.start()
    
    yield
    
    # Shutdown
    logger.info("Parando Consumer e Producer...")
    await consumer.stop()
    await producer.close()
```

---

## 11. Rollback Plan

Em caso de problemas críticos, o consumer pode ser desabilitado via configuração:

```python
KAFKA_CONSUMER_ENABLED: bool = Field(default=False)
```

O serviço continuará a funcionar via API REST.

---

## 12. Próximos Passos

1. Criar spec detalhada (`create-spec`)
2. Decompor epic em tickets
3. Implementar componentes
4. Escrever testes
5. Deploy em staging
6. Monitorizar e validar

---

**Aprovação:** Design aprovado para implementação.
**Próximo Skill:** `superpowers:writing-plans`
