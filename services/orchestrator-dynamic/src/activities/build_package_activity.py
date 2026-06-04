"""
Activity Temporal para integração G7 - Build & Package com Code-Forge.

Integra com code-forge via API REST para build, testes e empacotamento.
"""

import asyncio
from typing import Any

import httpx
import structlog
from temporalio import activity

logger = structlog.get_logger(__name__)

# Cliente HTTP reutilizado de code_generation_activity
from .code_generation_activity import _http_client


@activity.defn
async def build_package(
    code_artifact_id: str,
    cognitive_plan: dict[str, Any],
) -> dict[str, Any]:
    """
    G7: Compila, testa e empacota o código gerado.

    Integra com code-forge via API REST /api/v1/pipelines.

    Args:
        code_artifact_id: ID do artefato de código gerado no G6
        cognitive_plan: Plano cognitivo com parâmetros de build

    Returns:
        Dict com:
            - pipeline_id: ID do pipeline de build
            - container_image: Digest da imagem Docker
            - image_tag: Tag da imagem (e.g., service-xyz:1.0.0)
            - test_results: Resultados dos testes
            - sbom: Software Bill of Materials
            - package_uri: URI do artefato empacotado
            - quality_score: Score de qualidade (0-1)
            - security_scan: Resultados do scan de segurança
            - status: Status final do build

    Raises:
        RuntimeError: Se o build falhar
        TimeoutError: Se o build demorar mais que 15 minutos
    """
    plan_id = cognitive_plan.get("plan_id", "unknown")
    service_name = f"service-{plan_id}"
    version = cognitive_plan.get("version", "1.0.0")

    logger.info(
        "G7: Build e empacotamento",
        plan_id=plan_id,
        code_artifact_id=code_artifact_id,
    )

    # Preparar payload para code-forge pipeline
    parameters = cognitive_plan.get("parameters", {}) or {}
    payload = {
        "artifact_id": code_artifact_id,
        "parameters": {
            "service_name": service_name,
            "version": version,
            "language": parameters.get("language", "python"),
            "framework": parameters.get("framework", "fastapi"),
            "enable_tests": True,
            "enable_security_scan": True,
            "generate_sbom": True,
            "push_to_registry": parameters.get("push_to_registry", False),
            "registry_url": parameters.get("registry_url", ""),
        },
        "plan_id": plan_id,
    }

    try:
        # Usar cliente HTTP
        client = _http_client or httpx.AsyncClient(timeout=900.0)

        # Chamar code-forge API para iniciar pipeline
        response = await client.post(
            "http://code-forge:8020/api/v1/pipelines",
            json=payload,
            headers={"Content-Type": "application/json"},
        )

        if response.status_code != 201:
            logger.error(
                "build_package_failed",
                status_code=response.status_code,
                response_text=response.text,
            )
            raise RuntimeError(f"Falha ao iniciar build: HTTP {response.status_code}")

        result = response.json()
        pipeline_id = result.get("pipeline_id")

        logger.info(
            "build_package_started",
            pipeline_id=pipeline_id,
            plan_id=plan_id,
        )

        # Poll para completude
        final_result = await _wait_for_build_completion(
            client, pipeline_id, plan_id, code_artifact_id
        )

        logger.info(
            "build_package_completed",
            pipeline_id=pipeline_id,
            plan_id=plan_id,
            status=final_result.get("status"),
            quality_score=final_result.get("quality_score"),
        )

        return final_result

    except httpx.TimeoutException:
        logger.error("build_package_timeout", plan_id=plan_id)
        raise TimeoutError("Build timeout após 15 minutos")
    except Exception as e:
        logger.exception("build_package_exception", plan_id=plan_id, error=str(e))
        raise


async def _wait_for_build_completion(
    client: httpx.AsyncClient,
    pipeline_id: str,
    plan_id: str,
    code_artifact_id: str,
    max_wait: int = 900,
    poll_interval: int = 10,
) -> dict[str, Any]:
    """
    Aguarda o pipeline de build completar.

    Args:
        client: HTTP client
        pipeline_id: ID do pipeline
        plan_id: Plan ID para logging
        code_artifact_id: ID do artefato de código
        max_wait: Tempo máximo de espera em segundos
        poll_interval: Intervalo entre polls em segundos

    Returns:
        Resultado final do build

    Raises:
        TimeoutError: Se o build não completar no tempo máximo
        RuntimeError: Se o build falhar
    """
    started = asyncio.get_event_loop().time()

    while True:
        elapsed = asyncio.get_event_loop().time() - started

        if elapsed > max_wait:
            raise TimeoutError(f"Build timeout após {max_wait}s")

        try:
            response = await client.get(f"http://code-forge:8020/api/v1/pipelines/{pipeline_id}")

            if response.status_code == 200:
                status_data = response.json()
                status = status_data.get("status")
                stage = status_data.get("stage", "")

                logger.debug(
                    "build_package_poll",
                    pipeline_id=pipeline_id,
                    status=status,
                    stage=stage,
                    elapsed_ms=int(elapsed * 1000),
                )

                if status in ("completed", "failed", "requires_review"):
                    if status == "failed":
                        error = status_data.get("error", "Build falhou")
                        raise RuntimeError(f"Build falhou: {error}")

                    # Extrair resultados
                    artifacts = status_data.get("artifacts", [])

                    # Buscar artefatos específicos
                    container_image = None
                    test_results = None
                    sbom = None

                    for artifact in artifacts:
                        artifact_type = artifact.get("artifact_type", "")
                        if artifact_type == "container_image":
                            container_image = artifact
                        elif artifact_type == "test_results":
                            test_results = artifact
                        elif artifact_type == "sbom":
                            sbom = artifact

                    return {
                        "pipeline_id": pipeline_id,
                        "code_artifact_id": code_artifact_id,
                        "container_image": container_image.get("content_uri")
                        if container_image
                        else status_data.get("container_image", ""),
                        "image_tag": container_image.get("metadata", {}).get("tag")
                        if container_image
                        else f"service-{plan_id}:1.0.0",
                        "test_results": test_results.get("content", {}) if test_results else {},
                        "sbom": sbom.get("content_uri") if sbom else "",
                        "quality_score": status_data.get("quality_score", 0.8),
                        "security_scan": status_data.get("security_scan", {}),
                        "stage": stage,
                        "duration_ms": status_data.get("duration_ms", 0),
                        "artifacts": artifacts,
                        "status": "completed",
                    }

        except httpx.HTTPError as e:
            logger.warning(
                "build_package_poll_http_error",
                pipeline_id=pipeline_id,
                error=str(e),
            )
            # Continuar polling em caso de erro transitório
            pass

        await asyncio.sleep(poll_interval)


@activity.defn
async def validate_build_quality(
    build_result: dict[str, Any],
    min_quality_score: float = 0.5,
    min_test_pass_rate: float = 0.8,
) -> dict[str, Any]:
    """
    Valida qualidade do build e decide se prosseguir para deploy.

    Args:
        build_result: Resultado do build (saída do G7)
        min_quality_score: Score mínimo de qualidade
        min_test_pass_rate: Taxa mínima de testes passando

    Returns:
        Dict com:
            - approved: Se pode prosseguir para deploy
            - reasons: Lista de razões para aprovação/rejeição
            - warnings: Lista de warnings
    """
    reasons = []
    warnings = []
    approved = True

    quality_score = build_result.get("quality_score", 0.0)
    test_results = build_result.get("test_results", {})
    security_scan = build_result.get("security_scan", {})

    # Verificar quality score
    if quality_score < min_quality_score:
        approved = False
        reasons.append(f"Quality score {quality_score:.2f} abaixo do mínimo {min_quality_score}")

    # Verificar taxa de testes
    passed = test_results.get("passed", 0)
    total = test_results.get("total", passed)
    pass_rate = passed / total if total > 0 else 1.0

    if pass_rate < min_test_pass_rate:
        approved = False
        reasons.append(f"Taxa de testes {pass_rate:.1%} abaixo do mínimo {min_test_pass_rate:.1%}")

    # Verificar vulnerabilidades críticas
    vulnerabilities = security_scan.get("vulnerabilities", {})
    critical_count = vulnerabilities.get("critical", 0)
    high_count = vulnerabilities.get("high", 0)

    if critical_count > 0:
        approved = False
        reasons.append(f"{critical_count} vulnerabilidades críticas encontradas")
    elif high_count > 0:
        warnings.append(f"{high_count} vulnerabilidades altas encontradas")

    # Adicionar razão positiva se aprovado
    if approved:
        reasons.append(
            f"Build aprovado com quality score {quality_score:.2f} "
            f"e {pass_rate:.1%} dos testes passando"
        )

    logger.info(
        "build_quality_validated",
        approved=approved,
        quality_score=quality_score,
        pass_rate=pass_rate,
        reasons_count=len(reasons),
        warnings_count=len(warnings),
    )

    return {
        "approved": approved,
        "reasons": reasons,
        "warnings": warnings,
        "quality_score": quality_score,
        "pass_rate": pass_rate,
    }
