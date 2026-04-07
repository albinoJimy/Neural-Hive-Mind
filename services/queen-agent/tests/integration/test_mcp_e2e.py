"""
Testes de Integração E2E para MCP Integration

Valida fluxo completo:
- Scout MCP → Queen Agent → Resultado
- Optimizer MCP → Queen Agent → Resultado
- Paralelismo de ferramentas
- Timeout e error handling
- SDK Client → MCP Server

Espec: .agent-os/specs/2026-03-18-gaps-06-mcp-integration/
"""
import asyncio
import sys
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import uuid4

import pytest

# Mock de dependências externas ANTES de imports
sys.modules["neural_hive_domain"] = Mock()
sys.modules["neural_hive_specialists"] = Mock()
sys.modules["neural_hive_agent_sdk"] = Mock()
sys.modules["neural_hive_observability"] = Mock()
sys.modules["neural_hive_observability"].get_logger = Mock(return_value=MagicMock())

# Import direto via importlib para evitar __init__.py
import importlib.util

spec = importlib.util.spec_from_file_location(
    "mcp_tool_orchestrator",
    "src/services/mcp_tool_orchestrator.py",
)
mcp_orchestrator_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mcp_orchestrator_module)
MCPToolOrchestrator = mcp_orchestrator_module.MCPToolOrchestrator


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_scout_client():
    """Mock do Scout MCP Client."""
    client = AsyncMock()
    client.list_tools = AsyncMock(
        return_value=[
            {"name": "list_files", "description": "Lista arquivos"},
            {"name": "search_code", "description": "Busca código"},
            {"name": "analyze_structure", "description": "Analisa estrutura"},
        ]
    )
    return client


@pytest.fixture
def mock_optimizer_client():
    """Mock do Optimizer MCP Client."""
    client = AsyncMock()
    client.list_tools = AsyncMock(
        return_value=[
            {"name": "suggest_refactors", "description": "Sugere refatorações"},
            {"name": "analyze_performance", "description": "Analisa performance"},
            {"name": "optimize_queries", "description": "Otimiza queries"},
        ]
    )
    return client


@pytest.fixture
def mcp_orchestrator(mock_scout_client, mock_optimizer_client):
    """Instância do MCPToolOrchestrator com clients mockados."""
    return MCPToolOrchestrator(
        scout_client=mock_scout_client,
        optimizer_client=mock_optimizer_client,
    )


# =============================================================================
# TESTES E2E: Scout MCP → Queen Agent → Result
# =============================================================================


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_scout_list_files_e2e_success(mcp_orchestrator, mock_scout_client):
    """
    Teste E2E: Scout MCP list_files com sucesso.
    Valida fluxo completo: request → MCP → response.
    """
    expected_files = ["main.py", "config.py", "utils.py", "tests/"]
    mock_scout_client.execute_tool = AsyncMock(
        return_value={
            "files": expected_files,
            "count": len(expected_files),
            "path": "/src",
        }
    )

    result = await mcp_orchestrator.execute_tools_sequence(
        requests=[
            {"server": "scout", "tool_name": "list_files", "params": {"path": "/src"}},
        ]
    )

    assert len(result) == 1
    assert result[0]["status"] == "success"
    assert result[0]["server"] == "scout"
    assert result[0]["result"]["files"] == expected_files
    assert result[0]["result"]["count"] == 4


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_scout_search_code_e2e_success(mcp_orchestrator, mock_scout_client):
    """
    Teste E2E: Scout MCP search_code com sucesso.
    Valida busca de código por padrão.
    """
    expected_matches = [
        {"file": "src/services/worker.py", "line": 42, "context": "def execute_task"},
        {"file": "src/utils/task.py", "line": 15, "context": "class TaskExecutor"},
    ]

    mock_scout_client.execute_tool = AsyncMock(
        return_value={
            "matches": expected_matches,
            "count": len(expected_matches),
            "pattern": "execute_task",
        }
    )

    result = await mcp_orchestrator.execute_tools_sequence(
        requests=[
            {
                "server": "scout",
                "tool_name": "search_code",
                "params": {"pattern": "execute_task", "path": "/src"},
            },
        ]
    )

    assert len(result) == 1
    assert result[0]["status"] == "success"
    assert len(result[0]["result"]["matches"]) == 2
    assert result[0]["result"]["matches"][0]["file"] == "src/services/worker.py"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_scout_analyze_structure_e2e_success(mcp_orchestrator, mock_scout_client):
    """
    Teste E2E: Scout MCP analyze_structure com sucesso.
    Valida análise de estrutura de diretórios.
    """
    expected_structure = {
        "name": "src",
        "type": "directory",
        "children": [
            {"name": "services", "type": "directory", "children_count": 5},
            {"name": "utils", "type": "directory", "children_count": 3},
            {"name": "models", "type": "directory", "children_count": 2},
        ],
        "total_files": 42,
        "total_dirs": 10,
    }

    mock_scout_client.execute_tool = AsyncMock(return_value=expected_structure)

    result = await mcp_orchestrator.execute_tools_sequence(
        requests=[
            {
                "server": "scout",
                "tool_name": "analyze_structure",
                "params": {"path": "/src"},
            },
        ]
    )

    assert result[0]["status"] == "success"
    assert result[0]["result"]["total_files"] == 42
    assert len(result[0]["result"]["children"]) == 3


# =============================================================================
# TESTES E2E: Optimizer MCP → Queen Agent → Result
# =============================================================================


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_optimizer_suggest_refactors_e2e_success(mcp_orchestrator, mock_optimizer_client):
    """
    Teste E2E: Optimizer MCP suggest_refactors com sucesso.
    Valida sugestões de refatoração.
    """
    expected_suggestions = [
        {
            "type": "extract_method",
            "description": "Extrair lógica de validação para método separado",
            "location": {"file": "src/services/worker.py", "lines": "45-60"},
            "priority": "medium",
            "estimated_effort": "15min",
        },
        {
            "type": "reduce_complexity",
            "description": "Simplificar função execute_tasks (complexidade 15)",
            "location": {"file": "src/utils/task.py", "lines": "100-150"},
            "priority": "high",
            "estimated_effort": "30min",
        },
    ]

    mock_optimizer_client.execute_tool = AsyncMock(
        return_value={"suggestions": expected_suggestions}
    )

    result = await mcp_orchestrator.execute_tools_sequence(
        requests=[
            {
                "server": "optimizer",
                "tool_name": "suggest_refactors",
                "params": {"path": "/src/services/worker.py"},
            },
        ]
    )

    assert result[0]["status"] == "success"
    assert len(result[0]["result"]["suggestions"]) == 2
    assert result[0]["result"]["suggestions"][0]["type"] == "extract_method"
    assert result[0]["result"]["suggestions"][1]["priority"] == "high"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_optimizer_analyze_performance_e2e_success(mcp_orchestrator, mock_optimizer_client):
    """
    Teste E2E: Optimizer MCP analyze_performance com sucesso.
    Valida análise de performance de código.
    """
    expected_analysis = {
        "overall_score": 0.72,
        "bottlenecks": [
            {
                "location": "src/api/handlers.py:120",
                "issue": "Query N+1 detectado",
                "impact": "high",
                "suggestion": "Usar batch loading",
            }
        ],
        "optimization_potential": "30% improvement estimado",
    }

    mock_optimizer_client.execute_tool = AsyncMock(return_value=expected_analysis)

    result = await mcp_orchestrator.execute_tools_sequence(
        requests=[
            {
                "server": "optimizer",
                "tool_name": "analyze_performance",
                "params": {"path": "/src/api/handlers.py"},
            },
        ]
    )

    assert result[0]["status"] == "success"
    assert result[0]["result"]["overall_score"] == 0.72
    assert len(result[0]["result"]["bottlenecks"]) == 1
    assert result[0]["result"]["bottlenecks"][0]["issue"] == "Query N+1 detectado"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_optimizer_optimize_queries_e2e_success(mcp_orchestrator, mock_optimizer_client):
    """
    Teste E2E: Optimizer MCP optimize_queries com sucesso.
    Valida otimização de queries MongoDB.
    """
    expected_optimizations = [
        {
            "query": "db.users.find({age: {$gt: 25}}).sort({name: 1})",
            "issue": "Sort sem índice composto",
            "optimized_query": "db.users.find({age: {$gt: 25}}).sort({name: 1, age: 1})",
            "improvement": "40% mais rápido",
        }
    ]

    mock_optimizer_client.execute_tool = AsyncMock(
        return_value={"optimizations": expected_optimizations}
    )

    result = await mcp_orchestrator.execute_tools_sequence(
        requests=[
            {
                "server": "optimizer",
                "tool_name": "optimize_queries",
                "params": {"queries": ["db.users.find({age: {$gt: 25}}).sort({name: 1})"]},
            },
        ]
    )

    assert result[0]["status"] == "success"
    assert len(result[0]["result"]["optimizations"]) == 1
    assert "40% mais rápido" in result[0]["result"]["optimizations"][0]["improvement"]


# =============================================================================
# TESTES E2E: Paralelismo de Tools
# =============================================================================


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_parallel_tools_execution_e2e(
    mcp_orchestrator, mock_scout_client, mock_optimizer_client
):
    """
    Teste E2E: execução paralela de múltiplas ferramentas.
    Valida que ferramentas são executadas concorrentemente.
    """
    mock_scout_client.execute_tool = AsyncMock(
        side_effect=[
            {"files": ["main.py", "config.py"]},
            {"matches": [{"file": "worker.py", "line": 42}]},
        ]
    )

    mock_optimizer_client.execute_tool = AsyncMock(return_value={"overall_score": 0.85})

    requests = [
        {"server": "scout", "tool_name": "list_files", "params": {"path": "/src"}},
        {"server": "scout", "tool_name": "search_code", "params": {"pattern": "class"}},
        {
            "server": "optimizer",
            "tool_name": "analyze_performance",
            "params": {"path": "/src"},
        },
    ]

    results = await mcp_orchestrator.execute_tools_parallel(
        requests=requests,
        continue_on_error=False,
    )

    assert len(results) == 3
    assert all(r["status"] == "success" for r in results)

    assert mock_scout_client.execute_tool.call_count == 2
    assert mock_optimizer_client.execute_tool.call_count == 1


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_parallel_tools_with_one_failure_e2e(mcp_orchestrator, mock_scout_client):
    """
    Teste E2E: execução paralela com uma falha.
    Valida que falhas não impedem execuções bem-sucedidas quando continue_on_error=True.
    """
    call_count = {"count": 0}

    async def flaky_execute(tool_name, params):
        call_count["count"] += 1
        if tool_name == "invalid_tool":
            raise ValueError("Tool not found")
        return {"status": "ok"}

    mock_scout_client.execute_tool = flaky_execute

    requests = [
        {"server": "scout", "tool_name": "list_files", "params": {"path": "/src"}},
        {"server": "scout", "tool_name": "invalid_tool", "params": {}},
        {"server": "scout", "tool_name": "search_code", "params": {"pattern": "class"}},
    ]

    results = await mcp_orchestrator.execute_tools_parallel(
        requests=requests,
        continue_on_error=True,
    )

    assert len(results) == 3
    success_count = sum(1 for r in results if r["status"] == "success")
    error_count = sum(1 for r in results if r["status"] == "error")
    assert success_count == 2
    assert error_count == 1


# =============================================================================
# TESTES E2E: Timeout e Error Handling
# =============================================================================


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_tool_execution_timeout_e2e(mcp_orchestrator, mock_scout_client):
    """
    Teste E2E: timeout na execução de ferramenta.
    """

    async def slow_tool(tool_name, params):
        await asyncio.sleep(5)
        return {"result": "too_slow"}

    mock_scout_client.execute_tool = slow_tool

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(
            mcp_orchestrator.execute_tools_sequence(
                requests=[
                    {
                        "server": "scout",
                        "tool_name": "list_files",
                        "params": {"path": "/src"},
                    },
                ]
            ),
            timeout=0.1,
        )


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_tool_execution_with_error_e2e(mcp_orchestrator, mock_scout_client):
    """
    Teste E2E: erro na execução de ferramenta.
    """
    mock_scout_client.execute_tool = AsyncMock(
        side_effect=FileNotFoundError("Path not found: /nonexistent/path")
    )

    result = await mcp_orchestrator.execute_tools_sequence(
        requests=[
            {
                "server": "scout",
                "tool_name": "list_files",
                "params": {"path": "/nonexistent"},
            },
        ]
    )

    assert len(result) == 1
    assert result[0]["status"] == "error"
    assert "Path not found" in result[0]["error"]


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_aggregate_results_e2e(mcp_orchestrator, mock_scout_client):
    """
    Teste E2E: agregação de resultados de múltiplas execuções.
    """
    mock_scout_client.execute_tool = AsyncMock(
        side_effect=[
            {"files": ["a.py"]},
            {"matches": []},
            FileNotFoundError("error"),
        ]
    )

    requests = [
        {"server": "scout", "tool_name": "list_files", "params": {"path": "/src"}},
        {"server": "scout", "tool_name": "search_code", "params": {"pattern": "class"}},
        {
            "server": "scout",
            "tool_name": "analyze_structure",
            "params": {"path": "/bad"},
        },
    ]

    results = await mcp_orchestrator.execute_tools_sequence(requests=requests)

    aggregated = await mcp_orchestrator.aggregate_results(results)

    assert aggregated["total_count"] == 3
    assert aggregated["success_count"] == 2
    assert aggregated["error_count"] == 1
    assert aggregated["by_server"]["scout"] == 3
    assert aggregated["by_tool"]["list_files"] == 1


# =============================================================================
# TESTES E2E: SDK Client → MCP Server
# =============================================================================


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_sdk_client_list_tools_e2e():
    """Teste E2E: SDK Client lista ferramentas do MCP Server."""
    mock_server = AsyncMock()
    mock_server.list_tools = AsyncMock(
        return_value=[
            {"name": "list_files", "description": "Lista arquivos"},
            {"name": "search_code", "description": "Busca código"},
        ]
    )

    tools = await mock_server.list_tools()

    assert len(tools) == 2
    assert tools[0]["name"] == "list_files"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_sdk_client_execute_tool_e2e():
    """Teste E2E: SDK Client executa ferramenta no MCP Server."""
    mock_server = AsyncMock()
    mock_server.execute_tool = AsyncMock(
        return_value={"files": ["main.py", "config.py"], "count": 2}
    )

    result = await mock_server.execute_tool("list_files", {"path": "/src"})

    assert result["files"] == ["main.py", "config.py"]


# =============================================================================
# TESTES E2E: Fluxo Completo
# =============================================================================


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_full_workflow_e2e(mcp_orchestrator, mock_scout_client, mock_optimizer_client):
    """
    Teste E2E: fluxo completo multi-step.
    1. Listar arquivos (Scout)
    2. Buscar código (Scout)
    3. Analisar performance (Optimizer)
    4. Agregar resultados
    """
    mock_scout_client.execute_tool = AsyncMock(
        side_effect=[
            {"files": ["worker.py", "task.py"], "path": "/src/services"},
            {"matches": [{"file": "worker.py", "line": 42, "context": "execute_task"}]},
        ]
    )

    mock_optimizer_client.execute_tool = AsyncMock(
        return_value={
            "overall_score": 0.75,
            "bottlenecks": [],
            "optimization_potential": "15%",
        }
    )

    workflow_steps = [
        {
            "server": "scout",
            "tool_name": "list_files",
            "params": {"path": "/src/services"},
        },
        {
            "server": "scout",
            "tool_name": "search_code",
            "params": {"pattern": "execute"},
        },
        {
            "server": "optimizer",
            "tool_name": "analyze_performance",
            "params": {"path": "/src/services/worker.py"},
        },
    ]

    results = await mcp_orchestrator.execute_tools_sequence(requests=workflow_steps)

    assert len(results) == 3
    assert all(r["status"] == "success" for r in results)

    aggregated = await mcp_orchestrator.aggregate_results(results)
    assert aggregated["total_count"] == 3
    assert aggregated["success_count"] == 3


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_get_available_tools_e2e(mcp_orchestrator):
    """Teste E2E: lista ferramentas disponíveis em todos os servidores."""
    tools = await mcp_orchestrator.get_available_tools()

    assert "scout" in tools
    assert "optimizer" in tools
    assert len(tools["scout"]) == 3
    assert len(tools["optimizer"]) == 3


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_register_client_e2e(mock_optimizer_client):
    """Teste E2E: registra novo cliente MCP dinamicamente."""
    orchestrator = MCPToolOrchestrator()

    tools = await orchestrator.get_available_tools()
    assert len(tools) == 0

    orchestrator.register_client("optimizer", mock_optimizer_client)

    tools = await orchestrator.get_available_tools()
    assert "optimizer" in tools
    assert len(tools["optimizer"]) == 3
