# MCP Client SDK

SDK para conectar agentes especializados aos servidores MCP (Model Context Protocol).

## Instalação

```bash
pip install mcp-client-sdk
```

## Uso

```python
import asyncio
from mcp_client_sdk import MCPClient


async def main():
    # Criar cliente
    client = MCPClient(server_url="http://localhost:3010")

    # Listar ferramentas disponíveis
    tools = await client.list_tools()
    print(f"Ferramentas: {[t['name'] for t in tools]}")

    # Executar ferramenta
    result = await client.execute_tool(
        tool_name="list_files",
        params={"path": "/src", "pattern": "*.py"}
    )
    print(f"Arquivos: {result}")


if __name__ == "__main__":
    asyncio.run(main())
```

## Execução em lote

```python
results = await client.execute_batch([
    {"tool_name": "list_files", "params": {"path": "/src"}},
    {"tool_name": "analyze_structure", "params": {"path": "/src"}},
])
```
