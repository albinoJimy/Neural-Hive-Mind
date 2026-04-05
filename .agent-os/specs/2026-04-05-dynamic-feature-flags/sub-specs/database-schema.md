# Database Schema

Este é o schema de implementação para a spec detalhada em @.agent-os/specs/2026-04-05-dynamic-feature-flags/spec.md

## MongoDB Collections

### 1. feature_flags

Coleção principal para armazenar configurações de feature flags.

```javascript
{
  "_id": ObjectId("..."),
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
  "created_at": ISODate("2026-04-05T10:00:00Z"),
  "updated_at": ISODate("2026-04-05T12:30:00Z"),
  "created_by": "platform-team",
  "owner": "orchestrator-team",
  "tags": ["scheduling", "ml", "performance"],
  "expires_at": null,
  "archived": false
}
```

### Indexes

```javascript
// Index para lookup por nome (único)
db.feature_flags.createIndex(
  { "name": 1 },
  { unique: true, name: "idx_name_unique" }
)

// Index para filtros por status
db.feature_flags.createIndex(
  { "enabled": 1, "archived": 1 },
  { name: "idx_status_filter" }
)

// Index para filtros por owner
db.feature_flags.createIndex(
  { "owner": 1, "archived": 1 },
  { name: "idx_owner_filter" }
)

// Index para tags
db.feature_flags.createIndex(
  { "tags": 1 },
  { name: "idx_tags" }
)

// Index para TTL (auto-disable)
db.feature_flags.createIndex(
  { "expires_at": 1 },
  { name: "idx_expires_ttl", expireAfterSeconds: 0 }
)

// Compound index para queries comuns
db.feature_flags.createIndex(
  { "enabled": 1, "rollout_strategy": 1, "owner": 1 },
  { name: "idx_common_queries" }
)
```

### Migration Script

```python
# services/feature-flag-service/src/database/migrations/m001_initial_schema.py

from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime

async def upgrade(database: AsyncIOMotorDatabase) -> None:
    """Cria schema inicial de feature flags."""

    # Criar índices
    await database.feature_flags.create_index(
        [("name", 1)],
        unique=True,
        name="idx_name_unique"
    )

    await database.feature_flags.create_index(
        [("enabled", 1), ("archived", 1)],
        name="idx_status_filter"
    )

    await database.feature_flags.create_index(
        [("owner", 1), ("archived", 1)],
        name="idx_owner_filter"
    )

    await database.feature_flags.create_index(
        [("tags", 1)],
        name="idx_tags"
    )

    await database.feature_flags.create_index(
        [("expires_at", 1)],
        name="idx_expires_ttl",
        expireAfterSeconds=0
    )

    await database.feature_flags.create_index(
        [("enabled", 1), ("rollout_strategy", 1), ("owner", 1)],
        name="idx_common_queries"
    )

    # Inserir flags iniciais baseadas em feature_flags.rego
    initial_flags = [
        {
            "name": "enable_intelligent_scheduler",
            "description": "Habilita scheduler inteligente baseado em ML",
            "enabled": True,
            "rollout_strategy": "all",
            "conditions": [
                {"field": "risk_band", "operator": "in", "value": ["critical", "high"]}
            ],
            "created_by": "system",
            "owner": "orchestrator-team",
            "tags": ["scheduling", "ml"],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "archived": False
        },
        {
            "name": "enable_burst_capacity",
            "description": "Habilita capacidade burst para picos de carga",
            "enabled": False,
            "rollout_strategy": "whitelist",
            "conditions": [
                {"field": "tenant_id", "operator": "in", "value": []}
            ],
            "created_by": "system",
            "owner": "orchestrator-team",
            "tags": ["capacity", "performance"],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "archived": False
        },
        {
            "name": "enable_predictive_allocation",
            "description": "Habilita alocação preditiva baseada em modelos ML",
            "enabled": False,
            "rollout_strategy": "percentage",
            "rollout_percentage": 0,
            "conditions": [
                {"field": "namespace", "operator": "in", "value": ["staging", "beta"]}
            ],
            "created_by": "system",
            "owner": "ml-team",
            "tags": ["ml", "allocation"],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "archived": False
        },
        {
            "name": "enable_auto_scaling",
            "description": "Habilita auto-scaling baseado em depth da fila",
            "enabled": False,
            "rollout_strategy": "all",
            "conditions": [],
            "created_by": "system",
            "owner": "platform-team",
            "tags": ["scaling", "infrastructure"],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "archived": False
        },
        {
            "name": "enable_experimental_features",
            "description": "Habilita features experimentais (dev/staging only)",
            "enabled": False,
            "rollout_strategy": "whitelist",
            "conditions": [
                {"field": "namespace", "operator": "in", "value": ["development", "dev", "staging"]}
            ],
            "created_by": "system",
            "owner": "platform-team",
            "tags": ["experimental"],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "archived": False
        }
    ]

    await database.feature_flags.insert_many(initial_flags)

async def downgrade(database: AsyncIOMotorDatabase) -> None:
    """Remove schema de feature flags."""
    await database.feature_flags.drop()
```

## Redis Data Structures

### Keys Pattern

```
feature_flag:{flag_name}        # Hash com dados da flag (TTL: 60s)
feature_flags:all               # Hash com todas as flags (TTL: 60s)
feature_flag:eval:{hash}        # Cache de avaliação (TTL: 30s)
```

### Example Data

```
feature_flag:enable_intelligent_scheduler
{
  "id": "flag_a1b2c3d4",
  "name": "enable_intelligent_scheduler",
  "enabled": true,
  "rollout_strategy": "all",
  "conditions": [...],
  "updated_at": "2026-04-05T12:30:00Z"
}

feature_flags:all
{
  "enable_intelligent_scheduler": {...},
  "enable_burst_capacity": {...},
  "enable_predictive_allocation": {...}
}
```

## Validation Rules

### Field Validation

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| name | string | Yes | 1-100 chars, unique, snake_case |
| description | string | No | Max 500 chars |
| enabled | boolean | No | Default: false |
| rollout_strategy | enum | No | all, percentage, whitelist, canary, gradual |
| rollout_percentage | int | Conditional | 0-100, required if strategy=percentage |
| conditions | array | No | Max 20 conditions |
| created_by | string | Yes | User or service identifier |
| owner | string | No | Team identifier |
| tags | array | No | Max 10 tags, max 50 chars each |
| expires_at | datetime | No | Must be future |
| archived | boolean | No | Default: false |

### Business Logic

1. **Nome único**: Não pode existir duas flags com o mesmo nome
2. **Expiração**: Flags com `expires_at` no passado são automaticamente desabilitadas
3. **Archived**: Flags arquivadas não aparecem em queries padrão
4. **Rollout consistency**: Hash-based rollout garante mesmo resultado para mesma chave
5. **Cache TTL**: Sempre 60s para garantir consistência eventual

## Rationale

1. **Índice único em name**: Lookup primário, evita duplicatas
2. **Índice composto enabled+archived**: Queries mais comuns (listar flags ativas)
3. **TTL em expires_at**: Auto-disable sem cron job
4. **Redis cache**: Reduz latência de avaliação de <50ms para <5ms
5. **Hash determinístico**: Garante consistência em rollout gradual
