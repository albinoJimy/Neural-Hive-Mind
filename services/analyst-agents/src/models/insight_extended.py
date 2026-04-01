"""
Modelos estendidos para Insights Analyst Agents.
"""
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AnalysisType(str, Enum):
    """Tipos de análise suportados."""

    TIMESERIES = "timeseries"
    MCP_AGGREGATED = "mcp_aggregated"
    ANOMALY_DETECTION = "anomaly_detection"
    CAUSAL = "causal"
    SEMANTIC = "semantic"


class InsightSource(str, Enum):
    """Fontes de insights."""

    KAFKA = "kafka"
    MCP = "mcp"
    API = "api"
    SYSTEM = "system"


class InsightStatus(str, Enum):
    """Status do insight."""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class InsightMetadata(BaseModel):
    """Metadados do insight."""

    source: InsightSource
    source_id: Optional[str] = None
    mcp_server: Optional[str] = None
    mcp_tools: List[str] = Field(default_factory=list)
    created_by: str = "system"


class InsightMetrics(BaseModel):
    """Métricas do insight."""

    processing_time_ms: int
    confidence_score: float = Field(ge=0.0, le=1.0)
    data_points: int


class TimeSeriesData(BaseModel):
    """Dados de série temporal."""

    metric_name: str
    start_time: datetime
    end_time: datetime
    resolution: str  # "1m", "5m", "1h", "1d"
    anomalies: List[Dict[str, Any]] = Field(default_factory=list)
    trend: str  # "increasing", "decreasing", "stable"
    seasonality: bool = False


class AnomalyPoint(BaseModel):
    """Ponto de anomalia."""

    timestamp: datetime
    value: float
    score: float
    severity: str  # "low", "medium", "high"


class InsightCreate(BaseModel):
    """Schema para criar insight."""

    analysis_type: AnalysisType
    title: str
    description: str
    data: Dict[str, Any]
    metadata: InsightMetadata
    tags: List[str] = Field(default_factory=list)


class InsightResponse(BaseModel):
    """Schema de resposta de insight."""

    insight_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    analysis_type: AnalysisType
    title: str
    description: str
    data: Dict[str, Any]
    metadata: InsightMetadata
    metrics: InsightMetrics
    timeseries: Optional[TimeSeriesData] = None
    tags: List[str] = Field(default_factory=list)
    status: InsightStatus = InsightStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None


class InsightListResponse(BaseModel):
    """Schema de listagem de insights."""

    items: List[InsightResponse]
    total: int
    limit: int
    offset: int


class AnalyticsQueryRequest(BaseModel):
    """Request para nova análise."""

    analysis_type: AnalysisType
    target: Dict[str, Any]
    parameters: Dict[str, Any] = Field(default_factory=dict)


class AnalyticsQueryResponse(BaseModel):
    """Response de nova análise."""

    query_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: InsightStatus
    estimated_completion: Optional[datetime] = None
    insight_id: Optional[str] = None


class TimeSeriesQuery(BaseModel):
    """Query de série temporal."""

    metric_name: str
    start: datetime
    end: datetime
    resolution: str = "5m"


class TimeSeriesResponse(BaseModel):
    """Response de série temporal."""

    metric_name: str
    time_range: Dict[str, datetime]
    resolution: str
    data: List[Dict[str, Any]]
    statistics: Dict[str, float]


class AnomalyDetectionQuery(BaseModel):
    """Query de detecção de anomalias."""

    metric_name: str
    start: datetime
    end: datetime
    method: str = "zscore"  # "zscore", "isolation_forest"
    threshold: float = 2.5


class AnomalyDetectionResponse(BaseModel):
    """Response de detecção de anomalias."""

    metric_name: str
    method: str
    threshold: float
    anomalies: List[AnomalyPoint]
    summary: Dict[str, int]


class DashboardData(BaseModel):
    """Dados agregados para dashboard."""

    time_range: str
    insights_by_type: Dict[str, int]
    anomalies_detected: int
    avg_processing_time_ms: float
    confidence_distribution: Dict[str, int]
    top_sources: List[Dict[str, Any]]
    recent_insights: List[InsightResponse]


class TimeSeriesCacheEntry(BaseModel):
    """Entrada de cache de série temporal."""

    cache_key: str
    metric_name: str
    data: List[Dict[str, Any]]
    statistics: Dict[str, float]
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
