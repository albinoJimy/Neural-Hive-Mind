"""
Dependency Injection para APIs REST do Queen Agent.

Usa FastAPI Depends() para injetar dependências de forma tipada e testável.
"""

from typing import Any

from fastapi import HTTPException, Request

from ..clients import MongoDBClient
from ..services import ExceptionApprovalService, LeaderElection, LoadBalancer


async def get_mongodb_client(request: Request) -> MongoDBClient:
    """
    Obtém cliente MongoDB do app_state.

    Raises:
        HTTPException: Se cliente não estiver inicializado.
    """
    app_state = request.app.state.app_state

    if not app_state.mongodb_client:
        raise HTTPException(
            status_code=503,
            detail="MongoDB client not initialized",
        )

    return app_state.mongodb_client


async def get_load_balancer(request: Request) -> LoadBalancer:
    """
    Obtém LoadBalancer do app_state.

    Raises:
        HTTPException: Se LoadBalancer não estiver inicializado.
    """
    app_state = request.app.state.app_state

    if not app_state.load_balancer:
        raise HTTPException(
            status_code=503,
            detail="Load balancer not enabled",
        )

    return app_state.load_balancer


async def get_leader_election(request: Request) -> LeaderElection:
    """
    Obtém LeaderElection do app_state.

    Raises:
        HTTPException: Se LeaderElection não estiver inicializado.
    """
    app_state = request.app.state.app_state

    if not app_state.leader_election:
        raise HTTPException(
            status_code=503,
            detail="Leader election not enabled",
        )

    return app_state.leader_election


async def get_exception_service(request: Request) -> ExceptionApprovalService:
    """
    Obtém ExceptionApprovalService do app_state.

    Raises:
        HTTPException: Se serviço não estiver inicializado.
    """
    app_state = request.app.state.app_state

    if not app_state.exception_service:
        raise HTTPException(
            status_code=503,
            detail="Exception approval service not enabled",
        )

    return app_state.exception_service


async def get_mcp_orchestrator(request: Request) -> Any:
    """
    Obtém MCPToolOrchestrator do app_state.

    Raises:
        HTTPException: Se orquestrador não estiver inicializado.
    """
    app_state = request.app.state.app_state

    if not app_state.mcp_orchestrator:
        raise HTTPException(
            status_code=503,
            detail="MCP Orchestrator not available",
        )

    return app_state.mcp_orchestrator


async def get_app_state(request: Request) -> Any:
    """
    Obtém o app_state completo.

    Útil para serviços que não têm dependência específica ainda.
    Pode ser refatorado gradualmente para dependências específicas.
    """
    return request.app.state.app_state


# Dependências compostas podem ser adicionadas aqui
# Exemplo: async def get_decision_engine_with_validations(...)
