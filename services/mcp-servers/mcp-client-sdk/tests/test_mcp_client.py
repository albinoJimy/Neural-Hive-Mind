"""
Testes para MCP Client SDK.

TDD: Testes escritos antes da implementação.
Espec: @.agent-os/specs/2026-03-18-gaps-06-mcp-integration/
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestMCPClient:
    """Testes da classe MCPClient."""

    def test_mcp_client_init_with_server_url(self):
        """Testa inicialização com URL do servidor."""
        from src.mcp_client_sdk.client import MCPClient

        client = MCPClient(server_url="http://localhost:3010")

        assert client.server_url == "http://localhost:3010"
        assert client.timeout == 30

    def test_mcp_client_init_with_custom_timeout(self):
        """Testa inicialização com timeout customizado."""
        from src.mcp_client_sdk.client import MCPClient

        client = MCPClient(server_url="http://localhost:3010", timeout=60)

        assert client.timeout == 60

    def test_mcp_client_init_with_headers(self):
        """Testa inicialização com headers customizados."""
        from src.mcp_client_sdk.client import MCPClient

        headers = {"Authorization": "Bearer token123"}
        client = MCPClient(server_url="http://localhost:3010", headers=headers)

        assert client.headers == headers

    @pytest.mark.asyncio
    async def test_list_tools_returns_available_tools(self):
        """Testa que lista ferramentas disponíveis."""
        from src.mcp_client_sdk.client import MCPClient

        client = MCPClient(server_url="http://localhost:3010")

        # Mock HTTP response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "tools": [
                {"name": "list_files", "description": "List files"},
                {"name": "search_code", "description": "Search code"},
            ]
        }

        with patch("httpx.AsyncClient.get", return_value=mock_response):
            tools = await client.list_tools()

        assert len(tools) == 2
        assert tools[0]["name"] == "list_files"
        assert tools[1]["name"] == "search_code"

    @pytest.mark.asyncio
    async def test_execute_tool_calls_tool_with_params(self):
        """Testa execução de ferramenta com parâmetros."""
        from src.mcp_client_sdk.client import MCPClient

        client = MCPClient(server_url="http://localhost:3010")

        # Mock HTTP response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": {"files": ["file1.py", "file2.py"]}}

        with patch("httpx.AsyncClient.post", return_value=mock_response) as mock_post:
            result = await client.execute_tool(
                tool_name="list_files", params={"path": "/src", "pattern": "*.py"}
            )

        mock_post.assert_called_once()
        assert result["result"]["files"] == ["file1.py", "file2.py"]

    @pytest.mark.asyncio
    async def test_execute_tool_raises_on_http_error(self):
        """Testa erro HTTP na execução de ferramenta."""
        from src.mcp_client_sdk.client import MCPClient

        client = MCPClient(server_url="http://localhost:3010")

        # Mock HTTP error response
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch("httpx.AsyncClient.post", side_effect=Exception("HTTP 500")):
            with pytest.raises(Exception):
                await client.execute_tool(tool_name="list_files", params={})

    @pytest.mark.asyncio
    async def test_execute_batch_runs_tools_in_parallel(self):
        """Testa execução em lote de ferramentas em paralelo."""
        from src.mcp_client_sdk.client import MCPClient

        client = MCPClient(server_url="http://localhost:3010")

        # Mock HTTP responses
        mock_response_1 = MagicMock()
        mock_response_1.status_code = 200
        mock_response_1.json.return_value = {"result": {"count": 5}}

        mock_response_2 = MagicMock()
        mock_response_2.status_code = 200
        mock_response_2.json.return_value = {"result": {"files": ["a.py"]}}

        call_count = 0

        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return mock_response_1 if call_count == 1 else mock_response_2

        with patch("httpx.AsyncClient.post", side_effect=mock_post):
            results = await client.execute_batch(
                [
                    {"tool_name": "analyze_structure", "params": {"path": "/src"}},
                    {"tool_name": "list_files", "params": {"path": "/src"}},
                ]
            )

        assert len(results) == 2
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_execute_batch_returns_results_in_order(self):
        """Testa que resultados retornam na ordem de solicitação."""
        from src.mcp_client_sdk.client import MCPClient

        client = MCPClient(server_url="http://localhost:3010")

        # Mock HTTP responses
        mock_responses = [
            MagicMock(status_code=200, json=lambda: {"result": {"id": 1}}),
            MagicMock(status_code=200, json=lambda: {"result": {"id": 2}}),
            MagicMock(status_code=200, json=lambda: {"result": {"id": 3}}),
        ]

        with patch("httpx.AsyncClient.post", side_effect=mock_responses):
            results = await client.execute_batch(
                [
                    {"tool_name": "tool1", "params": {}},
                    {"tool_name": "tool2", "params": {}},
                    {"tool_name": "tool3", "params": {}},
                ]
            )

        assert results[0]["result"]["id"] == 1
        assert results[1]["result"]["id"] == 2
        assert results[2]["result"]["id"] == 3


class TestMCPClientConfig:
    """Testes de configuração do MCP Client."""

    def test_default_config_values(self):
        """Testa valores padrão de configuração."""
        from src.mcp_client_sdk.config import get_config

        config = get_config()

        assert config.default_timeout == 30
        assert config.max_retries == 3
        assert config.connection_pool_size == 10

    def test_config_from_env_variables(self):
        """Testa configuração via variáveis de ambiente."""
        from src.mcp_client_sdk.config import get_config

        # Reset config instance
        import src.mcp_client_sdk.config as config_module

        config_module._config_instance = None

        with patch.dict(
            "os.environ",
            {
                "MCP_CLIENT_TIMEOUT": "60",
                "MCP_CLIENT_MAX_RETRIES": "5",
            },
            clear=False,
        ):
            config = get_config()

        assert config.default_timeout == 60
        assert config.max_retries == 5

        # Reset again
        config_module._config_instance = None


class TestMCPClientErrors:
    """Testes de tratamento de erros do MCP Client."""

    @pytest.mark.asyncio
    async def test_connection_error_raises_mcp_error(self):
        """Testa erro de conexão."""
        from src.mcp_client_sdk.client import MCPClient, MCPConnectionError
        import httpx

        client = MCPClient(server_url="http://invalid:9999")

        # Mock the entire AsyncClient context manager
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.ConnectError("Connection refused")

        async def mock_get_client(*args, **kwargs):
            return mock_client

        with patch("httpx.AsyncClient.__aenter__", return_value=mock_client):
            with patch("httpx.AsyncClient.__aexit__", return_value=None):
                with pytest.raises(MCPConnectionError):
                    await client.list_tools()

    @pytest.mark.asyncio
    async def test_timeout_error_raises_mcp_error(self):
        """Testa erro de timeout."""
        from src.mcp_client_sdk.client import MCPClient, MCPTimeoutError
        import httpx

        client = MCPClient(server_url="http://localhost:3010", timeout=1)

        # Mock the entire AsyncClient context manager
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.TimeoutException("Timeout")

        async def mock_get_client(*args, **kwargs):
            return mock_client

        with patch("httpx.AsyncClient.__aenter__", return_value=mock_client):
            with patch("httpx.AsyncClient.__aexit__", return_value=None):
                with pytest.raises(MCPTimeoutError):
                    await client.list_tools()

    @pytest.mark.asyncio
    async def test_invalid_response_raises_mcp_error(self):
        """Testa resposta inválida."""
        from src.mcp_client_sdk.client import MCPClient, MCPResponseError

        client = MCPClient(server_url="http://localhost:3010")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = json.JSONDecodeError("Invalid", "", 0)

        with patch("httpx.AsyncClient.get", return_value=mock_response):
            with pytest.raises(MCPResponseError):
                await client.list_tools()
