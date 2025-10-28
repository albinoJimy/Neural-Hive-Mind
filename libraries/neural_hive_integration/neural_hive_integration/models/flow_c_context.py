"""
Flow C context models for integration tracking.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class FlowCContext(BaseModel):
    """Context for Flow C execution."""
    intent_id: str
    plan_id: str
    decision_id: str
    correlation_id: str
    trace_id: str
    span_id: str
    started_at: datetime
    sla_deadline: datetime
    priority: int = Field(ge=1, le=10)
    risk_band: str  # low, medium, high, critical


class FlowCStep(BaseModel):
    """Individual step in Flow C execution."""
    step_name: str  # C1, C2, C3, C4, C5, C6
    status: str  # pending, in_progress, completed, failed
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    error: Optional[str] = None
    metadata: dict = {}


class FlowCResult(BaseModel):
    """Complete Flow C execution result."""
    success: bool
    steps: List[FlowCStep]
    total_duration_ms: int
    tickets_generated: int
    tickets_completed: int
    tickets_failed: int
    telemetry_published: bool
    error: Optional[str] = None
