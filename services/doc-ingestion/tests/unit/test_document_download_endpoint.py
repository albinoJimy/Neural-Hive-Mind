"""Testes unitários para endpoint de download de documentos."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, status

from src.api.routers.documents import download_document
from src.models.document import Document, DocumentFormat, DocumentStatus


@pytest.fixture
def mock_document_repository():
    """Mock do DocumentRepository."""
    repo = MagicMock()
    repo.get_by_id = AsyncMock()
    return repo


@pytest.fixture
def mock_s3_client():
    """Mock do S3Client."""
    client = MagicMock()
    client.download_file_with_metadata = AsyncMock()
    return client


@pytest.fixture
def sample_document():
    """Documento de exemplo."""
    return Document(
        id="doc-123",
        filename="relatorio.pdf",
        format=DocumentFormat.PDF,
        s3_key="documents/relatorio.pdf",
        file_size_bytes=1024,
        uploaded_by="test-user",
        status=DocumentStatus.EXTRACTED,
    )


class TestDownloadDocumentEndpoint:
    """Testes para endpoint GET /documents/{id}/download."""

    @pytest.mark.asyncio
    async def test_download_document_success(
        self, mock_document_repository, mock_s3_client, sample_document
    ):
        """Testa download bem-sucedido."""
        document_id = "doc-123"
        file_content = b"PDF content here"

        mock_document_repository.get_by_id.return_value = sample_document
        mock_s3_client.download_file_with_metadata.return_value = (
            file_content,
            "relatorio.pdf",
            "application/pdf",
        )

        with patch(
            "src.api.routers.documents.get_s3_client",
            return_value=mock_s3_client,
        ):
            response = await download_document(document_id, mock_document_repository)

        assert response.body == file_content
        assert response.media_type == "application/pdf"
        assert "attachment" in response.headers["content-disposition"]
        assert "relatorio.pdf" in response.headers["content-disposition"]
        mock_document_repository.get_by_id.assert_called_once_with(document_id)
        mock_s3_client.download_file_with_metadata.assert_called_once_with(
            "documents/relatorio.pdf", return_metadata=True
        )

    @pytest.mark.asyncio
    async def test_download_document_not_found(self, mock_document_repository):
        """Testa erro quando documento não existe."""
        document_id = "nonexistent-doc"
        mock_document_repository.get_by_id.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await download_document(document_id, mock_document_repository)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_download_document_s3_error(
        self, mock_document_repository, mock_s3_client, sample_document
    ):
        """Testa erro no download do S3."""
        document_id = "doc-123"

        mock_document_repository.get_by_id.return_value = sample_document
        mock_s3_client.download_file_with_metadata.side_effect = Exception("S3 connection failed")

        with patch(
            "src.api.routers.documents.get_s3_client",
            return_value=mock_s3_client,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await download_document(document_id, mock_document_repository)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "failed to download" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_download_document_with_special_filename(
        self, mock_document_repository, mock_s3_client
    ):
        """Testa download com nome de arquivo especial (acentos, espaços)."""
        document_id = "doc-456"
        special_doc = Document(
            id=document_id,
            filename="Relatório Final 2024.pdf",
            format=DocumentFormat.PDF,
            s3_key="documents/relatorio-final.pdf",
            file_size_bytes=2048,
            uploaded_by="test-user",
            status=DocumentStatus.APPROVED,
        )
        file_content = b"Special content"

        mock_document_repository.get_by_id.return_value = special_doc
        mock_s3_client.download_file_with_metadata.return_value = (
            file_content,
            "Relatório Final 2024.pdf",
            "application/pdf",
        )

        with patch(
            "src.api.routers.documents.get_s3_client",
            return_value=mock_s3_client,
        ):
            response = await download_document(document_id, mock_document_repository)

        assert response.body == file_content
        assert response.media_type == "application/pdf"

    @pytest.mark.asyncio
    async def test_download_document_various_formats(
        self, mock_document_repository, mock_s3_client
    ):
        """Testa download de diferentes formatos de documento."""
        test_cases = [
            (DocumentFormat.PDF, b"PDF content", "doc.pdf", "application/pdf"),
            (
                DocumentFormat.DOCX,
                b"DOCX content",
                "doc.docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
        ]

        for doc_format, content, filename, content_type in test_cases:
            document_id = f"doc-{doc_format.value}"
            doc = Document(
                id=document_id,
                filename=filename,
                format=doc_format,
                s3_key=f"documents/{filename}",
                file_size_bytes=len(content),
                uploaded_by="test-user",
                status=DocumentStatus.EXTRACTED,
            )

            mock_document_repository.get_by_id.return_value = doc
            mock_s3_client.download_file_with_metadata.return_value = (
                content,
                filename,
                content_type,
            )

            with patch(
                "src.api.routers.documents.get_s3_client",
                return_value=mock_s3_client,
            ):
                response = await download_document(document_id, mock_document_repository)

            assert response.body == content
            assert response.media_type == content_type
