"""Generated Protocol Buffer files for Orchestrator Dynamic gRPC services."""

from .orchestrator_strategic_pb2 import (
    AdjustPrioritiesRequest,
    AdjustPrioritiesResponse,
    RebalanceResourcesRequest,
    RebalanceResourcesResponse,
    ResourceAllocation,
    WorkflowRebalanceResult,
    PauseWorkflowRequest,
    PauseWorkflowResponse,
    ResumeWorkflowRequest,
    ResumeWorkflowResponse,
    TriggerReplanningRequest,
    TriggerReplanningResponse,
    ReplanningTriggerType,
    GetWorkflowStatusRequest,
    GetWorkflowStatusResponse,
    WorkflowState,
    TicketSummary,
    WorkflowEvent,
)

from .orchestrator_strategic_pb2_grpc import (
    OrchestratorStrategicServicer,
    OrchestratorStrategicStub,
    add_OrchestratorStrategicServicer_to_server,
)

__all__ = [
    # Request/Response messages
    'AdjustPrioritiesRequest',
    'AdjustPrioritiesResponse',
    'RebalanceResourcesRequest',
    'RebalanceResourcesResponse',
    'ResourceAllocation',
    'WorkflowRebalanceResult',
    'PauseWorkflowRequest',
    'PauseWorkflowResponse',
    'ResumeWorkflowRequest',
    'ResumeWorkflowResponse',
    'TriggerReplanningRequest',
    'TriggerReplanningResponse',
    'GetWorkflowStatusRequest',
    'GetWorkflowStatusResponse',
    'TicketSummary',
    'WorkflowEvent',
    # Enums
    'ReplanningTriggerType',
    'WorkflowState',
    # gRPC
    'OrchestratorStrategicServicer',
    'OrchestratorStrategicStub',
    'add_OrchestratorStrategicServicer_to_server',
]
