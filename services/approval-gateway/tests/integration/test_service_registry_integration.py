"""Testes de integração com service registry."""

import pytest
from unittest.mock import Mock, AsyncMock, patch
import sys


# Mock service_registry_pb2 antes de importar o cliente
mock_pb2 = Mock()
mock_pb2.APPROVAL_GATEWAY = 6
mock_pb2.AgentType = Mock()
sys.modules['proto'] = Mock()
sys.modules['proto'].service_registry_pb2 = mock_pb2
sys.modules['proto'].service_registry_pb2_grpc = Mock()

from src.clients.engineering_service_registry_client import (
    EngineeringServiceRegistryClient,
)


@pytest.mark.asyncio
async def test_approval_gateway_registration():
    """Testa registro do approval-gateway no service registry."""
    client = EngineeringServiceRegistryClient(
        "approval-gateway",
        mock_pb2.APPROVAL_GATEWAY,
    )

    # Mock dos métodos do cliente
    with patch.object(client, 'initialize', new_callable=AsyncMock, return_value=True):
        with patch.object(client, 'register', new_callable=AsyncMock, return_value="agent-123"):
            with patch.object(client, 'close', new_callable=AsyncMock):
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
                assert agent_id == "agent-123"

                await client.close()


@pytest.mark.asyncio
async def test_approval_gateway_heartbeat():
    """Testa envio de heartbeat do approval-gateway."""
    client = EngineeringServiceRegistryClient(
        "approval-gateway",
        mock_pb2.APPROVAL_GATEWAY,
    )

    # Mock dos métodos do cliente
    with patch.object(client, 'initialize', new_callable=AsyncMock, return_value=True):
        with patch.object(client, 'register', new_callable=AsyncMock, return_value="agent-456"):
            with patch.object(client, 'send_heartbeat', new_callable=AsyncMock, return_value=True):
                with patch.object(client, 'close', new_callable=AsyncMock):
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
