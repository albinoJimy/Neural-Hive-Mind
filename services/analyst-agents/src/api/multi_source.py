"""
API REST para Multi-Source Aggregation.

Endpoint para consultar e fundir dados de múltiplas fontes.
"""

import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from ..models.query_request import (
    CorrelationRequest,
    MultiSourceQueryRequest,
    SourceStatus,
)
from ..services.query_engine import QueryEngine

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/analytics", tags=["multi-source"])

# Referência global para o QueryEngine
_query_engine: Optional[QueryEngine] = None


def set_query_engine(engine: QueryEngine):
    """Define referência para o QueryEngine."""
    global _query_engine
    _query_engine = engine


def get_query_engine() -> QueryEngine:
    """Obtém QueryEngine."""
    if _query_engine is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="QueryEngine não inicializado"
        )
    return _query_engine


# -------------------------------------------------------------------------
# Schemas de Request/Response
# -------------------------------------------------------------------------


class MultiSourceQueryResponse(BaseModel):
    """Response para query multi-source."""

    query_id: str
    results: Dict[str, Any]
    sources_queried: List[str]
    cached: bool
    fused: bool = False
    query_time_ms: float


class CrossSourceAnalysisResponse(BaseModel):
    """Response para análise cross-source."""

    query_id: str
    fused_data: Dict[str, Any]
    correlations: Dict[str, float]
    sources_summary: Dict[str, str]
    warnings: List[str]


class CorrelationResponse(BaseModel):
    """Response para correlação."""

    metric_x: str
    metric_y: str
    correlation: Optional[float]
    sources_analyzed: List[str]


# -------------------------------------------------------------------------
# Endpoints Multi-Source
# -------------------------------------------------------------------------


@router.post("/query-multi-source", response_model=MultiSourceQueryResponse)
async def query_multi_source(request: MultiSourceQueryRequest):
    """
    Consulta múltiplas fontes de dados em paralelo.

    Fontes suportadas: mongodb, postgresql, clickhouse, neo4j, prometheus

    Args:
        request: Configuração da query multi-source

    Returns:
        Resultados consolidados de todas as fontes
    """
    # time já importado no topo do módulo
    from uuid import uuid4

    start_time = time.time()
    query_id = request.query_id or str(uuid4())

    logger.info(
        "multi_source_query_started",
        query_id=query_id,
        sources=request.sources,
        query_type=request.query_type,
    )

    engine = get_query_engine()

    # Preparar query spec
    query_spec = {
        "query_id": query_id,
        "sources": request.sources,
        "query_type": request.query_type,
        "time_window": request.time_window,
        "filters": request.filters,
        "limit": request.limit,
        "enable_fusion": request.enable_fusion,
        "use_cache": request.use_cache,
    }

    # Adicionar plan_id se fornecido
    if hasattr(request, "plan_id") and request.plan_id:
        query_spec["plan_id"] = request.plan_id

    results = await engine.query_multi_source(query_spec)

    query_time_ms = (time.time() - start_time) * 1000

    return MultiSourceQueryResponse(
        query_id=query_id,
        results=results.get("results", {}),
        sources_queried=request.sources,
        cached=results.get("cached", False),
        fused=request.enable_fusion,
        query_time_ms=round(query_time_ms, 2),
    )


@router.post("/cross-source-analysis", response_model=CrossSourceAnalysisResponse)
async def cross_source_analysis(request: MultiSourceQueryRequest):
    """
    Realiza análise cross-source com fusão de dados e correlação.

    Funde dados de múltiplas fontes, calcula correlações
    e enriquece com contexto.

    Args:
        request: Configuração da análise

    Returns:
        Dados fundidos com correlações
    """
    # time já importado no topo do módulo
    from uuid import uuid4

    time.time()
    query_id = str(uuid4())

    logger.info(
        "cross_source_analysis_started",
        query_id=query_id,
        sources=request.sources,
    )

    engine = get_query_engine()

    # Preparar query spec com fusão habilitada
    query_spec = {
        "query_id": query_id,
        "sources": request.sources,
        "time_window": request.time_window,
        "filters": request.filters,
        "enable_fusion": True,
        "use_cache": request.use_cache,
    }

    results = await engine.query_multi_source(query_spec)

    # Extrair dados fundidos
    fused_data = results.get("results", {}).get("fused", {})
    correlations = fused_data.get("correlations", {})
    source_results = results.get("results", {}).get("by_source", {})

    # Sumário de fontes
    sources_summary = {}
    for source, data in source_results.items():
        if isinstance(data, dict) and "error" in data:
            sources_summary[source] = "error"
        elif isinstance(data, dict) and "data" in data:
            sources_summary[source] = "success"
        else:
            sources_summary[source] = "unknown"

    # Warnings
    warnings = fused_data.get("warnings", [])

    return CrossSourceAnalysisResponse(
        query_id=query_id,
        fused_data=fused_data,
        correlations=correlations,
        sources_summary=sources_summary,
        warnings=warnings,
    )


@router.get("/sources/status", response_model=List[SourceStatus])
async def get_sources_status():
    """
    Retorna status de todas as fontes de dados disponíveis.

    Verifica conectividade e latência de cada fonte.
    """
    engine = get_query_engine()
    sources_status = []

    # Lista de fontes disponíveis
    sources_config = {
        "clickhouse": engine.clickhouse,
        "neo4j": engine.neo4j,
        "elasticsearch": engine.elasticsearch,
        "prometheus": engine.prometheus,
        "postgresql": engine.postgresql,
        "mongodb": getattr(engine, "mongodb", None),
    }

    for source_name, client in sources_config.items():
        if client is None:
            sources_status.append(
                SourceStatus(
                    source=source_name,
                    status="not_configured",
                )
            )
            continue

        try:
            # Tentar health check específico por cliente
            time.time()

            if hasattr(client, "health_check"):
                if source_name == "postgresql":
                    health = await client.health_check()
                    source_status = health.get("status", "unknown")
                    latency_ms = health.get("latency_ms")
                else:
                    is_healthy = await client.health_check()
                    source_status = "healthy" if is_healthy else "unhealthy"
                    latency_ms = None
            elif hasattr(client, "ping"):
                is_healthy = await client.ping()
                source_status = "healthy" if is_healthy else "unhealthy"
                latency_ms = None
            else:
                source_status = "configured"
                latency_ms = None

            sources_status.append(
                SourceStatus(
                    source=source_name,
                    status=source_status,
                    latency_ms=latency_ms,
                    last_query_at=datetime.now(),
                )
            )

        except Exception as e:
            logger.warning("source_health_check_failed", source=source_name, error=str(e))
            sources_status.append(
                SourceStatus(
                    source=source_name,
                    status="unhealthy",
                    error=str(e),
                )
            )

    return sources_status


@router.post("/correlate", response_model=CorrelationResponse)
async def calculate_correlation(request: CorrelationRequest):
    """
    Calcula correlação entre duas métricas across sources.

    Args:
        request: Configuração da correlação

    Returns:
        Coeficiente de correlação entre as métricas
    """
    logger.info(
        "correlation_calculation_started",
        metric_x=request.metric_x,
        metric_y=request.metric_y,
        sources=request.sources,
    )

    engine = get_query_engine()

    correlation = await engine.correlate_metrics(
        sources=request.sources,
        metric_x=request.metric_x,
        metric_y=request.metric_y,
        time_window=request.time_window,
    )

    return CorrelationResponse(
        metric_x=request.metric_x,
        metric_y=request.metric_y,
        correlation=correlation,
        sources_analyzed=request.sources,
    )
