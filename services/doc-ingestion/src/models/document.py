"""Modelos de domínio para documentos."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class DocumentFormat(str, Enum):
    """Formato de documento suportado."""

    PDF = "pdf"
    DOCX = "docx"
    VSD = "vsd"
    VSDX = "vsdx"
    POSTMAN = "postman"


class DocumentStatus(str, Enum):
    """Status de processamento de documento."""

    UPLOADED = "uploaded"
    PARSING = "parsing"
    PARSED = "parsed"
    EXTRACTION = "extraction"
    EXTRACTED = "extracted"
    APPROVED = "approved"
    FAILED = "failed"


class Document(BaseModel):
    """Documento processado pelo serviço."""

    id: str = Field(..., description="ID único do documento")
    filename: str = Field(..., description="Nome do arquivo original")
    format: DocumentFormat = Field(..., description="Formato do documento")
    status: DocumentStatus = Field(
        default=DocumentStatus.UPLOADED, description="Status de processamento"
    )
    file_size_bytes: int = Field(..., ge=0, description="Tamanho do arquivo em bytes")
    s3_key: str = Field(..., description="Chave S3 do arquivo")
    uploaded_by: str = Field(..., description="Usuário que fez upload")

    # Metadados opcionais
    title: Optional[str] = Field(None, description="Título do documento")
    description: Optional[str] = Field(None, description="Descrição do documento")
    project_id: Optional[str] = Field(None, description="ID do projeto relacionado")
    tags: list[str] = Field(default_factory=list, description="Tags para categorização")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Metadados adicionais")

    # Resultados de parsing
    parsed_text: Optional[str] = Field(None, description="Texto extraído do documento")
    entity_count: int = Field(default=0, ge=0, description="Número de entidades extraídas")
    extracted_entity_types: list[str] = Field(
        default_factory=list, description="Tipos de entidades extraídas"
    )
    parsing_error: Optional[str] = Field(None, description="Erro de parsing, se houver")

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Data de upload")
    updated_at: Optional[datetime] = Field(None, description="Data da última atualização")
    parsed_at: Optional[datetime] = Field(None, description="Data do parsing")
    extracted_at: Optional[datetime] = Field(None, description="Data da extração de entidades")

    version: int = Field(default=1, description="Versão do registro")


class DocumentCreate(BaseModel):
    """DTO para criação de documento."""

    filename: str = Field(..., description="Nome do arquivo original")
    format: DocumentFormat = Field(..., description="Formato do documento")
    file_size_bytes: int = Field(..., ge=0, description="Tamanho do arquivo em bytes")
    s3_key: str = Field(..., description="Chave S3 do arquivo")
    uploaded_by: str = Field(..., description="Usuário que fez upload")
    title: Optional[str] = Field(None, description="Título do documento")
    description: Optional[str] = Field(None, description="Descrição do documento")
    project_id: Optional[str] = Field(None, description="ID do projeto relacionado")
    tags: list[str] = Field(default_factory=list, description="Tags para categorização")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Metadados adicionais")


class DocumentUpdate(BaseModel):
    """DTO para atualização de documento."""

    status: Optional[DocumentStatus] = Field(None, description="Status de processamento")
    title: Optional[str] = Field(None, description="Título do documento")
    description: Optional[str] = Field(None, description="Descrição do documento")
    project_id: Optional[str] = Field(None, description="ID do projeto relacionado")
    tags: Optional[list[str]] = Field(None, description="Tags para categorização")
    metadata: Optional[dict[str, Any]] = Field(None, description="Metadados adicionais")
    parsed_text: Optional[str] = Field(None, description="Texto extraído do documento")
    entity_count: Optional[int] = Field(None, ge=0, description="Número de entidades extraídas")
    extracted_entity_types: Optional[list[str]] = Field(
        None, description="Tipos de entidades extraídas"
    )
    parsing_error: Optional[str] = Field(None, description="Erro de parsing, se houver")
    updated_at: Optional[datetime] = Field(None, description="Data da última atualização")
    parsed_at: Optional[datetime] = Field(None, description="Data do parsing")
    extracted_at: Optional[datetime] = Field(None, description="Data da extração de entidades")


class DocumentList(BaseModel):
    """Lista de documentos com metadados."""

    total: int = Field(..., description="Número total de documentos")
    items: list[Document] = Field(..., description="Lista de documentos")
    filters: dict[str, Any] = Field(default_factory=dict, description="Filtros aplicados")
