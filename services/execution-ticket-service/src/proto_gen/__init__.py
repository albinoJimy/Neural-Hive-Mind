"""Stubs gerados do Protocol Buffer para Ticket Service."""

from .ticket_service_pb2 import (
    GetTicketRequest,
    GetTicketResponse,
    ListTicketsRequest,
    ListTicketsResponse,
    UpdateTicketStatusRequest,
    UpdateTicketStatusResponse,
    GenerateTokenRequest,
    GenerateTokenResponse,
    ExecutionTicketProto,
)
from .ticket_service_pb2_grpc import (
    TicketServiceServicer,
    TicketServiceStub,
    add_TicketServiceServicer_to_server,
)

__all__ = [
    'GetTicketRequest',
    'GetTicketResponse',
    'ListTicketsRequest',
    'ListTicketsResponse',
    'UpdateTicketStatusRequest',
    'UpdateTicketStatusResponse',
    'GenerateTokenRequest',
    'GenerateTokenResponse',
    'ExecutionTicketProto',
    'TicketServiceServicer',
    'TicketServiceStub',
    'add_TicketServiceServicer_to_server',
]
