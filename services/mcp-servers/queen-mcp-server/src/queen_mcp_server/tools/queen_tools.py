"""
Queen MCP Tools - Ferramentas estratégicas do Queen Agent.

Ferramentas:
- make_decision: Tomar decisões estratégicas
- arbitrate_conflict: Resolver conflitos entre agentes
- replan_workflow: Replanejar workflows falhados
- approve_exception: Aprovar exceções à política
- adjust_qos: Ajustar QoS de serviços
"""

from datetime import datetime
from typing import Any

import structlog
import httpx

from queen_mcp_server.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()


async def make_decision(
    event_type: str, source_id: str, trigger_data: dict[str, Any], priority: str = "normal"
) -> dict[str, Any]:
    """
    Tomar decisão estratégica baseada em evento trigger.

    Args:
        event_type: Tipo de evento (consolidated_decision, telemetry, critical_incident)
        source_id: ID da fonte do evento
        trigger_data: Dados do trigger
        priority: Prioridade da decisão (low, normal, high, critical)

    Returns:
        Dicionário com decisão estratégica
    """
    logger.info(
        "make_decision_called", event_type=event_type, source_id=source_id, priority=priority
    )

    # Validar event_type
    valid_event_types = [
        "consolidated_decision",
        "telemetry",
        "critical_incident",
        "sla_violation",
        "resource_saturation",
    ]

    if event_type not in valid_event_types:
        raise ValueError(
            f"Invalid event_type: {event_type}. " f"Must be one of: {', '.join(valid_event_types)}"
        )

    # Chamar Queen Agent via gRPC
    decision_data = await _call_queen_agent_decision(event_type, source_id, trigger_data)

    return decision_data


async def arbitrate_conflict(
    decisions: list[dict[str, Any]], conflict_description: str | None = None
) -> dict[str, Any]:
    """
    Arbitrar conflito entre decisões de múltiplos especialistas.

    Args:
        decisions: Lista de decisões em conflito
        conflict_description: Descrição opcional do conflito

    Returns:
        Dicionário com resolução do conflito
    """
    logger.info(
        "arbitrate_conflict_called",
        decisions_count=len(decisions),
        has_description=conflict_description is not None,
    )

    if len(decisions) < 2:
        raise ValueError("At least 2 decisions are required for conflict arbitration")

    # Chamar Queen Agent para arbitragem
    resolution = await _call_queen_agent_arbitration(decisions, conflict_description)

    return resolution


async def replan_workflow(
    plan_id: str,
    reason: str,
    trigger_type: str = "STRATEGIC",
    preserve_progress: bool = True,
    priority: int = 5,
) -> dict[str, Any]:
    """
    Acionar replanejamento de um workflow/plano cognitivo.

    Args:
        plan_id: ID do plano a ser replanejado
        reason: Razão do replanejamento
        trigger_type: Tipo de trigger (STRATEGIC, MANUAL, ERROR)
        preserve_progress: Se deve preservar progresso
        priority: Prioridade do replanejamento (1-10)

    Returns:
        Dicionário com resultado do replanejamento
    """
    logger.info("replan_workflow_called", plan_id=plan_id, reason=reason, trigger_type=trigger_type)

    # Chamar Queen Agent para replanejamento
    replanning_result = await _call_queen_agent_replanning(
        plan_id, reason, trigger_type, preserve_progress, priority
    )

    return replanning_result


async def approve_exception(
    exception_request_id: str,
    justification: str,
    risk_score: float,
    requested_by: str,
    expires_at: str | None = None,
) -> dict[str, Any]:
    """
    Aprovar exceção à política (ex: bypass de guardrail).

    Args:
        exception_request_id: ID do pedido de exceção
        justification: Justificativa para a exceção
        risk_score: Score de risco (0.0 a 1.0)
        requested_by: Quem solicitou
        expires_at: Timestamp de expiração (opcional)

    Returns:
        Dicionário com decisão de aprovação
    """
    logger.info(
        "approve_exception_called",
        exception_request_id=exception_request_id,
        requested_by=requested_by,
        risk_score=risk_score,
    )

    # Validar risk_score
    if not 0.0 <= risk_score <= 1.0:
        raise ValueError(f"risk_score must be between 0.0 and 1.0, got {risk_score}")

    # Chamar Queen Agent para aprovação
    approval_result = await _call_queen_agent_exception_approval(
        exception_request_id, justification, risk_score, requested_by, expires_at
    )

    return approval_result


async def adjust_qos(
    workflow_id: str,
    adjustment_type: str,
    new_priority: int | None = None,
    reason: str | None = None,
    duration_seconds: int | None = None,
) -> dict[str, Any]:
    """
    Ajustar QoS (Quality of Service) de um workflow.

    Args:
        workflow_id: ID do workflow
        adjustment_type: Tipo de ajuste (increase_priority, decrease_priority,
                              pause_execution, resume_execution, allocate_resources)
        new_priority: Nova prioridade (1-10)
        reason: Razão do ajuste
        duration_seconds: Duração (para pausas temporárias)

    Returns:
        Dicionário com resultado do ajuste
    """
    logger.info("adjust_qos_called", workflow_id=workflow_id, adjustment_type=adjustment_type)

    # Validar adjustment_type
    valid_types = [
        "increase_priority",
        "decrease_priority",
        "pause_execution",
        "resume_execution",
        "allocate_resources",
    ]

    if adjustment_type not in valid_types:
        raise ValueError(
            f"Invalid adjustment_type: {adjustment_type}. "
            f"Must be one of: {', '.join(valid_types)}"
        )

    # Chamar Queen Agent para ajuste de QoS
    qos_result = await _call_queen_agent_qos_adjustment(
        workflow_id, adjustment_type, new_priority, reason, duration_seconds
    )

    return qos_result


# ============ Helper Functions ============


async def _call_queen_agent_decision(
    event_type: str, source_id: str, trigger_data: dict[str, Any]
) -> dict[str, Any]:
    """Chamar Queen Agent para tomada de decisão estratégica."""
    try:
        # Preparar payload
        payload = {
            "event_type": event_type,
            "source_id": source_id,
            "trigger_data": trigger_data,
            "timestamp": int(datetime.now().timestamp() * 1000),
        }

        # Chamar via HTTP/gRPC
        async with httpx.AsyncClient(timeout=settings.decision_timeout) as client:
            response = await client.post(
                f"http://{settings.queen_agent_host}:{settings.queen_agent_port}/api/v1/decisions",
                json=payload,
            )
            response.raise_for_status()
            result = response.json()

        logger.info(
            "queen_agent_decision_success",
            decision_id=result.get("decision_id"),
            decision_type=result.get("decision_type"),
        )

        return result

    except httpx.HTTPStatusError as e:
        logger.error("queen_agent_decision_http_error", status_code=e.response.status_code)
        return {
            "error": f"HTTP error: {e.response.status_code}",
            "decision_id": None,
            "decision_type": "ERROR",
        }
    except Exception as e:
        logger.exception("queen_agent_decision_failed", error=str(e))
        return {"error": str(e), "decision_id": None, "decision_type": "ERROR"}


async def _call_queen_agent_arbitration(
    decisions: list[dict[str, Any]], conflict_description: str | None
) -> dict[str, Any]:
    """Chamar Queen Agent para arbitragem de conflito."""
    try:
        # Preparar payload
        payload = {
            "decisions": decisions,
            "conflict_description": conflict_description,
            "timestamp": int(datetime.now().timestamp() * 1000),
        }

        async with httpx.AsyncClient(timeout=settings.decision_timeout) as client:
            response = await client.post(
                f"http://{settings.queen_agent_host}:{settings.queen_agent_port}/api/v1/conflicts/arbitrate",
                json=payload,
            )
            response.raise_for_status()
            result = response.json()

        logger.info(
            "queen_agent_arbitration_success",
            conflict_id=result.get("conflict_id"),
            resolution_strategy=result.get("resolution_strategy"),
        )

        return result

    except httpx.HTTPStatusError as e:
        logger.error("queen_agent_arbitration_http_error", status_code=e.response.status_code)
        return {
            "error": f"HTTP error: {e.response.status_code}",
            "conflict_id": None,
            "resolution_strategy": "ERROR",
        }
    except Exception as e:
        logger.exception("queen_agent_arbitration_failed", error=str(e))
        return {"error": str(e), "conflict_id": None, "resolution_strategy": "ERROR"}


async def _call_queen_agent_replanning(
    plan_id: str, reason: str, trigger_type: str, preserve_progress: bool, priority: int
) -> dict[str, Any]:
    """Chamar Queen Agent para replanejamento."""
    try:
        # Preparar payload
        payload = {
            "plan_id": plan_id,
            "reason": reason,
            "trigger_type": trigger_type,
            "preserve_progress": preserve_progress,
            "priority": priority,
        }

        async with httpx.AsyncClient(timeout=settings.decision_timeout) as client:
            response = await client.post(
                f"http://{settings.queen_agent_host}:{settings.queen_agent_port}/api/v1/replanning/trigger",
                json=payload,
            )
            response.raise_for_status()
            result = response.json()

        logger.info(
            "queen_agent_replanning_success",
            plan_id=plan_id,
            replanning_id=result.get("replanning_id"),
        )

        return result

    except httpx.HTTPStatusError as e:
        logger.error("queen_agent_replanning_http_error", status_code=e.response.status_code)
        return {
            "error": f"HTTP error: {e.response.status_code}",
            "replanning_id": None,
            "success": False,
        }
    except Exception as e:
        logger.exception("queen_agent_replanning_failed", error=str(e))
        return {"error": str(e), "replanning_id": None, "success": False}


async def _call_queen_agent_exception_approval(
    exception_request_id: str,
    justification: str,
    risk_score: float,
    requested_by: str,
    expires_at: str | None,
) -> dict[str, Any]:
    """Chamar Queen Agent para aprovação de exceção."""
    try:
        # Preparar payload
        payload = {
            "exception_request_id": exception_request_id,
            "justification": justification,
            "risk_score": risk_score,
            "requested_by": requested_by,
            "expires_at": expires_at,
        }

        async with httpx.AsyncClient(timeout=settings.decision_timeout) as client:
            response = await client.post(
                f"http://{settings.queen_agent_host}:{settings.queen_agent_port}/api/v1/exceptions/approve",
                json=payload,
            )
            response.raise_for_status()
            result = response.json()

        logger.info(
            "queen_agent_exception_approval_success",
            exception_request_id=exception_request_id,
            approved=result.get("approved", False),
        )

        return result

    except httpx.HTTPStatusError as e:
        logger.error(
            "queen_agent_exception_approval_http_error", status_code=e.response.status_code
        )
        return {"error": f"HTTP error: {e.response.status_code}", "approved": False}
    except Exception as e:
        logger.exception("queen_agent_exception_approval_failed", error=str(e))
        return {"error": str(e), "approved": False}


async def _call_queen_agent_qos_adjustment(
    workflow_id: str,
    adjustment_type: str,
    new_priority: int | None,
    reason: str | None,
    duration_seconds: int | None,
) -> dict[str, Any]:
    """Chamar Queen Agent para ajuste de QoS."""
    try:
        # Preparar payload
        payload = {
            "workflow_id": workflow_id,
            "adjustment_type": adjustment_type,
            "new_priority": new_priority,
            "reason": reason,
            "duration_seconds": duration_seconds,
        }

        async with httpx.AsyncClient(timeout=settings.decision_timeout) as client:
            response = await client.post(
                f"http://{settings.queen_agent_host}:{settings.queen_agent_port}/api/v1/qos/adjust",
                json=payload,
            )
            response.raise_for_status()
            result = response.json()

        logger.info(
            "queen_agent_qos_adjustment_success",
            workflow_id=workflow_id,
            adjustment_type=adjustment_type,
        )

        return result

    except httpx.HTTPStatusError as e:
        logger.error("queen_agent_qos_adjustment_http_error", status_code=e.response.status_code)
        return {"error": f"HTTP error: {e.response.status_code}", "success": False}
    except Exception as e:
        logger.exception("queen_agent_qos_adjustment_failed", error=str(e))
        return {"error": str(e), "success": False}


async def health_check(include_services: bool = False) -> dict[str, Any]:
    """
    Verifica saúde do Queen MCP Server e suas dependências.

    Args:
        include_services: Se deve incluir verificação de serviços externos

    Returns:
        Dicionário com status de saúde dos componentes
    """
    logger.info("health_check_called", include_services=include_services)

    import socket
    from datetime import datetime

    status = {
        "server": "queen-mcp-server",
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": settings.service_version,
        "components": {"mcp_server": "healthy"},
    }

    # Verificar conexão com Queen Agent se solicitado
    if include_services:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex((settings.queen_agent_host, settings.queen_agent_port))
            sock.close()

            if result == 0:
                status["components"]["queen_agent"] = "healthy"
                status["queen_agent_connection"] = (
                    f"{settings.queen_agent_host}:{settings.queen_agent_port}"
                )
            else:
                status["components"]["queen_agent"] = "unreachable"
                status["status"] = "degraded"

        except Exception as e:
            logger.warning("queen_agent_health_check_failed", error=str(e))
            status["components"]["queen_agent"] = "error"
            status["status"] = "degraded"

    return status


def register_queen_tools(mcp) -> None:
    """Registra ferramentas Queen no servidor MCP."""
    mcp.tool()(make_decision)
    mcp.tool()(arbitrate_conflict)
    mcp.tool()(replan_workflow)
    mcp.tool()(approve_exception)
    mcp.tool()(adjust_qos)
    mcp.tool()(health_check)
