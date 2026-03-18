# API Specification

This is the API specification for the spec detailed in @.agent-os/specs/2026-03-18-gaps-06-mcp-integration/spec.md

## Endpoints

### Queen Agent MCP Orchestration API

### POST /api/v1/mcp/execute

**Purpose:** Executa múltiplas ferramentas MCP em paralelo

**Parameters:**
```json
{
  "tools": [
    {
      "server": "scout-mcp",
      "name": "search_code",
      "parameters": {"query": "class Scout"}
    },
    {
      "server": "optimizer-mcp",
      "name": "analyze_performance",
      "parameters": {"service": "scout-agents"}
    }
  ],
  "timeout_ms": 5000,
  "parallel": true
}
```

**Response:**
```json
{
  "results": [
    {
      "server": "scout-mcp",
      "name": "search_code",
      "status": "success",
      "data": {...}
    },
    {
      "server": "optimizer-mcp",
      "name": "analyze_performance",
      "status": "success",
      "data": {...}
    }
  ],
  "execution_time_ms": 1234,
  "correlation_id": "uuid"
}
```

**Errors:**
- `400 InvalidRequest` - Parâmetros inválidos
- `404 ServerNotFound` - Server MCP não registrado
- `504 ToolTimeout` - Tool excedeu timeout
- `500 InternalError` - Erro interno

### GET /api/v1/mcp/tools

**Purpose:** Lista todas as ferramentas MCP disponíveis

**Parameters:** None

**Response:**
```json
{
  "tools": [
    {
      "server": "scout-mcp",
      "name": "search_code",
      "description": "Busca padrões no código",
      "parameters": {
        "query": {"type": "string", "required": true},
        "file_pattern": {"type": "string", "required": false},
        "max_results": {"type": "integer", "required": false}
      }
    }
  ]
}
```

### POST /api/v1/mcp/tools/{server}/execute

**Purpose:** Executa uma ferramenta específica de um server

**Parameters:**
- `server`: Nome do MCP Server (path parameter)
```json
{
  "tool": "search_code",
  "parameters": {"query": "async def"}
}
```

**Response:**
```json
{
  "result": {...},
  "execution_time_ms": 123,
  "status": "success"
}
```

## MCP Client SDK API

### neural_hive_mcp_sdk.MCPClient

```python
class MCPClient:
    def __init__(
        self,
        server_name: str,
        timeout_ms: int = 5000
    ): ...

    async def execute_tool(
        self,
        tool_name: str,
        parameters: Dict[str, Any]
    ) -> ToolResult: ...

    async def list_tools(self) -> List[ToolDescriptor]: ...

    async def execute_batch(
        self,
        requests: List[ToolRequest]
    ) -> List[ToolResult]: ...
```

### neural_hive_mcp_sdk.ToolDecorator

```python
@mcp_tool(server="scout-mcp", name="custom_search")
async def custom_search(query: str) -> SearchResult:
    ...
```
