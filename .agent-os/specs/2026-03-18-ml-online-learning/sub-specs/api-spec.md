# API Specification

This is the API specification for the spec detailed in @.agent-os/specs/2026-03-18-ml-online-learning/spec.md

## Overview

Nova API REST no approval-service para gestão de modelos de ML: retreinamento, versionamento, promoção e monitoramento de drift.

## Endpoints

### POST /api/v1/ml/retrain

**Purpose:** Forçar retreinamento manual do modelo

**Request Body:**
```json
{
  "force": false,           // true ignora threshold de dados
  "samples_override": null  // null usa todos os dados disponíveis
}
```

**Response:** 202 Accepted
```json
{
  "job_id": "retrain-20260318-143052",
  "status": "queued",
  "estimated_samples": 523,
  "message": "Retraining job queued"
}
```

**Errors:**
- 400 Bad Request - Se já existe job em andamento
- 503 Service Unavailable - Se MLflow não está disponível

---

### GET /api/v1/ml/retrain/{job_id}

**Purpose:** Status do job de retreinamento

**Response:** 200 OK
```json
{
  "job_id": "retrain-20260318-143052",
  "status": "completed",  // queued | running | completed | failed
  "started_at": "2026-03-18T14:30:52Z",
  "completed_at": "2026-03-18T14:52:17Z",
  "result": {
    "version": "v9",
    "f1_score": 0.78,
    "accuracy": 0.84,
    "n_samples": 523,
    "mlflow_run_id": "abc123-def456"
  }
}
```

**Errors:**
- 404 Not Found - Job não existe

---

### GET /api/v1/ml/models

**Purpose:** Listar versões de modelos registradas

**Query Parameters:**
- `stage` (optional) - Filter by stage: staging | production | archived
- `limit` (optional) - Default 20
- `offset` (optional) - Default 0

**Response:** 200 OK
```json
{
  "models": [
    {
      "version": "v9",
      "stage": "staging",
      "is_active": false,
      "f1_score": 0.78,
      "accuracy": 0.84,
      "n_samples": 523,
      "created_at": "2026-03-18T14:52:17Z",
      "mlflow_run_id": "abc123-def456"
    },
    {
      "version": "v8",
      "stage": "production",
      "is_active": true,
      "f1_score": 0.73,
      "accuracy": 0.80,
      "n_samples": 485,
      "created_at": "2026-03-16T10:00:00Z",
      "promoted_at": "2026-03-16T12:00:00Z"
    }
  ],
  "total": 8,
  "limit": 20,
  "offset": 0
}
```

---

### GET /api/v1/ml/models/{version}

**Purpose:** Detalhes de uma versão específica

**Response:** 200 OK
```json
{
  "version": "v8",
  "stage": "production",
  "is_active": true,
  "f1_score": 0.73,
  "accuracy": 0.80,
  "precision": 0.76,
  "recall": 0.70,
  "n_samples": 485,
  "feature_importance": {
    "confidence": 0.6147,
    "rf_ml_risk": 0.2221,
    "rf_ml_confidence": 0.1632
  },
  "created_at": "2026-03-16T10:00:00Z",
  "promoted_at": "2026-03-16T12:00:00Z",
  "promoted_by": "canary",
  "mlflow_run_id": "xyz789-abc456",
  "drift_metrics": {
    "last_check": "2026-03-18T14:00:00Z",
    "confidence_drop": 0.02,
    "approve_rate_change": 0.05
  }
}
```

**Errors:**
- 404 Not Found - Versão não existe

---

### POST /api/v1/ml/models/{version}/promote

**Purpose:** Promover modelo para production (manual override)

**Request Body:**
```json
{
  "strategy": "immediate"  // immediate | canary
}
```

**Response:** 200 OK
```json
{
  "version": "v9",
  "previous_version": "v8",
  "stage": "production",
  "promoted_at": "2026-03-18T15:00:00Z",
  "strategy": "immediate"
}
```

**Errors:**
- 400 Bad Request - Versão não está em staging
- 409 Conflict - Modelo falhou validação

---

### GET /api/v1/ml/drift

**Purpose:** Métricas de drift do modelo atual

**Query Parameters:**
- `window` (optional) - Janela em horas, default 168 (7 dias)

**Response:** 200 OK
```json
{
  "model_version": "v8",
  "window_hours": 168,
  "baseline": {
    "f1_score": 0.73,
    "accuracy": 0.80,
    "approve_rate": 0.65,
    "avg_confidence": 0.72
  },
  "current": {
    "f1_score": 0.71,
    "accuracy": 0.78,
    "approve_rate": 0.62,
    "avg_confidence": 0.69
  },
  "drift_detected": true,
  "alerts": [
    {
      "metric": "approve_rate",
      "change": -0.046,
      "threshold": 0.05,
      "severity": "warning"
    },
    {
      "metric": "avg_confidence",
      "change": -0.042,
      "threshold": 0.10,
      "severity": "info"
    }
  ],
  "recommendation": "Consider retraining with latest 100+ samples",
  "last_updated": "2026-03-18T15:00:00Z"
}
```

---

### GET /api/v1/ml/metrics

**Purpose:** Métricas agregadas para Prometheus/Grafana

**Response:** 200 OK (text/plain)
```
# HELP ml_approval_model_version Version do modelo em produção
# TYPE ml_approval_model_version gauge
ml_approval_model_version{version="v8"} 1

# HELP ml_approval_model_f1_score F1-score do modelo
# TYPE ml_approval_model_f1_score gauge
ml_approval_model_f1_score{version="v8"} 0.73

# HELP ml_approval_drift_detected Se drift foi detectado
# TYPE ml_approval_drift_detected gauge
ml_approval_drift_detected 1

# HELP ml_approval_samples_available Amostras disponíveis para retreino
# TYPE ml_approval_samples_available gauge
ml_approval_samples_available 523
```

---

## Controllers

### MLManagementController

**Localização:** `services/approval-service/src/api/routers/ml_management.py`

**Ações:**
- `post_retrain()` - Enfileira job de retreinamento
- `get_retrain_status()` - Status do job
- `list_models()` - Lista versões do MongoDB
- `get_model_details()` - Detalhes específicos
- `promote_model()` - Promove para produção
- `get_drift_metrics()` - Calcula drift com base em métricas

**Integrações:**
- MLflow client para registrar/buscar modelos
- MongoDB para model_versions
- Kafka para publicar eventos de retreinamento

---

## Error Handling

| Código | Descrição |
|--------|-----------|
| 400 | Bad Request - Parâmetros inválidos |
| 404 | Not Found - Recurso não existe |
| 409 | Conflict - Operação não permitida (ex: promover modelo falhado) |
| 503 | Service Unavailable - MLflow ou dependências indisponíveis |
