from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ReplanningTriggerType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    TRIGGER_TYPE_UNSPECIFIED: _ClassVar[ReplanningTriggerType]
    TRIGGER_TYPE_DRIFT: _ClassVar[ReplanningTriggerType]
    TRIGGER_TYPE_FAILURE: _ClassVar[ReplanningTriggerType]
    TRIGGER_TYPE_STRATEGIC: _ClassVar[ReplanningTriggerType]
    TRIGGER_TYPE_SLA_VIOLATION: _ClassVar[ReplanningTriggerType]
    TRIGGER_TYPE_RESOURCE_CONSTRAINT: _ClassVar[ReplanningTriggerType]

class WorkflowState(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    WORKFLOW_STATE_UNSPECIFIED: _ClassVar[WorkflowState]
    WORKFLOW_STATE_PENDING: _ClassVar[WorkflowState]
    WORKFLOW_STATE_RUNNING: _ClassVar[WorkflowState]
    WORKFLOW_STATE_PAUSED: _ClassVar[WorkflowState]
    WORKFLOW_STATE_COMPLETED: _ClassVar[WorkflowState]
    WORKFLOW_STATE_FAILED: _ClassVar[WorkflowState]
    WORKFLOW_STATE_CANCELLED: _ClassVar[WorkflowState]
    WORKFLOW_STATE_REPLANNING: _ClassVar[WorkflowState]
TRIGGER_TYPE_UNSPECIFIED: ReplanningTriggerType
TRIGGER_TYPE_DRIFT: ReplanningTriggerType
TRIGGER_TYPE_FAILURE: ReplanningTriggerType
TRIGGER_TYPE_STRATEGIC: ReplanningTriggerType
TRIGGER_TYPE_SLA_VIOLATION: ReplanningTriggerType
TRIGGER_TYPE_RESOURCE_CONSTRAINT: ReplanningTriggerType
WORKFLOW_STATE_UNSPECIFIED: WorkflowState
WORKFLOW_STATE_PENDING: WorkflowState
WORKFLOW_STATE_RUNNING: WorkflowState
WORKFLOW_STATE_PAUSED: WorkflowState
WORKFLOW_STATE_COMPLETED: WorkflowState
WORKFLOW_STATE_FAILED: WorkflowState
WORKFLOW_STATE_CANCELLED: WorkflowState
WORKFLOW_STATE_REPLANNING: WorkflowState

class AdjustPrioritiesRequest(_message.Message):
    __slots__ = ("workflow_id", "plan_id", "new_priority", "reason", "adjustment_id", "metadata")
    class MetadataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    WORKFLOW_ID_FIELD_NUMBER: _ClassVar[int]
    PLAN_ID_FIELD_NUMBER: _ClassVar[int]
    NEW_PRIORITY_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    ADJUSTMENT_ID_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    workflow_id: str
    plan_id: str
    new_priority: int
    reason: str
    adjustment_id: str
    metadata: _containers.ScalarMap[str, str]
    def __init__(self, workflow_id: _Optional[str] = ..., plan_id: _Optional[str] = ..., new_priority: _Optional[int] = ..., reason: _Optional[str] = ..., adjustment_id: _Optional[str] = ..., metadata: _Optional[_Mapping[str, str]] = ...) -> None: ...

class AdjustPrioritiesResponse(_message.Message):
    __slots__ = ("success", "message", "previous_priority", "applied_priority", "applied_at")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    PREVIOUS_PRIORITY_FIELD_NUMBER: _ClassVar[int]
    APPLIED_PRIORITY_FIELD_NUMBER: _ClassVar[int]
    APPLIED_AT_FIELD_NUMBER: _ClassVar[int]
    success: bool
    message: str
    previous_priority: int
    applied_priority: int
    applied_at: int
    def __init__(self, success: bool = ..., message: _Optional[str] = ..., previous_priority: _Optional[int] = ..., applied_priority: _Optional[int] = ..., applied_at: _Optional[int] = ...) -> None: ...

class ResourceAllocation(_message.Message):
    __slots__ = ("cpu_millicores", "memory_mb", "max_parallel_tickets", "gpu_count", "scheduling_priority")
    CPU_MILLICORES_FIELD_NUMBER: _ClassVar[int]
    MEMORY_MB_FIELD_NUMBER: _ClassVar[int]
    MAX_PARALLEL_TICKETS_FIELD_NUMBER: _ClassVar[int]
    GPU_COUNT_FIELD_NUMBER: _ClassVar[int]
    SCHEDULING_PRIORITY_FIELD_NUMBER: _ClassVar[int]
    cpu_millicores: int
    memory_mb: int
    max_parallel_tickets: int
    gpu_count: int
    scheduling_priority: int
    def __init__(self, cpu_millicores: _Optional[int] = ..., memory_mb: _Optional[int] = ..., max_parallel_tickets: _Optional[int] = ..., gpu_count: _Optional[int] = ..., scheduling_priority: _Optional[int] = ...) -> None: ...

class RebalanceResourcesRequest(_message.Message):
    __slots__ = ("workflow_ids", "target_allocation", "reason", "rebalance_id", "force")
    class TargetAllocationEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: ResourceAllocation
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[ResourceAllocation, _Mapping]] = ...) -> None: ...
    WORKFLOW_IDS_FIELD_NUMBER: _ClassVar[int]
    TARGET_ALLOCATION_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    REBALANCE_ID_FIELD_NUMBER: _ClassVar[int]
    FORCE_FIELD_NUMBER: _ClassVar[int]
    workflow_ids: _containers.RepeatedScalarFieldContainer[str]
    target_allocation: _containers.MessageMap[str, ResourceAllocation]
    reason: str
    rebalance_id: str
    force: bool
    def __init__(self, workflow_ids: _Optional[_Iterable[str]] = ..., target_allocation: _Optional[_Mapping[str, ResourceAllocation]] = ..., reason: _Optional[str] = ..., rebalance_id: _Optional[str] = ..., force: bool = ...) -> None: ...

class WorkflowRebalanceResult(_message.Message):
    __slots__ = ("workflow_id", "success", "message", "previous_allocation", "applied_allocation")
    WORKFLOW_ID_FIELD_NUMBER: _ClassVar[int]
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    PREVIOUS_ALLOCATION_FIELD_NUMBER: _ClassVar[int]
    APPLIED_ALLOCATION_FIELD_NUMBER: _ClassVar[int]
    workflow_id: str
    success: bool
    message: str
    previous_allocation: ResourceAllocation
    applied_allocation: ResourceAllocation
    def __init__(self, workflow_id: _Optional[str] = ..., success: bool = ..., message: _Optional[str] = ..., previous_allocation: _Optional[_Union[ResourceAllocation, _Mapping]] = ..., applied_allocation: _Optional[_Union[ResourceAllocation, _Mapping]] = ...) -> None: ...

class RebalanceResourcesResponse(_message.Message):
    __slots__ = ("success", "message", "results", "applied_at")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    RESULTS_FIELD_NUMBER: _ClassVar[int]
    APPLIED_AT_FIELD_NUMBER: _ClassVar[int]
    success: bool
    message: str
    results: _containers.RepeatedCompositeFieldContainer[WorkflowRebalanceResult]
    applied_at: int
    def __init__(self, success: bool = ..., message: _Optional[str] = ..., results: _Optional[_Iterable[_Union[WorkflowRebalanceResult, _Mapping]]] = ..., applied_at: _Optional[int] = ...) -> None: ...

class PauseWorkflowRequest(_message.Message):
    __slots__ = ("workflow_id", "reason", "pause_duration_seconds", "adjustment_id")
    WORKFLOW_ID_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    PAUSE_DURATION_SECONDS_FIELD_NUMBER: _ClassVar[int]
    ADJUSTMENT_ID_FIELD_NUMBER: _ClassVar[int]
    workflow_id: str
    reason: str
    pause_duration_seconds: int
    adjustment_id: str
    def __init__(self, workflow_id: _Optional[str] = ..., reason: _Optional[str] = ..., pause_duration_seconds: _Optional[int] = ..., adjustment_id: _Optional[str] = ...) -> None: ...

class PauseWorkflowResponse(_message.Message):
    __slots__ = ("success", "message", "paused_at", "scheduled_resume_at")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    PAUSED_AT_FIELD_NUMBER: _ClassVar[int]
    SCHEDULED_RESUME_AT_FIELD_NUMBER: _ClassVar[int]
    success: bool
    message: str
    paused_at: int
    scheduled_resume_at: int
    def __init__(self, success: bool = ..., message: _Optional[str] = ..., paused_at: _Optional[int] = ..., scheduled_resume_at: _Optional[int] = ...) -> None: ...

class ResumeWorkflowRequest(_message.Message):
    __slots__ = ("workflow_id", "reason", "adjustment_id")
    WORKFLOW_ID_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    ADJUSTMENT_ID_FIELD_NUMBER: _ClassVar[int]
    workflow_id: str
    reason: str
    adjustment_id: str
    def __init__(self, workflow_id: _Optional[str] = ..., reason: _Optional[str] = ..., adjustment_id: _Optional[str] = ...) -> None: ...

class ResumeWorkflowResponse(_message.Message):
    __slots__ = ("success", "message", "resumed_at", "pause_duration_seconds")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    RESUMED_AT_FIELD_NUMBER: _ClassVar[int]
    PAUSE_DURATION_SECONDS_FIELD_NUMBER: _ClassVar[int]
    success: bool
    message: str
    resumed_at: int
    pause_duration_seconds: int
    def __init__(self, success: bool = ..., message: _Optional[str] = ..., resumed_at: _Optional[int] = ..., pause_duration_seconds: _Optional[int] = ...) -> None: ...

class TriggerReplanningRequest(_message.Message):
    __slots__ = ("plan_id", "reason", "trigger_type", "adjustment_id", "context", "preserve_progress", "priority")
    class ContextEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    PLAN_ID_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    TRIGGER_TYPE_FIELD_NUMBER: _ClassVar[int]
    ADJUSTMENT_ID_FIELD_NUMBER: _ClassVar[int]
    CONTEXT_FIELD_NUMBER: _ClassVar[int]
    PRESERVE_PROGRESS_FIELD_NUMBER: _ClassVar[int]
    PRIORITY_FIELD_NUMBER: _ClassVar[int]
    plan_id: str
    reason: str
    trigger_type: ReplanningTriggerType
    adjustment_id: str
    context: _containers.ScalarMap[str, str]
    preserve_progress: bool
    priority: int
    def __init__(self, plan_id: _Optional[str] = ..., reason: _Optional[str] = ..., trigger_type: _Optional[_Union[ReplanningTriggerType, str]] = ..., adjustment_id: _Optional[str] = ..., context: _Optional[_Mapping[str, str]] = ..., preserve_progress: bool = ..., priority: _Optional[int] = ...) -> None: ...

class TriggerReplanningResponse(_message.Message):
    __slots__ = ("success", "message", "replanning_id", "triggered_at", "estimated_completion_seconds")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    REPLANNING_ID_FIELD_NUMBER: _ClassVar[int]
    TRIGGERED_AT_FIELD_NUMBER: _ClassVar[int]
    ESTIMATED_COMPLETION_SECONDS_FIELD_NUMBER: _ClassVar[int]
    success: bool
    message: str
    replanning_id: str
    triggered_at: int
    estimated_completion_seconds: int
    def __init__(self, success: bool = ..., message: _Optional[str] = ..., replanning_id: _Optional[str] = ..., triggered_at: _Optional[int] = ..., estimated_completion_seconds: _Optional[int] = ...) -> None: ...

class GetWorkflowStatusRequest(_message.Message):
    __slots__ = ("workflow_id", "include_tickets", "include_history")
    WORKFLOW_ID_FIELD_NUMBER: _ClassVar[int]
    INCLUDE_TICKETS_FIELD_NUMBER: _ClassVar[int]
    INCLUDE_HISTORY_FIELD_NUMBER: _ClassVar[int]
    workflow_id: str
    include_tickets: bool
    include_history: bool
    def __init__(self, workflow_id: _Optional[str] = ..., include_tickets: bool = ..., include_history: bool = ...) -> None: ...

class TicketSummary(_message.Message):
    __slots__ = ("total", "completed", "pending", "running", "failed")
    TOTAL_FIELD_NUMBER: _ClassVar[int]
    COMPLETED_FIELD_NUMBER: _ClassVar[int]
    PENDING_FIELD_NUMBER: _ClassVar[int]
    RUNNING_FIELD_NUMBER: _ClassVar[int]
    FAILED_FIELD_NUMBER: _ClassVar[int]
    total: int
    completed: int
    pending: int
    running: int
    failed: int
    def __init__(self, total: _Optional[int] = ..., completed: _Optional[int] = ..., pending: _Optional[int] = ..., running: _Optional[int] = ..., failed: _Optional[int] = ...) -> None: ...

class WorkflowEvent(_message.Message):
    __slots__ = ("event_type", "timestamp", "description", "metadata")
    class MetadataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    EVENT_TYPE_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    event_type: str
    timestamp: int
    description: str
    metadata: _containers.ScalarMap[str, str]
    def __init__(self, event_type: _Optional[str] = ..., timestamp: _Optional[int] = ..., description: _Optional[str] = ..., metadata: _Optional[_Mapping[str, str]] = ...) -> None: ...

class GetWorkflowStatusResponse(_message.Message):
    __slots__ = ("workflow_id", "plan_id", "state", "current_priority", "allocated_resources", "tickets", "progress_percent", "started_at", "updated_at", "sla_deadline", "sla_remaining_seconds", "history", "metadata")
    class MetadataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    WORKFLOW_ID_FIELD_NUMBER: _ClassVar[int]
    PLAN_ID_FIELD_NUMBER: _ClassVar[int]
    STATE_FIELD_NUMBER: _ClassVar[int]
    CURRENT_PRIORITY_FIELD_NUMBER: _ClassVar[int]
    ALLOCATED_RESOURCES_FIELD_NUMBER: _ClassVar[int]
    TICKETS_FIELD_NUMBER: _ClassVar[int]
    PROGRESS_PERCENT_FIELD_NUMBER: _ClassVar[int]
    STARTED_AT_FIELD_NUMBER: _ClassVar[int]
    UPDATED_AT_FIELD_NUMBER: _ClassVar[int]
    SLA_DEADLINE_FIELD_NUMBER: _ClassVar[int]
    SLA_REMAINING_SECONDS_FIELD_NUMBER: _ClassVar[int]
    HISTORY_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    workflow_id: str
    plan_id: str
    state: WorkflowState
    current_priority: int
    allocated_resources: ResourceAllocation
    tickets: TicketSummary
    progress_percent: float
    started_at: int
    updated_at: int
    sla_deadline: int
    sla_remaining_seconds: int
    history: _containers.RepeatedCompositeFieldContainer[WorkflowEvent]
    metadata: _containers.ScalarMap[str, str]
    def __init__(self, workflow_id: _Optional[str] = ..., plan_id: _Optional[str] = ..., state: _Optional[_Union[WorkflowState, str]] = ..., current_priority: _Optional[int] = ..., allocated_resources: _Optional[_Union[ResourceAllocation, _Mapping]] = ..., tickets: _Optional[_Union[TicketSummary, _Mapping]] = ..., progress_percent: _Optional[float] = ..., started_at: _Optional[int] = ..., updated_at: _Optional[int] = ..., sla_deadline: _Optional[int] = ..., sla_remaining_seconds: _Optional[int] = ..., history: _Optional[_Iterable[_Union[WorkflowEvent, _Mapping]]] = ..., metadata: _Optional[_Mapping[str, str]] = ...) -> None: ...
