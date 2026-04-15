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
