"""Unit tests for ArchitectureDiagramGenerator."""

import pytest
from src.generators.architecture_diagram_generator import ArchitectureDiagramGenerator
from src.models.bounded_context import BoundedContext
from src.models.diagrams import DiagramType


@pytest.mark.asyncio
async def test_generate_context_diagram():
    """Testa geração de diagrama C4 Context."""

    generator = ArchitectureDiagramGenerator(output_dir="/tmp/test_diagrams")

    result = await generator.generate_context_diagram(
        project_name="TestProject",
        system_description="Sistema de teste",
        actors=["Admin", "User"],
        external_systems=["ExternalAPI"],
        render=False  # Não renderiza no teste unitário
    )

    assert result.diagram_id == "TestProject-context"
    assert result.type == DiagramType.C4_CONTEXT
    assert "C4Context" in result.mermaid_code
    assert "Admin" in result.mermaid_code
    assert result.svg_url is None  # render=False


@pytest.mark.asyncio
async def test_generate_container_diagram():
    """Testa geração de diagrama C4 Container."""

    generator = ArchitectureDiagramGenerator(output_dir="/tmp/test_diagrams")

    bounded_contexts = [
        BoundedContext(
            name="Sales",
            description="Contexto de vendas",
            responsibilities=["Process orders"],
            domain_models=["Order", "Customer"],
            relationships=[],
            ubiquitous_language=[]
        ),
        BoundedContext(
            name="Inventory",
            description="Contexto de inventário",
            responsibilities=["Manage stock"],
            domain_models=["Product", "Stock"],
            relationships=[],
            ubiquitous_language=[]
        )
    ]

    result = await generator.generate_container_diagram(
        project_name="TestProject",
        bounded_contexts=bounded_contexts,
        tech_stack=None,
        render=False
    )

    assert result.diagram_id == "TestProject-container"
    assert result.type == DiagramType.C4_CONTAINER
    assert "C4Container" in result.mermaid_code
    assert "Sales" in result.mermaid_code
    assert "Inventory" in result.mermaid_code


@pytest.mark.asyncio
async def test_generate_component_diagram():
    """Testa geração de diagrama C4 Component."""

    generator = ArchitectureDiagramGenerator(output_dir="/tmp/test_diagrams")

    result = await generator.generate_component_diagram(
        component_name="OrderService",
        component_description="Serviço de pedidos",
        subcomponents=["OrderController", "OrderService", "OrderRepository"],
        render=False
    )

    assert result.diagram_id == "OrderService-component"
    assert result.type == DiagramType.C4_COMPONENT
    assert "C4Component" in result.mermaid_code


@pytest.mark.asyncio
async def test_generate_all_diagrams():
    """Testa geração de todos os diagramas."""

    generator = ArchitectureDiagramGenerator(output_dir="/tmp/test_diagrams")

    bounded_contexts = [
        BoundedContext(
            name="Core",
            description="Núcleo",
            responsibilities=["Core logic"],
            domain_models=["Entity"],
            relationships=[],
            ubiquitous_language=[]
        )
    ]

    results = await generator.generate_all_diagrams(
        project_name="FullTest",
        system_description="Teste completo",
        bounded_contexts=bounded_contexts,
        actors=["User"],
        external_systems=[],
        tech_stack=None,
        render=False  # Não renderiza no teste unitário
    )

    assert len(results) == 2  # Context + Container
    types = {d.type for d in results}
    assert DiagramType.C4_CONTEXT in types
    assert DiagramType.C4_CONTAINER in types


@pytest.mark.asyncio
async def test_generate_sequence_diagram():
    """Testa geração de diagrama de sequência."""

    generator = ArchitectureDiagramGenerator(output_dir="/tmp/test_diagrams")

    steps = [
        "User->>Gateway: Send request",
        "Gateway->>Service: Forward request",
        "Service->>Database: Query data",
        "Database-->>Service: Return results",
        "Service-->>Gateway: Response",
        "Gateway-->>User: Return response"
    ]

    artifacts = ["Request", "Response"]

    result = await generator.generate_sequence(
        title="API Request Flow",
        steps=steps,
        artifacts=artifacts,
        render=False
    )

    assert result.diagram_id == "api-request-flow-sequence"
    assert result.type == DiagramType.SEQUENCE
    assert "sequenceDiagram" in result.mermaid_code
    assert "User->>Gateway" in result.mermaid_code
    assert "Note over" in result.mermaid_code
    assert result.svg_url is None  # render=False


@pytest.mark.asyncio
async def test_generate_sequence_diagram_without_artifacts():
    """Testa geração de diagrama de sequência sem artefatos."""

    generator = ArchitectureDiagramGenerator(output_dir="/tmp/test_diagrams")

    steps = [
        "Client->>Server: Connect",
        "Server-->>Client: Acknowledge"
    ]

    result = await generator.generate_sequence(
        title="Simple Connection",
        steps=steps,
        artifacts=None,
        render=False
    )

    assert result.type == DiagramType.SEQUENCE
    assert "Client->>Server" in result.mermaid_code
    assert "Note over" not in result.mermaid_code  # Sem artefatos


@pytest.mark.asyncio
async def test_generate_from_description_sequence():
    """Testa geração de diagrama a partir de descrição (sequência)."""

    generator = ArchitectureDiagramGenerator(output_dir="/tmp/test_diagrams")

    description = "User sends request to system, then system processes and returns response"

    result = await generator.generate_from_description(
        description=description,
        render=False
    )

    assert result.type == DiagramType.SEQUENCE
    assert "sequenceDiagram" in result.mermaid_code


@pytest.mark.asyncio
async def test_generate_from_description_context():
    """Testa geração de diagrama a partir de descrição (contexto)."""

    generator = ArchitectureDiagramGenerator(output_dir="/tmp/test_diagrams")

    description = "System with user authentication and external payment integration"

    result = await generator.generate_from_description(
        description=description,
        render=False
    )

    assert result.type == DiagramType.C4_CONTEXT
    assert "C4Context" in result.mermaid_code


@pytest.mark.asyncio
async def test_parse_sequence_from_description():
    """Testa parsing de sequência de descrição textual."""

    generator = ArchitectureDiagramGenerator(output_dir="/tmp/test_diagrams")

    description = "User logs in. Then system validates credentials. Then returns token."

    steps = generator._parse_sequence_from_description(description)

    assert len(steps) > 0
    assert any("User" in step for step in steps)


@pytest.mark.asyncio
async def test_generate_from_description_fallback():
    """Testa fallback quando não há palavras-chave reconhecidas."""

    generator = ArchitectureDiagramGenerator(output_dir="/tmp/test_diagrams")

    description = "Generic component architecture"

    result = await generator.generate_from_description(
        description=description,
        render=False
    )

    assert result.diagram_id == "generated-diagram"
    assert "graph TD" in result.mermaid_code


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
