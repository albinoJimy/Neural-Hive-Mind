"""
Deployments API Router.
"""

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse

from src.models.deployment import (
    DeploymentRequest,
    DeploymentResponse,
    RollbackRequest,
    RollbackResponse,
)
from src.services.kubernetes_deployer import KubernetesDeployer

router = APIRouter(prefix="/deployments", tags=["deployments"])
deployer = KubernetesDeployer()

# Storage em memória para deployments (produção deve usar MongoDB)
_deployments: dict[str, DeploymentResponse] = {}


@router.post("", response_model=DeploymentResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_deployment(request: DeploymentRequest) -> DeploymentResponse:
    """
    Cria um novo deployment.

    Args:
        request: Deployment request

    Returns:
        Deployment response com ID criado
    """
    try:
        # Executar deploy
        response = await deployer.deploy(request)

        # Armazenar
        _deployments[response.deployment_id] = response

        return response

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Deployment failed: {str(e)}",
        )


@router.get("/{deployment_id}", response_model=DeploymentResponse)
async def get_deployment(deployment_id: str) -> DeploymentResponse:
    """
    Obtém status de um deployment.

    Args:
        deployment_id: ID do deployment

    Returns:
        Deployment response atualizado
    """
    if deployment_id not in _deployments:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Deployment {deployment_id} not found",
        )

    return _deployments[deployment_id]


@router.post("/{deployment_id}/rollback", response_model=RollbackResponse)
async def rollback_deployment(deployment_id: str, request: RollbackRequest) -> RollbackResponse:
    """
    Executa rollback de um deployment.

    Args:
        deployment_id: ID do deployment
        request: Rollback request

    Returns:
        Rollback response
    """
    if deployment_id not in _deployments:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Deployment {deployment_id} not found",
        )

    deployment = _deployments[deployment_id]

    if not deployment.rollback_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Rollback is not enabled for this deployment",
        )

    try:
        k8s_info = deployment.kubernetes
        if not k8s_info:
            raise ValueError("Kubernetes info not available")

        result = await deployer.rollback(
            k8s_info.deployment_name,
            k8s_info.namespace,
        )

        return RollbackResponse(
            deployment_id=deployment_id,
            rollback_status=result["rollback_status"],
            previous_version=deployment.previous_version,
            reason=request.reason,
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Rollback failed: {str(e)}",
        )


@router.get("", response_model=list[DeploymentResponse])
async def list_deployments(
    plan_id: str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list[DeploymentResponse]:
    """
    Lista deployments.

    Args:
        plan_id: Filtrar por plan_id
        status: Filtrar por status
        limit: Limite de resultados

    Returns:
        Lista de deployments
    """
    deployments = list(_deployments.values())

    if plan_id:
        deployments = [d for d in deployments if d.plan_id == plan_id]

    if status:
        deployments = [d for d in deployments if d.status == status]

    return deployments[:limit]


@router.delete("/{deployment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_deployment(deployment_id: str):
    """
    Remove um deployment do Kubernetes.

    Args:
        deployment_id: ID do deployment
    """
    if deployment_id not in _deployments:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Deployment {deployment_id} not found",
        )

    # TODO: Implementar delete no Kubernetes
    # kubectl delete deployment/{_deployments[deployment_id].kubernetes.deployment_name}

    del _deployments[deployment_id]

    return JSONResponse(status_code=status.HTTP_204_NO_CONTENT, content={})
