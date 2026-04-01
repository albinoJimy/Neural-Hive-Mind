from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class QueryType(str, Enum):
    BY_ID = "BY_ID"
    BY_TYPE = "BY_TYPE"
    BY_PRIORITY = "BY_PRIORITY"
    BY_TIME_RANGE = "BY_TIME_RANGE"
    BY_ENTITY = "BY_ENTITY"
    BY_TAG = "BY_TAG"


class QueryRequest(BaseModel):
    """Request para query multi-source."""

    query_id: str
    plan_id: Optional[str] = None
    analyst_types: List[str] = Field(default_factory=list)
    time_window: Optional[Dict[str, datetime]] = None
    filters: Dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(default=100, ge=1, le=1000)


class MultiSourceQueryRequest(BaseModel):
    """Request para query multi-source com fusão."""

    sources: List[str] = Field(
        ..., description="Fontes de dados (mongodb, postgresql, clickhouse, neo4j)"
    )
    query_type: Optional[str] = Field(default="insights", description="Tipo de query")
    time_window: Optional[Dict[str, datetime]] = None
    filters: Dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(default=100, ge=1, le=1000)
    enable_fusion: bool = Field(default=True, description="Aplicar fusão de dados")
    use_cache: bool = Field(default=True)


class CorrelationRequest(BaseModel):
    """Request para calcular correlação entre métricas."""

    sources: List[str] = Field(..., description="Fontes de dados")
    metric_x: str = Field(..., description="Nome da métrica X")
    metric_y: str = Field(..., description="Nome da métrica Y")
    time_window: Optional[Dict[str, datetime]] = None


class SourceStatus(BaseModel):
    """Status de uma fonte de dados."""

    source: str
    status: str  # "healthy", "unhealthy", "degraded"
    latency_ms: Optional[float] = None
    last_query_at: Optional[datetime] = None
    error: Optional[str] = None


class InsightQueryRequest(BaseModel):
    query_type: QueryType
    insight_id: Optional[str] = None
    insight_type: Optional[str] = None
    priority: Optional[str] = None
    start_timestamp: Optional[int] = None
    end_timestamp: Optional[int] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    tags: Optional[List[str]] = None
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)
    include_expired: bool = Field(default=False)


class InsightQueryResponse(BaseModel):
    insights: List[dict]
    total_count: int
    query_time_ms: float
    cached: bool = False
