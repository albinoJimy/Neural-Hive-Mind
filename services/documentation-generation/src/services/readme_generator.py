"""Gerador de documentação README usando LLM."""

from typing import Optional
from openai import AsyncOpenAI
import structlog

from src.models import DocType, DocFormat, Document, ReadmeRequest
from src.config.settings import get_settings

logger = structlog.get_logger(__name__)

README_PROMPT = """
Gere um README.md completo para o seguinte projeto:

**Nome do Projeto:** {project_name}

**Descrição:** {project_description}

**Funcionalidades:**
{features}

**Instalação:**
{installation}

**Uso:**
{usage}

**Stack Tecnológico:**
{tech_stack}

O README deve seguir este formato:

# {project_name}

{project_description}

## Funcionalidades

{features_list}

## Instalação

{installation_content}

## Uso

{usage_content}

## Stack Tecnológico

{tech_stack_content}

## Licença

MIT License
"""


class ReadmeGenerator:
    """Gerador de documentação README."""

    def __init__(self, llm_client: Optional[AsyncOpenAI] = None):
        """Inicializa o gerador."""
        settings = get_settings()
        self._llm_client = llm_client or AsyncOpenAI(api_key=settings.openai_api_key)
        self._model = settings.llm_model
        self._logger = logger

    async def generate(self, request: ReadmeRequest) -> Document:
        """
        Gera README a partir da request.

        Args:
            request: Dados para geração do README

        Returns:
            Document com o README gerado
        """
        self._logger.info("generating_readme", project=request.project_name)

        features_text = "\n".join([f"- {f}" for f in request.features]) if request.features else "A definir"

        prompt = README_PROMPT.format(
            project_name=request.project_name,
            project_description=request.project_description,
            features=features_text,
            installation=request.installation or "A definir",
            usage=request.usage or "A definir",
            tech_stack=request.tech_stack or "A definir"
        )

        try:
            response = await self._llm_client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": "Você é um technical writer especialista."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=4000
            )

            content = response.choices[0].message.content

            return Document(
                id=f"DOC-README-{request.project_name.replace(' ', '-').lower()}",
                doc_type=DocType.README,
                format=DocFormat.MARKDOWN,
                title=f"{request.project_name} README",
                content=content,
                file_path="README.md"
            )

        except Exception as e:
            self._logger.error("failed_to_generate_readme", error=str(e))
            raise
