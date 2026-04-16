"""Models package for Documentation Generation service."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DocType(str, Enum):
    """Tipo de documento."""

    README = "readme"
    API_DOCS = "api_docs"
    USER_GUIDE = "user_guide"
    ARCHITECTURE = "architecture"
    DIAGRAM = "diagram"


class DocFormat(str, Enum):
    """Formato de documento."""

    MARKDOWN = "md"
    HTML = "html"
    PDF = "pdf"
    MERMAID = "mmd"


class Document(BaseModel):
    """Documento gerado."""

    id: str = Field(..., description="ID único")
    doc_type: DocType = Field(..., description="Tipo de documento")
    format: DocFormat = Field(default=DocFormat.MARKDOWN)
    title: str = Field(..., description="Título do documento")
    content: str = Field(..., description="Conteúdo do documento")
    file_path: str | None = Field(None, description="Caminho do arquivo gerado")
    requirements_id: str | None = Field(None)
    user_story_id: str | None = Field(None)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ReadmeRequest(BaseModel):
    """Request para geração de README."""

    project_name: str = Field(..., description="Nome do projeto")
    project_description: str = Field(..., description="Descrição do projeto")
    features: list[str] = Field(default_factory=list, description="Funcionalidades principais")
    installation: str | None = Field(None, description="Instruções de instalação")
    usage: str | None = Field(None, description="Instruções de uso")
    tech_stack: str | None = Field(None, description="Stack tecnológico")


class APIDocsRequest(BaseModel):
    """Request para geração de documentação de API."""

    endpoints: list[dict] = Field(..., description="Lista de endpoints da API")
    service_name: str = Field(..., description="Nome do serviço")
    base_url: str = Field(..., description="URL base da API")
    description: str | None = Field(None, description="Descrição do serviço")
