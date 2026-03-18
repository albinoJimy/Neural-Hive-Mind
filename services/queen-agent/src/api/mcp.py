# MCP API Router

from fastapi import APIRouter, Depends, HTTPException
from typing import Any

from neural_hive_observability import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/mcp", tags=["mcp"])


def get_orchestrator():
    """Dependency injection para MCPToolOrchestrator."""
    from fastapi import Request

    async def _get_orchestrator(request: Request) -> Any:
        app_state = request.app.state.app_state
        orchestrator = app_state.mcp_orchestrator
        if orchestrator is None:
            raise HTTPException(
                status_code=503, detail="MCP Orchestrator not available"
            )
        return orchestrator

    return _get_orchestrator


@router.get("/tools")
async def list_tools(orchestrator=Depends(get_orchestrator())):
    """
    Lista todas as ferramentas disponíveis nos servidores MCP.

    Returns:
        Dict com ferramentas por servidor
    """
    try:
        tools = await orchestrator.get_available_tools()
        return {
            "tools": tools,
            "total_servers": len(tools),
            "total_tools": sum(len(t) for t in tools.values()),
        }
    except Exception as e:
        logger.error("list_tools_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/execute")
async def execute_tools(
    requests: list[dict[str, Any]],
    parallel: bool = True,
    continue_on_error: bool = False,
    orchestrator=Depends(get_orchestrator()),
):
    """
    Executa múltiplas ferramentas MCP.

    Args:
        requests: Lista de {server, tool_name, params}
        parallel: Execução paralela (True) ou sequencial (False)
        continue_on_error: Continuar mesmo com erros

    Returns:
        Lista de resultados
    """
    try:
        if parallel:
            results = await orchestrator.execute_tools_parallel(
                requests, continue_on_error=continue_on_error
            )
        else:
            results = await orchestrator.execute_tools_sequence(requests)

        aggregated = await orchestrator.aggregate_results(results)

        return {
            "results": results,
            "aggregation": aggregated,
            "execution_mode": "parallel" if parallel else "sequence",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("execute_tools_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tools/{server}/execute")
async def execute_server_tool(
    server: str, tool_request: dict[str, Any], orchestrator=Depends(get_orchestrator())
):
    """
    Executa uma ferramenta específica de um servidor.

    Args:
        server: Nome do servidor (scout, optimizer)
        tool_request: {tool_name, params}

    Returns:
        Resultado da execução
    """
    try:
        tool_name = tool_request.get("tool_name")
        params = tool_request.get("params", {})

        if not tool_name:
            raise HTTPException(status_code=400, detail="tool_name is required")

        # Create request format
        request = {"server": server, "tool_name": tool_name, "params": params}

        results = await orchestrator.execute_tools_sequence([request])

        if not results or results[0]["status"] == "error":
            error = results[0].get("error", "Unknown error") if results else "No result"
            raise HTTPException(status_code=500, detail=error)

        return results[0]["result"]

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error("execute_server_tool_failed", server=server, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_mcp_status(orchestrator=Depends(get_orchestrator())):
    """
    Retorna status dos servidores MCP.

    Returns:
        Status de conexão com cada servidor
    """
    try:
        tools = await orchestrator.get_available_tools()

        return {
            "servers": {
                server: {"connected": True, "tools_count": len(server_tools)}
                for server, server_tools in tools.items()
            },
            "total_servers": len(tools),
        }
    except Exception as e:
        logger.error("get_mcp_status_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
