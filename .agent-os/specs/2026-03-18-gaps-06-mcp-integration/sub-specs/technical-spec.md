# Technical Specification

This is the technical specification for the spec detailed in @.agent-os/specs/2026-03-18-gaps-06-mcp-integration/spec.md

## Technical Requirements

### Scout MCP Server

**Port:** 3010 (stdio-based, via container)
**Protocol:** MCP (JSON-RPC 2.0 over stdio)

**Ferramentas:**
1. `list_files` - Lista arquivos do codebase
   - Input: `{path: string, pattern?: string, recursive?: boolean}`
   - Output: `{files: [{path, size, type}]}`

2. `search_code` - Busca padrões no código
   - Input: `{query: string, file_pattern?: string, max_results?: number}`
   - Output: `{matches: [{file, line, content, context}]}`

3. `analyze_structure` - Analisa estrutura de diretórios
   - Input: `{path: string, depth?: number}`
   - Output: `{structure: tree, metrics: {files, dirs, complexity}}}`

### Optimizer MCP Server

**Port:** 3011 (stdio-based, via container)
**Protocol:** MCP (JSON-RPC 2.0 over stdio)

**Ferramentas:**
1. `suggest_refactors` - Sugere refatorações
   - Input: `{file_path: string, complexity_threshold?: number}`
   - Output: `{suggestions: [{type, description, effort, impact}]}`

2. `analyze_performance` - Analisa performance
   - Input: `{service: string, duration?: string}`
   - Output: `{metrics: {latency_p50, p95, p99, bottlenecks}}}`

3. `optimize_queries` - Otimiza queries MongoDB
   - Input: `{query: object, collection: string}`
   - Output: `{optimized_query, suggested_indexes, improvement_estimate}``

### Queen Agent ↔ MCP Integration

**Implementação:**
- `MCPToolOrchestrator` service em `queen-agent/src/mcp/`
- Paralelismo via `asyncio.gather()`
- Timeout por tool configurável
- Agregação de resultados com error handling

**API:**
```python
class MCPToolOrchestrator:
    async def execute_tools_parallel(
        self,
        tool_requests: List[ToolRequest]
    ) -> List[ToolResult]

    async def execute_tools_sequence(
        self,
        tool_requests: List[ToolRequest]
    ) -> List[ToolResult]
```

### MCP Client SDK

**Pacote:** `neural_hive_mcp_sdk`
**Version:** 1.0.0

**Componentes:**
```
neural_hive_mcp_sdk/
├── __init__.py
├── client.py           # MCPClient principal
├── tools.py            # Tool decorators e helpers
├── exceptions.py       # Exceções customizadas
└── types.py            # Type hints e modelos
```

**API:**
```python
from neural_hive_mcp_sdk import MCPClient

client = MCPClient(server_name="scout-mcp")
result = await client.execute_tool(
    tool_name="search_code",
    parameters={"query": "class Scout", "max_results": 10}
)
```

## External Dependencies

- **mcp** - Protocol implementation da Anthropic
  - Version: `>=0.9.0`
  - Justification: Implementação oficial do protocolo MCP

- **httpx** - HTTP client async para MCP REST wrappers
  - Version: `>=0.27.0`
  - Justification: Necessário para transporte HTTP alternativo

## Integration Requirements

### Kafka Topics

- `mcp.tool.execution.request` - Requisições de execução
- `mcp.tool.execution.response` - Respostas de execução
- `mcp.tool.discovery` - Descoberta de tools disponíveis

### Service Registry Integration

- Scout MCP Server: registra como `scout-mcp-server`
- Optimizer MCP Server: registra como `optimizer-mcp-server`
- Health checks via gRPC

### MongoDB Collections

- `mcp_tool_executions` - Log de execuções (TTL 30 dias)
- `mcp_tool_metrics` - Métricas de performance
- `mcp_tool_catalog` - Cache de tools disponíveis

## Performance Criteria

- Latência máxima de tool call: 500ms (p95)
- Paralelismo: até 10 calls simultâneas
- Throughput: 100 calls/segundo por server
- Timeout: 30 segundos por tool call
