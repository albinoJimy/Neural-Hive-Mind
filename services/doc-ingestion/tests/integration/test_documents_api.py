"""Testes de integração para API de documentos."""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.asyncio
class TestDocumentsAPI:
    """Testes de integração para endpoints de documentos."""

    async def test_upload_document_pdf(
        self, test_client: TestClient, sample_pdf_bytes: bytes
    ) -> None:
        """Testa upload de documento PDF."""
        # Arrange
        files = {"file": ("test.pdf", sample_pdf_bytes, "application/pdf")}
        data = {
            "uploaded_by": "test@example.com",
            "title": "Test PDF",
            "description": "A test PDF document",
            "tags": "test,pdf",
        }

        # Act
        response = test_client.post(
            "/api/v1/documents/upload",
            files=files,
            data=data,
        )

        # Assert
        assert response.status_code == 201
        result = response.json()
        assert "id" in result
        assert result["filename"] == "test.pdf"
        assert result["format"] == "pdf"
        assert result["status"] == "uploaded"
        assert result["uploaded_by"] == "test@example.com"
        assert result["title"] == "Test PDF"

    async def test_upload_document_missing_file(self, test_client: TestClient) -> None:
        """Testa upload sem arquivo."""
        # Arrange
        data = {"uploaded_by": "test@example.com"}

        # Act
        response = test_client.post("/api/v1/documents/upload", data=data)

        # Assert
        assert response.status_code == 422  # Validation error

    async def test_upload_document_missing_uploaded_by(
        self, test_client: TestClient, sample_pdf_bytes: bytes
    ) -> None:
        """Testa upload sem campo uploaded_by."""
        # Arrange
        files = {"file": ("test.pdf", sample_pdf_bytes, "application/pdf")}

        # Act
        response = test_client.post(
            "/api/v1/documents/upload",
            files=files,
        )

        # Assert
        assert response.status_code == 422  # Validation error

    async def test_upload_unsupported_format(self, test_client: TestClient) -> None:
        """Testa upload de formato não suportado."""
        # Arrange
        files = {"file": ("test.txt", b"test content", "text/plain")}
        data = {"uploaded_by": "test@example.com"}

        # Act
        response = test_client.post(
            "/api/v1/documents/upload",
            files=files,
            data=data,
        )

        # Assert
        assert response.status_code == 400
        assert "Unsupported file format" in response.json()["detail"]

    async def test_list_documents_empty(self, test_client: TestClient) -> None:
        """Testa listagem de documentos vazia."""
        # Act
        response = test_client.get("/api/v1/documents")

        # Assert
        assert response.status_code == 200
        result = response.json()
        assert result["total"] == 0
        assert result["items"] == []

    async def test_list_documents_with_filters(
        self, test_client: TestClient, sample_pdf_bytes: bytes
    ) -> None:
        """Testa listagem de documentos com filtros."""
        # Arrange - Upload documento
        files = {"file": ("test.pdf", sample_pdf_bytes, "application/pdf")}
        data = {"uploaded_by": "user1@example.com", "project_id": "PROJ-001"}
        test_client.post("/api/v1/documents/upload", files=files, data=data)

        # Act - Listar por projeto
        response = test_client.get("/api/v1/documents?project_id=PROJ-001")

        # Assert
        assert response.status_code == 200
        result = response.json()
        assert result["total"] >= 1

    async def test_get_document_by_id(
        self, test_client: TestClient, sample_pdf_bytes: bytes
    ) -> None:
        """Testa busca de documento por ID."""
        # Arrange - Upload documento
        files = {"file": ("test.pdf", sample_pdf_bytes, "application/pdf")}
        data = {"uploaded_by": "test@example.com"}
        upload_response = test_client.post("/api/v1/documents/upload", files=files, data=data)
        document_id = upload_response.json()["id"]

        # Act
        response = test_client.get(f"/api/v1/documents/{document_id}")

        # Assert
        assert response.status_code == 200
        result = response.json()
        assert result["id"] == document_id
        assert result["filename"] == "test.pdf"

    async def test_get_document_not_found(self, test_client: TestClient) -> None:
        """Testa busca de documento inexistente."""
        # Act
        response = test_client.get("/api/v1/documents/NONEXISTENT")

        # Assert
        assert response.status_code == 404

    async def test_get_document_status(
        self, test_client: TestClient, sample_pdf_bytes: bytes
    ) -> None:
        """Testa busca de status de documento."""
        # Arrange
        files = {"file": ("test.pdf", sample_pdf_bytes, "application/pdf")}
        data = {"uploaded_by": "test@example.com"}
        upload_response = test_client.post("/api/v1/documents/upload", files=files, data=data)
        document_id = upload_response.json()["id"]

        # Act
        response = test_client.get(f"/api/v1/documents/{document_id}/status")

        # Assert
        assert response.status_code == 200
        result = response.json()
        assert result["id"] == document_id
        assert result["status"] == "uploaded"

    async def test_delete_document(self, test_client: TestClient, sample_pdf_bytes: bytes) -> None:
        """Testa deleção de documento."""
        # Arrange
        files = {"file": ("test.pdf", sample_pdf_bytes, "application/pdf")}
        data = {"uploaded_by": "test@example.com"}
        upload_response = test_client.post("/api/v1/documents/upload", files=files, data=data)
        document_id = upload_response.json()["id"]

        # Act
        response = test_client.delete(f"/api/v1/documents/{document_id}")

        # Assert
        assert response.status_code == 204

        # Verificar que foi deletado
        get_response = test_client.get(f"/api/v1/documents/{document_id}")
        assert get_response.status_code == 404

    async def test_list_with_pagination(
        self, test_client: TestClient, sample_pdf_bytes: bytes
    ) -> None:
        """Testa paginação na listagem de documentos."""
        # Arrange - Upload múltiplos documentos
        for i in range(5):
            files = {"file": (f"test{i}.pdf", sample_pdf_bytes, "application/pdf")}
            data = {"uploaded_by": "test@example.com"}
            test_client.post("/api/v1/documents/upload", files=files, data=data)

        # Act - Limitar a 3 resultados
        response = test_client.get("/api/v1/documents?limit=3&skip=0")

        # Assert
        assert response.status_code == 200
        result = response.json()
        assert len(result["items"]) <= 3

    async def test_upload_with_tags(self, test_client: TestClient, sample_pdf_bytes: bytes) -> None:
        """Testa upload com tags."""
        # Arrange
        files = {"file": ("test.pdf", sample_pdf_bytes, "application/pdf")}
        data = {
            "uploaded_by": "test@example.com",
            "tags": "requirement,spec,v1.0",
        }

        # Act
        response = test_client.post("/api/v1/documents/upload", files=files, data=data)

        # Assert
        assert response.status_code == 201
        result = response.json()
        assert "requirement" in result["tags"]
        assert "spec" in result["tags"]
        assert "v1.0" in result["tags"]
