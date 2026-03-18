# Database Schema

This is the database schema implementation for the spec detailed in @.agent-os/specs/2026-03-18-analyst-agents-expansion/spec.md

## Changes

### New Collection: `insights`

Armazena insights analíticos gerados pelo Analyst Agents.

### New Collection: `time_series_cache`

Cache de séries temporais processadas para performance.

## Schema Specifications

### Collection: `insights`

```python
{
    "_id": ObjectId,
    "insight_id": str,  # UUID
    "analysis_type": str,  # "timeseries", "mcp_aggregated", "anomaly_detection"
    "title": str,
    "description": str,
    "data": dict,  # Dados específicos do tipo de análise
    "metadata": {
        "source": str,  # "kafka", "mcp", "api"
        "source_id": str,  # ID da fonte (workflow_id, ticket_id, etc)
        "mcp_server": str,  # Se aplicável: "scout", "optimizer"
        "mcp_tools": list[str],  # Ferramentas MCP usadas
        "created_by": str,  # "system", "user:<user_id>"
    },
    "metrics": {
        "processing_time_ms": int,
        "confidence_score": float,  # 0.0 - 1.0
        "data_points": int
    },
    "timeseries": {  # Para análise time-series
        "metric_name": str,
        "start_time": datetime,
        "end_time": datetime,
        "resolution": str,  # "1m", "5m", "1h", "1d"
        "anomalies": list[dict],  # [{timestamp, value, score}]
        "trend": str,  # "increasing", "decreasing", "stable"
        "seasonality": bool
    },
    "tags": list[str],
    "status": str,  # "pending", "completed", "failed"
    "created_at": datetime,
    "expires_at": datetime  # TTL
}
```

### Collection: `time_series_cache`

```python
{
    "_id": ObjectId,
    "cache_key": str,  # "{metric_name}:{start}:{end}:{resolution}"
    "metric_name": str,
    "data": list[dict],  # [{timestamp, value}]
    "statistics": {
        "min": float,
        "max": float,
        "mean": float,
        "std": float,
        "count": int
    },
    "created_at": datetime,
    "expires_at": datetime  # TTL 24h
}
```

## Indexes

### `insights` Indexes

```python
# Primary lookup
db.insights.create_index({"insight_id": 1}, unique=True)

# Time-series queries
db.insights.create_index({"analysis_type": 1, "created_at": -1})

# Source queries
db.insights.create_index({"metadata.source": 1, "metadata.source_id": 1})

# Tag queries
db.insights.create_index({"tags": 1})

# TTL - 90 days
db.insights.create_index({"expires_at": 1}, expireAfterSeconds=0)

# Dashboard queries
db.insights.create_index({"status": 1, "created_at": -1})
```

### `time_series_cache` Indexes

```python
# Cache lookup
db.time_series_cache.create_index({"cache_key": 1}, unique=True)

# TTL - 24 hours
db.time_series_cache.create_index({"expires_at": 1}, expireAfterSeconds=0)
```

## Migration Script

```python
# migrations/m003_insights_collection.py

from datetime import datetime, timedelta

def upgrade():
    """Create insights collections with indexes."""
    db = client.get_database()

    # Create insights collection
    insights = db.insights

    # Create indexes
    insights_indexes = [
        ([("insight_id", 1)], {"unique": True}),
        ([("analysis_type", 1), ("created_at", -1)], {}),
        ([("metadata.source", 1), ("metadata.source_id", 1)], {}),
        ([("tags", 1)], {}),
        ([("expires_at", 1)], {"expireAfterSeconds": 0}),
        ([("status", 1), ("created_at", -1)], {}),
    ]

    for keys, options in insights_indexes:
        insights.create_index(keys, **options)

    # Create time_series_cache collection
    ts_cache = db.time_series_cache

    ts_cache_indexes = [
        ([("cache_key", 1)], {"unique": True}),
        ([("expires_at", 1)], {"expireAfterSeconds": 0}),
    ]

    for keys, options in ts_cache_indexes:
        ts_cache.create_index(keys, **options)

    print("Migration m003: Insights collections created successfully")

def downgrade():
    """Drop insights collections."""
    db = client.get_database()
    db.insights.drop()
    db.time_series_cache.drop()
    print("Migration m003: Insights collections dropped")
```

## Rationale

- **TTL 90 dias** para insights: Dados analíticos têm valor decrescente; 90 dias cobre trimestral de análise histórica
- **TTL 24h** para cache: Time-series mudam frequentemente; cache curto evita dados obsoletos
- **Índice composto** analysis_type + created_at: Suporta queries principais do dashboard
- **Índice unique** em insight_id: Previne duplicatas em reprocessamentos
