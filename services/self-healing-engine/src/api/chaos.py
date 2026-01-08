"""
API REST para Chaos Engineering.

Endpoints para gerenciamento de experimentos de chaos,
execução de cenários e validação de playbooks.
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from ..chaos.chaos_models import (
    ChaosExperiment,
    ChaosExperimentRequest,
    ChaosExperimentResponse,
    ChaosExperimentStatus,
    ExperimentReport,
    ScenarioConfig,
    ValidationCriteria,
    ValidationResult,
)

router = APIRouter(prefix="/chaos", tags=["chaos"])


def get_chaos_engine(request: Request):
    """Dependency para obter ChaosEngine do app state."""
    chaos_engine = getattr(request.app.state, "chaos_engine", None)
    if not chaos_engine:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chaos Engine não está habilitado"
        )
    return chaos_engine


class ScenarioRequest(BaseModel):
    """Request para execução de cenário."""
    scenario_name: str = Field(..., description="Nome do cenário")
    target_service: str = Field(..., description="Serviço alvo")
    target_namespace: str = Field(default="default", description="Namespace")
    playbook_to_validate: Optional[str] = Field(default=None, description="Playbook para validar")
    custom_parameters: Dict[str, Any] = Field(default_factory=dict, description="Parâmetros customizados")
    executed_by: Optional[str] = Field(default=None, description="Executor")


class PlaybookValidationRequest(BaseModel):
    """Request para validação de playbook."""
    playbook_name: str = Field(..., description="Nome do playbook")
    scenario_name: str = Field(default="pod_failure", description="Cenário a usar")
    target_service: str = Field(..., description="Serviço alvo")
    target_namespace: str = Field(default="default", description="Namespace")


class ExperimentExecuteRequest(BaseModel):
    """Request para executar experimento."""
    executed_by: Optional[str] = Field(default=None, description="Executor")


@router.post("/experiments", response_model=ChaosExperimentResponse)
async def create_experiment(
    request: ChaosExperimentRequest,
    chaos_engine=Depends(get_chaos_engine),
):
    """
    Cria um novo experimento de chaos.

    O experimento é criado mas não executado automaticamente.
    Use POST /experiments/{id}/execute para executar.
    """
    try:
        response = await chaos_engine.create_experiment(request)
        return response
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/experiments/{experiment_id}")
async def get_experiment(
    experiment_id: str,
    chaos_engine=Depends(get_chaos_engine),
):
    """
    Retorna status de um experimento.
    """
    experiment = await chaos_engine.get_experiment_status(experiment_id)
    if not experiment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experimento não encontrado: {experiment_id}"
        )

    return experiment.model_dump(mode="json")


@router.post("/experiments/{experiment_id}/execute", response_model=ExperimentReport)
async def execute_experiment(
    experiment_id: str,
    request: ExperimentExecuteRequest,
    chaos_engine=Depends(get_chaos_engine),
):
    """
    Executa um experimento de chaos existente.

    Retorna relatório completo após conclusão.
    """
    try:
        report = await chaos_engine.execute_experiment(
            experiment_id,
            executed_by=request.executed_by
        )
        return report
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/experiments/{experiment_id}/rollback")
async def rollback_experiment(
    experiment_id: str,
    chaos_engine=Depends(get_chaos_engine),
):
    """
    Executa rollback manual de um experimento.

    Remove todas as injeções de falha ativas.
    """
    try:
        success = await chaos_engine.rollback_experiment(experiment_id)
        return {
            "success": success,
            "experiment_id": experiment_id,
            "message": "Rollback executado" if success else "Rollback falhou"
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/experiments")
async def list_active_experiments(
    chaos_engine=Depends(get_chaos_engine),
):
    """
    Lista experimentos ativos.
    """
    experiments = chaos_engine.get_active_experiments()
    return {
        "active_count": len(experiments),
        "experiments": [exp.model_dump(mode="json") for exp in experiments]
    }


@router.get("/scenarios")
async def list_scenarios(
    chaos_engine=Depends(get_chaos_engine),
):
    """
    Lista cenários disponíveis.
    """
    scenarios = chaos_engine.list_scenarios()
    scenario_info = []

    for name in scenarios:
        info = chaos_engine.get_scenario_info(name)
        if info:
            scenario_info.append({
                "name": name,
                **info
            })

    return {
        "total": len(scenario_info),
        "scenarios": scenario_info
    }


@router.get("/scenarios/{scenario_name}")
async def get_scenario(
    scenario_name: str,
    chaos_engine=Depends(get_chaos_engine),
):
    """
    Retorna informações sobre um cenário específico.
    """
    info = chaos_engine.get_scenario_info(scenario_name)
    if not info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cenário não encontrado: {scenario_name}"
        )

    return {
        "name": scenario_name,
        **info
    }


@router.post("/scenarios/execute", response_model=ExperimentReport)
async def execute_scenario(
    request: ScenarioRequest,
    chaos_engine=Depends(get_chaos_engine),
):
    """
    Executa um cenário pré-definido.

    Cria e executa o experimento automaticamente.
    """
    config = ScenarioConfig(
        name=f"{request.scenario_name} - {request.target_service}",
        description=f"Execução de cenário {request.scenario_name}",
        target_service=request.target_service,
        target_namespace=request.target_namespace,
        playbook_to_validate=request.playbook_to_validate,
        custom_parameters=request.custom_parameters,
    )

    try:
        report = await chaos_engine.execute_scenario(
            request.scenario_name,
            config,
            executed_by=request.executed_by
        )
        return report
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/validate-playbook", response_model=ValidationResult)
async def validate_playbook(
    request: PlaybookValidationRequest,
    chaos_engine=Depends(get_chaos_engine),
):
    """
    Valida eficácia de um playbook específico.

    Executa cenário de chaos e mede recuperação via playbook.
    """
    try:
        result = await chaos_engine.validate_playbook(
            playbook_name=request.playbook_name,
            scenario_name=request.scenario_name,
            target_service=request.target_service,
            target_namespace=request.target_namespace,
        )
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/reports")
async def list_reports(
    limit: int = 10,
    offset: int = 0,
    chaos_engine=Depends(get_chaos_engine),
):
    """
    Lista relatórios de experimentos.

    Requer MongoDB configurado.
    """
    if not chaos_engine.mongodb_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MongoDB não configurado para persistência de relatórios"
        )

    try:
        reports = await chaos_engine.mongodb_client.find(
            "chaos_reports",
            {},
            limit=limit,
            skip=offset,
            sort=[("generated_at", -1)]
        )

        return {
            "total": len(reports),
            "offset": offset,
            "limit": limit,
            "reports": reports
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/reports/{experiment_id}")
async def get_report(
    experiment_id: str,
    chaos_engine=Depends(get_chaos_engine),
):
    """
    Retorna relatório de um experimento específico.
    """
    if not chaos_engine.mongodb_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MongoDB não configurado"
        )

    try:
        report = await chaos_engine.mongodb_client.find_one(
            "chaos_reports",
            {"experiment_id": experiment_id}
        )

        if not report:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Relatório não encontrado: {experiment_id}"
            )

        return report
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/health")
async def chaos_health(request: Request):
    """
    Verifica saúde do módulo de Chaos Engineering.
    """
    chaos_engine = getattr(request.app.state, "chaos_engine", None)

    if not chaos_engine:
        return {
            "status": "disabled",
            "message": "Chaos Engine não está habilitado"
        }

    active_experiments = len(chaos_engine.get_active_experiments())

    return {
        "status": "healthy",
        "active_experiments": active_experiments,
        "max_concurrent_experiments": chaos_engine.max_concurrent_experiments,
        "opa_enabled": chaos_engine.require_opa_approval,
        "scenarios_available": len(chaos_engine.list_scenarios())
    }
