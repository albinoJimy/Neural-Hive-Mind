import os

import pytest

# Skip se dependências não estão disponíveis
pytest.importorskip("grpc")
pytest.importorskip("neural_hive_security", reason="neural_hive_security not installed")

import grpc

from tests.e2e.fixtures.vault_spire_setup import (
    vault_client,
    spiffe_manager,
    orchestrator_vault_client,
    require_real_env,
    build_test_settings,
)
from src.clients.service_registry_client import ServiceRegistryClient
from src.clients.execution_ticket_client import ExecutionTicketClient

REAL_E2E = os.getenv("RUN_VAULT_SPIFFE_E2E", "").lower() == "true"
pytestmark = pytest.mark.skipif(not REAL_E2E, reason="RUN_VAULT_SPIFFE_E2E not enabled")


@pytest.mark.asyncio
async def test_orchestrator_to_service_registry_jwt_auth(spiffe_manager):
    """Orchestrator -> Service Registry com JWT-SVID."""
    require_real_env()
    config = build_test_settings()
    config.spiffe_enabled = True
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
async def test_worker_to_service_registry_jwt_auth(spiffe_manager):
    """Worker (simulado) -> Service Registry com JWT-SVID."""
    require_real_env()
    config = build_test_settings()
    config.spiffe_enabled = True
    config.service_registry_host = os.getenv('SERVICE_REGISTRY_HOST', config.service_registry_host)
    config.service_registry_port = int(os.getenv('SERVICE_REGISTRY_PORT', config.service_registry_port))

    client = ServiceRegistryClient(config, spiffe_manager=spiffe_manager)
    try:
        await client.initialize()
        agents = await client.discover_agents(capabilities=['deploy'], filters={}, max_results=1)
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
async def test_orchestrator_to_execution_ticket_jwt_auth(spiffe_manager):
    """Orchestrator -> Execution Ticket Service autenticado com JWT-SVID."""
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
async def test_end_to_end_credentials_and_auth(vault_client, orchestrator_vault_client, spiffe_manager):
    """Fluxo ponta-a-ponta: segredos no Vault + autenticação gRPC com JWT-SVID."""
    require_real_env()

    # Vault secrets
    pg_creds = await orchestrator_vault_client.get_postgres_credentials()
    mongo_uri = await orchestrator_vault_client.get_mongodb_uri()
    kafka_creds = await orchestrator_vault_client.get_kafka_credentials()

    assert pg_creds["username"]
    assert mongo_uri
    assert kafka_creds.get("username") is not None or kafka_creds.get("password") is not None

    # JWT-SVID
    jwt_svid = await spiffe_manager.fetch_jwt_svid(
        audience=os.getenv('SPIFFE_JWT_AUDIENCE', 'vault.neural-hive.local')
    )
    assert jwt_svid.token

    # gRPC call com JWT
    config = build_test_settings()
    config.spiffe_enabled = True
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
async def test_token_rotation_tasks(orchestrator_vault_client):
    """Valida chamadas de renovação de token e credenciais."""
    require_real_env()
    await orchestrator_vault_client._renew_vault_token_if_needed()
    await orchestrator_vault_client._renew_postgres_credentials_if_needed()
