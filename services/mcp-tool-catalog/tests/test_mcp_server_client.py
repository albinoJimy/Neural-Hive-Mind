"""Testes unitários para MCPServerClient."""
import asyncio
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aioresponses import aioresponses

from src.clients.mcp_exceptions import (
    MCPProtocolError,
    MCPServerError,
    MCPTransportError,
)
from src.clients.mcp_server_client import MCPServerClient


@pytest.fixture
def mcp_client():
    """Cria instância de MCPServerClient para testes."""
    return MCPServerClient(
        server_url="http://test-mcp:3000",
        timeout_seconds=5,
        max_retries=3,
        circuit_breaker_threshold=3,
        circuit_breaker_timeout=10,
    )


@pytest.fixture
def mock_aiohttp():
    """Context manager para mockar requisições aiohttp."""
    with aioresponses() as m:
        yield m


class TestMCPServerClientLifecycle:
    """Testes de ciclo de vida do cliente."""

    @pytest.mark.asyncio
    async def test_start_initializes_session(self, mcp_client):
        """Verifica que start() cria sessão HTTP."""
        assert mcp_client._session is None

        await mcp_client.start()

        assert mcp_client._session is not None
        await mcp_client.stop()

    @pytest.mark.asyncio
    async def test_stop_closes_session(self, mcp_client):
        """Verifica que stop() fecha sessão."""
        await mcp_client.start()
        assert mcp_client._session is not None

        await mcp_client.stop()

        assert mcp_client._session is None

    @pytest.mark.asyncio
    async def test_context_manager(self, mcp_client):
        """Verifica funcionamento como context manager."""
        async with mcp_client as client:
            assert client._session is not None
        assert mcp_client._session is None


class TestListTools:
    """Testes para list_tools()."""

    @pytest.mark.asyncio
    async def test_list_tools_success(self, mcp_client, mock_aiohttp):
        """Mock resposta com 3 ferramentas, verificar parsing."""
        mock_response = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "tools": [
                    {
                        "name": "tool1",
                        "description": "Tool 1 description",
                        "inputSchema": {"type": "object"},
                    },
                    {
                        "name": "tool2",
                        "description": "Tool 2 description",
                        "inputSchema": {"type": "object"},
                    },
                    {
                        "name": "tool3",
                        "description": "Tool 3 description",
                        "inputSchema": {"type": "object"},
                    },
                ]
            },
        }

        mock_aiohttp.post("http://test-mcp:3000", payload=mock_response)

        async with mcp_client:
            tools = await mcp_client.list_tools()

        assert len(tools) == 3
        assert tools[0].name == "tool1"
        assert tools[1].name == "tool2"
        assert tools[2].name == "tool3"

    @pytest.mark.asyncio
    async def test_list_tools_empty(self, mcp_client, mock_aiohttp):
        """Mock resposta com lista vazia, verificar retorno []."""
        mock_response = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"tools": []},
        }

        mock_aiohttp.post("http://test-mcp:3000", payload=mock_response)

        async with mcp_client:
            tools = await mcp_client.list_tools()

        assert tools == []


class TestCallTool:
    """Testes para call_tool()."""

    @pytest.mark.asyncio
    async def test_call_tool_success(self, mcp_client, mock_aiohttp):
        """Mock resposta com content e structuredContent, verificar parsing."""
        mock_response = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "content": [
                    {"type": "text", "text": "Resultado da execução"},
                ],
                "structuredContent": {"status": "success", "data": {"key": "value"}},
                "isError": False,
            },
        }

        mock_aiohttp.post("http://test-mcp:3000", payload=mock_response)

        async with mcp_client:
            response = await mcp_client.call_tool("test_tool", {"arg1": "value1"})

        assert len(response.content) == 1
        assert response.content[0].type == "text"
        assert response.content[0].text == "Resultado da execução"
        assert response.structuredContent == {"status": "success", "data": {"key": "value"}}
        assert response.isError is False

    @pytest.mark.asyncio
    async def test_call_tool_error(self, mcp_client, mock_aiohttp):
        """Mock resposta com isError=True, verificar lançamento de MCPServerError."""
        mock_response = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "content": [{"type": "text", "text": "Error message"}],
                "isError": True,
            },
        }

        mock_aiohttp.post("http://test-mcp:3000", payload=mock_response)

        async with mcp_client:
            with pytest.raises(MCPServerError) as exc_info:
                await mcp_client.call_tool("failing_tool", {})

        assert "failing_tool" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_call_tool_empty_name_raises_valueerror(self, mcp_client):
        """Verificar que tool_name vazio lança ValueError."""
        async with mcp_client:
            with pytest.raises(ValueError) as exc_info:
                await mcp_client.call_tool("", {})

        assert "vazio" in str(exc_info.value)


class TestGetResource:
    """Testes para get_resource()."""

    @pytest.mark.asyncio
    async def test_get_resource_success(self, mcp_client, mock_aiohttp):
        """Mock resposta com uri, mimeType, text, verificar parsing."""
        mock_response = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "contents": [
                    {
                        "uri": "file:///config.yaml",
                        "mimeType": "application/yaml",
                        "text": "key: value\n",
                    }
                ]
            },
        }

        mock_aiohttp.post("http://test-mcp:3000", payload=mock_response)

        async with mcp_client:
            resource = await mcp_client.get_resource("file:///config.yaml")

        assert resource.uri == "file:///config.yaml"
        assert resource.mimeType == "application/yaml"
        assert resource.text == "key: value\n"


class TestListPrompts:
    """Testes para list_prompts()."""

    @pytest.mark.asyncio
    async def test_list_prompts_success(self, mcp_client, mock_aiohttp):
        """Mock resposta com 2 prompts, verificar parsing."""
        mock_response = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "prompts": [
                    {"name": "prompt1", "description": "First prompt"},
                    {"name": "prompt2", "description": "Second prompt"},
                ]
            },
        }

        mock_aiohttp.post("http://test-mcp:3000", payload=mock_response)

        async with mcp_client:
            prompts = await mcp_client.list_prompts()

        assert len(prompts) == 2
        assert prompts[0].name == "prompt1"
        assert prompts[1].name == "prompt2"


class TestRetryMechanism:
    """Testes para mecanismo de retry."""

    @pytest.mark.asyncio
    async def test_send_request_retry_on_timeout(self, mcp_client, mock_aiohttp):
        """Mock timeout na 1ª tentativa, sucesso na 2ª, verificar retry."""
        import aiohttp

        # Primeira chamada: timeout
        mock_aiohttp.post(
            "http://test-mcp:3000",
            exception=asyncio.TimeoutError(),
        )
        # Segunda chamada: sucesso
        mock_aiohttp.post(
            "http://test-mcp:3000",
            payload={
                "jsonrpc": "2.0",
                "id": 2,
                "result": {"tools": []},
            },
        )

        async with mcp_client:
            # Reduzir tempo de backoff para teste
            with patch("asyncio.sleep", new_callable=AsyncMock):
                tools = await mcp_client.list_tools()

        assert tools == []

    @pytest.mark.asyncio
    async def test_send_request_exponential_backoff(self, mcp_client, mock_aiohttp):
        """Verificar delays de 2^attempt segundos entre retries."""
        import asyncio

        sleep_calls = []

        async def mock_sleep(seconds):
            sleep_calls.append(seconds)

        # Simular falhas
        for _ in range(2):
            mock_aiohttp.post(
                "http://test-mcp:3000",
                exception=asyncio.TimeoutError(),
            )
        # Sucesso na terceira
        mock_aiohttp.post(
            "http://test-mcp:3000",
            payload={"jsonrpc": "2.0", "id": 3, "result": {"tools": []}},
        )

        async with mcp_client:
            with patch("asyncio.sleep", side_effect=mock_sleep):
                await mcp_client.list_tools()

        # Backoff: 2^1 = 2, 2^2 = 4
        assert sleep_calls == [2, 4]


class TestCircuitBreaker:
    """Testes para circuit breaker."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_after_threshold(self, mcp_client, mock_aiohttp):
        """Mock 3 falhas consecutivas, verificar circuit breaker abre."""
        # Simular 3 falhas (threshold do fixture)
        for _ in range(3):
            mock_aiohttp.post(
                "http://test-mcp:3000",
                exception=asyncio.TimeoutError(),
            )

        async with mcp_client:
            with patch("asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(MCPTransportError):
                    await mcp_client.list_tools()

        assert mcp_client._circuit_breaker_open_until is not None
        assert mcp_client._circuit_breaker_failures >= mcp_client.circuit_breaker_threshold

    @pytest.mark.asyncio
    async def test_circuit_breaker_prevents_requests(self, mcp_client):
        """Abrir circuit breaker, verificar que próxima requisição lança MCPTransportError."""
        # Abrir circuit breaker manualmente
        mcp_client._circuit_breaker_open_until = datetime.now() + timedelta(seconds=60)
        mcp_client._circuit_breaker_failures = 5

        async with mcp_client:
            with pytest.raises(MCPTransportError) as exc_info:
                await mcp_client.list_tools()

        assert "Circuit breaker open" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_circuit_breaker_closes_after_timeout(self, mcp_client, mock_aiohttp):
        """Abrir circuit breaker, aguardar timeout, verificar que requisição é permitida."""
        # Abrir circuit breaker mas já expirado
        mcp_client._circuit_breaker_open_until = datetime.now() - timedelta(seconds=1)
        mcp_client._circuit_breaker_failures = 5

        mock_aiohttp.post(
            "http://test-mcp:3000",
            payload={"jsonrpc": "2.0", "id": 1, "result": {"tools": []}},
        )

        async with mcp_client:
            tools = await mcp_client.list_tools()

        assert tools == []
        assert mcp_client._circuit_breaker_open_until is None
        assert mcp_client._circuit_breaker_failures == 0


class TestProtocolErrors:
    """Testes para erros de protocolo."""

    @pytest.mark.asyncio
    async def test_invalid_json_response_raises_protocol_error(self, mcp_client, mock_aiohttp):
        """Mock resposta com JSON inválido, verificar MCPProtocolError."""
        mock_aiohttp.post(
            "http://test-mcp:3000",
            body="not valid json{{{",
            content_type="application/json",
        )

        async with mcp_client:
            with pytest.raises(MCPProtocolError) as exc_info:
                await mcp_client.list_tools()

        assert "Invalid JSON" in str(exc_info.value.message)

    @pytest.mark.asyncio
    async def test_missing_result_field_raises_protocol_error(self, mcp_client, mock_aiohttp):
        """Mock resposta sem campo result, verificar erro."""
        mock_aiohttp.post(
            "http://test-mcp:3000",
            payload={"jsonrpc": "2.0", "id": 1},  # Sem 'result'
        )

        async with mcp_client:
            with pytest.raises(MCPProtocolError) as exc_info:
                await mcp_client.list_tools()

        assert "Missing 'result'" in str(exc_info.value.message)

    @pytest.mark.asyncio
    async def test_jsonrpc_error_raises_mcp_server_error(self, mcp_client, mock_aiohttp):
        """Mock resposta com campo error, verificar MCPServerError com código correto."""
        mock_aiohttp.post(
            "http://test-mcp:3000",
            payload={
                "jsonrpc": "2.0",
                "id": 1,
                "error": {
                    "code": -32601,
                    "message": "Method not found",
                    "data": "tools/unknown",
                },
            },
        )

        async with mcp_client:
            with pytest.raises(MCPServerError) as exc_info:
                await mcp_client.list_tools()

        assert exc_info.value.code == -32601

    @pytest.mark.asyncio
    async def test_invalid_jsonrpc_version_raises_protocol_error(self, mcp_client, mock_aiohttp):
        """Mock resposta com jsonrpc diferente de 2.0, verificar MCPProtocolError."""
        mock_aiohttp.post(
            "http://test-mcp:3000",
            payload={
                "jsonrpc": "1.0",  # Versão incorreta
                "id": 1,
                "result": {"tools": []},
            },
        )

        async with mcp_client:
            with pytest.raises(MCPProtocolError) as exc_info:
                await mcp_client.list_tools()

        assert "jsonrpc" in str(exc_info.value.message).lower()

    @pytest.mark.asyncio
    async def test_missing_jsonrpc_version_raises_protocol_error(self, mcp_client, mock_aiohttp):
        """Mock resposta sem campo jsonrpc, verificar MCPProtocolError."""
        mock_aiohttp.post(
            "http://test-mcp:3000",
            payload={
                "id": 1,
                "result": {"tools": []},
            },
        )

        async with mcp_client:
            with pytest.raises(MCPProtocolError) as exc_info:
                await mcp_client.list_tools()

        assert "jsonrpc" in str(exc_info.value.message).lower()

    @pytest.mark.asyncio
    async def test_mismatched_response_id_raises_protocol_error(self, mcp_client, mock_aiohttp):
        """Mock resposta com ID diferente do enviado, verificar MCPProtocolError."""
        mock_aiohttp.post(
            "http://test-mcp:3000",
            payload={
                "jsonrpc": "2.0",
                "id": 999,  # ID diferente do esperado
                "result": {"tools": []},
            },
        )

        async with mcp_client:
            with pytest.raises(MCPProtocolError) as exc_info:
                await mcp_client.list_tools()

        assert "mismatch" in str(exc_info.value.message).lower()

    @pytest.mark.asyncio
    async def test_null_response_id_raises_protocol_error(self, mcp_client, mock_aiohttp):
        """Mock resposta com ID null, verificar MCPProtocolError."""
        mock_aiohttp.post(
            "http://test-mcp:3000",
            payload={
                "jsonrpc": "2.0",
                "id": None,
                "result": {"tools": []},
            },
        )

        async with mcp_client:
            with pytest.raises(MCPProtocolError) as exc_info:
                await mcp_client.list_tools()

        assert "mismatch" in str(exc_info.value.message).lower()


class TestStdioTransport:
    """Testes para transporte stdio."""

    def test_stdio_transport_accepted_in_init(self):
        """Verificar que transporte stdio é aceito na inicialização."""
        client = MCPServerClient(
            server_url="stdio:///usr/bin/mcp-server",
            transport="stdio",
        )
        assert client.transport == "stdio"

    def test_invalid_transport_raises_valueerror(self):
        """Verificar que transporte inválido lança ValueError."""
        with pytest.raises(ValueError) as exc_info:
            MCPServerClient(
                server_url="http://test:3000",
                transport="websocket",  # Não suportado
            )
        assert "websocket" in str(exc_info.value)
        assert "suportado" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_empty_server_url_raises_valueerror(self):
        """Verificar que server_url vazio para stdio lança ValueError."""
        client = MCPServerClient(
            server_url="stdio://",
            transport="stdio",
        )
        with pytest.raises(ValueError) as exc_info:
            await client.start()
        assert "caminho do executável" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_stdio_subprocess_lifecycle(self):
        """Verificar ciclo de vida do subprocess."""
        # Mock subprocess
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.returncode = None
        mock_process.stdin = MagicMock()
        mock_process.stdin.close = MagicMock()
        mock_process.stdin.wait_closed = AsyncMock()
        mock_process.stdout = MagicMock()
        mock_process.stderr = MagicMock()
        mock_process.stderr.readline = AsyncMock(return_value=b"")
        mock_process.wait = AsyncMock(return_value=0)

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_process):
            client = MCPServerClient(
                server_url="stdio:///usr/bin/test-server",
                transport="stdio",
            )

            await client.start()
            assert client._process is not None
            assert client._process.pid == 12345

            await client.stop()
            assert client._process is None

    @pytest.mark.asyncio
    async def test_stdio_list_tools_success(self):
        """Mock subprocess com resposta válida para list_tools."""
        # Mock subprocess
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.returncode = None

        # Mock stdin
        mock_stdin = MagicMock()
        mock_stdin.write = MagicMock()
        mock_stdin.drain = AsyncMock()
        mock_stdin.close = MagicMock()
        mock_stdin.wait_closed = AsyncMock()

        # Mock stdout com resposta JSON-RPC válida
        response_json = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "tools": [
                    {
                        "name": "test_tool",
                        "description": "Test tool",
                        "inputSchema": {"type": "object"},
                    }
                ]
            },
        }) + "\n"
        mock_stdout = MagicMock()
        mock_stdout.readline = AsyncMock(return_value=response_json.encode("utf-8"))

        # Mock stderr
        mock_stderr = MagicMock()
        mock_stderr.readline = AsyncMock(return_value=b"")

        mock_process.stdin = mock_stdin
        mock_process.stdout = mock_stdout
        mock_process.stderr = mock_stderr
        mock_process.wait = AsyncMock(return_value=0)

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_process):
            client = MCPServerClient(
                server_url="stdio:///usr/bin/test-server",
                transport="stdio",
            )

            async with client:
                tools = await client.list_tools()

            assert len(tools) == 1
            assert tools[0].name == "test_tool"

    @pytest.mark.asyncio
    async def test_stdio_call_tool_success(self):
        """Mock subprocess com resposta válida para call_tool."""
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.returncode = None

        mock_stdin = MagicMock()
        mock_stdin.write = MagicMock()
        mock_stdin.drain = AsyncMock()
        mock_stdin.close = MagicMock()
        mock_stdin.wait_closed = AsyncMock()

        response_json = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "content": [{"type": "text", "text": "Execution result"}],
                "isError": False,
            },
        }) + "\n"
        mock_stdout = MagicMock()
        mock_stdout.readline = AsyncMock(return_value=response_json.encode("utf-8"))

        mock_stderr = MagicMock()
        mock_stderr.readline = AsyncMock(return_value=b"")

        mock_process.stdin = mock_stdin
        mock_process.stdout = mock_stdout
        mock_process.stderr = mock_stderr
        mock_process.wait = AsyncMock(return_value=0)

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_process):
            client = MCPServerClient(
                server_url="stdio:///usr/bin/test-server",
                transport="stdio",
            )

            async with client:
                result = await client.call_tool("test_tool", {"arg": "value"})

            assert result.isError is False
            assert len(result.content) == 1
            assert result.content[0].text == "Execution result"

    @pytest.mark.asyncio
    async def test_stdio_subprocess_terminated_raises_error(self):
        """Verificar erro quando subprocess termina inesperadamente."""
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.returncode = 1  # Processo terminou

        mock_stdin = MagicMock()
        mock_stdin.write = MagicMock()
        mock_stdin.drain = AsyncMock()
        mock_stdin.close = MagicMock()
        mock_stdin.wait_closed = AsyncMock()

        mock_stdout = MagicMock()
        mock_stdout.readline = AsyncMock(return_value=b"")  # EOF

        mock_stderr = MagicMock()
        mock_stderr.readline = AsyncMock(return_value=b"")

        mock_process.stdin = mock_stdin
        mock_process.stdout = mock_stdout
        mock_process.stderr = mock_stderr
        mock_process.wait = AsyncMock(return_value=1)

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_process):
            client = MCPServerClient(
                server_url="stdio:///usr/bin/test-server",
                transport="stdio",
                max_retries=1,
            )

            await client.start()
            with patch("asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(MCPTransportError) as exc_info:
                    await client.list_tools()

            assert "terminated" in str(exc_info.value.message).lower()

    @pytest.mark.asyncio
    async def test_stdio_timeout_raises_error(self):
        """Verificar timeout em requisição stdio."""
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.returncode = None

        mock_stdin = MagicMock()
        mock_stdin.write = MagicMock()
        mock_stdin.drain = AsyncMock()
        mock_stdin.close = MagicMock()
        mock_stdin.wait_closed = AsyncMock()

        mock_stdout = MagicMock()
        mock_stdout.readline = AsyncMock(side_effect=asyncio.TimeoutError())

        mock_stderr = MagicMock()
        mock_stderr.readline = AsyncMock(return_value=b"")

        mock_process.stdin = mock_stdin
        mock_process.stdout = mock_stdout
        mock_process.stderr = mock_stderr
        mock_process.wait = AsyncMock(return_value=0)

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_process):
            # Patch asyncio.wait_for para simular timeout
            original_wait_for = asyncio.wait_for

            async def mock_wait_for(coro, timeout):
                raise asyncio.TimeoutError()

            with patch("asyncio.wait_for", side_effect=mock_wait_for):
                client = MCPServerClient(
                    server_url="stdio:///usr/bin/test-server",
                    transport="stdio",
                    timeout_seconds=1,
                    max_retries=1,
                )

                await client.start()
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    with pytest.raises(MCPTransportError) as exc_info:
                        await client.list_tools()

                assert "timeout" in str(exc_info.value.message).lower()

    @pytest.mark.asyncio
    async def test_stdio_invalid_json_raises_protocol_error(self):
        """Verificar erro quando resposta não é JSON válido."""
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.returncode = None

        mock_stdin = MagicMock()
        mock_stdin.write = MagicMock()
        mock_stdin.drain = AsyncMock()
        mock_stdin.close = MagicMock()
        mock_stdin.wait_closed = AsyncMock()

        mock_stdout = MagicMock()
        mock_stdout.readline = AsyncMock(return_value=b"not valid json\n")

        mock_stderr = MagicMock()
        mock_stderr.readline = AsyncMock(return_value=b"")

        mock_process.stdin = mock_stdin
        mock_process.stdout = mock_stdout
        mock_process.stderr = mock_stderr
        mock_process.wait = AsyncMock(return_value=0)

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_process):
            client = MCPServerClient(
                server_url="stdio:///usr/bin/test-server",
                transport="stdio",
            )

            async with client:
                with pytest.raises(MCPProtocolError) as exc_info:
                    await client.list_tools()

            assert "Invalid JSON" in str(exc_info.value.message)

    @pytest.mark.asyncio
    async def test_stdio_circuit_breaker_opens(self):
        """Verificar que circuit breaker abre após falhas consecutivas."""
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.returncode = None

        mock_stdin = MagicMock()
        mock_stdin.write = MagicMock()
        mock_stdin.drain = AsyncMock()
        mock_stdin.close = MagicMock()
        mock_stdin.wait_closed = AsyncMock()

        mock_stdout = MagicMock()
        mock_stdout.readline = AsyncMock(return_value=b"")  # EOF - simula falha

        mock_stderr = MagicMock()
        mock_stderr.readline = AsyncMock(return_value=b"")

        mock_process.stdin = mock_stdin
        mock_process.stdout = mock_stdout
        mock_process.stderr = mock_stderr
        mock_process.wait = AsyncMock(return_value=0)

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_process):
            client = MCPServerClient(
                server_url="stdio:///usr/bin/test-server",
                transport="stdio",
                max_retries=3,
                circuit_breaker_threshold=3,
            )

            await client.start()
            with patch("asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(MCPTransportError):
                    await client.list_tools()

            assert client._circuit_breaker_open_until is not None
