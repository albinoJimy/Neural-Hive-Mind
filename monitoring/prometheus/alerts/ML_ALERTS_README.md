# ML Alerts - Prometheus Alert Rules

## Overview

Arquivo de alertas Prometheus para monitoramento do pipeline ML do Neural Hive Mind.
Implementação do **EPIC 4.4** da especificação FASE 0 - IA/ML Integration.

**Arquivo:** `ml_alerts.yml`
**Ref:** `.agent-os/specs/2026-04-24-ia-ml-integracao-fase0/spec.md`

## Grupos de Alertas

### 1. ml_model_health
Alertas relacionados à saúde do modelo em produção.

| Alerta | Severidade | Threshold | Duração | Descrição |
|--------|------------|-----------|---------|-----------|
| `MLModelAccuracyLow` | warning | accuracy < 0.8 | 5m | Acurácia do modelo abaixo de 80% |

**Métricas utilizadas:**
- `approval_service_approvals_total{result="approved"}`

### 2. ml_drift_detection
Alertas para detecção de drift nos dados/modelos.

| Alerta | Severidade | Threshold | Duração | Descrição |
|--------|------------|-----------|---------|-----------|
| `MLModelDriftDetected` | critical | drift_score > 0.5 | 2m | Drift detectado no modelo |
| `MLModelDriftStatusCritical` | critical | drift_status >= 2 | 1m | Status de drift crítico |
| `MLModelDriftRateHigh` | warning | rate > 0.1/min | 10m | Alta taxa de drifts |

**Métricas utilizadas:**
- `orchestration_ml_drift_score`
- `orchestration_ml_drift_status`
- `ml_drift_detected_total`

### 3. ml_training_pipeline
Alertas para pipeline de treinamento e retrain.

| Alerta | Severidade | Threshold | Duração | Descrição |
|--------|------------|-----------|---------|-----------|
| `MLRetrainFailed` | critical | failed > 0 | 1m | Job de retrain falhou |
| `MLModelPromotionFailed` | critical | failed > 0 | 5m | Promoção de modelo falhou |
| `MLTrainingJobStuck` | warning | running > 0 | 30m | Job travado |

**Métricas utilizadas:**
- `orchestration_ml_training_jobs_total{status="failed"}`
- `orchestration_ml_model_promotion_total{result="failed"}`
- `orchestration_ml_training_jobs_total{status="running"}`

### 4. ml_shadow_mode
Alertas para modo shadow de modelos.

| Alerta | Severidade | Threshold | Duração | Descrição |
|--------|------------|-----------|---------|-----------|
| `MLShadowModeDisagreementHigh` | warning | agreement < 0.7 | 15m | Baixa taxa de agreement |
| `MLShadowComparisonErrors` | warning | errors > 0.1/s | 10m | Erros na comparação |

**Métricas utilizadas:**
- `neural_hive_shadow_agreement_rate`
- `neural_hive_shadow_comparison_errors_total`

### 5. ml_prediction_cache
Alertas para cache de predições.

| Alerta | Severidade | Threshold | Duração | Descrição |
|--------|------------|-----------|---------|-----------|
| `MLPredictionCacheMissRateHigh` | info | cache hit < 50% | 15m | Baixa taxa de cache hit |

**Métricas utilizadas:**
- `orchestration_ml_prediction_cache_hits_total`

## Instalação

### 1. Configurar Prometheus

Adicionar ao `prometheus.yml`:

```yaml
rule_files:
  - '/etc/prometheus/alerts/ml_alerts.yml'
```

### 2. Reiniciar Prometheus

```bash
kubectl rollout restart deployment prometheus -n monitoring
```

Ou via Docker Compose:

```bash
docker-compose restart prometheus
```

### 3. Verificar Alertas

Acessar o Prometheus UI e verificar em "Alerts" que todos os alertas ML estão carregados.

## Labels Comuns

Todos os alertas incluem os labels:
- `severity`: warning, critical, info
- `service`: ml-pipeline
- `component`: approval-service, drift-detector, training, model-promotion, shadow-mode, cache

## Roteamento

Configurar roteamento no Alertmanager para enviar alertas para:
- Slack: severity=warning
- PagerDuty: severity=critical
- Email: Todos os alertas

## Teste

### Simular Drift

```python
from neural_hive_observability.metrics import MetricsRegistry

metrics = MetricsRegistry()
metrics.ml_drift_score.labels(
    drift_type="psi",
    feature="nlp_features",
    model_name="approval_v7"
).set(0.6)  # Acima de 0.5
```

### Simular Falha de Retrain

```python
metrics.ml_training_jobs_total.labels(
    status="failed",
    trigger="drift_detected"
).inc()
```

## Referências

- Spec: `.agent-os/specs/2026-04-24-ia-ml-integracao-fase0/spec.md`
- Métricas: `services/orchestrator-dynamic/src/observability/metrics.py`
- Prometheus: https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/
