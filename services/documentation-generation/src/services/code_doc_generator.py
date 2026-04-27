"""Gerador de documentação de código."""

import ast
from typing import Any

import structlog
from src.clients.llm_client_wrapper import LLMClient
from src.config.settings import get_settings
from src.models import DocFormat, DocType, Document

logger = structlog.get_logger(__name__)


CODE_DOC_PROMPT = """
Gere documentação técnica para o seguinte código:

**Arquivo:** {file_path}

**Linguagem:** {language}

**Código:**
```{language}
{code}
```

A documentação deve incluir:
1. Descrição do propósito do código
2. Parâmetros e retornos (se aplicável)
3. Exemplos de uso
4. Notas importantes

Use formatação Markdown clara.
"""


class CodeDocGenerator:
    """Gerador de documentação de código."""

    def __init__(self, llm_client: LLMClient | None = None):
        """Inicializa o gerador."""
        settings = get_settings()
        self._llm_client = llm_client or LLMClient(api_key=settings.openai_api_key)
        self._model = settings.llm_model
        self._logger = logger

    async def generate_from_code(
        self, code: str, file_path: str, language: str = "python"
    ) -> Document:
        """
        Gera documentação a partir do código fonte.

        Args:
            code: Código fonte
            file_path: Caminho do arquivo
            language: Linguagem de programação

        Returns:
            Document com a documentação gerada
        """
        self._logger.info("generating_code_docs", file=file_path, language=language)

        user_prompt = CODE_DOC_PROMPT.format(
            file_path=file_path,
            language=language,
            code=code[:5000],  # Limitar para não exceder contexto
        )

        try:
            response = await self._llm_client.generate(
                messages=[
                    {
                        "role": "system",
                        "content": "Você é um technical writer especialista em documentação de código.",
                    },
                    {"role": "user", "content": user_prompt},
                ],
                model=self._model,
            )

            content = response.choices[0].message["content"]

            return Document(
                id=f"DOC-CODE-{file_path.replace('/', '-').replace('.', '-')}",
                doc_type=DocType.API_DOCS,
                format=DocFormat.MARKDOWN,
                title=f"Documentation: {file_path}",
                content=content,
                file_path=file_path,
                metadata={"language": language, "original_file": file_path},
            )

        except Exception as e:
            self._logger.error("failed_to_generate_code_docs", error=str(e))
            raise

    def extract_functions(self, code: str, language: str = "python") -> list[dict[str, Any]]:
        """
        Extrai funções/classes do código para análise.

        Args:
            code: Código fonte
            language: Linguagem de programação

        Returns:
            Lista de funções/classes encontradas
        """
        if language == "python":
            return self._extract_python(code)
        return []

    def _extract_python(self, code: str) -> list[dict[str, Any]]:
        """Extrai funções/classes de código Python."""
        try:
            tree = ast.parse(code)
            items = []

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    items.append(
                        {
                            "type": "function",
                            "name": node.name,
                            "lineno": node.lineno,
                            "docstring": ast.get_docstring(node),
                        }
                    )
                elif isinstance(node, ast.ClassDef):
                    items.append(
                        {
                            "type": "class",
                            "name": node.name,
                            "lineno": node.lineno,
                            "docstring": ast.get_docstring(node),
                        }
                    )

            return items
        except Exception:
            return []

    async def generate_for_project(
        self, files: list[dict[str, str]], project_name: str
    ) -> Document:
        """
        Gera documentação completa para um projeto.

        Args:
            files: Lista de arquivos {path: content}
            project_name: Nome do projeto

        Returns:
            Document com documentação do projeto
        """
        self._logger.info("generating_project_docs", project=project_name, files=len(files))

        user_prompt = f"""
Gere documentação técnica completa para o projeto {project_name}.

O projeto contém {len(files)} arquivos:

{self._summarize_files(files)}

A documentação deve incluir:
1. Visão geral do projeto
2. Arquitetura e componentes
3. Principais funcionalidades
4. Como executar
5. Estrutura de diretórios
"""
        system_prompt = (
            "Você é um technical writer especialista em documentação de projetos de software."
        )

        try:
            response = await self._llm_client.generate(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                model=self._model,
            )

            content = response.choices[0].message["content"]

            return Document(
                id=f"DOC-PROJ-{project_name.lower().replace(' ', '-')}",
                doc_type=DocType.ARCHITECTURE,
                format=DocFormat.MARKDOWN,
                title=f"{project_name} Documentation",
                content=content,
                file_path=f"docs/{project_name}/README.md",
                metadata={"project": project_name, "files_count": len(files)},
            )

        except Exception as e:
            self._logger.error("failed_to_generate_project_docs", error=str(e))
            raise

    def _summarize_files(self, files: list[dict[str, str]]) -> str:
        """Cria resumo dos arquivos para o prompt."""
        summary = []
        for file_info in files[:20]:  # Limitar a 20 arquivos
            path = file_info.get("path", "")
            content = file_info.get("content", "")
            summary.append(f"- {path}")

            if len(content) > 0:
                # Extrair primeiras linhas relevantes
                lines = content.split("\n")[:5]
                summary.extend([f"  {line}" for line in lines[:3]])
            summary.append("")

        return "\n".join(summary)
