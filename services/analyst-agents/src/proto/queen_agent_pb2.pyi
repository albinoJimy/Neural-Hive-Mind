from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class GetStrategicDecisionRequest(_message.Message):
    __slots__ = ("decision_id",)
    DECISION_ID_FIELD_NUMBER: _ClassVar[int]
    decision_id: str
    def __init__(self, decision_id: _Optional[str] = ...) -> None: ...

class StrategicDecisionResponse(_message.Message):
    __slots__ = ("decision_id", "decision_type", "confidence_score", "risk_score", "reasoning_summary", "created_at", "target_entities", "action")
    DECISION_ID_FIELD_NUMBER: _ClassVar[int]
    DECISION_TYPE_FIELD_NUMBER: _ClassVar[int]
    CONFIDENCE_SCORE_FIELD_NUMBER: _ClassVar[int]
    RISK_SCORE_FIELD_NUMBER: _ClassVar[int]
    REASONING_SUMMARY_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    TARGET_ENTITIES_FIELD_NUMBER: _ClassVar[int]
    ACTION_FIELD_NUMBER: _ClassVar[int]
    decision_id: str
    decision_type: str
    confidence_score: float
    risk_score: float
    reasoning_summary: str
    created_at: int
    target_entities: _containers.RepeatedScalarFieldContainer[str]
    action: str
    def __init__(self, decision_id: _Optional[str] = ..., decision_type: _Optional[str] = ..., confidence_score: _Optional[float] = ..., risk_score: _Optional[float] = ..., reasoning_summary: _Optional[str] = ..., created_at: _Optional[int] = ..., target_entities: _Optional[_Iterable[str]] = ..., action: _Optional[str] = ...) -> None: ...

class ListStrategicDecisionsRequest(_message.Message):
    __slots__ = ("decision_type", "start_date", "end_date", "limit", "offset")
    DECISION_TYPE_FIELD_NUMBER: _ClassVar[int]
    START_DATE_FIELD_NUMBER: _ClassVar[int]
    END_DATE_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    decision_type: str
    start_date: int
    end_date: int
    limit: int
    offset: int
    def __init__(self, decision_type: _Optional[str] = ..., start_date: _Optional[int] = ..., end_date: _Optional[int] = ..., limit: _Optional[int] = ..., offset: _Optional[int] = ...) -> None: ...

class ListStrategicDecisionsResponse(_message.Message):
    __slots__ = ("decisions", "total")
    DECISIONS_FIELD_NUMBER: _ClassVar[int]
    TOTAL_FIELD_NUMBER: _ClassVar[int]
    decisions: _containers.RepeatedCompositeFieldContainer[StrategicDecisionResponse]
    total: int
    def __init__(self, decisions: _Optional[_Iterable[_Union[StrategicDecisionResponse, _Mapping]]] = ..., total: _Optional[int] = ...) -> None: ...

class GetSystemStatusRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class SystemStatusResponse(_message.Message):
    __slots__ = ("system_score", "sla_compliance", "error_rate", "resource_saturation", "active_incidents", "timestamp")
    SYSTEM_SCORE_FIELD_NUMBER: _ClassVar[int]
    SLA_COMPLIANCE_FIELD_NUMBER: _ClassVar[int]
    ERROR_RATE_FIELD_NUMBER: _ClassVar[int]
    RESOURCE_SATURATION_FIELD_NUMBER: _ClassVar[int]
    ACTIVE_INCIDENTS_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    system_score: float
    sla_compliance: float
    error_rate: float
    resource_saturation: float
    active_incidents: int
    timestamp: int
    def __init__(self, system_score: _Optional[float] = ..., sla_compliance: _Optional[float] = ..., error_rate: _Optional[float] = ..., resource_saturation: _Optional[float] = ..., active_incidents: _Optional[int] = ..., timestamp: _Optional[int] = ...) -> None: ...

class RequestExceptionRequest(_message.Message):
    __slots__ = ("exception_type", "plan_id", "justification", "guardrails_affected", "expires_at")
    EXCEPTION_TYPE_FIELD_NUMBER: _ClassVar[int]
    PLAN_ID_FIELD_NUMBER: _ClassVar[int]
    JUSTIFICATION_FIELD_NUMBER: _ClassVar[int]
    GUARDRAILS_AFFECTED_FIELD_NUMBER: _ClassVar[int]
    EXPIRES_AT_FIELD_NUMBER: _ClassVar[int]
    exception_type: str
    plan_id: str
    justification: str
    guardrails_affected: _containers.RepeatedScalarFieldContainer[str]
    expires_at: int
    def __init__(self, exception_type: _Optional[str] = ..., plan_id: _Optional[str] = ..., justification: _Optional[str] = ..., guardrails_affected: _Optional[_Iterable[str]] = ..., expires_at: _Optional[int] = ...) -> None: ...

class RequestExceptionResponse(_message.Message):
    __slots__ = ("exception_id", "status")
    EXCEPTION_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    exception_id: str
    status: str
    def __init__(self, exception_id: _Optional[str] = ..., status: _Optional[str] = ...) -> None: ...

class ApproveExceptionRequest(_message.Message):
    __slots__ = ("exception_id", "decision_id", "conditions")
    EXCEPTION_ID_FIELD_NUMBER: _ClassVar[int]
    DECISION_ID_FIELD_NUMBER: _ClassVar[int]
    CONDITIONS_FIELD_NUMBER: _ClassVar[int]
    exception_id: str
    decision_id: str
    conditions: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, exception_id: _Optional[str] = ..., decision_id: _Optional[str] = ..., conditions: _Optional[_Iterable[str]] = ...) -> None: ...

class ApproveExceptionResponse(_message.Message):
    __slots__ = ("exception_id", "status", "approved_at")
    EXCEPTION_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    APPROVED_AT_FIELD_NUMBER: _ClassVar[int]
    exception_id: str
    status: str
    approved_at: int
    def __init__(self, exception_id: _Optional[str] = ..., status: _Optional[str] = ..., approved_at: _Optional[int] = ...) -> None: ...

class RejectExceptionRequest(_message.Message):
    __slots__ = ("exception_id", "reason")
    EXCEPTION_ID_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    exception_id: str
    reason: str
    def __init__(self, exception_id: _Optional[str] = ..., reason: _Optional[str] = ...) -> None: ...

class RejectExceptionResponse(_message.Message):
    __slots__ = ("exception_id", "status", "rejected_at")
    EXCEPTION_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    REJECTED_AT_FIELD_NUMBER: _ClassVar[int]
    exception_id: str
    status: str
    rejected_at: int
    def __init__(self, exception_id: _Optional[str] = ..., status: _Optional[str] = ..., rejected_at: _Optional[int] = ...) -> None: ...

class GetActiveConflictsRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ConflictInfo(_message.Message):
    __slots__ = ("decision_id", "conflicts_with", "created_at")
    DECISION_ID_FIELD_NUMBER: _ClassVar[int]
    CONFLICTS_WITH_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    decision_id: str
    conflicts_with: str
    created_at: int
    def __init__(self, decision_id: _Optional[str] = ..., conflicts_with: _Optional[str] = ..., created_at: _Optional[int] = ...) -> None: ...

class GetActiveConflictsResponse(_message.Message):
    __slots__ = ("conflicts",)
    CONFLICTS_FIELD_NUMBER: _ClassVar[int]
    conflicts: _containers.RepeatedCompositeFieldContainer[ConflictInfo]
    def __init__(self, conflicts: _Optional[_Iterable[_Union[ConflictInfo, _Mapping]]] = ...) -> None: ...

class Recommendation(_message.Message):
    __slots__ = ("action", "priority", "estimated_impact")
    ACTION_FIELD_NUMBER: _ClassVar[int]
    PRIORITY_FIELD_NUMBER: _ClassVar[int]
    ESTIMATED_IMPACT_FIELD_NUMBER: _ClassVar[int]
    action: str
    priority: str
    estimated_impact: float
    def __init__(self, action: _Optional[str] = ..., priority: _Optional[str] = ..., estimated_impact: _Optional[float] = ...) -> None: ...

class RelatedEntity(_message.Message):
    __slots__ = ("entity_type", "entity_id", "relationship")
    ENTITY_TYPE_FIELD_NUMBER: _ClassVar[int]
    ENTITY_ID_FIELD_NUMBER: _ClassVar[int]
    RELATIONSHIP_FIELD_NUMBER: _ClassVar[int]
    entity_type: str
    entity_id: str
    relationship: str
    def __init__(self, entity_type: _Optional[str] = ..., entity_id: _Optional[str] = ..., relationship: _Optional[str] = ...) -> None: ...

class TimeWindow(_message.Message):
    __slots__ = ("start_timestamp", "end_timestamp")
    START_TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    END_TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    start_timestamp: int
    end_timestamp: int
    def __init__(self, start_timestamp: _Optional[int] = ..., end_timestamp: _Optional[int] = ...) -> None: ...

class SubmitInsightRequest(_message.Message):
    __slots__ = ("insight_id", "version", "correlation_id", "trace_id", "span_id", "insight_type", "priority", "title", "summary", "detailed_analysis", "data_sources", "metrics", "confidence_score", "impact_score", "recommendations", "related_entities", "time_window", "created_at", "valid_until", "tags", "metadata", "hash", "schema_version")
    class MetricsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: float
        def __init__(self, key: _Optional[str] = ..., value: _Optional[float] = ...) -> None: ...
    class MetadataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    INSIGHT_ID_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    CORRELATION_ID_FIELD_NUMBER: _ClassVar[int]
    TRACE_ID_FIELD_NUMBER: _ClassVar[int]
    SPAN_ID_FIELD_NUMBER: _ClassVar[int]
    INSIGHT_TYPE_FIELD_NUMBER: _ClassVar[int]
    PRIORITY_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    SUMMARY_FIELD_NUMBER: _ClassVar[int]
    DETAILED_ANALYSIS_FIELD_NUMBER: _ClassVar[int]
    DATA_SOURCES_FIELD_NUMBER: _ClassVar[int]
    METRICS_FIELD_NUMBER: _ClassVar[int]
    CONFIDENCE_SCORE_FIELD_NUMBER: _ClassVar[int]
    IMPACT_SCORE_FIELD_NUMBER: _ClassVar[int]
    RECOMMENDATIONS_FIELD_NUMBER: _ClassVar[int]
    RELATED_ENTITIES_FIELD_NUMBER: _ClassVar[int]
    TIME_WINDOW_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    VALID_UNTIL_FIELD_NUMBER: _ClassVar[int]
    TAGS_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    HASH_FIELD_NUMBER: _ClassVar[int]
    SCHEMA_VERSION_FIELD_NUMBER: _ClassVar[int]
    insight_id: str
    version: str
    correlation_id: str
    trace_id: str
    span_id: str
    insight_type: str
    priority: str
    title: str
    summary: str
    detailed_analysis: str
    data_sources: _containers.RepeatedScalarFieldContainer[str]
    metrics: _containers.ScalarMap[str, float]
    confidence_score: float
    impact_score: float
    recommendations: _containers.RepeatedCompositeFieldContainer[Recommendation]
    related_entities: _containers.RepeatedCompositeFieldContainer[RelatedEntity]
    time_window: TimeWindow
    created_at: int
    valid_until: int
    tags: _containers.RepeatedScalarFieldContainer[str]
    metadata: _containers.ScalarMap[str, str]
    hash: str
    schema_version: int
    def __init__(self, insight_id: _Optional[str] = ..., version: _Optional[str] = ..., correlation_id: _Optional[str] = ..., trace_id: _Optional[str] = ..., span_id: _Optional[str] = ..., insight_type: _Optional[str] = ..., priority: _Optional[str] = ..., title: _Optional[str] = ..., summary: _Optional[str] = ..., detailed_analysis: _Optional[str] = ..., data_sources: _Optional[_Iterable[str]] = ..., metrics: _Optional[_Mapping[str, float]] = ..., confidence_score: _Optional[float] = ..., impact_score: _Optional[float] = ..., recommendations: _Optional[_Iterable[_Union[Recommendation, _Mapping]]] = ..., related_entities: _Optional[_Iterable[_Union[RelatedEntity, _Mapping]]] = ..., time_window: _Optional[_Union[TimeWindow, _Mapping]] = ..., created_at: _Optional[int] = ..., valid_until: _Optional[int] = ..., tags: _Optional[_Iterable[str]] = ..., metadata: _Optional[_Mapping[str, str]] = ..., hash: _Optional[str] = ..., schema_version: _Optional[int] = ...) -> None: ...

class SubmitInsightResponse(_message.Message):
    __slots__ = ("accepted", "insight_id", "message")
    ACCEPTED_FIELD_NUMBER: _ClassVar[int]
    INSIGHT_ID_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    accepted: bool
    insight_id: str
    message: str
    def __init__(self, accepted: bool = ..., insight_id: _Optional[str] = ..., message: _Optional[str] = ...) -> None: ...
