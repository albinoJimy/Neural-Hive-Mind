"""Models package for Documentation Generation service."""

import hashlib
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


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
    version: str = Field(default="1.0.0", description="Versão do documento")
    checksum: str | None = Field(None, description="Hash MD5 do conteúdo para verificação")
    word_count: int = Field(default=0, description="Número de palavras no documento")
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @model_validator(mode="after")
    def calculate_metadata(self) -> "Document":
        """Calcula checksum e word_count após definir o conteúdo."""
        if self.content:
            self.checksum = hashlib.md5(self.content.encode()).hexdigest()
            self.word_count = len(self.content.split())
        else:
            self.checksum = None
            self.word_count = 0
        return self

    def increment_version(self) -> str:
        """Incrementa a versão do documento (patch version)."""
        major, minor, patch = map(int, self.version.split("."))
        patch += 1
        self.version = f"{major}.{minor}.{patch}"
        return self.version

    def update_content(self, new_content: str) -> None:
        """Atualiza o conteúdo e recalcula checksum e word_count."""
        self.content = new_content
        if new_content:
            self.checksum = hashlib.md5(new_content.encode()).hexdigest()
            self.word_count = len(new_content.split())
        else:
            self.checksum = None
            self.word_count = 0


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


class DiagramType(str, Enum):
    """Tipo de diagrama."""

    SEQUENCE = "sequence"
    FLOWCHART = "flowchart"
    C4 = "c4"
    ER = "er"
    CLASS = "class"
    STATE = "state"
    GANTT = "gantt"


class Diagram(BaseModel):
    """Diagrama gerado."""

    id: str = Field(..., description="ID único")
    diagram_type: DiagramType = Field(..., description="Tipo de diagrama")
    title: str = Field(..., description="Título do diagrama")
    mermaid_code: str = Field(..., description="Código Mermaid")
    rendered_content: str | None = Field(None, description="Conteúdo renderizado (SVG/PNG)")
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class DocumentationSet(BaseModel):
    """Conjunto de documentos para um projeto."""

    id: str = Field(..., description="ID único")
    project_id: str = Field(..., description="ID do projeto")
    documents: list[Document] = Field(default_factory=list, description="Lista de documentos")
    diagrams: list[Diagram] = Field(default_factory=list, description="Diagramas associados")
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime | None = Field(None, description="Data da última atualização")

    def add_document(self, document: Document) -> None:
        """Adiciona um documento ao conjunto."""
        self.documents.append(document)
        self.updated_at = datetime.now(timezone.utc)

    def add_diagram(self, diagram: Diagram) -> None:
        """Adiciona um diagrama ao conjunto."""
        self.diagrams.append(diagram)
        self.updated_at = datetime.now(timezone.utc)

    def get_by_type(self, doc_type: DocType) -> list[Document]:
        """Filtra documentos por tipo."""
        return [d for d in self.documents if d.doc_type == doc_type]

    def get_diagrams_by_type(self, diagram_type: DiagramType) -> list[Diagram]:
        """Filtra diagramas por tipo."""
        return [d for d in self.diagrams if d.diagram_type == diagram_type]


__all__ = [
    "APIDocsRequest",
    "Diagram",
    "DiagramType",
    "DocFormat",
    "DocType",
    "Document",
    "DocumentationSet",
    "ReadmeRequest",
]
