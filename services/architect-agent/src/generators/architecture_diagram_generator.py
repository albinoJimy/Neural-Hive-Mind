"""Architecture diagram generator orchestrator."""

from pathlib import Path
from typing import List, Optional

from src.generators.c4_diagram import C4DiagramGenerator
from src.generators.mermaid_renderer import MermaidRenderer
from src.models.bounded_context import BoundedContext
from src.models.diagrams import Diagram, DiagramType
from src.models.tech_stack import TechStackRecommendation
from src.models.architecture import Component

from structlog import get_logger

logger = get_logger(__name__)


class ArchitectureDiagramGenerator:
    """Orquestra geração de diagramas de arquitetura."""

    def __init__(
        self,
        output_dir: Optional[str] = None,
        mmdc_command: str = "mmdc"
    ):
        """
        Inicializa o gerador.

        Args:
            output_dir: Diretório base para diagramas gerados
            mmdc_command: Comando mermaid-cli
        """
        self._output_dir = Path(output_dir) if output_dir else Path("diagrams")
        self._c4_generator = C4DiagramGenerator()
        self._renderer = MermaidRenderer(mmdc_command)
        self._logger = logger

    async def generate_context_diagram(
        self,
        project_name: str,
        system_description: str,
        actors: List[str],
        external_systems: List[str],
        render: bool = True
    ) -> Diagram:
        """
        Gera diagrama C4 Context.

        Args:
            project_name: Nome do projeto
            system_description: Descrição do sistema
            actors: Lista de atores (usuários)
            external_systems: Lista de sistemas externos
            render: Se True, renderiza para SVG

        Returns:
            Diagram com código Mermaid e caminho SVG (se renderizado)
        """
        self._logger.info("generating_context_diagram", project=project_name)

        mermaid_code = self._c4_generator.generate_context(
            project_name=project_name,
            system_description=system_description,
            actors=actors,
            external_systems=external_systems
        )

        svg_url = None
        if render:
            output_path = self._output_dir / "context"
            svg_url = await self._renderer.render_to_svg(
                mermaid_code,
                str(output_path)
            )

        return Diagram(
            diagram_id=f"{project_name}-context",
            type=DiagramType.C4_CONTEXT,
            title=f"{project_name} - Context Diagram",
            mermaid_code=mermaid_code,
            svg_url=svg_url
        )

    async def generate_container_diagram(
        self,
        project_name: str,
        bounded_contexts: List[BoundedContext],
        tech_stack: Optional[TechStackRecommendation] = None,
        render: bool = True
    ) -> Diagram:
        """
        Gera diagrama C4 Container.

        Args:
            project_name: Nome do projeto
            bounded_contexts: Contextos limitrófes identificados
            tech_stack: Stack tecnológico recomendado
            render: Se True, renderiza para SVG

        Returns:
            Diagram com código Mermaid e caminho SVG
        """
        self._logger.info("generating_container_diagram", project=project_name)

        # Simplificado: usa bounded contexts como containers
        containers = [
            Component(
                name=ctx.name,
                stack=tech_stack.choices[0].name if tech_stack else "TBD"
            )
            for ctx in bounded_contexts
        ]

        mermaid_code = self._c4_generator.generate_container(
            project_name=project_name,
            containers=containers
        )

        svg_url = None
        if render:
            output_path = self._output_dir / "container"
            svg_url = await self._renderer.render_to_svg(
                mermaid_code,
                str(output_path)
            )

        return Diagram(
            diagram_id=f"{project_name}-container",
            type=DiagramType.C4_CONTAINER,
            title=f"{project_name} - Container Diagram",
            mermaid_code=mermaid_code,
            svg_url=svg_url
        )

    async def generate_component_diagram(
        self,
        component_name: str,
        component_description: str,
        subcomponents: List[str],
        render: bool = True
    ) -> Diagram:
        """
        Gera diagrama C4 Component.

        Args:
            component_name: Nome do componente
            component_description: Descrição do componente
            subcomponents: Lista de subcomponentes
            render: Se True, renderiza para SVG

        Returns:
            Diagram com código Mermaid e caminho SVG
        """
        self._logger.info("generating_component_diagram", component=component_name)

        mermaid_code = self._c4_generator.generate_component(
            component_name=component_name,
            component_description=component_description,
            subcomponents=subcomponents
        )

        svg_url = None
        if render:
            output_path = self._output_dir / "component"
            svg_url = await self._renderer.render_to_svg(
                mermaid_code,
                str(output_path)
            )

        return Diagram(
            diagram_id=f"{component_name}-component",
            type=DiagramType.C4_COMPONENT,
            title=f"{component_name} - Component Diagram",
            mermaid_code=mermaid_code,
            svg_url=svg_url
        )

    async def generate_all_diagrams(
        self,
        project_name: str,
        system_description: str,
        bounded_contexts: List[BoundedContext],
        tech_stack: Optional[TechStackRecommendation] = None,
        actors: Optional[List[str]] = None,
        external_systems: Optional[List[str]] = None,
        render: bool = False
    ) -> List[Diagram]:
        """
        Gera todos os diagramas de arquitetura.

        Args:
            project_name: Nome do projeto
            system_description: Descrição do sistema
            bounded_contexts: Contextos limitrófes
            tech_stack: Stack tecnológico
            actors: Atores (para contexto)
            external_systems: Sistemas externos (para contexto)
            render: Se True, renderiza para SVG

        Returns:
            Lista de Diagram gerados
        """
        self._logger.info("generating_all_diagrams", project=project_name)

        diagrams = []

        # Context diagram
        if actors is not None and external_systems is not None:
            context = await self.generate_context_diagram(
                project_name=project_name,
                system_description=system_description,
                actors=actors or ["User"],
                external_systems=external_systems or [],
                render=render
            )
            diagrams.append(context)

        # Container diagram
        container = await self.generate_container_diagram(
            project_name=project_name,
            bounded_contexts=bounded_contexts,
            tech_stack=tech_stack,
            render=render
        )
        diagrams.append(container)

        return diagrams

    async def generate_sequence(
        self,
        title: str,
        steps: List[str],
        artifacts: Optional[List[str]] = None,
        render: bool = True
    ) -> Diagram:
        """
        Gera diagrama de sequência.

        Args:
            title: Título do diagrama
            steps: Lista de passos da sequência (formato: "Actor->System: message")
            artifacts: Artefatos envolvidos (opcional)
            render: Se True, renderiza para SVG

        Returns:
            Diagram com código Mermaid e caminho SVG
        """
        self._logger.info("generating_sequence_diagram", title=title)

        # Construir código Mermaid para sequência
        mermaid_lines = ["sequenceDiagram"]
        for step in steps:
            mermaid_lines.append(f"    {step}")

        # Adicionar notas para artefatos se fornecidos
        if artifacts:
            for artifact in artifacts:
                mermaid_lines.append(f"    Note over {artifact}: {artifact}")

        mermaid_code = "\n".join(mermaid_lines)

        svg_url = None
        if render:
            output_path = self._output_dir / "sequence"
            svg_url = await self._renderer.render_to_svg(
                mermaid_code,
                str(output_path)
            )

        return Diagram(
            diagram_id=f"{title.lower().replace(' ', '-')}-sequence",
            type=DiagramType.SEQUENCE,
            title=title,
            mermaid_code=mermaid_code,
            svg_url=svg_url
        )

    async def generate_from_description(
        self,
        description: str,
        render: bool = True
    ) -> Diagram:
        """
        Gera diagrama a partir de descrição em linguagem natural.

        Este método usa heurísticas para determinar o tipo de diagrama
        mais apropriado baseado em palavras-chave na descrição.

        Args:
            description: Descrição do sistema/fluxo em linguagem natural
            render: Se True, renderiza para SVG

        Returns:
            Diagram gerado baseado na descrição
        """
        self._logger.info("generating_from_description", desc_preview=description[:100])

        description_lower = description.lower()

        # Converter para lista de palavras para matching exato (evita substrings)
        words = description_lower.split()

        # Heurísticas para determinar tipo de diagrama
        # Prioridade: contexto (descrição de sistema) > sequência (fluxo)
        context_keywords = {"context", "system", "architecture", "component"}
        sequence_keywords = {"sequence", "flow", "step", "then", "after", "next"}

        # Verificar se há palavras-chave de contexto (prioridade alta)
        has_context = any(word in words or f"{word}s" in words for word in context_keywords)

        # Verificar se há palavras-chave de sequência (mas apenas se não for contexto)
        has_sequence = any(word in words or f"{word}s" in words for word in sequence_keywords)

        # Detectar padrões de fluxo sequencial (frases como "then X happens")
        has_explicit_sequence = any(pattern in description_lower for pattern in [
            ", then ", ", after ", " next ", " followed by ", " subsequently "
        ])

        if has_context and not has_explicit_sequence:
            # Diagrama de contexto C4
            title = "Generated Context Diagram"
            project_name = "System"
            actors = ["User"]
            external_systems = []
            mermaid_code = self._c4_generator.generate_context(
                project_name=project_name,
                system_description=description,
                actors=actors,
                external_systems=external_systems
            )
            return Diagram(
                diagram_id=f"{project_name}-context",
                type=DiagramType.C4_CONTEXT,
                title=title,
                mermaid_code=mermaid_code,
                svg_url=None
            )
        elif has_sequence or has_explicit_sequence:
            # Diagrama de sequência
            title = "Generated Sequence Diagram"
            steps = self._parse_sequence_from_description(description)
            return await self.generate_sequence(title, steps, render=render)
        else:
            # Fallback: diagrama de contexto simples
            title = "Generated Diagram"
            mermaid_code = f"graph TD\n    A[{description[:50]}...]\n    B[Component B]\n    A --> B"
            return Diagram(
                diagram_id="generated-diagram",
                type=DiagramType.C4_CONTEXT,
                title=title,
                mermaid_code=mermaid_code,
                svg_url=None
            )

    def _parse_sequence_from_description(self, description: str) -> List[str]:
        """
        Parseia passos de sequência de uma descrição textual.

        Args:
            description: Descrição textual

        Returns:
            Lista de passos formatados para Mermaid
        """
        steps = []
        lines = description.split(".")
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Tentar identificar actor e ação
            if " then " in line.lower():
                parts = line.lower().split(" then ")
                for i, part in enumerate(parts):
                    part = part.strip()
                    if part:
                        steps.append(f"Step{i+1}->>Step{i+2}: {part}")
            elif "user" in line.lower() or "system" in line.lower():
                if "user" in line.lower():
                    steps.append(f"User->>System: {line}")
                else:
                    steps.append(f"System->>User: {line}")
            else:
                steps.append(f"Actor->>System: {line}")

        # Garantir pelo menos um passo
        if not steps:
            steps = ["User->>System: Process request", "System->>User: Return response"]

        return steps
