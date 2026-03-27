"""Router para endpoints de arquitetura."""

from fastapi import APIRouter, HTTPException, status
from datetime import datetime

from src.api.schemas import (
    ArchitectureRequest,
    ArchitectureResponse,
    ComponentResponse,
)
from src.planners.design_planner import DesignPlanner
from src.repositories.architecture_repository import ArchitectureRepository
from src.models.architecture import ArchitectureType
import structlog

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
            created_at=plan.created_at or datetime.utcnow(),
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
        created_at=plan.created_at or datetime.utcnow(),
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
            created_at=p.created_at or datetime.utcnow(),
        )
        for p in plans
    ]
