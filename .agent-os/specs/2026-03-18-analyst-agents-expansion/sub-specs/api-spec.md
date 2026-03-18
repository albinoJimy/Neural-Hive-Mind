# API Specification

This is the API specification for the spec detailed in @.agent-os/specs/2026-03-18-analyst-agents-expansion/spec.md

## Endpoints

### GET /api/v1/analytics/insights

**Purpose:** Listar insights analíticos com paginação e filtros

**Parameters:**
- `analysis_type` (query, optional): Tipo de análise (timeseries, mcp_aggregated, anomaly_detection)
- `source` (query, optional): Fonte do insight (kafka, mcp, api)
- `tags` (query, optional): Filtro por tags (comma-separated)
- `status` (query, optional): pending, completed, failed
- `limit` (query, optional): Itens por página (default: 50, max: 1000)
- `offset` (query, optional): Paginação (default: 0)
- `start_date` (query, optional): Data inicial (ISO 8601)
- `end_date` (query, optional): Data final (ISO 8601)

**Response:**
```json
{
  "items": [
    {
      "insight_id": "uuid",
      "analysis_type": "timeseries",
      "title": "CPU Usage Anomaly Detected",
      "description": "Unusual spike in worker-agents CPU",
      "data": {...},
      "metrics": {
        "processing_time_ms": 150,
        "confidence_score": 0.87,
        "data_points": 1008
      },
      "tags": ["cpu", "anomaly", "worker-agents"],
      "status": "completed",
      "created_at": "2026-03-18T12:00:00Z"
    }
  ],
  "total": 234,
  "limit": 50,
  "offset": 0
}
```

**Errors:**
- 400 Bad Request: Parâmetros inválidos
- 500 Internal Server Error

---

### GET /api/v1/analytics/insights/{insight_id}

**Purpose:** Obter detalhes completos de um insight específico

**Parameters:**
- `insight_id` (path): UUID do insight

**Response:**
```json
{
  "insight_id": "uuid",
  "analysis_type": "timeseries",
  "title": "...",
  "description": "...",
  "data": {
    "full_timeseries": [...],
    "anomalies": [...],
    "trend_analysis": {...}
  },
  "metadata": {
    "source": "kafka",
    "source_id": "workflow-123",
    "created_by": "system"
  },
  "metrics": {...},
  "timeseries": {...},
  "tags": [...],
  "status": "completed",
  "created_at": "2026-03-18T12:00:00Z",
  "expires_at": "2026-06-18T12:00:00Z"
}
```

**Errors:**
- 404 Not Found: Insight não existe
- 500 Internal Server Error

---

### POST /api/v1/analytics/insights/query

**Purpose:** Criar nova análise sob demanda

**Request Body:**
```json
{
  "analysis_type": "timeseries|mcp_aggregated|anomaly_detection",
  "target": {
    "metric_name": "worker_agents_cpu_usage",
    "time_range": {
      "start": "2026-03-11T00:00:00Z",
      "end": "2026-03-18T00:00:00Z"
    }
  },
  "parameters": {
    "resolution": "5m",
    "anomaly_threshold": 2.5,
    "mcp_tools": ["analyze_performance", "suggest_optimizations"]
  }
}
```

**Response:**
```json
{
  "query_id": "uuid",
  "status": "pending|completed|failed",
  "estimated_completion": "2026-03-18T12:02:00Z",
  "insight_id": "uuid"  // Presente se status=completed
}
```

**Errors:**
- 400 Bad Request: Parâmetros inválidos
- 422 Unprocessable Entity: Tipo de análise não suportado
- 500 Internal Server Error

---

### GET /api/v1/analytics/insights/{insight_id}/export

**Purpose:** Exportar insight em formato específico

**Parameters:**
- `insight_id` (path): UUID do insight
- `format` (query): json, csv, pdf (default: json)

**Response:**
- JSON: `application/json` com dados completos
- CSV: `text/csv` com dados tabulares
- PDF: `application/pdf` com relatório formatado

**Errors:**
- 404 Not Found: Insight não existe
- 400 Bad Request: Formato não suportado
- 500 Internal Server Error

---

### GET /api/v1/analytics/metrics

**Purpose:** Métricas do Analyst Agent (Prometheus format)

**Response:**
```
# HELP analyst_insights_total Total number of insights generated
# TYPE analyst_insights_total counter
analyst_insights_total{analysis_type="timeseries"} 1234

# HELP analyst_processing_time_seconds Insight processing time
# TYPE analyst_processing_time_seconds histogram
analyst_processing_time_seconds_bucket{le="0.1"} 100
analyst_processing_time_seconds_bucket{le="1.0"} 450
...
```

**Errors:**
- 500 Internal Server Error

---

### GET /api/v1/analytics/timeseries/{metric_name}

**Purpose:** Obter série temporal de métrica específica

**Parameters:**
- `metric_name` (path): Nome da métrica
- `start` (query): Data inicial (ISO 8601)
- `end` (query): Data final (ISO 8601)
- `resolution` (query): 1m, 5m, 1h, 1d (default: 5m)

**Response:**
```json
{
  "metric_name": "worker_agents_cpu_usage",
  "time_range": {
    "start": "2026-03-11T00:00:00Z",
    "end": "2026-03-18T00:00:00Z"
  },
  "resolution": "5m",
  "data": [
    {"timestamp": "2026-03-11T00:00:00Z", "value": 45.2},
    {"timestamp": "2026-03-11T00:05:00Z", "value": 47.8},
    ...
  ],
  "statistics": {
    "min": 12.3,
    "max": 89.5,
    "mean": 52.4,
    "std": 15.2
  }
}
```

**Errors:**
- 404 Not Found: Métrica não existe
- 400 Bad Request: Parâmetros inválidos
- 500 Internal Server Error

---

### GET /api/v1/analytics/timeseries/{metric_name}/anomalies

**Purpose:** Detectar anomalias em série temporal

**Parameters:**
- `metric_name` (path): Nome da métrica
- `start` (query): Data inicial
- `end` (query): Data final
- `method` (query): zscore, isolation_forest (default: zscore)
- `threshold` (query): Limiar de anomalia (default: 2.5)

**Response:**
```json
{
  "metric_name": "worker_agents_cpu_usage",
  "method": "zscore",
  "threshold": 2.5,
  "anomalies": [
    {
      "timestamp": "2026-03-15T14:30:00Z",
      "value": 87.3,
      "z_score": 3.4,
      "severity": "high"
    },
    ...
  ],
  "summary": {
    "total_anomalies": 5,
    "high_severity": 2,
    "medium_severity": 3
  }
}
```

**Errors:**
- 404 Not Found: Métrica não existe
- 400 Bad Request: Método não suportado
- 500 Internal Server Error

---

### GET /api/v1/analytics/dashboard

**Purpose:** Dados agregados para dashboard Grafana

**Parameters:**
- `time_range` (query): 1h, 6h, 24h, 7d (default: 24h)

**Response:**
```json
{
  "time_range": "24h",
  "insights_by_type": {
    "timeseries": 45,
    "mcp_aggregated": 23,
    "anomaly_detection": 12
  },
  "anomalies_detected": 8,
  "avg_processing_time_ms": 180,
  "confidence_distribution": {
    "high": 30,
    "medium": 35,
    "low": 15
  },
  "top_sources": [
    {"source": "kafka", "count": 45},
    {"source": "mcp", "count": 23},
    {"source": "api", "count": 12}
  ],
  "recent_insights": [
    {...},
    {...},
    {...}
  ]
}
```

**Errors:**
- 400 Bad Request: Time range inválido
- 500 Internal Server Error
