# API Specification

This is the API specification for the spec detailed in @.agent-os/specs/2026-03-18-optimizer-agents/spec.md

## Endpoints

### GET /api/v1/optimizations/recommendations

**Purpose:** Listar recomendações de otimização com filtros opcionais

**Parameters:**
- `status` (optional): `pending` | `approved` | `applied` | `rejected`
- `workflow_id` (optional): Filtrar por workflow específico
- `severity` (optional): `low` | `medium` | `high` | `critical`
- `auto_apply` (optional): `true` | `false`
- `limit` (optional): Número de resultados (default: 50, max: 100)
- `offset` (optional): Paginação (default: 0)

**Response:**
```json
{
    "total": 42,
    "offset": 0,
    "limit": 50,
    "items": [
        {
            "id": "675f8e9a1b2c3d4e5f6a7b8c",
            "ticket_id": "TICKET-123",
            "workflow_id": "workflow-abc",
            "status": "pending",
            "created_at": "2026-03-18T10:30:00Z",
            "recommendations": [
                {
                    "id": "rec-001",
                    "type": "reduce_complexity",
                    "severity": "high",
                    "file_path": "services/worker-agents/src/executors/query_executor.py",
                    "line_number": 145,
                    "description": "Função execute_query tem complexidade ciclomática 18",
                    "estimated_improvement_pct": 25.0,
                    "auto_apply": false
                }
            ]
        }
    ]
}
```

**Errors:**
- `400 Bad Request`: Parâmetros inválidos
- `500 Internal Server Error`: Erro no servidor

---

### GET /api/v1/optimizations/recommendations/{id}

**Purpose:** Obter detalhes de uma recomendação específica

**Parameters:**
- `id` (path): ID da recomendação (ObjectId)

**Response:**
```json
{
    "id": "675f8e9a1b2c3d4e5f6a7b8c",
    "ticket_id": "TICKET-123",
    "workflow_id": "workflow-abc",
    "status": "pending",
    "created_at": "2026-03-18T10:30:00Z",
    "updated_at": "2026-03-18T10:30:00Z",
    "performance_analysis": {
        "total_duration_ms": 5432,
        "peak_memory_mb": 128,
        "task_count": 5,
        "bottlenecks": [
            {
                "task_id": "task-456",
                "task_type": "query",
                "duration_ms": 3200,
                "issue": "N+1 query problem",
                "impact_score": 0.85
            }
        ]
    },
    "recommendations": [
        {
            "id": "rec-001",
            "type": "reduce_complexity",
            "severity": "high",
            "file_path": "services/worker-agents/src/executors/query_executor.py",
            "line_number": 145,
            "function_name": "execute_query",
            "description": "Função execute_query tem complexidade ciclomática 18",
            "estimated_improvement_pct": 25.0,
            "code_diff": "@@ -145,20 +145,10 @@\n-async def execute_query(...):\n-    # Complex logic here\n+async def execute_query(...):\n+    # Simplified logic",
            "auto_apply": false,
            "status": "pending"
        }
    ],
    "analyzed_by": "optimizer-mcp-server",
    "analyzed_at": "2026-03-18T10:30:00Z"
}
```

**Errors:**
- `404 Not Found`: Recomendação não encontrada
- `500 Internal Server Error`: Erro no servidor

---

### POST /api/v1/optimizations/recommendations/{id}/approve

**Purpose:** Aprovar uma recomendação para aplicação

**Parameters:**
- `id` (path): ID da recomendação

**Request Body:**
```json
{
    "recommendation_ids": ["rec-001", "rec-002"],
    "approved_by": "user@example.com"
}
```

**Response:**
```json
{
    "id": "675f8e9a1b2c3d4e5f6a7b8c",
    "status": "approved",
    "approved_recommendations": ["rec-001", "rec-002"],
    "approved_at": "2026-03-18T11:00:00Z"
}
```

**Errors:**
- `400 Bad Request`: Recomendação já aprovada ou IDs inválidos
- `404 Not Found`: Recomendação não encontrada
- `500 Internal Server Error`: Erro no servidor

---

### POST /api/v1/optimizations/recommendations/{id}/apply

**Purpose:** Aplicar uma otimização aprovada

**Parameters:**
- `id` (path): ID da recomendação

**Request Body:**
```json
{
    "recommendation_ids": ["rec-001"],
    "validate": true
}
```

**Response:**
```json
{
    "id": "675f8e9a1b2c3d4e5f6a7b8c",
    "status": "applied",
    "applied_recommendations": ["rec-001"],
    "applied_at": "2026-03-18T11:05:00Z",
    "files_modified": [
        "services/worker-agents/src/executors/query_executor.py"
    ]
}
```

**Errors:**
- `400 Bad Request`: Recomendação não aprovada ou falha na aplicação
- `404 Not Found`: Recomendação não encontrada
- `500 Internal Server Error`: Erro no servidor

---

### GET /api/v1/optimizations/metrics

**Purpose:** Obter métricas agregadas de otimizações

**Parameters:**
- `from_date` (optional): Data inicial (ISO 8601)
- `to_date` (optional): Data final (ISO 8601)

**Response:**
```json
{
    "period": {
        "from": "2026-03-01T00:00:00Z",
        "to": "2026-03-18T23:59:59Z"
    },
    "summary": {
        "total_recommendations": 42,
        "pending": 15,
        "approved": 20,
        "applied": 18,
        "rejected": 7
    },
    "performance": {
        "avg_improvement_pct": 23.5,
        "total_time_saved_ms": 125430,
        "best_improvement_pct": 67.0
    },
    "top_issues": [
        {"type": "high_complexity", "count": 18, "avg_improvement": 28.5},
        {"type": "long_function", "count": 12, "avg_improvement": 15.0},
        {"type": "missing_cache", "count": 8, "avg_improvement": 35.0}
    ]
}
```

**Errors:**
- `400 Bad Request`: Datas inválidas
- `500 Internal Server Error`: Erro no servidor

---

### GET /api/v1/optimizations/dashboard

**Purpose:** Dashboard agregado para UI

**Response:**
```json
{
    "total_recommendations": 42,
    "pending_approval": 15,
    "applied": 18,
    "avg_improvement_pct": 23.5,
    "top_issue_types": [
        {"type": "high_complexity", "count": 18},
        {"type": "long_function", "count": 12},
        {"type": "missing_cache", "count": 8}
    ],
    "recent_recommendations": [
        {
            "id": "675f8e9a1b2c3d4e5f6a7b8c",
            "severity": "high",
            "description": "Função execute_query tem complexidade 18",
            "created_at": "2026-03-18T10:30:00Z"
        }
    ]
}
```

**Errors:**
- `500 Internal Server Error`: Erro no servidor

---

### GET /api/v1/optimizations/timeline/{workflow_id}

**Purpose:** Timeline de otimizações para um workflow específico

**Parameters:**
- `workflow_id` (path): ID do workflow

**Response:**
```json
{
    "workflow_id": "workflow-abc",
    "optimizations": [
        {
            "id": "675f8e9a1b2c3d4e5f6a7b8c",
            "ticket_id": "TICKET-123",
            "status": "applied",
            "applied_at": "2026-03-18T11:05:00Z",
            "improvement_pct": 25.0
        },
        {
            "id": "675f8e9b2c3d4e5f6a7b8c9",
            "ticket_id": "TICKET-124",
            "status": "pending",
            "created_at": "2026-03-18T12:00:00Z"
        }
    ]
}
```

**Errors:**
- `404 Not Found`: Workflow não encontrado
- `500 Internal Server Error`: Erro no servidor
