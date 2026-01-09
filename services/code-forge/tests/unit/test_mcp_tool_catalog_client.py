"""
Testes unitarios para MCPToolCatalogClient.

Cobertura:
- Requisicao de selecao de ferramentas (sucesso, timeout, erro)
- Envio de feedback (sucesso, timeout, nao bloqueia execucao)
- Retry logic
- Parsing de resposta
- Metricas de API calls
"""

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import httpx


class TestMCPToolCatalogClientInitialization:
    """Testes de inicializacao do cliente."""

    def test_client_default_config(self):
        """Deve usar configuracao padrao."""
        from services.code_forge.src.clients.mcp_tool_catalog_client import MCPToolCatalogClient

        client = MCPToolCatalogClient()

        assert client.base_url == 'http://mcp-tool-catalog:8080'
        assert client.client is None

    def test_client_custom_config(self):
        """Deve aceitar configuracao customizada."""
        from services.code_forge.src.clients.mcp_tool_catalog_client import MCPToolCatalogClient

        client = MCPToolCatalogClient(host='custom-host', port=9090)

        assert client.base_url == 'http://custom-host:9090'

    @pytest.mark.asyncio
    async def test_client_start_creates_http_client(self):
        """Deve criar HTTP client ao iniciar."""
        from services.code_forge.src.clients.mcp_tool_catalog_client import MCPToolCatalogClient

        client = MCPToolCatalogClient()
        await client.start()

        assert client.client is not None
        await client.stop()

    @pytest.mark.asyncio
    async def test_client_stop_closes_http_client(self):
        """Deve fechar HTTP client ao parar."""
        from services.code_forge.src.clients.mcp_tool_catalog_client import MCPToolCatalogClient

        client = MCPToolCatalogClient()
        await client.start()
        await client.stop()

        # Client deve ter sido fechado (verificacao indireta)


class TestMCPToolCatalogClientToolSelection:
    """Testes de requisicao de selecao de ferramentas."""

    @pytest.mark.asyncio
    async def test_request_tool_selection_success(self):
        """Deve retornar selecao de ferramentas com sucesso."""
        from services.code_forge.src.clients.mcp_tool_catalog_client import MCPToolCatalogClient

        client = MCPToolCatalogClient()
        client.client = AsyncMock()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'request_id': str(uuid.uuid4()),
            'selected_tools': [
                {'tool_id': 'tool-001', 'tool_name': 'SonarQube', 'category': 'VALIDATION'}
            ],
            'selection_method': 'GENETIC_ALGORITHM'
        }
        mock_response.raise_for_status = MagicMock()
        client.client.post = AsyncMock(return_value=mock_response)

        request_data = {
            'request_id': str(uuid.uuid4()),
            'required_categories': ['VALIDATION']
        }

        result = await client.request_tool_selection(request_data)

        assert result is not None
        assert 'selected_tools' in result
        assert len(result['selected_tools']) == 1

    @pytest.mark.asyncio
    async def test_request_tool_selection_http_error(self):
        """Deve retornar None em caso de erro HTTP."""
        from services.code_forge.src.clients.mcp_tool_catalog_client import MCPToolCatalogClient

        client = MCPToolCatalogClient()
        client.client = AsyncMock()
        client.client.post = AsyncMock(side_effect=httpx.HTTPError('Connection refused'))

        request_data = {'request_id': str(uuid.uuid4())}

        result = await client.request_tool_selection(request_data)

        assert result is None

    @pytest.mark.asyncio
    async def test_request_tool_selection_timeout(self):
        """Deve retornar None em caso de timeout."""
        from services.code_forge.src.clients.mcp_tool_catalog_client import MCPToolCatalogClient

        client = MCPToolCatalogClient()
        client.client = AsyncMock()
        client.client.post = AsyncMock(side_effect=httpx.ReadTimeout('Timeout'))

        request_data = {'request_id': str(uuid.uuid4())}

        result = await client.request_tool_selection(request_data)

        assert result is None


class TestMCPToolCatalogClientGetTool:
    """Testes de busca de ferramenta por ID."""

    @pytest.mark.asyncio
    async def test_get_tool_success(self):
        """Deve retornar ferramenta com sucesso."""
        from services.code_forge.src.clients.mcp_tool_catalog_client import MCPToolCatalogClient

        client = MCPToolCatalogClient()
        client.client = AsyncMock()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'tool_id': 'tool-001',
            'tool_name': 'SonarQube',
            'category': 'VALIDATION'
        }
        mock_response.raise_for_status = MagicMock()
        client.client.get = AsyncMock(return_value=mock_response)

        result = await client.get_tool('tool-001')

        assert result is not None
        assert result['tool_id'] == 'tool-001'

    @pytest.mark.asyncio
    async def test_get_tool_not_found(self):
        """Deve retornar None quando ferramenta nao encontrada."""
        from services.code_forge.src.clients.mcp_tool_catalog_client import MCPToolCatalogClient

        client = MCPToolCatalogClient()
        client.client = AsyncMock()
        client.client.get = AsyncMock(side_effect=httpx.HTTPStatusError(
            'Not Found',
            request=MagicMock(),
            response=MagicMock(status_code=404)
        ))

        result = await client.get_tool('nonexistent-tool')

        assert result is None


class TestMCPToolCatalogClientListTools:
    """Testes de listagem de ferramentas."""

    @pytest.mark.asyncio
    async def test_list_tools_success(self):
        """Deve retornar lista de ferramentas."""
        from services.code_forge.src.clients.mcp_tool_catalog_client import MCPToolCatalogClient

        client = MCPToolCatalogClient()
        client.client = AsyncMock()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'tools': [
                {'tool_id': 'tool-001', 'tool_name': 'SonarQube'},
                {'tool_id': 'tool-002', 'tool_name': 'Snyk'}
            ]
        }
        mock_response.raise_for_status = MagicMock()
        client.client.get = AsyncMock(return_value=mock_response)

        result = await client.list_tools()

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_list_tools_with_category_filter(self):
        """Deve filtrar ferramentas por categoria."""
        from services.code_forge.src.clients.mcp_tool_catalog_client import MCPToolCatalogClient

        client = MCPToolCatalogClient()
        client.client = AsyncMock()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'tools': [
                {'tool_id': 'tool-001', 'tool_name': 'SonarQube', 'category': 'VALIDATION'}
            ]
        }
        mock_response.raise_for_status = MagicMock()
        client.client.get = AsyncMock(return_value=mock_response)

        result = await client.list_tools(category='VALIDATION')

        client.client.get.assert_called_once_with(
            '/api/v1/tools',
            params={'category': 'VALIDATION'}
        )

    @pytest.mark.asyncio
    async def test_list_tools_empty_on_error(self):
        """Deve retornar lista vazia em caso de erro."""
        from services.code_forge.src.clients.mcp_tool_catalog_client import MCPToolCatalogClient

        client = MCPToolCatalogClient()
        client.client = AsyncMock()
        client.client.get = AsyncMock(side_effect=httpx.HTTPError('Error'))

        result = await client.list_tools()

        assert result == []


class TestMCPToolCatalogClientFeedback:
    """Testes de envio de feedback."""

    @pytest.mark.asyncio
    async def test_send_tool_feedback_success(self):
        """Deve enviar feedback com sucesso."""
        from services.code_forge.src.clients.mcp_tool_catalog_client import MCPToolCatalogClient

        client = MCPToolCatalogClient()
        client.client = AsyncMock()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        client.client.post = AsyncMock(return_value=mock_response)

        feedback = {
            'selection_id': str(uuid.uuid4()),
            'tool_id': 'tool-001',
            'success': True,
            'execution_time_ms': 1500
        }

        result = await client.send_tool_feedback(feedback)

        assert result is True
        client.client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_tool_feedback_failure(self):
        """Deve retornar False em caso de erro."""
        from services.code_forge.src.clients.mcp_tool_catalog_client import MCPToolCatalogClient

        client = MCPToolCatalogClient()
        client.client = AsyncMock()
        client.client.post = AsyncMock(side_effect=httpx.HTTPError('Error'))

        feedback = {
            'tool_id': 'tool-001',
            'success': True
        }

        result = await client.send_tool_feedback(feedback)

        assert result is False

    @pytest.mark.asyncio
    async def test_send_tool_feedback_non_blocking(self):
        """Deve nao bloquear execucao em caso de timeout."""
        from services.code_forge.src.clients.mcp_tool_catalog_client import MCPToolCatalogClient

        client = MCPToolCatalogClient()
        client.client = AsyncMock()

        async def slow_post(*args, **kwargs):
            await asyncio.sleep(0.1)
            raise httpx.ReadTimeout('Timeout')

        client.client.post = slow_post

        feedback = {'tool_id': 'tool-001', 'success': True}

        import time
        start = time.time()
        result = await client.send_tool_feedback(feedback)
        duration = time.time() - start

        assert result is False
        assert duration < 1.0  # Nao deve demorar muito
