# Technical Specification

This is the technical specification for the spec detailed in @.agent-os/specs/2026-03-18-optimizer-agents/spec.md

## Technical Requirements

### 1. Optimization Service (optimizer-agents)

**Localização:** `services/optimizer-agents/`

**Funcionalidades:**
- Consumir eventos `ticket.completed` do Kafka
- Extrair metadados do ticket (duração, memória, tarefas executadas)
- Chamar `optimizer-mcp-server` via HTTPMCPClient para análise
- Persistir recomendações no MongoDB

**Endpoints HTTP:**
- `GET /api/v1/optimizations/recommendations` — Listar recomendações
- `GET /api/v1/optimizations/recommendations/{id}` — Detalhe da recomendação
- `POST /api/v1/optimizations/recommendations/{id}/approve` — Aprovar recomendação
- `POST /api/v1/optimizations/recommendations/{id}/apply` — Aplicar otimização
- `GET /api/v1/optimizations/metrics` — Métricas de performance

**Integração MCP:**
```python
# Chamar optimizer-mcp-server para analisar código
result = await mcp_optimizer_client.execute_tool(
    "analyze_file_performance",
    {"file_path": ticket.execution_context.file_path}
)
```

### 2. Integration Orchestrator-Optimizer

**Localização:** `services/orchestrator-dynamic/`

**Hook pós-execução:**
```python
# Em orchestration_workflow.py, após completar ticket
async def _publish_ticket_completed(ticket: ExecutionTicket):
    await optimization_producer.produce(
        topic="ticket.completed",
        value={
            "ticket_id": ticket.id,
            "workflow_id": ticket.workflow_id,
            "duration_ms": ticket.duration_ms,
            "peak_memory_mb": ticket.peak_memory_mb,
            "tasks": [
                {
                    "task_id": t.id,
                    "executor_type": t.executor_type,
                    "duration_ms": t.duration_ms,
                    "file_path": t.execution_context.get("file_path")
                }
                for t in ticket.tasks
            ]
        }
    )
```

### 3. Optimization Repository

**Coleção MongoDB:** `optimization_recommendations`

**Suporte Multi-database:**
- MongoDB: Pipeline analysis, index suggestions
- PostgreSQL: EXPLAIN ANALYZE, query plan optimization
- Neo4j: Cypher query analysis, pattern optimization
- Redis: Key patterns, TTL suggestions, data type optimization
- ClickHouse: Query profiling, partitioning recommendations

**Schema:**
```python
{
    "_id": ObjectId,
    "ticket_id": str,
    "workflow_id": str,
    "created_at": datetime,
    "status": "pending" | "approved" | "applied" | "rejected",

    # Análise de performance
    "performance_analysis": {
        "total_duration_ms": int,
        "peak_memory_mb": int,
        "bottlenecks": [
            {
                "task_id": str,
                "issue": str,
                "impact_score": float  # 0-1
            }
        ]
    },

    # Recomendações
    "recommendations": [
        {
            "type": "reduce_complexity" | "split_function" | "add_caching",
            "file_path": str,
            "line_number": int,
            "description": str,
            "estimated_improvement_pct": float,
            "code_diff": str  # opcional
        }
    ],

    # Validação pós-aplicação
    "validation": {
        "before_duration_ms": int,
        "after_duration_ms": int,
        "improvement_pct": float
    }
}
```

### 4. Auto-apply Mechanism

**Lógica:**
1. Recomendação marcada `auto_apply=True`
2. Orchestrator verifica recomendações pendentes antes de executar
3. Se otimização disponível, patch é aplicado ao código
4. Métricas antes/depois são registradas

**Limites de segurança:**
- Never auto-aplicar mudanças em `services/*/config/`
- Never auto-aplicar mudanças em `tests/`
- Require approval para mudanças em `migrations/`

### 5. Performance Dashboard

**Endpoints API:**
- `GET /api/v1/optimizations/dashboard` — Resumo agregado
- `GET /api/v1/optimizations/timeline/{workflow_id}` — Timeline de otimizações
- `GET /api/v1/optimizations/top-issues` — Top issues por frequência

**Response dashboard:**
```json
{
    "total_recommendations": 42,
    "pending_approval": 15,
    "applied": 20,
    "rejected": 7,
    "avg_improvement_pct": 23.5,
    "top_issue_types": [
        {"type": "high_complexity", "count": 18},
        {"type": "long_function", "count": 12},
        {"type": "missing_cache", "count": 8}
    ]
}
```

## Integration Requirements

### Kafka Topics
- **Input:** `ticket.completed` (produzido por orchestrator-dynamic)
- **Output:** Nenhum (apenas persistência em MongoDB)

### MCP Integration
- **Server:** `http://optimizer-mcp-server.neural-hive-mcp.svc:8080`
- **Client:** `HTTPMCPClient` (já implementado em queen-agent)
- **Tools utilizadas:**
  - `analyze_file_performance` — Python AST analysis
  - `detect_code_smells` — Code smells detection
  - `get_recommendations` — Optimization suggestions
  - `analyze_mongodb_query` — MongoDB pipeline analysis
  - `analyze_postgresql_query` — PostgreSQL EXPLAIN ANALYZE
  - `analyze_neo4j_query` — Neo4j Cypher analysis
  - `analyze_redis_usage` — Redis key patterns
  - `analyze_clickhouse_query` — ClickHouse query profiling

**Arquitetura de Analyzers:**
```python
# Analyzer factory para selecionar analyzer correto
class AnalyzerFactory:
    @staticmethod
    def get_analyzer(db_type: str, language: str) -> BaseAnalyzer:
        if db_type == "mongodb":
            return MongoDBAnalyzer()
        elif db_type == "postgresql":
            return PostgreSQLAnalyzer()
        elif db_type == "neo4j":
            return Neo4jAnalyzer()
        elif db_type == "redis":
            return RedisAnalyzer()
        elif db_type == "clickhouse":
            return ClickHouseAnalyzer()
        else:
            return GenericAnalyzer()
```

### Dependencies
- `neural_hive_observability` — logging, tracing
- `motor` — MongoDB async client
- `aiokafka` — Kafka consumer
- `httpx` — HTTP client para MCP

## Performance Criteria

- Análise de performance deve completar em < 5s por ticket
- Dashboard deve responder em < 200ms
- Auto-aplicação não deve adicionar > 100ms de overhead
