"""
Analytics API V2 - Router expandido para Analyst Agents.
Implementa endpoints REST para insights, time-series, e dashboard.
"""
import asyncio
import json
from datetime import datetime, timedelta
from typing import Optional

import structlog
from fastapi import APIRouter, HTTPException, Query, Request, Response

from ..models.insight_extended import (
    AnalysisType,
    AnalyticsQueryRequest,
    AnalyticsQueryResponse,
    AnomalyDetectionQuery,
    AnomalyDetectionResponse,
    DashboardData,
    InsightCreate,
    InsightListResponse,
    InsightMetadata,
    InsightResponse,
    InsightSource,
    InsightStatus,
    TimeSeriesResponse,
)
from ..repositories.insight_repository import InsightRepository
from ..services.mcp_integration import MCPIntegration
from ..services.timeseries_analyzer import TimeSeriesAnalyzer
from ..utils.export_utils import export_insight as export_insight_util

logger = structlog.get_logger()
router = APIRouter()


# ============================================================================
# Insights Endpoints
# ============================================================================


@router.get("/analytics/insights", response_model=InsightListResponse)
async def list_insights(
    request: Request,
    analysis_type: Optional[str] = Query(None, description="Tipo de análise"),
    source: Optional[str] = Query(None, description="Fonte do insight"),
    tags: Optional[str] = Query(None, description="Tags separadas por vírgula"),
    status: Optional[str] = Query(None, description="Status do insight"),
    start_date: Optional[datetime] = Query(None, description="Data inicial (ISO 8601)"),
    end_date: Optional[datetime] = Query(None, description="Data final (ISO 8601)"),
    limit: int = Query(50, ge=1, le=1000, description="Itens por página"),
    offset: int = Query(0, ge=0, description="Paginação"),
):
    """Listar insights analíticos com paginação e filtros."""
    try:
        app_state = request.app.state.app_state
        insight_repo: InsightRepository = app_state.insight_repository

        # Parse filters
        analysis_type_enum = AnalysisType(analysis_type) if analysis_type else None
        source_enum = InsightSource(source) if source else None
        status_enum = InsightStatus(status) if status else None
        tags_list = tags.split(",") if tags else None

        items, total = await insight_repo.list(
            analysis_type=analysis_type_enum,
            source=source_enum,
            tags=tags_list,
            status=status_enum,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset,
        )

        return InsightListResponse(items=items, total=total, limit=limit, offset=offset)

    except Exception as e:
        logger.error("list_insights_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/insights/{insight_id}", response_model=InsightResponse)
async def get_insight(insight_id: str, request: Request):
    """Obter detalhes completos de um insight específico."""
    try:
        app_state = request.app.state.app_state
        insight_repo: InsightRepository = app_state.insight_repository

        insight = await insight_repo.get_by_id(insight_id)
        if not insight:
            raise HTTPException(status_code=404, detail="Insight not found")

        return insight

    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_insight_failed", insight_id=insight_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analytics/insights/query", response_model=AnalyticsQueryResponse)
async def create_query(query: AnalyticsQueryRequest, request: Request):
    """Criar nova análise sob demanda."""
    try:
        app_state = request.app.state.app_state
        insight_repo: InsightRepository = app_state.insight_repository

        # Create insight
        insight_create = InsightCreate(
            analysis_type=query.analysis_type,
            title=f"{query.analysis_type.value} analysis",
            description=f"Custom analysis for {query.target.get('metric_name', 'unknown')}",
            data=query.target,
            metadata=InsightMetadata(source=InsightSource.API, created_by="api"),
            tags=["api", query.analysis_type.value],
        )

        # Process based on type
        if query.analysis_type == AnalysisType.TIMESERIES:
            query.target.get("metric_name", "")
            query.target.get("time_range", {})
            # Simular processamento assíncrono
            insight = await insight_repo.create(insight_create)
            # Atualizar status
            await insight_repo.update_status(insight.insight_id, InsightStatus.COMPLETED)

            return AnalyticsQueryResponse(
                query_id=insight.insight_id,
                status=InsightStatus.COMPLETED,
                insight_id=insight.insight_id,
            )

        elif query.analysis_type == AnalysisType.MCP_AGGREGATED:
            # Process MCP integration
            mcp_integration: MCPIntegration = app_state.mcp_integration
            result = await mcp_integration.execute_aggregated_analysis(
                analysis_type=query.target.get("mcp_analysis", "code_discovery"),
                params=query.parameters,
            )

            insight_create.data = result
            insight = await insight_repo.create(insight_create)
            await insight_repo.update_status(insight.insight_id, InsightStatus.COMPLETED)

            return AnalyticsQueryResponse(
                query_id=insight.insight_id,
                status=InsightStatus.COMPLETED,
                insight_id=insight.insight_id,
            )

        else:
            raise HTTPException(
                status_code=422, detail=f"Unsupported analysis type: {query.analysis_type}"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("create_query_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/insights/{insight_id}/export")
async def export_insight(
    insight_id: str,
    request: Request,
    format: str = Query("json", pattern="^(json|csv|pdf)$", description="Formato de exportação"),
):
    """Exportar insight em formato específico (JSON/CSV/PDF)."""
    try:
        app_state = request.app.state.app_state
        insight_repo: InsightRepository = app_state.insight_repository

        insight = await insight_repo.get_by_id(insight_id)
        if not insight:
            raise HTTPException(status_code=404, detail="Insight not found")

        # Use export utility
        media_type, content = export_insight_util(insight, format)
        filename = f"insight_{insight_id[:8]}_{format}"

        return Response(
            content=content,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("export_insight_failed", insight_id=insight_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/metrics")
async def get_analytics_metrics(request: Request):
    """Métricas do Analyst Agent (Prometheus format)."""
    try:
        app_state = request.app.state.app_state
        insight_repo: InsightRepository = app_state.insight_repository

        # Get summary stats
        summary = await insight_repo.get_analytics_summary(time_range_hours=24)

        metrics_text = """# HELP analyst_insights_total Total number of insights generated
# TYPE analyst_insights_total counter"""
        for analysis_type, count in summary.get("insights_by_type", {}).items():
            metrics_text += f'\nanalyst_insights_total{{analysis_type="{analysis_type}"}} {count}'

        metrics_text += "\n\n# HELP analyst_anomalies_detected_total Total anomalies detected"
        metrics_text += "\n# TYPE analyst_anomalies_detected_total gauge"
        metrics_text += f'\nanalyst_anomalies_detected_total {summary.get("anomalies_detected", 0)}'

        metrics_text += "\n\n# HELP analyst_processing_time_seconds Insight processing time"
        metrics_text += "\n# TYPE analyst_processing_time_seconds gauge"
        metrics_text += (
            f'\nanalyst_processing_time_seconds {summary.get("avg_processing_time_ms", 0) / 1000}'
        )

        return Response(content=metrics_text, media_type="text/plain")

    except Exception as e:
        logger.error("get_metrics_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Time-Series Endpoints
# ============================================================================


@router.get("/analytics/timeseries/{metric_name}", response_model=TimeSeriesResponse)
async def get_timeseries(
    metric_name: str,
    request: Request,
    start: datetime = Query(..., description="Data inicial"),
    end: datetime = Query(..., description="Data final"),
    resolution: str = Query("5m", pattern="^(1m|5m|1h|1d)$", description="Resolução"),
):
    """Obter série temporal de métrica específica."""
    try:
        app_state = request.app.state.app_state
        ts_analyzer: TimeSeriesAnalyzer = app_state.ts_analyzer

        # Simular busca de dados (em produção, buscar do ClickHouse/Prometheus)
        # Para este exemplo, gerar dados mock
        delta = end - start
        points = max(10, min(1000, int(delta.total_seconds() / 300)))  # 5-min intervals

        import random

        data = [(start + timedelta(minutes=i * 5), random.gauss(50, 15)) for i in range(points)]

        response = await ts_analyzer.analyze_timeseries(
            metric_name=metric_name,
            data=data,
            start=start,
            end=end,
            resolution=resolution,
        )

        return response

    except Exception as e:
        logger.error("get_timeseries_failed", metric_name=metric_name, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/analytics/timeseries/{metric_name}/anomalies", response_model=AnomalyDetectionResponse
)
async def detect_timeseries_anomalies(
    metric_name: str,
    request: Request,
    start: datetime = Query(..., description="Data inicial"),
    end: datetime = Query(..., description="Data final"),
    method: str = Query(
        "zscore", pattern="^(zscore|iqr|moving_avg)$", description="Método de detecção"
    ),
    threshold: float = Query(2.5, ge=1.0, le=5.0, description="Limiar de anomalia"),
):
    """Detectar anomalias em série temporal."""
    try:
        app_state = request.app.state.app_state
        ts_analyzer: TimeSeriesAnalyzer = app_state.ts_analyzer

        # Simular busca de dados
        delta = end - start
        points = max(10, min(1000, int(delta.total_seconds() / 300)))

        import random

        data = [(start + timedelta(minutes=i * 5), random.gauss(50, 15)) for i in range(points)]
        # Adicionar algumas anomalias
        data[points // 3] = (data[points // 3][0], 95.0)
        data[2 * points // 3] = (data[2 * points // 3][0], 5.0)

        query = AnomalyDetectionQuery(
            metric_name=metric_name,
            start=start,
            end=end,
            method=method,
            threshold=threshold,
        )

        response = await ts_analyzer.detect_anomalies_async(query, data)

        return response

    except Exception as e:
        logger.error("detect_anomalies_failed", metric_name=metric_name, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Dashboard Endpoint
# ============================================================================


@router.get("/analytics/dashboard", response_model=DashboardData)
async def get_dashboard_data(
    request: Request,
    time_range: str = Query("24h", pattern="^(1h|6h|24h|7d)$", description="Range de tempo"),
):
    """Dados agregados para dashboard Grafana."""
    try:
        app_state = request.app.state.app_state
        insight_repo: InsightRepository = app_state.insight_repository

        # Parse time range
        time_range_hours = {
            "1h": 1,
            "6h": 6,
            "24h": 24,
            "7d": 168,
        }.get(time_range, 24)

        summary = await insight_repo.get_analytics_summary(time_range_hours)

        # Get recent insights
        recent_items, _ = await insight_repo.list(limit=5, offset=0)

        return DashboardData(
            time_range=time_range,
            insights_by_type=summary.get("insights_by_type", {}),
            anomalies_detected=summary.get("anomalies_detected", 0),
            avg_processing_time_ms=summary.get("avg_processing_time_ms", 0),
            confidence_distribution=summary.get("confidence_distribution", {}),
            top_sources=summary.get("top_sources", []),
            recent_insights=recent_items,
        )

    except Exception as e:
        logger.error("get_dashboard_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/dashboard/stream")
async def get_dashboard_stream(
    request: Request,
    time_range: str = Query("24h", pattern="^(1h|6h|24h|7d)$", description="Range de tempo"),
    refresh_interval: int = Query(30, ge=5, le=300, description="Intervalo de refresh (segundos)"),
):
    """
    Stream de dados do dashboard em tempo real via Server-Sent Events (SSE).

    Envia atualizações do dashboard a cada `refresh_interval` segundos.
    Cliente deve usar EventSource para consumir este endpoint.
    """
    app_state = request.app.state.app_state
    insight_repo: InsightRepository = app_state.insight_repository

    # Parse time range
    time_range_hours = {
        "1h": 1,
        "6h": 6,
        "24h": 24,
        "7d": 168,
    }.get(time_range, 24)

    async def event_generator():
        """Gerador de eventos SSE."""
        try:
            while True:
                # Verificar se cliente desconectou
                if await request.is_disconnected():
                    logger.info("dashboard_stream_client_disconnected")
                    break

                # Buscar dados atualizados
                summary = await insight_repo.get_analytics_summary(time_range_hours)

                # Verificar disconnect após DB query
                if await request.is_disconnected():
                    logger.info("dashboard_stream_client_disconnected_after_summary")
                    break

                # Buscar insights recentes
                recent_items, _ = await insight_repo.list(
                    limit=10,
                    offset=0,
                )

                # Verificar disconnect após lista de insights
                if await request.is_disconnected():
                    logger.info("dashboard_stream_client_disconnected_after_list")
                    break

                # Criar payload
                dashboard_data = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "time_range": time_range,
                    "insights_by_type": summary.get("insights_by_type", {}),
                    "anomalies_detected": summary.get("anomalies_detected", 0),
                    "avg_processing_time_ms": summary.get("avg_processing_time_ms", 0),
                    "confidence_distribution": summary.get("confidence_distribution", {}),
                    "top_sources": summary.get("top_sources", []),
                    "recent_insights": [
                        {
                            "insight_id": item.insight_id,
                            "analysis_type": item.analysis_type.value,
                            "status": item.status.value,
                            "created_at": item.created_at.isoformat() if item.created_at else None,
                            "confidence_score": item.metrics.confidence_score
                            if item.metrics
                            else 0,
                        }
                        for item in recent_items
                    ],
                }

                # Verificar disconnect apos construcao do JSON
                if await request.is_disconnected():
                    logger.info("dashboard_stream_client_disconnected_after_json")
                    break

                # Enviar evento SSE
                yield f"data: {json.dumps(dashboard_data)}\n\n"

                # Aguardar próximo refresh
                await asyncio.sleep(refresh_interval)

        except Exception as e:
            logger.error("dashboard_stream_error", error=str(e))
            # Enviar erro via SSE e terminar loop
            error_data = {"error": str(e), "timestamp": datetime.utcnow().isoformat()}
            yield f"event: error\ndata: {json.dumps(error_data)}\n\n"
            # Break para evitar memory leak - cliente desconectou ou erro grave
            break

        finally:
            # Cleanup do generator
            logger.debug("dashboard_stream_generator_cleanup")

    return Response(
        content=event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Desabilitar buffering em nginx
        },
    )


# ============================================================================
# Health Check for MCP Integration
# ============================================================================


@router.get("/analytics/mcp-health")
async def get_mcp_health(request: Request):
    """Verificar saúde dos servidores MCP."""
    try:
        app_state = request.app.state.app_state
        mcp_integration: MCPIntegration = app_state.mcp_integration

        health = await mcp_integration.health_check()

        return health

    except Exception as e:
        logger.error("mcp_health_check_failed", error=str(e))
        return {"scout": False, "optimizer": False}


# Re-import Metadata for create_query endpoint
