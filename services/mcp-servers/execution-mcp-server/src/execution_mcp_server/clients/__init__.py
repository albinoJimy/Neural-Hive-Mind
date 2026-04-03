"""Clients para integração com serviços externos."""

from .grpc_client import ExecutionTicketClient, get_grpc_client

__all__ = ["ExecutionTicketClient", "get_grpc_client"]
