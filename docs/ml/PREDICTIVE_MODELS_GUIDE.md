# Guia de Modelos Preditivos - Neural Hive-Mind

## 📋 Visão Geral

O Neural Hive-Mind utiliza 3 modelos preditivos centralizados para otimizar scheduling e detecção de anomalias:

1. **SchedulingPredictor** - Prediz duração e recursos de tickets
2. **LoadPredictor** - Prevê carga futura do sistema (60min, 6h, 24h)
3. **AnomalyDetector** - Detecta tickets anômalos

## 🏗️ Arquitetura

```mermaid
graph TD
    A[Cognitive Plan] --> B[Orchestrator Dynamic]
    B --> C[IntelligentScheduler]
    C --> D[SchedulingPredictor]
    C --> E[AnomalyDetector]
    C --> F[LoadPredictor]
    D --> G[MLflow Registry]
    E --> G
    F --> G
    G --> H[MongoDB Historical Data]
    G --> I[ClickHouse Analytics]
```

## 📊 Modelos Registrados

### SchedulingPredictor

- **Algoritmo:** XGBoost Regressor
- **Features:** 20 features (risk_weight, capabilities_count, qos_priority, etc.)
- **Métricas:**
  - MAE < 1000ms
  - MAPE < 15%
  - R² > 0.75
- **Uso:** Prediz `predicted_duration_ms` e `cpu_cores`/`memory_mb`

### LoadPredictor

- **Algoritmo:** Prophet (time-series forecasting)
- **Horizontes:** 60min, 360min, 1440min
- **Métricas:**
  - MAPE < 20%
  - MAE < 10 tickets
- **Uso:** Prevê carga futura para capacity planning
- **Dados:** Usa registros reais do ClickHouse/MongoDB quando disponíveis (fallback sintético se <1000 amostras)

### AnomalyDetector

- **Algoritmo:** Isolation Forest
- **Contamination:** 5% (taxa esperada de anomalias)
- **Métricas:**
  - F1-score > 0.65
  - Precision > 0.70
  - Recall > 0.60
- **Uso:** Detecta tickets com padrões anômalos

## 🔄 Pipeline de Treinamento

### Treinamento Automático (CronJob)

- **Frequência:** Semanal (domingos 2 AM UTC)
- **Duração:** ~10-20 minutos
- **Dados:** Últimos 18 meses (540 dias)
- **Auto-promoção:** Modelos promovidos se métricas melhorarem >5%

### Treinamento Manual

```bash
kubectl create job --from=cronjob/predictive-models-training \
  manual-training-$(date +%Y%m%d-%H%M%S) \
  -n neural-hive-ml
```

## 📈 Monitoramento

### Métricas Prometheus

- `orchestration_ml_prediction_duration_seconds` - Latência de predições (histograma por modelo)
- `orchestration_ml_predictions_total` - Contagem de predições por modelo/status
- `orchestration_ml_anomalies_detected_total` - Total de anomalias detectadas
- `orchestration_ml_prediction_cache_hits_total` - Hits de cache de predições/forecasts
- `orchestration_ml_model_accuracy` - Métricas de acurácia (gauges por modelo/metric_type)

### Alertas

- **MLTrainingJobFailed** - Job de treinamento falhou
- **MLTrainingJobTookTooLong** - Job rodando >2h
- **PredictionLatencyHigh** - P95 latency >100ms
- **AnomalyRateHigh** - Taxa de anomalias >10%

## 🔧 Troubleshooting

### Modelos não carregam no Orchestrator

1. Verificar se modelos estão em Production:
   ```bash
   ./ml_pipelines/training/validate_model_promotion.sh
   ```

2. Verificar logs do Orchestrator:
   ```bash
   kubectl logs -n semantic-translation -l app=orchestrator-dynamic | grep -i "predictor"
   ```

3. Verificar MLflow acessível:
   ```bash
   kubectl port-forward -n mlflow svc/mlflow 5000:5000
   curl http://localhost:5000/health
   ```

### Predições com baixa confiança

- **Causa:** Dados históricos insuficientes
- **Solução:** Aguardar acúmulo de dados (mínimo 1000 tickets)

### Taxa de anomalias muito alta (>10%)

- **Causa:** Threshold muito sensível
- **Solução:** Ajustar `contamination` em `anomaly_detector.py` (linha 44)

## 📚 Referências

- Pipeline de treinamento: `file:ml_pipelines/training/train_predictive_models.py`
- Modelos: `file:libraries/python/neural_hive_ml/predictive_models/`
- Scheduler: `file:services/orchestrator-dynamic/src/scheduler/intelligent_scheduler.py`
- Testes E2E: `file:tests/e2e/test_predictive_models_e2e.py`
