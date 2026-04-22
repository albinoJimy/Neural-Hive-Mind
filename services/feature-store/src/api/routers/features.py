"""
Feature Store API Endpoints

Endpoints REST para gerenciamento de features de planos cognitivos.
"""

from typing import Optional

import structlog
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from src.models.feature import (
    ComputationStatus,
    FeatureComputationRequest,
    FeatureListResponse,
    FeatureMetrics,
    FeatureResponse,
    FeatureVector,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/features", tags=["features"])

# Referência global para o serviço
_feature_store_service = None


def set_feature_store_service(service):
    """Define referência para o serviço de feature store"""
    global _feature_store_service
    _feature_store_service = service


def get_feature_store_service():
    """Obtém serviço de feature store"""
    if _feature_store_service is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Serviço de feature store não inicializado",
        )
    return _feature_store_service


@router.get("/{plan_id}", response_model=FeatureVector)
async def get_features(
    plan_id: str, use_cache: bool = Query(default=True, description="Usar cache")
):
    """
    Busca features de um plano

    Args:
        plan_id: ID do plano cognitivo
        use_cache: Se deve usar cache Redis

    Returns:
        FeatureVector com as features
    """
    logger.info("Buscando features", plan_id=plan_id, use_cache=use_cache)

    service = get_feature_store_service()
    features = await service.get_features(plan_id, use_cache=use_cache)

    if features is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Features não encontradas para plan_id: {plan_id}",
        )

    return features


@router.post("/{plan_id}", response_model=FeatureVector)
async def save_or_compute_features(plan_id: str, request: FeatureComputationRequest):
    """
    Salva ou computa features para um plano

    Se as features já existirem e force_recompute=False, retorna as existentes.
    Caso contrário, computa novas features.

    Args:
        plan_id: ID do plano cognitivo
        request: Dados para computação

    Returns:
        FeatureVector com as features
    """
    logger.info(
        "Salvando/computando features", plan_id=plan_id, force_recompute=request.force_recompute
    )

    # Garante que plan_id na URL bate com o request
    request.plan_id = plan_id

    service = get_feature_store_service()
    features = await service.compute_and_save(request)

    return features


@router.delete("/{plan_id}", response_model=FeatureResponse)
async def delete_features(plan_id: str):
    """
    Deleta features de um plano

    Args:
        plan_id: ID do plano cognitivo

    Returns:
        Confirmação da deleção
    """
    logger.info("Deletando features", plan_id=plan_id)

    service = get_feature_store_service()
    deleted = await service.delete_features(plan_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Features não encontradas para plan_id: {plan_id}",
        )

    return FeatureResponse(success=True, message=f"Features deletadas para plan_id: {plan_id}")


@router.get("", response_model=FeatureListResponse)
async def list_features(
    limit: int = Query(default=50, ge=1, le=100, description="Limite de resultados"),
    offset: int = Query(default=0, ge=0, description="Offset para paginação"),
    status: Optional[ComputationStatus] = Query(default=None, description="Filtro por status"),
):
    """
    Lista features com paginação

    Args:
        limit: Limite de resultados (max 100)
        offset: Offset para paginação
        status: Filtro opcional por status

    Returns:
        Lista de features
    """
    logger.info("Listando features", limit=limit, offset=offset, status=status)

    service = get_feature_store_service()
    result = await service.list_features(limit=limit, offset=offset, status_filter=status)

    return result


class BatchFeatureComputationRequest(BaseModel):
    """Wrapper para batch computation requests"""

    requests: list[FeatureComputationRequest]


@router.post("/batch", response_model=list[FeatureVector])
async def batch_compute_features(body: BatchFeatureComputationRequest):
    """
    Computa features para múltiplos planos em batch

    Args:
        body: Wrapper contendo lista de requests de computação

    Returns:
        Lista de FeatureVectors
    """
    logger.info("Computando features em batch", count=len(body.requests))

    service = get_feature_store_service()
    results = []

    for req in body.requests:
        try:
            features = await service.compute_and_save(req)
            results.append(features)
        except Exception as e:
            logger.error("Erro ao computar features", plan_id=req.plan_id, error=str(e))
            # Continua com outros requests

    return results


@router.get("/metrics/summary", response_model=FeatureMetrics)
async def get_metrics():
    """
    Retorna métricas do Feature Store

    Returns:
        Métricas de uso e performance
    """
    service = get_feature_store_service()
    metrics = await service.get_metrics()

    # Calcula tempo médio de computação (aproximado)
    avg_time = metrics.get("computation_count", 0) * 20  # Estimativa em ms

    return FeatureMetrics(
        total_features=metrics.get("total_features", 0),
        cached_features=metrics.get("cached_features", 0),
        computation_count=metrics.get("computation_count", 0),
        avg_computation_time_ms=avg_time,
        cache_hit_rate=metrics.get("cache_hit_rate", 0.0),
    )


@router.get("/by-plan-ids", response_model=list[FeatureVector])
async def get_features_by_plan_ids(
    plan_ids: str = Query(..., description="Lista de plan_ids separados por vírgula")
):
    """
    Busca features para múltiplos planos

    Args:
        plan_ids: IDs de planos separados por vírgula

    Returns:
        Lista de FeatureVectors
    """
    id_list = [pid.strip() for pid in plan_ids.split(",") if pid.strip()]

    logger.info("Buscando features múltiplas", count=len(id_list))

    service = get_feature_store_service()
    features_map = await service.get_features_by_plan_ids(id_list)

    # Retorna na mesma ordem dos IDs
    result = [features_map[pid] for pid in id_list if pid in features_map]

    return result


# -------------------------------------------------------------------------
# Lineage Endpoints
# -------------------------------------------------------------------------


@router.get("/{plan_id}/lineage")
async def get_feature_lineage(plan_id: str):
    """
    Obtém lineage de uma feature

    Args:
        plan_id: ID do plano cognitivo

    Returns:
        Dict com metadados de lineage
    """
    logger.info("Buscando lineage", plan_id=plan_id)

    service = get_feature_store_service()
    lineage = await service.get_feature_lineage(plan_id)

    if lineage is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lineage não encontrado para plan_id: {plan_id}",
        )

    return lineage


@router.get("/{plan_id}/lineage/tree")
async def get_lineage_tree(
    plan_id: str,
    max_depth: int = Query(default=5, ge=1, le=10, description="Profundidade máxima da árvore"),
):
    """
    Obtém árvore completa de lineage (upstream e downstream)

    Args:
        plan_id: ID do plano cognitivo
        max_depth: Profundidade máxima da árvore

    Returns:
        Dict com árvore de lineage incluindo upstream e downstream
    """
    logger.info("Buscando árvore de lineage", plan_id=plan_id, max_depth=max_depth)

    service = get_feature_store_service()
    tree = await service.get_lineage_tree(plan_id, max_depth)

    if tree is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Features não encontradas para plan_id: {plan_id}",
        )

    return tree


@router.get("/{plan_id}/lineage/impact")
async def get_lineage_impact(plan_id: str):
    """
    Analisa impacto downstream de uma feature

    Retorna informações sobre quais features seriam afetadas
    se esta feature mudar.

    Args:
        plan_id: ID do plano cognitivo

    Returns:
        Dict com análise de impacto
    """
    logger.info("Analisando impacto de lineage", plan_id=plan_id)

    service = get_feature_store_service()
    impact = await service.get_lineage_impact(plan_id)

    if impact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Features não encontradas para plan_id: {plan_id}",
        )

    return impact


@router.get("/lineage/validate/{plan_id}")
async def validate_lineage_integrity(plan_id: str):
    """
    Valida integridade do lineage de uma feature

    Verifica ciclos, timestamps, consistência de datasources, etc.

    Args:
        plan_id: ID do plano cognitivo

    Returns:
        Dict com relatório de validação
    """
    logger.info("Validando integridade de lineage", plan_id=plan_id)

    service = get_feature_store_service()
    report = await service.validate_lineage_integrity(plan_id)

    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Features não encontradas para plan_id: {plan_id}",
        )

    return report
