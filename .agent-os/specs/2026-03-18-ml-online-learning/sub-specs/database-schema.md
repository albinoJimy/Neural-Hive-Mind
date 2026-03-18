# Database Schema

This is the database schema implementation for the spec detailed in @.agent-os/specs/2026-03-18-ml-online-learning/spec.md

## Overview

Este spec adiciona schemas para:
1. **MLflow PostgreSQL** - Model registry e tracking
2. **MongoDB** - Coleção para histórico de versões de modelos

## MLflow PostgreSQL Schema

MLflow usa seu próprio schema PostgreSQL. Instalação padrão cria:

### Tabelas Principais

```sql
-- MLflow usa estas tabelas automaticamente:
CREATE TABLE experiments (
    experiment_id INT PRIMARY KEY,
    name VARCHAR(256) UNIQUE NOT NULL,
    artifact_location VARCHAR(256),
    lifecycle_stage VARCHAR(32)
);

CREATE TABLE runs (
    run_uuid VARCHAR(32) PRIMARY KEY,
    experiment_id INT REFERENCES experiments(experiment_id),
    start_time BIGINT,
    end_time BIGINT,
    status VARCHAR(32),
    artifact_uri VARCHAR(256)
);

CREATE TABLE metrics (
    key VARCHAR(256),
    value DOUBLE,
    timestamp BIGINT,
    run_uuid VARCHAR(32) REFERENCES runs(run_uuid),
    PRIMARY KEY (key, run_uuid, timestamp)
);

CREATE TABLE params (
    key VARCHAR(256),
    value VARCHAR(512),
    run_uuid VARCHAR(32) REFERENCES runs(run_uuid),
    PRIMARY KEY (key, run_uuid)
);

CREATE TABLE registered_models (
    name VARCHAR(256) PRIMARY KEY,
    description TEXT,
    last_updated_timestamp BIGINT
);

CREATE TABLE model_versions (
    name VARCHAR(256) REFERENCES registered_models(name),
    version INT,
    creation_timestamp BIGINT,
    source VARCHAR(512),
    stage VARCHAR(20),
    PRIMARY KEY (name, version)
);
```

## MongoDB: model_versions History

Nova coleção para rastrear deployments de modelos no approval-service.

### Coleção: model_versions

```javascript
db.createCollection("model_versions");

// Índices
db.model_versions.createIndex({ version: 1 });
db.model_versions.createIndex({ stage: 1, created_at: -1 });
db.model_versions.createIndex({ is_active: 1 });
db.model_versions.createIndex({ created_at: -1 });
```

### Schema Documento

```javascript
{
  _id: ObjectId,
  version: "v9",              // Versão do modelo
  mlflow_run_id: "uuid",      // Referência ao run MLflow
  stage: "staging" | "production" | "archived",
  is_active: true,            // Se está em uso
  f1_score: 0.75,             // Métricas
  accuracy: 0.82,
  precision: 0.78,
  recall: 0.73,
  n_samples: 500,             // Amostras usadas no treino
  feature_importance: {       // Feature importance
    confidence: 0.6147,
    rf_ml_risk: 0.2221,
    rf_ml_confidence: 0.1632
  },
  created_at: ISODate("2026-03-18T10:00:00Z"),
  promoted_at: ISODate("2026-03-18T12:00:00Z"),  // Quando foi para produção
  promoted_by: "system" | "manual" | "canary",
  drift_metrics: {             // Métricas de drift (coletado periodicamente)
    last_check: ISODate("2026-03-18T14:00:00Z"),
    confidence_drop: 0.02,     // 2% drop vs baseline
    approve_rate_change: 0.05  // 5% change vs baseline
  }
}
```

### Migration Script

**Localização:** `services/approval-service/src/database/migrations/m002_model_versions.py`

```python
async def upgrade():
    """Criar coleção model_versions com índices."""
    await db.model_versions.create_index([("version", 1)])
    await db.model_versions.create_index([("stage", -1), ("created_at", -1)])
    await db.model_versions.create_index([("is_active", 1)])
    await db.model_versions.create_index([("created_at", -1)])

async def downgrade():
    """Remover coleção model_versions."""
    await db.model_versions.drop()
```

## Rationale

**MLflow PostgreSQL:**
- Padrão da indústria para MLOps
- Suporta queries complexas por métricas
- ACID para transações de promoção de modelos

**MongoDB model_versions:**
- Mantém histórico local de deployments
- Permite queries rápidas de versões ativas
- Schema flexível para drift metrics
- Integra com approval-service existente
