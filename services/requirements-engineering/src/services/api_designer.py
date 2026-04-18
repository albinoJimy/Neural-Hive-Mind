"""Serviço para design de APIs RESTful."""

import json
import re
import uuid
from typing import Any

import structlog
from openai import AsyncOpenAI
from src.config.settings import get_settings
from src.models.api_design import (
    APIEndpoint,
    APIDesign,
    APIParameter,
    APIResponse,
    APISecurity,
    APIServer,
    HTTPMethod,
    ParameterLocation,
    ParameterType,
    RequestBody,
    ResponseType,
)
from src.models.requirements import RequirementsSet

logger = structlog.get_logger(__name__)

API_DESIGN_PROMPT = """
Você é um arquiteto de API especialista em RESTful design. Analise os seguintes requisitos e proponha uma API RESTful.

**Requisitos:**
{requirements_text}

**Instruções:**
1. Identifique os recursos principais do domínio
2. Para cada recurso, defina endpoints CRUD (Create, Read, Update, Delete)
3. Para cada endpoint, defina métodos HTTP, parâmetros, request body e responses
4. Inclua códigos de status apropriados (200, 201, 204, 400, 404, etc.)
5. Retorne APENAS JSON válido

**Formato JSON:**
{{
  "name": "Nome da API",
  "version": "1.0.0",
  "description": "Descrição da API",
  "base_path": "/api/v1",
  "servers": [
    {{
      "url": "https://api.example.com",
      "description": "Produção",
      "environment": "production"
    }}
  ],
  "tags": [
    {{"name": "resources", "description": "Operações de recursos"}},
    {{"name": "auth", "description": "Autenticação"}}
  ],
  "security": [
    {{
      "type": "jwt",
      "scheme_name": "bearerAuth",
      "description": "Autenticação via JWT Bearer token"
    }}
  ],
  "endpoints": [
    {{
      "path": "/resources",
      "method": "GET",
      "summary": "Listar recursos",
      "description": "Retorna lista paginada de recursos",
      "tags": ["resources"],
      "parameters": [
        {{
          "name": "page",
          "type": "integer",
          "location": "query",
          "required": false,
          "description": "Número da página",
          "default_value": 1,
          "example": 1
        }},
        {{
          "name": "limit",
          "type": "integer",
          "location": "query",
          "required": false,
          "description": "Itens por página",
          "default_value": 20,
          "example": 20
        }}
      ],
      "request_body": null,
      "responses": [
        {{
          "status_code": 200,
          "description": "Lista de recursos retornada com sucesso",
          "response_type": "success",
          "schema": {{
            "type": "object",
            "properties": {{
              "data": {{
                "type": "array",
                "items": {{"type": "object"}}
              }},
              "pagination": {{
                "type": "object",
                "properties": {{
                  "page": {{"type": "integer"}},
                  "limit": {{"type": "integer"}},
                  "total": {{"type": "integer"}}
                }}
              }}
            }}
          }}
        }}
      ],
      "security": ["bearerAuth"],
      "deprecated": false,
      "rate_limit": "100/minute"
    }}
  ]
}}
"""


class APIDesigner:
    """Serviço para design de APIs RESTful usando LLM."""

    def __init__(self, llm_client: AsyncOpenAI | None = None):
        """Inicializa o APIDesigner.

        Args:
            llm_client: Cliente OpenAI (opcional, cria padrão se não fornecido)
        """
        settings = get_settings()
        self._llm_client = llm_client or AsyncOpenAI(api_key=settings.openai_api_key)
        self._model = settings.llm_model
        self._logger = logger

    async def design_from_requirements(
        self,
        requirements_set: RequirementsSet,
    ) -> APIDesign:
        """Desenha uma API RESTful a partir de requisitos.

        Args:
            requirements_set: Conjunto de requisitos

        Returns:
            APIDesign com endpoints, segurança e documentação
        """
        self._logger.info(
            "designing_api",
            requirements_set_id=requirements_set.id,
            total_requirements=len(requirements_set.requirements),
        )

        # Preparar texto dos requisitos
        requirements_text = "\n".join(
            [
                f"- {r.title}: {r.description[:200]}..."
                for r in requirements_set.requirements[:10]
            ]
        )

        prompt = API_DESIGN_PROMPT.format(requirements_text=requirements_text)

        try:
            response = await self._llm_client.chat.completions.create(
                model=self._model,
                messages=[
                    {
                        "role": "system",
                        "content": "Você é um arquiteto de API especialista em RESTful design.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.5,
                max_tokens=4000,
            )

            content = response.choices[0].message.content

            # Extrair JSON da resposta
            json_match = self._extract_json(content)
            design_data = json.loads(json_match) if json_match else json.loads(content)

            # Criar APIDesign
            design = APIDesign(
                id=f"API-{uuid.uuid4().hex[:8].upper()}",
                name=design_data.get("name", "API"),
                version=design_data.get("version", "1.0.0"),
                description=design_data.get("description"),
                cognitive_plan_id=requirements_set.cognitive_plan_id,
                requirements_set_id=requirements_set.id,
            )

            # Processar servidores
            for server_data in design_data.get("servers", []):
                server = APIServer(**server_data)
                design.servers.append(server)

            # Processar tags globais
            for tag_data in design_data.get("tags", []):
                design.tags.append(tag_data)

            # Processar esquemas de segurança
            for security_data in design_data.get("security", []):
                security = APISecurity(**security_data)
                design.add_security_scheme(security)

            # Processar endpoints
            for endpoint_data in design_data.get("endpoints", []):
                endpoint = self._create_endpoint(endpoint_data)
                design.add_endpoint(endpoint)

            self._logger.info(
                "api_designed",
                design_id=design.id,
                endpoints_count=len(design.endpoints),
                security_schemes_count=len(design.security_schemes),
            )

            return design

        except Exception:
            self._logger.exception("failed_to_design_api")
            raise

    def _create_endpoint(self, endpoint_data: dict[str, Any]) -> APIEndpoint:
        """Cria um APIEndpoint a partir de dados JSON.

        Args:
            endpoint_data: Dados do endpoint

        Returns:
            APIEndpoint populado
        """
        endpoint_id = f"EP-{uuid.uuid4().hex[:6].upper()}"

        # Processar parâmetros
        parameters = []
        for param_data in endpoint_data.get("parameters", []):
            param = APIParameter(
                name=param_data.get("name", ""),
                param_type=self._parse_param_type(param_data.get("type", "string")),
                location=self._parse_param_location(param_data.get("location", "query")),
                required=param_data.get("required", False),
                description=param_data.get("description"),
                default_value=param_data.get("default_value"),
                example=param_data.get("example"),
            )
            parameters.append(param)

        # Processar request body
        request_body = None
        if endpoint_data.get("request_body"):
            body_data = endpoint_data["request_body"]
            request_body = RequestBody(
                content_type=body_data.get("content_type", "application/json"),
                required=body_data.get("required", True),
                schema=body_data.get("schema"),
                example=body_data.get("example"),
                description=body_data.get("description"),
            )

        # Processar respostas
        responses = []
        for resp_data in endpoint_data.get("responses", []):
            response = APIResponse(
                status_code=resp_data.get("status_code", 200),
                description=resp_data.get("description", ""),
                response_type=self._parse_response_type(resp_data.get("response_type", "success")),
                schema=resp_data.get("schema"),
                example=resp_data.get("example"),
            )
            responses.append(response)

        return APIEndpoint(
            id=endpoint_id,
            path=endpoint_data.get("path", "/"),
            method=self._parse_http_method(endpoint_data.get("method", "GET")),
            summary=endpoint_data.get("summary", ""),
            description=endpoint_data.get("description"),
            tags=endpoint_data.get("tags", []),
            parameters=parameters,
            request_body=request_body,
            responses=responses,
            security=endpoint_data.get("security", []),
            deprecated=endpoint_data.get("deprecated", False),
            rate_limit=endpoint_data.get("rate_limit"),
        )

    def _parse_http_method(self, value: str) -> HTTPMethod:
        """Converte string para HTTPMethod."""
        try:
            return HTTPMethod[value.upper()]
        except KeyError:
            return HTTPMethod.GET

    def _parse_param_type(self, value: str) -> ParameterType:
        """Converte string para ParameterType."""
        mapping = {
            "string": ParameterType.STRING,
            "integer": ParameterType.INTEGER,
            "number": ParameterType.NUMBER,
            "boolean": ParameterType.BOOLEAN,
            "array": ParameterType.ARRAY,
            "object": ParameterType.OBJECT,
        }
        return mapping.get(value.lower(), ParameterType.STRING)

    def _parse_param_location(self, value: str) -> ParameterLocation:
        """Converte string para ParameterLocation."""
        mapping = {
            "query": ParameterLocation.QUERY,
            "path": ParameterLocation.PATH,
            "header": ParameterLocation.HEADER,
            "cookie": ParameterLocation.COOKIE,
        }
        return mapping.get(value.lower(), ParameterLocation.QUERY)

    def _parse_response_type(self, value: str) -> ResponseType:
        """Converte string para ResponseType."""
        mapping = {
            "success": ResponseType.SUCCESS,
            "error": ResponseType.ERROR,
            "validation": ResponseType.VALIDATION,
            "not_found": ResponseType.NOT_FOUND,
            "unauthorized": ResponseType.UNAUTHORIZED,
        }
        return mapping.get(value.lower(), ResponseType.SUCCESS)

    def _extract_json(self, text: str) -> str | None:
        """Extrai JSON de texto markdown."""
        # Tentar encontrar JSON em blocos markdown
        json_match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
        if json_match:
            return json_match.group(1)

        # Tentar encontrar JSON sem markdown
        json_match = re.search(r"\{.*\}", text, re.DOTALL)
        if json_match:
            return json_match.group(0)

        return None
