# Database Schema

This is the database schema implementation for the spec detailed in @.agent-os/specs/2026-03-17-gaps-05-scout-agents/spec.md

## Coleções MongoDB

### scout_explorations

Armazena resultados de explorações realizadas pelos Scout Agents.

```javascript
{
  _id: ObjectId("..."),
  exploration_id: "scout-exp-abc123",  // unique
  plan_id: "plan-xyz",                  // associado ao CognitivePlan
  intent_text: "Implementar...",        // intenção original

  // Tipo de exploração
  exploration_type: "codebase" | "patterns" | "solutions" | "dependencies",

  // Configuração
  scouts_deployed: ["pattern_matcher", "dependency_analyzer", "code_searcher"],
  parallel: true,
  timeout_ms: 30000,

  // Status
  status: "pending" | "running" | "completed" | "failed" | "timeout",
  started_at: ISODate("2026-03-17T19:00:00Z"),
  completed_at: ISODate("2026-03-17T19:00:08Z"),
  duration_ms: 8234,

  // Resultados agregados
  results: {
    solutions_found: [
      {
        approach: "FastAPI + SQLAlchemy",
        confidence: 0.85,
        complexity: "medium",
        pros: ["type-safe", "async-native"],
        cons: ["boilerplate", "learning curve"],
        code_example: "..."
      }
    ],
    patterns_discovered: [
      {
        name: "repository_pattern",
        occurrences: 15,
        locations: ["services/*/repositories/"],
        suggestion: "consolidate into shared library"
      }
    ],
    dependencies: {
      internal: ["service-a", "service-b"],
      external: ["fastapi", "sqlalchemy"],
      circular: []
    }
  },

  // Metadados
  created_at: ISODate("2026-03-17T19:00:00Z"),
  expires_at: ISODate("2026-03-24T19:00:00Z")  // TTL 7 dias
}
```

## Índices

```javascript
// scout_explorations
db.scout_explorations.createIndex(
  { exploration_id: 1 },
  { unique: true, name: "idx_exploration_id" }
)

db.scout_explorations.createIndex(
  { plan_id: 1 },
  { name: "idx_plan_id" }
)

db.scout_explorations.createIndex(
  { status: 1, created_at: -1 },
  { name: "idx_status_created" }
)

db.scout_explorations.createIndex(
  { exploration_type: 1 },
  { name: "idx_exploration_type" }
)

db.scout_explorations.createIndex(
  { expires_at: 1 },
  { name: "idx_expires_at", expireAfterSeconds: 0 }
)
```

## Rationale

- **exploration_id único**: Evita duplicação de explorações
- **plan_id index**: Permite consultar explorações por plano
- **TTL de 7 dias**: Explorações antigas perdem relevância rápido
- **status + created_at**: Filtragem eficiente para queries recentes
- **estrutura results aninhada**: Facilita agregação de múltiplos scouts
