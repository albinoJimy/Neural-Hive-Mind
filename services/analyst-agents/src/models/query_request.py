from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


class QueryType(str, Enum):
    BY_ID = 'BY_ID'
    BY_TYPE = 'BY_TYPE'
    BY_PRIORITY = 'BY_PRIORITY'
    BY_TIME_RANGE = 'BY_TIME_RANGE'
    BY_ENTITY = 'BY_ENTITY'
    BY_TAG = 'BY_TAG'


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
