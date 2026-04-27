"""Gerador de documentação de arquitetura."""

import structlog
from src.clients.llm_client_wrapper import LLMClient
from src.config.settings import get_settings
from src.models import DocFormat, DocType, Document

logger = structlog.get_logger(__name__)

ARCHITECTURE_DOC_PROMPT = """
Gere documentação de arquitetura para o seguinte sistema:

**Nome do Sistema:** {system_name}

**Descrição:** {description}

**Componentes:**
{components}

**Requisitos Não-Funcionais:**
{non_functional}

**Padrões Arquiteturais:**
{patterns}

A documentação deve incluir:
1. Visão Geral da Arquitetura
2. Componentes Principais
3. Comunicação entre Componentes
4. Decisões Arquiteturais (ADRs)
5. Considerações de Escalabilidade
6. Diagrama Mermaid de alto nível

Use formatação Markdown clara.
"""


class ArchitectureDocsGenerator:
    """Gerador de documentação de arquitetura."""

    def __init__(self, llm_client: LLMClient | None = None):
        """Inicializa o gerador."""
        settings = get_settings()
        self._llm_client = llm_client or LLMClient(api_key=settings.openai_api_key)
        self._model = settings.llm_model
        self._logger = logger

    async def generate_from_requirements(
        self,
        system_name: str,
        description: str,
        components: list[dict],
        non_functional: list[str] | None = None,
        patterns: list[str] | None = None,
    ) -> Document:
        """
        Gera documentação de arquitetura a partir de requisitos.

        Args:
            system_name: Nome do sistema
            description: Descrição do sistema
            components: Lista de componentes [{name, responsibility, interfaces}]
            non_functional: Requisitos não-funcionais
            patterns: Padrões arquiteturais utilizados

        Returns:
            Document com a arquitetura documentada
        """
        self._logger.info("generating_architecture_docs", system=system_name)

        components_text = self._format_components(components)
        non_functional_text = (
            "\n".join([f"- {req}" for req in non_functional]) if non_functional else "A definir"
        )
        patterns_text = "\n".join([f"- {p}" for p in patterns]) if patterns else "A definir"

        prompt = ARCHITECTURE_DOC_PROMPT.format(
            system_name=system_name,
            description=description,
            components=components_text,
            non_functional=non_functional_text,
            patterns=patterns_text,
        )

        try:
            response = await self._llm_client.generate(
                messages=[
                    {
                        "role": "system",
                        "content": "Você é um arquiteto de software especialista em documentação de arquitetura.",
                    },
                    {"role": "user", "content": prompt},
                ],
                model=self._model,
            )

            content = response.choices[0].message["content"]

            return Document(
                id=f"DOC-ARCH-{system_name.replace(' ', '-').lower()}",
                doc_type=DocType.ARCHITECTURE,
                format=DocFormat.MARKDOWN,
                title=f"{system_name} - Architecture Documentation",
                content=content,
                file_path=f"docs/architecture/{system_name.lower().replace(' ', '-')}.md",
                metadata={
                    "system": system_name,
                    "components_count": len(components),
                    "patterns": patterns or [],
                },
            )

        except Exception as e:
            self._logger.error("failed_to_generate_architecture_docs", error=str(e))
            raise

    async def generate_adr(
        self,
        title: str,
        context: str,
        decision: str,
        consequences: list[str],
        alternatives: list[dict] | None = None,
        adr_id: int = 1,
    ) -> Document:
        """
        Gera um Architecture Decision Record (ADR).

        Args:
            title: Título da decisão
            context: Contexto e problema
            decision: Decisão tomada
            consequences: Consequências da decisão
            alternatives: Alternativas consideradas [{approach, pros, cons}]
            adr_id: Número do ADR

        Returns:
            Document com o ADR formatado
        """
        self._logger.info("generating_adr", title=title, adr_id=adr_id)

        # Formatar ADR no padrão
        content = f"""# ADR-{adr_id:03d}: {title}

## Status
Accepted

## Context
{context}

## Decision
{decision}

## Consequences
"""

        for consequence in consequences:
            content += f"- {consequence}\n"

        if alternatives:
            content += "\n## Alternatives Considered\n"
            for i, alt in enumerate(alternatives, 1):
                content += f"\n### {i}. {alt.get('approach', 'Alternative')}\n"
                if "pros" in alt:
                    content += "**Pros:**\n"
                    for pro in alt["pros"]:
                        content += f"- {pro}\n"
                if "cons" in alt:
                    content += "**Cons:**\n"
                    for con in alt["cons"]:
                        content += f"- {con}\n"

        return Document(
            id=f"DOC-ADR-{adr_id:03d}",
            doc_type=DocType.ARCHITECTURE,
            format=DocFormat.MARKDOWN,
            title=f"ADR-{adr_id:03d}: {title}",
            content=content,
            file_path=f"docs/adr/{adr_id:03d}-{title.lower().replace(' ', '-')}.md",
            metadata={"adr_id": adr_id, "type": "ADR"},
        )

    async def generate_component_doc(
        self,
        component_name: str,
        responsibility: str,
        interfaces: list[dict],
        dependencies: list[str] | None = None,
    ) -> Document:
        """
        Gera documentação detalhada de um componente.

        Args:
            component_name: Nome do componente
            responsibility: Responsabilidade principal
            interfaces: Interfaces expostas [{name, method, description}]
            dependencies: Dependências de outros componentes

        Returns:
            Document com a documentação do componente
        """
        self._logger.info("generating_component_doc", component=component_name)

        prompt = f"""
Gere documentação técnica detalhada para o seguinte componente:

**Nome:** {component_name}

**Responsabilidade:**
{responsibility}

**Interfaces:**
{self._format_interfaces(interfaces)}

**Dependências:**
{', '.join(dependencies) if dependencies else 'Nenhuma'}

A documentação deve incluir:
1. Descrição do Componente
2. Responsabilidades
3. Interface Pública (APIs, eventos, mensagens)
4. Dependências
5. Diagrama de sequência Mermaid (se aplicável)
"""

        try:
            response = await self._llm_client.generate(
                messages=[
                    {
                        "role": "system",
                        "content": "Você é um arquiteto de software especialista em documentação de componentes.",
                    },
                    {"role": "user", "content": prompt},
                ],
                model=self._model,
            )

            content = response.choices[0].message["content"]

            return Document(
                id=f"DOC-COMP-{component_name.lower().replace(' ', '-')}",
                doc_type=DocType.ARCHITECTURE,
                format=DocFormat.MARKDOWN,
                title=f"Component: {component_name}",
                content=content,
                file_path=f"docs/components/{component_name.lower().replace(' ', '-')}.md",
                metadata={
                    "component": component_name,
                    "interfaces_count": len(interfaces),
                },
            )

        except Exception as e:
            self._logger.error("failed_to_generate_component_doc", error=str(e))
            raise

    def _format_components(self, components: list[dict]) -> str:
        """Formata lista de componentes para o prompt."""
        if not components:
            return "A definir"

        formatted = []
        for comp in components:
            name = comp.get("name", "Unknown")
            resp = comp.get("responsibility", "N/A")
            interfaces = comp.get("interfaces", [])
            interfaces_str = ", ".join(interfaces) if interfaces else "N/A"

            formatted.append(f"**{name}**: {resp}\n  - Interfaces: {interfaces_str}")

        return "\n\n".join(formatted)

    def _format_interfaces(self, interfaces: list[dict]) -> str:
        """Formata lista de interfaces para o prompt."""
        if not interfaces:
            return "Nenhuma"

        formatted = []
        for iface in interfaces:
            name = iface.get("name", "Unknown")
            method = iface.get("method", "N/A")
            desc = iface.get("description", "")

            formatted.append(f"- **{name}** ({method}): {desc}")

        return "\n".join(formatted) if formatted else "Nenhuma"
