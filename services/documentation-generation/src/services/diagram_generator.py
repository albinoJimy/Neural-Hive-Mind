"""Gerador de diagramas Mermaid."""

from typing import List, Optional
from openai import AsyncOpenAI
import structlog

from src.models import DocType, DocFormat, Document
from src.config.settings import get_settings

logger = structlog.get_logger(__name__)

DIAGRAM_GENERATION_PROMPT = """
Gere um diagrama Mermaid para o seguinte cenário:

**Descrição:** {description}

**Tipo:** {diagram_type}

Tipos suportados:
- sequence: Diagrama de sequência
- flowchart: Fluxograma
- er: Diagrama entidade-relacionamento
- class: Diagrama de classes

Gere apenas o código Mermaid, sem formatação adicional.
"""


class DiagramGenerator:
    """Gerador de diagramas Mermaid."""

    def __init__(self, llm_client: Optional[AsyncOpenAI] = None):
        """Inicializa o gerador."""
        settings = get_settings()
        self._llm_client = llm_client or AsyncOpenAI(api_key=settings.openai_api_key)
        self._model = settings.llm_model
        self._logger = logger

    async def generate(
        self, description: str, diagram_type: str = "sequence", metadata: Optional[dict] = None
    ) -> Document:
        """
        Gera diagrama Mermaid.

        Args:
            description: Descrição do diagrama
            diagram_type: Tipo de diagrama
            metadata: Metadados adicionais

        Returns:
            Document com o diagrama gerado
        """
        self._logger.info("generating_diagram", type=diagram_type)

        prompt = DIAGRAM_GENERATION_PROMPT.format(
            description=description, diagram_type=diagram_type
        )

        try:
            response = await self._llm_client.chat.completions.create(
                model=self._model,
                messages=[
                    {
                        "role": "system",
                        "content": "Você é um especialista em diagramas UML e Mermaid.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=2000,
            )

            content = response.choices[0].message.content

            # Limpar código markdown se presente
            if "```" in content:
                import re

                match = re.search(r"```(?:mermaid)?\s*\n(.*?)\n```", content, re.DOTALL)
                if match:
                    content = match.group(1)

            return Document(
                id=f"DOC-DIAG-{diagram_type}-{hash(description) % 10000}",
                doc_type=DocType.DIAGRAM,
                format=DocFormat.MERMAID,
                title=f"{diagram_type.title()} Diagram",
                content=content,
                metadata=metadata or {},
            )

        except Exception as e:
            self._logger.error("failed_to_generate_diagram", error=str(e))
            raise
