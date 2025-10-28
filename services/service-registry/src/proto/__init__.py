"""Módulo de protobuf gerado para o Service Registry."""

from .service_registry_pb2 import (
    AgentType,
    AgentStatus,
    AgentTelemetry,
    AgentInfo,
    RegisterRequest,
    RegisterResponse,
    HeartbeatRequest,
    HeartbeatResponse,
    DeregisterRequest,
    DeregisterResponse,
    DiscoverRequest,
    DiscoverResponse,
    GetAgentRequest,
    GetAgentResponse,
    ListAgentsRequest,
    ListAgentsResponse,
    WatchAgentsRequest,
    AgentChangeEvent,
)

from .service_registry_pb2_grpc import (
    ServiceRegistryStub,
    ServiceRegistryServicer,
    add_ServiceRegistryServicer_to_server,
)

__all__ = [
    # Enums
    'AgentType',
    'AgentStatus',
    # Messages
    'AgentTelemetry',
    'AgentInfo',
    'RegisterRequest',
    'RegisterResponse',
    'HeartbeatRequest',
    'HeartbeatResponse',
    'DeregisterRequest',
    'DeregisterResponse',
    'DiscoverRequest',
    'DiscoverResponse',
    'GetAgentRequest',
    'GetAgentResponse',
    'ListAgentsRequest',
    'ListAgentsResponse',
    'WatchAgentsRequest',
    'AgentChangeEvent',
    # gRPC
    'ServiceRegistryStub',
    'ServiceRegistryServicer',
    'add_ServiceRegistryServicer_to_server',
]
