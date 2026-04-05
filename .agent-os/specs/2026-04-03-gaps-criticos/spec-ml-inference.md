# Spec: ML Inference Service

> **Epic:** ML-001 - Production ML Inference
> **Prioridade:** 🔴 CRÍTICA (ML Pipeline incompleto)
> **Esforço Estimado:** 16-19 dias (~3 semanas)
> **Data:** 2026-04-03

---

## Resumo Executivo

O **ML Inference** está apenas **50% completo**. O training pipeline está 90% mas falta uma API REST dedicada, model registry integration, batch inference, e monitoring robusto. Precisamos completar para produção.

---

## Contexto

### Status Atual
- **ml_pipelines/training/** - 90% completo ✅
- **ml_pipelines/inference/** - 50% completo ⚠️

### O que Existe
- `approval_predictor.py` - Classe ApprovalPredictor
- Extração de features NLP (30 features)
- Predição com RandomForest
- Suporte a GPU via GPUInferenceWrapper

### O que Falta
- ❌ API REST dedicada
- ❌ Batch inference
- ❌ Model versioning
- ❌ Model registry integration (MLflow)
- ❌ Monitoring/Prometheus metrics
- ❌ Error handling robusto
- ❌ Rate limiting

### Problemas da Arquitetura Atual
1. **Inference acoplado ao Approval Service** - Não é independente
2. **Sem API dedicada** - Hard to scale
3. **Sem batch processing** - Ineficiente para múltiplas predições
4. **Sem versionamento** - Difficult rollback

---

## User Stories

### US-001: Como Approval Service, quero chamar uma API de inference dedicada
Para que o inference possa escalar independentemente.

### US-002: Como ML Engineer, quero fazer batch predictions
Para que possa processar múltiplos casos eficientemente.

### US-003: Como operador, quero monitorar performance dos modelos
Para que possa detectar degradação e drift.

### US-004: Como desenvolvedor, quero fazer rollback de modelos
Para que possa reverter rapidamente em caso de problemas.

---

## Escopo

### IN CLUDE

#### 1. ML Inference API Service
**Path:** `services/ml-inference-api/` (NOVO SERVIÇO)

##### Core Features
- **REST API** para predições individuais
- **Batch endpoint** para múltiplas predições
- **Health checks** (readiness, liveness)
- **Metrics** (Prometheus)
- **Tracing** (OpenTelemetry)

##### API Endpoints
```python
# Predição individual
POST /api/v1/inference/predict
{
  "intent_text": "Create new user with email verification",
  "features": {...},
  "model_version": "v7",
  "options": {
    "explain": true,
    "include_probabilities": true
  }
}

# Batch prediction
POST /api/v1/inference/predict-batch
{
  "requests": [
    {"intent_text": "...", "features": {...}},
    {"intent_text": "...", "features": {...}}
  ]
}

# Model info
GET /api/v1/inference/models
GET /api/v1/inference/models/{model_name}/versions

# Health
GET /health
GET /ready
```

#### 2. Model Registry Integration
- **MLflow client** para buscar modelos em produção
- **Auto-promotion** de staging → production
- **Model versioning** (v1, v2, v3...)
- **Fallback** para versão anterior

#### 3. Batch Inference Engine
- **Async processing** de batches
- **ThreadPoolExecutor** para paralelismo
- **Chunking** de grandes volumes
- **Progress tracking**

#### 4. Monitoring & Metrics
- **Prediction metrics:**
  - `model_predictions_total` (counter)
  - `prediction_confidence` (gauge/histogram)
  - `prediction_duration_ms` (histogram)
  - `model_errors_total` (counter)
- **Model metrics:**
  - `model_version_info` (gauge)
  - `model_drift_score` (gauge)

#### 5. Additional Features
- **Rate limiting** (user-based)
- **Circuit breaker** para model failures
- **Request/response logging**
- **A/B testing support**

### OUT OF SCOPE
- ML training pipeline (já existe)
- Feature computation (já existe em approval-service)
- Model training automation

---

## Especificação Técnica

### Arquitetura Proposta

```
┌─────────────────────────────────────────────────────────────┐
│                    ML INFERENCE API SERVICE                  │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   REST API   │  │ Batch Engine │  │  Health API  │      │
│  └──────┬───────┘  └──────┬───────┘  └──────────────┘      │
│         │                 │                                  │
│         └────────┬────────┘                                  │
│                  ▼                                           │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              Model Registry Client                   │   │
│  │         (MLflow Integration)                         │   │
│  └──────────────────────┬──────────────────────────────┘   │
│                         │                                   │
│  ┌──────────────────────▼──────────────────────────────┐   │
│  │              Inference Engine                        │   │
│  │  • Feature Extraction                                │   │
│  │  • Model Loading                                     │   │
│  │  • Prediction                                        │   │
│  │  • Explanation (SHAP/LIME)                           │   │
│  └──────────────────────┬──────────────────────────────┘   │
│                         │                                   │
│  ┌──────────────────────▼──────────────────────────────┐   │
│  │              GPU Inference Wrapper                   │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              Observability Layer                     │   │
│  │  • Prometheus Metrics                                │   │
│  │  • OpenTelemetry Tracing                             │   │
│  │  • Structured Logging                                │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### Stack Tecnológica

```txt
# Core
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
pydantic>=2.5.0

# ML
mlflow>=2.9.0
scikit-learn>=1.3.0
transformers>=4.35.0  # Para NLP features
torch>=2.1.0  # GPU support

# Observability
prometheus-client>=0.19.0
opentelemetry-api>=1.21.0
opentelemetry-sdk>=1.21.0
structlog>=24.1.0

# Infra
redis>=5.0.0  # Cache
httpx>=0.25.0  # HTTP client
```

### Model Registry Client

```python
# ml_pipelines/inference/model_registry.py
from mlflow import MlflowClient
from typing import Optional

class ModelRegistryClient:
    def __init__(self, mlflow_uri: str):
        self.mlflow_uri = mlflow_uri
        self.client = MlflowClient(mlflow_uri)
        self._cache = {}

    def get_production_model(self, model_name: str) -> ModelInfo:
        """Get model in production stage."""
        versions = self.client.get_latest_versions(
            model_name,
            stages=["Production"]
        )
        if not versions:
            raise ModelNotFoundError(f"No production model for {model_name}")
        return ModelInfo(
            name=model_name,
            version=versions[0].version,
            uri=versions[0].source
        )

    def promote_model(self, model_name: str, version: str, stage: str):
        """Promote model to specific stage."""
        self.client.transition_model_version_stage(
            name=model_name,
            version=version,
            target_stage=stage
        )

    def get_model(self, model_name: str, version: Optional[str] = None):
        """Load model from registry."""
        import mlflow.pyfunc
        model_uri = f"models:/{model_name}/{version or 'Production'}"
        return mlflow.pyfunc.load_model(model_uri)
```

### Batch Inference Engine

```python
# ml_pipelines/inference/batch_engine.py
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict
import asyncio

class BatchInferenceEngine:
    def __init__(self, model_path: str, batch_size: int = 32):
        self.model = load_model(model_path)
        self.batch_size = batch_size
        self.executor = ThreadPoolExecutor(max_workers=4)

    async def predict_batch(self, requests: List[Dict]) -> List[Dict]:
        """Process multiple prediction requests efficiently."""
        # Chunk into batches
        chunks = [requests[i:i + self.batch_size]
                  for i in range(0, len(requests), self.batch_size)]

        # Process in parallel
        loop = asyncio.get_event_loop()
        results = await asyncio.gather(*[
            loop.run_in_executor(
                self.executor,
                self._process_batch,
                chunk
            )
            for chunk in chunks
        ])

        return [item for sublist in results for item in sublist]

    def _process_batch(self, batch: List[Dict]) -> List[Dict]:
        """Process a single batch."""
        features = [self._extract_features(r) for r in batch]
        predictions = self.model.predict_proba(features)
        return [
            {
                "request_id": r["request_id"],
                "decision": "approve" if p[1] > 0.5 else "reject",
                "confidence": float(max(p))
            }
            for r, p in zip(batch, predictions)
        ]
```

### Inference Metrics

```python
# ml_pipelines/inference/metrics.py
from prometheus_client import Counter, Histogram, Gauge, Info

class InferenceMetrics:
    def __init__(self):
        self.registry = CollectorRegistry()

        # Prediction metrics
        self.predictions_total = Counter(
            'model_predictions_total',
            'Total number of predictions',
            ['model_name', 'model_version', 'decision'],
            registry=self.registry
        )

        self.prediction_confidence = Histogram(
            'prediction_confidence',
            'Prediction confidence distribution',
            ['model_name', 'model_version'],
            buckets=[0.1, 0.3, 0.5, 0.7, 0.9, 1.0],
            registry=self.registry
        )

        self.prediction_duration = Histogram(
            'prediction_duration_ms',
            'Prediction duration in milliseconds',
            ['model_name', 'model_version'],
            registry=self.registry
        )

        # Model info
        self.model_info = Info(
            'model_info',
            'Current model information',
            registry=self.registry
        )

    def record_prediction(self, model_name: str, model_version: str,
                         decision: str, confidence: float, duration_ms: int):
        self.predictions_total.labels(
            model_name=model_name,
            model_version=model_version,
            decision=decision
        ).inc()
        self.prediction_confidence.labels(
            model_name=model_name,
            model_version=model_version
        ).observe(confidence)
        self.prediction_duration.labels(
            model_name=model_name,
            model_version=model_version
        ).observe(duration_ms)

    def set_model_info(self, model_name: str, model_version: str,
                      model_type: str):
        self.model_info.info({
            'model_name': model_name,
            'model_version': model_version,
            'model_type': model_type
        })
```

### Avro Schema para Inference

```json
{
  "type": "record",
  "name": "InferenceRequest",
  "namespace": "io.neuralhive.inference",
  "fields": [
    {
      "name": "request_id",
      "type": "string"
    },
    {
      "name": "intent_text",
      "type": ["null", "string"],
      "default": null
    },
    {
      "name": "features",
      "type": [{"type": "map", "values": "double"}, "null"],
      "default": null
    },
    {
      "name": "model_version",
      "type": ["null", "string"],
      "default": "latest"
    },
    {
      "name": "options",
      "type": [
        {
          "type": "record",
          "name": "InferenceOptions",
          "fields": [
            {"name": "explain", "type": "boolean", "default": false},
            {"name": "include_probabilities", "type": "boolean", "default": true},
            {"name": "batch_mode", "type": "boolean", "default": false}
          ]
        },
        "null"
      ],
      "default": null
    }
  ]
}
```

---

## Testes

### Unit Tests
- Model registry client
- Batch inference engine
- Metrics collection
- Feature extraction

### Integration Tests
- MLflow integration
- Model loading/prediction
- API endpoints

### Performance Tests
- Latência p50, p95, p99
- Throughput (req/s)
- Batch vs individual
- GPU vs CPU

---

## Deliverables

### Fase 1: Core Infrastructure (2-3 semanas)
1. [ ] Criar serviço ml-inference-api
2. [ ] Implementar API REST (/predict, /predict-batch)
3. [ ] Integrar com MLflow registry
4. [ ] Adicionar Prometheus metrics
5. [ ] Implementar rate limiting

### Fase 2: Advanced Features (1-2 semanas)
1. [ ] Batch inference engine
2. [ ] GPU acceleration
3. [ ] Circuit breaker
4. [ ] Request/response logging

### Fase 3: Production Readiness (1 semana)
1. [ ] Avro/Protobuf schemas
2. [ ] Canary deployment support
3. [ ] Comprehensive monitoring
4. [ ] Documentation

---

## Critérios de Aceite

### Funcional
- [ ] API REST funcional
- [ ] Batch inference operacional
- [ ] Model registry integration
- [ ] Metrics Prometheus funcionando

### Performance
- [ ] Latência p50 < 50ms
- [ ] Latência p99 < 200ms
- [ ] Throughput > 1000 req/s
- [ ] Batch 10x mais eficiente que individual

### Operacional
- [ ] Health checks funcionando
- [ ] Graceful shutdown
- [ ] Error logging
- [ ] Circuit breaker ativo

---

## Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| MLflow latency | Média | Alto | Cache de modelos |
| GPU memory leak | Baixa | Alto | Monitoring rigoroso |
| Batch timeout | Média | Médio | Timeout configurável |

---

## Referências
- Predictor existente: `ml_pipelines/inference/approval_predictor.py`
- Training pipeline: `ml_pipelines/training/`
- MLflow docs: https://mlflow.org/docs/latest/
