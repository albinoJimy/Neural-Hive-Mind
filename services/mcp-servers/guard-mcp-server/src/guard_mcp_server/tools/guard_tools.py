"""
Guard MCP Tools - Ferramentas de validação de segurança.

Ferramentas:
- validate_security: Validar políticas de segurança
- scan_vulnerabilities: Scan de vulnerabilidades
- detect_threats: Detectar ameaças em tempo real
- check_compliance: Verificar compliance regulatório
- remediate_issue: Executar ações de remediação
"""

from datetime import datetime
from typing import Any

import httpx
import structlog

from guard_mcp_server.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()


async def validate_security(
    ticket_id: str,
    task_type: str,
    environment: str,
    security_level: str = "INTERNAL",
) -> dict[str, Any]:
    """
    Validar políticas de segurança para um ExecutionTicket.

    Args:
        ticket_id: ID do ticket
        task_type: Tipo da tarefa (DEPLOY, DELETE, etc.)
        environment: Ambiente (production, staging, development)
        security_level: Nível de segurança (INTERNAL, CONFIDENTIAL, RESTRICTED)

    Returns:
        Dicionário com validation_status, violations, risk_assessment
    """
    logger.info(
        "validate_security_called",
        ticket_id=ticket_id,
        task_type=task_type,
        environment=environment,
    )

    # Validações
    if not ticket_id:
        raise ValueError("ticket_id is required")

    # Chamar Guard Agent via HTTP
    try:
        payload = {
            "ticket_id": ticket_id,
            "task_type": task_type,
            "environment": environment,
            "security_level": security_level,
            "timestamp": int(datetime.now().timestamp() * 1000),
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"http://{settings.guard_agent_host}:{settings.guard_agent_port}/api/v1/security/validate",
                json=payload,
            )
            response.raise_for_status()
            result = response.json()

        logger.info(
            "guard_agent_validate_success",
            ticket_id=ticket_id,
            validation_id=result.get("validation_id"),
        )

        return result

    except httpx.HTTPStatusError as e:
        logger.error("guard_agent_validate_http_error", status_code=e.response.status_code)
        return {
            "error": f"HTTP error: {e.response.status_code}",
            "validation_status": "error",
            "validation_id": None,
        }
    except Exception as e:
        logger.exception("guard_agent_validate_failed", error=str(e))
        return {"error": str(e), "validation_status": "error", "validation_id": None}


async def scan_vulnerabilities(target: str, scan_type: str = "container") -> dict[str, Any]:
    """
    Escanear vulnerabilidades em uma imagem ou código.

    Args:
        target: Alvo do scan (imagem docker, path de código, etc.)
        scan_type: Tipo de scan (container, code, dependency)

    Returns:
        Dicionário com vulnerabilities encontradas e scan_status
    """
    logger.info("scan_vulnerabilities_called", target=target, scan_type=scan_type)

    # Validações
    valid_scan_types = ["container", "code", "dependency", "filesystem", "repository"]

    if scan_type not in valid_scan_types:
        raise ValueError(f"scan_type must be one of: {valid_scan_types}, got: {scan_type}")

    # Chamar Trivy ou Guard Agent
    try:
        payload = {
            "target": target,
            "scan_type": scan_type,
            "timestamp": int(datetime.now().timestamp() * 1000),
        }

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"http://{settings.trivy_host}:{settings.trivy_port}/api/v1/scan",
                json=payload,
            )
            response.raise_for_status()
            result = response.json()

        logger.info(
            "trivy_scan_success", target=target, vuln_count=len(result.get("vulnerabilities", []))
        )

        return result

    except httpx.HTTPStatusError as e:
        logger.error("trivy_scan_http_error", status_code=e.response.status_code)
        return {
            "error": f"HTTP error: {e.response.status_code}",
            "scan_status": "error",
            "vulnerabilities": [],
        }
    except Exception as e:
        logger.exception("trivy_scan_failed", error=str(e))
        return {"error": str(e), "scan_status": "error", "vulnerabilities": []}


async def detect_threats(event_type: str, event_data: dict[str, Any]) -> dict[str, Any]:
    """
    Detectar ameaças em tempo real em eventos de segurança.

    Args:
        event_type: Tipo do evento (authentication, request_metrics, etc.)
        event_data: Dados do evento

    Returns:
        Dicionário com threat_type, severity, confidence se ameaça detectada
    """
    logger.info("detect_threats_called", event_type=event_type, event_id=event_data.get("event_id"))

    # Chamar Guard Agent Threat Detector
    try:
        payload = {
            "event_type": event_type,
            "event_data": event_data,
            "timestamp": int(datetime.now().timestamp() * 1000),
        }

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"http://{settings.guard_agent_host}:{settings.guard_agent_port}/api/v1/threats/detect",
                json=payload,
            )
            response.raise_for_status()
            result = response.json()

        logger.info(
            "threat_detector_success",
            event_type=event_type,
            threat_found=result.get("threat_found", result.get("threat_id") is not None),
        )

        return result

    except httpx.HTTPStatusError as e:
        logger.error("threat_detector_http_error", status_code=e.response.status_code)
        return {
            "error": f"HTTP error: {e.response.status_code}",
            "threat_found": False,
            "threat_id": None,
        }
    except Exception as e:
        logger.exception("threat_detector_failed", error=str(e))
        return {"error": str(e), "threat_found": False, "threat_id": None}


async def check_compliance(ticket_id: str, regulations: list[str] | None = None) -> dict[str, Any]:
    """
    Verificar compliance regulatório para um ticket.

    Args:
        ticket_id: ID do ticket
        regulations: Lista de regulamentos (GDPR, SOC2, ISO27001, etc.)

    Returns:
        Dicionário com compliant=True/False e lista de breaches
    """
    logger.info(
        "check_compliance_called",
        ticket_id=ticket_id,
        regulations=regulations or [],
    )

    # Default regulations
    if regulations is None:
        regulations = ["GDPR", "SOC2"]

    # Chamar Guard Agent Compliance Validator
    try:
        payload = {
            "ticket_id": ticket_id,
            "regulations": regulations,
            "timestamp": int(datetime.now().timestamp() * 1000),
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"http://{settings.guard_agent_host}:{settings.guard_agent_port}/api/v1/compliance/check",
                json=payload,
            )
            response.raise_for_status()
            result = response.json()

        logger.info(
            "compliance_check_success",
            ticket_id=ticket_id,
            compliant=result.get("compliant"),
        )

        return result

    except httpx.HTTPStatusError as e:
        logger.error("compliance_check_http_error", status_code=e.response.status_code)
        return {
            "error": f"HTTP error: {e.response.status_code}",
            "compliant": False,
            "breaches": [],
        }
    except Exception as e:
        logger.exception("compliance_check_failed", error=str(e))
        return {"error": str(e), "compliant": False, "breaches": []}


async def remediate_issue(
    issue_id: str,
    remediation_type: str,
    parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Executar ação de remediação para uma violação de segurança.

    Args:
        issue_id: ID da violação/issue
        remediation_type: Tipo de remediação (block_ip, kill_process, etc.)
        parameters: Parâmetros específicos da remediação

    Returns:
        Dicionário com success=True/False e remediation_id
    """
    logger.info(
        "remediate_issue_called",
        issue_id=issue_id,
        remediation_type=remediation_type,
    )

    # Validações
    valid_types = [
        "block_ip",
        "kill_process",
        "isolate_container",
        "revoke_token",
        "rollback_deployment",
        "manual_intervention",
    ]

    if remediation_type not in valid_types:
        raise ValueError(f"remediation_type must be one of: {valid_types}, got: {remediation_type}")

    # Chamar Guard Agent para executar remediação
    try:
        payload = {
            "issue_id": issue_id,
            "remediation_type": remediation_type,
            "parameters": parameters or {},
            "timestamp": int(datetime.now().timestamp() * 1000),
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"http://{settings.guard_agent_host}:{settings.guard_agent_port}/api/v1/remediate",
                json=payload,
            )
            response.raise_for_status()
            result = response.json()

        logger.info(
            "remediation_executed_success",
            issue_id=issue_id,
            remediation_id=result.get("remediation_id"),
        )

        return result

    except httpx.HTTPStatusError as e:
        logger.error("remediation_http_error", status_code=e.response.status_code)
        return {
            "success": False,
            "error": f"HTTP error: {e.response.status_code}",
            "remediation_id": None,
        }
    except Exception as e:
        logger.exception("remediation_failed", error=str(e))
        return {"success": False, "error": str(e), "remediation_id": None}


def register_guard_tools(mcp) -> None:
    """Registra ferramentas Guard no servidor MCP."""
    mcp.tool()(validate_security)
    mcp.tool()(scan_vulnerabilities)
    mcp.tool()(detect_threats)
    mcp.tool()(check_compliance)
    mcp.tool()(remediate_issue)
