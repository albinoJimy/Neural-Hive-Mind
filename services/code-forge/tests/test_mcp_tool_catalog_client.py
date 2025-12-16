"""Testes unitários para MCPToolCatalogClient"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.clients.mcp_tool_catalog_client import MCPToolCatalogClient


@pytest.fixture
def client():
    c = MCPToolCatalogClient("localhost", 8080)
    c.client = AsyncMock()
    return c


@pytest.mark.asyncio
async def test_request_tool_selection_success(client):
    """Deve retornar dict quando HTTP 200."""
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {"selected_tools": [{"tool_id": "t1"}], "selection_method": "genetic"}
    client.client.post = AsyncMock(return_value=response)

    result = await client.request_tool_selection({"request_id": "123"})

    assert result["selected_tools"][0]["tool_id"] == "t1"
    client.client.post.assert_awaited_once()


@pytest.mark.asyncio
async def test_request_tool_selection_http_error(client):
    """Deve retornar None em erro HTTP."""
    client.client.post = AsyncMock(side_effect=httpx.HTTPError("boom"))

    result = await client.request_tool_selection({"request_id": "123"})

    assert result is None


@pytest.mark.asyncio
async def test_send_tool_feedback_success(client):
    """Deve retornar True quando feedback é enviado."""
    response = MagicMock()
    response.raise_for_status = MagicMock()
    client.client.post = AsyncMock(return_value=response)

    success = await client.send_tool_feedback({
        "tool_id": "tool-1",
        "selection_id": "sel-1",
        "success": True,
        "execution_time_ms": 100,
        "metadata": {}
    })

    assert success is True
    client.client.post.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_tool_feedback_failure(client):
    """Deve retornar False em erro HTTP."""
    client.client.post = AsyncMock(side_effect=httpx.HTTPError("fail"))

    success = await client.send_tool_feedback({
        "tool_id": "tool-1",
        "selection_id": "sel-1",
        "success": False,
        "execution_time_ms": 10,
        "metadata": {}
    })

    assert success is False


@pytest.mark.asyncio
async def test_get_tool_success(client):
    """Deve retornar descriptor quando encontrado."""
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {"tool_id": "tool-1"}
    client.client.get = AsyncMock(return_value=response)

    tool = await client.get_tool("tool-1")

    assert tool["tool_id"] == "tool-1"
    client.client.get.assert_awaited_once_with("/api/v1/tools/tool-1")


@pytest.mark.asyncio
async def test_list_tools_with_filters(client):
    """Deve passar params para listagem com filtro de categoria."""
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {"tools": [{"tool_id": "t1"}]}
    client.client.get = AsyncMock(return_value=response)

    tools = await client.list_tools(category="VALIDATION")

    assert tools[0]["tool_id"] == "t1"
    client.client.get.assert_awaited_once_with("/api/v1/tools", params={"category": "VALIDATION"})
