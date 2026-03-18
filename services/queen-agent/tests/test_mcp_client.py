"""
Testes para MCPClient.
"""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from src.clients.mcp_client import (
    MCPClient,
    HTTPMCPClient,
    MCPClientError,
    MCPConnectionError,
    MCPToolExecutionError,
    MCPTool,
    MCPServerInfo,
    MCPClientFactory,
)


@pytest.fixture
def mock_settings():
    """Mock de configurações."""
    settings = MagicMock()
    settings.MCP_SCOUT_SERVER_URL = "http://scout-mcp:3000"
    settings.MCP_OPTIMIZER_SERVER_URL = "http://optimizer-mcp:3000"
    settings.MCP_TIMEOUT = 30.0
    return settings


@pytest_asyncio.fixture
async def mock_http_response():
    """Mock de resposta HTTP."""
    response = MagicMock()
    response.status_code = 200
    response.json = MagicMock(return_value={"result": {"data": "test"}})
    response.raise_for_status = MagicMock()
    return response


@pytest.mark.asyncio
async def test_mcp_client_connect_success():
    """Testa conexão bem-sucedida com servidor MCP."""
    client = MCPClient(server_url="http://localhost:3000")

    # Mock HTTP client
    mock_http_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(
        return_value={
            "result": {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "Test Server", "version": "1.0.0"},
            }
        }
    )
    mock_response.raise_for_status = MagicMock()
    mock_http_client.post = AsyncMock(return_value=mock_response)
    mock_http_client.aclose = AsyncMock()

    with patch("httpx.AsyncClient", return_value=mock_http_client):
        await client.connect()

        assert client.is_connected()
        assert client.server_info is not None
        assert client.server_info.name == "Test Server"
        assert client.server_info.version == "1.0.0"

        await client.close()


@pytest.mark.asyncio
async def test_mcp_client_list_tools():
    """Testa listagem de ferramentas disponíveis."""
    client = MCPClient(server_url="http://localhost:3000")

    # Mock HTTP client
    mock_http_client = AsyncMock()

    # Mock initialize response
    init_response = MagicMock()
    init_response.status_code = 200
    init_response.json = MagicMock(
        return_value={
            "result": {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "Test", "version": "1.0"},
            }
        }
    )
    init_response.raise_for_status = MagicMock()

    # Mock tools/list response
    tools_response = MagicMock()
    tools_response.status_code = 200
    tools_response.json = MagicMock(
        return_value={
            "result": {
                "tools": [
                    {
                        "name": "scan_code",
                        "description": "Scans code for vulnerabilities",
                        "inputSchema": {"type": "object"},
                    },
                    {
                        "name": "analyze_performance",
                        "description": "Analyzes code performance",
                        "inputSchema": {"type": "object"},
                    },
                ]
            }
        }
    )
    tools_response.raise_for_status = MagicMock()

    mock_http_client.post = AsyncMock(side_effect=[init_response, tools_response])
    mock_http_client.aclose = AsyncMock()

    with patch("httpx.AsyncClient", return_value=mock_http_client):
        await client.connect()

        tools = await client.list_tools()

        assert len(tools) == 2
        assert tools[0]["name"] == "scan_code"
        assert tools[1]["name"] == "analyze_performance"
        assert client.tools_count == 2

        await client.close()


@pytest.mark.asyncio
async def test_mcp_client_execute_tool_success():
    """Testa execução bem-sucedida de ferramenta."""
    client = MCPClient(server_url="http://localhost:3000")

    # Mock HTTP client
    mock_http_client = AsyncMock()

    # Mock responses
    init_response = MagicMock()
    init_response.status_code = 200
    init_response.json = MagicMock(
        return_value={
            "result": {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "Test", "version": "1.0"},
            }
        }
    )
    init_response.raise_for_status = MagicMock()

    tools_response = MagicMock()
    tools_response.status_code = 200
    tools_response.json = MagicMock(return_value={"result": {"tools": []}})
    tools_response.raise_for_status = MagicMock()

    execute_response = MagicMock()
    execute_response.status_code = 200
    execute_response.json = MagicMock(
        return_value={
            "result": {
                "output": "Scan complete, no vulnerabilities found",
                "exitCode": 0,
            }
        }
    )
    execute_response.raise_for_status = MagicMock()

    mock_http_client.post = AsyncMock(
        side_effect=[init_response, tools_response, execute_response]
    )
    mock_http_client.aclose = AsyncMock()

    with patch("httpx.AsyncClient", return_value=mock_http_client):
        await client.connect()

        # Manually add tool for testing
        from src.clients.mcp_client import MCPTool
        client._tools["scan_code"] = MCPTool(
            name="scan_code",
            description="Scan code",
            input_schema={}
        )

        result = await client.execute_tool(
            tool_name="scan_code",
            arguments={"path": "/app/src"}
        )

        assert result["output"] == "Scan complete, no vulnerabilities found"
        assert result["exitCode"] == 0

        await client.close()


@pytest.mark.asyncio
async def test_mcp_client_execute_tool_not_found():
    """Testa erro ao executar ferramenta inexistente."""
    client = MCPClient(server_url="http://localhost:3000")

    # Mock minimal connect
    mock_http_client = AsyncMock()
    init_response = MagicMock()
    init_response.status_code = 200
    init_response.json = MagicMock(
        return_value={
            "result": {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "Test", "version": "1.0"},
            }
        }
    )
    init_response.raise_for_status = MagicMock()

    mock_http_client.post = AsyncMock(return_value=init_response)
    mock_http_client.aclose = AsyncMock()

    with patch("httpx.AsyncClient", return_value=mock_http_client):
        await client.connect()

        with pytest.raises(ValueError, match="Tool not found"):
            await client.execute_tool(
                tool_name="nonexistent_tool",
                arguments={}
            )

        await client.close()


@pytest.mark.asyncio
async def test_mcp_client_execute_tool_http_error():
    """Testa tratamento de erro HTTP na execução."""
    client = MCPClient(server_url="http://localhost:3000")

    mock_http_client = AsyncMock()

    # Init
    init_response = MagicMock()
    init_response.status_code = 200
    init_response.json = MagicMock(
        return_value={
            "result": {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "Test", "version": "1.0"},
            }
        }
    )
    init_response.raise_for_status = MagicMock()

    # Tools
    tools_response = MagicMock()
    tools_response.status_code = 200
    tools_response.json = MagicMock(return_value={"result": {"tools": []}})
    tools_response.raise_for_status = MagicMock()

    # Execute error
    error_response = MagicMock()
    error_response.status_code = 500
    error_response.text = "Internal Server Error"
    error_response.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError(
            "Server error", request=MagicMock(), response=error_response
        )
    )

    mock_http_client.post = AsyncMock(
        side_effect=[init_response, tools_response, error_response]
    )
    mock_http_client.aclose = AsyncMock()

    with patch("httpx.AsyncClient", return_value=mock_http_client):
        await client.connect()

        # Add tool manually
        from src.clients.mcp_client import MCPTool
        client._tools["scan"] = MCPTool(
            name="scan",
            description="Scan",
            input_schema={}
        )

        with pytest.raises(MCPToolExecutionError, match="HTTP error"):
            await client.execute_tool(tool_name="scan", arguments={})

        await client.close()


@pytest.mark.asyncio
async def test_mcp_client_connection_error():
    """Testa erro ao conectar com servidor indisponível."""
    client = MCPClient(server_url="http://unavailable:3000")

    mock_http_client = AsyncMock()
    mock_http_client.post = AsyncMock(side_effect=ConnectionError("Connection refused"))
    mock_http_client.aclose = AsyncMock()

    with patch("httpx.AsyncClient", return_value=mock_http_client):
        with pytest.raises(MCPConnectionError, match="Failed to connect"):
            await client.connect()


@pytest.mark.asyncio
async def test_mcp_client_json_rpc_error():
    """Testa tratamento de erro JSON-RPC."""
    client = MCPClient(server_url="http://localhost:3000")

    mock_http_client = AsyncMock()

    # Init
    init_response = MagicMock()
    init_response.status_code = 200
    init_response.json = MagicMock(
        return_value={
            "result": {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "Test", "version": "1.0"},
            }
        }
    )
    init_response.raise_for_status = MagicMock()

    # Tools
    tools_response = MagicMock()
    tools_response.status_code = 200
    tools_response.json = MagicMock(return_value={"result": {"tools": []}})
    tools_response.raise_for_status = MagicMock()

    # JSON-RPC error
    error_response = MagicMock()
    error_response.status_code = 200
    error_response.json = MagicMock(
        return_value={
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32601, "message": "Method not found"}
        }
    )
    error_response.raise_for_status = MagicMock()

    mock_http_client.post = AsyncMock(
        side_effect=[init_response, tools_response, error_response]
    )
    mock_http_client.aclose = AsyncMock()

    with patch("httpx.AsyncClient", return_value=mock_http_client):
        await client.connect()

        # Add tool
        from src.clients.mcp_client import MCPTool
        client._tools["test"] = MCPTool(
            name="test",
            description="Test",
            input_schema={}
        )

        # O erro JSON-RPC é wrapped em MCPToolExecutionError
        with pytest.raises(MCPToolExecutionError, match="Tool execution failed"):
            await client.execute_tool(tool_name="test", arguments={})

        await client.close()


@pytest.mark.asyncio
async def test_mcp_client_not_connected():
    """Testa erro quando cliente não está conectado."""
    client = MCPClient(server_url="http://localhost:3000")

    with pytest.raises(MCPConnectionError, match="Client not connected"):
        await client.list_tools()


@pytest.mark.asyncio
async def test_mcp_client_get_tool():
    """Testa obtenção de informações de ferramenta específica."""
    client = MCPClient(server_url="http://localhost:3000")

    mock_http_client = AsyncMock()

    init_response = MagicMock()
    init_response.status_code = 200
    init_response.json = MagicMock(
        return_value={
            "result": {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "Test", "version": "1.0"},
            }
        }
    )
    init_response.raise_for_status = MagicMock()

    tools_response = MagicMock()
    tools_response.status_code = 200
    tools_response.json = MagicMock(
        return_value={
            "result": {
                "tools": [
                    {
                        "name": "scan_code",
                        "description": "Scan code",
                        "inputSchema": {"type": "object"},
                    }
                ]
            }
        }
    )
    tools_response.raise_for_status = MagicMock()

    mock_http_client.post = AsyncMock(
        side_effect=[init_response, tools_response]
    )
    mock_http_client.aclose = AsyncMock()

    with patch("httpx.AsyncClient", return_value=mock_http_client):
        await client.connect()

        tool = client.get_tool("scan_code")

        assert tool is not None
        assert tool.name == "scan_code"
        assert tool.description == "Scan code"

        # Tool inexistente
        assert client.get_tool("nonexistent") is None

        await client.close()


@pytest.mark.asyncio
async def test_mcp_client_close_without_connect():
    """Testa close sem conexão prévia."""
    client = MCPClient(server_url="http://localhost:3000")

    # Não deve levantar exceção
    await client.close()
    assert not client.is_connected()


# ============ HTTPMCPClient Tests ============

@pytest.mark.asyncio
async def test_http_mcp_client_connect_success():
    """Testa conexão bem-sucedida com servidor HTTP MCP."""
    client = HTTPMCPClient(server_url="http://localhost:8080")

    mock_http_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(
        return_value={
            "status": "healthy",
            "server": "Scout HTTP Server",
            "version": "1.0.0"
        }
    )
    mock_response.raise_for_status = MagicMock()
    mock_http_client.get = AsyncMock(return_value=mock_response)
    mock_http_client.aclose = AsyncMock()

    with patch("httpx.AsyncClient", return_value=mock_http_client):
        await client.connect()

        assert client.is_connected()
        assert client.server_info is not None
        assert client.server_info.name == "Scout HTTP Server"
        assert client.server_info.version == "1.0.0"

        await client.close()


@pytest.mark.asyncio
async def test_http_mcp_client_list_tools():
    """Testa listagem de ferramentas via REST."""
    client = HTTPMCPClient(server_url="http://localhost:8080")

    mock_http_client = AsyncMock()

    # Mock health response
    health_response = MagicMock()
    health_response.status_code = 200
    health_response.json = MagicMock(
        return_value={
            "status": "healthy",
            "server": "Scout HTTP Server",
            "version": "1.0.0"
        }
    )
    health_response.raise_for_status = MagicMock()

    # Mock tools response
    tools_response = MagicMock()
    tools_response.status_code = 200
    tools_response.json = MagicMock(
        return_value={
            "tools": [
                {"name": "scan_directory", "description": "Scan directory"},
                {"name": "find_files", "description": "Find files"},
            ]
        }
    )
    tools_response.raise_for_status = MagicMock()

    mock_http_client.get = AsyncMock(
        side_effect=[health_response, tools_response]
    )
    mock_http_client.aclose = AsyncMock()

    with patch("httpx.AsyncClient", return_value=mock_http_client):
        await client.connect()

        tools = await client.list_tools()

        assert len(tools) == 2
        assert tools[0]["name"] == "scan_directory"
        assert tools[1]["name"] == "find_files"

        await client.close()


@pytest.mark.asyncio
async def test_http_mcp_client_execute_tool_success():
    """Testa execução de ferramenta via POST /execute."""
    client = HTTPMCPClient(server_url="http://localhost:8080")

    mock_http_client = AsyncMock()

    # Health
    health_response = MagicMock()
    health_response.status_code = 200
    health_response.json = MagicMock(
        return_value={"status": "healthy", "server": "Test", "version": "1.0"}
    )
    health_response.raise_for_status = MagicMock()

    # Tools
    tools_response = MagicMock()
    tools_response.status_code = 200
    tools_response.json = MagicMock(
        return_value={"tools": [{"name": "scan", "description": "Scan"}]}
    )
    tools_response.raise_for_status = MagicMock()

    # Execute
    exec_response = MagicMock()
    exec_response.status_code = 200
    exec_response.json = MagicMock(
        return_value={
            "total_files": 10,
            "total_dirs": 2,
            "languages": {"python": 10}
        }
    )
    exec_response.raise_for_status = MagicMock()

    mock_http_client.get = AsyncMock(
        side_effect=[health_response, tools_response]
    )
    mock_http_client.post = AsyncMock(return_value=exec_response)
    mock_http_client.aclose = AsyncMock()

    with patch("httpx.AsyncClient", return_value=mock_http_client):
        await client.connect()

        result = await client.execute_tool(
            tool_name="scan",
            arguments={"path": "/repo", "max_depth": 3}
        )

        assert result["total_files"] == 10
        assert result["languages"]["python"] == 10

        await client.close()


@pytest.mark.asyncio
async def test_http_mcp_client_execute_tool_not_found():
    """Testa erro ao executar ferramenta inexistente."""
    client = HTTPMCPClient(server_url="http://localhost:8080")

    mock_http_client = AsyncMock()

    health_response = MagicMock()
    health_response.status_code = 200
    health_response.json = MagicMock(
        return_value={"status": "healthy", "server": "Test", "version": "1.0"}
    )
    health_response.raise_for_status = MagicMock()

    tools_response = MagicMock()
    tools_response.status_code = 200
    tools_response.json = MagicMock(return_value={"tools": []})
    tools_response.raise_for_status = MagicMock()

    mock_http_client.get = AsyncMock(
        side_effect=[health_response, tools_response]
    )
    mock_http_client.aclose = AsyncMock()

    with patch("httpx.AsyncClient", return_value=mock_http_client):
        await client.connect()

        with pytest.raises(ValueError, match="Tool not found"):
            await client.execute_tool(tool_name="nonexistent", arguments={})

        await client.close()


@pytest.mark.asyncio
async def test_http_mcp_client_connection_error():
    """Testa erro ao conectar com servidor indisponível."""
    client = HTTPMCPClient(server_url="http://unavailable:8080")

    mock_http_client = AsyncMock()
    mock_http_client.get = AsyncMock(side_effect=ConnectionError("Connection refused"))
    mock_http_client.aclose = AsyncMock()

    with patch("httpx.AsyncClient", return_value=mock_http_client):
        with pytest.raises(MCPConnectionError, match="Failed to connect"):
            await client.connect()


@pytest.mark.asyncio
async def test_http_mcp_client_tools_count():
    """Testa contagem de ferramentas disponíveis."""
    client = HTTPMCPClient(server_url="http://localhost:8080")

    mock_http_client = AsyncMock()

    health_response = MagicMock()
    health_response.status_code = 200
    health_response.json = MagicMock(
        return_value={"status": "healthy", "server": "Test", "version": "1.0"}
    )
    health_response.raise_for_status = MagicMock()

    tools_response = MagicMock()
    tools_response.status_code = 200
    tools_response.json = MagicMock(
        return_value={
            "tools": [
                {"name": "tool1", "description": "Tool 1"},
                {"name": "tool2", "description": "Tool 2"},
                {"name": "tool3", "description": "Tool 3"},
            ]
        }
    )
    tools_response.raise_for_status = MagicMock()

    mock_http_client.get = AsyncMock(
        side_effect=[health_response, tools_response]
    )
    mock_http_client.aclose = AsyncMock()

    with patch("httpx.AsyncClient", return_value=mock_http_client):
        await client.connect()

        assert client.tools_count == 3

        await client.close()
