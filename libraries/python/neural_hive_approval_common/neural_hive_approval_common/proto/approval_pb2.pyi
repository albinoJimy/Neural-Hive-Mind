from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf import struct_pb2 as _struct_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class RiskBand(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    RISK_BAND_UNSPECIFIED: _ClassVar[RiskBand]
    RISK_BAND_LOW: _ClassVar[RiskBand]
    RISK_BAND_MEDIUM: _ClassVar[RiskBand]
    RISK_BAND_HIGH: _ClassVar[RiskBand]
    RISK_BAND_CRITICAL: _ClassVar[RiskBand]

class ApprovalStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    APPROVAL_STATUS_UNSPECIFIED: _ClassVar[ApprovalStatus]
    APPROVAL_STATUS_PENDING: _ClassVar[ApprovalStatus]
    APPROVAL_STATUS_APPROVED: _ClassVar[ApprovalStatus]
    APPROVAL_STATUS_REJECTED: _ClassVar[ApprovalStatus]
    APPROVAL_STATUS_CANCELLED: _ClassVar[ApprovalStatus]
    APPROVAL_STATUS_EXPIRED: _ClassVar[ApprovalStatus]

class Decision(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    DECISION_UNSPECIFIED: _ClassVar[Decision]
    DECISION_APPROVED: _ClassVar[Decision]
    DECISION_REJECTED: _ClassVar[Decision]
RISK_BAND_UNSPECIFIED: RiskBand
RISK_BAND_LOW: RiskBand
RISK_BAND_MEDIUM: RiskBand
RISK_BAND_HIGH: RiskBand
RISK_BAND_CRITICAL: RiskBand
APPROVAL_STATUS_UNSPECIFIED: ApprovalStatus
APPROVAL_STATUS_PENDING: ApprovalStatus
APPROVAL_STATUS_APPROVED: ApprovalStatus
APPROVAL_STATUS_REJECTED: ApprovalStatus
APPROVAL_STATUS_CANCELLED: ApprovalStatus
APPROVAL_STATUS_EXPIRED: ApprovalStatus
DECISION_UNSPECIFIED: Decision
DECISION_APPROVED: Decision
DECISION_REJECTED: Decision

class UnifiedApprovalRequest(_message.Message):
    __slots__ = ("approval_id", "plan_id", "intent_id", "original_intent_text", "risk_score", "risk_band", "is_destructive", "destructive_tasks", "risk_matrix", "status", "requested_at", "approved_by", "approved_at", "rejection_reason", "comments", "cognitive_plan")
    class RiskMatrixEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: float
        def __init__(self, key: _Optional[str] = ..., value: _Optional[float] = ...) -> None: ...
    APPROVAL_ID_FIELD_NUMBER: _ClassVar[int]
    PLAN_ID_FIELD_NUMBER: _ClassVar[int]
    INTENT_ID_FIELD_NUMBER: _ClassVar[int]
    ORIGINAL_INTENT_TEXT_FIELD_NUMBER: _ClassVar[int]
    RISK_SCORE_FIELD_NUMBER: _ClassVar[int]
    RISK_BAND_FIELD_NUMBER: _ClassVar[int]
    IS_DESTRUCTIVE_FIELD_NUMBER: _ClassVar[int]
    DESTRUCTIVE_TASKS_FIELD_NUMBER: _ClassVar[int]
    RISK_MATRIX_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    REQUESTED_AT_FIELD_NUMBER: _ClassVar[int]
    APPROVED_BY_FIELD_NUMBER: _ClassVar[int]
    APPROVED_AT_FIELD_NUMBER: _ClassVar[int]
    REJECTION_REASON_FIELD_NUMBER: _ClassVar[int]
    COMMENTS_FIELD_NUMBER: _ClassVar[int]
    COGNITIVE_PLAN_FIELD_NUMBER: _ClassVar[int]
    approval_id: str
    plan_id: str
    intent_id: str
    original_intent_text: str
    risk_score: float
    risk_band: RiskBand
    is_destructive: bool
    destructive_tasks: _containers.RepeatedScalarFieldContainer[str]
    risk_matrix: _containers.ScalarMap[str, float]
    status: ApprovalStatus
    requested_at: _timestamp_pb2.Timestamp
    approved_by: str
    approved_at: _timestamp_pb2.Timestamp
    rejection_reason: str
    comments: str
    cognitive_plan: _struct_pb2.Struct
    def __init__(self, approval_id: _Optional[str] = ..., plan_id: _Optional[str] = ..., intent_id: _Optional[str] = ..., original_intent_text: _Optional[str] = ..., risk_score: _Optional[float] = ..., risk_band: _Optional[_Union[RiskBand, str]] = ..., is_destructive: bool = ..., destructive_tasks: _Optional[_Iterable[str]] = ..., risk_matrix: _Optional[_Mapping[str, float]] = ..., status: _Optional[_Union[ApprovalStatus, str]] = ..., requested_at: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., approved_by: _Optional[str] = ..., approved_at: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., rejection_reason: _Optional[str] = ..., comments: _Optional[str] = ..., cognitive_plan: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ...) -> None: ...

class UnifiedApprovalDecision(_message.Message):
    __slots__ = ("plan_id", "decision", "approved_by", "approved_at", "rejection_reason", "comments", "ml_confidence", "ml_model_version", "auto_approved")
    PLAN_ID_FIELD_NUMBER: _ClassVar[int]
    DECISION_FIELD_NUMBER: _ClassVar[int]
    APPROVED_BY_FIELD_NUMBER: _ClassVar[int]
    APPROVED_AT_FIELD_NUMBER: _ClassVar[int]
    REJECTION_REASON_FIELD_NUMBER: _ClassVar[int]
    COMMENTS_FIELD_NUMBER: _ClassVar[int]
    ML_CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    ML_MODEL_VERSION_FIELD_NUMBER: _ClassVar[int]
    AUTO_APPROVED_FIELD_NUMBER: _ClassVar[int]
    plan_id: str
    decision: Decision
    approved_by: str
    approved_at: _timestamp_pb2.Timestamp
    rejection_reason: str
    comments: str
    ml_confidence: float
    ml_model_version: str
    auto_approved: bool
    def __init__(self, plan_id: _Optional[str] = ..., decision: _Optional[_Union[Decision, str]] = ..., approved_by: _Optional[str] = ..., approved_at: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., rejection_reason: _Optional[str] = ..., comments: _Optional[str] = ..., ml_confidence: _Optional[float] = ..., ml_model_version: _Optional[str] = ..., auto_approved: bool = ...) -> None: ...

class ApprovalResponse(_message.Message):
    __slots__ = ("plan_id", "intent_id", "decision", "approved_by", "approved_at", "rejection_reason", "cognitive_plan")
    PLAN_ID_FIELD_NUMBER: _ClassVar[int]
    INTENT_ID_FIELD_NUMBER: _ClassVar[int]
    DECISION_FIELD_NUMBER: _ClassVar[int]
    APPROVED_BY_FIELD_NUMBER: _ClassVar[int]
    APPROVED_AT_FIELD_NUMBER: _ClassVar[int]
    REJECTION_REASON_FIELD_NUMBER: _ClassVar[int]
    COGNITIVE_PLAN_FIELD_NUMBER: _ClassVar[int]
    plan_id: str
    intent_id: str
    decision: Decision
    approved_by: str
    approved_at: _timestamp_pb2.Timestamp
    rejection_reason: str
    cognitive_plan: _struct_pb2.Struct
    def __init__(self, plan_id: _Optional[str] = ..., intent_id: _Optional[str] = ..., decision: _Optional[_Union[Decision, str]] = ..., approved_by: _Optional[str] = ..., approved_at: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., rejection_reason: _Optional[str] = ..., cognitive_plan: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ...) -> None: ...
