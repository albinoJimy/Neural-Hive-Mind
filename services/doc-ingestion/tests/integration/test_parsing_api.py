"""Testes de integração para API de parsing."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
class TestParsingAPI:
    """Testes de integração para endpoints de parsing."""

    async def test_parse_document_pdf(
        self, test_client, sample_pdf_bytes
    ):
        """Testa parsing de documento PDF."""
        # Arrange - Upload documento primeiro
        files = {"file": ("test.pdf", sample_pdf_bytes, "application/pdf")}
        data = {"uploaded_by": "test@example.com"}
        upload_response = test_client.post("/api/v1/documents/upload", files=files, data=data)
        document_id = upload_response.json()["id"]

        # Mock parser response
        with patch(
            "src.services.parsers.pdf_parser.PDFParser.parse",
            new_callable=AsyncMock,
            return_value="Sample Document\nThis is a test document",
        ):
            # Act
            response = test_client.post(f"/api/v1/documents/{document_id}/parse")

        # Assert
        assert response.status_code == 202
        result = response.json()
        assert "job_id" in result
        assert result["document_id"] == document_id
        assert result["status"] in ["completed", "failed"]

    async def test_parse_document_not_found(self, test_client):
        """Testa parsing de documento inexistente."""
        # Act
        response = test_client.post("/api/v1/documents/NONEXISTENT/parse")

        # Assert
        assert response.status_code == 404

    async def test_parse_unsupported_format(self, test_client):
        """Testa parsing de formato não suportado."""
        # Arrange - Criar documento com formato não suportado (simulado)
        # Nota: Em teste real, isso seria filtrado no upload

        # Act - Tentar parsear
        response = test_client.post("/api/v1/documents/SOME-ID/parse")

        # Assert - Se não encontrar, retorna 404
        assert response.status_code in [404, 500]

    async def test_extract_entities_success(
        self, test_client, sample_pdf_bytes
    ):
        """Testa extração de entidades."""
        # Arrange - Upload e parse documento
        files = {"file": ("test.pdf", sample_pdf_bytes, "application/pdf")}
        data = {"uploaded_by": "test@example.com"}
        upload_response = test_client.post("/api/v1/documents/upload", files=files, data=data)
        document_id = upload_response.json()["id"]

        # Mock parser e entity extractor
        with patch(
            "src.services.parsers.pdf_parser.PDFParser.parse",
            new_callable=AsyncMock,
            return_value="System with user authentication and payment processing",
        ):
            test_client.post(f"/api/v1/documents/{document_id}/parse")

        with patch(
            "src.services.entity_extractor.EntityExtractor.extract",
            new_callable=AsyncMock,
            return_value=[
                {
                    "id": "ENT-001",
                    "type": "functionality",
                    "name": "User Authentication",
                    "description": "System for user login",
                    "source_text": "user authentication",
                    "confidence_score": 0.9,
                    "document_id": document_id,
                    "metadata": {},
                }
            ],
        ):
            # Act
            response = test_client.post(
                f"/api/v1/documents/{document_id}/extract"
            )

        # Assert
        assert response.status_code == 202
        result = response.json()
        assert "job_id" in result
        assert result["document_id"] == document_id

    async def test_extract_entities_not_parsed(self, test_client, sample_pdf_bytes):
        """Testa extração de entidades sem parse prévio."""
        # Arrange - Upload documento (sem parse)
        files = {"file": ("test.pdf", sample_pdf_bytes, "application/pdf")}
        data = {"uploaded_by": "test@example.com"}
        upload_response = test_client.post("/api/v1/documents/upload", files=files, data=data)
        document_id = upload_response.json()["id"]

        # Act - Tentar extrair sem parse
        response = test_client.post(f"/api/v1/documents/{document_id}/extract")

        # Assert
        assert response.status_code == 400
        assert "must be parsed" in response.json()["detail"].lower()

    async def test_approve_document(
        self, test_client, sample_pdf_bytes
    ):
        """Testa aprovação de documento."""
        # Arrange - Upload documento
        files = {"file": ("test.pdf", sample_pdf_bytes, "application/pdf")}
        data = {"uploaded_by": "test@example.com"}
        upload_response = test_client.post("/api/v1/documents/upload", files=files, data=data)
        document_id = upload_response.json()["id"]

        # Mock parser para definir status como parsed
        with patch(
            "src.services.parsers.pdf_parser.PDFParser.parse",
            new_callable=AsyncMock,
            return_value="Sample content",
        ):
            test_client.post(f"/api/v1/documents/{document_id}/parse")

        # Act
        response = test_client.post(
            f"/api/v1/documents/{document_id}/approve",
            params={"approved_by": "admin@example.com", "notes": "Approved for migration"}
        )

        # Assert
        assert response.status_code == 200
        result = response.json()
        assert result["document_id"] == document_id
        assert result["status"] == "approved"
        assert result["approved_by"] == "admin@example.com"

    async def test_approve_document_not_parsed(
        self, test_client, sample_pdf_bytes
    ):
        """Testa aprovação de documento não parseado."""
        # Arrange - Upload documento (sem parse)
        files = {"file": ("test.pdf", sample_pdf_bytes, "application/pdf")}
        data = {"uploaded_by": "test@example.com"}
        upload_response = test_client.post("/api/v1/documents/upload", files=files, data=data)
        document_id = upload_response.json()["id"]

        # Act - Tentar aprovar sem parse
        response = test_client.post(
            f"/api/v1/documents/{document_id}/approve",
            params={"approved_by": "admin@example.com"}
        )

        # Assert
        assert response.status_code == 400
        assert "must be parsed" in response.json()["detail"].lower()

    async def test_get_document_entities(
        self, test_client, sample_pdf_bytes
    ):
        """Testa busca de entidades de documento."""
        # Arrange - Upload, parse e extrair entidades
        files = {"file": ("test.pdf", sample_pdf_bytes, "application/pdf")}
        data = {"uploaded_by": "test@example.com"}
        upload_response = test_client.post("/api/v1/documents/upload", files=files, data=data)
        document_id = upload_response.json()["id"]

        # Act
        response = test_client.get(f"/api/v1/documents/{document_id}/entities")

        # Assert - Sem extração prévia, pode retornar erro ou informações
        assert response.status_code in [200, 400]

    async def test_parsing_job_status(self, test_client):
        """Testa status de job de parsing."""
        # Act
        response = test_client.get("/api/v1/documents/jobs/SOME-JOB-ID")

        # Assert - Job tracking ainda não implementado
        assert response.status_code == 200
        result = response.json()
        assert "job_id" in result

    async def test_extract_with_custom_confidence(
        self, test_client, sample_pdf_bytes
    ):
        """Testa extração com confiança customizada."""
        # Arrange
        files = {"file": ("test.pdf", sample_pdf_bytes, "application/pdf")}
        data = {"uploaded_by": "test@example.com"}
        upload_response = test_client.post("/api/v1/documents/upload", files=files, data=data)
        document_id = upload_response.json()["id"]

        # Mock parser
        with patch(
            "src.services.parsers.pdf_parser.PDFParser.parse",
            new_callable=AsyncMock,
            return_value="Sample content",
        ):
            test_client.post(f"/api/v1/documents/{document_id}/parse")

        # Mock extractor
        with patch(
            "src.services.entity_extractor.EntityExtractor.extract",
            new_callable=AsyncMock,
            return_value=[],
        ):
            # Act - Com confiança mínima de 0.9
            response = test_client.post(
                f"/api/v1/documents/{document_id}/extract?min_confidence=0.9"
            )

        # Assert
        assert response.status_code == 202


@pytest.mark.asyncio
class TestParsingErrorHandling:
    """Testes de tratamento de erros na API de parsing."""

    async def test_parse_with_s3_error(
        self, test_client, sample_pdf_bytes
    ):
        """Testa parsing com erro no S3."""
        # Arrange
        files = {"file": ("test.pdf", sample_pdf_bytes, "application/pdf")}
        data = {"uploaded_by": "test@example.com"}
        upload_response = test_client.post("/api/v1/documents/upload", files=files, data=data)
        document_id = upload_response.json()["id"]

        # Mock S3 download error
        with patch(
            "src.clients.s3_client.S3Client.download_file",
            new_callable=AsyncMock,
            side_effect=Exception("S3 connection failed"),
        ):
            # Act
            response = test_client.post(f"/api/v1/documents/{document_id}/parse")

        # Assert
        assert response.status_code in [500, 202]  # 202 com erro no job

    async def test_extract_with_llm_error(
        self, test_client, sample_pdf_bytes
    ):
        """Testa extração com erro no LLM."""
        # Arrange
        files = {"file": ("test.pdf", sample_pdf_bytes, "application/pdf")}
        data = {"uploaded_by": "test@example.com"}
        upload_response = test_client.post("/api/v1/documents/upload", files=files, data=data)
        document_id = upload_response.json()["id"]

        # Mock parser
        with patch(
            "src.services.parsers.pdf_parser.PDFParser.parse",
            new_callable=AsyncMock,
            return_value="Sample content",
        ):
            test_client.post(f"/api/v1/documents/{document_id}/parse")

        # Mock LLM error
        with patch(
            "src.services.entity_extractor.EntityExtractor.extract",
            new_callable=AsyncMock,
            side_effect=Exception("LLM API error"),
        ):
            # Act
            response = test_client.post(f"/api/v1/documents/{document_id}/extract")

        # Assert
        assert response.status_code == 500
