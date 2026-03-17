# API Specification

This is the API specification for the spec detailed in @.agent-os/specs/2026-03-17-gaps-05-scout-agents/spec.md

## Endpoints

### POST /api/v1/scout/explore

Inicia uma nova exploração do codebase.

**Purpose:** Dispara múltiplos Scout Agents para analisar o codebase e descobrir alternativas/padrões

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| plan_id | string | Yes | ID do CognitivePlan associado |
| intent_text | string | Yes | Texto da intenção original |
| exploration_type | string | No | Tipo: codebase, patterns, solutions, dependencies (default: codebase) |
| scouts | array[string] | No | Scouts específicos para deploy (default: all available) |
| timeout_ms | integer | No | Timeout em ms (default: 30000) |

**Request:**
```json
{
  "plan_id": "plan-xyz",
  "intent_text": "Implementar API de usuários com CRUD",
  "exploration_type": "solutions",
  "scouts": ["pattern_matcher", "code_searcher"],
  "timeout_ms": 30000
}
```

**Response:** 202 Accepted
```json
{
  "exploration_id": "scout-exp-abc123",
  "status": "running",
  "estimated_completion_ms": 8000,
  "scouts_deployed": ["pattern_matcher", "code_searcher"]
}
```

**Errors:**
- 400 Invalid request parameters
- 503 Scout service unavailable

---

### GET /api/v1/scout/explore/{exploration_id}

Consulta o status/resultados de uma exploração.

**Purpose:** Recupera resultados ou status de exploração em andamento

**Parameters:**
- Path: exploration_id (string)

**Response:** 200 OK
```json
{
  "exploration_id": "scout-exp-abc123",
  "plan_id": "plan-xyz",
  "status": "completed",
  "started_at": "2026-03-17T19:00:00Z",
  "completed_at": "2026-03-17T19:00:08Z",
  "duration_ms": 8234,
  "results": {
    "solutions_found": [...],
    "patterns_discovered": [...],
    "dependencies": {...}
  }
}
```

**Errors:**
- 404 Exploration not found

---

### GET /api/v1/scout/patterns

Consulta padrões descobertos no codebase.

**Purpose:** Lista padrões recorrentes identificados pelos scouts

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| domain | string | No | Filtrar por domínio (security, performance, etc.) |
| min_occurrences | integer | No | Mínimo de ocorrências (default: 3) |
| limit | integer | No | Máximo de resultados (default: 50) |

**Response:** 200 OK
```json
{
  "patterns": [
    {
      "name": "repository_pattern",
      "category": "data_access",
      "occurrences": 15,
      "locations": ["services/user/repositories/", "services/order/repositories/"],
      "example": "class UserRepository: ...",
      "suggestion": "consolidate into shared library"
    }
  ],
  "total": 42
}
```

---

### POST /api/v1/scout/synthesize

Sintetiza múltiplas descobertas em recomendações.

**Purpose:** Combina resultados de múltiplas explorações em insights acionáveis

**Request:**
```json
{
  "exploration_ids": ["scout-exp-abc123", "scout-exp-def456"],
  "focus": "implementation" | "optimization" | "refactoring"
}
```

**Response:** 200 OK
```json
{
  "recommendations": [
    {
      "priority": "high",
      "title": "Consolidate Repository Pattern",
      "description": "Multiple services implement similar repository patterns...",
      "effort": "M",
      "impact": "reduce code duplication by 30%"
    }
  ]
}
```

---

### GET /api/v1/scout/health

Health check do Scout service.

**Response:** 200 OK
```json
{
  "status": "healthy",
  "scouts_available": ["pattern_matcher", "dependency_analyzer", "code_searcher"],
  "active_explorations": 3,
  "cache_hit_rate": 0.72
}
```
