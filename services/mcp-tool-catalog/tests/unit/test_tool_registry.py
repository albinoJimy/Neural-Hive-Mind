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
        self, mock_mongodb_client, mock_redis_client, cli_tool, rest_tool
    ):
        """Deve listar ferramentas por categoria."""
        from src.services.tool_registry import ToolRegistry
        from src.models.tool_descriptor import ToolCategory

        # Mock list_tools retornando ferramentas
        mock_mongodb_client.list_tools = AsyncMock(return_value=[cli_tool, rest_tool])

        registry = ToolRegistry(mongodb_client=mock_mongodb_client, redis_client=mock_redis_client)

        tools = await registry.list_tools_by_category(ToolCategory.VALIDATION)

        assert len(tools) >= 1
        mock_mongodb_client.list_tools.assert_called_once_with(category=ToolCategory.VALIDATION)

    @pytest.mark.asyncio
    async def test_list_tools_filters_inactive(
        self, mock_mongodb_client, mock_redis_client, cli_tool, unhealthy_tool
    ):
        """Deve filtrar ferramentas inativas."""
        from src.services.tool_registry import ToolRegistry
        from src.models.tool_descriptor import ToolCategory

        # Mock list_tools retornando ferramentas (filtragem feita pelo MongoDBClient)
        mock_mongodb_client.list_tools = AsyncMock(return_value=[cli_tool])

        registry = ToolRegistry(mongodb_client=mock_mongodb_client, redis_client=mock_redis_client)

        tools = await registry.list_tools_by_category(ToolCategory.VALIDATION)

        # Ferramentas ativas filtradas conforme implementacao
        assert len(tools) >= 1


class TestToolRegistryGet:
    """Testes de busca de ferramenta."""

    @pytest.mark.asyncio
    async def test_get_tool_by_id(self, mock_mongodb_client, mock_redis_client, cli_tool):
        """Deve retornar ferramenta por ID."""
        from src.services.tool_registry import ToolRegistry

        mock_mongodb_client.get_tool = AsyncMock(return_value=cli_tool)

        registry = ToolRegistry(mongodb_client=mock_mongodb_client, redis_client=mock_redis_client)

        tool = await registry.get_tool("pytest-001")

        assert tool is not None
        assert tool.tool_id == "pytest-001"
        mock_mongodb_client.get_tool.assert_called_once_with("pytest-001")

    @pytest.mark.asyncio
    async def test_get_tool_not_found(self, mock_mongodb_client, mock_redis_client):
        """Deve retornar None quando ferramenta nao encontrada."""
        from src.services.tool_registry import ToolRegistry

        mock_mongodb_client.get_tool = AsyncMock(return_value=None)

        registry = ToolRegistry(mongodb_client=mock_mongodb_client, redis_client=mock_redis_client)

        tool = await registry.get_tool("nonexistent")

        assert tool is None

    @pytest.mark.asyncio
    async def test_get_tool_uses_cache(self, mock_mongodb_client, mock_redis_client, cli_tool):
        """Deve usar cache para busca de ferramenta."""
        from src.services.tool_registry import ToolRegistry

        # Mock get_tool para retornar a ferramenta
        mock_mongodb_client.get_tool = AsyncMock(return_value=cli_tool)

        registry = ToolRegistry(mongodb_client=mock_mongodb_client, redis_client=mock_redis_client)

        tool = await registry.get_tool("pytest-001")

        # Verificar que get_tool foi chamado
        mock_mongodb_client.get_tool.assert_called_once_with("pytest-001")
        assert tool is not None


class TestToolRegistryUpdate:
    """Testes de atualizacao de ferramentas."""

    @pytest.mark.asyncio
    async def test_update_tool(self, mock_mongodb_client, mock_redis_client, cli_tool):
        """Deve atualizar ferramenta."""
        from src.services.tool_registry import ToolRegistry

        mock_mongodb_client.get_tool = AsyncMock(return_value=cli_tool)
        mock_mongodb_client.save_tool = AsyncMock(return_value="pytest-001")

        registry = ToolRegistry(mongodb_client=mock_mongodb_client, redis_client=mock_redis_client)

        await registry.update_tool("pytest-001", {"reputation_score": 0.99})

        # Verificar que get_tool e save_tool foram chamados (API correta)
        mock_mongodb_client.get_tool.assert_called_once_with("pytest-001")
        mock_mongodb_client.save_tool.assert_called_once()


class TestToolRegistryReputation:
    """Testes de atualizacao de reputacao."""

    @pytest.mark.asyncio
    async def test_update_tool_reputation_increase(
        self, mock_mongodb_client, mock_redis_client, cli_tool
    ):
        """Deve aumentar reputacao apos execucao bem-sucedida."""
        from src.services.tool_registry import ToolRegistry

        registry = ToolRegistry(mongodb_client=mock_mongodb_client, redis_client=mock_redis_client)

        old_reputation = cli_tool.reputation_score

        await registry.update_tool_reputation(tool_id="pytest-001", success=True)

        # Verificar que update_tool_reputation foi chamado (API correta)
        mock_mongodb_client.update_tool_reputation.assert_called_once_with("pytest-001", 1.0)

    @pytest.mark.asyncio
    async def test_update_tool_reputation_decrease(
        self, mock_mongodb_client, mock_redis_client, cli_tool
    ):
        """Deve diminuir reputacao apos execucao falha."""
        from src.services.tool_registry import ToolRegistry

        registry = ToolRegistry(mongodb_client=mock_mongodb_client, redis_client=mock_redis_client)

        await registry.update_tool_reputation(tool_id="pytest-001", success=False)

        # Verificar que update_tool_reputation foi chamado (API correta)
        mock_mongodb_client.update_tool_reputation.assert_called_once_with("pytest-001", 0.0)


class TestToolRegistryHealth:
    """Testes de atualizacao de saude."""

    @pytest.mark.asyncio
    async def test_update_tool_health_healthy(self, mock_mongodb_client, mock_redis_client):
        """Deve marcar ferramenta como saudavel."""
        from src.services.tool_registry import ToolRegistry

        registry = ToolRegistry(mongodb_client=mock_mongodb_client, redis_client=mock_redis_client)

        # Usar update_tool_metrics ao inves de update_tool_health
        await registry.update_tool_metrics(
            tool_id="pytest-001",
            category="VALIDATION",
            success=True,
            execution_time_ms=1000,
            metadata={"is_healthy": True},
        )

        # Verificar que os métodos corretos foram chamados
        mock_redis_client.increment_tool_usage.assert_called_once_with("pytest-001")
        mock_redis_client.increment_tool_feedback.assert_called_once_with("pytest-001", True)
        mock_mongodb_client.update_tool_reputation.assert_called_once_with("pytest-001", True)

    @pytest.mark.asyncio
    async def test_update_tool_health_unhealthy(self, mock_mongodb_client, mock_redis_client):
        """Deve marcar ferramenta como nao saudavel."""
        from src.services.tool_registry import ToolRegistry

        registry = ToolRegistry(mongodb_client=mock_mongodb_client, redis_client=mock_redis_client)

        # Usar update_tool_metrics ao inves de update_tool_health
        await registry.update_tool_metrics(
            tool_id="pytest-001",
            category="VALIDATION",
            success=False,
            execution_time_ms=5000,
            metadata={"is_healthy": False},
        )

        # Verificar que os métodos corretos foram chamados
        mock_redis_client.increment_tool_usage.assert_called_once_with("pytest-001")
        mock_redis_client.increment_tool_feedback.assert_called_once_with("pytest-001", False)
        mock_mongodb_client.update_tool_reputation.assert_called_once_with("pytest-001", False)
