# API Documentation - Scout Agents

Base URL: `http://localhost:8000`

## Health Checks

### GET /health/live

Liveness probe - verifica se o serviço está rodando.

**Response:**
```json
{
  "status": "alive",
  "timestamp": "2026-03-18T21:00:00Z"
}
```

### GET /health/ready

Readiness probe - verifica se o serviço está pronto para receber tráfego.

**Response:**
```json
{
  "status": "ready",
  "timestamp": "2026-03-18T21:00:00Z",
  "agent_id": "scout-agent-001"
}
```

### GET /metrics

Métricas Prometheus em formato texto.

## Exploration Endpoints

### GET /api/v1/explorations

Lista explorações ativas ou recentes.

**Query Parameters:**
- `status` (string, default="active"): Filtrar por status (active, completed, failed)
- `limit` (integer, default=50, max=100): Máximo de explorações

**Response:**
```json
{
  "explorations": [
    {
      "exploration_id": "exp_1234567890",
      "target": "/src",
      "status": "active",
      "created_at": "2026-03-18T20:00:00Z",
      "scouts_assigned": 3,
      "files_scanned": 150,
      "patterns_found": 12
    }
  ],
  "total": 1,
  "status_filter": "active"
}
```

### POST /api/v1/explorations

Cria nova exploração.

**Query Parameters:**
- `target` (string, required): Diretório ou arquivo alvo
- `task_type` (string, default="scan"): Tipo de tarefa

**Response:**
```json
{
  "exploration_id": "exp_1234567891",
  "target": "/src",
  "status": "pending",
  "message": "Exploration created successfully"
}
```

### DELETE /api/v1/explorations/{exploration_id}

Cancela exploração em andamento.

**Path Parameters:**
- `exploration_id` (string, required): ID da exploração

**Response:**
```json
{
  "exploration_id": "exp_1234567890",
  "status": "cancelled",
  "message": "Exploration cancelled successfully"
}
```

### POST /api/v1/explorations/{exploration_id}/scouts

Adiciona scout à exploração.

**Path Parameters:**
- `exploration_id` (string, required): ID da exploração

**Query Parameters:**
- `scout_id` (string, required): ID do scout

**Response:**
```json
{
  "exploration_id": "exp_1234567890",
  "scout_id": "scout_2",
  "total_scouts": 2
}
```

## Detection Endpoints

### POST /api/v1/signal-detect

Detecta sinais de mudança em diretório.

**Query Parameters:**
- `directory` (string, required): Diretório para escanear
- `extensions` (string, default=".py,.ts,.js,.yaml,.json"): Extensões separadas por vírgula

**Response:**
```json
{
  "directory": "/src",
  "signals_detected": 5,
  "signals": [
    {
      "filepath": "/src/main.py",
      "signal_type": "modified",
      "intensity": 0.75,
      "timestamp": "2026-03-18T20:00:00Z"
    }
  ]
}
```

## Curiosity Endpoints

### GET /api/v1/curiosity/{directory:path}

Retorna arquivos mais curiosos de um diretório.

**Path Parameters:**
- `directory` (string, required): Diretório para analisar

**Query Parameters:**
- `limit` (integer, default=10, max=50): Máximo de arquivos

**Response:**
```json
{
  "directory": "/src",
  "files": [
    {
      "filepath": "/src/services/analyzer.py",
      "curiosity_score": 85.5,
      "factors": {
        "complexity": 30,
        "patterns": 25,
        "keywords": 15,
        "unknown_libs": 10,
        "documentation": 5.5
      }
    }
  ],
  "total": 1
}
```

### GET /api/v1/exploration-summary/{directory:path}

Retorna resumo completo de exploração.

**Path Parameters:**
- `directory` (string, required): Diretório para analisar

**Response:**
```json
{
  "directory_curiosity": 75.0,
  "signal_summary": {
    "total_signals": 15,
    "by_type": {
      "modified": 10,
      "created": 3,
      "deleted": 2
    }
  },
  "hotspots": [
    {
      "filepath": "/src/services/api.py",
      "signal_count": 5,
      "burst_score": 4.2
    }
  ]
}
```

## Pattern Endpoints

### GET /api/v1/patterns

Lista padrões de design detectados.

**Query Parameters:**
- `category` (string, optional): Filtrar por categoria (creational, structural, behavioral)
- `limit` (integer, default=100, max=500): Máximo de padrões

**Response:**
```json
{
  "patterns": [
    {
      "name": "Repository",
      "category": "creational",
      "count": 5,
      "files": ["/src/repositories/user.py"]
    },
    {
      "name": "Observer",
      "category": "behavioral",
      "count": 2,
      "files": ["/src/observers/event.py"]
    }
  ],
  "total": 7,
  "category_filter": null,
  "categories": {
    "creational": ["Factory", "Builder", "Singleton", "Prototype"],
    "structural": ["Adapter", "Bridge", "Composite", "Decorator"],
    "behavioral": ["Observer", "Strategy", "Command", "Chain"]
  }
}
```

## Status Endpoint

### GET /api/v1/status

Retorna status detalhado do Scout Agent.

**Response:**
```json
{
  "agent_id": "scout-agent-001",
  "version": "1.0.0",
  "environment": "production",
  "uptime_seconds": 3600.5,
  "stats": {
    "processed": 1500,
    "detected": 450,
    "published": 450,
    "queue_size": 5
  },
  "configuration": {
    "max_signals_per_minute": 100,
    "curiosity_threshold": 70.0,
    "confidence_threshold": 0.6
  },
  "timestamp": "2026-03-18T21:00:00Z"
}
```

## Erros

### 400 Bad Request

```json
{
  "detail": "Invalid parameter value"
}
```

### 404 Not Found

```json
{
  "detail": "Exploration not found"
}
```

### 503 Service Unavailable

```json
{
  "detail": "Engine not initialized"
}
```

## Rate Limiting

- 100 requests por minuto por IP
- Header `X-RateLimit-Remaining` indica requests restantes

## Exemplos cURL

```bash
# Criar exploração
curl -X POST "http://localhost:8000/api/v1/explorations?target=/src&task_type=scan"

# Listar explorações
curl "http://localhost:8000/api/v1/explorations?status=active"

# Detectar sinais
curl -X POST "http://localhost:8000/api/v1/signal-detect?directory=/src&extensions=.py,.ts"

# Obter curiosidade
curl "http://localhost:8000/api/v1/curiosity/src?limit=20"

# Status
curl "http://localhost:8000/api/v1/status"
```
