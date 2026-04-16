"""Router para endpoints de requisitos."""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, status, Depends

from src.models.requirements import (
    Requirement,
    RequirementCreate,
    RequirementUpdate,
    RequirementList,
    RequirementPriority,
    RequirementType,
)
from src.services.requirements_engineer import RequirementsEngineer
from src.main import get_engineering_service

router = APIRouter(prefix="/requirements", tags=["requirements"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_requirement(
    request: RequirementCreate,
    engineer: RequirementsEngineer = Depends(get_engineering_service)
):
    """Gera requisitos a partir de uma descrição em linguagem natural."""
    try:
        # Gerar ID único
        import uuid
        req_id = f"REQ-{uuid.uuid4().hex[:6].upper()}"

        requirement = Requirement(
            id=req_id,
            title=request.title,
            description=request.description,
            requirement_type=request.requirement_type,
            priority=request.priority,
            rationale=request.rationale,
            tags=request.tags,
            cognitive_plan_id=request.cognitive_plan_id,
            architecture_plan_id=request.architecture_plan_id
        )

        return {
            "requirement": requirement,
            "message": "Requirement created successfully"
        }

    except Exception as e:
        logger.error("create_requirement_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/generate", status_code=status.HTTP_200_OK)
async def generate_requirements(
    plan_text: str,
    plan_id: str,
    engineer: RequirementsEngineer = Depends(get_engineering_service)
):
    """Gera requisitos completos a partir de um plano cognitivo."""
    try:
        requirements_set = await engineer.generate_from_cognitive_plan(
            plan_id=plan_id,
            plan_text=plan_text
        )

        return {
            "requirements_set_id": requirements_set.id,
            "cognitive_plan_id": requirements_set.cognitive_plan_id,
            "total": len(requirements_set.requirements),
            "functional_count": requirements_set.functional_count,
            "non_functional_count": requirements_set.non_functional_count,
            "requirements": requirements_set.requirements
        }

    except Exception as e:
        logger.error("generate_requirements_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/analyze-dependencies")
async def analyze_dependencies(
    requirements_data: List[dict],
    engineer: RequirementsEngineer = Depends(get_engineering_service)
):
    """Analisa dependências entre requisitos."""
    try:
        # Converter dict para objetos Requirement
        requirements = [
            Requirement(**req) for req in requirements_data
        ]

        analyzed = await engineer.analyze_dependencies(requirements)

        return {
            "requirements": analyzed,
            "total": len(analyzed)
        }

    except Exception as e:
        logger.error("analyze_dependencies_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("", response_model=RequirementList)
async def list_requirements(
    priority: Optional[RequirementPriority] = None,
    req_type: Optional[RequirementType] = None,
    limit: int = 50
):
    """Lista requisitos (placeholder - implementação com MongoDB futura)."""
    return RequirementList(
        total=0,
        items=[],
        filters={"priority": priority, "type": req_type}
    )


@router.get("/{requirement_id}")
async def get_requirement(requirement_id: str):
    """Obtém requisito por ID (placeholder)."""
    return {
        "message": "Get by ID not yet implemented",
        "requirement_id": requirement_id
    }
