# Database Schema

This is the database schema implementation for the spec detailed in @.agent-os/specs/2026-03-18-gaps-06-mcp-integration/spec.md

## Changes

### Nova Coleção: mcp_tool_executions

Armazena log de execuções de ferramentas MCP para auditoria e debugging.

### Nova Coleção: mcp_tool_metrics

Armazena métricas agregadas de performance das ferramentas MCP.

### Nova Coleção: mcp_tool_catalog

Cache de ferramentas MCP disponíveis com metadata.

## Specifications

### mcp_tool_executions

```javascript
{
  _id: ObjectId,
  correlation_id: string,      // UUID
  server_name: string,          // "scout-mcp", "optimizer-mcp"
  tool_name: string,            // "search_code", "analyze_performance"
  parameters: object,           // Parâmetros da chamada
  status: string,               // "success", "error", "timeout"
  result: object,               // Resultado da execução (se sucesso)
  error_message: string,        // Mensagem de erro (se falha)
  execution_time_ms: number,    // Tempo de execução
  requested_by: string,         // Serviço/agente solicitante
  requested_at: ISODate,        // Timestamp da requisição
  completed_at: ISODate,        // Timestamp de conclusão
  created_at: ISODate           // Timestamp de criação
}
```

**Indexes:**
```javascript
db.mcp_tool_executions.createIndex(
  { correlation_id: 1 },
  { name: "idx_correlation_id" }
)

db.mcp_tool_executions.createIndex(
  { server_name: 1, tool_name: 1, requested_at: -1 },
  { name: "idx_server_tool_time" }
)

db.mcp_tool_executions.createIndex(
  { created_at: 1 },
  { name: "idx_created_at",
    expireAfterSeconds: 2592000 }  // TTL 30 dias
)
```

### mcp_tool_metrics

```javascript
{
  _id: ObjectId,
  server_name: string,           // "scout-mcp", "optimizer-mcp"
  tool_name: string,             // "search_code", "analyze_performance"
  date: string,                  // "YYYY-MM-DD"
  total_calls: number,           // Total de chamadas no dia
  successful_calls: number,      // Chamadas bem-sucedidas
  failed_calls: number,          // Chamadas falhadas
  timeout_calls: number,         // Chamadas com timeout
  avg_execution_time_ms: number, // Tempo médio de execução
  p50_execution_time_ms: number, // Percentil 50
  p95_execution_time_ms: number, // Percentil 95
  p99_execution_time_ms: number, // Percentil 99
  updated_at: ISODate
}
```

**Indexes:**
```javascript
db.mcp_tool_metrics.createIndex(
  { server_name: 1, tool_name: 1, date: -1 },
  { name: "idx_server_tool_date", unique: true }
)
```

### mcp_tool_catalog

```javascript
{
  _id: ObjectId,
  server_name: string,           // "scout-mcp", "optimizer-mcp"
  tool_name: string,             // "search_code"
  description: string,
  parameters: [                  // Schema dos parâmetros
    {
      name: string,
      type: string,              // "string", "number", "boolean", "object"
      required: boolean,
      description: string
    }
  ],
  response_schema: object,       // Schema da resposta
  tags: [string],                // ["code-analysis", "search"]
  version: string,               // "1.0.0"
  enabled: boolean,
  registered_at: ISODate,
  updated_at: ISODate
}
```

**Indexes:**
```javascript
db.mcp_tool_catalog.createIndex(
  { server_name: 1, tool_name: 1 },
  { name: "idx_server_tool", unique: true }
)

db.mcp_tool_catalog.createIndex(
  { tags: 1 },
  { name: "idx_tags" }
)

db.mcp_tool_catalog.createIndex(
  { enabled: 1 },
  { name: "idx_enabled" }
)
```

## Rationale

1. **TTL em mcp_tool_executions**: Logs antigos são automaticamente removidos após 30 dias para controlar o tamanho da coleção.

2. **Índice composto em mcp_tool_metrics**: Permite queries eficientes por server/tool/date com garantia de unicidade para agregação diária.

3. **Índice de tags em mcp_tool_catalog**: Facilita descoberta de ferramentas por categoria funcional.

4. **Campo enabled em mcp_tool_catalog**: Permite desabilitar ferramentas sem remover o registro.
