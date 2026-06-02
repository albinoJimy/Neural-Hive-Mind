"""
Activity Temporal para integração G6 - Code Generation com Code-Forge.

Integra com code-forge via API REST para geração de código a partir
de requisitos e documentação gerados no Fluxo G.
"""

import asyncio
from typing import Any

import httpx
import structlog
from temporalio import activity

logger = structlog.get_logger(__name__)

# Cliente HTTP (injetado pelo worker)
_http_client: httpx.AsyncClient | None = None


def set_code_generation_dependencies(http_client: httpx.AsyncClient):
    """Injeta dependências para activities de geração de código."""
    global _http_client
    _http_client = http_client


@activity.defn
async def generate_code(
    requirements_set: dict[str, Any],
    documentation: dict[str, Any],
    cognitive_plan: dict[str, Any],
) -> dict[str, Any]:
    """
    G6: Gera código fonte a partir de requisitos e documentação.

    Integra com code-forge via API REST /api/v1/generate.

    Args:
        requirements_set: Saída do G1 (generate_requirements)
        documentation: Saída do G2 (generate_documentation)
        cognitive_plan: Plano cognitivo original com parâmetros

    Returns:
        Dict com:
            - request_id: ID da requisição de geração
            - code_artifact_id: ID do artefato de código gerado
            - language: Linguagem do código gerado
            - framework: Framework utilizado
            - generation_method: Método de geração
            - confidence_score: Confiança na qualidade
            - code_preview: Primeiras linhas do código
            - status: Status final da geração

    Raises:
        RuntimeError: Se a geração falhar
        TimeoutError: Se a geração demorar mais que 10 minutos
    """
    plan_id = cognitive_plan.get("plan_id", "unknown")
    intent_id = cognitive_plan.get("intent_id", "")

    logger.info(
        "G6: Gerando código",
        plan_id=plan_id,
        intent_id=intent_id,
    )

    # Extrair parâmetros do cognitive_plan
    parameters = cognitive_plan.get("parameters", {}) or cognitive_plan.get("metadata", {})

    # Determinar linguagem e framework
    language = parameters.get("language", "python")
    framework = parameters.get("framework", "fastapi")
    artifact_type = parameters.get("artifact_type", "microservice")
    generation_method = parameters.get("generation_method", "LLM")

    # Preparar payload para code-forge
    payload = {
        "ticket_id": f"TKT-{plan_id}",
        "template_id": f"tmpl-{language}-{framework}",
        "parameters": {
            "language": language,
            "framework": framework,
            "service_name": f"service-{plan_id}",
            "artifact_type": artifact_type,
            "generation_method": generation_method,
            "include_tests": True,
            "include_iac": True,
        },
        "requirements": requirements_set,
        "documentation": documentation,
        "plan_id": plan_id,
        "intent_id": intent_id,
    }

    try:
        # Usar cliente injetado ou criar novo
        client = _http_client or httpx.AsyncClient(timeout=600.0)

        # Chamar code-forge API para iniciar geração
        response = await client.post(
            "http://code-forge:8020/api/v1/generate",
            json=payload,
            headers={"Content-Type": "application/json"},
        )

        if response.status_code != 202:
            logger.error(
                "code_generation_failed",
                status_code=response.status_code,
                response_text=response.text,
            )
            raise RuntimeError(f"Falha ao iniciar geração: HTTP {response.status_code}")

        result = response.json()
        request_id = result.get("request_id")

        logger.info(
            "code_generation_started",
            request_id=request_id,
            plan_id=plan_id,
        )

        # Poll para completude
        final_result = await _wait_for_generation(client, request_id, plan_id)

        logger.info(
            "code_generation_completed",
            request_id=request_id,
            plan_id=plan_id,
            artifact_id=final_result.get("code_artifact_id"),
        )

        return final_result

    except httpx.TimeoutException:
        logger.error("code_generation_timeout", plan_id=plan_id)
        raise TimeoutError("Geração de código timeout após 10 minutos")
    except Exception as e:
        logger.exception("code_generation_exception", plan_id=plan_id, error=str(e))
        raise


async def _wait_for_generation(
    client: httpx.AsyncClient,
    request_id: str,
    plan_id: str,
    max_wait: int = 600,
    poll_interval: int = 5,
) -> dict[str, Any]:
    """
    Aguarda a geração de código completar.

    Args:
        client: HTTP client
        request_id: ID da requisição de geração
        plan_id: Plan ID para logging
        max_wait: Tempo máximo de espera em segundos
        poll_interval: Intervalo entre polls em segundos

    Returns:
        Resultado final da geração com artefatos

    Raises:
        TimeoutError: Se a geração não completar no tempo máximo
        RuntimeError: Se a geração falhar
    """
    started = asyncio.get_event_loop().time()
    last_status = None

    while True:
        elapsed = asyncio.get_event_loop().time() - started

        if elapsed > max_wait:
            raise TimeoutError(f"Geração timeout após {max_wait}s")

        try:
            response = await client.get(f"http://code-forge:8020/api/v1/generate/{request_id}")

            if response.status_code == 200:
                status_data = response.json()
                last_status = status_data.get("status")

                logger.debug(
                    "code_generation_poll",
                    request_id=request_id,
                    status=last_status,
                    elapsed_ms=int(elapsed * 1000),
                )

                if last_status in ("completed", "failed", "requires_review"):
                    if last_status != "completed":
                        error = status_data.get("error", "Status não completado")
                        raise RuntimeError(f"Geração falhou: {error}")

                    # Extrair artefatos
                    artifacts = status_data.get("artifacts", [])
                    code_artifact = None

                    for artifact in artifacts:
                        if artifact.get("artifact_type") == "code":
                            code_artifact = artifact
                            break

                    if not code_artifact:
                        # Fallback: usar primeiro artefato
                        code_artifact = artifacts[0] if artifacts else {}

                    return {
                        "request_id": request_id,
                        "code_artifact_id": code_artifact.get("artifact_id"),
                        "language": code_artifact.get("language", "python"),
                        "framework": code_artifact.get("framework", "fastapi"),
                        "generation_method": code_artifact.get("generation_method", "TEMPLATE"),
                        "confidence_score": code_artifact.get("confidence_score", 0.8),
                        "code_preview": status_data.get("code_preview", ""),
                        "lines_of_code": code_artifact.get("lines_of_code", 0),
                        "artifacts": artifacts,
                        "status": "completed",
                    }

        except httpx.HTTPError as e:
            logger.warning(
                "code_generation_poll_http_error",
                request_id=request_id,
                error=str(e),
            )
            # Continuar polling em caso de erro transitório
            pass

        await asyncio.sleep(poll_interval)


@activity.defn
async def generate_code_simple(
    cognitive_plan: dict[str, Any],
) -> dict[str, Any]:
    """
    Versão simplificada do G6 para casos sem requisitos detalhados.

    Usa valores padrão para geração de código.

    Args:
        cognitive_plan: Plano cognitivo com parâmetros mínimos

    Returns:
        Dict com resultado da geração
    """
    plan_id = cognitive_plan.get("plan_id", "unknown")
    parameters = cognitive_plan.get("parameters", {}) or {}

    # Valores padrão
    language = parameters.get("language", "python")
    framework = parameters.get("framework", "fastapi")

    logger.info(
        "G6: Geração simplificada de código",
        plan_id=plan_id,
        language=language,
        framework=framework,
    )

    # Requisitos mínimos stub
    requirements_set = {
        "requirements_set_id": f"REQ-SET-{plan_id}",
        "plan_id": plan_id,
        "requirements": [
            {
                "id": f"REQ-{plan_id}-1",
                "title": "API Endpoint principal",
                "description": f"Endpoint principal do serviço {plan_id}",
            }
        ],
    }

    # Documentação stub
    documentation = {
        "documentation_id": f"DOC-{plan_id}",
        "readme": f"# Service {plan_id}\nGenerated by Neural Hive Mind",
    }

    # Chamar geração completa
    return await generate_code(requirements_set, documentation, cognitive_plan)
