"""Testes de integração com service registry."""

import pytest

from src.clients.engineering_service_registry_client import (
    EngineeringServiceRegistryClient,
)
from src.proto import service_registry_pb2


@pytest.mark.asyncio
async def test_requirements_engineering_registration():
    """Testa registro do requirements-engineering no service registry."""
    client = EngineeringServiceRegistryClient(
        "requirements-engineering",
        service_registry_pb2.REQUIREMENTS_ENGINEERING,
    )

    initialized = await client.initialize()
    assert initialized is True

    agent_id = await client.register(
        capabilities=[
            "requirements_generation",
            "user_stories",
            "acceptance_criteria",
            "data_model_design",
        ],
        metadata={
            "kafka_consumer": "cognitive_plan_consumer",
            "kafka_producer": "requirements_producer",
            "version": "1.0.0",
        },
    )
    assert agent_id is not None
    assert client._registered is True

    await client.close()


@pytest.mark.asyncio
async def test_requirements_engineering_heartbeat():
    """Testa envio de heartbeat do requirements-engineering."""
    client = EngineeringServiceRegistryClient(
        "requirements-engineering",
        service_registry_pb2.REQUIREMENTS_ENGINEERING,
    )

    initialized = await client.initialize()
    assert initialized is True

    agent_id = await client.register(
        capabilities=[
            "requirements_generation",
            "user_stories",
            "acceptance_criteria",
            "data_model_design",
        ]
    )
    assert agent_id is not None

    # Testar heartbeat
    result = await client.send_heartbeat(
        metrics={
            "success_rate": 0.95,
            "total_executions": 100,
            "failed_executions": 5,
        }
    )
    assert result is True

    await client.close()
