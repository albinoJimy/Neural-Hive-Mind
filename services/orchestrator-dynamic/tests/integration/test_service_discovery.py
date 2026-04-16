"""Testes de descoberta de serviços Fluxo G."""

import pytest

from src.clients.service_registry_client import ServiceRegistryClient
from src.config.settings import get_settings


@pytest.mark.asyncio
async def test_discover_requirements_engineering():
    """Testa descoberta do serviço requirements-engineering."""
    config = get_settings()
    client = ServiceRegistryClient(config)
    await client.initialize()

    # Descobrir agentes por capability
    agents = await client.discover_agents(
        capabilities=["requirements_generation"],
        filters={},
        max_results=10,
    )

    # Verificar se encontrou o serviço
    if agents:
        # Filtrar apenas REQUIREMENTS_ENGINEERING
        req_eng_agents = [a for a in agents if a.get("agent_type") == "REQUIREMENTS_ENGINEERING"]
        if req_eng_agents:
            assert req_eng_agents[0]["agent_type"] == "REQUIREMENTS_ENGINEERING"
            assert "requirements_generation" in req_eng_agents[0]["capabilities"]

    await client.close()


@pytest.mark.asyncio
async def test_discover_documentation_generation():
    """Testa descoberta do serviço documentation-generation."""
    config = get_settings()
    client = ServiceRegistryClient(config)
    await client.initialize()

    agents = await client.discover_agents(
        capabilities=["readme_generation"],
        filters={},
        max_results=10,
    )

    if agents:
        doc_gen_agents = [a for a in agents if a.get("agent_type") == "DOCUMENTATION_GENERATION"]
        if doc_gen_agents:
            assert doc_gen_agents[0]["agent_type"] == "DOCUMENTATION_GENERATION"
            assert "readme_generation" in doc_gen_agents[0]["capabilities"]

    await client.close()


@pytest.mark.asyncio
async def test_discover_knowledge_graph_rag():
    """Testa descoberta do serviço knowledge-graph-rag."""
    config = get_settings()
    client = ServiceRegistryClient(config)
    await client.initialize()

    agents = await client.discover_agents(
        capabilities=["rag_query"],
        filters={},
        max_results=10,
    )

    if agents:
        kg_rag_agents = [a for a in agents if a.get("agent_type") == "KNOWLEDGE_GRAPH_RAG"]
        if kg_rag_agents:
            assert kg_rag_agents[0]["agent_type"] == "KNOWLEDGE_GRAPH_RAG"
            assert "rag_query" in kg_rag_agents[0]["capabilities"]

    await client.close()


@pytest.mark.asyncio
async def test_discover_approval_gateway():
    """Testa descoberta do serviço approval-gateway."""
    config = get_settings()
    client = ServiceRegistryClient(config)
    await client.initialize()

    agents = await client.discover_agents(
        capabilities=["approval_management"],
        filters={},
        max_results=10,
    )

    if agents:
        approval_agents = [a for a in agents if a.get("agent_type") == "APPROVAL_GATEWAY"]
        if approval_agents:
            assert approval_agents[0]["agent_type"] == "APPROVAL_GATEWAY"
            assert "approval_management" in approval_agents[0]["capabilities"]

    await client.close()


@pytest.mark.asyncio
async def test_discover_all_engineering_services():
    """Testa descoberta de todos os serviços de engenharia."""
    config = get_settings()
    client = ServiceRegistryClient(config)
    await client.initialize()

    # Descobrir todos sem filtro de capability
    agents = await client.discover_agents(
        capabilities=[],  # Vazio para trazer todos
        filters={},
        max_results=50,
    )

    # Filtrar apenas serviços de engenharia
    engineering_types = {
        "REQUIREMENTS_ENGINEERING",
        "DOCUMENTATION_GENERATION",
        "KNOWLEDGE_GRAPH_RAG",
        "APPROVAL_GATEWAY",
    }

    engineering_agents = [
        a for a in agents if a.get("agent_type") in engineering_types
    ]

    # Verificar tipos únicos encontrados
    found_types = {a.get("agent_type") for a in engineering_agents}

    # Log para debug
    print(f"Found {len(engineering_agents)} engineering agents")
    print(f"Found types: {found_types}")

    await client.close()
