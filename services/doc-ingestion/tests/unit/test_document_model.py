"""Testes unitários para modelos de documento."""

from datetime import datetime

from src.models.document import (
    Document,
    DocumentCreate,
    DocumentFormat,
    DocumentStatus,
    DocumentUpdate,
)


def test_document_format_enum():
    """Testa enum DocumentFormat."""
    # Assert
    assert DocumentFormat.PDF == "pdf"
    assert DocumentFormat.DOCX == "docx"
    assert DocumentFormat.VSD == "vsd"
    assert DocumentFormat.VSDX == "vsdx"
    assert DocumentFormat.POSTMAN == "postman"


def test_document_status_enum():
    """Testa enum DocumentStatus."""
    # Assert
    assert DocumentStatus.UPLOADED == "uploaded"
    assert DocumentStatus.PARSING == "parsing"
    assert DocumentStatus.PARSED == "parsed"
    assert DocumentStatus.EXTRACTION == "extraction"
    assert DocumentStatus.EXTRACTED == "extracted"
    assert DocumentStatus.APPROVED == "approved"
    assert DocumentStatus.FAILED == "failed"


def test_document_creation():
    """Testa criação de Document."""
    # Arrange & Act
    doc = Document(
        id="DOC-001",
        filename="spec.pdf",
        format=DocumentFormat.PDF,
        status=DocumentStatus.UPLOADED,
        file_size_bytes=1024000,
        s3_key="documents/spec.pdf",
        uploaded_by="user@example.com",
    )

    # Assert
    assert doc.id == "DOC-001"
    assert doc.filename == "spec.pdf"
    assert doc.format == DocumentFormat.PDF
    assert doc.status == DocumentStatus.UPLOADED
    assert doc.file_size_bytes == 1024000
    assert doc.s3_key == "documents/spec.pdf"
    assert doc.uploaded_by == "user@example.com"
    assert isinstance(doc.created_at, datetime)
    assert doc.version == 1


def test_document_with_optional_fields():
    """Testa criação de Document com campos opcionais."""
    # Arrange & Act
    doc = Document(
        id="DOC-002",
        filename="spec.docx",
        format=DocumentFormat.DOCX,
        status=DocumentStatus.PARSED,
        file_size_bytes=2048000,
        s3_key="documents/spec.docx",
        uploaded_by="user@example.com",
        title="Especificação Técnica",
        description="Documento de requisitos",
        project_id="PROJ-001",
        tags=["requirements", "v1.0"],
        metadata={"author": "John Doe", "department": "Engineering"},
    )

    # Assert
    assert doc.title == "Especificação Técnica"
    assert doc.description == "Documento de requisitos"
    assert doc.project_id == "PROJ-001"
    assert "requirements" in doc.tags
    assert doc.metadata["author"] == "John Doe"


def test_document_create_model():
    """Testa modelo DocumentCreate."""
    # Arrange & Act
    doc_create = DocumentCreate(
        filename="spec.pdf",
        format=DocumentFormat.PDF,
        file_size_bytes=1024000,
        s3_key="documents/spec.pdf",
        uploaded_by="user@example.com",
        title="Especificação",
        project_id="PROJ-001",
    )

    # Assert
    assert doc_create.filename == "spec.pdf"
    assert doc_create.format == DocumentFormat.PDF
    assert doc_create.uploaded_by == "user@example.com"
    assert doc_create.project_id == "PROJ-001"


def test_document_update_model():
    """Testa modelo DocumentUpdate."""
    # Arrange & Act
    doc_update = DocumentUpdate(
        status=DocumentStatus.PARSED,
        title="Novo Título",
        description="Nova descrição",
    )

    # Assert
    assert doc_update.status == DocumentStatus.PARSED
    assert doc_update.title == "Novo Título"
    assert doc_update.description == "Nova descrição"


def test_document_update_with_all_optional_fields():
    """Testa DocumentUpdate com todos os campos opcionais."""
    # Arrange & Act
    doc_update = DocumentUpdate(
        status=DocumentStatus.EXTRACTED,
        title="Updated Title",
        description="Updated Description",
        project_id="PROJ-002",
        tags=["updated", "v2.0"],
        metadata={"version": "2.0"},
        parsing_error="No errors",
    )

    # Assert
    assert doc_update.status == DocumentStatus.EXTRACTED
    assert doc_update.tags == ["updated", "v2.0"]
    assert doc_update.parsing_error == "No errors"


def test_document_default_values():
    """Testa valores padrão de Document."""
    # Arrange & Act
    doc = Document(
        id="DOC-003",
        filename="test.pdf",
        format=DocumentFormat.PDF,
        status=DocumentStatus.UPLOADED,
        file_size_bytes=1000,
        s3_key="test.pdf",
        uploaded_by="user@example.com",
    )

    # Assert
    assert doc.title is None
    assert doc.description is None
    assert doc.project_id is None
    assert doc.tags == []
    assert doc.metadata == {}
    assert doc.parsing_error is None
    assert doc.entity_count == 0
    assert doc.version == 1


def test_document_with_parsing_results():
    """Testa Document com resultados de parsing."""
    # Arrange & Act
    doc = Document(
        id="DOC-004",
        filename="parsed.pdf",
        format=DocumentFormat.PDF,
        status=DocumentStatus.EXTRACTED,
        file_size_bytes=5000,
        s3_key="parsed.pdf",
        uploaded_by="user@example.com",
        parsed_text="Conteúdo extraído do documento",
        entity_count=15,
        extracted_entity_types=["services", "apis", "data_models"],
    )

    # Assert
    assert doc.status == DocumentStatus.EXTRACTED
    assert doc.parsed_text == "Conteúdo extraído do documento"
    assert doc.entity_count == 15
    assert "services" in doc.extracted_entity_types
