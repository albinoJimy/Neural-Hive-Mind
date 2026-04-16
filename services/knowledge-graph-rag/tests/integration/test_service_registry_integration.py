"""Testes de integração com service registry."""

import pytest

from knowledge_graph_rag.clients.engineering_service_registry_client import (
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
async def test_knowledge_graph_rag_registration():
    """Testa registro do knowledge-graph-rag no service registry."""
    client = EngineeringServiceRegistryClient(
        "knowledge-graph-rag",
        service_registry_pb2.KNOWLEDGE_GRAPH_RAG,
    )

    initialized = await client.initialize()
    assert initialized is True

    agent_id = await client.register(
        capabilities=[
            "rag_query",
            "contextual_retrieval",
            "template_indexing",
            "code_indexing",
        ],
        metadata={
            "neo4j": "enabled",
            "qdrant": "enabled",
            "version": "1.0.0",
        },
    )
    assert agent_id is not None
    assert client._registered is True

    await client.close()


@pytest.mark.asyncio
async def test_knowledge_graph_rag_heartbeat():
    """Testa envio de heartbeat do knowledge-graph-rag."""
    client = EngineeringServiceRegistryClient(
        "knowledge-graph-rag",
        service_registry_pb2.KNOWLEDGE_GRAPH_RAG,
    )

    initialized = await client.initialize()
    assert initialized is True

    agent_id = await client.register(
        capabilities=[
            "rag_query",
            "contextual_retrieval",
        ]
    )
    assert agent_id is not None

    result = await client.send_heartbeat(
        metrics={
            "success_rate": 0.88,
            "total_executions": 200,
            "failed_executions": 24,
        }
    )
    assert result is True

    await client.close()
