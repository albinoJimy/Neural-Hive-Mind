# ML Inference API

API de inferência ML para predição de aprovação de planos cognitivos no Neural Hive-Mind.

## Visão Geral

O **ML Inference API** é responsável por:

- **Carregar e servir** modelos ML treinados para predição de aprovação
- **Processar predições** individuais ou em batch
- **Proteger** o serviço com circuit breaker e rate limiting
- **Fornecer métricas** Prometheus e tracing OpenTelemetry
- **Suportar GPUs** opcionalmente para inferência acelerada

## Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│                    ML Inference API                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌────────────┐  ┌────────────┐  ┌──────────────────────┐ │
│  │ FastAPI    │  │ Circuit    │  │ Batch Engine         │ │
│  │ (porta 8010)│  │ Breaker    │  │ (processamento       │ │
│  │            │  │ (proteção) │  │  paralelo)            │ │
│  └─────┬──────┘  └─────┬──────┘  └──────────┬───────────┘ │
│        │               │                    │              │
│  ┌─────┴───────────────┴────────────────────┴───────────┐ │
│  │           Predictor Service                           │ │
│  │  • ApprovalPredictor wrapper                          │ │
│  │  • Feature extraction NLP                             │ │
│  │  • Model caching                                       │ │
│  └───────────────────────────────────────────────────────┘ │
│        │                                                      │
│  ┌─────┴──────────────────────────────────────────────────┐ │
│  │           ML Model (ApprovalPredictor)                 │ │
│  │  • GradientBoostingClassifier                         │ │
│  │  • 30+ features NLP                                    │ │
│  │  • Probabilidades multi-classe                         │ │
│  └───────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Estrutura do Projeto

```
ml-inference-api/
├── src/
│   ├── config/          # Configurações (Pydantic Settings)
│   ├── models/          # Modelos Pydantic (schemas)
│   ├── services/        # Serviços core
│   │   ├── predictor_service.py    # Wrapper ApprovalPredictor
│   │   ├── batch_engine.py          # Processamento batch
│   │   └── circuit_breaker.py       # Circuit breaker pattern
│   ├── api/             # Routers FastAPI
│   │   ├── health.py                 # Health, ready, metrics
│   │   └── inference.py              # Predict endpoints
│   ├── observability/   # Métricas Prometheus
│   ├── utils/           # Utilitários (GPU wrapper)
│   └── main.py          # Entry point
├── tests/
│   ├── unit/            # Testes unitários
│   └── integration/     # Testes de integração
├── Dockerfile
├── requirements.txt
├── pyproject.toml
└── README.md
```

## Tecnologias

- **FastAPI**: Framework web assíncrono
- **scikit-learn**: Biblioteca ML para o modelo
- **MLflow**: Model registry e versionamento
- **Circuit Breaker**: Padrão de resiliência
- **Prometheus**: Métricas customizadas
- **OpenTelemetry**: Distributed tracing
- **SlowAPI**: Rate limiting

## API REST

### Health & Metrics

- `GET /health` - Health check (liveness probe)
- `GET /ready` - Readiness check (dependências)
- `GET /metrics` - Métricas Prometheus
- `GET /model-info` - Informações do modelo carregado
- `GET /circuit-breaker` - Estado do circuit breaker

### Inferência

- `POST /api/v1/inference/predict` - Predição individual
- `POST /api/v1/inference/predict-batch` - Predição em batch
- `POST /api/v1/inference/circuit-breaker/reset` - Reset circuit breaker (admin)

## Exemplos de Uso

### Predição Individual

```bash
curl -X POST http://localhost:8010/api/v1/inference/predict \
  -H "Content-Type: application/json" \
  -d '{
    "intent_text": "Create new user with email verification and password hashing",
    "specialist_confidence": 0.75,
    "specialist_type": "security"
  }'
```

Response:
```json
{
  "decision": "approve",
  "confidence": 0.92,
  "probabilities": {
    "approve": 0.92,
    "reject": 0.05,
    "review_required": 0.03
  },
  "model_version": "v7",
  "inference_time_ms": 15.3,
  "timestamp": "2026-04-04T10:30:00Z"
}
```

### Predição em Batch

```bash
curl -X POST http://localhost:8010/api/v1/inference/predict-batch \
  -H "Content-Type: application/json" \
  -d '{
    "requests": [
      {
        "intent_text": "Create new user with email verification",
        "specialist_confidence": 0.75
      },
      {
        "intent_text": "Delete all records without backup",
        "specialist_confidence": 0.5
      }
    ],
    "options": {
      "parallel": true,
      "aggregate_results": true
    }
  }'
```

## Configuração

### Variáveis de Ambiente

```bash
# Geral
SERVICE_NAME=ml-inference-api
ENVIRONMENT=development
LOG_LEVEL=INFO

# API
API_HOST=0.0.0.0
API_PORT=8010

# MLflow / Model Registry
MLFLOW_TRACKING_URI=http://mlflow:5000
MLFLOW_MODEL_NAME=nhm_approval_model
LOCAL_MODEL_PATH=/app/ml_models

# Batch Inference
BATCH_DEFAULT_SIZE=10
BATCH_MAX_SIZE=100

# Rate Limiting
ENABLE_RATE_LIMITING=true
RATE_LIMIT_REQUESTS_PER_MINUTE=60

# GPU (opcional)
ENABLE_GPU=false
GPU_MEMORY_FRACTION=0.8

# Circuit Breaker
CIRCUIT_BREAKER_THRESHOLD=5
CIRCUIT_BREAKER_TIMEOUT_SECONDS=60

# Observabilidade
OTEL_EXPORTER_ENDPOINT=http://otel-collector:4317
PROMETHEUS_PORT=9091
```

## Métricas Prometheus

### Principais Métricas

- `model_loaded` - Se o modelo ML está carregado (gauge)
- `predictions_total` - Total de predições por decisão (counter)
- `prediction_duration_seconds` - Duração das predições (histogram)
- `prediction_confidence` - Distribuição de confiança (histogram)
- `batch_predictions_total` - Total de batches processados (counter)
- `circuit_breaker_state` - Estado do circuit breaker (gauge)

### Circuit Breaker

O circuit breaker protege o serviço contra falhas em cascata:

- **CLOSED**: Funcionamento normal
- **OPEN**: Rejeita chamadas após threshold de falhas
- **HALF_OPEN**: Testando recuperação

## Observabilidade

### Tracing

OpenTelemetry instrumentado automaticamente para:
- FastAPI requests
- Funções de predição
- Extração de features

Traces exportados para Jaeger via OTLP Collector.

### Logging

Logs estruturados com structlog em formato JSON:
- `prediction_request` - Request recebida
- `prediction_completed` - Predição completada
- `circuit_breaker_opened` - Circuit breaker aberto
- `model_loaded` - Modelo carregado

## Deployment

### Local Development

```bash
# Instalar dependências
pip install -r requirements.txt

# Copiar modelo ML treinado para ml_models/
cp ../../ml_models/nhm_approval_model.pkl ./ml_models/

# Iniciar serviço
python -m src.main
```

### Docker

```bash
# Build imagem
docker build -t ml-inference-api:1.0.0 .

# Executar container
docker run -p 8010:8010 -p 9091:9091 \
  -v $(pwd)/ml_models:/app/ml_models \
  ml-inference-api:1.0.0
```

### Kubernetes

```bash
# Deploy via Helm
helm install ml-inference-api ./charts/ml-inference-api

# Validação
./scripts/validation/validate-ml-inference-api.sh
```

## Integração com Neural Hive-Mind

O ML Inference API integra-se com outros serviços:

1. **Semantic Translation Engine** extrai NLP features
2. **Consensus Engine** aguarda predição ML para权重
3. **Approval Service** usa predição para decisão humana

## Status da Implementação

✅ **100% Completo:**
- Modelos Pydantic para requests/responses
- Circuit breaker pattern
- Predictor service com wrapper
- Batch engine com processamento paralelo
- API REST (health, predict, predict-batch)
- Métricas Prometheus customizadas
- Rate limiting com SlowAPI
- Observabilidade completa
- Main application com lifecycle management

## Roadmap (Melhorias Futuras)

- [ ] Suporte a GPU com ONNX Runtime
- [ ] Cache de predições com Redis
- [ ] A/B testing de modelos
- [ ] Model ensemble (múltiplos modelos)
- [ ] Streaming de predições
- [ ] Modelo Canary deployment
- [ ] Autenticação JWT para endpoints admin

## Contribuindo

Contribuições são bem-vindas! Por favor:

1. Siga os padrões de código existentes
2. Adicione testes para novas funcionalidades
3. Atualize a documentação
4. Execute validação completa antes de PR

## Licença

Copyright © 2026 Neural Hive-Mind Team
