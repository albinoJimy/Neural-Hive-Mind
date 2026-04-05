# API Specification

Esta é a especificação de API para a spec detalhada em @.agent-os/specs/2026-04-05-dynamic-feature-flags/spec.md

## Base URL

```
Production:  https://feature-flag-service.neural-hive.svc.cluster.local:8080
Staging:     https://feature-flag-service.staging.neural-hive.svc.cluster.local:8080
Local:       http://localhost:8080
```

## Authentication

```
Authorization: Bearer {service_token}
```

Tokens de serviço são validados via OPA antes do processamento.

## Endpoints

### 1. Create Feature Flag

Cria uma nova feature flag.

**Request**

```http
POST /api/v1/feature-flags
Content-Type: application/json
Authorization: Bearer {token}

{
  "name": "enable_intelligent_scheduler",
  "description": "Habilita scheduler inteligente baseado em ML",
  "enabled": true,
  "rollout_strategy": "percentage",
  "rollout_percentage": 50,
  "conditions": [
    {
      "field": "risk_band",
      "operator": "in",
      "value": ["critical", "high"]
    }
  ],
  "owner": "orchestrator-team",
  "tags": ["scheduling", "ml"]
}
```

**Response** (201 Created)

```json
{
  "id": "flag_a1b2c3d4",
  "name": "enable_intelligent_scheduler",
  "description": "Habilita scheduler inteligente baseado em ML",
  "enabled": true,
  "rollout_strategy": "percentage",
  "rollout_percentage": 50,
  "conditions": [
    {
      "field": "risk_band",
      "operator": "in",
      "value": ["critical", "high"]
    }
  ],
  "created_at": "2026-04-05T10:00:00Z",
  "updated_at": "2026-04-05T10:00:00Z",
  "created_by": "platform-team",
  "owner": "orchestrator-team",
  "tags": ["scheduling", "ml"],
  "expires_at": null,
  "archived": false
}
```

**Errors**

| Code | Description |
|------|-------------|
| 400 | Validation error (invalid name, missing required field) |
| 409 | Flag name already exists |
| 422 | Unprocessable entity (invalid rollout config) |

---

### 2. List Feature Flags

Lista todas as flags com filtros opcionais.

**Request**

```http
GET /api/v1/feature-flags?enabled=true&owner=orchestrator-team&tag=scheduling&archived=false
Authorization: Bearer {token}
```

**Query Parameters**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| enabled | boolean | No | Filter by enabled status |
| owner | string | No | Filter by owner team |
| tag | string | No | Filter by tag (matches any) |
| archived | boolean | No | Include archived flags (default: false) |
| page | int | No | Page number (default: 1) |
| limit | int | No | Items per page (default: 50, max: 100) |

**Response** (200 OK)

```json
{
  "items": [
    {
      "id": "flag_a1b2c3d4",
      "name": "enable_intelligent_scheduler",
      "description": "Habilita scheduler inteligente",
      "enabled": true,
      "rollout_strategy": "percentage",
      "rollout_percentage": 50,
      "owner": "orchestrator-team",
      "tags": ["scheduling", "ml"],
      "created_at": "2026-04-05T10:00:00Z",
      "updated_at": "2026-04-05T12:30:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "limit": 50
}
```

---

### 3. Get Feature Flag

Obtém uma flag específica por ID ou nome.

**Request**

```http
GET /api/v1/feature-flags/enable_intelligent_scheduler
Authorization: Bearer {token}
```

**Response** (200 OK)

```json
{
  "id": "flag_a1b2c3d4",
  "name": "enable_intelligent_scheduler",
  "description": "Habilita scheduler inteligente baseado em ML",
  "enabled": true,
  "rollout_strategy": "percentage",
  "rollout_percentage": 50,
  "conditions": [
    {
      "field": "risk_band",
      "operator": "in",
      "value": ["critical", "high"]
    }
  ],
  "created_at": "2026-04-05T10:00:00Z",
  "updated_at": "2026-04-05T12:30:00Z",
  "created_by": "platform-team",
  "owner": "orchestrator-team",
  "tags": ["scheduling", "ml"],
  "expires_at": null,
  "archived": false
}
```

**Errors**

| Code | Description |
|------|-------------|
| 404 | Flag not found |

---

### 4. Update Feature Flag

Atualiza uma flag existente (invalida cache).

**Request**

```http
PUT /api/v1/feature-flags/enable_intelligent_scheduler
Content-Type: application/json
Authorization: Bearer {token}

{
  "enabled": false,
  "rollout_percentage": 75
}
```

**Response** (200 OK)

```json
{
  "id": "flag_a1b2c3d4",
  "name": "enable_intelligent_scheduler",
  "enabled": false,
  "rollout_strategy": "percentage",
  "rollout_percentage": 75,
  "updated_at": "2026-04-05T14:00:00Z",
  ...
}
```

**Errors**

| Code | Description |
|------|-------------|
| 400 | Validation error |
| 404 | Flag not found |
| 409 | Name conflict (if renaming) |

---

### 5. Delete Feature Flag

Remove uma flag permanentemente.

**Request**

```http
DELETE /api/v1/feature-flags/enable_intelligent_scheduler
Authorization: Bearer {token}
```

**Response** (204 No Content)

**Errors**

| Code | Description |
|------|-------------|
| 404 | Flag not found |

---

### 6. Toggle Feature Flag

Ativa/desativa uma flag rapidamente.

**Request**

```http
POST /api/v1/feature-flags/enable_intelligent_scheduler/toggle
Authorization: Bearer {token}
```

**Response** (200 OK)

```json
{
  "id": "flag_a1b2c3d4",
  "name": "enable_intelligent_scheduler",
  "enabled": false,
  "updated_at": "2026-04-05T14:05:00Z",
  ...
}
```

**Errors**

| Code | Description |
|------|-------------|
| 404 | Flag not found |

---

### 7. Evaluate Flags

Avalia múltiplas flags para um contexto específico.

**Request**

```http
POST /api/v1/feature-flags/evaluate
Content-Type: application/json
Authorization: Bearer {token}

{
  "flags": ["enable_intelligent_scheduler", "enable_burst_capacity"],
  "context": {
    "tenant_id": "tenant-123",
    "namespace": "production",
    "risk_band": "critical",
    "host": "orchestrator-1",
    "request_id": "req-abc123"
  }
}
```

**Response** (200 OK)

```json
{
  "enable_intelligent_scheduler": true,
  "enable_burst_capacity": false,
  "evaluated_at": "2026-04-05T14:10:00Z"
}
```

---

### 8. Batch Update

Atualiza múltiplas flags em uma transação.

**Request**

```http
POST /api/v1/feature-flags/batch
Content-Type: application/json
Authorization: Bearer {token}

{
  "updates": [
    {
      "name": "enable_intelligent_scheduler",
      "enabled": true
    },
    {
      "name": "enable_burst_capacity",
      "enabled": false
    }
  ]
}
```

**Response** (200 OK)

```json
{
  "updated": [
    {
      "id": "flag_a1b2c3d4",
      "name": "enable_intelligent_scheduler",
      "enabled": true,
      "updated_at": "2026-04-05T14:15:00Z"
    },
    {
      "id": "flag_e5f6g7h8",
      "name": "enable_burst_capacity",
      "enabled": false,
      "updated_at": "2026-04-05T14:15:00Z"
    }
  ],
  "failed": []
}
```

---

### 9. Get Metrics

Obtém métricas agregadas de uso.

**Request**

```http
GET /api/v1/feature-flags/metrics
Authorization: Bearer {token}
```

**Response** (200 OK)

```json
{
  "total_flags": 15,
  "enabled_flags": 8,
  "archived_flags": 2,
  "by_strategy": {
    "all": 3,
    "percentage": 4,
    "whitelist": 2,
    "canary": 1,
    "gradual": 1
  },
  "by_owner": {
    "orchestrator-team": 5,
    "ml-team": 3,
    "platform-team": 7
  },
  "cache_stats": {
    "hit_ratio": 0.95,
    "avg_latency_ms": 2.3
  },
  "top_evaluated": [
    {"name": "enable_intelligent_scheduler", "count": 15420},
    {"name": "enable_burst_capacity", "count": 8230}
  ]
}
```

---

### 10. Health Check

Endpoint para health check do serviço.

**Request**

```http
GET /health
```

**Response** (200 OK)

```json
{
  "status": "healthy",
  "version": "1.0.0",
  "dependencies": {
    "mongodb": "healthy",
    "redis": "healthy",
    "opa": "healthy"
  }
}
```

**Response** (503 Service Unavailable)

```json
{
  "status": "unhealthy",
  "dependencies": {
    "mongodb": "healthy",
    "redis": "unhealthy",
    "opa": "healthy"
  }
}
```

---

## Data Types

### RolloutStrategy

```typescript
enum RolloutStrategy {
  ALL = "all",
  PERCENTAGE = "percentage",
  WHITELIST = "whitelist",
  CANARY = "canary",
  GRADUAL = "gradual"
}
```

### ConditionOperator

```typescript
enum ConditionOperator {
  EQUALS = "equals",
  NOT_EQUALS = "not_equals",
  IN = "in",
  NOT_IN = "not_in",
  CONTAINS = "contains",
  REGEX_MATCH = "regex_match"
}
```

### Condition

```typescript
interface Condition {
  field: string;           // Campo a avaliar (ex: namespace, tenant_id)
  operator: ConditionOperator;
  value: any;              // Valor esperado
}
```

### FeatureFlag

```typescript
interface FeatureFlag {
  id: string;
  name: string;
  description?: string;
  enabled: boolean;
  rollout_strategy: RolloutStrategy;
  rollout_percentage?: number;  // 0-100, required if strategy=percentage
  conditions: Condition[];
  created_at: string;           // ISO 8601
  updated_at: string;           // ISO 8601
  created_by: string;
  owner?: string;
  tags: string[];
  expires_at?: string;          // ISO 8601
  archived: boolean;
}
```

## Rate Limiting

| Tier | Requests | Window |
|------|----------|--------|
| Default | 1000 | 1 minute |
| Service | 10000 | 1 minute |
| Admin | Unlimited | - |

## Webhooks

### Flag Changed Event

O serviço envia eventos de mudança para configured webhooks.

**Event Payload**

```json
{
  "event": "flag.changed",
  "timestamp": "2026-04-05T14:15:00Z",
  "flag": {
    "name": "enable_intelligent_scheduler",
    "enabled": true,
    "changed_fields": ["enabled", "rollout_percentage"]
  },
  "changed_by": "platform-team"
}
```

Configure webhooks via environment variable:
```bash
WEBHOOK_URLS=http://notification-service/internal/feature-flags
```
