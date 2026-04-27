"""Architecture diagram generator orchestrator."""

from pathlib import Path

from structlog import get_logger

from neural_hive_llm import LLMClient, LLMProvider, LLMResponse

from src.generators.c4_diagram import C4DiagramGenerator
from src.generators.mermaid_renderer import MermaidRenderer
from src.models.architecture import Component
from src.models.bounded_context import BoundedContext
from src.models.diagrams import Diagram, DiagramType
from src.models.tech_stack import TechStackRecommendation

logger = get_logger(__name__)


class ArchitectureDiagramGenerator:
    """Orquestra geração de diagramas de arquitetura."""

    SEQUENCE_PROMPT = """
Gere um diagrama de sequência Mermaid para o seguinte fluxo:

{flow_description}

O diagrama deve mostrar a interação entre componentes.
Use formato: sequenceDiagram

Responda apenas com o código Mermaid, sem markdown.
"""

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        mermaid_renderer: MermaidRenderer | None = None,
        output_dir: str | None = None,
        mmdc_command: str = "mmdc",
    ):
        """
        Inicializa o gerador.

        Args:
            llm_client: Cliente LLM para geração de diagramas via LLM
            mermaid_renderer: Renderer Mermaid (opcional, cria padrão se não fornecido)
            output_dir: Diretório base para diagramas gerados
            mmdc_command: Comando mermaid-cli
        """
        self._llm_client = llm_client
        self._renderer = mermaid_renderer or MermaidRenderer(mmdc_command)
        self._output_dir = Path(output_dir) if output_dir else Path("diagrams")
        self._c4_generator = C4DiagramGenerator()
        self._logger = logger
        self._llm_started = False

    async def generate_context_diagram(
        self,
        project_name: str,
        system_description: str,
        actors: list[str],
        external_systems: list[str],
        render: bool = True,
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
            external_systems=external_systems,
        )

        svg_url = None
        if render:
            output_path = self._output_dir / "context"
            svg_url = await self._renderer.render_to_svg(mermaid_code, str(output_path))

        return Diagram(
            diagram_id=f"{project_name}-context",
            type=DiagramType.C4_CONTEXT,
            title=f"{project_name} - Context Diagram",
            mermaid_code=mermaid_code,
            svg_url=svg_url,
        )

    async def generate_container_diagram(
        self,
        project_name: str,
        bounded_contexts: list[BoundedContext],
        tech_stack: TechStackRecommendation | None = None,
        render: bool = True,
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
            Component(name=ctx.name, stack=tech_stack.choices[0].name if tech_stack else "TBD")
            for ctx in bounded_contexts
        ]

        mermaid_code = self._c4_generator.generate_container(
            project_name=project_name, containers=containers
        )

        svg_url = None
        if render:
            output_path = self._output_dir / "container"
            svg_url = await self._renderer.render_to_svg(mermaid_code, str(output_path))

        return Diagram(
            diagram_id=f"{project_name}-container",
            type=DiagramType.C4_CONTAINER,
            title=f"{project_name} - Container Diagram",
            mermaid_code=mermaid_code,
            svg_url=svg_url,
        )

    async def generate_component_diagram(
        self,
        component_name: str,
        component_description: str,
        subcomponents: list[str],
        render: bool = True,
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
            subcomponents=subcomponents,
        )

        svg_url = None
        if render:
            output_path = self._output_dir / "component"
            svg_url = await self._renderer.render_to_svg(mermaid_code, str(output_path))

        return Diagram(
            diagram_id=f"{component_name}-component",
            type=DiagramType.C4_COMPONENT,
            title=f"{component_name} - Component Diagram",
            mermaid_code=mermaid_code,
            svg_url=svg_url,
        )

    async def generate_all_diagrams(
        self,
        project_name: str,
        system_description: str,
        bounded_contexts: list[BoundedContext],
        tech_stack: TechStackRecommendation | None = None,
        actors: list[str] | None = None,
        external_systems: list[str] | None = None,
        render: bool = False,
    ) -> list[Diagram]:
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
                render=render,
            )
            diagrams.append(context)

        # Container diagram
        container = await self.generate_container_diagram(
            project_name=project_name,
            bounded_contexts=bounded_contexts,
            tech_stack=tech_stack,
            render=render,
        )
        diagrams.append(container)

        return diagrams

    async def generate_sequence(
        self,
        title: str,
        steps: list[str] | None = None,
        artifacts: list[str] | None = None,
        render: bool = True,
        mermaid_code: str | None = None,
    ) -> Diagram:
        """
        Gera diagrama de sequência.

        Args:
            title: Título do diagrama
            steps: Lista de passos da sequência (formato: "Actor->System: message")
            artifacts: Artefatos envolvidos (opcional)
            render: Se True, renderiza para SVG
            mermaid_code: Código Mermaid já gerado (opcional, prioridade sobre steps)

        Returns:
            Diagram com código Mermaid e caminho SVG
        """
        self._logger.info("generating_sequence_diagram", title=title)

        # Se mermaid_code fornecido, usar diretamente
        if mermaid_code:
            final_mermaid_code = mermaid_code
        else:
            # Construir código Mermaid para sequência
            mermaid_lines = ["sequenceDiagram"]
            for step in steps or []:
                mermaid_lines.append(f"    {step}")

            # Adicionar notas para artefatos se fornecidos
            if artifacts:
                for artifact in artifacts:
                    mermaid_lines.append(f"    Note over {artifact}: {artifact}")

            final_mermaid_code = "\n".join(mermaid_lines)

        svg_url = None
        if render:
            output_path = self._output_dir / "sequence"
            svg_url = await self._renderer.render_to_svg(final_mermaid_code, str(output_path))

        return Diagram(
            diagram_id=f"{title.lower().replace(' ', '-')}-sequence",
            type=DiagramType.SEQUENCE,
            title=title,
            mermaid_code=final_mermaid_code,
            svg_url=svg_url,
        )

    async def _ensure_llm_started(self):
        """Garante que o cliente LLM está inicializado."""
        if not self._llm_client:
            # Criar cliente padrão com settings
            from src.config.settings import get_settings

            settings = get_settings()
            if not settings.llm.provider or not settings.llm.api_key:
                raise ConnectionError("LLM not configured: provider or api_key missing")

            provider = LLMProvider.OPENAI if settings.llm.provider == "openai" else LLMProvider.ANTHROPIC
            self._llm_client = LLMClient(provider=provider, api_key=settings.llm.api_key, model="gpt-4")
            await self._llm_client.start()
            self._llm_started = True
        elif not self._llm_started:
            await self._llm_client.start()
            self._llm_started = True

    async def generate_from_description(self, description: str, render: bool = True) -> Diagram:
        """
        Gera diagrama a partir de descrição em linguagem natural usando LLM.

        Args:
            description: Descrição do sistema/fluxo em linguagem natural
            render: Se True, renderiza para SVG

        Returns:
            Diagram gerado baseado na descrição
        """
        self._logger.info("generating_diagram_from_description")

        await self._ensure_llm_started()

        response: LLMResponse = await self._llm_client.generate(
            prompt=self.SEQUENCE_PROMPT.format(flow_description=description),
            system_prompt="Você é um especialista em diagramas UML e Mermaid.",
        )

        mermaid_code = response.text.strip()

        # Limpar markdown se presente
        if mermaid_code.startswith("```"):
            mermaid_code = mermaid_code.split("\n", 1)[-1].rstrip("\n`")

        return await self.generate_sequence(
            title="Generated Diagram", steps=[], render=render  # Steps já estão no mermaid_code
        )

    def _parse_sequence_from_description(self, description: str) -> list[str]:
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
