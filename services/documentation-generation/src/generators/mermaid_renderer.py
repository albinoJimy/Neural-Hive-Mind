"""Renderizador de diagramas Mermaid."""

import re
import subprocess
import tempfile
from enum import Enum
from pathlib import Path
from typing import Any

import structlog
from src.models import DocFormat, DocType, Document

logger = structlog.get_logger(__name__)


class MermaidOutputFormat(str, Enum):
    """Formatos de saída para renderização Mermaid."""

    SVG = "svg"
    PNG = "png"
    PDF = "pdf"


class MermaidRenderer:
    """Renderizador de diagramas Mermaid para imagens."""

    def __init__(self, cli_path: str | None = None):
        """
        Inicializa o renderizador.

        Args:
            cli_path: Caminho para o executável mmdc (mermaid-cli)
        """
        self._cli_path = cli_path or "mmdc"
        self._logger = logger
        self._available = self._check_availability()

    def _check_availability(self) -> bool:
        """
        Verifica se o mermaid-cli está disponível.

        Returns:
            True se mmdc está disponível
        """
        try:
            result = subprocess.run(
                [self._cli_path, "--version"],
                capture_output=True,
                timeout=5,
            )
            available = result.returncode == 0
            self._logger.info(
                "mermaid_cli_check",
                available=available,
                path=self._cli_path,
            )
            return available
        except FileNotFoundError:
            self._logger.warning(
                "mermaid_cli_not_found",
                path=self._cli_path,
                message="Install with: npm install -g @mermaid-js/mermaid-cli",
            )
            return False
        except Exception as e:
            self._logger.warning("mermaid_cli_check_failed", error=str(e))
            return False

    async def render_to_svg(
        self,
        mermaid_code: str,
        output_path: str | None = None,
    ) -> Document:
        """
        Renderiza código Mermaid para SVG.

        Args:
            mermaid_code: Código Mermaid
            output_path: Caminho para salvar o arquivo SVG

        Returns:
            Document com o SVG gerado
        """
        return await self._render(
            mermaid_code=mermaid_code,
            output_format=MermaidOutputFormat.SVG,
            output_path=output_path,
        )

    async def render_to_png(
        self,
        mermaid_code: str,
        output_path: str | None = None,
    ) -> Document:
        """
        Renderiza código Mermaid para PNG.

        Args:
            mermaid_code: Código Mermaid
            output_path: Caminho para salvar o arquivo PNG

        Returns:
            Document com o PNG gerado
        """
        return await self._render(
            mermaid_code=mermaid_code,
            output_format=MermaidOutputFormat.PNG,
            output_path=output_path,
        )

    async def _render(
        self,
        mermaid_code: str,
        output_format: MermaidOutputFormat,
        output_path: str | None = None,
    ) -> Document:
        """
        Renderiza código Mermaid para o formato especificado.

        Args:
            mermaid_code: Código Mermaid
            output_format: Formato de saída
            output_path: Caminho para salvar o arquivo

        Returns:
            Document com o conteúdo gerado
        """
        self._logger.info(
            "rendering_mermaid",
            format=output_format,
            code_length=len(mermaid_code),
        )

        # Limpar código
        clean_code = self._clean_mermaid_code(mermaid_code)

        # Gerar output path se não fornecido
        if output_path is None:
            output_path = f"/tmp/mermaid_{hash(clean_code) % 100000}.{output_format}"

        try:
            if self._available:
                # Usar mermaid-cli
                result = await self._render_with_cli(
                    clean_code, output_format, output_path
                )
            else:
                # Fallback: manter como código Mermaid
                self._logger.warning(
                    "mermaid_cli_unavailable", message="Falling back to Mermaid code"
                )
                result = self._create_fallback_document(clean_code, output_path)

            return result

        except Exception as e:
            self._logger.error("failed_to_render_mermaid", error=str(e))
            # Fallback para código Mermaid
            return self._create_fallback_document(clean_code, output_path)

    async def _render_with_cli(
        self,
        mermaid_code: str,
        output_format: MermaidOutputFormat,
        output_path: str,
    ) -> Document:
        """
        Renderiza usando mermaid-cli.

        Args:
            mermaid_code: Código Mermaid limpo
            output_format: Formato de saída
            output_path: Caminho de saída

        Returns:
            Document com o resultado
        """
        # Criar arquivo temporário com o código
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".mmd", delete=False
        ) as input_file:
            input_file.write(mermaid_code)
            input_path = input_file.name

        try:
            # Executar mmdc
            cmd = [
                self._cli_path,
                "-i",
                input_path,
                "-o",
                output_path,
                "-b",
                "transparent",  # Fundo transparente
            ]

            process = await subprocess.run_async(cmd, capture_output=True)

            if process.returncode != 0:
                error = process.stderr.decode("utf-8", errors="replace")
                raise RuntimeError(f"mmdc failed: {error}")

            # Ler resultado
            with open(output_path, "rb") as f:
                content = f.read()

            # Para SVG, extrair como texto
            if output_format == MermaidOutputFormat.SVG:
                with open(output_path, "r", encoding="utf-8") as f:
                    svg_content = f.read()

                doc_type = DocType.DIAGRAM
                doc_format = DocFormat.HTML  # SVG como HTML

                return Document(
                    id=f"DOC-DIAG-SVG-{hash(mermaid_code) % 10000}",
                    doc_type=doc_type,
                    format=doc_format,
                    title="Mermaid Diagram",
                    content=svg_content,
                    file_path=output_path,
                    metadata={"render_method": "mermaid-cli", "format": "svg"},
                )
            else:
                # Para PNG/PDF, manter como binário (base64 encoded)
                import base64

                b64_content = base64.b64encode(content).decode("ascii")

                return Document(
                    id=f"DOC-DIAG-{output_format.upper()}-{hash(mermaid_code) % 10000}",
                    doc_type=DocType.DIAGRAM,
                    format=DocFormat.MARKDOWN,
                    title=f"Mermaid Diagram ({output_format})",
                    content=f"![diagram](data:image/{output_format};base64,{b64_content})",
                    file_path=output_path,
                    metadata={"render_method": "mermaid-cli", "format": str(output_format)},
                )

        finally:
            # Limpar arquivo temporário
            try:
                Path(input_path).unlink(missing_ok=True)
            except Exception:
                pass

    def _create_fallback_document(
        self, mermaid_code: str, output_path: str
    ) -> Document:
        """
        Cria documento de fallback quando mmdc não está disponível.

        Args:
            mermaid_code: Código Mermaid
            output_path: Caminho de saída

        Returns:
            Document com código Mermaid embutido
        """
        # Criar HTML com Mermaid.js
        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <script type="module">
        import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
        mermaid.initialize({{ startOnLoad: true }});
    </script>
</head>
<body>
    <pre class="mermaid">
{mermaid_code}
    </pre>
</body>
</html>
"""

        return Document(
            id=f"DOC-DIAG-MERMAID-{hash(mermaid_code) % 10000}",
            doc_type=DocType.DIAGRAM,
            format=DocFormat.HTML,
            title="Mermaid Diagram (Interactive)",
            content=html_content,
            file_path=output_path.replace(".svg", ".html").replace(".png", ".html"),
            metadata={"render_method": "mermaid-js", "fallback": True},
        )

    def _clean_mermaid_code(self, code: str) -> str:
        """
        Limpa código Mermaid removendo formatação Markdown.

        Args:
            code: Código possivelmente formatado

        Returns:
            Código Mermaid limpo
        """
        # Remover blocos de código markdown
        code = re.sub(r"```(?:mermaid)?\s*\n", "", code)
        code = re.sub(r"\n```\s*$", "", code)

        # Remover aspas extras
        code = code.strip().strip('"').strip("'")

        return code

    def extract_diagram_type(self, mermaid_code: str) -> str | None:
        """
        Extrai o tipo de diagrama do código Mermaid.

        Args:
            mermaid_code: Código Mermaid

        Returns:
            Tipo de diagrama ou None
        """
        clean_code = self._clean_mermaid_code(mermaid_code)

        # Padrões para diferentes tipos
        patterns = {
            "sequence": r"^(sequenceDiagram|participant)",
            "flowchart": r"^(graph|flowchart)",
            "er": r"^(erDiagram)",
            "class": r"^(classDiagram)",
            "state": r"^(stateDiagram)",
            "gantt": r"^(gantt)",
            "pie": r"^(pie)",
            "journey": r"^(journey)",
        }

        for diagram_type, pattern in patterns.items():
            if re.search(pattern, clean_code, re.MULTILINE):
                return diagram_type

        return None

    def validate_mermaid_syntax(self, mermaid_code: str) -> dict[str, Any]:
        """
        Valida sintaxe básica do código Mermaid.

        Args:
            mermaid_code: Código Mermaid

        Returns:
            Dict com {valid, errors, warnings}
        """
        clean_code = self._clean_mermaid_code(mermaid_code)

        errors = []
        warnings = []

        # Verificar se está vazio
        if not clean_code.strip():
            errors.append("Empty Mermaid code")

        # Verificar se tem diretiva de tipo
        first_line = clean_code.split("\n")[0].strip()
        valid_starts = [
            "graph",
            "flowchart",
            "sequenceDiagram",
            "erDiagram",
            "classDiagram",
            "stateDiagram",
            "gantt",
            "pie",
            "journey",
            "mindmap",
            "gitGraph",
        ]

        if not any(first_line.startswith(start) for start in valid_starts):
            warnings.append(
                f"Unknown diagram type: {first_line}. "
                f"Valid types: {', '.join(valid_starts)}"
            )

        # Verificar balanceamento de chaves
        open_braces = clean_code.count("{")
        close_braces = clean_code.count("}")

        if open_braces != close_braces:
            errors.append(
                f"Unbalanced braces: {open_braces} open, {close_braces} close"
            )

        # Verificar linhas vazias excessivas
        empty_lines = len([line for line in clean_code.split("\n") if not line.strip()])
        if empty_lines > len(clean_code.split("\n")) * 0.5:
            warnings.append("More than 50% of lines are empty")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "diagram_type": self.extract_diagram_type(clean_code),
        }


# Helper function for async subprocess
async def subprocess_run_async(cmd: list, capture_output: bool = True):
    """
    Executa subprocess de forma assíncrona.

    Args:
        cmd: Comando a executar
        capture_output: Se deve capturar stdout/stderr

    Returns:
        Objeto com returncode, stdout, stderr
    """
    import asyncio

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE if capture_output else None,
        stderr=asyncio.subprocess.PIPE if capture_output else None,
    )

    stdout, stderr = await proc.communicate()

    class CompletedProcess:
        def __init__(self, returncode, stdout, stderr):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    return CompletedProcess(proc.returncode, stdout, stderr)
