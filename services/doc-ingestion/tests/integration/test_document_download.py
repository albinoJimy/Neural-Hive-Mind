"""Testes de integração para endpoint de download."""

import pytest
from httpx import AsyncClient

from src.main import app


@pytest.mark.asyncio
async def test_download_document():
    """Testa download de documento armazenado no S3."""
    # Setup: criar documento de teste
    from src.models.document import DocumentCreate, DocumentFormat
    from src.repositories.document_repository import DocumentRepository

    repository = DocumentRepository()
    doc_create = DocumentCreate(
        filename="test_download.pdf",
        format=DocumentFormat.PDF,
        file_size_bytes=1024,
        s3_key="test/test_download.pdf",
        uploaded_by="test_user",
    )
    document = await repository.create(doc_create)

    # Testar download
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(f"/api/v1/documents/{document.id}/download")

    assert response.status_code == 200
    assert response.content == b"test content"  # Conteúdo esperado
    assert "attachment" in response.headers.get("content-disposition", "")

    # Cleanup
    await repository.delete(document.id)
