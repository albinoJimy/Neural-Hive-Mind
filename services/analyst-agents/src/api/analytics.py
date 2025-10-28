from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional
import structlog

logger = structlog.get_logger()
router = APIRouter()


class AnalyticsQueryRequest(BaseModel):
    sources: List[str]
    time_window: Dict[str, int]
    filters: Optional[Dict] = None
    metrics: Optional[List[str]] = None
    use_cache: bool = True


@router.post('/analytics/query')
async def execute_analytics_query(query: AnalyticsQueryRequest, request: Request):
    """Executar consulta analítica customizada"""
    try:
        app_state = request.app.state.app_state
        query_engine = app_state.query_engine

        query_spec = {
            'sources': query.sources,
            'time_window': query.time_window,
            'filters': query.filters or {},
            'metrics': query.metrics or [],
            'use_cache': query.use_cache
        }

        result = await query_engine.query_multi_source(query_spec)

        return {
            'results': result.get('results', {}),
            'cached': result.get('cached', False),
            'sources_queried': query.sources
        }

    except Exception as e:
        logger.error('analytics_query_failed', error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


class AnomalyDetectionRequest(BaseModel):
    metric_name: str
    values: List[float]
    method: str = 'zscore'
    threshold: float = 3.0


@router.post('/analytics/anomalies')
async def detect_anomalies(anomaly_request: AnomalyDetectionRequest, request: Request):
    """Detectar anomalias em métrica"""
    try:
        app_state = request.app.state.app_state
        analytics_engine = app_state.analytics_engine

        anomalies = analytics_engine.detect_anomalies(
            anomaly_request.metric_name,
            anomaly_request.values,
            method=anomaly_request.method,
            threshold=anomaly_request.threshold
        )

        return {
            'anomalies': anomalies,
            'count': len(anomalies),
            'method': anomaly_request.method,
            'threshold': anomaly_request.threshold
        }

    except Exception as e:
        logger.error('detect_anomalies_failed', error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


class TrendAnalysisRequest(BaseModel):
    metric_name: str
    time_series: List[List]  # [[timestamp, value], ...]


@router.post('/analytics/trends')
async def analyze_trends(trend_request: TrendAnalysisRequest, request: Request):
    """Analisar tendências"""
    try:
        app_state = request.app.state.app_state
        analytics_engine = app_state.analytics_engine

        time_series_tuples = [(t[0], t[1]) for t in trend_request.time_series]
        trend_analysis = analytics_engine.calculate_trend(
            trend_request.metric_name,
            time_series_tuples
        )

        return {
            'metric_name': trend_request.metric_name,
            'trend_analysis': trend_analysis
        }

    except Exception as e:
        logger.error('analyze_trends_failed', error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


class CorrelationRequest(BaseModel):
    metric1_name: str
    metric1_values: List[float]
    metric2_name: str
    metric2_values: List[float]


@router.post('/analytics/correlation')
async def calculate_correlation(corr_request: CorrelationRequest, request: Request):
    """Calcular correlação entre métricas"""
    try:
        app_state = request.app.state.app_state
        analytics_engine = app_state.analytics_engine

        correlation = analytics_engine.calculate_correlation(
            corr_request.metric1_values,
            corr_request.metric2_values
        )

        return {
            'metric1': corr_request.metric1_name,
            'metric2': corr_request.metric2_name,
            'correlation': correlation
        }

    except Exception as e:
        logger.error('calculate_correlation_failed', error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
