from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class AgentType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    AGENT_TYPE_UNSPECIFIED: _ClassVar[AgentType]
    WORKER: _ClassVar[AgentType]
    SCOUT: _ClassVar[AgentType]
    GUARD: _ClassVar[AgentType]
    ANALYST: _ClassVar[AgentType]

class AgentStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    AGENT_STATUS_UNSPECIFIED: _ClassVar[AgentStatus]
    HEALTHY: _ClassVar[AgentStatus]
    UNHEALTHY: _ClassVar[AgentStatus]
    DEGRADED: _ClassVar[AgentStatus]
AGENT_TYPE_UNSPECIFIED: AgentType
WORKER: AgentType
SCOUT: AgentType
GUARD: AgentType
ANALYST: AgentType
AGENT_STATUS_UNSPECIFIED: AgentStatus
HEALTHY: AgentStatus
UNHEALTHY: AgentStatus
DEGRADED: AgentStatus

class AgentTelemetry(_message.Message):
    __slots__ = ("success_rate", "avg_duration_ms", "total_executions", "failed_executions", "last_execution_at")
    SUCCESS_RATE_FIELD_NUMBER: _ClassVar[int]
    AVG_DURATION_MS_FIELD_NUMBER: _ClassVar[int]
    TOTAL_EXECUTIONS_FIELD_NUMBER: _ClassVar[int]
    FAILED_EXECUTIONS_FIELD_NUMBER: _ClassVar[int]
    LAST_EXECUTION_AT_FIELD_NUMBER: _ClassVar[int]
    success_rate: float
    avg_duration_ms: int
    total_executions: int
    failed_executions: int
    last_execution_at: int
    def __init__(self, success_rate: _Optional[float] = ..., avg_duration_ms: _Optional[int] = ..., total_executions: _Optional[int] = ..., failed_executions: _Optional[int] = ..., last_execution_at: _Optional[int] = ...) -> None: ...

class AgentInfo(_message.Message):
    __slots__ = ("agent_id", "agent_type", "capabilities", "metadata", "telemetry", "status", "registered_at", "last_seen", "namespace", "cluster", "version", "schema_version")
    class MetadataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    AGENT_ID_FIELD_NUMBER: _ClassVar[int]
    AGENT_TYPE_FIELD_NUMBER: _ClassVar[int]
    CAPABILITIES_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    TELEMETRY_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    REGISTERED_AT_FIELD_NUMBER: _ClassVar[int]
    LAST_SEEN_FIELD_NUMBER: _ClassVar[int]
    NAMESPACE_FIELD_NUMBER: _ClassVar[int]
    CLUSTER_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    SCHEMA_VERSION_FIELD_NUMBER: _ClassVar[int]
    agent_id: str
    agent_type: AgentType
    capabilities: _containers.RepeatedScalarFieldContainer[str]
    metadata: _containers.ScalarMap[str, str]
    telemetry: AgentTelemetry
    status: AgentStatus
    registered_at: int
    last_seen: int
    namespace: str
    cluster: str
    version: str
    schema_version: int
    def __init__(self, agent_id: _Optional[str] = ..., agent_type: _Optional[_Union[AgentType, str]] = ..., capabilities: _Optional[_Iterable[str]] = ..., metadata: _Optional[_Mapping[str, str]] = ..., telemetry: _Optional[_Union[AgentTelemetry, _Mapping]] = ..., status: _Optional[_Union[AgentStatus, str]] = ..., registered_at: _Optional[int] = ..., last_seen: _Optional[int] = ..., namespace: _Optional[str] = ..., cluster: _Optional[str] = ..., version: _Optional[str] = ..., schema_version: _Optional[int] = ...) -> None: ...

class RegisterRequest(_message.Message):
    __slots__ = ("agent_type", "capabilities", "metadata", "namespace", "cluster", "version", "telemetry")
    class MetadataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    AGENT_TYPE_FIELD_NUMBER: _ClassVar[int]
    CAPABILITIES_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    NAMESPACE_FIELD_NUMBER: _ClassVar[int]
    CLUSTER_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    TELEMETRY_FIELD_NUMBER: _ClassVar[int]
    agent_type: AgentType
    capabilities: _containers.RepeatedScalarFieldContainer[str]
    metadata: _containers.ScalarMap[str, str]
    namespace: str
    cluster: str
    version: str
    telemetry: AgentTelemetry
    def __init__(self, agent_type: _Optional[_Union[AgentType, str]] = ..., capabilities: _Optional[_Iterable[str]] = ..., metadata: _Optional[_Mapping[str, str]] = ..., namespace: _Optional[str] = ..., cluster: _Optional[str] = ..., version: _Optional[str] = ..., telemetry: _Optional[_Union[AgentTelemetry, _Mapping]] = ...) -> None: ...

class RegisterResponse(_message.Message):
    __slots__ = ("agent_id", "registration_token", "registered_at")
    AGENT_ID_FIELD_NUMBER: _ClassVar[int]
    REGISTRATION_TOKEN_FIELD_NUMBER: _ClassVar[int]
    REGISTERED_AT_FIELD_NUMBER: _ClassVar[int]
    agent_id: str
    registration_token: str
    registered_at: int
    def __init__(self, agent_id: _Optional[str] = ..., registration_token: _Optional[str] = ..., registered_at: _Optional[int] = ...) -> None: ...

class HeartbeatRequest(_message.Message):
    __slots__ = ("agent_id", "telemetry")
    AGENT_ID_FIELD_NUMBER: _ClassVar[int]
    TELEMETRY_FIELD_NUMBER: _ClassVar[int]
    agent_id: str
    telemetry: AgentTelemetry
    def __init__(self, agent_id: _Optional[str] = ..., telemetry: _Optional[_Union[AgentTelemetry, _Mapping]] = ...) -> None: ...

class HeartbeatResponse(_message.Message):
    __slots__ = ("status", "last_seen")
    STATUS_FIELD_NUMBER: _ClassVar[int]
    LAST_SEEN_FIELD_NUMBER: _ClassVar[int]
    status: AgentStatus
    last_seen: int
    def __init__(self, status: _Optional[_Union[AgentStatus, str]] = ..., last_seen: _Optional[int] = ...) -> None: ...

class DeregisterRequest(_message.Message):
    __slots__ = ("agent_id",)
    AGENT_ID_FIELD_NUMBER: _ClassVar[int]
    agent_id: str
    def __init__(self, agent_id: _Optional[str] = ...) -> None: ...

class DeregisterResponse(_message.Message):
    __slots__ = ("success",)
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    success: bool
    def __init__(self, success: bool = ...) -> None: ...

class DiscoverRequest(_message.Message):
    __slots__ = ("capabilities", "filters", "max_results")
    class FiltersEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    CAPABILITIES_FIELD_NUMBER: _ClassVar[int]
    FILTERS_FIELD_NUMBER: _ClassVar[int]
    MAX_RESULTS_FIELD_NUMBER: _ClassVar[int]
    capabilities: _containers.RepeatedScalarFieldContainer[str]
    filters: _containers.ScalarMap[str, str]
    max_results: int
    def __init__(self, capabilities: _Optional[_Iterable[str]] = ..., filters: _Optional[_Mapping[str, str]] = ..., max_results: _Optional[int] = ...) -> None: ...

class DiscoverResponse(_message.Message):
    __slots__ = ("agents", "ranked")
    AGENTS_FIELD_NUMBER: _ClassVar[int]
    RANKED_FIELD_NUMBER: _ClassVar[int]
    agents: _containers.RepeatedCompositeFieldContainer[AgentInfo]
    ranked: bool
    def __init__(self, agents: _Optional[_Iterable[_Union[AgentInfo, _Mapping]]] = ..., ranked: bool = ...) -> None: ...

class GetAgentRequest(_message.Message):
    __slots__ = ("agent_id",)
    AGENT_ID_FIELD_NUMBER: _ClassVar[int]
    agent_id: str
    def __init__(self, agent_id: _Optional[str] = ...) -> None: ...

class GetAgentResponse(_message.Message):
    __slots__ = ("agent",)
    AGENT_FIELD_NUMBER: _ClassVar[int]
    agent: AgentInfo
    def __init__(self, agent: _Optional[_Union[AgentInfo, _Mapping]] = ...) -> None: ...

class ListAgentsRequest(_message.Message):
    __slots__ = ("agent_type", "filters")
    class FiltersEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    AGENT_TYPE_FIELD_NUMBER: _ClassVar[int]
    FILTERS_FIELD_NUMBER: _ClassVar[int]
    agent_type: AgentType
    filters: _containers.ScalarMap[str, str]
    def __init__(self, agent_type: _Optional[_Union[AgentType, str]] = ..., filters: _Optional[_Mapping[str, str]] = ...) -> None: ...

class ListAgentsResponse(_message.Message):
    __slots__ = ("agents",)
    AGENTS_FIELD_NUMBER: _ClassVar[int]
    agents: _containers.RepeatedCompositeFieldContainer[AgentInfo]
    def __init__(self, agents: _Optional[_Iterable[_Union[AgentInfo, _Mapping]]] = ...) -> None: ...

class WatchAgentsRequest(_message.Message):
    __slots__ = ("agent_type",)
    AGENT_TYPE_FIELD_NUMBER: _ClassVar[int]
    agent_type: AgentType
    def __init__(self, agent_type: _Optional[_Union[AgentType, str]] = ...) -> None: ...

class AgentChangeEvent(_message.Message):
    __slots__ = ("event_type", "agent", "timestamp")
    class EventType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        EVENT_TYPE_UNSPECIFIED: _ClassVar[AgentChangeEvent.EventType]
        REGISTERED: _ClassVar[AgentChangeEvent.EventType]
        UPDATED: _ClassVar[AgentChangeEvent.EventType]
        DEREGISTERED: _ClassVar[AgentChangeEvent.EventType]
        STATUS_CHANGED: _ClassVar[AgentChangeEvent.EventType]
    EVENT_TYPE_UNSPECIFIED: AgentChangeEvent.EventType
    REGISTERED: AgentChangeEvent.EventType
    UPDATED: AgentChangeEvent.EventType
    DEREGISTERED: AgentChangeEvent.EventType
    STATUS_CHANGED: AgentChangeEvent.EventType
    EVENT_TYPE_FIELD_NUMBER: _ClassVar[int]
    AGENT_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    event_type: AgentChangeEvent.EventType
    agent: AgentInfo
    timestamp: int
    def __init__(self, event_type: _Optional[_Union[AgentChangeEvent.EventType, str]] = ..., agent: _Optional[_Union[AgentInfo, _Mapping]] = ..., timestamp: _Optional[int] = ...) -> None: ...

class NotifyAgentRequest(_message.Message):
    __slots__ = ("agent_id", "notification_type", "message", "metadata")
    class MetadataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    AGENT_ID_FIELD_NUMBER: _ClassVar[int]
    NOTIFICATION_TYPE_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    agent_id: str
    notification_type: str
    message: str
    metadata: _containers.ScalarMap[str, str]
    def __init__(self, agent_id: _Optional[str] = ..., notification_type: _Optional[str] = ..., message: _Optional[str] = ..., metadata: _Optional[_Mapping[str, str]] = ...) -> None: ...

class NotifyAgentResponse(_message.Message):
    __slots__ = ("success", "error")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    success: bool
    error: str
    def __init__(self, success: bool = ..., error: _Optional[str] = ...) -> None: ...
