"""
Healer MCP Tools - Ferramentas de auto-recuperação.

Ferramentas:
- detect_incident: Detectar incidentes automaticamente
- execute_playbook: Executar playbooks de recuperação
- validate_recovery: Validar sucesso da recuperação
- monitor_health: Monitorar saúde dos serviços
- escalate_issue: Escalar incidentes não resolvidos
"""

from datetime import datetime
from typing import Any

import httpx
import structlog

from healer_mcp_server.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()


async def detect_incident(
    service: str,
    incident_type: str,
    metrics: dict[str, Any],
) -> dict[str, Any]:
    """
    Detectar incidentes automaticamente baseado em métricas.

    Args:
        service: Nome do serviço afetado
        incident_type: Tipo do incidente (pod_crash_loop, high_memory_usage, etc.)
        metrics: Métricas relevantes para detecção

    Returns:
        Dicionário com incident_id, severity, suggested_playbook, auto_recoverable
    """
    logger.info(
        "detect_incident_called",
        service=service,
        incident_type=incident_type,
    )

    # Validações
    if not service:
        raise ValueError("service is required")

    # Chamar Healer Agent via HTTP
    try:
        payload = {
            "service": service,
            "incident_type": incident_type,
            "metrics": metrics,
            "timestamp": int(datetime.now().timestamp() * 1000),
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"http://{settings.healer_agent_host}:{settings.healer_agent_port}/api/v1/incidents/detect",
                json=payload,
            )
            response.raise_for_status()
            result = response.json()

        logger.info(
            "healer_agent_detect_success",
            service=service,
            incident_id=result.get("incident_id"),
        )

        return result

    except httpx.HTTPStatusError as e:
        logger.error("healer_agent_detect_http_error", status_code=e.response.status_code)
        return {
            "error": f"HTTP error: {e.response.status_code}",
            "incident_id": None,
            "incident_type": incident_type,
            "service": service,
        }
    except Exception as e:
        logger.exception("healer_agent_detect_failed", error=str(e))
        return {"error": str(e), "incident_id": None, "incident_type": incident_type, "service": service}


async def execute_playbook(
    incident_id: str,
    playbook_id: str,
    parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Executar playbook de recuperação para um incidente.

    Args:
        incident_id: ID do incidente
        playbook_id: ID do playbook a executar
        parameters: Parâmetros específicos do playbook

    Returns:
        Dicionário com execution_id, execution_status, recovery_achieved
    """
    logger.info(
        "execute_playbook_called",
        incident_id=incident_id,
        playbook_id=playbook_id,
    )

    # Validações
    if not incident_id:
        raise ValueError("incident_id is required")

    # Chamar Healer Agent via HTTP
    try:
        payload = {
            "incident_id": incident_id,
            "playbook_id": playbook_id,
            "parameters": parameters or {},
            "timestamp": int(datetime.now().timestamp() * 1000),
        }

        async with httpx.AsyncClient(timeout=settings.timeout) as client:
            response = await client.post(
                f"http://{settings.healer_agent_host}:{settings.healer_agent_port}/api/v1/playbooks/execute",
                json=payload,
            )
            response.raise_for_status()
            result = response.json()

        logger.info(
            "healer_agent_execute_success",
            incident_id=incident_id,
            execution_id=result.get("execution_id"),
        )

        return result

    except httpx.HTTPStatusError as e:
        logger.error("healer_agent_execute_http_error", status_code=e.response.status_code)
        return {
            "error": f"HTTP error: {e.response.status_code}",
            "execution_id": None,
            "execution_status": "error",
            "recovery_achieved": False,
        }
    except Exception as e:
        logger.exception("healer_agent_execute_failed", error=str(e))
        return {"error": str(e), "execution_id": None, "execution_status": "error", "recovery_achieved": False}


async def validate_recovery(
    incident_id: str,
    playbook_id: str,
) -> dict[str, Any]:
    """
    Validar sucesso da recuperação executada.

    Args:
        incident_id: ID do incidente
        playbook_id: ID do playbook executado

    Returns:
        Dicionário com recovery_status, all_checks_passed, can_close_incident
    """
    logger.info(
        "validate_recovery_called",
        incident_id=incident_id,
        playbook_id=playbook_id,
    )

    # Validações
    if not incident_id:
        raise ValueError("incident_id is required")

    # Chamar Healer Agent via HTTP
    try:
        payload = {
            "incident_id": incident_id,
            "playbook_id": playbook_id,
            "timestamp": int(datetime.now().timestamp() * 1000),
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"http://{settings.healer_agent_host}:{settings.healer_agent_port}/api/v1/recovery/validate",
                json=payload,
            )
            response.raise_for_status()
            result = response.json()

        logger.info(
            "healer_agent_validate_success",
            incident_id=incident_id,
            recovery_status=result.get("recovery_status"),
        )

        return result

    except httpx.HTTPStatusError as e:
        logger.error("healer_agent_validate_http_error", status_code=e.response.status_code)
        return {
            "error": f"HTTP error: {e.response.status_code}",
            "recovery_status": "error",
            "all_checks_passed": False,
            "can_close_incident": False,
        }
    except Exception as e:
        logger.exception("healer_agent_validate_failed", error=str(e))
        return {
            "error": str(e),
            "recovery_status": "error",
            "all_checks_passed": False,
            "can_close_incident": False,
        }


async def monitor_health(
    service: str,
    checks: list[str] | None = None,
) -> dict[str, Any]:
    """
    Monitorar saúde de um serviço.

    Args:
        service: Nome do serviço a monitorizar
        checks: Lista de checks (liveness, readiness, startup, etc.)

    Returns:
        Dicionário com overall_status, endpoints, metrics, issues
    """
    logger.info(
        "monitor_health_called",
        service=service,
        checks=checks or [],
    )

    # Validações
    if not service:
        raise ValueError("service is required")

    # Chamar Healer Agent via HTTP
    try:
        params = {
            "service": service,
            "checks": checks or ["liveness", "readiness"],
            "timestamp": int(datetime.now().timestamp() * 1000),
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"http://{settings.healer_agent_host}:{settings.healer_agent_port}/api/v1/health",
                params=params,
            )
            response.raise_for_status()
            result = response.json()

        logger.info(
            "healer_agent_health_success",
            service=service,
            overall_status=result.get("overall_status"),
        )

        return result

    except httpx.HTTPStatusError as e:
        logger.error("healer_agent_health_http_error", status_code=e.response.status_code)
        return {
            "error": f"HTTP error: {e.response.status_code}",
            "service": service,
            "overall_status": "error",
            "endpoints": [],
            "issues": [],
        }
    except Exception as e:
        logger.exception("healer_agent_health_failed", error=str(e))
        return {
            "error": str(e),
            "service": service,
            "overall_status": "error",
            "endpoints": [],
            "issues": [],
        }


async def escalate_issue(
    incident_id: str,
    target_team: str,
    urgency: str,
    reason: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Escalar incidente não resolvido para time apropriado.

    Args:
        incident_id: ID do incidente
        target_team: Time alvo (sre_team, platform_team, etc.)
        urgency: Urgência (low, medium, high, critical)
        reason: Razão do escalamento
        context: Contexto adicional sobre o incidente

    Returns:
        Dicionário com escalation_id, status, ticket_url
    """
    logger.info(
        "escalate_issue_called",
        incident_id=incident_id,
        target_team=target_team,
        urgency=urgency,
    )

    # Validações
    if not incident_id:
        raise ValueError("incident_id is required")

    valid_urgencies = ["low", "medium", "high", "critical"]
    if urgency not in valid_urgencies:
        raise ValueError(
            f"urgency must be one of: {valid_urgencies}, got: {urgency}"
        )

    # Chamar Healer Agent via HTTP
    try:
        payload = {
            "incident_id": incident_id,
            "target_team": target_team,
            "urgency": urgency,
            "reason": reason,
            "context": context or {},
            "timestamp": int(datetime.now().timestamp() * 1000),
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"http://{settings.healer_agent_host}:{settings.healer_agent_port}/api/v1/incidents/escalate",
                json=payload,
            )
            response.raise_for_status()
            result = response.json()

        logger.info(
            "healer_agent_escalate_success",
            incident_id=incident_id,
            escalation_id=result.get("escalation_id"),
        )

        return result

    except httpx.HTTPStatusError as e:
        logger.error("healer_agent_escalate_http_error", status_code=e.response.status_code)
        return {
            "error": f"HTTP error: {e.response.status_code}",
            "escalation_id": None,
            "status": "error",
        }
    except Exception as e:
        logger.exception("healer_agent_escalate_failed", error=str(e))
        return {"error": str(e), "escalation_id": None, "status": "error"}


def register_healer_tools(mcp) -> None:
    """Registra ferramentas Healer no servidor MCP."""
    mcp.tool()(detect_incident)
    mcp.tool()(execute_playbook)
    mcp.tool()(validate_recovery)
    mcp.tool()(monitor_health)
    mcp.tool()(escalate_issue)
