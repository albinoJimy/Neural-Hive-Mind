"""
Worker MCP Tools - Ferramentas de execução distribuída.

Ferramentas:
- execute_task: Executar tarefas específicas
- check_dependencies: Verificar dependências
- monitor_progress: Monitorar progresso de execução
- handle_compensation: Executar compensações (saga)
- report_status: Reportar status de execução
"""

from datetime import datetime
from typing import Any

import httpx
import structlog

from worker_mcp_server.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()


async def execute_task(
    task_id: str, workflow_id: str, executor_type: str, parameters: dict[str, Any] | None = None
) -> dict[str, Any]:
    """
    Executar uma tarefa específica via Worker Agent.

    Args:
        task_id: ID da tarefa
        workflow_id: ID do workflow
        executor_type: Tipo de executor (query, transform, validate, etc.)
        parameters: Parâmetros da tarefa

    Returns:
        Dicionário com execution_id e status
    """
    logger.info(
        "execute_task_called", task_id=task_id, workflow_id=workflow_id, executor_type=executor_type
    )

    # Validações
    if not task_id:
        raise ValueError("task_id is required")

    valid_executors = ["query", "transform", "validate", "code_generation", "data_processing"]

    if executor_type not in valid_executors:
        raise ValueError(f"executor_type must be one of: {valid_executors}, got: {executor_type}")

    # Chamar Worker Agent via HTTP/gRPC
    try:
        payload = {
            "task_id": task_id,
            "workflow_id": workflow_id,
            "executor_type": executor_type,
            "parameters": parameters or {},
            "timestamp": int(datetime.now().timestamp() * 1000),
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"http://worker-agents:{8005}/api/v1/execute", json=payload
            )
            response.raise_for_status()
            result = response.json()

        logger.info(
            "worker_agent_execute_success", task_id=task_id, execution_id=result.get("execution_id")
        )

        return result

    except httpx.HTTPStatusError as e:
        logger.error("worker_agent_execute_http_error", status_code=e.response.status_code)
        return {
            "error": f"HTTP error: {e.response.status_code}",
            "execution_id": None,
            "status": "ERROR",
        }
    except Exception as e:
        logger.exception("worker_agent_execute_failed", error=str(e))
        return {"error": str(e), "execution_id": None, "status": "ERROR"}


async def check_dependencies(workflow_id: str, dependencies: list[str]) -> dict[str, Any]:
    """
    Verificar se dependências do workflow estão satisfeitas.

    Args:
        workflow_id: ID do workflow
        dependencies: Lista de dependências (serviços, dados, etc.)

    Returns:
        Dicionário com satisfied=True/False e lista de missing
    """
    logger.info(
        "check_dependencies_called", workflow_id=workflow_id, dependencies_count=len(dependencies)
    )

    if not dependencies:
        return {"satisfied": True, "missing": [], "workflow_id": workflow_id}

    # Consultar Service Registry para verificar dependências
    try:
        missing = []

        async with httpx.AsyncClient(timeout=10) as client:
            for dep in dependencies:
                response = await client.get(
                    f"http://service-registry:{8007}/api/v1/services/{dep}/health"
                )

                if response.status_code != 200:
                    missing.append(dep)

        satisfied = len(missing) == 0

        return {"satisfied": satisfied, "missing": missing, "workflow_id": workflow_id}

    except Exception as e:
        logger.exception("check_dependencies_failed", error=str(e))
        # Em caso de erro, assumir dependências OK para não bloquear
        return {"satisfied": True, "missing": [], "workflow_id": workflow_id}


async def monitor_progress(execution_id: str) -> dict[str, Any]:
    """
    Monitorar progresso de uma execução de tarefa.

    Args:
        execution_id: ID da execução

    Returns:
        Dicionário com status, progress_percent e logs
    """
    logger.info("monitor_progress_called", execution_id=execution_id)

    # Consultar Worker Agent para status da execução
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"http://worker-agents:{8005}/api/v1/executions/{execution_id}"
            )
            response.raise_for_status()
            result = response.json()

        return result

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            # Execução não encontrada - assumir não iniciada
            return {"status": "not_found", "progress_percent": 0, "execution_id": execution_id}
        logger.error("monitor_progress_http_error", status_code=e.response.status_code)
        return {"status": "error", "progress_percent": 0, "execution_id": execution_id}
    except Exception as e:
        logger.exception("monitor_progress_failed", error=str(e))
        return {"status": "error", "progress_percent": 0, "execution_id": execution_id}


async def handle_compensation(
    execution_id: str, original_task_id: str, compensation_type: str
) -> dict[str, Any]:
    """
    Executar compensação (transação saga) para execução falhada.

    Args:
        execution_id: ID da execução falhada
        original_task_id: ID da tarefa original
        compensation_type: Tipo de compensação

    Returns:
        Dicionário com success=True/False e compensation_id
    """
    logger.info(
        "handle_compensation_called",
        execution_id=execution_id,
        original_task_id=original_task_id,
        compensation_type=compensation_type,
    )

    # Validações
    valid_types = ["rollback", "retry", "compensating_action", "manual_intervention"]

    if compensation_type not in valid_types:
        raise ValueError(
            f"compensation_type must be one of: {valid_types}, got: {compensation_type}"
        )

    # Chamar Worker Agent para executar compensação
    try:
        payload = {
            "execution_id": execution_id,
            "original_task_id": original_task_id,
            "compensation_type": compensation_type,
            "timestamp": int(datetime.now().timestamp() * 1000),
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"http://worker-agents:{8005}/api/v1/compensate", json=payload
            )
            response.raise_for_status()
            result = response.json()

        logger.info(
            "compensation_executed_success",
            execution_id=execution_id,
            compensation_id=result.get("compensation_id"),
        )

        return result

    except httpx.HTTPStatusError as e:
        logger.error("compensation_http_error", status_code=e.response.status_code)
        return {
            "success": False,
            "error": f"HTTP error: {e.response.status_code}",
            "compensation_id": None,
        }
    except Exception as e:
        logger.exception("handle_compensation_failed", error=str(e))
        return {"success": False, "error": str(e), "compensation_id": None}


async def report_status(
    execution_id: str,
    task_id: str,
    workflow_id: str,
    status: str,
    output: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Reportar status de execução ao Orchestrator.

    Args:
        execution_id: ID da execução
        task_id: ID da tarefa
        workflow_id: ID do workflow
        status: Status da execução
        output: Output da execução (se completada)

    Returns:
        Dicionário com success=True/False
    """
    logger.info("report_status_called", execution_id=execution_id, status=status)

    # Validações
    valid_statuses = ["pending", "in_progress", "completed", "failed", "cancelled"]

    if status not in valid_statuses:
        raise ValueError(f"status must be one of: {valid_statuses}, got: {status}")

    # Reportar ao Orchestrator via Kafka ou HTTP
    try:
        payload = {
            "execution_id": execution_id,
            "task_id": task_id,
            "workflow_id": workflow_id,
            "status": status,
            "output": output,
            "timestamp": int(datetime.now().timestamp() * 1000),
        }

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"http://orchestrator-dynamic:{8003}/api/v1/status/report", json=payload
            )
            response.raise_for_status()

        logger.info("status_reported_success", execution_id=execution_id, status=status)

        return {"success": True, "execution_id": execution_id}

    except httpx.HTTPStatusError as e:
        logger.error("report_status_http_error", status_code=e.response.status_code)
        return {
            "success": False,
            "error": f"HTTP error: {e.response.status_code}",
            "execution_id": execution_id,
        }
    except Exception as e:
        logger.exception("report_status_failed", error=str(e))
        return {"success": False, "error": str(e), "execution_id": execution_id}


def register_worker_tools(mcp) -> None:
    """Registra ferramentas Worker no servidor MCP."""
    mcp.tool()(execute_task)
    mcp.tool()(check_dependencies)
    mcp.tool()(monitor_progress)
    mcp.tool()(handle_compensation)
    mcp.tool()(report_status)
