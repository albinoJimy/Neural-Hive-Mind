"""Router para endpoints de design de UI/UX."""

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from src.main import get_engineering_service
from src.models.ui_ux_design import (
    ComponentType,
    Screen,
    UIDesign,
    UIComponent,
    UserFlow,
)
from src.services.ui_ux_designer import UIUXDesigner

router = APIRouter(prefix="/ui-ux-design", tags=["ui-ux-design"])
logger = structlog.get_logger(__name__)


@router.post("/generate", status_code=status.HTTP_200_OK)
async def generate_ui_ux_design(
    requirements_set_id: str = Query(..., description="ID do conjunto de requisitos"),
    designer: UIUXDesigner = Depends(get_engineering_service),
):
    """Gera design de UI/UX a partir de requisitos.

    Args:
        requirements_set_id: ID do conjunto de requisitos
        designer: Instância do UIUXDesigner

    Returns:
        UIDesign com cores, telas, componentes e fluxos
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

        ui_design = await designer.design_from_requirements(requirements_set)

        return {
            "ui_design": ui_design,
            "screens_count": len(ui_design.screens),
            "flows_count": len(ui_design.user_flows),
            "components_count": sum(len(s.components) for s in ui_design.screens),
            "message": "UI/UX design generated successfully",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("generate_ui_ux_design_error", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/screens", response_model=list[Screen])
async def list_screens(
    design_id: str | None = Query(None, description="Filtrar por design ID"),
):
    """Lista telas do design.

    Args:
        design_id: ID do design (opcional)

    Returns:
        Lista de telas
    """
    try:
        # TODO: Implementar recuperação do repositório
        # Por ora, retorna lista vazia
        return []
    except Exception as e:
        logger.error("list_screens_error", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/screens/{screen_id}")
async def get_screen(screen_id: str):
    """Obtém tela por ID.

    Args:
        screen_id: ID da tela

    Returns:
        Screen
    """
    try:
        # TODO: Implementar recuperação do repositório
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Screen {screen_id} not found",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_screen_error", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/flows", response_model=list[UserFlow])
async def list_user_flows(
    design_id: str | None = Query(None, description="Filtrar por design ID"),
):
    """Lista fluxos de utilizador.

    Args:
        design_id: ID do design (opcional)

    Returns:
        Lista de fluxos
    """
    try:
        # TODO: Implementar recuperação do repositório
        # Por ora, retorna lista vazia
        return []
    except Exception as e:
        logger.error("list_user_flows_error", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/components", response_model=list[UIComponent])
async def list_components(
    component_type: ComponentType | None = Query(None, description="Filtrar por tipo"),
):
    """Lista componentes de UI.

    Args:
        component_type: Tipo de componente (opcional)

    Returns:
        Lista de componentes
    """
    try:
        # TODO: Implementar recuperação do repositório
        # Por ora, retorna lista vazia
        return []
    except Exception as e:
        logger.error("list_components_error", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/export/{design_id}")
async def export_design_assets(
    design_id: str,
    format: str = Query("json", description="Formato de exportação (json, figma, svg)"),
):
    """Exporta design de UI/UX em diferentes formatos.

    Args:
        design_id: ID do design
        format: Formato de exportação

    Returns:
        Assets exportados
    """
    try:
        # TODO: Implementar exportação para diferentes formatos
        return {
            "design_id": design_id,
            "format": format,
            "assets": {},
            "message": "Export not yet implemented",
        }
    except Exception as e:
        logger.error("export_design_assets_error", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
