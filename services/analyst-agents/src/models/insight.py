from pydantic import BaseModel, Field
from typing import List, Dict, Optional
from enum import Enum
from datetime import datetime
import hashlib
import json


class InsightType(str, Enum):
    STRATEGIC = 'STRATEGIC'
    OPERATIONAL = 'OPERATIONAL'
    PREDICTIVE = 'PREDICTIVE'
    CAUSAL = 'CAUSAL'
    ANOMALY = 'ANOMALY'


class Priority(str, Enum):
    LOW = 'LOW'
    MEDIUM = 'MEDIUM'
    HIGH = 'HIGH'
    CRITICAL = 'CRITICAL'


class Recommendation(BaseModel):
    action: str
    priority: str
    estimated_impact: float


class RelatedEntity(BaseModel):
    entity_type: str
    entity_id: str
    relationship: str


class TimeWindow(BaseModel):
    start_timestamp: int
    end_timestamp: int


class AnalystInsight(BaseModel):
    insight_id: str = Field(..., description='UUID único do insight')
    version: str = Field(default='1.0.0', description='Versão do schema')
    correlation_id: str
    trace_id: str
    span_id: str
    insight_type: InsightType
    priority: Priority
    title: str
    summary: str
    detailed_analysis: str
    data_sources: List[str]
    metrics: Dict[str, float]
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    impact_score: float = Field(..., ge=0.0, le=1.0)
    recommendations: List[Recommendation]
    related_entities: List[RelatedEntity]
    time_window: TimeWindow
    created_at: int = Field(default_factory=lambda: int(datetime.utcnow().timestamp() * 1000))
    valid_until: Optional[int] = None
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, str] = Field(default_factory=dict)
    hash: str = Field(default='')
    schema_version: int = Field(default=1)

    def calculate_hash(self) -> str:
        """Calcular hash SHA-256 para integridade"""
        data = self.model_dump(exclude={'hash'})
        json_str = json.dumps(data, sort_keys=True)
        return hashlib.sha256(json_str.encode()).hexdigest()

    def model_post_init(self, __context):
        """Calcular hash após inicialização"""
        if not self.hash:
            self.hash = self.calculate_hash()
