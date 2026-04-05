"""
Architect MCP Tools - Ferramentas de análise arquitetural.

Ferramentas:
- plan_architecture: Planejar arquitetura de features
- validate_design: Validar designs contra padrões
- track_evolution: Rastrear evolução arquitetural
- analyze_patterns: Analisar padrões arquiteturais
- generate_documentation: Gerar documentação automática
"""

from datetime import datetime
from typing import Any

import httpx
import structlog

from architect_mcp_server.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()


async def plan_architecture(
    ticket_id: str,
    feature_name: str,
    feature_description: str,
    requirements: list[str] | None = None,
    constraints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Planejar arquitetura para uma nova feature.

    Args:
        ticket_id: ID do ticket associado
        feature_name: Nome da feature
        feature_description: Descrição da feature
        requirements: Lista de requisitos funcionais e não-funcionais
        constraints: Restrições (tempo, equipe, complexidade)

    Returns:
        Dicionário com plano arquitetural incluindo componentes, dataflows, padrões
    """
    logger.info(
        "plan_architecture_called",
        ticket_id=ticket_id,
        feature_name=feature_name,
    )

    # Validações
    if not ticket_id:
        raise ValueError("ticket_id is required")

    # Chamar Architect Agent via HTTP
    try:
        payload = {
            "ticket_id": ticket_id,
            "feature_name": feature_name,
            "feature_description": feature_description,
            "requirements": requirements or [],
            "constraints": constraints or {},
            "timestamp": int(datetime.now().timestamp() * 1000),
        }

        async with httpx.AsyncClient(timeout=settings.analysis_timeout) as client:
            response = await client.post(
                f"http://{settings.architect_agent_host}:{settings.architect_agent_port}/api/v1/architecture/plan",
                json=payload,
            )
            response.raise_for_status()
            result = response.json()

        logger.info(
            "architect_agent_plan_success",
            ticket_id=ticket_id,
            plan_id=result.get("plan_id"),
        )

        return result

    except httpx.HTTPStatusError as e:
        logger.error("architect_agent_plan_http_error", status_code=e.response.status_code)
        return {
            "error": f"HTTP error: {e.response.status_code}",
            "status": "error",
            "plan_id": None,
        }
    except Exception as e:
        logger.exception("architect_agent_plan_failed", error=str(e))
        return {"error": str(e), "status": "error", "plan_id": None}


async def validate_design(
    design_document: dict[str, Any],
    validation_profile: str = "standard",
) -> dict[str, Any]:
    """
    Validar design document contra padrões arquiteturais.

    Args:
        design_document: Documento de design a ser validado
        validation_profile: Perfil de validação (strict, standard, lenient)

    Returns:
        Dicionário com valid, violations, warnings, pattern_compliance
    """
    logger.info(
        "validate_design_called",
        design_id=design_document.get("design_id"),
        profile=validation_profile,
    )

    # Validações
    valid_profiles = ["strict", "standard", "lenient"]

    if validation_profile not in valid_profiles:
        raise ValueError(
            f"validation_profile must be one of: {valid_profiles}, got: {validation_profile}"
        )

    # Chamar Architect Agent para validação
    try:
        payload = {
            "design_document": design_document,
            "validation_profile": validation_profile,
            "timestamp": int(datetime.now().timestamp() * 1000),
        }

        async with httpx.AsyncClient(timeout=settings.validation_timeout) as client:
            response = await client.post(
                f"http://{settings.architect_agent_host}:{settings.architect_agent_port}/api/v1/design/validate",
                json=payload,
            )
            response.raise_for_status()
            result = response.json()

        logger.info(
            "design_validation_success",
            design_id=design_document.get("design_id"),
            valid=result.get("valid"),
        )

        return result

    except httpx.HTTPStatusError as e:
        logger.error("design_validation_http_error", status_code=e.response.status_code)
        return {
            "error": f"HTTP error: {e.response.status_code}",
            "valid": False,
            "violations": [],
        }
    except Exception as e:
        logger.exception("design_validation_failed", error=str(e))
        return {"error": str(e), "valid": False, "violations": []}


async def track_evolution(
    current_state: dict[str, Any],
    changes: list[dict[str, Any]],
    change_type: str = "minor",
) -> dict[str, Any]:
    """
    Rastrear evolução arquitetural do sistema.

    Args:
        current_state: Estado atual da arquitetura
        changes: Lista de mudanças propostas
        change_type: Tipo de mudança (major, minor, patch)

    Returns:
        Dicionário com new_version, evolution_path, breaking_changes
    """
    logger.info(
        "track_evolution_called",
        current_version=current_state.get("version"),
        change_type=change_type,
    )

    # Validações
    valid_change_types = ["major", "minor", "patch"]

    if change_type not in valid_change_types:
        raise ValueError(
            f"change_type must be one of: {valid_change_types}, got: {change_type}"
        )

    # Chamar Architect Agent para rastrear evolução
    try:
        payload = {
            "current_state": current_state,
            "changes": changes,
            "change_type": change_type,
            "timestamp": int(datetime.now().timestamp() * 1000),
        }

        async with httpx.AsyncClient(timeout=settings.validation_timeout) as client:
            response = await client.post(
                f"http://{settings.architect_agent_host}:{settings.architect_agent_port}/api/v1/evolution/track",
                json=payload,
            )
            response.raise_for_status()
            result = response.json()

        logger.info(
            "evolution_track_success",
            previous_version=result.get("previous_version"),
            new_version=result.get("new_version"),
        )

        return result

    except httpx.HTTPStatusError as e:
        logger.error("evolution_track_http_error", status_code=e.response.status_code)
        return {
            "error": f"HTTP error: {e.response.status_code}",
            "new_version": current_state.get("version"),
            "breaking_changes": [],
        }
    except Exception as e:
        logger.exception("evolution_track_failed", error=str(e))
        return {
            "error": str(e),
            "new_version": current_state.get("version"),
            "breaking_changes": [],
        }


async def analyze_patterns(
    repository_path: str,
    analysis_depth: str = "standard",
    focus_areas: list[str] | None = None,
) -> dict[str, Any]:
    """
    Analisar padrões arquiteturais e anti-patterns no código.

    Args:
        repository_path: Caminho do repositório a analisar
        analysis_depth: Profundidade da análise (quick, standard, deep)
        focus_areas: Áreas de foco (services, communication, data, etc.)

    Returns:
        Dicionário com patterns_detected, anti_patterns_detected, metrics
    """
    logger.info(
        "analyze_patterns_called",
        repository_path=repository_path,
        depth=analysis_depth,
    )

    # Validações
    valid_depths = ["quick", "standard", "deep"]

    if analysis_depth not in valid_depths:
        raise ValueError(
            f"analysis_depth must be one of: {valid_depths}, got: {analysis_depth}"
        )

    # Chamar Architect Agent para análise
    try:
        payload = {
            "repository_path": repository_path,
            "analysis_depth": analysis_depth,
            "focus_areas": focus_areas or [],
            "timestamp": int(datetime.now().timestamp() * 1000),
        }

        async with httpx.AsyncClient(timeout=settings.analysis_timeout) as client:
            response = await client.post(
                f"http://{settings.architect_agent_host}:{settings.architect_agent_port}/api/v1/patterns/analyze",
                json=payload,
            )
            response.raise_for_status()
            result = response.json()

        logger.info(
            "pattern_analysis_success",
            patterns_count=len(result.get("patterns_detected", [])),
            anti_patterns_count=len(result.get("anti_patterns_detected", [])),
        )

        return result

    except httpx.HTTPStatusError as e:
        logger.error("pattern_analysis_http_error", status_code=e.response.status_code)
        return {
            "error": f"HTTP error: {e.response.status_code}",
            "patterns_detected": [],
            "anti_patterns_detected": [],
            "metrics": {},
        }
    except Exception as e:
        logger.exception("pattern_analysis_failed", error=str(e))
        return {
            "error": str(e),
            "patterns_detected": [],
            "anti_patterns_detected": [],
            "metrics": {},
        }


async def generate_documentation(
    ticket_id: str,
    doc_type: str,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Gerar documentação arquitetural automática.

    Args:
        ticket_id: ID do ticket associado
        doc_type: Tipo de documento (adr, system_design, api_docs, etc.)
        config: Configurações específicas do documento

    Returns:
        Dicionário com doc_id, content, output_path, download_urls
    """
    logger.info(
        "generate_documentation_called",
        ticket_id=ticket_id,
        doc_type=doc_type,
    )

    # Validações
    valid_doc_types = [
        "architecture_decision_record",
        "system_design",
        "api_documentation",
        "data_model",
        "deployment_guide",
        "runbook",
    ]

    if doc_type not in valid_doc_types:
        raise ValueError(
            f"doc_type must be one of: {valid_doc_types}, got: {doc_type}"
        )

    # Chamar Architect Agent para gerar documentação
    try:
        payload = {
            "ticket_id": ticket_id,
            "doc_type": doc_type,
            "config": config or {},
            "timestamp": int(datetime.now().timestamp() * 1000),
        }

        async with httpx.AsyncClient(timeout=settings.doc_generation_timeout) as client:
            response = await client.post(
                f"http://{settings.architect_agent_host}:{settings.architect_agent_port}/api/v1/documentation/generate",
                json=payload,
            )
            response.raise_for_status()
            result = response.json()

        logger.info(
            "documentation_generation_success",
            ticket_id=ticket_id,
            doc_id=result.get("doc_id"),
        )

        return result

    except httpx.HTTPStatusError as e:
        logger.error("documentation_generation_http_error", status_code=e.response.status_code)
        return {
            "error": f"HTTP error: {e.response.status_code}",
            "status": "error",
            "doc_id": None,
        }
    except Exception as e:
        logger.exception("documentation_generation_failed", error=str(e))
        return {"error": str(e), "status": "error", "doc_id": None}


def register_architect_tools(mcp) -> None:
    """Registra ferramentas Architect no servidor MCP."""
    mcp.tool()(plan_architecture)
    mcp.tool()(validate_design)
    mcp.tool()(track_evolution)
    mcp.tool()(analyze_patterns)
    mcp.tool()(generate_documentation)
