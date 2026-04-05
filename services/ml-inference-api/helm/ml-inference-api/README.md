# ML Inference API Helm Chart

Helm chart para o serviço de inferência ML do Neural Hive-Mind.

## Descrição

O ML Inference API é responsável por:
- Servir modelos ML via REST API
- Integrar com MLflow para model registry
- Suportar batch inference
- Fornecer métricas Prometheus
- Suporte opcional a GPU

## Instalação

```bash
# Instalar com valores padrão
helm install ml-inference-api ./helm/ml-inference-api

# Instalar com valores personalizados
helm install ml-inference-api ./helm/ml-inference-api -f custom-values.yaml

# Instalar em namespace específico
helm install ml-inference-api ./helm/ml-inference-api --namespace ml-systems --create-namespace
```

## Configuração

### Configurações Importantes

| Parâmetro | Descrição | Default |
|-----------|-----------|---------|
| `replicaCount` | Número de réplicas iniciais | `2` |
| `image.repository` | Repository da imagem Docker | `ml-inference-api` |
| `image.tag` | Tag da imagem Docker | `1.0.0` |
| `service.ports.http` | Porta do serviço HTTP | `8008` |
| `service.ports.metrics` | Porta das métricas Prometheus | `9098` |

### GPU Support

Para habilitar suporte a GPU:

```yaml
gpuResources:
  enabled: true
  nvidiaComGpu: "1"
```

### MLflow Configuration

```yaml
env:
  MLFLOW_TRACKING_URI: http://mlflow:5000
  MLFLOW_MODEL_NAME: nhm_approval_model
  LOCAL_MODEL_PATH: /app/ml_models
```

### Secrets

Configure os secrets sensíveis:

```yaml
secrets:
  jwt_secret_key: "your-secret-key"
  mlflow_tracking_password: "mlflow-password"
  s3_access_key: "your-access-key"
  s3_secret_key: "your-secret-key"
```

## Endpoints

- `GET /health` - Health check
- `GET /ready` - Readiness probe
- `GET /metrics` - Métricas Prometheus
- `POST /api/v1/predict` - Inferência batch
- `GET /api/v1/models` - Listar modelos disponíveis

## Escalabilidade

O HPA está configurado para escalar automaticamente:

```yaml
autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilizationPercentage: 70
  targetMemoryUtilizationPercentage: 80
```

## Monitorização

O serviço expõe métricas em `/metrics` na porta configurada (default: 9098).

Métricas disponíveis:
- Taxa de requests
- Latência de inferência
- Taxa de erros
- Utilização de GPU (se aplicável)
- Batch size statistics

## Upgrade

```bash
helm upgrade ml-inference-api ./helm/ml-inference-api
```

## Uninstall

```bash
helm uninstall ml-inference-api
```
