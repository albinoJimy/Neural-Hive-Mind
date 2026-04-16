"""Router para endpoints de requisitos."""

import structlog
from typing import List, Optional
from fastapi import APIRouter, HTTPException, status, Depends, Query

from src.models.requirements import (
    Requirement,
    RequirementCreate,
    RequirementUpdate,
    RequirementList,
    RequirementPriority,
    RequirementType,
    RequirementStatus,
)
from src.services.requirements_engineer import RequirementsEngineer
from src.repositories.requirements_repository import RequirementsRepository
from src.main import get_engineering_service

router = APIRouter(prefix="/requirements", tags=["requirements"])
logger = structlog.get_logger(__name__)


def get_repository() -> RequirementsRepository:
    """Retorna instância do repositório."""
    return RequirementsRepository()


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_requirement(
    request: RequirementCreate, repository: RequirementsRepository = Depends(get_repository)
):
    """Cria um novo requisito."""
    try:
        requirement = await repository.create(request)
        return {"requirement": requirement, "message": "Requirement created successfully"}
    except Exception as e:
        logger.error("create_requirement_error", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/generate", status_code=status.HTTP_200_OK)
async def generate_requirements(
    plan_text: str = Query(..., description="Texto do plano cognitivo"),
    plan_id: str = Query(..., description="ID do plano cognitivo"),
    engineer: RequirementsEngineer = Depends(get_engineering_service),
    repository: RequirementsRepository = Depends(get_repository),
):
    """Gera requisitos completos a partir de um plano cognitivo."""
    try:
        requirements_set = await engineer.generate_from_cognitive_plan(
            plan_id=plan_id, plan_text=plan_text
        )

        # Salvar conjunto de requisitos
        await repository.save_set(requirements_set)

        # Salvar requisitos individuais
        for req in requirements_set.requirements:
            try:
                await repository.create(
                    RequirementCreate(
                        title=req.title,
                        description=req.description,
                        requirement_type=req.requirement_type,
                        priority=req.priority,
                        rationale=req.rationale,
                        tags=req.tags,
                        cognitive_plan_id=plan_id,
                    )
                )
            except Exception as e:
                logger.warning("failed_to_save_requirement", id=req.id, error=str(e))

        return {
            "requirements_set_id": requirements_set.id,
            "cognitive_plan_id": requirements_set.cognitive_plan_id,
            "total": len(requirements_set.requirements),
            "functional_count": requirements_set.functional_count,
            "non_functional_count": requirements_set.non_functional_count,
            "requirements": requirements_set.requirements,
        }
    except Exception as e:
        logger.error("generate_requirements_error", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/analyze-dependencies")
async def analyze_dependencies(
    requirements_data: List[dict], engineer: RequirementsEngineer = Depends(get_engineering_service)
):
    """Analisa dependências entre requisitos."""
    try:
        # Converter dict para objetos Requirement
        requirements = [Requirement(**req) for req in requirements_data]

        analyzed = await engineer.analyze_dependencies(requirements)

        return {"requirements": analyzed, "total": len(analyzed)}
    except Exception as e:
        logger.error("analyze_dependencies_error", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("", response_model=RequirementList)
async def list_requirements(
    priority: Optional[RequirementPriority] = None,
    req_type: Optional[RequirementType] = None,
    status_filter: Optional[RequirementStatus] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
    skip: int = Query(0, ge=0),
    repository: RequirementsRepository = Depends(get_repository),
):
    """Lista requisitos com filtros."""
    try:
        requirements, total = await repository.list(
            priority=priority.value if priority else None,
            req_type=req_type.value if req_type else None,
            status=status_filter.value if status_filter else None,
            limit=limit,
            skip=skip,
        )

        return RequirementList(
            total=total,
            items=requirements,
            filters={"priority": priority, "type": req_type, "status": status_filter},
        )
    except Exception as e:
        logger.error("list_requirements_error", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/{requirement_id}")
async def get_requirement(
    requirement_id: str, repository: RequirementsRepository = Depends(get_repository)
):
    """Obtém requisito por ID."""
    try:
        requirement = await repository.get_by_id(requirement_id)

        if not requirement:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Requirement {requirement_id} not found",
            )

        return requirement
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_requirement_error", id=requirement_id, error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.put("/{requirement_id}")
async def update_requirement(
    requirement_id: str,
    update_data: RequirementUpdate,
    repository: RequirementsRepository = Depends(get_repository),
):
    """Atualiza um requisito."""
    try:
        requirement = await repository.update(requirement_id, update_data)

        if not requirement:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Requirement {requirement_id} not found",
            )

        return requirement
    except HTTPException:
        raise
    except Exception as e:
        logger.error("update_requirement_error", id=requirement_id, error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete("/{requirement_id}")
async def delete_requirement(
    requirement_id: str, repository: RequirementsRepository = Depends(get_repository)
):
    """Deleta um requisito."""
    try:
        deleted = await repository.delete(requirement_id)

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Requirement {requirement_id} not found",
            )

        return {"message": f"Requirement {requirement_id} deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("delete_requirement_error", id=requirement_id, error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
