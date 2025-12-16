from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class GetInsightRequest(_message.Message):
    __slots__ = ("insight_id",)
    INSIGHT_ID_FIELD_NUMBER: _ClassVar[int]
    insight_id: str
    def __init__(self, insight_id: _Optional[str] = ...) -> None: ...

class GetInsightResponse(_message.Message):
    __slots__ = ("insight", "found")
    INSIGHT_FIELD_NUMBER: _ClassVar[int]
    FOUND_FIELD_NUMBER: _ClassVar[int]
    insight: Insight
    found: bool
    def __init__(self, insight: _Optional[_Union[Insight, _Mapping]] = ..., found: bool = ...) -> None: ...

class QueryInsightsRequest(_message.Message):
    __slots__ = ("insight_type", "priority", "start_timestamp", "end_timestamp", "limit", "offset")
    INSIGHT_TYPE_FIELD_NUMBER: _ClassVar[int]
    PRIORITY_FIELD_NUMBER: _ClassVar[int]
    START_TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    END_TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    insight_type: str
    priority: str
    start_timestamp: int
    end_timestamp: int
    limit: int
    offset: int
    def __init__(self, insight_type: _Optional[str] = ..., priority: _Optional[str] = ..., start_timestamp: _Optional[int] = ..., end_timestamp: _Optional[int] = ..., limit: _Optional[int] = ..., offset: _Optional[int] = ...) -> None: ...

class QueryInsightsResponse(_message.Message):
    __slots__ = ("insights", "total_count")
    INSIGHTS_FIELD_NUMBER: _ClassVar[int]
    TOTAL_COUNT_FIELD_NUMBER: _ClassVar[int]
    insights: _containers.RepeatedCompositeFieldContainer[Insight]
    total_count: int
    def __init__(self, insights: _Optional[_Iterable[_Union[Insight, _Mapping]]] = ..., total_count: _Optional[int] = ...) -> None: ...

class ExecuteAnalysisRequest(_message.Message):
    __slots__ = ("analysis_type", "parameters")
    class ParametersEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    ANALYSIS_TYPE_FIELD_NUMBER: _ClassVar[int]
    PARAMETERS_FIELD_NUMBER: _ClassVar[int]
    analysis_type: str
    parameters: _containers.ScalarMap[str, str]
    def __init__(self, analysis_type: _Optional[str] = ..., parameters: _Optional[_Mapping[str, str]] = ...) -> None: ...

class ExecuteAnalysisResponse(_message.Message):
    __slots__ = ("analysis_id", "results", "confidence")
    class ResultsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: float
        def __init__(self, key: _Optional[str] = ..., value: _Optional[float] = ...) -> None: ...
    ANALYSIS_ID_FIELD_NUMBER: _ClassVar[int]
    RESULTS_FIELD_NUMBER: _ClassVar[int]
    CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    analysis_id: str
    results: _containers.ScalarMap[str, float]
    confidence: float
    def __init__(self, analysis_id: _Optional[str] = ..., results: _Optional[_Mapping[str, float]] = ..., confidence: _Optional[float] = ...) -> None: ...

class GetStatisticsRequest(_message.Message):
    __slots__ = ("start_timestamp", "end_timestamp")
    START_TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    END_TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    start_timestamp: int
    end_timestamp: int
    def __init__(self, start_timestamp: _Optional[int] = ..., end_timestamp: _Optional[int] = ...) -> None: ...

class GetStatisticsResponse(_message.Message):
    __slots__ = ("insights_by_type", "insights_by_priority", "avg_confidence", "avg_impact")
    class InsightsByTypeEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: int
        def __init__(self, key: _Optional[str] = ..., value: _Optional[int] = ...) -> None: ...
    class InsightsByPriorityEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: int
        def __init__(self, key: _Optional[str] = ..., value: _Optional[int] = ...) -> None: ...
    INSIGHTS_BY_TYPE_FIELD_NUMBER: _ClassVar[int]
    INSIGHTS_BY_PRIORITY_FIELD_NUMBER: _ClassVar[int]
    AVG_CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    AVG_IMPACT_FIELD_NUMBER: _ClassVar[int]
    insights_by_type: _containers.ScalarMap[str, int]
    insights_by_priority: _containers.ScalarMap[str, int]
    avg_confidence: float
    avg_impact: float
    def __init__(self, insights_by_type: _Optional[_Mapping[str, int]] = ..., insights_by_priority: _Optional[_Mapping[str, int]] = ..., avg_confidence: _Optional[float] = ..., avg_impact: _Optional[float] = ...) -> None: ...

class HealthCheckRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class HealthCheckResponse(_message.Message):
    __slots__ = ("healthy", "status")
    HEALTHY_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    healthy: bool
    status: str
    def __init__(self, healthy: bool = ..., status: _Optional[str] = ...) -> None: ...

class Insight(_message.Message):
    __slots__ = ("insight_id", "version", "correlation_id", "trace_id", "span_id", "insight_type", "priority", "title", "summary", "detailed_analysis", "data_sources", "metrics", "confidence_score", "impact_score", "recommendations", "created_at", "hash")
    class MetricsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: float
        def __init__(self, key: _Optional[str] = ..., value: _Optional[float] = ...) -> None: ...
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
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    HASH_FIELD_NUMBER: _ClassVar[int]
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
    created_at: int
    hash: str
    def __init__(self, insight_id: _Optional[str] = ..., version: _Optional[str] = ..., correlation_id: _Optional[str] = ..., trace_id: _Optional[str] = ..., span_id: _Optional[str] = ..., insight_type: _Optional[str] = ..., priority: _Optional[str] = ..., title: _Optional[str] = ..., summary: _Optional[str] = ..., detailed_analysis: _Optional[str] = ..., data_sources: _Optional[_Iterable[str]] = ..., metrics: _Optional[_Mapping[str, float]] = ..., confidence_score: _Optional[float] = ..., impact_score: _Optional[float] = ..., recommendations: _Optional[_Iterable[_Union[Recommendation, _Mapping]]] = ..., created_at: _Optional[int] = ..., hash: _Optional[str] = ...) -> None: ...

class Recommendation(_message.Message):
    __slots__ = ("action", "priority", "estimated_impact")
    ACTION_FIELD_NUMBER: _ClassVar[int]
    PRIORITY_FIELD_NUMBER: _ClassVar[int]
    ESTIMATED_IMPACT_FIELD_NUMBER: _ClassVar[int]
    action: str
    priority: str
    estimated_impact: float
    def __init__(self, action: _Optional[str] = ..., priority: _Optional[str] = ..., estimated_impact: _Optional[float] = ...) -> None: ...
