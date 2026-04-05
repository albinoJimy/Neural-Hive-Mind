# Deployment Guide - ML Inference API

Guia completo de deployment do serviço ML Inference API em diferentes ambientes.

## Índice

- [Requisitos](#requisitos)
- [Variáveis de Ambiente](#variáveis-de-ambiente)
- [Deploy Local](#deploy-local)
- [Deploy com Docker](#deploy-com-docker)
- [Deploy Kubernetes (Helm)](#deploy-kubernetes-helm)
- [Configuração de MLflow](#configuração-de-mlflow)
- [GPU Support](#gpu-support)
- [Troubleshooting](#troubleshooting)

---

## Requisitos

### Sistema

- **SO:** Linux (Ubuntu 20.04+, Debian 11+) ou macOS 12+
- **Python:** 3.10 ou superior
- **RAM:** Mínimo 512MB, recomendado 1GB+
- **CPU:** Mínimo 1 core, recomendado 2+ cores
- **Disco:** Mínimo 500MB (incluindo modelo ML)

### Dependências Python

Ver `requirements.txt` para a lista completa. Principais:

```txt
fastapi>=0.115.0
uvicorn[standard]>=0.34.0
pydantic>=2.10.0
pydantic-settings>=2.6.0
mlflow>=2.9.0
scikit-learn>=1.3.0
structlog>=24.1.0
prometheus-client>=0.19.0
opentelemetry-api>=1.21.0
slowapi>=0.1.9
```

### Serviços Externos (Opcionais)

| Serviço | Propósito | Obrigatório |
|---------|-----------|-------------|
| MLflow | Model Registry | Recomendado |
| Prometheus | Métricas | Recomendado |
| OTel Collector | Tracing | Recomendado |
| Jaeger | Visualização de traces | Opcional |

---

## Variáveis de Ambiente

### Variáveis Obrigatórias

```bash
# Mínimo para funcionamento
ENVIRONMENT=development
API_PORT=8010
```

### Variáveis Recomendadas

```bash
# Identificação
SERVICE_NAME=ml-inference-api
SERVICE_VERSION=1.0.0

# Logging
LOG_LEVEL=INFO

# Modelo ML
LOCAL_MODEL_PATH=/app/ml_models
MLFLOW_MODEL_NAME=nhm_approval_model
```

### Variáveis Opcionais

```bash
# API
API_HOST=0.0.0.0

# MLflow
MLFLOW_TRACKING_URI=http://mlflow:5000

# Batch
BATCH_DEFAULT_SIZE=10
BATCH_MAX_SIZE=100
BATCH_TIMEOUT_SECONDS=5.0

# Rate Limiting
ENABLE_RATE_LIMITING=true
RATE_LIMIT_REQUESTS_PER_MINUTE=60

# Circuit Breaker
CIRCUIT_BREAKER_THRESHOLD=5
CIRCUIT_BREAKER_TIMEOUT_SECONDS=60
CIRCUIT_BREAKER_RECOVERY_TIMEOUT_SECONDS=30

# GPU
ENABLE_GPU=false
GPU_MEMORY_FRACTION=0.8
GPU_DEVICE_ID=0

# Observabilidade
OTEL_EXPORTER_ENDPOINT=http://otel-collector:4317
PROMETHEUS_PORT=9091
JAEGER_SAMPLING_RATE=0.1

# CORS
CORS_ORIGINS=["http://localhost:3000"]

# Autenticação
ENABLE_AUTH=false
JWT_SECRET_KEY=change-me-in-production
JWT_ALGORITHM=HS256
```

### Referência Completa

Ver `.env.example` para todas as variáveis disponíveis.

---

## Deploy Local

### 1. Clone e Setup

```bash
cd services/ml-inference-api
```

### 2. Criar Ambiente Virtual

```bash
python3.10 -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows
```

### 3. Instalar Dependências

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configurar Variáveis de Ambiente

```bash
cp .env.example .env
# Editar .env conforme necessário
```

### 5. Preparar Modelo ML

O modelo precisa estar disponível em `LOCAL_MODEL_PATH`:

```bash
mkdir -p ml_models
# Copiar modelo treinado para ml_models/
cp ../../ml_pipelines/models/nhm_approval_model.pkl ml_models/
```

### 6. Executar Serviço

```bash
# Modo desenvolvimento (com reload)
python -m src.main

# Modo produção
uvicorn src.main:app --host 0.0.0.0 --port 8010 --workers 4
```

### 7. Verificar Deploy

```bash
# Health check
curl http://localhost:8010/health

# Ver modelo carregado
curl http://localhost:8010/model-info

# Testar predição
curl -X POST http://localhost:8010/api/v1/inference/predict \
  -H "Content-Type: application/json" \
  -d '{"intent_text": "Create user account", "specialist_confidence": 0.7}'
```

---

## Deploy com Docker

### Build da Imagem

```bash
# Build local
docker build -t ml-inference-api:1.0.0 .

# Build com argumentos
docker build \
  --build-arg VERSION=1.0.0 \
  --build-arg GIT_COMMIT=$(git rev-parse --short HEAD) \
  --build-arg BUILD_DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ) \
  -t ml-inference-api:1.0.0 .
```

### Executar Container

```bash
# Básico
docker run -d \
  --name ml-inference-api \
  -p 8010:8010 \
  -p 9091:9091 \
  -v $(pwd)/ml_models:/app/ml_models \
  -e ENVIRONMENT=production \
  -e LOG_LEVEL=INFO \
  ml-inference-api:1.0.0

# Com todas as variáveis
docker run -d \
  --name ml-inference-api \
  -p 8010:8010 \
  -p 9091:9091 \
  -v $(pwd)/ml_models:/app/ml_models \
  -e ENVIRONMENT=production \
  -e LOG_LEVEL=INFO \
  -e MLFLOW_TRACKING_URI=http://mlflow:5000 \
  -e OTEL_EXPORTER_ENDPOINT=http://otel-collector:4317 \
  -e PROMETHEUS_PORT=9091 \
  -e ENABLE_RATE_LIMITING=true \
  -e RATE_LIMIT_REQUESTS_PER_MINUTE=60 \
  ml-inference-api:1.0.0
```

### Docker Compose

Exemplo de `docker-compose.yml`:

```yaml
version: '3.8'

services:
  ml-inference-api:
    build: .
    image: ml-inference-api:1.0.0
    container_name: ml-inference-api
    ports:
      - "8010:8010"   # API
      - "9091:9091"   # Metrics
    volumes:
      - ./ml_models:/app/ml_models:ro
    environment:
      ENVIRONMENT: production
      LOG_LEVEL: INFO
      MLFLOW_TRACKING_URI: http://mlflow:5000
      OTEL_EXPORTER_ENDPOINT: http://otel-collector:4317
      ENABLE_RATE_LIMITING: "true"
      RATE_LIMIT_REQUESTS_PER_MINUTE: "60"
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8010/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
```

Executar:

```bash
docker-compose up -d
```

### Logs e Debug

```bash
# Ver logs
docker logs ml-inference-api

# Follow logs
docker logs -f ml-inference-api

# Executar comando no container
docker exec -it ml-inference-api bash

# Verificar saúde
docker exec ml-inference-api curl http://localhost:8010/health
```

---

## Deploy Kubernetes (Helm)

### Pré-requisitos

- Kubernetes 1.24+
- Helm 3.0+
- kubectl configurado

### 1. Preparar Chart

O chart Helm está localizado em `./helm/ml-inference-api/`.

### 2. Configurar Values

Editar `helm/ml-inference-api/values.yaml` ou criar um override:

```yaml
# production-values.yaml
replicaCount: 3

image:
  repository: ghcr.io/albinojimy/ml-inference-api
  tag: "1.0.0"
  pullPolicy: IfNotPresent

resources:
  requests:
    cpu: 500m
    memory: 512Mi
  limits:
    cpu: 2000m
    memory: 2Gi

autoscaling:
  enabled: true
  minReplicas: 3
  maxReplicas: 20
  targetCPUUtilizationPercentage: 70

env:
  ENVIRONMENT: production
  LOG_LEVEL: INFO
  ENABLE_RATE_LIMITING: "true"
  RATE_LIMIT_REQUESTS_PER_MINUTE: "120"
```

### 3. Instalar Chart

```bash
# Instalar
helm install ml-inference-api ./helm/ml-inference-api \
  -f production-values.yaml \
  --namespace neural-hive-mind \
  --create-namespace

# Upgrade existente
helm upgrade ml-inference-api ./helm/ml-inference-api \
  -f production-values.yaml \
  --namespace neural-hive-mind
```

### 4. Verificar Deploy

```bash
# Ver pods
kubectl get pods -n neural-hive-mind -l app=ml-inference-api

# Ver serviço
kubectl get svc -n neural-hive-mind ml-inference-api

# Ver logs
kubectl logs -n neural-hive-mind -l app=ml-inference-api --tail=100 -f

# Port forward para teste
kubectl port-forward -n neural-hive-mind svc/ml-inference-api 8010:8010
```

### 5. Configurar Ingress (Opcional)

Habilitar ingress em `values.yaml`:

```yaml
ingress:
  enabled: true
  className: nginx
  hosts:
    - host: ml-inference.neural-hive.local
      paths:
        - path: /
          pathType: Prefix
  tls:
    - hosts:
        - ml-inference.neural-hive.local
      secretName: ml-inference-tls
```

### 6. HPA (Horizontal Pod Autoscaler)

O chart inclui HPA configurado:

```yaml
autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilizationPercentage: 70
  targetMemoryUtilizationPercentage: 80
```

Verificar HPA:

```bash
kubectl get hpa -n neural-hive-mind ml-inference-api
```

### 7. Pod Disruption Budget

Configurado para garantir disponibilidade:

```yaml
podDisruptionBudget:
  enabled: true
  minAvailable: 1
```

### 8. Secrets

Para ambientes de produção, usar Kubernetes Secrets:

```bash
# Criar secret
kubectl create secret generic ml-inference-secrets \
  -n neural-hive-mind \
  --from-literal=jwt_secret_key='seu-secret-aqui' \
  --from-literal=mlflow_tracking_password='senha-aqui'
```

Referenciar no `values.yaml`:

```yaml
env:
  JWT_SECRET_KEY:
    secretKeyRef:
      name: ml-inference-secrets
      key: jwt_secret_key
```

---

## Configuração de MLflow

### MLflow Local

```bash
# Iniciar MLflow
mlflow server \
  --backend-store-uri sqlite:///mlflow.db \
  --default-artifact-root ./mlflow-artifacts \
  --host 0.0.0.0 \
  --port 5000
```

Configurar variável:

```bash
export MLFLOW_TRACKING_URI=http://localhost:5000
```

### MLflow em Produção

```bash
# Com PostgreSQL backend
mlflow server \
  --backend-store-uri postgresql://user:pass@localhost/mlflow \
  --default-artifact-root s3://mlflow/artifacts \
  --host 0.0.0.0 \
  --port 5000
```

### Registrar Modelo

```python
import mlflow

# Set tracking URI
mlflow.set_tracking_uri("http://mlflow:5000")

# Log modelo
with mlflow.start_run():
    mlflow.sklearn.log_model(
        model,
        "model",
        registered_model_name="nhm_approval_model"
    )
```

### Carregar Modelo do MLflow

O serviço carrega automaticamente do MLflow se configurado:

```bash
MLFLOW_TRACKING_URI=http://mlflow:5000
MLFLOW_MODEL_NAME=nhm_approval_model
```

---

## GPU Support

### Pré-requisitos

- NVIDIA GPU com CUDA 11.8+
- nvidia-docker2 instalado
- Imagem Docker com suporte GPU

### Habilitar GPU

```bash
# Variáveis de ambiente
ENABLE_GPU=true
GPU_MEMORY_FRACTION=0.8
GPU_DEVICE_ID=0
```

### Docker com GPU

```bash
docker run -d \
  --name ml-inference-api \
  --gpus all \
  -p 8010:8010 \
  -e ENABLE_GPU=true \
  -e GPU_MEMORY_FRACTION=0.8 \
  ml-inference-api:1.0.0-gpu
```

### Kubernetes com GPU

```yaml
resources:
  requests:
    nvidia.com/gpu: 1
  limits:
    nvidia.com/gpu: 1

nodeSelector:
  accelerator: nvidia-gpu

tolerations:
  - key: nvidia.com/gpu
    operator: Exists
    effect: NoSchedule
```

---

## Troubleshooting

### Problemas Comuns

#### 1. Modelo Não Carrega

**Sintoma:** `/ready` retorna `ml_model: false`

**Solução:**

```bash
# Verificar caminho do modelo
ls -la $LOCAL_MODEL_PATH

# Verificar permissões
chmod 644 /app/ml_models/*.pkl

# Verificar logs
docker logs ml-inference-api | grep -i "model"
```

#### 2. Circuit Breaker Aberto

**Sintoma:** `/predict` retorna 503

**Diagnóstico:**

```bash
# Ver estado
curl http://localhost:8010/circuit-breaker

# Reset manual (admin)
curl -X POST http://localhost:8010/api/v1/inference/circuit-breaker/reset
```

**Solução:** Investigar causa raiz das falhas antes de resetar.

#### 3. Rate Limiting

**Sintoma:** HTTP 429

**Solução:**

```bash
# Aumentar limite
export RATE_LIMIT_REQUESTS_PER_MINUTE=120

# Ou desabilitar temporariamente
export ENABLE_RATE_LIMITING=false
```

#### 4. Alta Latência

**Diagnóstico:**

```bash
# Ver métricas
curl http://localhost:8010/metrics | grep prediction_duration

# Ver recursos
docker stats ml-inference-api
kubectl top pod -l app=ml-inference-api
```

**Soluções:**

- Aumentar recursos CPU/memória
- Habilitar GPU
- Implementar cache
- Ajustar batch size

#### 5. OOM (Out of Memory)

**Sintoma:** Container/Pod reinicia frequentemente

**Solução:**

```yaml
resources:
  limits:
    memory: 2Gi  # Aumentar limite
```

#### 6. Conexão MLflow Falha

**Sintoma:** Erro ao carregar modelo

**Solução:**

```bash
# Verificar conectividade
curl $MLFLOW_TRACKING_URI/health

# Verificar DNS
nslookup mlflow

# Usar fallback LOCAL_MODEL_PATH
```

### Logs Estruturados

Os logs estão em formato JSON com structlog:

```bash
# Filtrar por nível
docker logs ml-inference-api 2>&1 | grep '"level":"error"'

# Filtrar por evento
docker logs ml-inference-api 2>&1 | grep '"event":"prediction_failed"'

# Parse com jq
docker logs ml-inference-api 2>&1 | jq '. | select(.level == "error")'
```

### Health Checks

```bash
# Liveness
curl http://localhost:8010/health

# Readiness
curl http://localhost:8010/ready

# Detalhado
curl http://localhost:8010/model-info
curl http://localhost:8010/circuit-breaker
```

### Performance Tuning

| Parâmetro | Default | Recomendação Produção |
|-----------|---------|----------------------|
| `workers` | 1 | 4-8 |
| `BATCH_MAX_SIZE` | 100 | 50-100 |
| `RATE_LIMIT_REQUESTS_PER_MINUTE` | 60 | 120-300 |
| `CIRCUIT_BREAKER_THRESHOLD` | 5 | 10 |
| CPU limit | 1000m | 2000m+ |
| Memory limit | 1Gi | 2Gi+ |

---

## Checklist de Deploy Produção

- [ ] Configurar variáveis de ambiente production
- [ ] Usar secrets para dados sensíveis
- [ ] Configurar recursos adequados (CPU/memória)
- [ ] Habilitar HPA
- [ ] Configurar PDB
- [ ] Configurar probes (liveness/readiness)
- [ ] Habilitar ingress com TLS
- [ ] Configurar observabilidade (Prometheus/Jaeger)
- [ ] Testar circuit breaker
- [ ] Verificar rate limiting
- [ ] Configurar alertas
- [ ] Documentar procedimentos de rollback

---

## Links Relacionados

- [API Documentation](./API.md)
- [Development Guide](./DEVELOPMENT.md)
- [Metrics Documentation](./METRICS.md)
- [Helm Chart](../helm/ml-inference-api/README.md)
