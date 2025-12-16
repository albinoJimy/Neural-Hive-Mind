import os

import grpc
import pytest

from tests.e2e.fixtures.vault_spire_setup import (
    spiffe_manager,
    require_real_env,
    build_test_settings,
)
from src.clients.service_registry_client import ServiceRegistryClient
from src.clients.execution_ticket_client import ExecutionTicketClient
from src.clients import execution_ticket_client as etc_module

REAL_E2E = os.getenv("RUN_VAULT_SPIFFE_E2E", "").lower() == "true"
pytestmark = pytest.mark.skipif(not REAL_E2E, reason="RUN_VAULT_SPIFFE_E2E not enabled")


@pytest.mark.asyncio
async def test_fetch_jwt_svid(spiffe_manager):
    """Obtém JWT-SVID real via SPIRE agent."""
    require_real_env()
    audience = os.getenv('SPIFFE_JWT_AUDIENCE', 'vault.neural-hive.local')
    jwt_svid = await spiffe_manager.fetch_jwt_svid(audience=audience)
    assert jwt_svid.token
    assert audience in jwt_svid.token or jwt_svid.spiffe_id


@pytest.mark.asyncio
async def test_service_registry_call_with_jwt(spiffe_manager):
    """Chamada gRPC ao Service Registry com JWT-SVID."""
    require_real_env()
    config = build_test_settings()
    config.spiffe_enabled = True
    config.spiffe_fallback_allowed = False
    config.service_registry_host = os.getenv('SERVICE_REGISTRY_HOST', config.service_registry_host)
    config.service_registry_port = int(os.getenv('SERVICE_REGISTRY_PORT', config.service_registry_port))

    client = ServiceRegistryClient(config, spiffe_manager=spiffe_manager)
    try:
        await client.initialize()
        agents = await client.discover_agents(capabilities=['python'], filters={}, max_results=1)
        assert isinstance(agents, list)
    except grpc.RpcError as e:
        if e.code() in (grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED):
            pytest.skip(f"Service Registry indisponível: {e}")
        raise
    finally:
        try:
            await client.close()
        except Exception:
            pass


@pytest.mark.asyncio
async def test_execution_ticket_call_with_jwt(spiffe_manager):
    """Chamada gRPC ao Execution Ticket Service autenticada com JWT-SVID."""
    require_real_env()
    config = build_test_settings()
    config.spiffe_enabled = True
    config.execution_ticket_service_host = os.getenv(
        'EXECUTION_TICKET_HOST',
        getattr(config, 'execution_ticket_service_host', 'execution-ticket-service.neural-hive-execution.svc.cluster.local')
    )
    config.execution_ticket_service_port = int(os.getenv('EXECUTION_TICKET_PORT', getattr(config, 'execution_ticket_service_port', 50052)))

    client = ExecutionTicketClient(config, spiffe_manager=spiffe_manager)
    try:
        await client.initialize()
        response = await client.list_tickets(limit=1)
        assert 'tickets' in response
    except grpc.RpcError as e:
        if e.code() in (grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED):
            pytest.skip(f"Execution Ticket Service indisponível: {e}")
        raise
    finally:
        try:
            await client.close()
        except Exception:
            pass


@pytest.mark.asyncio
async def test_invalid_jwt_returns_unauthenticated():
    """JWT inválido deve retornar UNAUTHENTICATED/PERMISSION_DENIED."""
    require_real_env()
    config = build_test_settings()
    config.spiffe_enabled = False
    config.execution_ticket_service_host = os.getenv(
        'EXECUTION_TICKET_HOST',
        getattr(config, 'execution_ticket_service_host', 'execution-ticket-service.neural-hive-execution.svc.cluster.local')
    )
    config.execution_ticket_service_port = int(os.getenv('EXECUTION_TICKET_PORT', getattr(config, 'execution_ticket_service_port', 50052)))

    client = ExecutionTicketClient(config, spiffe_manager=None)
    await client.initialize()

    request = etc_module.ticket_service_pb2.ListTicketsRequest(limit=1)

    try:
        with pytest.raises(grpc.RpcError) as rpc_error:
            await client.stub.ListTickets(
                request,
                metadata=[('authorization', 'Bearer invalid')],
                timeout=client.timeout_seconds
            )
        assert rpc_error.value.code() in (
            grpc.StatusCode.UNAUTHENTICATED,
            grpc.StatusCode.PERMISSION_DENIED
        )
    except grpc.RpcError as e:
        if e.code() in (grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED):
            pytest.skip(f"Execution Ticket Service indisponível: {e}")
        raise
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_fallback_to_unauthenticated_when_allowed():
    """Fallback para modo não autenticado quando SPIFFE indisponível e fallback permitido."""
    require_real_env()
    config = build_test_settings()
    config.spiffe_enabled = True
    config.spiffe_fallback_allowed = True
    config.execution_ticket_service_host = os.getenv(
        'EXECUTION_TICKET_HOST',
        getattr(config, 'execution_ticket_service_host', 'execution-ticket-service.neural-hive-execution.svc.cluster.local')
    )
    config.execution_ticket_service_port = int(os.getenv('EXECUTION_TICKET_PORT', getattr(config, 'execution_ticket_service_port', 50052)))

    client = ExecutionTicketClient(config, spiffe_manager=None)
    try:
        await client.initialize()
        response = await client.list_tickets(limit=1)
        assert 'tickets' in response
    except grpc.RpcError as e:
        if e.code() in (grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED):
            pytest.skip(f"Execution Ticket Service indisponível: {e}")
        raise
    finally:
        await client.close()
