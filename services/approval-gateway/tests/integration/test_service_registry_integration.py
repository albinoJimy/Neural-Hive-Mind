"""Testes de integração com service registry."""

import pytest

from src.clients.engineering_service_registry_client import (
    EngineeringServiceRegistryClient,
)

# Import proto
import sys
from pathlib import Path

# Adicionar caminho para o service-registry
sr_path = Path(__file__).parent.parent.parent.parent.parent / "service-registry" / "src"
if str(sr_path) not in sys.path:
    sys.path.insert(0, str(sr_path))

from proto import service_registry_pb2


@pytest.mark.asyncio
async def test_approval_gateway_registration():
    """Testa registro do approval-gateway no service registry."""
    client = EngineeringServiceRegistryClient(
        "approval-gateway",
        service_registry_pb2.APPROVAL_GATEWAY,
    )

    initialized = await client.initialize()
    assert initialized is True

    agent_id = await client.register(
        capabilities=[
            "approval_management",
            "artifact_storage",
            "jwt_tokens",
            "notifications",
        ],
        metadata={
            "mongodb": "enabled",
            "jwt": "enabled",
            "version": "1.0.0",
        },
    )
    assert agent_id is not None
    assert client._registered is True

    await client.close()


@pytest.mark.asyncio
async def test_approval_gateway_heartbeat():
    """Testa envio de heartbeat do approval-gateway."""
    client = EngineeringServiceRegistryClient(
        "approval-gateway",
        service_registry_pb2.APPROVAL_GATEWAY,
    )

    initialized = await client.initialize()
    assert initialized is True

    agent_id = await client.register(
        capabilities=[
            "approval_management",
            "jwt_tokens",
        ]
    )
    assert agent_id is not None

    result = await client.send_heartbeat(
        metrics={
            "success_rate": 0.99,
            "total_executions": 500,
            "failed_executions": 5,
        }
    )
    assert result is True

    await client.close()
