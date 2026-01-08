# -*- coding: utf-8 -*-
"""
API Endpoints para A/B Testing.

Fornece endpoints REST para criar, gerenciar e analisar testes A/B.
"""

from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.clients.mongodb_client import MongoDBClient
from src.clients.redis_client import RedisClient
from src.config.settings import get_settings
from src.experimentation.ab_testing_engine import ABTestingEngine
from src.experimentation.randomization import RandomizationStrategyType
from src.experimentation.sample_size_calculator import SampleSizeCalculator

router = APIRouter(prefix="/api/v1/ab-tests", tags=["ab-testing"])

settings = get_settings()


# Request/Response Models

class CreateABTestRequest(BaseModel):
    """Request para criar teste A/B."""

    name: str = Field(..., description="Nome do teste")
    hypothesis: str = Field(..., description="Hipotese a ser testada")
    primary_metrics: List[str] = Field(..., description="Metricas primarias para decisao")
    secondary_metrics: List[str] = Field(default_factory=list, description="Metricas secundarias")
    traffic_split: float = Field(default=0.5, ge=0.0, le=1.0, description="Proporcao para treatment")
    randomization_strategy: str = Field(default="RANDOM", description="Estrategia de randomizacao")
    guardrails: List[Dict] = Field(default_factory=list, description="Configuracao de guardrails")
    minimum_sample_size: int = Field(default=100, ge=10, description="Tamanho minimo de amostra")
    maximum_duration_seconds: int = Field(default=604800, gt=0, description="Duracao maxima em segundos")
    early_stopping_enabled: bool = Field(default=True, description="Habilitar parada antecipada")
    bayesian_analysis_enabled: bool = Field(default=True, description="Habilitar analise Bayesiana")
    metadata: Dict = Field(default_factory=dict, description="Metadados adicionais")


class CreateABTestResponse(BaseModel):
    """Response de criacao de teste A/B."""

    experiment_id: str
    name: str
    status: str
    traffic_split: float
    minimum_sample_size: int
    message: str


class AssignmentRequest(BaseModel):
    """Request para atribuicao de entidade a grupo."""

    entity_id: str = Field(..., description="ID da entidade")
    strata_key: Optional[str] = Field(default=None, description="Chave de estrato")
    block_size: int = Field(default=10, ge=2, description="Tamanho do bloco")


class AssignmentResponse(BaseModel):
    """Response de atribuicao."""

    entity_id: str
    experiment_id: str
    group: str
    assigned_at: str


class MetricsSubmissionRequest(BaseModel):
    """Request para submissao de metricas."""

    group: str = Field(..., description="Grupo (control ou treatment)")
    metrics: Dict[str, float] = Field(..., description="Metricas coletadas")
    entity_id: Optional[str] = Field(default=None, description="ID da entidade")


class MetricsSubmissionResponse(BaseModel):
    """Response de submissao de metricas."""

    experiment_id: str
    group: str
    metrics_count: int
    message: str


class ABTestResultsResponse(BaseModel):
    """Response de resultados de teste A/B."""

    experiment_id: str
    status: str
    control_size: int
    treatment_size: int
    primary_metrics_analysis: List[Dict]
    secondary_metrics_analysis: List[Dict]
    bayesian_analysis: Optional[List[Dict]]
    guardrails_status: Dict
    statistical_recommendation: str
    confidence_level: float
    early_stopped: bool
    early_stop_reason: Optional[str]
    analysis_timestamp: str


class ABTestStatusResponse(BaseModel):
    """Response de status de teste A/B."""

    experiment_id: str
    status: str
    control_size: int
    treatment_size: int
    minimum_sample_size: int
    percentage_complete: float
    estimated_remaining_hours: Optional[float]
    guardrails_ok: bool


class SampleSizeRequest(BaseModel):
    """Request para calculo de tamanho de amostra."""

    metric_type: str = Field(..., description="Tipo de metrica (continuous ou binary)")
    baseline_value: float = Field(..., description="Valor baseline")
    mde: float = Field(..., description="Minimum Detectable Effect")
    std_dev: Optional[float] = Field(default=None, description="Desvio padrao (para continuous)")
    alpha: float = Field(default=0.05, ge=0.01, le=0.10, description="Nivel de significancia")
    power: float = Field(default=0.80, ge=0.70, le=0.99, description="Power estatistico")
    is_relative: bool = Field(default=False, description="MDE e relativo")


class SampleSizeResponse(BaseModel):
    """Response de calculo de tamanho de amostra."""

    sample_size_per_group: int
    total_sample_size: int
    mde: float
    alpha: float
    power: float
    baseline_metric: float
    effect_type: str


# Dependency injection functions

def get_mongodb_client() -> MongoDBClient:
    """Dependency para injetar MongoDBClient."""
    raise NotImplementedError("MongoDBClient dependency not configured")


def get_redis_client() -> RedisClient:
    """Dependency para injetar RedisClient."""
    raise NotImplementedError("RedisClient dependency not configured")


def get_ab_testing_engine() -> ABTestingEngine:
    """Dependency para injetar ABTestingEngine."""
    raise NotImplementedError("ABTestingEngine dependency not configured")


# Endpoints

@router.post("/create", response_model=CreateABTestResponse)
async def create_ab_test(
    request: CreateABTestRequest,
    ab_engine: ABTestingEngine = Depends(get_ab_testing_engine),
):
    """
    Criar novo teste A/B.

    Cria um experimento A/B com as configuracoes especificadas.
    """
    try:
        # Converter estrategia
        strategy = RandomizationStrategyType(request.randomization_strategy)

        config = await ab_engine.create_ab_test(
            name=request.name,
            hypothesis=request.hypothesis,
            primary_metrics=request.primary_metrics,
            secondary_metrics=request.secondary_metrics,
            traffic_split=request.traffic_split,
            randomization_strategy=strategy,
            guardrails=request.guardrails,
            minimum_sample_size=request.minimum_sample_size,
            maximum_duration_seconds=request.maximum_duration_seconds,
            early_stopping_enabled=request.early_stopping_enabled,
            bayesian_analysis_enabled=request.bayesian_analysis_enabled,
            metadata=request.metadata,
        )

        return CreateABTestResponse(
            experiment_id=config.experiment_id,
            name=config.name,
            status=config.status,
            traffic_split=config.traffic_split,
            minimum_sample_size=config.minimum_sample_size,
            message=f"Teste A/B criado com sucesso: {config.experiment_id}",
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao criar teste A/B: {str(e)}")


@router.post("/{experiment_id}/assign", response_model=AssignmentResponse)
async def assign_to_group(
    experiment_id: str,
    request: AssignmentRequest,
    ab_engine: ABTestingEngine = Depends(get_ab_testing_engine),
):
    """
    Atribuir entidade a grupo do experimento.

    Atribui uma entidade ao grupo controle ou tratamento usando
    a estrategia de randomizacao configurada.
    """
    try:
        group = await ab_engine.assign_to_group(
            entity_id=request.entity_id,
            experiment_id=experiment_id,
            strata_key=request.strata_key,
            block_size=request.block_size,
        )

        from datetime import datetime

        return AssignmentResponse(
            entity_id=request.entity_id,
            experiment_id=experiment_id,
            group=group,
            assigned_at=datetime.utcnow().isoformat(),
        )

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha na atribuicao: {str(e)}")


@router.post("/{experiment_id}/metrics", response_model=MetricsSubmissionResponse)
async def submit_metrics(
    experiment_id: str,
    request: MetricsSubmissionRequest,
    ab_engine: ABTestingEngine = Depends(get_ab_testing_engine),
):
    """
    Submeter metricas coletadas.

    Envia metricas coletadas para um grupo do experimento.
    """
    try:
        if request.group not in ["control", "treatment"]:
            raise HTTPException(
                status_code=400,
                detail="Grupo deve ser 'control' ou 'treatment'",
            )

        await ab_engine.collect_metrics(
            experiment_id=experiment_id,
            group=request.group,
            metrics=request.metrics,
            entity_id=request.entity_id,
        )

        return MetricsSubmissionResponse(
            experiment_id=experiment_id,
            group=request.group,
            metrics_count=len(request.metrics),
            message="Metricas coletadas com sucesso",
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao coletar metricas: {str(e)}")


@router.get("/{experiment_id}/results", response_model=ABTestResultsResponse)
async def get_results(
    experiment_id: str,
    ab_engine: ABTestingEngine = Depends(get_ab_testing_engine),
):
    """
    Obter resultados do teste A/B.

    Retorna analise estatistica completa dos resultados.
    """
    try:
        results = await ab_engine.analyze_results(experiment_id)

        return ABTestResultsResponse(
            experiment_id=results.experiment_id,
            status=results.status,
            control_size=results.control_size,
            treatment_size=results.treatment_size,
            primary_metrics_analysis=results.primary_metrics_analysis,
            secondary_metrics_analysis=results.secondary_metrics_analysis,
            bayesian_analysis=results.bayesian_analysis,
            guardrails_status=results.guardrails_status,
            statistical_recommendation=results.statistical_recommendation,
            confidence_level=results.confidence_level,
            early_stopped=results.early_stopped,
            early_stop_reason=results.early_stop_reason,
            analysis_timestamp=results.analysis_timestamp.isoformat(),
        )

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao obter resultados: {str(e)}")


@router.get("/{experiment_id}/status", response_model=ABTestStatusResponse)
async def get_status(
    experiment_id: str,
    ab_engine: ABTestingEngine = Depends(get_ab_testing_engine),
):
    """
    Obter status do teste A/B.

    Retorna informacoes de progresso do experimento.
    """
    try:
        # Validar tamanho de amostra
        sample_validation = await ab_engine._validate_sample_size(experiment_id)

        # Obter configuracao
        config = await ab_engine._get_experiment_config(experiment_id)
        if not config:
            raise HTTPException(status_code=404, detail=f"Experimento {experiment_id} nao encontrado")

        # Verificar guardrails
        control_metrics = await ab_engine._get_collected_metrics(experiment_id, "control")
        treatment_metrics = await ab_engine._get_collected_metrics(experiment_id, "treatment")

        guardrails_result = await ab_engine.guardrail_monitor.check_guardrails(
            experiment_id=experiment_id,
            guardrails_config=config.guardrails,
            control_metrics=control_metrics,
            treatment_metrics=treatment_metrics,
        )

        # Estimar tempo restante (simplificado)
        estimated_remaining = None
        if sample_validation["percentage_complete"] < 100:
            # Assumir taxa de 100 amostras/hora como default
            samples_remaining = sample_validation.get("samples_remaining", 0) * 2
            if samples_remaining > 0:
                estimated_remaining = samples_remaining / 100.0

        return ABTestStatusResponse(
            experiment_id=experiment_id,
            status=config.status,
            control_size=sample_validation["control_size"],
            treatment_size=sample_validation["treatment_size"],
            minimum_sample_size=sample_validation["minimum_required"],
            percentage_complete=sample_validation["percentage_complete"],
            estimated_remaining_hours=estimated_remaining,
            guardrails_ok=not guardrails_result.violated,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao obter status: {str(e)}")


@router.post("/{experiment_id}/stop")
async def stop_experiment(
    experiment_id: str,
    ab_engine: ABTestingEngine = Depends(get_ab_testing_engine),
    mongodb_client: MongoDBClient = Depends(get_mongodb_client),
):
    """
    Parar experimento manualmente.

    Interrompe o experimento e marca como completado.
    """
    try:
        # Atualizar status no MongoDB
        if mongodb_client:
            await mongodb_client.update_experiment_status(
                experiment_id, "COMPLETED", {"stopped_manually": True}
            )

        return {
            "experiment_id": experiment_id,
            "status": "COMPLETED",
            "message": "Experimento parado manualmente",
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao parar experimento: {str(e)}")


@router.post("/calculate-sample-size", response_model=SampleSizeResponse)
async def calculate_sample_size(
    request: SampleSizeRequest,
):
    """
    Calcular tamanho de amostra necessario.

    Calcula o tamanho de amostra necessario para atingir
    significancia estatistica desejada.
    """
    try:
        calculator = SampleSizeCalculator()

        if request.metric_type == "continuous":
            if request.std_dev is None:
                raise HTTPException(
                    status_code=400,
                    detail="std_dev e obrigatorio para metricas continuas",
                )

            if request.is_relative:
                result = calculator.calculate_for_continuous_relative(
                    baseline_mean=request.baseline_value,
                    mde_percentage=request.mde,
                    std_dev=request.std_dev,
                    alpha=request.alpha,
                    power=request.power,
                )
            else:
                result = calculator.calculate_for_continuous(
                    baseline_mean=request.baseline_value,
                    mde=request.mde,
                    std_dev=request.std_dev,
                    alpha=request.alpha,
                    power=request.power,
                )
        elif request.metric_type == "binary":
            if request.is_relative:
                result = calculator.calculate_for_binary_relative(
                    baseline_rate=request.baseline_value,
                    mde_percentage=request.mde,
                    alpha=request.alpha,
                    power=request.power,
                )
            else:
                result = calculator.calculate_for_binary(
                    baseline_rate=request.baseline_value,
                    mde=request.mde,
                    alpha=request.alpha,
                    power=request.power,
                )
        else:
            raise HTTPException(
                status_code=400,
                detail="metric_type deve ser 'continuous' ou 'binary'",
            )

        return SampleSizeResponse(
            sample_size_per_group=result.sample_size_per_group,
            total_sample_size=result.total_sample_size,
            mde=result.mde,
            alpha=result.alpha,
            power=result.power,
            baseline_metric=result.baseline_metric,
            effect_type=result.effect_type,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha no calculo: {str(e)}")


@router.get("", response_model=List[Dict])
async def list_ab_tests(
    status: Optional[str] = Query(default=None, description="Filtrar por status"),
    limit: int = Query(default=50, ge=1, le=100, description="Limite de resultados"),
    mongodb_client: MongoDBClient = Depends(get_mongodb_client),
):
    """
    Listar testes A/B.

    Retorna lista de testes A/B com filtros opcionais.
    """
    try:
        filters = {"experiment_type": "A_B_TEST"}
        if status:
            filters["status"] = status

        if mongodb_client:
            experiments = await mongodb_client.list_experiments(
                filters=filters,
                limit=limit,
            )
            return experiments

        return []

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao listar experimentos: {str(e)}")
