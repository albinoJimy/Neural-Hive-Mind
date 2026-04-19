"""Testes de integração com service registry."""

import pytest
from src.clients.engineering_service_registry_client import (
    EngineeringServiceRegistryClient,
)
from src.proto import service_registry_pb2


@pytest.mark.asyncio()
async def test_documentation_generation_registration():
    """Testa registro do documentation-generation no service registry."""
    client = EngineeringServiceRegistryClient(
        "documentation-generation",
        service_registry_pb2.DOCUMENTATION_GENERATION,
    )

    initialized = await client.initialize()
    assert initialized is True

    agent_id = await client.register(
        capabilities=[
            "readme_generation",
            "api_docs",
            "markdown_generation",
            "mermaid_rendering",
            "architecture_docs",
        ],
        metadata={
            "kafka_consumer": "architecture_plan_consumer",
            "version": "1.0.0",
        },
    )
    assert agent_id is not None
    assert client._registered is True

    await client.close()


@pytest.mark.asyncio()
async def test_documentation_generation_heartbeat():
    """Testa envio de heartbeat do documentation-generation."""
    client = EngineeringServiceRegistryClient(
        "documentation-generation",
        service_registry_pb2.DOCUMENTATION_GENERATION,
    )

    initialized = await client.initialize()
    assert initialized is True

    agent_id = await client.register(
        capabilities=[
            "readme_generation",
            "api_docs",
            "markdown_generation",
        ]
    )
    assert agent_id is not None

    result = await client.send_heartbeat(
        metrics={
            "success_rate": 0.92,
            "total_executions": 50,
            "failed_executions": 4,
        }
    )
    assert result is True

    await client.close()
