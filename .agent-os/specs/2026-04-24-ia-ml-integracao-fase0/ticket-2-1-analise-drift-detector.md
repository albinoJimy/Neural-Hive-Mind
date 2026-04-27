# TICKET 2.1: Análise Completa do Drift Detector

**Data:** 2026-04-24
**Status:** COMPLETO
**Arquivos Analisados:**
- `services/orchestrator-dynamic/src/ml/drift_detector.py` (634 linhas)
- `libraries/python/neural_hive_specialists/drift_monitoring/drift_detector.py` (171 linhas)
- `libraries/python/neural_hive_ml/drift_detector.py` (556 linhas)

---

## Resumo Executivo

Existem **3 implementações diferentes** de drift detection no NHM:

1. **orchestrator-dynamic** - Detecção completa com PSI, MAE ratio, K-S test
2. **neural_hive_specialists** - Orquestrador com Evidently AI + alertas
3. **neural_hive_ml** - Focado em approval models (confidence, approve rate)

**Recomendação:** Usar **orchestrator-dynamic** como base para integração por ser mais completo e especializado para o domínio de orquestração.

---

## 1. API do DriftDetector (orchestrator-dynamic)

### 1.1 Construtor

```python
def __init__(
    self,
    config: OrchestratorSettings,
    mongodb_client: MongoDBClient,
    metrics: OrchestratorMetrics | None = None,
)
```

**Parâmetros:**
- `config`: Configurações do orchestrator (contém thresholds)
- `mongodb_client`: Cliente MongoDB async para queries
- `metrics`: Instância de métricas Prometheus (opcional)

### 1.2 Thresholds Configuráveis

| Threshold | Default | Descrição |
|-----------|---------|-----------|
| `ml_drift_psi_threshold` | 0.25 | PSI para feature drift significativo |
| `ml_drift_mae_ratio_threshold` | 1.5 | Ratio de degradação de predição |
| `ml_drift_ks_pvalue_threshold` | 0.05 | P-value para K-S test (target drift) |
| `ml_drift_check_window_days` | 7 | Janela de análise em dias |

**Config via settings:**
```python
# OrchestratorSettings
ml_drift_detection_enabled: bool = True
ml_drift_check_window_days: int = 7
ml_drift_psi_threshold: float = 0.25
ml_drift_mae_ratio_threshold: float = 1.5
ml_drift_ks_pvalue_threshold: float = 0.05
```

### 1.3 Métodos Principais

#### `detect_feature_drift(window_days: int = 7) -> dict[str, float]`
Detecta drift nas features de entrada usando PSI (Population Stability Index).

**Retorna:** Dict com PSI score por feature
```python
{
    "duration_ms": 0.15,
    "complexity": 0.08,
    "priority": 0.32  # > threshold = drift
}
```

#### `detect_prediction_drift(window_days: int = 7) -> dict[str, float]`
Detecta degradação de acurácia comparando MAE atual vs treino.

**Retorna:** Dict com MAE por janela e drift ratio
```python
{
    "mae_1d": 4500.0,
    "mae_3d": 4800.0,
    "mae_7d": 5100.0,
    "mae_training": 4000.0,
    "drift_ratio": 1.275  # > threshold = degradation
}
```

#### `detect_target_drift(window_days: int = 7) -> dict[str, Any]`
Detecta mudanças na distribuição do target usando Kolmogorov-Smirnov test.

**Retorna:** Dict com estatísticas K-S
```python
{
    "ks_statistic": 0.15,
    "p_value": 0.03,  # < threshold = drift
    "mean_shift_pct": 12.5,
    "std_shift_pct": 8.3,
    "baseline_mean": 50000.0,
    "recent_mean": 56250.0
}
```

#### `run_drift_check() -> dict[str, Any]`
**Método principal** - executa verificação completa de drift.

**Retorna:** Relatório consolidado
```python
{
    "timestamp": "2026-04-24T10:00:00Z",
    "window_days": 7,
    "feature_drift": {...},
    "prediction_drift": {...},
    "target_drift": {...},
    "overall_status": "warning",  # ok | warning | critical
    "recommendations": [
        "Feature drift detectado em complexity (PSI=0.320). Revisar distribuição.",
        "Acurácia degradou 27.5%. Monitorar e considerar retreinamento."
    ]
}
```

#### `save_feature_baseline(...) -> None`
Salva baseline de features para futuras comparações.

```python
await detector.save_feature_baseline(
    features_data=[...],  # Lista de features extraídas
    target_values=[...],  # Valores do target (actual_duration_ms)
    training_mae=4000.0,
    model_name="duration-predictor",
    version="v7"
)
```

---

## 2. API do DriftDetector (neural_hive_specialists)

### 2.1 Construtor

```python
def __init__(
    self,
    config: dict[str, Any],
    evidently_monitor: EvidentlyMonitor,
    drift_alerter: DriftAlerter,
    ledger_client: Any,
)
```

**Parâmetros:**
- `config`: Dict com configurações (window_hours, threshold_psi)
- `evidently_monitor`: Monitor Evidently AI
- `drift_alerter`: Alerter para Slack/Alertmanager
- `ledger_client`: Cliente MongoDB para persistência

### 2.2 Configurações

```python
self.window_hours = config.get("drift_detection_window_hours", 24)
self.threshold_psi = config.get("drift_threshold_psi", 0.2)
self.check_interval_minutes = config.get("drift_check_interval_minutes", 60)
```

### 2.3 Métodos Principais

#### `start_monitoring()`
Inicia loop periódico de verificação (background task).

#### `stop_monitoring()`
Para o loop de monitoramento.

#### `check_drift() -> dict[str, Any]`
Executa verificação de drift usando Evidently AI.

```python
{
    "drift_detected": True,
    "drift_score": 0.4,  # PSI
    "drifted_features": ["f1", "f2"],
    "report": {...},  # Relatório Evidently completo
    "timestamp": "2026-04-24T10:00:00Z"
}
```

#### `log_evaluation_features(features: dict[str, Any])`
Registra features de uma avaliação para monitoramento.

---

## 3. API do DriftDetector (neural_hive_ml)

### 3.1 Foco
Específico para **approval models** - monitora confidence e approve rate.

### 3.2 Construtor

```python
def __init__(
    self,
    mongo_client: AsyncIOMotorDatabase,
    kafka_producer: Any,
    confidence_threshold: float = 0.10,
    approve_rate_threshold: float = 0.15,
    baseline_window_hours: int = 168,  # 7 dias
)
```

### 3.3 Métodos Principais

#### `detect_drift(window_hours: int = 168) -> dict[str, Any]`
```python
{
    "model_version": "v7",
    "window_hours": 168,
    "baseline": {
        "approve_rate": 0.65,
        "avg_confidence": 0.72,
        "sample_count": 1000
    },
    "current": {
        "approve_rate": 0.58,
        "avg_confidence": 0.65,
        "sample_count": 200
    },
    "drift_detected": True,
    "alerts": [
        {
            "metric": "avg_confidence",
            "change": -0.07,
            "threshold": 0.10,
            "severity": "warning"
        }
    ]
}
```

---

## 4. Comparação das Implementações

| Aspecto | orchestrator-dynamic | neural_hive_specialists | neural_hive_ml |
|---------|---------------------|------------------------|----------------|
| **Framework** | Scipy/numpy puro | Evidently AI | MongoDB aggregation |
| **Tipo de Drift** | Feature, Prediction, Target | Feature (PSI via Evidently) | Approval (confidence, rate) |
| **Persistência** | MongoDB (ml_feature_baselines) | MongoDB (drift_monitoring) | MongoDB (plan_approvals) |
| **Alertas** | Logger + Prometheus | Slack + Alertmanager | Kafka (ml.model_drift_detected) |
| **Monitoring** | Manual check | Loop periódico automático | Manual check |
| **Métricas** | Integrado com OrchestratorMetrics | Independente | Independente |
| **Baselines** | Salva durante treinamento | Carrega de parquet | Calcula on-demand |
| **Testes** | Não identificados | 9 testes em test_drift_detector.py | Testes em test_drift_detector.py |

---

## 5. Fluxo de Detecção (orchestrator-dynamic)

```
┌─────────────────────────────────────────────────────────────────┐
│                    run_drift_check()                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. detect_feature_drift()  ───► PSI por feature              │
│     ├── Query execution_tickets (7 dias)                       │
│     ├── Extract features de cada ticket                         │
│     ├── Carregar baseline (ml_feature_baselines)               │
│     └── Calcular PSI para cada feature                          │
│         PSI = sum((actual - expected) * ln(actual/expected))    │
│                                                                  │
│  2. detect_prediction_drift()  ───► MAE ratio                  │
│     ├── Query tickets com predictions                          │
│     ├── Calcular MAE por janela (1d, 3d, 7d)                    │
│     ├── Obter training MAE do baseline                         │
│     └── drift_ratio = current_mae / training_mae               │
│                                                                  │
│  3. detect_target_drift()  ───► K-S test                       │
│     ├── Query actual_duration_ms (7 dias)                      │
│     ├── Carregar distribuição baseline                          │
│     └── scipy.stats.ks_2samp(baseline, recent)                 │
│         Retorna: ks_statistic, p_value                         │
│                                                                  │
│  4. _determine_overall_status()  ───► ok | warning | critical  │
│     ├── CRITICAL: mae_ratio > 1.5 OR psi_features > 3         │
│     ├── WARNING: mae_ratio > 1.2 OR any psi > 0.1             │
│     └── OK: nenhum threshold excedido                          │
│                                                                  │
│  5. _generate_recommendations()                                 │
│     └── Mensagens baseadas nos drifts detectados               │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 6. Fórmulas de Drift

### 6.1 PSI (Population Stability Index)

```python
PSI = sum((actual_pct - expected_pct) * ln(actual_pct / expected_pct))

# Interpretação
PSI < 0.1:     Sem drift
0.1 <= PSI < 0.2:  Drift leve
PSI >= 0.2:    Drift significativo (default threshold: 0.25)
```

### 6.2 MAE Ratio

```python
drift_ratio = current_mae / training_mae

# Interpretação
drift_ratio < 1.2:  OK
1.2 <= ratio < 1.5: WARNING (degradação até 50%)
ratio >= 1.5:       CRITICAL (degradação > 50%)
```

### 6.3 Kolmogorov-Smirnov Test

```python
ks_statistic, p_value = stats.ks_2samp(baseline_durations, recent_durations)

# Interpretação
p_value >= 0.05: Distribuições similares (sem drift)
p_value < 0.05:  Distribuições diferentes (drift detectado)
```

---

## 7. Integração com Prometheus

### 7.1 Métricas Existentes (OrchestratorMetrics)

```python
# Gauges
ml_drift_score.labels(drift_type, feature, model_name).set(score)
ml_drift_status.labels(model_name, drift_type).set(status)  # 0=ok, 1=warning, 2=critical

# Método helper
metrics.record_drift_score(
    drift_type="feature",  # ou "prediction", "target"
    score=0.32,
    feature="complexity",
    model_name="duration-predictor"
)

metrics.update_drift_status(
    model_name="duration-predictor",
    drift_type="overall",
    status="warning"  # ok | warning | critical
)
```

---

## 8. Coleções MongoDB

### 8.1 ml_feature_baselines
```javascript
{
  "_id": ObjectId("..."),
  "model_name": "duration-predictor",
  "version": "v7",
  "timestamp": ISODate("2026-04-17T10:00:00Z"),
  "features": {
    "duration_ms": {
      "values": [45000, 50000, 55000, ...],
      "mean": 50000.0,
      "std": 15000.0,
      "min": 10000.0,
      "max": 120000.0
    },
    "complexity": {...}
  },
  "target_distribution": {
    "values": [40000, 45000, 50000, ...],
    "mean": 50000.0,
    "std": 15000.0,
    "percentiles": {"p50": 48000, "p95": 85000, "p99": 110000}
  },
  "training_mae": 4000.0,
  "sample_count": 1000
}
```

### 8.2 drift_monitoring (neural_hive_specialists)
```javascript
{
  "type": "drift_detection",
  "timestamp": ISODate("2026-04-24T10:00:00Z"),
  "drift_detected": true,
  "drift_score": 0.4,
  "drifted_features": ["anomaly_score", "risk_weight"],
  "threshold_psi": 0.2,
  "window_hours": 24,
  "report_summary": {
    "num_drifted_features": 2,
    "timestamp": "2026-04-24T10:00:00Z"
  }
}
```

---

## 9. Recomendações para Integração

### 9.1 Qual Implementação Usar?

**Usar `orchestrator-dynamic/src/ml/drift_detector.py` como base porque:**

1. **Completo**: Detecta 3 tipos de drift (feature, prediction, target)
2. **Integrado**: Já usa OrchestratorMetrics para Prometheus
3. **Async**: Totalmente async com motor (MongoDB async)
4. **Especializado**: Focado em orquestração (duration prediction)
5. **Configurável**: Thresholds via OrchestratorSettings

### 9.2 O Que Falta para Integração Completa?

1. **Chamada periódica**: Adicionar scheduler para `run_drift_check()`
2. **Alertas**: Integrar com DriftAlerter (neural_hive_specialists)
3. **Auto-retrain**: Conectar com ml_pipelines/monitoring/auto_retrain.py
4. **Dashboard**: Criar dashboard Grafana com métricas `ml_drift_*`

### 9.3 Padrão de Uso Recomendado

```python
# No decision_consumer.py ou scheduler
from src.ml.drift_detector import DriftDetector

detector = DriftDetector(
    config=settings,
    mongodb_client=mongo_client,
    metrics=metrics
)

# Verificação manual (em cada decisão ou batch)
report = await detector.run_drift_check()

if report["overall_status"] != "ok":
    logger.warning(
        "Drift detected",
        status=report["overall_status"],
        recommendations=report["recommendations"]
    )
    # Trigger auto-retrain se critical
    if report["overall_status"] == "critical":
        await trigger_retrain_pipeline(report)
```

---

## 10. Próximos Passos (TICKET 2.2)

1. Integrar DriftDetector no `decision_consumer.py`
2. Criar reference data inicial para approval model v7
3. Adicionar métricas de drift ao Prometheus existente
4. Implementar loop periódico de verificação
5. Testes E2E de drift detection

---

**Fim do Relatório**
