"""Testes unitários para DocumentRepository."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.models.document import (
    DocumentCreate,
    DocumentFormat,
    DocumentStatus,
    DocumentUpdate,
)
from src.repositories.document_repository import DocumentRepository


def create_update_result(modified_count: int = 1):
    """Cria UpdateResult mock."""
    result = Mock(spec=["modified_count"])
    result.modified_count = modified_count
    return result


def create_delete_result(deleted_count: int = 1):
    """Cria DeleteResult mock."""
    result = Mock(spec=["deleted_count"])
    result.deleted_count = deleted_count
    return result


@pytest.fixture
def mock_db():
    """Cria mock do MongoDB."""
    db = Mock()
    db.documents_collection = Mock()
    db.requirements_sets_collection = Mock()
    return db


@pytest.fixture
def mock_mongodb_client(mock_db):
    """Cria mock do MongoDB client."""
    client = Mock()
    # Create simple dict for database that supports __getitem__
    db_dict = {"documents": mock_db.documents_collection}

    # Mock client properties
    client.database = db_dict
    client.documents_collection = mock_db.documents_collection
    client.entities_collection = Mock()
    client.parsing_jobs_collection = Mock()

    return client


@pytest.mark.asyncio
class TestDocumentRepository:
    """Testes unitários para DocumentRepository."""

    async def test_create_document(self, mock_mongodb_client):
        """Testa criação de documento."""
        # Arrange
        with patch(
            "src.repositories.document_repository.get_mongodb_client",
            return_value=mock_mongodb_client,
        ):
            mock_mongodb_client.documents_collection.insert_one = AsyncMock()

            repository = DocumentRepository()
            doc_create = DocumentCreate(
                filename="test.pdf",
                format=DocumentFormat.PDF,
                file_size_bytes=1024,
                s3_key="test/test.pdf",
                uploaded_by="user@example.com",
            )

            # Act
            document = await repository.create(doc_create)

            # Assert
            assert document.id.startswith("DOC-")
            assert document.filename == "test.pdf"
            assert document.format == DocumentFormat.PDF
            assert document.status == DocumentStatus.UPLOADED
            mock_mongodb_client.documents_collection.insert_one.assert_called_once()

    async def test_get_by_id_found(self, mock_mongodb_client):
        """Testa busca de documento por ID quando encontrado."""
        # Arrange
        doc_data = {
            "_id": "507f1f77bcf86cd799439011",
            "id": "DOC-001",
            "filename": "test.pdf",
            "format": "pdf",
            "status": "uploaded",
            "file_size_bytes": 1024,
            "s3_key": "test/test.pdf",
            "uploaded_by": "user@example.com",
            "title": None,
            "description": None,
            "project_id": None,
            "tags": [],
            "metadata": {},
            "parsed_text": None,
            "entity_count": 0,
            "extracted_entity_types": [],
            "parsing_error": None,
            "created_at": "2024-01-01T00:00:00",
            "updated_at": None,
            "parsed_at": None,
            "extracted_at": None,
            "version": 1,
        }

        with patch(
            "src.repositories.document_repository.get_mongodb_client",
            return_value=mock_mongodb_client,
        ):
            mock_mongodb_client.documents_collection.find_one = AsyncMock(return_value=doc_data)

            repository = DocumentRepository()

            # Act
            document = await repository.get_by_id("DOC-001")

            # Assert
            assert document is not None
            assert document.id == "DOC-001"
            assert document.filename == "test.pdf"

    async def test_get_by_id_not_found(self, mock_mongodb_client):
        """Testa busca de documento por ID quando não encontrado."""
        # Arrange
        with patch(
            "src.repositories.document_repository.get_mongodb_client",
            return_value=mock_mongodb_client,
        ):
            mock_mongodb_client.documents_collection.find_one = AsyncMock(return_value=None)

            repository = DocumentRepository()

            # Act
            document = await repository.get_by_id("NONEXISTENT")

            # Assert
            assert document is None

    async def test_list_documents_empty(self, mock_mongodb_client):
        """Testa listagem de documentos vazia."""
        # Arrange
        with patch(
            "src.repositories.document_repository.get_mongodb_client",
            return_value=mock_mongodb_client,
        ):
            # Criar mock para cursor que suporta chaining
            class AsyncCursor:
                def skip(self, n):
                    return self
                def limit(self, n):
                    return self
                def sort(self, *args):
                    return self
                async def to_list(self, length=None):
                    return []

            mock_mongodb_client.documents_collection.find = Mock(return_value=AsyncCursor())
            mock_mongodb_client.documents_collection.count_documents = AsyncMock(return_value=0)

            repository = DocumentRepository()

            # Act
            documents, total = await repository.list()

            # Assert
            assert documents == []
            assert total == 0

    async def test_list_documents_with_filters(self, mock_mongodb_client):
        """Testa listagem de documentos com filtros."""
        # Arrange
        doc_data = {
            "_id": "507f1f77bcf86cd799439011",
            "id": "DOC-001",
            "filename": "test.pdf",
            "format": "pdf",
            "status": "uploaded",
            "file_size_bytes": 1024,
            "s3_key": "test/test.pdf",
            "uploaded_by": "user@example.com",
            "title": None,
            "description": None,
            "project_id": None,
            "tags": [],
            "metadata": {},
            "parsed_text": None,
            "entity_count": 0,
            "extracted_entity_types": [],
            "parsing_error": None,
            "created_at": "2024-01-01T00:00:00",
            "updated_at": None,
            "parsed_at": None,
            "extracted_at": None,
            "version": 1,
        }

        with patch(
            "src.repositories.document_repository.get_mongodb_client",
            return_value=mock_mongodb_client,
        ):
            # Criar mock para cursor que suporta chaining
            class AsyncCursor:
                def skip(self, n):
                    return self
                def limit(self, n):
                    return self
                def sort(self, *args):
                    return self
                async def to_list(self, length=None):
                    return [doc_data]

            mock_mongodb_client.documents_collection.find = Mock(return_value=AsyncCursor())
            mock_mongodb_client.documents_collection.count_documents = AsyncMock(return_value=1)

            repository = DocumentRepository()

            # Act
            documents, total = await repository.list(
                status_filter=DocumentStatus.UPLOADED,
                format_filter="pdf",
            )

            # Assert
            assert len(documents) == 1
            assert total == 1
            assert documents[0].id == "DOC-001"

    async def test_update_document(self, mock_mongodb_client):
        """Testa atualização de documento."""
        # Arrange
        updated_doc = {
            "_id": "507f1f77bcf86cd799439011",
            "id": "DOC-001",
            "filename": "test.pdf",
            "format": "pdf",
            "status": "uploaded",
            "file_size_bytes": 1024,
            "s3_key": "test/test.pdf",
            "uploaded_by": "user@example.com",
            "title": "New Title",
            "description": None,
            "project_id": None,
            "tags": [],
            "metadata": {},
            "parsed_text": None,
            "entity_count": 0,
            "extracted_entity_types": [],
            "parsing_error": None,
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-02T00:00:00",
            "parsed_at": None,
            "extracted_at": None,
            "version": 1,
        }

        with patch(
            "src.repositories.document_repository.get_mongodb_client",
            return_value=mock_mongodb_client,
        ):
            # find_one retorna o documento atualizado (após update)
            mock_mongodb_client.documents_collection.find_one = AsyncMock(return_value=updated_doc)
            mock_mongodb_client.documents_collection.update_one = AsyncMock(
                return_value=create_update_result(1)
            )

            repository = DocumentRepository()
            update_data = DocumentUpdate(title="New Title")

            # Act
            document = await repository.update("DOC-001", update_data)

            # Assert
            assert document is not None
            assert document.title == "New Title"

    async def test_delete_document(self, mock_mongodb_client):
        """Testa deleção de documento."""
        # Arrange
        with patch(
            "src.repositories.document_repository.get_mongodb_client",
            return_value=mock_mongodb_client,
        ):
            mock_mongodb_client.documents_collection.delete_one = AsyncMock(
                return_value=create_delete_result(1)
            )

            repository = DocumentRepository()

            # Act
            result = await repository.delete("DOC-001")

            # Assert
            assert result is True

    async def test_delete_document_not_found(self, mock_mongodb_client):
        """Testa deleção de documento inexistente."""
        # Arrange
        with patch(
            "src.repositories.document_repository.get_mongodb_client",
            return_value=mock_mongodb_client,
        ):
            mock_mongodb_client.documents_collection.delete_one = AsyncMock(
                return_value=create_delete_result(0)
            )

            repository = DocumentRepository()

            # Act
            result = await repository.delete("NONEXISTENT")

            # Assert
            assert result is False

    async def test_update_status(self, mock_mongodb_client):
        """Testa atualização de status."""
        # Arrange
        doc_data = {
            "_id": "507f1f77bcf86cd799439011",
            "id": "DOC-001",
            "filename": "test.pdf",
            "format": "pdf",
            "status": "uploaded",
            "file_size_bytes": 1024,
            "s3_key": "test/test.pdf",
            "uploaded_by": "user@example.com",
            "title": None,
            "description": None,
            "project_id": None,
            "tags": [],
            "metadata": {},
            "parsed_text": None,
            "entity_count": 0,
            "extracted_entity_types": [],
            "parsing_error": None,
            "created_at": "2024-01-01T00:00:00",
            "updated_at": None,
            "parsed_at": None,
            "extracted_at": None,
            "version": 1,
        }

        with patch(
            "src.repositories.document_repository.get_mongodb_client",
            return_value=mock_mongodb_client,
        ):
            mock_mongodb_client.documents_collection.find_one = AsyncMock(return_value=doc_data)
            mock_mongodb_client.documents_collection.update_one = AsyncMock(
                return_value=create_update_result(1)
            )

            repository = DocumentRepository()

            # Act
            document = await repository.update_status(
                "DOC-001", DocumentStatus.PARSED, error="Test error"
            )

            # Assert
            assert document is not None
            # O status atualizado virá do segundo find_one chamado pelo update
            mock_mongodb_client.documents_collection.update_one.assert_called_once()

    async def test_update_parsed_content(self, mock_mongodb_client):
        """Testa atualização de conteúdo parseado."""
        # Arrange
        doc_data = {
            "_id": "507f1f77bcf86cd799439011",
            "id": "DOC-001",
            "filename": "test.pdf",
            "format": "pdf",
            "status": "uploaded",
            "file_size_bytes": 1024,
            "s3_key": "test/test.pdf",
            "uploaded_by": "user@example.com",
            "title": None,
            "description": None,
            "project_id": None,
            "tags": [],
            "metadata": {},
            "parsed_text": None,
            "entity_count": 0,
            "extracted_entity_types": [],
            "parsing_error": None,
            "created_at": "2024-01-01T00:00:00",
            "updated_at": None,
            "parsed_at": None,
            "extracted_at": None,
            "version": 1,
        }

        with patch(
            "src.repositories.document_repository.get_mongodb_client",
            return_value=mock_mongodb_client,
        ):
            mock_mongodb_client.documents_collection.find_one = AsyncMock(return_value=doc_data)
            mock_mongodb_client.documents_collection.update_one = AsyncMock(
                return_value=create_update_result(1)
            )

            repository = DocumentRepository()

            # Act
            document = await repository.update_parsed_content("DOC-001", "Extracted text content")

            # Assert
            assert document is not None
            mock_mongodb_client.documents_collection.update_one.assert_called_once()

    async def test_update_extraction_results(self, mock_mongodb_client):
        """Testa atualização de resultados de extração."""
        # Arrange
        doc_data = {
            "_id": "507f1f77bcf86cd799439011",
            "id": "DOC-001",
            "filename": "test.pdf",
            "format": "pdf",
            "status": "uploaded",
            "file_size_bytes": 1024,
            "s3_key": "test/test.pdf",
            "uploaded_by": "user@example.com",
            "title": None,
            "description": None,
            "project_id": None,
            "tags": [],
            "metadata": {},
            "parsed_text": "Some text",
            "entity_count": 0,
            "extracted_entity_types": [],
            "parsing_error": None,
            "created_at": "2024-01-01T00:00:00",
            "updated_at": None,
            "parsed_at": None,
            "extracted_at": None,
            "version": 1,
        }

        with patch(
            "src.repositories.document_repository.get_mongodb_client",
            return_value=mock_mongodb_client,
        ):
            mock_mongodb_client.documents_collection.find_one = AsyncMock(return_value=doc_data)
            mock_mongodb_client.documents_collection.update_one = AsyncMock(
                return_value=create_update_result(1)
            )

            repository = DocumentRepository()

            # Act
            document = await repository.update_extraction_results(
                "DOC-001", 15, ["functionality", "api"]
            )

            # Assert
            assert document is not None
            mock_mongodb_client.documents_collection.update_one.assert_called_once()
