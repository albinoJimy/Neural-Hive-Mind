import pytest
import httpx
import grpc
from temporalio.client import Client as TemporalClient


@pytest.fixture(scope="session")
async def gateway_client(port_forward_manager):
    async with httpx.AsyncClient(
        base_url=f"http://{port_forward_manager['gateway']}",
        timeout=30.0,
    ) as client:
        yield client


@pytest.fixture(scope="session")
async def orchestrator_client(port_forward_manager):
    async with httpx.AsyncClient(
        base_url=f"http://{port_forward_manager['orchestrator']}",
        timeout=30.0,
    ) as client:
        yield client


@pytest.fixture(scope="session")
async def service_registry_grpc_client(k8s_service_endpoints):
    channel = grpc.aio.insecure_channel(k8s_service_endpoints["service_registry"])
    # Placeholder stub to be replaced with actual generated stub when available
    yield channel
    await channel.close()


@pytest.fixture(scope="session")
async def temporal_client(k8s_service_endpoints):
    client = await TemporalClient.connect(k8s_service_endpoints["temporal"], namespace="neural-hive-mind")
    try:
        yield client
    finally:
        await client.close()
