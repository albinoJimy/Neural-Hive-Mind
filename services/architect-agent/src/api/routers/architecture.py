"""Router para endpoints de arquitetura."""

from datetime import datetime, timezone
from typing import Optional, List

import structlog
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from src.api.schemas import (
    ArchitectureRequest,
    ArchitectureResponse,
    ComponentResponse,
)
from src.models.architecture import ArchitectureType
from src.planners.design_planner import DesignPlanner
from src.repositories.architecture_repository import ArchitectureRepository


# Novos schemas para os endpoints extendidos


class BoundedContextsResponse(BaseModel):
    """Resposta com bounded contexts."""

    architecture_id: str
    bounded_contexts: List[dict]
    total_contexts: int


class ContextIdentificationRequest(BaseModel):
    """Request para identificação de bounded contexts."""

    requirements: str
    domain_hints: Optional[List[str]] = None


class DiagramGenerationRequest(BaseModel):
    """Request para geração de diagrama."""

    description: str
    diagram_type: str  # "c4_context", "c4_container", etc.


class TechStackRecommendationRequest(BaseModel):
    """Request para recomendação de tech stack."""

    requirements: str
    constraints: Optional[List[dict]] = None

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/architecture", tags=["architecture"])

# Dependências (singleton instances)
_planner_instance = None
_repository_instance = None


def get_planner() -> DesignPlanner:
    """Retorna instância singleton do DesignPlanner."""
    global _planner_instance
    if _planner_instance is None:
        _planner_instance = DesignPlanner()
    return _planner_instance


def get_repository() -> ArchitectureRepository:
    """Retorna instância singleton do ArchitectureRepository."""
    global _repository_instance
    if _repository_instance is None:
        _repository_instance = ArchitectureRepository()
    return _repository_instance


@router.post("", response_model=ArchitectureResponse, status_code=status.HTTP_201_CREATED)
async def create_architecture(request: ArchitectureRequest) -> ArchitectureResponse:
    """Cria novo plano de arquitetura."""
    try:
        planner = get_planner()
        repository = get_repository()

        requirements = {
            "intent": request.intent,
            "context": request.context,
        }
        if request.cognitive_plan_id:
            requirements["cognitive_plan_id"] = request.cognitive_plan_id

        # Gerar plano
        plan = await planner.plan(requirements)

        # Persistir
        await repository.create(plan)

        logger.info(
            "architecture_created",
            plan_id=plan.plan_id,
            architecture_type=plan.architecture_type.value,
        )

        return ArchitectureResponse(
            plan_id=plan.plan_id,
            cognitive_plan_id=plan.cognitive_plan_id,
            architecture_type=plan.architecture_type.value,
            components=[
                ComponentResponse(
                    name=c.name,
                    stack=c.stack,
                    replicas=c.replicas,
                    ha=c.ha,
                )
                for c in plan.components
            ],
            patterns=[p.value for p in plan.patterns],
            rationale=plan.rationale,
            created_at=plan.created_at or datetime.now(timezone.utc),
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("architecture_creation_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal error")


@router.get("/{plan_id}", response_model=ArchitectureResponse)
async def get_architecture(plan_id: str) -> ArchitectureResponse:
    """Obtém plano de arquitetura por ID."""
    repository = get_repository()
    plan = await repository.get_by_plan_id(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Architecture plan not found")

    return ArchitectureResponse(
        plan_id=plan.plan_id,
        cognitive_plan_id=plan.cognitive_plan_id,
        architecture_type=plan.architecture_type.value,
        components=[
            ComponentResponse(
                name=c.name,
                stack=c.stack,
                replicas=c.replicas,
                ha=c.ha,
            )
            for c in plan.components
        ],
        patterns=[p.value for p in plan.patterns],
        rationale=plan.rationale,
        created_at=plan.created_at or datetime.now(timezone.utc),
    )


@router.get("", response_model=list[ArchitectureResponse])
async def list_architectures(
    limit: int = 50,
    architecture_type: str | None = None,
) -> list[ArchitectureResponse]:
    """Lista planos de arquitetura."""
    repository = get_repository()

    if architecture_type:
        plans = await repository.list_by_type(ArchitectureType(architecture_type), limit)
    else:
        plans = await repository.list_all(limit=limit)

    return [
        ArchitectureResponse(
            plan_id=p.plan_id,
            cognitive_plan_id=p.cognitive_plan_id,
            architecture_type=p.architecture_type.value,
            components=[
                ComponentResponse(
                    name=c.name,
                    stack=c.stack,
                    replicas=c.replicas,
                    ha=c.ha,
                )
                for c in p.components
            ],
            patterns=[p.value for p in p.patterns],
            rationale=p.rationale,
            created_at=p.created_at or datetime.now(timezone.utc),
        )
        for p in plans
    ]


# NOVOS ENDPOINTS para funcionalidades extendidas


@router.post("/bounded-contexts/identify")
async def identify_bounded_contexts(request: ContextIdentificationRequest):
    """Identifica bounded contexts a partir de requisitos.

    Endpoint independente que identifica bounded contexts sem criar arquitetura.
    """
    try:
        planner = get_planner()

        if not planner._bounded_contexts_identifier:
            raise HTTPException(
                status_code=503,
                detail="Bounded contexts feature not available (check LLM configuration)"
            )

        result = await planner._bounded_contexts_identifier.identify(
            requirements=request.requirements,
            domain_hints=request.domain_hints
        )

        return {
            "total_contexts": result.total_contexts,
            "contexts": [
                {
                    "name": ctx.name,
                    "description": ctx.description,
                    "responsibilities": ctx.responsibilities,
                    "domain_models": ctx.domain_models,
                    "ubiquitous_language": [
                        {"term": t.term, "definition": t.definition}
                        for t in ctx.ubiquitous_language
                    ],
                    "relationships": [
                        {"type": r.relationship_type, "target": r.to_context}
                        for r in ctx.relationships
                    ]
                }
                for ctx in result.contexts
            ],
            "confidence_score": result.confidence_score
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("identify_contexts_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tech-stack/recommend")
async def recommend_tech_stack(request: TechStackRecommendationRequest):
    """Recomenda stack tecnológico baseado em requisitos.

    Endpoint independente que recomenda tecnologias sem criar arquitetura.
    """
    try:
        planner = get_planner()

        if not planner._tech_stack_recommender:
            raise HTTPException(
                status_code=503,
                detail="Tech stack recommendation feature not available (check LLM configuration)"
            )

        result = await planner._tech_stack_recommender.recommend(
            requirements=request.requirements,
            constraints=request.constraints
        )

        return {
            "choices": [
                {
                    "category": choice.category,
                    "name": choice.name,
                    "version": choice.version,
                    "rationale": choice.rationale
                }
                for choice in result.choices
            ],
            "constraints_satisfied": result.constraints_satisfied,
            "constraints_violated": result.constraints_violated,
            "confidence_score": result.confidence_score,
            "estimated_complexity": result.estimated_complexity,
            "estimated_cost": result.estimated_cost
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("recommend_stack_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/diagrams/generate")
async def generate_diagram(request: DiagramGenerationRequest):
    """Gera diagrama C4 a partir de descrição.

    Endpoint independente para geração de diagramas.
    """
    try:
        planner = get_planner()

        if not planner._diagram_generator:
            raise HTTPException(
                status_code=503,
                detail="Diagram generation feature not available"
            )

        # Gerar diagrama baseado no tipo
        if request.diagram_type == "c4_context":
            diagram = await planner._diagram_generator.generate_context_diagram(
                project_name="Generated",
                system_description=request.description,
                actors=["User"],
                external_systems=[],
                render=False
            )
        elif request.diagram_type == "c4_container":
            # Para container, precisamos de bounded contexts
            # Por simplicidade, retornar um placeholder
            diagram = {
                "diagram_type": request.diagram_type,
                "mermaid_code": "C4Container\n    title Generated Container\n",
                "note": "Container diagram requires bounded contexts"
            }
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported diagram type: {request.diagram_type}"
            )

        if isinstance(diagram, dict):
            return diagram
        else:
            return {
                "diagram_id": diagram.diagram_id,
                "type": diagram.type.value,
                "title": diagram.title,
                "mermaid_code": diagram.mermaid_code,
                "svg_url": diagram.svg_url
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("generate_diagram_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
