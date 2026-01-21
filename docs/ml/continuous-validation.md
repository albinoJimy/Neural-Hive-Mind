# Continuous Validation - Guia de Uso

## Visão Geral

O sistema de validação contínua monitora modelos ML em produção, comparando predições com outcomes reais e calculando métricas de performance em janelas temporais.

## Arquitetura

```
┌─────────────┐     ┌───────────────────┐     ┌─────────────┐
│  Predictor  │────▶│ ContinuousValidator│────▶│  MongoDB    │
└─────────────┘     └───────────────────┘     └─────────────┘
       │                     │                       │
       │                     ▼                       │
       │            ┌───────────────┐                │
       └───────────▶│  Prometheus   │◀───────────────┘
                    └───────────────┘
                           │
                           ▼
                    ┌───────────────┐
                    │   Grafana     │
                    └───────────────┘
```

### Fluxo de Dados

1. **Predictor** faz predição e registra via `record_prediction()`
2. **ContinuousValidator** armazena predição em buffer pendente
3. Quando execução completa, **record_actual()** é chamado
4. Validator calcula erro e adiciona às janelas temporais
5. Resultado é persistido no **MongoDB** (collection `model_predictions`)
6. Métricas são emitidas para **Prometheus**

## Métricas Coletadas

### Métricas de Predição (por janela: 1h, 24h, 7d)

| Métrica | Descrição |
|---------|-----------|
| **MAE** | Mean Absolute Error - Erro médio absoluto em ms |
| **MAE %** | Erro percentual relativo à média |
| **RMSE** | Root Mean Squared Error - Raiz do erro quadrático médio |
| **MAPE** | Mean Absolute Percentage Error - Erro percentual médio |
| **R²** | Coeficiente de Determinação - Qualidade do ajuste (0-1) |

### Métricas de Latência (por janela: 1h, 24h, 7d)

| Métrica | Descrição |
|---------|-----------|
| **p50** | Latência mediana em ms |
| **p95** | Latência do percentil 95 em ms |
| **p99** | Latência do percentil 99 em ms |
| **error_rate** | Taxa de erros (0-1) |

## Configuração

### Variáveis de Ambiente

```bash
# Habilitar validação contínua
ML_CONTINUOUS_VALIDATION_ENABLED=true

# Usar MongoDB como fonte primária
ML_VALIDATION_USE_MONGODB=true
ML_VALIDATION_MONGODB_COLLECTION=model_predictions

# Janelas temporais
ML_VALIDATION_WINDOWS=1h,24h,7d

# Habilitar métricas adicionais
ML_VALIDATION_LATENCY_ENABLED=true
ML_VALIDATION_R2_ENABLED=true

# Thresholds
ML_VALIDATION_MAE_THRESHOLD=0.15  # 15%
ML_VALIDATION_ALERT_COOLDOWN_MINUTES=30

# Intervalo de verificação
ML_VALIDATION_CHECK_INTERVAL_SECONDS=300  # 5 minutos
```

### Settings (Python)

```python
# services/orchestrator-dynamic/src/config/settings.py

ml_continuous_validation_enabled: bool = True
ml_validation_check_interval_seconds: int = 300
ml_validation_use_mongodb: bool = True
ml_validation_mongodb_collection: str = 'model_predictions'
ml_validation_windows: List[str] = ['1h', '24h', '7d']
ml_validation_alert_cooldown_minutes: int = 30
ml_validation_latency_enabled: bool = True
ml_validation_r2_enabled: bool = True
```

## Uso Programático

### Registrar Predição

```python
from src.ml.continuous_validator import ContinuousValidator

validator = ContinuousValidator(config=settings, mongodb_client=mongodb)

# Registrar predição com latência
validator.record_prediction(
    ticket_id="ticket-123",
    predicted_duration_ms=5000.0,
    model_version="v1.2.3",
    prediction_latency_ms=45.2  # Latência da inferência
)
```

### Registrar Outcome Real

```python
# Quando execução completar
result = await validator.record_actual(
    ticket_id="ticket-123",
    actual_duration_ms=5200.0,
    had_error=False
)

# result contém: ticket_id, predicted, actual, error_ms, error_pct, etc.
```

### Obter Métricas Atuais

```python
metrics = validator.get_current_metrics()

# Métricas de predição
mae_24h = metrics['prediction_metrics']['24h']['mae']
r2_24h = metrics['prediction_metrics']['24h']['r2']

# Métricas de latência
p95_24h = metrics['latency_metrics']['24h']['p95']
error_rate_24h = metrics['latency_metrics']['24h']['error_rate']
```

### Iniciar Validação Contínua

```python
# Inicia loop de validação em background
await validator.start_continuous_validation(
    check_interval_seconds=300  # 5 minutos
)

# Para parar
await validator.stop_continuous_validation()
```

## CronJob

O CronJob `continuous-validation-collector` executa a cada hora para popular janelas do MongoDB e publicar métricas.

### Comandos Úteis

```bash
# Verificar status
kubectl get cronjobs -n neural-hive-orchestration continuous-validation-collector

# Ver logs do último job
kubectl logs -n neural-hive-orchestration \
  $(kubectl get pods -n neural-hive-orchestration \
    -l job-name --sort-by=.metadata.creationTimestamp \
    -o jsonpath='{.items[-1].metadata.name}')

# Executar manualmente
kubectl create job --from=cronjob/continuous-validation-collector \
  manual-validation-$(date +%s) -n neural-hive-orchestration
```

### Arquivo CronJob

```yaml
# k8s/cronjobs/continuous-validation-job.yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: continuous-validation-collector
  namespace: neural-hive-orchestration
spec:
  schedule: "0 * * * *"  # A cada hora
  ...
```

## Alertas

### Degradação de Acurácia

Disparado quando MAE % excede threshold (15%):

```yaml
alert: MLModelAccuracyDegraded
expr: neural_hive_validation_mae_pct{window="24h"} > 15
for: 10m
severity: warning
```

### Latência Alta

Disparado quando p95 excede 100ms:

```yaml
alert: MLModelHighLatency
expr: neural_hive_validation_latency_p95{window="24h"} > 100
for: 5m
severity: warning
```

## Schema MongoDB

### Collection: `model_predictions`

```javascript
{
  _id: ObjectId("..."),
  ticket_id: "ticket-123",
  model_name: "duration-predictor",
  predicted: 5000.0,
  actual: 5200.0,
  error_ms: 200.0,
  error_pct: 4.0,
  latency_ms: 45.2,
  had_error: false,
  model_version: "v1.2.3",
  prediction_timestamp: ISODate("2026-01-21T10:00:00Z"),
  validation_timestamp: ISODate("2026-01-21T10:05:00Z"),
  timestamp: ISODate("2026-01-21T10:05:00Z")
}
```

### Índices

```javascript
// Executar: scripts/mongodb/create_continuous_validation_indexes.js

// Índice para queries de janela temporal
db.model_predictions.createIndex(
  { model_name: 1, timestamp: -1, actual: 1 },
  { name: 'idx_model_timestamp_actual' }
);

// Índice para ticket_id
db.model_predictions.createIndex(
  { ticket_id: 1 },
  { name: 'idx_ticket_id' }
);

// TTL 90 dias
db.model_predictions.createIndex(
  { timestamp: 1 },
  { expireAfterSeconds: 7776000, name: 'idx_ttl_90days' }
);
```

## Troubleshooting

### Métricas não aparecem

1. Verificar se MongoDB está acessível
2. Verificar se collection `model_predictions` existe
3. Verificar logs do CronJob
4. Verificar se Pushgateway está acessível

```bash
# Verificar conexão MongoDB
kubectl exec -it -n neural-hive-orchestration deployment/orchestrator-dynamic -- \
  python -c "from motor.motor_asyncio import AsyncIOMotorClient; print('OK')"

# Verificar Pushgateway
curl http://prometheus-pushgateway.monitoring.svc.cluster.local:9091/metrics
```

### Dados insuficientes

- Aguardar acúmulo de predições (mínimo 10 por janela)
- Verificar se `record_actual()` está sendo chamado
- Verificar TTL do MongoDB (90 dias)

```python
# Verificar quantidade de dados
from motor.motor_asyncio import AsyncIOMotorClient
client = AsyncIOMotorClient(MONGODB_URI)
db = client['neural_hive_orchestration']
count = await db['model_predictions'].count_documents({})
print(f"Total de predições: {count}")
```

### Fallback para In-Memory

Se MongoDB estiver indisponível, o sistema usa automaticamente fallback in-memory:

```python
# No log aparecerá:
# "mongodb_disabled_using_in_memory"

# Métricas continuarão funcionando, mas não serão persistidas
```

## Integração com ModelPromotionManager

O `ModelPromotionManager` usa métricas do validador contínuo para decisões de promoção:

```python
# services/orchestrator-dynamic/src/ml/model_promotion.py

async def _collect_current_metrics(self, model_name: str) -> Dict[str, float]:
    current_metrics = self.continuous_validator.get_current_metrics()

    prediction_metrics = current_metrics.get('prediction_metrics', {})
    window_24h = prediction_metrics.get('24h', {})

    latency_metrics = current_metrics.get('latency_metrics', {})
    latency_24h = latency_metrics.get('24h', {})

    return {
        'mae': window_24h.get('mae'),
        'mae_pct': window_24h.get('mae_pct'),
        'r2': window_24h.get('r2'),
        'latency_p95': latency_24h.get('p95'),
        'error_rate': latency_24h.get('error_rate')
    }
```

## Métricas Prometheus

As seguintes métricas são exportadas:

```promql
# Métricas de predição
neural_hive_validation_mae{window="24h", model="duration-predictor"}
neural_hive_validation_mae_pct{window="24h", model="duration-predictor"}
neural_hive_validation_r2{window="24h", model="duration-predictor"}
neural_hive_validation_sample_count{window="24h", model="duration-predictor"}

# Métricas de latência
neural_hive_validation_latency_p50{window="24h", model="duration-predictor"}
neural_hive_validation_latency_p95{window="24h", model="duration-predictor"}
neural_hive_validation_latency_p99{window="24h", model="duration-predictor"}
neural_hive_validation_latency_error_rate{window="24h", model="duration-predictor"}
```
