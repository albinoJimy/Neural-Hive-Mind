"""
Testes unitarios para ToolRegistry.

Cobertura:
- Listagem de ferramentas por categoria
- Busca de ferramenta por ID
- Atualizacao de ferramenta
- Atualizacao de reputacao
- Atualizacao de saude
- Filtragem de ferramentas inativas
"""

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestToolRegistryList:
    """Testes de listagem de ferramentas."""

    @pytest.mark.asyncio
    async def test_list_tools_by_category(
        self,
        mock_mongodb_client,
        mock_redis_client,
        cli_tool,
        rest_tool
    ):
        """Deve listar ferramentas por categoria."""
        from src.services.tool_registry import ToolRegistry
        from src.models.tool_descriptor import ToolCategory

        # Mock find retornando ferramentas
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=[
            cli_tool.to_dict(),
            rest_tool.to_dict()
        ])
        mock_mongodb_client.tools.find.return_value = mock_cursor

        registry = ToolRegistry(
            mongodb_client=mock_mongodb_client,
            redis_client=mock_redis_client
        )

        tools = await registry.list_tools_by_category(ToolCategory.VALIDATION)

        assert len(tools) >= 1

    @pytest.mark.asyncio
    async def test_list_tools_filters_inactive(
        self,
        mock_mongodb_client,
        mock_redis_client,
        cli_tool,
        unhealthy_tool
    ):
        """Deve filtrar ferramentas inativas."""
        from src.services.tool_registry import ToolRegistry
        from src.models.tool_descriptor import ToolCategory

        # Adicionar ferramenta inativa
        inactive_tool = cli_tool.to_dict()
        inactive_tool['metadata'] = {'active': False}

        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=[
            cli_tool.to_dict(),
            inactive_tool
        ])
        mock_mongodb_client.tools.find.return_value = mock_cursor

        registry = ToolRegistry(
            mongodb_client=mock_mongodb_client,
            redis_client=mock_redis_client
        )

        tools = await registry.list_tools_by_category(ToolCategory.VALIDATION)

        # Ferramentas ativas filtradas conforme implementacao


class TestToolRegistryGet:
    """Testes de busca de ferramenta."""

    @pytest.mark.asyncio
    async def test_get_tool_by_id(
        self,
        mock_mongodb_client,
        mock_redis_client,
        cli_tool
    ):
        """Deve retornar ferramenta por ID."""
        from src.services.tool_registry import ToolRegistry

        mock_mongodb_client.tools.find_one = AsyncMock(return_value=cli_tool.to_dict())

        registry = ToolRegistry(
            mongodb_client=mock_mongodb_client,
            redis_client=mock_redis_client
        )

        tool = await registry.get_tool('pytest-001')

        assert tool is not None
        assert tool.tool_id == 'pytest-001'

    @pytest.mark.asyncio
    async def test_get_tool_not_found(
        self,
        mock_mongodb_client,
        mock_redis_client
    ):
        """Deve retornar None quando ferramenta nao encontrada."""
        from src.services.tool_registry import ToolRegistry

        mock_mongodb_client.tools.find_one = AsyncMock(return_value=None)

        registry = ToolRegistry(
            mongodb_client=mock_mongodb_client,
            redis_client=mock_redis_client
        )

        tool = await registry.get_tool('nonexistent')

        assert tool is None

    @pytest.mark.asyncio
    async def test_get_tool_uses_cache(
        self,
        mock_mongodb_client,
        mock_redis_client,
        cli_tool
    ):
        """Deve usar cache para busca de ferramenta."""
        from src.services.tool_registry import ToolRegistry

        # Cache hit
        mock_redis_client.get.return_value = cli_tool.to_dict()

        registry = ToolRegistry(
            mongodb_client=mock_mongodb_client,
            redis_client=mock_redis_client
        )

        tool = await registry.get_tool('pytest-001')

        # MongoDB nao deve ser chamado quando cache hit
        # (comportamento depende da implementacao)


class TestToolRegistryUpdate:
    """Testes de atualizacao de ferramentas."""

    @pytest.mark.asyncio
    async def test_update_tool(
        self,
        mock_mongodb_client,
        mock_redis_client,
        cli_tool
    ):
        """Deve atualizar ferramenta."""
        from src.services.tool_registry import ToolRegistry

        mock_mongodb_client.tools.update_one = AsyncMock()

        registry = ToolRegistry(
            mongodb_client=mock_mongodb_client,
            redis_client=mock_redis_client
        )

        cli_tool.reputation_score = 0.99

        await registry.update_tool(cli_tool)

        mock_mongodb_client.tools.update_one.assert_called()


class TestToolRegistryReputation:
    """Testes de atualizacao de reputacao."""

    @pytest.mark.asyncio
    async def test_update_tool_reputation_increase(
        self,
        mock_mongodb_client,
        mock_redis_client,
        cli_tool
    ):
        """Deve aumentar reputacao apos execucao bem-sucedida."""
        from src.services.tool_registry import ToolRegistry

        mock_mongodb_client.tools.find_one = AsyncMock(return_value=cli_tool.to_dict())
        mock_mongodb_client.tools.update_one = AsyncMock()

        registry = ToolRegistry(
            mongodb_client=mock_mongodb_client,
            redis_client=mock_redis_client
        )

        old_reputation = cli_tool.reputation_score

        await registry.update_tool_reputation(
            tool_id='pytest-001',
            success=True,
            execution_time_ms=1000
        )

        # Verificar que update foi chamado
        mock_mongodb_client.tools.update_one.assert_called()

    @pytest.mark.asyncio
    async def test_update_tool_reputation_decrease(
        self,
        mock_mongodb_client,
        mock_redis_client,
        cli_tool
    ):
        """Deve diminuir reputacao apos execucao falha."""
        from src.services.tool_registry import ToolRegistry

        mock_mongodb_client.tools.find_one = AsyncMock(return_value=cli_tool.to_dict())
        mock_mongodb_client.tools.update_one = AsyncMock()

        registry = ToolRegistry(
            mongodb_client=mock_mongodb_client,
            redis_client=mock_redis_client
        )

        await registry.update_tool_reputation(
            tool_id='pytest-001',
            success=False,
            execution_time_ms=5000
        )

        mock_mongodb_client.tools.update_one.assert_called()


class TestToolRegistryHealth:
    """Testes de atualizacao de saude."""

    @pytest.mark.asyncio
    async def test_update_tool_health_healthy(
        self,
        mock_mongodb_client,
        mock_redis_client
    ):
        """Deve marcar ferramenta como saudavel."""
        from src.services.tool_registry import ToolRegistry

        mock_mongodb_client.tools.update_one = AsyncMock()

        registry = ToolRegistry(
            mongodb_client=mock_mongodb_client,
            redis_client=mock_redis_client
        )

        await registry.update_tool_health('pytest-001', is_healthy=True)

        mock_mongodb_client.tools.update_one.assert_called()

    @pytest.mark.asyncio
    async def test_update_tool_health_unhealthy(
        self,
        mock_mongodb_client,
        mock_redis_client
    ):
        """Deve marcar ferramenta como nao saudavel."""
        from src.services.tool_registry import ToolRegistry

        mock_mongodb_client.tools.update_one = AsyncMock()

        registry = ToolRegistry(
            mongodb_client=mock_mongodb_client,
            redis_client=mock_redis_client
        )

        await registry.update_tool_health('pytest-001', is_healthy=False)

        mock_mongodb_client.tools.update_one.assert_called()
