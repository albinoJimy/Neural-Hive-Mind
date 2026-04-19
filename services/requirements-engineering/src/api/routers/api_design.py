"""Router para endpoints de design de API."""

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from src.main import get_engineering_service
from src.models.api_design import APIEndpoint, HTTPMethod
from src.services.api_designer import APIDesigner

router = APIRouter(prefix="/api-design", tags=["api-design"])
logger = structlog.get_logger(__name__)


@router.post("/generate", status_code=status.HTTP_200_OK)
async def generate_api_design(
    requirements_set_id: str = Query(..., description="ID do conjunto de requisitos"),
    designer: APIDesigner = Depends(get_engineering_service),
):
    """Gera design de API a partir de requisitos.

    Args:
        requirements_set_id: ID do conjunto de requisitos
        designer: Instância do APIDesigner

    Returns:
        APIDesign com endpoints, segurança e documentação
    """
    try:
        from src.repositories.requirements_repository import RequirementsRepository

        repo = RequirementsRepository()
        requirements_set = await repo.get_set_by_id(requirements_set_id)

        if not requirements_set:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"RequirementsSet {requirements_set_id} not found",
            )

        api_design = await designer.design_from_requirements(requirements_set)

        return {
            "api_design": api_design,
            "endpoints_count": len(api_design.endpoints),
            "security_schemes_count": len(api_design.security_schemes),
            "message": "API design generated successfully",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("generate_api_design_error", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/openapi/{design_id}")
async def export_openapi(
    design_id: str,
    designer: APIDesigner = Depends(get_engineering_service),
):
    """Exporta design de API como especificação OpenAPI.

    Args:
        design_id: ID do design de API
        designer: Instância do APIDesigner

    Returns:
        Especificação OpenAPI em JSON
    """
    try:
        # TODO: Implementar recuperação do design do repositório
        # Por ora, retorna placeholder
        return {
            "openapi": "3.0.0",
            "info": {"title": "API", "version": "1.0.0"},
            "paths": {},
        }
    except Exception as e:
        logger.error("export_openapi_error", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/endpoints", response_model=list[APIEndpoint])
async def list_endpoints(
    design_id: str | None = Query(None, description="Filtrar por design ID"),
    method: HTTPMethod | None = Query(None, description="Filtrar por método HTTP"),
    tag: str | None = Query(None, description="Filtrar por tag"),
):
    """Lista endpoints de API com filtros.

    Args:
        design_id: ID do design (opcional)
        method: Método HTTP (opcional)
        tag: Tag (opcional)

    Returns:
        Lista de endpoints
    """
    try:
        # TODO: Implementar recuperação do repositório
        # Por ora, retorna lista vazia
        return []
    except Exception as e:
        logger.error("list_endpoints_error", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/endpoints/{endpoint_id}")
async def get_endpoint(endpoint_id: str):
    """Obtém endpoint por ID.

    Args:
        endpoint_id: ID do endpoint

    Returns:
        APIEndpoint
    """
    try:
        # TODO: Implementar recuperação do repositório
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Endpoint {endpoint_id} not found",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_endpoint_error", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
