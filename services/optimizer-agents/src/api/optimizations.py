from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from src.clients.mongodb_client import MongoDBClient
from src.clients.redis_client import RedisClient
from src.config.settings import get_settings
from src.models.optimization_event import OptimizationEvent, OptimizationType
from src.services.optimization_engine import OptimizationEngine
from src.services.weight_recalibrator import WeightRecalibrator
from src.services.slo_adjuster import SLOAdjuster

router = APIRouter(prefix="/api/v1/optimizations", tags=["optimizations"])

settings = get_settings()


# Request/Response models
class TriggerOptimizationRequest(BaseModel):
    """Request para trigger manual de otimização."""

    target_component: str
    optimization_type: OptimizationType
    justification: str
    proposed_adjustments: List[dict]


class TriggerOptimizationResponse(BaseModel):
    """Response de trigger de otimização."""

    optimization_id: str
    status: str
    message: str


class OptimizationListResponse(BaseModel):
    """Response de listagem de otimizações."""

    optimizations: List[dict]
    total: int
    page: int
    page_size: int


class OptimizationStatisticsResponse(BaseModel):
    """Response de estatísticas de otimizações."""

    total_optimizations: int
    success_rate: float
    average_improvement: float
    by_type: dict
    by_component: dict


# Dependency injection functions (será configurado via app.dependency_overrides no main.py)
def get_mongodb_client() -> MongoDBClient:
    """
    Retorna a instância de MongoDBClient do estado da aplicação.

    Em produção, este fallback acessa o singleton global diretamente.
    Pode ser sobrescrito via FastAPI dependency_overrides no main.py.
    """
    from src import main
    if main.mongodb_client is None:
        raise HTTPException(
            status_code=503,
            detail="MongoDBClient not initialized. Service is starting up."
        )
    return main.mongodb_client


def get_redis_client() -> RedisClient:
    """
    Retorna a instância de RedisClient do estado da aplicação.

    Em produção, este fallback acessa o singleton global diretamente.
    Pode ser sobrescrito via FastAPI dependency_overrides no main.py.
    """
    from src import main
    if main.redis_client is None:
        raise HTTPException(
            status_code=503,
            detail="RedisClient not initialized. Service is starting up."
        )
    return main.redis_client


def get_optimization_engine() -> OptimizationEngine:
    """
    Retorna a instância de OptimizationEngine do estado da aplicação.

    Em produção, este fallback acessa o singleton global diretamente.
    Pode ser sobrescrito via FastAPI dependency_overrides no main.py.
    """
    from src import main
    if main.optimization_engine is None:
        raise HTTPException(
            status_code=503,
            detail="OptimizationEngine not initialized. Service is starting up."
        )
    return main.optimization_engine


def get_weight_recalibrator() -> WeightRecalibrator:
    """
    Retorna a instância de WeightRecalibrator do estado da aplicação.

    Em produção, este fallback acessa o singleton global diretamente.
    Pode ser sobrescrito via FastAPI dependency_overrides no main.py.
    """
    from src import main
    if main.weight_recalibrator is None:
        raise HTTPException(
            status_code=503,
            detail="WeightRecalibrator not initialized. Service is starting up."
        )
    return main.weight_recalibrator


def get_slo_adjuster() -> SLOAdjuster:
    """
    Retorna a instância de SLOAdjuster do estado da aplicação.

    Em produção, este fallback acessa o singleton global diretamente.
    Pode ser sobrescrito via FastAPI dependency_overrides no main.py.
    """
    from src import main
    if main.slo_adjuster is None:
        raise HTTPException(
            status_code=503,
            detail="SLOAdjuster not initialized. Service is starting up."
        )
    return main.slo_adjuster


@router.post("/trigger", response_model=TriggerOptimizationResponse)
async def trigger_optimization(
    request: TriggerOptimizationRequest,
    weight_recalibrator: WeightRecalibrator = Depends(get_weight_recalibrator),
    slo_adjuster: SLOAdjuster = Depends(get_slo_adjuster),
):
    """
    Trigger manual de otimização.

    Permite trigger manual de uma otimização específica com justificativa.
    """
    try:
        # Criar hipótese sintética
        from src.models.optimization_hypothesis import OptimizationHypothesis
        from src.models.optimization_event import Adjustment

        # Converter proposed_adjustments para objetos Adjustment
        adjustments = [
            Adjustment(
                parameter_name=adj.get('parameter_name', adj.get('key', '')),
                parameter=adj.get('parameter', ''),
                old_value=str(adj.get('old_value', '')),
                new_value=str(adj.get('new_value', adj.get('value', ''))),
                justification=adj.get('justification', request.justification),
            )
            for adj in request.proposed_adjustments
        ]

        hypothesis = OptimizationHypothesis(
            hypothesis_id=f"manual-{request.target_component}-{request.optimization_type.value}",
            optimization_type=request.optimization_type,
            target_component=request.target_component,
            hypothesis_text=request.justification,
            proposed_adjustments=adjustments,
            baseline_metrics={},
            target_metrics={},  # Will be populated during optimization
            expected_improvement=0.1,  # Placeholder
            confidence_score=0.8,
            risk_score=0.3,
            priority=3,  # Medium priority for manual triggers
        )

        # Aplicar otimização baseado no tipo
        optimization_event = None

        if request.optimization_type == OptimizationType.WEIGHT_RECALIBRATION:
            optimization_event = await weight_recalibrator.apply_weight_recalibration(hypothesis)

        elif request.optimization_type == OptimizationType.SLO_ADJUSTMENT:
            optimization_event = await slo_adjuster.apply_slo_adjustment(hypothesis)

        else:
            raise HTTPException(
                status_code=400, detail=f"Unsupported optimization type: {request.optimization_type.value}"
            )

        if not optimization_event:
            raise HTTPException(status_code=500, detail="Failed to apply optimization")

        return TriggerOptimizationResponse(
            optimization_id=optimization_event.optimization_id,
            status="applied",
            message=f"Optimization applied successfully to {request.target_component}",
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to trigger optimization: {str(e)}")


@router.get("", response_model=OptimizationListResponse)
async def list_optimizations(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    optimization_type: Optional[OptimizationType] = None,
    target_component: Optional[str] = None,
    status: Optional[str] = None,
    mongodb_client: MongoDBClient = Depends(get_mongodb_client),
):
    """
    Listar otimizações com filtros.

    Retorna lista paginada de otimizações aplicadas.
    """
    try:
        # Construir filtros
        filters = {}
        if optimization_type:
            filters["optimization_type"] = optimization_type.value
        if target_component:
            filters["target_component"] = target_component
        if status:
            filters["approval_status"] = status

        # Buscar otimizações
        optimizations = await mongodb_client.list_optimizations(
            filters=filters, skip=(page - 1) * page_size, limit=page_size
        )

        # Contar total (simplificado - idealmente seria uma query separada)
        total = len(optimizations)

        return OptimizationListResponse(
            optimizations=optimizations, total=total, page=page, page_size=page_size
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list optimizations: {str(e)}")


@router.get("/{optimization_id}")
async def get_optimization(
    optimization_id: str,
    mongodb_client: MongoDBClient = Depends(get_mongodb_client),
):
    """
    Obter detalhes de uma otimização.

    Retorna informações completas sobre uma otimização específica.
    """
    try:
        optimization = await mongodb_client.get_optimization(optimization_id)

        if not optimization:
            raise HTTPException(status_code=404, detail=f"Optimization {optimization_id} not found")

        return optimization

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get optimization: {str(e)}")


@router.post("/{optimization_id}/rollback")
async def rollback_optimization(
    optimization_id: str,
    mongodb_client: MongoDBClient = Depends(get_mongodb_client),
    weight_recalibrator: WeightRecalibrator = Depends(get_weight_recalibrator),
    slo_adjuster: SLOAdjuster = Depends(get_slo_adjuster),
):
    """
    Reverter uma otimização.

    Reverte uma otimização aplicada para o estado anterior.
    """
    try:
        # Obter otimização
        optimization = await mongodb_client.get_optimization(optimization_id)

        if not optimization:
            raise HTTPException(status_code=404, detail=f"Optimization {optimization_id} not found")

        optimization_type = OptimizationType(optimization.get("optimization_type"))

        # Executar rollback baseado no tipo
        success = False

        if optimization_type == OptimizationType.WEIGHT_RECALIBRATION:
            success = await weight_recalibrator.rollback_weight_recalibration(optimization_id)

        elif optimization_type == OptimizationType.SLO_ADJUSTMENT:
            success = await slo_adjuster.rollback_slo_adjustment(optimization_id)

        if not success:
            raise HTTPException(status_code=500, detail="Failed to rollback optimization")

        return {"optimization_id": optimization_id, "status": "rolled_back", "message": "Optimization rolled back successfully"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to rollback optimization: {str(e)}")


@router.get("/statistics/summary", response_model=OptimizationStatisticsResponse)
async def get_statistics(
    mongodb_client: MongoDBClient = Depends(get_mongodb_client),
):
    """
    Obter estatísticas de otimizações.

    Retorna métricas agregadas sobre otimizações aplicadas.
    """
    try:
        # Buscar todas otimizações (simplificado - idealmente seria agregação MongoDB)
        all_optimizations = await mongodb_client.list_optimizations(filters={}, skip=0, limit=1000)

        total = len(all_optimizations)

        # Calcular success rate
        success_count = sum(1 for opt in all_optimizations if opt.get("approval_status") == "APPROVED")
        success_rate = success_count / total if total > 0 else 0.0

        # Calcular improvement médio
        improvements = [opt.get("improvement_percentage", 0) for opt in all_optimizations]
        average_improvement = sum(improvements) / len(improvements) if improvements else 0.0

        # Agrupar por tipo
        by_type = {}
        for opt in all_optimizations:
            opt_type = opt.get("optimization_type", "unknown")
            by_type[opt_type] = by_type.get(opt_type, 0) + 1

        # Agrupar por componente
        by_component = {}
        for opt in all_optimizations:
            component = opt.get("target_component", "unknown")
            by_component[component] = by_component.get(component, 0) + 1

        return OptimizationStatisticsResponse(
            total_optimizations=total,
            success_rate=success_rate,
            average_improvement=average_improvement,
            by_type=by_type,
            by_component=by_component,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get statistics: {str(e)}")
