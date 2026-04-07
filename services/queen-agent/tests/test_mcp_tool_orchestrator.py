"""
Testes para MCP Tool Orchestrator.

TDD: Testes escritos antes da implementação.
Espec: @.agent-os/specs/2026-03-18-gaps-06-mcp-integration/
"""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest


# Load MCPToolOrchestrator directly without triggering __init__.py
def load_mcp_orchestrator():
    """Carrega MCPToolOrchestrator diretamente do arquivo."""
    src_path = Path(__file__).parent.parent / "src" / "services" / "mcp_tool_orchestrator.py"
    spec = importlib.util.spec_from_file_location("mcp_tool_orchestrator", src_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["mcp_tool_orchestrator"] = module
    spec.loader.exec_module(module)
    return module.MCPToolOrchestrator


MCPToolOrchestrator = load_mcp_orchestrator()


class TestMCPToolOrchestrator:
    """Testes do MCPToolOrchestrator."""

    @pytest.fixture
    def orchestrator(self):
        """Retorna instância do orchestrator."""

        # Mock MCP clients
        scout_client = AsyncMock()
        optimizer_client = AsyncMock()

        return MCPToolOrchestrator(scout_client=scout_client, optimizer_client=optimizer_client)

    @pytest.mark.asyncio
    async def test_execute_tools_parallel(self, orchestrator):
        """Testa execução paralela de ferramentas."""
        # Mock responses
        orchestrator._clients["scout"].execute_tool.return_value = {
            "result": {"files": ["a.py", "b.py"]}
        }
        orchestrator._clients["optimizer"].execute_tool.return_value = {
            "result": {"suggestions": []}
        }

        requests = [
            {"server": "scout", "tool_name": "list_files", "params": {"path": "/src"}},
            {
                "server": "optimizer",
                "tool_name": "suggest_refactors",
                "params": {"path": "/src"},
            },
        ]

        results = await orchestrator.execute_tools_parallel(requests)

        assert len(results) == 2
        assert results[0]["server"] == "scout"
        assert results[1]["server"] == "optimizer"

    @pytest.mark.asyncio
    async def test_execute_tools_sequence(self, orchestrator):
        """Testa execução sequencial de ferramentas."""

        # Mock responses - need async functions
        async def mock_execute(*args, **kwargs):
            return {"files": ["a.py"]}

        orchestrator._clients["scout"].execute_tool = mock_execute

        requests = [
            {"server": "scout", "tool_name": "list_files", "params": {"path": "/src"}},
            {
                "server": "scout",
                "tool_name": "analyze_structure",
                "params": {"path": "/src"},
            },
        ]

        results = await orchestrator.execute_tools_sequence(requests)

        assert len(results) == 2
        # Verify sequential execution (each waits for previous)
        # We can't verify call_count on a function, but we can verify results
        assert results[0]["status"] == "success"
        assert results[1]["status"] == "success"

    @pytest.mark.asyncio
    async def test_aggregate_results(self, orchestrator):
        """Testa agregação de resultados."""
        results = [
            {
                "server": "scout",
                "tool_name": "list_files",
                "status": "success",
                "result": {"files": ["a.py"]},
            },
            {
                "server": "optimizer",
                "tool_name": "suggest_refactors",
                "status": "success",
                "result": {"suggestions": []},
            },
            {
                "server": "scout",
                "tool_name": "analyze_structure",
                "status": "success",
                "result": {"complexity": 5},
            },
        ]

        aggregated = await orchestrator.aggregate_results(results)

        assert "total_count" in aggregated
        assert aggregated["total_count"] == 3
        assert "by_server" in aggregated
        assert aggregated["by_server"]["scout"] == 2
        assert aggregated["by_server"]["optimizer"] == 1

    @pytest.mark.asyncio
    async def test_execute_tools_with_unknown_server(self, orchestrator):
        """Testa erro com servidor desconhecido."""
        requests = [
            {"server": "unknown", "tool_name": "some_tool", "params": {}},
        ]

        with pytest.raises(ValueError):
            await orchestrator.execute_tools_parallel(requests)

    @pytest.mark.asyncio
    async def test_execute_tools_handles_partial_failure(self, orchestrator):
        """Testa que falhas parciais são tratadas."""
        # Mock: first succeeds, second fails
        orchestrator._clients["scout"].execute_tool.return_value = {"result": {"files": ["a.py"]}}
        orchestrator._clients["optimizer"].execute_tool.side_effect = Exception("Optimizer error")

        requests = [
            {"server": "scout", "tool_name": "list_files", "params": {"path": "/src"}},
            {
                "server": "optimizer",
                "tool_name": "suggest_refactors",
                "params": {"path": "/src"},
            },
        ]

        results = await orchestrator.execute_tools_parallel(requests, continue_on_error=True)

        assert len(results) == 2
        assert results[0]["status"] == "success"
        assert results[1]["status"] == "error"

    @pytest.mark.asyncio
    async def test_get_available_tools(self, orchestrator):
        """Testa listagem de ferramentas disponíveis."""
        orchestrator._clients["scout"].list_tools.return_value = [
            {"name": "list_files", "description": "List files"}
        ]
        orchestrator._clients["optimizer"].list_tools.return_value = [
            {"name": "suggest_refactors", "description": "Suggest refactors"}
        ]

        tools = await orchestrator.get_available_tools()

        assert "scout" in tools
        assert "optimizer" in tools
        assert len(tools["scout"]) == 1
        assert len(tools["optimizer"]) == 1


class TestMCPToolOrchestratorIntegration:
    """Testes de integração do MCPToolOrchestrator."""

    @pytest.mark.asyncio
    async def test_full_workflow(self):
        """Testa workflow completo: descoberta -> execução -> agregação."""

        # Mock clients
        scout_client = AsyncMock()
        scout_client.list_tools.return_value = [{"name": "list_files", "description": "List files"}]
        scout_client.execute_tool.return_value = {"result": {"files": ["a.py", "b.py"]}}

        orchestrator = MCPToolOrchestrator(scout_client=scout_client)

        # 1. List tools
        tools = await orchestrator.get_available_tools()
        assert "scout" in tools

        # 2. Execute
        results = await orchestrator.execute_tools_parallel(
            [{"server": "scout", "tool_name": "list_files", "params": {"path": "/src"}}]
        )
        assert len(results) == 1

        # 3. Aggregate
        aggregated = await orchestrator.aggregate_results(results)
        assert aggregated["total_count"] == 1
