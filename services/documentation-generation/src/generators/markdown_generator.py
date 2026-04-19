"""Gerador de documentos Markdown."""

import re
from datetime import datetime, timezone
from typing import Any

import structlog
from src.models import DocFormat, DocType, Document

logger = structlog.get_logger(__name__)


class MarkdownGenerator:
    """Gerador de documentos Markdown formatados."""

    def __init__(self):
        """Inicializa o gerador."""
        self._logger = logger

    def generate_api_doc(
        self,
        service_name: str,
        base_url: str,
        endpoints: list[dict[str, Any]],
        description: str | None = None,
    ) -> Document:
        """
        Gera documentação de API em Markdown.

        Args:
            service_name: Nome do serviço
            base_url: URL base da API
            endpoints: Lista de endpoints [{method, path, description, params, responses}]
            description: Descrição do serviço

        Returns:
            Document com a documentação da API
        """
        self._logger.info("generating_api_markdown", service=service_name)

        # Descrição condicional
        desc_section = ""
        if description:
            desc_section = f"## Description\n\n{description}\n"

        content = f"""# {service_name} API Documentation

**Base URL:** `{base_url}`

{desc_section}
## Endpoints

"""

        for endpoint in endpoints:
            method = endpoint.get("method", "GET").upper()
            path = endpoint.get("path", "/")
            desc = endpoint.get("description", "")
            params = endpoint.get("params", [])
            responses = endpoint.get("responses", {})

            content += f"### {method} {path}\n\n"

            if desc:
                content += f"{desc}\n\n"

            if params:
                content += "**Parameters:**\n\n"
                for param in params:
                    param_name = param.get("name", "")
                    param_type = param.get("type", "string")
                    required = param.get("required", False)
                    param_desc = param.get("description", "")

                    content += (
                        f"- `{param_name}` ({param_type})"
                        f"{' **(required)**' if required else ''}: {param_desc}\n"
                    )
                content += "\n"

            if responses:
                content += "**Responses:**\n\n"
                for status, body in responses.items():
                    content += f"- **{status}**: {body}\n"
                content += "\n"

            content += "---\n\n"

        content += (
            f"\n*Generated on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC*\n"
        )

        return Document(
            id=f"DOC-API-{service_name.lower().replace(' ', '-')}",
            doc_type=DocType.API_DOCS,
            format=DocFormat.MARKDOWN,
            title=f"{service_name} API Documentation",
            content=content,
            file_path=f"docs/api/{service_name.lower().replace(' ', '-')}.md",
            metadata={
                "service": service_name,
                "endpoints_count": len(endpoints),
                "base_url": base_url,
            },
        )

    def generate_user_guide(
        self,
        title: str,
        features: list[dict[str, Any]],
        getting_started: str | None = None,
        examples: list[dict] | None = None,
    ) -> Document:
        """
        Gera guia de usuário em Markdown.

        Args:
            title: Título do guia
            features: Lista de funcionalidades [{name, description, usage}]
            getting_started: Instruções iniciais
            examples: Exemplos de uso [{title, code, description}]

        Returns:
            Document com o guia de usuário
        """
        self._logger.info("generating_user_guide", title=title)

        content = f"""# {title}

"""

        if getting_started:
            content += f"""## Getting Started

{getting_started}

"""

        content += """## Features

"""

        for feature in features:
            name = feature.get("name", "Feature")
            desc = feature.get("description", "")
            usage = feature.get("usage", "")

            content += f"### {name}\n\n"

            if desc:
                content += f"{desc}\n\n"

            if usage:
                content += f"**Usage:**\n\n{usage}\n\n"

        if examples:
            content += "## Examples\n\n"

            for example in examples:
                ex_title = example.get("title", "Example")
                ex_desc = example.get("description", "")
                ex_code = example.get("code", "")

                content += f"### {ex_title}\n\n"

                if ex_desc:
                    content += f"{ex_desc}\n\n"

                if ex_code:
                    lang = example.get("language", "text")
                    content += f"```{lang}\n{ex_code}\n```\n\n"

        content += (
            f"\n*Generated on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC*\n"
        )

        return Document(
            id=f"DOC-GUIDE-{title.lower().replace(' ', '-').replace('/', '-')}",
            doc_type=DocType.USER_GUIDE,
            format=DocFormat.MARKDOWN,
            title=title,
            content=content,
            file_path=f"docs/guides/{title.lower().replace(' ', '-')}.md",
            metadata={
                "features_count": len(features),
                "examples_count": len(examples) if examples else 0,
            },
        )

    def generate_readme(
        self,
        project_name: str,
        description: str,
        sections: dict[str, str] | None = None,
    ) -> Document:
        """
        Gera README em Markdown.

        Args:
            project_name: Nome do projeto
            description: Descrição do projeto
            sections: Seções adicionais {section_name: content}

        Returns:
            Document com o README
        """
        self._logger.info("generating_readme", project=project_name)

        content = f"""# {project_name}

{description}

"""

        if sections:
            for section_name, section_content in sections.items():
                # Converter para Title Case
                formatted_name = section_name.replace("_", " ").title()
                content += f"## {formatted_name}\n\n{section_content}\n\n"

        # Adicionar seção padrão de license se não existente
        if sections and "license" not in {k.lower() for k in sections.keys()}:
            content += """## License

MIT License - see LICENSE file for details.
"""

        content += (
            f"\n*Generated on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC*\n"
        )

        return Document(
            id=f"DOC-README-{project_name.lower().replace(' ', '-')}",
            doc_type=DocType.README,
            format=DocFormat.MARKDOWN,
            title=f"{project_name} README",
            content=content,
            file_path="README.md",
            metadata={"project": project_name},
        )

    def generate_changelog(
        self,
        project_name: str,
        versions: list[dict[str, Any]],
    ) -> Document:
        """
        Gera CHANGELOG em Markdown.

        Args:
            project_name: Nome do projeto
            versions: Lista de versões [{version, date, changes[{type, description}]}]

        Returns:
            Document com o CHANGELOG
        """
        self._logger.info("generating_changelog", project=project_name)

        content = f"""# Changelog

All notable changes to {project_name} will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

"""

        for version in versions:
            ver = version.get("version", "Unreleased")
            date = version.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
            changes = version.get("changes", [])

            content += f"## [{ver}] - {date}\n\n"

            # Agrupar por tipo
            by_type: dict[str, list[str]] = {}
            for change in changes:
                change_type = change.get("type", "changed").lower()
                desc = change.get("description", "")

                if change_type not in by_type:
                    by_type[change_type] = []

                by_type[change_type].append(desc)

            # Ordenar tipos: added > changed > deprecated > removed > fixed > security
            type_order = ["added", "changed", "deprecated", "removed", "fixed", "security"]

            for change_type in type_order:
                if change_type in by_type and by_type[change_type]:
                    content += f"### {change_type.title()}\n\n"
                    for desc in by_type[change_type]:
                        content += f"- {desc}\n"
                    content += "\n"

        content += (
            f"\n*Generated on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC*\n"
        )

        return Document(
            id=f"DOC-CHANGELOG-{project_name.lower().replace(' ', '-')}",
            doc_type=DocType.ARCHITECTURE,
            format=DocFormat.MARKDOWN,
            title=f"{project_name} Changelog",
            content=content,
            file_path="CHANGELOG.md",
            metadata={"project": project_name, "versions_count": len(versions)},
        )

    def format_table(self, headers: list[str], rows: list[list[str]]) -> str:
        """
        Formata tabela em Markdown.

        Args:
            headers: Cabeçalhos da tabela
            rows: Linhas da tabela

        Returns:
            String com a tabela formatada
        """
        if not headers or not rows:
            return ""

        # Calcular largura de cada coluna
        col_widths = [len(h) for h in headers]

        for row in rows:
            for i, cell in enumerate(row):
                if i < len(col_widths):
                    col_widths[i] = max(col_widths[i], len(str(cell)))

        # Construir tabela
        lines = []

        # Cabeçalho
        header_line = (
            "| " + " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers)) + " |"
        )
        lines.append(header_line)

        # Separador
        separator_line = "|" + "|".join("-" * (w + 2) for w in col_widths) + "|"
        lines.append(separator_line)

        # Linhas
        for row in rows:
            cells = []
            for i, cell in enumerate(row):
                if i < len(col_widths):
                    cells.append(str(cell).ljust(col_widths[i]))
                else:
                    cells.append(str(cell))

            lines.append("| " + " | ".join(cells) + " |")

        return "\n".join(lines)

    def format_code_block(
        self, code: str, language: str = "python", title: str | None = None
    ) -> str:
        """
        Formata bloco de código em Markdown.

        Args:
            code: Código a formatar
            language: Linguagem de programação
            title: Título opcional do bloco

        Returns:
            String com o código formatado
        """
        result = ""

        if title:
            result += f"**{title}**\n\n"

        result += f"```{language}\n{code}\n```\n"

        return result

    def format_list(self, items: list[str], ordered: bool = False) -> str:
        """
        Formata lista em Markdown.

        Args:
            items: Itens da lista
            ordered: Se True, usa lista numerada

        Returns:
            String com a lista formatada
        """
        if not items:
            return ""

        if ordered:
            return "\n".join(f"{i+1}. {item}" for i, item in enumerate(items))
        else:
            return "\n".join(f"- {item}" for item in items)

    def escape_markdown(self, text: str) -> str:
        """
        Escapa caracteres especiais Markdown.

        Args:
            text: Texto a escapar

        Returns:
            Texto com caracteres escapados
        """
        # Caracteres que precisam de escape
        special_chars = r"\\`*_{}[]()#+-.!"

        # Escapar apenas fora de blocos de código
        def replace_fn(match):
            # Não escapar se está dentro de um bloco de código
            if match.group(1).startswith("```"):
                return match.group(0)
            # Não escapar o último backtick de código inline
            if match.group(0) == "`" and match.group(1).endswith("`"):
                return match.group(0)
            return "\\" + match.group(0)

        pattern = f"([{re.escape(special_chars)}])"
        return re.sub(pattern, replace_fn, text)
