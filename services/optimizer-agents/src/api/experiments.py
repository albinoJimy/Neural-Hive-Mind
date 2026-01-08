from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from src.clients.mongodb_client import MongoDBClient
from src.config.settings import get_settings
from src.models.experiment_request import ExperimentRequest, ExperimentType
from src.services.experiment_manager import ExperimentManager

router = APIRouter(prefix="/api/v1/experiments", tags=["experiments"])

settings = get_settings()


# Request/Response models
class SubmitExperimentRequest(BaseModel):
    """Request para submissão de experimento."""

    experiment_type: ExperimentType
    hypothesis: dict
    objective: str
    baseline_configuration: dict
    experimental_configuration: dict
    success_criteria: List[dict]
    guardrails: List[dict]
    traffic_percentage: float = 0.1
    duration_seconds: int = 3600


class SubmitExperimentResponse(BaseModel):
    """Response de submissão de experimento."""

    experiment_id: str
    status: str
    message: str


class ExperimentListResponse(BaseModel):
    """Response de listagem de experimentos."""

    experiments: List[dict]
    total: int
    page: int
    page_size: int


class ExperimentStatisticsResponse(BaseModel):
    """Response de estatísticas de experimentos."""

    total_experiments: int
    by_status: dict
    by_type: dict
    average_duration_seconds: float
    success_rate: float


# Dependency injection functions (será configurado via app.dependency_overrides no main.py)
def get_mongodb_client() -> MongoDBClient:
    """Dependency para injetar MongoDBClient."""
    raise NotImplementedError("MongoDBClient dependency not configured")


def get_experiment_manager() -> ExperimentManager:
    """Dependency para injetar ExperimentManager."""
    raise NotImplementedError("ExperimentManager dependency not configured")


@router.post("/submit", response_model=SubmitExperimentResponse)
async def submit_experiment(
    request: SubmitExperimentRequest,
    experiment_manager: ExperimentManager = Depends(get_experiment_manager),
):
    """
    Submeter novo experimento.

    Cria e submete um novo experimento para validação de hipótese.
    """
    try:
        # Criar hipótese sintética para ExperimentManager
        from src.models.optimization_hypothesis import OptimizationHypothesis
        from src.models.optimization_event import OptimizationType

        # Convert baseline_configuration values to float for metrics
        baseline_metrics = {}
        for k, v in request.baseline_configuration.items():
            try:
                baseline_metrics[k] = float(v) if isinstance(v, (int, float, str)) else 0.0
            except (ValueError, TypeError):
                baseline_metrics[k] = 0.0

        hypothesis = OptimizationHypothesis(
            hypothesis_id=f"exp-{request.experiment_type.value}",
            optimization_type=OptimizationType.POLICY_CHANGE,  # Default
            target_component=request.hypothesis.get("target_component", "unknown"),
            hypothesis_text=request.objective,
            proposed_adjustments=[],
            baseline_metrics=baseline_metrics,
            target_metrics=baseline_metrics,  # Start with same, will be updated by experiment
            expected_improvement=0.1,
            confidence_score=0.8,
            risk_score=0.3,
            priority=3,  # Medium priority
        )

        # Submeter experimento
        experiment_id = await experiment_manager.submit_experiment(hypothesis)

        if not experiment_id:
            raise HTTPException(status_code=500, detail="Failed to submit experiment")

        return SubmitExperimentResponse(
            experiment_id=experiment_id,
            status="submitted",
            message=f"Experiment submitted successfully: {experiment_id}",
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to submit experiment: {str(e)}")


@router.get("", response_model=ExperimentListResponse)
async def list_experiments(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: Optional[str] = None,
    experiment_type: Optional[ExperimentType] = None,
    mongodb_client: MongoDBClient = Depends(get_mongodb_client),
):
    """
    Listar experimentos com filtros.

    Retorna lista paginada de experimentos.
    """
    try:
        # Construir filtros
        filters = {}
        if status:
            filters["status"] = status
        if experiment_type:
            filters["experiment_type"] = experiment_type.value

        # Buscar experimentos (simplificado - idealmente seria query MongoDB)
        # Por enquanto, retornar lista vazia como placeholder
        experiments = []
        total = 0

        return ExperimentListResponse(experiments=experiments, total=total, page=page, page_size=page_size)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list experiments: {str(e)}")


@router.get("/{experiment_id}")
async def get_experiment(
    experiment_id: str,
    experiment_manager: ExperimentManager = Depends(get_experiment_manager),
):
    """
    Obter detalhes de um experimento.

    Retorna informações completas sobre um experimento específico.
    """
    try:
        experiment = await experiment_manager.get_experiment(experiment_id)

        if not experiment:
            raise HTTPException(status_code=404, detail=f"Experiment {experiment_id} not found")

        return experiment

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get experiment: {str(e)}")


@router.post("/{experiment_id}/abort")
async def abort_experiment(
    experiment_id: str,
    experiment_manager: ExperimentManager = Depends(get_experiment_manager),
):
    """
    Abortar experimento em execução.

    Interrompe um experimento que está em andamento.
    """
    try:
        # Obter experimento
        experiment = await experiment_manager.get_experiment(experiment_id)

        if not experiment:
            raise HTTPException(status_code=404, detail=f"Experiment {experiment_id} not found")

        # Verificar se está em execução
        status = experiment.get("status", "")
        if status not in ["RUNNING", "PENDING"]:
            raise HTTPException(
                status_code=400, detail=f"Experiment {experiment_id} is not running (status: {status})"
            )

        # Abortar
        success = await experiment_manager.abort_experiment(experiment_id)

        if not success:
            raise HTTPException(status_code=500, detail="Failed to abort experiment")

        return {"experiment_id": experiment_id, "status": "aborted", "message": "Experiment aborted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to abort experiment: {str(e)}")


@router.get("/{experiment_id}/results")
async def get_experiment_results(
    experiment_id: str,
    experiment_manager: ExperimentManager = Depends(get_experiment_manager),
):
    """
    Obter resultados de um experimento.

    Retorna análise detalhada dos resultados de um experimento completado.
    """
    try:
        # Obter experimento
        experiment = await experiment_manager.get_experiment(experiment_id)

        if not experiment:
            raise HTTPException(status_code=404, detail=f"Experiment {experiment_id} not found")

        # Verificar se completado
        status = experiment.get("status", "")
        if status != "COMPLETED":
            raise HTTPException(
                status_code=400, detail=f"Experiment {experiment_id} is not completed (status: {status})"
            )

        # Analisar resultados
        results = await experiment_manager.analyze_experiment_results(experiment_id)

        if not results:
            raise HTTPException(status_code=500, detail="Failed to analyze experiment results")

        return results

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get experiment results: {str(e)}")


@router.get("/statistics/summary", response_model=ExperimentStatisticsResponse)
async def get_statistics(
    mongodb_client: MongoDBClient = Depends(get_mongodb_client),
):
    """
    Obter estatísticas de experimentos.

    Retorna métricas agregadas sobre experimentos executados.
    """
    try:
        # Placeholder - idealmente seria agregação MongoDB
        return ExperimentStatisticsResponse(
            total_experiments=0,
            by_status={},
            by_type={},
            average_duration_seconds=0.0,
            success_rate=0.0,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get statistics: {str(e)}")
