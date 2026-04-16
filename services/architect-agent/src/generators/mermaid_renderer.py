"""Mermaid diagram renderer using mermaid-cli."""

import asyncio
import tempfile
from pathlib import Path
from typing import Optional
import subprocess

from structlog import get_logger

logger = get_logger(__name__)


class MermaidRenderer:
    """Renderiza diagramas Mermaid para SVG usando mermaid-cli."""

    def __init__(self, mmdc_command: str = "mmdc"):
        """
        Inicializa o renderer.

        Args:
            mmdc_command: Comando para executar mermaid-cli (padrão: "mmdc")
        """
        self._mmdc_command = mmdc_command
        self._logger = logger

    async def render_to_svg(
        self,
        mermaid_code: str,
        output_dir: Optional[str] = None
    ) -> str:
        """
        Renderiza código Mermaid para SVG.

        Args:
            mermaid_code: Código Mermaid completo
            output_dir: Diretório de saída (opcional, usa temp se não fornecido)

        Returns:
            Caminho para o arquivo SVG gerado

        Raises:
            RuntimeError: Se mermaid-cli não estiver instalado
            subprocess.CalledProcessError: Se a renderização falhar
        """
        self._logger.info("rendering_mermaid_diagram")

        # Criar diretório temporário se output_dir não fornecido
        if output_dir is None:
            temp_dir = tempfile.mkdtemp(prefix="mermaid_")
            output_path = Path(temp_dir) / "diagram.svg"
        else:
            output_path = Path(output_dir) / "diagram.svg"
            output_path.parent.mkdir(parents=True, exist_ok=True)

        # Criar arquivo .mmd temporário
        input_path = output_path.parent / "diagram.mmd"
        input_path.write_text(mermaid_code, encoding="utf-8")

        # Executar mmdc em subprocess para não bloquear event loop
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                [
                    self._mmdc_command,
                    "-i", str(input_path),
                    "-o", str(output_path),
                    "-b", "transparent"  # Fundo transparente
                ],
                capture_output=True,
                text=True,
                check=True
            )
        )

        # Validar que o arquivo foi criado
        output_path = Path(output_path)
        if not output_path.exists():
            raise RuntimeError(f"Mermaid rendering failed: {output_path} not created")

        self._logger.info(
            "mermaid_rendered",
            output_path=str(output_path)
        )

        return str(output_path)

    async def render_to_png(
        self,
        mermaid_code: str,
        output_dir: Optional[str] = None
    ) -> str:
        """
        Renderiza código Mermaid para PNG.

        Args:
            mermaid_code: Código Mermaid completo
            output_dir: Diretório de saída (opcional, usa temp se não fornecido)

        Returns:
            Caminho para o arquivo PNG gerado
        """
        self._logger.info("rendering_mermaid_to_png")

        if output_dir is None:
            temp_dir = tempfile.mkdtemp(prefix="mermaid_")
            output_path = Path(temp_dir) / "diagram.png"
        else:
            output_path = Path(output_dir) / "diagram.png"
            output_path.parent.mkdir(parents=True, exist_ok=True)

        input_path = output_path.parent / "diagram.mmd"
        input_path.write_text(mermaid_code, encoding="utf-8")

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                [
                    self._mmdc_command,
                    "-i", str(input_path),
                    "-o", str(output_path),
                    "-b", "transparent"
                ],
                capture_output=True,
                text=True,
                check=True
            )
        )

        return str(output_path)
