# Database Schema

This is the database schema implementation for the spec detailed in @.agent-os/specs/2026-03-18-optimizer-agents/spec.md

## New Collection

### optimization_recommendations

**Propósito:** Armazenar recomendações de otimização geradas pelo optimizer-mcp-server.

**Database:** `neural_hive`
**Collection:** `optimization_recommendations`

## Schema Definition

```python
{
    "_id": ObjectId,  # Auto-generated
    "ticket_id": str,  # ID do ticket analisado
    "workflow_id": str,  # ID do workflow
    "created_at": datetime,  # Timestamp de criação
    "updated_at": datetime,  # Timestamp de última atualização
    "status": str,  # pending | approved | applied | rejected

    # Análise de performance
    "performance_analysis": {
        "total_duration_ms": int,
        "peak_memory_mb": int,
        "task_count": int,
        "bottlenecks": [
            {
                "task_id": str,
                "task_type": str,  # query | transform | validate
                "duration_ms": int,
                "issue": str,
                "impact_score": float  # 0.0 a 1.0
            }
        ]
    },

    # Recomendações de otimização
    "recommendations": [
        {
            "id": str,  # UUID da recomendação
            "type": str,  # reduce_complexity | split_function | add_caching | refactor | query_optimize | index_suggestion
            "severity": str,  # low | medium | high | critical
            "target_type": str,  # code | mongodb | postgresql | neo4j | redis | clickhouse
            "file_path": str,  # para code optimizations
            "line_number": int,  # para code optimizations
            "function_name": str,  # opcional
            "description": str,
            "estimated_improvement_pct": float,
            "code_diff": str,  # opcional, diff patch para código
            "query_suggestion": str,  # opcional, query otimizada para DB
            "auto_apply": bool,  # pode ser aplicada automaticamente
            "status": str  # pending | approved | applied | rejected
        }
    ],

    # Validação pós-aplicação
    "validation": {
        "before_duration_ms": int,
        "after_duration_ms": int,
        "improvement_pct": float,
        "validated_at": datetime
    },

    # Metadados
    "analyzed_by": str,  # optimizer-mcp-server
    "analyzed_at": datetime,
    "approved_by": str,  # opcional, usuário que aprovou
    "approved_at": datetime,  # opcional
    "applied_at": datetime  # opcional
}
```

## Indexes

```python
# Index para busca por ticket
db.optimization_recommendations.create_index(
    [("ticket_id", 1)],
    name="idx_ticket_id"
)

# Index para busca por workflow
db.optimization_recommendations.create_index(
    [("workflow_id", 1), ("created_at", -1)],
    name="idx_workflow_created"
)

# Index para busca por status
db.optimization_recommendations.create_index(
    [("status", 1), ("created_at", -1)],
    name="idx_status_created"
)

# Index para recomendações pendentes
db.optimization_recommendations.create_index(
    [
        ("recommendations.status", 1),
        ("recommendations.auto_apply", 1)
    ],
    name="idx_pending_auto_apply"
)

# Index para análise de bottlenecks
db.optimization_recommendations.create_index(
    [("performance_analysis.bottlenecks.issue", 1)],
    name="idx_bottleneck_issues"
)

# Index para tipo de target (code vs database)
db.optimization_recommendations.create_index(
    [("recommendations.target_type", 1), ("status", 1)],
    name="idx_target_type_status"
)
```

## Migration Script

```python
# services/optimizer-agents/src/database/migrations/m001_optimization_recommendations.py

async def upgrade(mongo_client):
    """Criar coleção optimization_recommendations."""
    db = mongo_client["neural_hive"]

    # Criar coleção
    await db.create_collection("optimization_recommendations")

    # Criar indexes
    await db.optimization_recommendations.create_index([("ticket_id", 1)], name="idx_ticket_id")
    await db.optimization_recommendations.create_index(
        [("workflow_id", 1), ("created_at", -1)],
        name="idx_workflow_created"
    )
    await db.optimization_recommendations.create_index(
        [("status", 1), ("created_at", -1)],
        name="idx_status_created"
    )
    await db.optimization_recommendations.create_index(
        [("recommendations.status", 1), ("recommendations.auto_apply", 1)],
        name="idx_pending_auto_apply"
    )
    await db.optimization_recommendations.create_index(
        [("performance_analysis.bottlenecks.issue", 1)],
        name="idx_bottleneck_issues"
    )


async def downgrade(mongo_client):
    """Remover coleção optimization_recommendations."""
    db = mongo_client["neural_hive"]
    await db.optimization_recommendations.drop()
```

## Rationale

1. **Documento por ticket:** Cada recomendação está associada a um ticket específico para rastreabilidade
2. **Array de recomendações:** Um ticket pode gerar múltiplas recomendações
3. **Status separado:** Recomendações individuais têm seu próprio status para aprovação seletiva
4. **Índices compostos:** Queries comuns filtram por workflow+data ou status+data
5. **Auto-apply flag:** Permite otimizações automáticas sem intervenção humana

## Performance Considerations

- Tamanho estimado do documento: 5-10 KB
- Crescimento esperado: ~1000 tickets/dia → ~1 milhão documentos/ano
- Índices cobrem queries principais sem collection scans
