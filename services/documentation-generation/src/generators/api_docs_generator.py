"""Gerador de documentação de API (OpenAPI/Swagger)."""

import json
from datetime import datetime, timezone
from typing import Any

import structlog
from openai import AsyncOpenAI
from src.config.settings import get_settings
from src.models import DocFormat, DocType, Document

logger = structlog.get_logger(__name__)


class APIDocsGenerator:
    """Gerador de especificações OpenAPI e documentação de API."""

    def __init__(self, llm_client: AsyncOpenAI | None = None):
        """Inicializa o gerador."""
        settings = get_settings()
        self._llm_client = llm_client or AsyncOpenAI(api_key=settings.openai_api_key)
        self._model = settings.llm_model
        self._logger = logger

    def generate_openapi(
        self,
        title: str,
        version: str,
        endpoints: list[dict[str, Any]],
        base_url: str = "/",
        description: str | None = None,
    ) -> dict[str, Any]:
        """
        Gera especificação OpenAPI.

        Args:
            title: Título da API
            version: Versão da API
            endpoints: Lista de endpoints
            base_url: URL base
            description: Descrição da API

        Returns:
            Dicionário OpenAPI válido
        """
        self._logger.info("generating_openapi_spec", title=title, endpoints=len(endpoints))

        spec = {
            "openapi": "3.0.0",
            "info": {
                "title": title,
                "version": version,
                "description": description or f"API documentation for {title}",
            },
            "servers": [{"url": base_url}],
            "paths": {},
            "components": {
                "schemas": {},
            },
        }

        for endpoint in endpoints:
            path = endpoint.get("path", "/")
            method = endpoint.get("method", "GET").lower()

            if path not in spec["paths"]:
                spec["paths"][path] = {}

            operation = {
                "summary": endpoint.get("summary", f"{method.upper()} {path}"),
                "description": endpoint.get("description", ""),
                "operationId": endpoint.get("operation_id", f"{method}_{path.replace('/', '_')}"),
                "tags": endpoint.get("tags", []),
            }

            # Parâmetros
            params = endpoint.get("parameters", [])
            if params:
                operation["parameters"] = [
                    {
                        "name": p.get("name"),
                        "in": p.get("in", "query"),
                        "required": p.get("required", False),
                        "schema": {"type": p.get("type", "string")},
                        "description": p.get("description", ""),
                    }
                    for p in params
                ]

            # Request body
            request_body = endpoint.get("request_body")
            if request_body:
                operation["requestBody"] = {
                    "required": request_body.get("required", True),
                    "content": {"application/json": {"schema": request_body.get("schema", {})}},
                }

            # Responses
            responses = endpoint.get("responses", {})
            if responses:
                operation["responses"] = {}
                for status_code, response in responses.items():
                    operation["responses"][status_code] = {
                        "description": response.get("description", ""),
                    }
                    if "schema" in response:
                        operation["responses"][status_code]["content"] = {
                            "application/json": {"schema": response["schema"]}
                        }

            spec["paths"][path][method] = operation

        return spec

    def generate_openapi_json(self, *args, **kwargs) -> str:
        """
        Gera especificação OpenAPI como JSON string.

        Args:
            *args: Argumentos para generate_openapi
            **kwargs: Argumentos para generate_openapi

        Returns:
            JSON string da especificação
        """
        spec = self.generate_openapi(*args, **kwargs)
        return json.dumps(spec, indent=2)

    async def generate_markdown(
        self,
        title: str,
        endpoints: list[dict[str, Any]],
        base_url: str = "/",
        description: str | None = None,
    ) -> Document:
        """
        Gera documentação de API em Markdown usando LLM.

        Args:
            title: Título da API
            endpoints: Lista de endpoints
            base_url: URL base
            description: Descrição

        Returns:
            Document com a documentação em Markdown
        """
        self._logger.info("generating_api_markdown", title=title)

        # Gerar OpenAPI spec primeiro
        openapi_spec = self.generate_openapi(
            title=title,
            version="1.0.0",
            endpoints=endpoints,
            base_url=base_url,
            description=description,
        )

        # Usar LLM para gerar documentação melhorada
        prompt = f"""
Gere documentação de API em Markdown profissional para a seguinte especificação OpenAPI:

**Título:** {title}
**URL Base:** {base_url}
**Descrição:** {description or "N/A"}

**Endpoints:**
{self._format_endpoints(endpoints)}

A documentação deve incluir:
1. Descrição geral da API
2. Autenticação (se aplicável)
3. Seção de endpoints organizada por recurso
4. Para cada endpoint: método, path, descrição, parâmetros, body schema, responses
5. Exemplos de requisição/resposta em JSON
6. Códigos de erro comuns

Use formatação Markdown clara com tabelas e blocos de código.
"""

        try:
            response = await self._llm_client.chat.completions.create(
                model=self._model,
                messages=[
                    {
                        "role": "system",
                        "content": "Você é um technical writer especialista em documentação de APIs.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.5,
                max_tokens=4000,
            )

            content = response.choices[0].message.content

            return Document(
                id=f"DOC-API-{title.lower().replace(' ', '-')}",
                doc_type=DocType.API_DOCS,
                format=DocFormat.MARKDOWN,
                title=f"{title} API Documentation",
                content=content,
                file_path=f"docs/api/{title.lower().replace(' ', '-')}.md",
                metadata={
                    "title": title,
                    "base_url": base_url,
                    "endpoints_count": len(endpoints),
                    "openapi_spec": openapi_spec,
                },
            )

        except Exception as e:
            self._logger.error("failed_to_generate_api_docs", error=str(e))
            # Fallback para documentação gerada sem LLM
            content = self._generate_fallback_markdown(
                title, endpoints, base_url, description, openapi_spec
            )
            return Document(
                id=f"DOC-API-{title.lower().replace(' ', '-')}",
                doc_type=DocType.API_DOCS,
                format=DocFormat.MARKDOWN,
                title=f"{title} API Documentation",
                content=content,
                file_path=f"docs/api/{title.lower().replace(' ', '-')}.md",
                metadata={
                    "title": title,
                    "base_url": base_url,
                    "endpoints_count": len(endpoints),
                },
            )

    def _format_endpoints(self, endpoints: list[dict]) -> str:
        """Formata endpoints para o prompt."""
        lines = []
        for ep in endpoints:
            method = ep.get("method", "GET").upper()
            path = ep.get("path", "/")
            desc = ep.get("description", "")
            lines.append(f"- {method} {path}: {desc}")
        return "\n".join(lines)

    def _generate_fallback_markdown(
        self,
        title: str,
        endpoints: list[dict],
        base_url: str,
        description: str | None,
        openapi_spec: dict,
    ) -> str:
        """Gera documentação Markdown básica sem LLM."""
        # Descrição condicional
        desc_section = ""
        if description:
            desc_section = description + "\n\n"

        content = f"""# {title} API Documentation

**Base URL:** `{base_url}`

{desc_section}
## OpenAPI Specification

```json
{json.dumps(openapi_spec, indent=2)}
```

## Endpoints

"""

        for endpoint in endpoints:
            method = endpoint.get("method", "GET").upper()
            path = endpoint.get("path", "/")
            desc = endpoint.get("description", "")
            params = endpoint.get("parameters", [])
            request_body = endpoint.get("request_body", {})
            responses = endpoint.get("responses", {})

            content += f"### {method} {path}\n\n"
            if desc:
                content += f"{desc}\n\n"

            if params:
                content += "**Parameters:**\n\n"
                content += "| Name | In | Type | Required | Description |\n"
                content += "|------|-----|------|----------|-------------|\n"
                for p in params:
                    content += f"| {p.get('name', '-')} | {p.get('in', 'query')} | {p.get('type', 'string')} | {p.get('required', False)} | {p.get('description', '')} |\n"
                content += "\n"

            if request_body:
                content += "**Request Body:**\n\n"
                content += (
                    "```json\n" + json.dumps(request_body.get("schema", {}), indent=2) + "\n```\n\n"
                )

            if responses:
                content += "**Responses:**\n\n"
                for status, response in responses.items():
                    content += f"- **{status}**: {response.get('description', '')}\n"
                content += "\n"

            content += "---\n\n"

        content += (
            f"\n*Generated on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC*\n"
        )

        return content

    def generate_swagger_ui_html(
        self,
        openapi_spec: dict[str, Any],
        title: str = "API Documentation",
    ) -> str:
        """
        Gera HTML com Swagger UI.

        Args:
            openapi_spec: Especificação OpenAPI
            title: Título da página

        Returns:
            HTML com Swagger UI embedado
        """
        spec_json = json.dumps(openapi_spec)

        return f"""<!DOCTYPE html>
<html>
<head>
    <title>{title}</title>
    <link rel="stylesheet" type="text/css" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css">
    <style>
        body {{ margin: 0; padding: 0; }}
        #swagger-ui {{ max-width: 1460px; margin: 0 auto; }}
    </style>
</head>
<body>
    <div id="swagger-ui"></div>
    <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
    <script>
    window.onload = function() {{
        const ui = SwaggerUIBundle({{
            spec: {spec_json},
            dom_id: '#swagger-ui',
            presets: [
                SwaggerUIBundle.presets.apis,
                SwaggerUIBundle.SwaggerUIStandalonePreset
            ],
            layout: "BaseLayout",
            deepLinking: true
        }});
        window.ui = ui;
    }};
    </script>
</body>
</html>
"""
