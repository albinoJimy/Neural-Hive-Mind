"""
Activity Temporal para integração G8 - Deploy com Deploy-Service.

Integra com deploy-service via API REST para deploy em Kubernetes.
"""

import asyncio
from typing import Any

import httpx
import structlog
from temporalio import activity

logger = structlog.get_logger(__name__)

# Cliente HTTP reutilizado de code_generation_activity.
# Importamos o módulo (não o símbolo) para ler _http_client dinamicamente
# após a injeção feita pelo worker.
from . import code_generation_activity


def _get_http_client() -> httpx.AsyncClient | None:
    """Lê o cliente HTTP injetado dinamicamente (pode ser None)."""
    client = code_generation_activity._http_client
    if client is None:
        logger.warning(
            "http_client_not_injected_using_ephemeral",
            degraded=True,
            reason="set_code_generation_dependencies_not_called",
        )
    return client


@activity.defn
async def deploy_software(
    container_image: str,
    build_result: dict[str, Any],
    cognitive_plan: dict[str, Any],
) -> dict[str, Any]:
    """
    G8: Faz deploy do software containerizado em Kubernetes.

    Integra com deploy-service via API REST /api/v1/deployments.

    Args:
        container_image: Digest da imagem Docker (saída do G7)
        build_result: Resultado completo do build (saída do G7)
        cognitive_plan: Plano cognitivo com parâmetros de deploy

    Returns:
        Dict com:
            - deployment_id: ID único do deployment
            - deployment_name: Nome do deployment no Kubernetes
            - namespace: Namespace Kubernetes
            - replica_count: Número de réplicas
            - service_url: URL externa do serviço
            - status: Status do deployment (pending, deployed, failed)
            - health_checks: Resultados dos health checks
            - rollback_info: Informações para rollback

    Raises:
        RuntimeError: Se o deploy falhar
        TimeoutError: Se o deploy demorar mais que 20 minutos
    """
    plan_id = cognitive_plan.get("plan_id", "unknown")
    service_name = f"service-{plan_id}"
    version = cognitive_plan.get("version", "1.0.0")

    logger.info(
        "G8: Iniciando deploy",
        plan_id=plan_id,
        container_image=container_image,
    )

    # Extrair parâmetros do cognitive_plan
    parameters = cognitive_plan.get("parameters", {}) or {}

    # Preparar payload para deploy-service
    payload = {
        "service_name": service_name,
        "version": version,
        "container_image": container_image,
        "namespace": parameters.get("namespace", "default"),
        "replicas": parameters.get("replicas", 2),
        "resources": {
            "cpu": parameters.get("cpu", "500m"),
            "memory": parameters.get("memory", "512Mi"),
            "limits": {
                "cpu": parameters.get("cpu_limit", "1000m"),
                "memory": parameters.get("memory_limit", "1Gi"),
            },
        },
        "environment": parameters.get("environment", "production"),
        "ingress": {
            "enabled": parameters.get("ingress_enabled", True),
            "host": parameters.get("ingress_host", f"{service_name}.nhm.local"),
            "path": parameters.get("ingress_path", "/"),
        },
        "health_checks": {
            "liveness_path": parameters.get("liveness_path", "/health/live"),
            "readiness_path": parameters.get("readiness_path", "/health/ready"),
            "initial_delay": parameters.get("health_check_delay", 10),
            "period": parameters.get("health_check_period", 10),
        },
        "config_maps": parameters.get("config_maps", {}),
        "secrets_ref": parameters.get("secrets_ref", ""),
        "plan_id": plan_id,
    }

    try:
        # Usar cliente HTTP
        client = _get_http_client() or httpx.AsyncClient(timeout=1200.0)

        # Chamar deploy-service API para iniciar deploy
        response = await client.post(
            "http://deploy-service:8010/api/v1/deployments",
            json=payload,
            headers={"Content-Type": "application/json"},
        )

        if response.status_code != 202:
            logger.error(
                "deploy_software_failed",
                status_code=response.status_code,
                response_text=response.text,
            )
            raise RuntimeError(f"Falha ao iniciar deploy: HTTP {response.status_code}")

        result = response.json()
        deployment_id = result.get("deployment_id")

        logger.info(
            "deploy_software_started",
            deployment_id=deployment_id,
            plan_id=plan_id,
        )

        # Poll para completude
        final_result = await _wait_for_deploy_completion(
            client, deployment_id, plan_id, service_name
        )

        logger.info(
            "deploy_software_completed",
            deployment_id=deployment_id,
            plan_id=plan_id,
            status=final_result.get("status"),
            service_url=final_result.get("service_url"),
        )

        return final_result

    except httpx.TimeoutException:
        logger.error("deploy_software_timeout", plan_id=plan_id)
        raise TimeoutError("Deploy timeout após 20 minutos")
    except Exception as e:
        logger.exception("deploy_software_exception", plan_id=plan_id, error=str(e))
        raise


async def _wait_for_deploy_completion(
    client: httpx.AsyncClient,
    deployment_id: str,
    plan_id: str,
    service_name: str,
    max_wait: int = 1200,
    poll_interval: int = 15,
) -> dict[str, Any]:
    """
    Aguarda o deployment completar.

    Args:
        client: HTTP client
        deployment_id: ID do deployment
        plan_id: Plan ID para logging
        service_name: Nome do serviço
        max_wait: Tempo máximo de espera em segundos
        poll_interval: Intervalo entre polls em segundos

    Returns:
        Resultado final do deployment

    Raises:
        TimeoutError: Se o deploy não completar no tempo máximo
        RuntimeError: Se o deploy falhar
    """
    started = asyncio.get_event_loop().time()
    last_status = None

    while True:
        elapsed = asyncio.get_event_loop().time() - started

        if elapsed > max_wait:
            raise TimeoutError(f"Deploy timeout após {max_wait}s")

        try:
            response = await client.get(
                f"http://deploy-service:8010/api/v1/deployments/{deployment_id}"
            )

            if response.status_code == 200:
                status_data = response.json()
                last_status = status_data.get("status")

                logger.debug(
                    "deploy_software_poll",
                    deployment_id=deployment_id,
                    status=last_status,
                    elapsed_ms=int(elapsed * 1000),
                )

                if last_status in ("deployed", "failed", "rollback_complete"):
                    if last_status == "failed":
                        error = status_data.get("error", "Deploy falhou")
                        raise RuntimeError(f"Deploy falhou: {error}")

                    # Extrair resultados
                    kubernetes_info = status_data.get("kubernetes", {})
                    service_info = status_data.get("service", {})
                    health_checks = status_data.get("health_checks", {})

                    return {
                        "deployment_id": deployment_id,
                        "deployment_name": kubernetes_info.get("deployment_name", service_name),
                        "namespace": kubernetes_info.get("namespace", "default"),
                        "replica_count": kubernetes_info.get("replicas", 0),
                        "available_replicas": kubernetes_info.get("available_replicas", 0),
                        "service_url": service_info.get("url", ""),
                        "service_port": service_info.get("port", 80),
                        "ingress_url": service_info.get("ingress_url", ""),
                        "status": last_status,
                        "health_checks": {
                            "liveness": health_checks.get("liveness", "unknown"),
                            "readiness": health_checks.get("readiness", "unknown"),
                            "custom": health_checks.get("custom", {}),
                        },
                        "rollback_info": {
                            "enabled": status_data.get("rollback_enabled", False),
                            "previous_version": status_data.get("previous_version"),
                            "rollback_command": f"kubectl rollout undo deployment/{service_name}",
                        },
                        "duration_ms": status_data.get("duration_ms", 0),
                    }

        except httpx.HTTPError as e:
            logger.warning(
                "deploy_software_poll_http_error",
                deployment_id=deployment_id,
                error=str(e),
            )
            # Continuar polling em caso de erro transitório
            pass

        await asyncio.sleep(poll_interval)


@activity.defn
async def verify_deployment(
    deployment_result: dict[str, Any],
    min_replicas: int = 1,
    require_healthy: bool = True,
) -> dict[str, Any]:
    """
    Verifica se o deployment foi bem-sucedido.

    Args:
        deployment_result: Resultado do deploy (saída do G8)
        min_replicas: Número mínimo de réplicas disponíveis
        require_healthy: Se requer health checks passando

    Returns:
        Dict com:
            - verified: Se o deployment está verificado
            - reasons: Lista de razões para verificação/falha
            - health_status: Status dos health checks
    """
    reasons = []
    verified = True

    status = deployment_result.get("status", "unknown")
    available_replicas = deployment_result.get("available_replicas", 0)
    health_checks = deployment_result.get("health_checks", {})

    # Verificar status
    if status != "deployed":
        verified = False
        reasons.append(f"Status é '{status}', não 'deployed'")

    # Verificar réplicas
    if available_replicas < min_replicas:
        verified = False
        reasons.append(f"Apenas {available_replicas} réplicas disponíveis (mínimo: {min_replicas})")

    # Verificar health checks
    if require_healthy:
        liveness = health_checks.get("liveness", "unknown")
        readiness = health_checks.get("readiness", "unknown")

        if liveness != "healthy":
            verified = False
            reasons.append(f"Liveness check: {liveness}")

        if readiness != "healthy":
            verified = False
            reasons.append(f"Readiness check: {readiness}")

    # Adicionar razão positiva se verificado
    if verified:
        reasons.append(
            f"Deployment verificado com {available_replicas} réplicas disponíveis "
            f"e health checks passando"
        )

    logger.info(
        "deployment_verified",
        verified=verified,
        status=status,
        available_replicas=available_replicas,
        reasons_count=len(reasons),
    )

    return {
        "verified": verified,
        "reasons": reasons,
        "health_status": health_checks,
        "replica_status": {
            "available": available_replicas,
            "total": deployment_result.get("replica_count", 0),
        },
    }


@activity.defn
async def rollback_deployment(
    deployment_result: dict[str, Any],
    reason: str = "manual",
) -> dict[str, Any]:
    """
    Executa rollback de um deployment.

    Args:
        deployment_result: Resultado do deploy anterior
        reason: Razão do rollback

    Returns:
        Dict com resultado do rollback
    """
    deployment_id = deployment_result.get("deployment_id")
    deployment_name = deployment_result.get("deployment_name")

    logger.warning(
        "rollback_initiated",
        deployment_id=deployment_id,
        deployment_name=deployment_name,
        reason=reason,
    )

    rollback_info = deployment_result.get("rollback_info", {})

    if not rollback_info.get("enabled"):
        raise RuntimeError("Rollback não está habilitado para este deployment")

    try:
        client = _get_http_client() or httpx.AsyncClient(timeout=300.0)

        response = await client.post(
            f"http://deploy-service:8010/api/v1/deployments/{deployment_id}/rollback",
            json={"reason": reason},
        )

        if response.status_code != 200:
            raise RuntimeError(f"Falha ao executar rollback: HTTP {response.status_code}")

        result = response.json()

        logger.info(
            "rollback_completed",
            deployment_id=deployment_id,
            previous_version=result.get("previous_version"),
        )

        return {
            "deployment_id": deployment_id,
            "rollback_status": "completed",
            "previous_version": result.get("previous_version"),
            "reason": reason,
        }

    except Exception as e:
        logger.exception("rollback_failed", deployment_id=deployment_id, error=str(e))
        raise
