from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class GetTicketRequest(_message.Message):
    __slots__ = ("ticket_id",)
    TICKET_ID_FIELD_NUMBER: _ClassVar[int]
    ticket_id: str
    def __init__(self, ticket_id: _Optional[str] = ...) -> None: ...

class GetTicketResponse(_message.Message):
    __slots__ = ("ticket",)
    TICKET_FIELD_NUMBER: _ClassVar[int]
    ticket: ExecutionTicketProto
    def __init__(self, ticket: _Optional[_Union[ExecutionTicketProto, _Mapping]] = ...) -> None: ...

class ListTicketsRequest(_message.Message):
    __slots__ = ("plan_id", "status", "offset", "limit")
    PLAN_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    plan_id: str
    status: str
    offset: int
    limit: int
    def __init__(self, plan_id: _Optional[str] = ..., status: _Optional[str] = ..., offset: _Optional[int] = ..., limit: _Optional[int] = ...) -> None: ...

class ListTicketsResponse(_message.Message):
    __slots__ = ("tickets", "total")
    TICKETS_FIELD_NUMBER: _ClassVar[int]
    TOTAL_FIELD_NUMBER: _ClassVar[int]
    tickets: _containers.RepeatedCompositeFieldContainer[ExecutionTicketProto]
    total: int
    def __init__(self, tickets: _Optional[_Iterable[_Union[ExecutionTicketProto, _Mapping]]] = ..., total: _Optional[int] = ...) -> None: ...

class UpdateTicketStatusRequest(_message.Message):
    __slots__ = ("ticket_id", "status", "error_message")
    TICKET_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    ERROR_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    ticket_id: str
    status: str
    error_message: str
    def __init__(self, ticket_id: _Optional[str] = ..., status: _Optional[str] = ..., error_message: _Optional[str] = ...) -> None: ...

class UpdateTicketStatusResponse(_message.Message):
    __slots__ = ("ticket",)
    TICKET_FIELD_NUMBER: _ClassVar[int]
    ticket: ExecutionTicketProto
    def __init__(self, ticket: _Optional[_Union[ExecutionTicketProto, _Mapping]] = ...) -> None: ...

class GenerateTokenRequest(_message.Message):
    __slots__ = ("ticket_id",)
    TICKET_ID_FIELD_NUMBER: _ClassVar[int]
    ticket_id: str
    def __init__(self, ticket_id: _Optional[str] = ...) -> None: ...

class GenerateTokenResponse(_message.Message):
    __slots__ = ("access_token", "expires_at")
    ACCESS_TOKEN_FIELD_NUMBER: _ClassVar[int]
    EXPIRES_AT_FIELD_NUMBER: _ClassVar[int]
    access_token: str
    expires_at: int
    def __init__(self, access_token: _Optional[str] = ..., expires_at: _Optional[int] = ...) -> None: ...

class ExecutionTicketProto(_message.Message):
    __slots__ = ("ticket_id", "plan_id", "intent_id", "task_id", "task_type", "description", "status", "priority", "created_at")
    TICKET_ID_FIELD_NUMBER: _ClassVar[int]
    PLAN_ID_FIELD_NUMBER: _ClassVar[int]
    INTENT_ID_FIELD_NUMBER: _ClassVar[int]
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    TASK_TYPE_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    PRIORITY_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    ticket_id: str
    plan_id: str
    intent_id: str
    task_id: str
    task_type: str
    description: str
    status: str
    priority: str
    created_at: int
    def __init__(self, ticket_id: _Optional[str] = ..., plan_id: _Optional[str] = ..., intent_id: _Optional[str] = ..., task_id: _Optional[str] = ..., task_type: _Optional[str] = ..., description: _Optional[str] = ..., status: _Optional[str] = ..., priority: _Optional[str] = ..., created_at: _Optional[int] = ...) -> None: ...
