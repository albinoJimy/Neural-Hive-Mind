"""Teste E2E real para transporte stdio com servidor MCP mock."""
import asyncio
import json
import sys
import tempfile
from pathlib import Path

import pytest

from src.clients.mcp_server_client import MCPServerClient


# Script Python que age como servidor MCP stdio mock
MOCK_MCP_SERVER_SCRIPT = '''
import sys
import json

def main():
    """Servidor MCP mock que responde a requisições JSON-RPC via stdio."""
    for line in sys.stdin:
        try:
            request = json.loads(line.strip())
        except json.JSONDecodeError:
            continue

        request_id = request.get("id")
        method = request.get("method")

        # Responder a tools/list
        if method == "tools/list":
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "tools": [
                        {
                            "name": "mock_tool",
                            "description": "Mock tool for testing stdio transport",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "message": {"type": "string"}
                                }
                            }
                        },
                        {
                            "name": "echo_tool",
                            "description": "Echo tool that returns input",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "text": {"type": "string"}
                                }
                            }
                        }
                    ]
                }
            }
            print(json.dumps(response), flush=True)

        # Responder a tools/call
        elif method == "tools/call":
            tool_name = request.get("params", {}).get("name", "")
            arguments = request.get("params", {}).get("arguments", {})

            if tool_name == "mock_tool":
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [
                            {"type": "text", "text": f"Mock result: {arguments.get('message', 'no message')}"}
                        ],
                        "isError": False
                    }
                }
            elif tool_name == "echo_tool":
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [
                            {"type": "text", "text": arguments.get("text", "")}
                        ],
                        "isError": False
                    }
                }
            elif tool_name == "error_tool":
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [
                            {"type": "text", "text": "Error occurred"}
                        ],
                        "isError": True
                    }
                }
            else:
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32601,
                        "message": f"Tool not found: {tool_name}"
                    }
                }
            print(json.dumps(response), flush=True)

        # Responder a resources/read
        elif method == "resources/read":
            uri = request.get("params", {}).get("uri", "")
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "contents": [
                        {
                            "uri": uri,
                            "mimeType": "text/plain",
                            "text": f"Content of {uri}"
                        }
                    ]
                }
            }
            print(json.dumps(response), flush=True)

        # Responder a prompts/list
        elif method == "prompts/list":
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "prompts": [
                        {"name": "test_prompt", "description": "Test prompt"}
                    ]
                }
            }
            print(json.dumps(response), flush=True)

        # Método desconhecido
        else:
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {method}"
                }
            }
            print(json.dumps(response), flush=True)

        # Log para stderr (para teste de captura)
        print(f"[INFO] Processed {method}", file=sys.stderr, flush=True)

if __name__ == "__main__":
    main()
'''


@pytest.fixture
def mock_mcp_server_path():
    """Cria script de servidor MCP mock temporário."""
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".py",
        delete=False,
        prefix="mock_mcp_server_"
    ) as f:
        f.write(MOCK_MCP_SERVER_SCRIPT)
        server_path = f.name

    yield server_path

    # Cleanup
    Path(server_path).unlink(missing_ok=True)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_stdio_list_tools_with_mock_server(mock_mcp_server_path):
    """Teste E2E: list_tools via stdio com servidor mock."""
    client = MCPServerClient(
        server_url=f"stdio://{sys.executable} {mock_mcp_server_path}",
        transport="stdio",
        timeout_seconds=10,
    )

    async with client:
        tools = await client.list_tools()

    assert len(tools) == 2
    assert tools[0].name == "mock_tool"
    assert tools[1].name == "echo_tool"
    assert "stdio transport" in tools[0].description


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_stdio_call_tool_with_mock_server(mock_mcp_server_path):
    """Teste E2E: call_tool via stdio com servidor mock."""
    client = MCPServerClient(
        server_url=f"stdio://{sys.executable} {mock_mcp_server_path}",
        transport="stdio",
        timeout_seconds=10,
    )

    async with client:
        result = await client.call_tool("mock_tool", {"message": "Hello from test"})

    assert result.isError is False
    assert len(result.content) == 1
    assert "Hello from test" in result.content[0].text


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_stdio_echo_tool_with_mock_server(mock_mcp_server_path):
    """Teste E2E: echo_tool via stdio com servidor mock."""
    client = MCPServerClient(
        server_url=f"stdio://{sys.executable} {mock_mcp_server_path}",
        transport="stdio",
        timeout_seconds=10,
    )

    test_text = "Echo test message"

    async with client:
        result = await client.call_tool("echo_tool", {"text": test_text})

    assert result.isError is False
    assert result.content[0].text == test_text


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_stdio_get_resource_with_mock_server(mock_mcp_server_path):
    """Teste E2E: get_resource via stdio com servidor mock."""
    client = MCPServerClient(
        server_url=f"stdio://{sys.executable} {mock_mcp_server_path}",
        transport="stdio",
        timeout_seconds=10,
    )

    async with client:
        resource = await client.get_resource("file:///test/config.yaml")

    assert resource.uri == "file:///test/config.yaml"
    assert resource.mimeType == "text/plain"
    assert "config.yaml" in resource.text


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_stdio_list_prompts_with_mock_server(mock_mcp_server_path):
    """Teste E2E: list_prompts via stdio com servidor mock."""
    client = MCPServerClient(
        server_url=f"stdio://{sys.executable} {mock_mcp_server_path}",
        transport="stdio",
        timeout_seconds=10,
    )

    async with client:
        prompts = await client.list_prompts()

    assert len(prompts) == 1
    assert prompts[0].name == "test_prompt"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_stdio_multiple_requests_sequential(mock_mcp_server_path):
    """Teste E2E: múltiplas requisições sequenciais via stdio."""
    client = MCPServerClient(
        server_url=f"stdio://{sys.executable} {mock_mcp_server_path}",
        transport="stdio",
        timeout_seconds=10,
    )

    async with client:
        # Primeira requisição
        tools = await client.list_tools()
        assert len(tools) == 2

        # Segunda requisição
        result1 = await client.call_tool("echo_tool", {"text": "first"})
        assert result1.content[0].text == "first"

        # Terceira requisição
        result2 = await client.call_tool("echo_tool", {"text": "second"})
        assert result2.content[0].text == "second"

        # Quarta requisição
        prompts = await client.list_prompts()
        assert len(prompts) == 1


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_stdio_subprocess_restart_on_failure(mock_mcp_server_path):
    """Teste E2E: verificar que subprocess reinicia em caso de falha."""
    client = MCPServerClient(
        server_url=f"stdio://{sys.executable} {mock_mcp_server_path}",
        transport="stdio",
        timeout_seconds=10,
    )

    async with client:
        # Primeira requisição bem sucedida
        tools1 = await client.list_tools()
        assert len(tools1) == 2

        # Forçar término do processo
        if client._process:
            client._process.kill()
            await client._process.wait()

        # Próxima requisição deve reiniciar subprocess
        tools2 = await client.list_tools()
        assert len(tools2) == 2
