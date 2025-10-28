"""
Memory Query Models
"""
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List
from enum import Enum


class QueryType(str, Enum):
    """Types of memory queries"""
    CONTEXT = 'context'
    SEMANTIC = 'semantic'
    HISTORICAL = 'historical'
    LINEAGE = 'lineage'
    QUALITY = 'quality'


class MemoryQueryRequest(BaseModel):
    """Request for unified memory query"""
    query_type: QueryType
    entity_id: str
    time_range: Optional[Tuple[datetime, datetime]] = None
    use_cache: bool = True
    max_results: int = Field(default=100, le=1000)
    include_metadata: bool = True


class MemoryQueryResponse(BaseModel):
    """Response from unified memory query"""
    query_id: str
    entity_id: str
    data: Dict[str, Any]
    source_layer: str  # 'redis', 'mongodb', 'clickhouse', 'neo4j'
    cache_hit: bool
    latency_ms: int
    metadata: Dict[str, Any]


class LineageNode(BaseModel):
    """Lineage tree node"""
    entity_id: str
    entity_type: str
    sources: List[str] = Field(default_factory=list)
    transformations: List[str] = Field(default_factory=list)
    timestamp: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DataQualityMetrics(BaseModel):
    """Data quality metrics"""
    data_type: str
    timestamp: datetime
    completeness_score: float = Field(ge=0.0, le=100.0)
    accuracy_score: float = Field(ge=0.0, le=100.0)
    timeliness_score: float = Field(ge=0.0, le=100.0)
    uniqueness_score: float = Field(ge=0.0, le=100.0)
    consistency_score: float = Field(ge=0.0, le=100.0)
    overall_score: float = Field(ge=0.0, le=100.0)
    violations: List[str] = Field(default_factory=list)
