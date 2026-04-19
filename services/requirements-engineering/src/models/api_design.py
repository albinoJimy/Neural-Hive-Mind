"""Modelos para design de API."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class HTTPMethod(str, Enum):
    """Métodos HTTP suportados."""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    OPTIONS = "OPTIONS"
    HEAD = "HEAD"


class ParameterLocation(str, Enum):
    """Localização de parâmetros."""

    QUERY = "query"
    PATH = "path"
    HEADER = "header"
    COOKIE = "cookie"


class ParameterType(str, Enum):
    """Tipos de parâmetros."""

    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"


class ResponseType(str, Enum):
    """Tipos de resposta padrão."""

    SUCCESS = "success"
    ERROR = "error"
    VALIDATION = "validation"
    NOT_FOUND = "not_found"
    UNAUTHORIZED = "unauthorized"


class APIParameter(BaseModel):
    """Parâmetro de endpoint."""

    name: str = Field(..., description="Nome do parâmetro")
    param_type: ParameterType = Field(default=ParameterType.STRING, description="Tipo de dado")
    location: ParameterLocation = Field(default=ParameterLocation.QUERY, description="Localização")
    required: bool = Field(default=False, description="É obrigatório")
    description: str | None = Field(default=None, description="Descrição")
    default_value: Any = Field(default=None, description="Valor padrão")
    example: Any = Field(default=None, description="Exemplo de uso")


class APIResponse(BaseModel):
    """Resposta de endpoint."""

    status_code: int = Field(..., description="Código HTTP")
    description: str = Field(..., description="Descrição da resposta")
    response_type: ResponseType = Field(
        default=ResponseType.SUCCESS, description="Tipo de resposta"
    )
    schema: dict[str, Any] | None = Field(default=None, description="Schema JSON da resposta")
    example: dict[str, Any] | None = Field(default=None, description="Exemplo de resposta")


class RequestBody(BaseModel):
    """Body de requisição."""

    content_type: str = Field(default="application/json", description="Content-Type")
    required: bool = Field(default=True, description="É obrigatório")
    schema: dict[str, Any] | None = Field(default=None, description="Schema JSON")
    example: dict[str, Any] | None = Field(default=None, description="Exemplo de body")
    description: str | None = Field(default=None, description="Descrição")


class APIEndpoint(BaseModel):
    """Endpoint de API."""

    id: str = Field(..., description="ID único")
    path: str = Field(..., description="Caminho do endpoint")
    method: HTTPMethod = Field(..., description="Método HTTP")
    summary: str = Field(..., description="Resumo da operação")
    description: str | None = Field(default=None, description="Descrição detalhada")
    tags: list[str] = Field(default_factory=list, description="Tags para agrupamento")
    parameters: list[APIParameter] = Field(default_factory=list, description="Parâmetros")
    request_body: RequestBody | None = Field(default=None, description="Body da requisição")
    responses: list[APIResponse] = Field(default_factory=list, description="Respostas possíveis")
    security: list[str] = Field(default_factory=list, description="Requisitos de segurança")
    deprecated: bool = Field(default=False, description="Está deprecated")
    rate_limit: str | None = Field(default=None, description="Limite de rate limiting")


class APISecurity(BaseModel):
    """Configuração de segurança da API."""

    type: str = Field(..., description="Tipo de segurança (apiKey, oauth2, jwt)")
    scheme_name: str = Field(..., description="Nome do esquema")
    description: str | None = Field(default=None, description="Descrição")
    flow: str | None = Field(default=None, description="Flow OAuth2 (implicit, password, etc.)")
    scopes: list[str] = Field(default_factory=list, description="Scopes OAuth2")


class APIServer(BaseModel):
    """Servidor da API."""

    url: str = Field(..., description="URL base do servidor")
    description: str | None = Field(default=None, description="Descrição")
    environment: str = Field(default="production", description="Ambiente")


class APIDesign(BaseModel):
    """Design completo de API."""

    id: str = Field(..., description="ID único")
    name: str = Field(..., description="Nome da API")
    version: str = Field(default="1.0.0", description="Versão da API")
    description: str | None = Field(default=None, description="Descrição da API")
    cognitive_plan_id: str | None = Field(default=None, description="ID do plano cognitivo")
    requirements_set_id: str | None = Field(
        default=None, description="ID do conjunto de requisitos"
    )

    servers: list[APIServer] = Field(default_factory=list, description="Servidores")
    endpoints: list[APIEndpoint] = Field(default_factory=list, description="Endpoints")
    security_schemes: list[APISecurity] = Field(
        default_factory=list, description="Esquemas de segurança"
    )
    tags: list[dict[str, str]] = Field(default_factory=list, description="Tags globais")

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Data de criação"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Data de atualização"
    )

    def add_endpoint(self, endpoint: APIEndpoint) -> None:
        """Adiciona um endpoint ao design."""
        self.endpoints.append(endpoint)
        self.updated_at = datetime.now(timezone.utc)

    def add_security_scheme(self, security: APISecurity) -> None:
        """Adiciona um esquema de segurança."""
        self.security_schemes.append(security)
        self.updated_at = datetime.now(timezone.utc)

    def get_endpoints_by_tag(self, tag: str) -> list[APIEndpoint]:
        """Retorna endpoints filtrados por tag."""
        return [ep for ep in self.endpoints if tag in ep.tags]

    def get_endpoints_by_method(self, method: HTTPMethod) -> list[APIEndpoint]:
        """Retorna endpoints filtrados por método."""
        return [ep for ep in self.endpoints if ep.method == method]
