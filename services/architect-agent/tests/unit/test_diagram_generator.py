"""Unit tests for ArchitectureDiagramGenerator."""

from unittest.mock import AsyncMock, Mock

import pytest
from neural_hive_llm import LLMResponse, LLMProvider
from src.generators.architecture_diagram_generator import ArchitectureDiagramGenerator
from src.models.bounded_context import BoundedContext
from src.models.diagrams import DiagramType


@pytest.fixture
def mock_llm_client():
    """Mock do cliente LLM usando neural_hive_llm."""
    client = Mock()
    client.start = AsyncMock()
    # Resposta padrão para generate_from_description
    client.generate = AsyncMock(
        return_value=LLMResponse(
            text="sequenceDiagram\n    User->>System: Request\n    System-->>User: Response",
            prompt_tokens=20,
            completion_tokens=30,
            total_tokens=50,
            model="gpt-4",
            provider=LLMProvider.OPENAI,
            latency_ms=100,
        )
    )
    return client


@pytest.mark.asyncio
async def test_generate_context_diagram(mock_llm_client):
    """Testa geração de diagrama C4 Context."""

    generator = ArchitectureDiagramGenerator(
        llm_client=mock_llm_client, output_dir="/tmp/test_diagrams"
    )

    result = await generator.generate_context_diagram(
        project_name="TestProject",
        system_description="Sistema de teste",
        actors=["Admin", "User"],
        external_systems=["ExternalAPI"],
        render=False,  # Não renderiza no teste unitário
    )

    assert result.diagram_id == "TestProject-context"
    assert result.type == DiagramType.C4_CONTEXT
    assert "C4Context" in result.mermaid_code
    assert "Admin" in result.mermaid_code
    assert result.svg_url is None  # render=False


@pytest.mark.asyncio
async def test_generate_container_diagram(mock_llm_client):
    """Testa geração de diagrama C4 Container."""

    generator = ArchitectureDiagramGenerator(
        llm_client=mock_llm_client, output_dir="/tmp/test_diagrams"
    )

    bounded_contexts = [
        BoundedContext(
            name="Sales",
            description="Contexto de vendas",
            responsibilities=["Process orders"],
            domain_models=["Order", "Customer"],
            relationships=[],
            ubiquitous_language=[],
        ),
        BoundedContext(
            name="Inventory",
            description="Contexto de inventário",
            responsibilities=["Manage stock"],
            domain_models=["Product", "Stock"],
            relationships=[],
            ubiquitous_language=[],
        ),
    ]

    result = await generator.generate_container_diagram(
        project_name="TestProject", bounded_contexts=bounded_contexts, tech_stack=None, render=False
    )

    assert result.diagram_id == "TestProject-container"
    assert result.type == DiagramType.C4_CONTAINER
    assert "C4Container" in result.mermaid_code
    assert "Sales" in result.mermaid_code
    assert "Inventory" in result.mermaid_code


@pytest.mark.asyncio
async def test_generate_component_diagram(mock_llm_client):
    """Testa geração de diagrama C4 Component."""

    generator = ArchitectureDiagramGenerator(
        llm_client=mock_llm_client, output_dir="/tmp/test_diagrams"
    )

    result = await generator.generate_component_diagram(
        component_name="OrderService",
        component_description="Serviço de pedidos",
        subcomponents=["OrderController", "OrderService", "OrderRepository"],
        render=False,
    )

    assert result.diagram_id == "OrderService-component"
    assert result.type == DiagramType.C4_COMPONENT
    assert "C4Component" in result.mermaid_code


@pytest.mark.asyncio
async def test_generate_all_diagrams(mock_llm_client):
    """Testa geração de todos os diagramas."""

    generator = ArchitectureDiagramGenerator(
        llm_client=mock_llm_client, output_dir="/tmp/test_diagrams"
    )

    bounded_contexts = [
        BoundedContext(
            name="Core",
            description="Núcleo",
            responsibilities=["Core logic"],
            domain_models=["Entity"],
            relationships=[],
            ubiquitous_language=[],
        )
    ]

    results = await generator.generate_all_diagrams(
        project_name="FullTest",
        system_description="Teste completo",
        bounded_contexts=bounded_contexts,
        actors=["User"],
        external_systems=[],
        tech_stack=None,
        render=False,  # Não renderiza no teste unitário
    )

    assert len(results) == 2  # Context + Container
    types = {d.type for d in results}
    assert DiagramType.C4_CONTEXT in types
    assert DiagramType.C4_CONTAINER in types


@pytest.mark.asyncio
async def test_generate_sequence_diagram(mock_llm_client):
    """Testa geração de diagrama de sequência."""

    generator = ArchitectureDiagramGenerator(
        llm_client=mock_llm_client, output_dir="/tmp/test_diagrams"
    )

    steps = [
        "User->>Gateway: Send request",
        "Gateway->>Service: Forward request",
        "Service->>Database: Query data",
        "Database-->>Service: Return results",
        "Service-->>Gateway: Response",
        "Gateway-->>User: Return response",
    ]

    artifacts = ["Request", "Response"]

    result = await generator.generate_sequence(
        title="API Request Flow", steps=steps, artifacts=artifacts, render=False
    )

    assert result.diagram_id == "api-request-flow-sequence"
    assert result.type == DiagramType.SEQUENCE
    assert "sequenceDiagram" in result.mermaid_code
    assert "User->>Gateway" in result.mermaid_code
    assert "Note over" in result.mermaid_code
    assert result.svg_url is None  # render=False


@pytest.mark.asyncio
async def test_generate_sequence_diagram_without_artifacts(mock_llm_client):
    """Testa geração de diagrama de sequência sem artefatos."""

    generator = ArchitectureDiagramGenerator(
        llm_client=mock_llm_client, output_dir="/tmp/test_diagrams"
    )

    steps = ["Client->>Server: Connect", "Server-->>Client: Acknowledge"]

    result = await generator.generate_sequence(
        title="Simple Connection", steps=steps, artifacts=None, render=False
    )

    assert result.type == DiagramType.SEQUENCE
    assert "Client->>Server" in result.mermaid_code
    assert "Note over" not in result.mermaid_code  # Sem artefatos


@pytest.mark.asyncio
async def test_generate_sequence_with_mermaid_code(mock_llm_client):
    """Testa geração de sequência com mermaid_code já fornecido."""

    generator = ArchitectureDiagramGenerator(
        llm_client=mock_llm_client, output_dir="/tmp/test_diagrams"
    )

    mermaid_code = "sequenceDiagram\n    A->>B: Test"

    result = await generator.generate_sequence(
        title="Test", steps=None, mermaid_code=mermaid_code, render=False
    )

    assert result.type == DiagramType.SEQUENCE
    assert result.mermaid_code == mermaid_code


@pytest.mark.asyncio
async def test_generate_from_description_uses_llm(mock_llm_client):
    """Testa que generate_from_description usa LLM."""

    generator = ArchitectureDiagramGenerator(
        llm_client=mock_llm_client, output_dir="/tmp/test_diagrams"
    )

    description = "User sends request to system, then system processes and returns response"

    result = await generator.generate_from_description(description=description, render=False)

    # Verificar que o LLM foi chamado
    mock_llm_client.generate.assert_called_once()

    # Verificar argumentos da chamada
    call_args = mock_llm_client.generate.call_args
    assert "sequenceDiagram" in call_args[1]["prompt"]

    # Verificar resultado
    assert result.type == DiagramType.SEQUENCE
    assert "sequenceDiagram" in result.mermaid_code


@pytest.mark.asyncio
async def test_generate_from_description_cleans_markdown(mock_llm_client):
    """Testa que generate_from_description limpa markdown do response."""

    # Mock com markdown code blocks
    mock_llm_client.generate = AsyncMock(
        return_value=LLMResponse(
            text="```mermaid\nsequenceDiagram\n    A->>B: Test\n```",
            prompt_tokens=20,
            completion_tokens=20,
            total_tokens=40,
            model="gpt-4",
            provider=LLMProvider.OPENAI,
            latency_ms=100,
        )
    )

    generator = ArchitectureDiagramGenerator(
        llm_client=mock_llm_client, output_dir="/tmp/test_diagrams"
    )

    result = await generator.generate_from_description(description="Test", render=False)

    # Verificar que markdown foi limpo
    assert not result.mermaid_code.startswith("```")
    assert "sequenceDiagram" in result.mermaid_code


@pytest.mark.asyncio
async def test_mermaid_renderer_render_to_svg(monkeypatch):
    """Testa MermaidRenderer.render_to_svg (mockado)."""

    from src.generators.mermaid_renderer import MermaidRenderer

    # Mock subprocess.run
    async def mock_run(*args, **kwargs):
        class Result:
            returncode = 0

        return Result()

    import subprocess

    monkeypatch.setattr(subprocess, "run", mock_run)

    renderer = MermaidRenderer()

    # Mock write_text
    import tempfile

    original_mkdtemp = tempfile.mkdtemp

    def mock_mkdtemp(*args, **kwargs):
        return "/tmp/test_mermaid"

    monkeypatch.setattr(tempfile, "mkdtemp", mock_mkdtemp)

    # Teste básico sem renderização real
    assert renderer._mmdc_command == "mmdc"
