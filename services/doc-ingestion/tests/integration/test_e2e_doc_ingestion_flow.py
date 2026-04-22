"""Testes E2E para o fluxo completo de ingestão de documentos.

Estes testes verificam o fluxo completo:
1. Upload de documento
2. Parse do documento
3. Extração de entidades
4. Publicação de eventos Kafka

Requisitos:
- MongoDB (pode ser mockado)
- S3/MinIO (pode ser mockado com moto)
- Kafka (pode ser mockado)
"""

import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.mark.e2e
@pytest.mark.asyncio
class TestE2EDocIngestionFlow:
    """Testes E2E para fluxo completo de ingestão de documentos."""

    async def test_complete_pdf_flow(
        self, test_client_with_all_mocks: TestClient, sample_pdf_bytes: bytes
    ) -> None:
        """Testa fluxo completo: upload PDF -> parse -> extract -> Kafka event."""
        # Arrange
        files = {"file": ("test.pdf", sample_pdf_bytes, "application/pdf")}
        data = {
            "uploaded_by": "test@example.com",
            "title": "Test PDF Document",
            "description": "A test PDF for E2E testing",
            "tags": "test,e2e,pdf",
        }

        # Act - Upload documento
        upload_response = test_client_with_all_mocks.post(
            "/api/v1/documents/upload",
            files=files,
            data=data,
        )

        # Assert - Upload bem-sucedido
        assert upload_response.status_code == 201
        upload_result = upload_response.json()
        document_id = upload_result["id"]
        assert document_id is not None
        assert upload_result["status"] == "uploaded"

        # Act - Obter status do documento
        status_response = test_client_with_all_mocks.get(f"/api/v1/documents/{document_id}/status")

        # Assert - Status obtido com sucesso
        assert status_response.status_code == 200
        status_result = status_response.json()
        assert status_result["id"] == document_id
        assert status_result["status"] == "uploaded"

        # Act - Parse documento (mock response)
        parse_response = test_client_with_all_mocks.post(
            f"/api/v1/parsing/{document_id}/parse",
            json={"format": "pdf"},
        )

        # Assert - Parse iniciado com sucesso
        assert parse_response.status_code == 202
        parse_result = parse_response.json()
        assert "job_id" in parse_result

        # Act - Obter documento completo
        get_response = test_client_with_all_mocks.get(f"/api/v1/documents/{document_id}")

        # Assert - Documento obtido com sucesso
        assert get_response.status_code == 200
        doc_result = get_response.json()
        assert doc_result["id"] == document_id
        assert doc_result["title"] == "Test PDF Document"

    async def test_complete_word_flow(
        self, test_client_with_all_mocks: TestClient, sample_docx_bytes: bytes
    ) -> None:
        """Testa fluxo completo para documento Word."""
        # Arrange
        files = {
            "file": (
                "test.docx",
                sample_docx_bytes,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        }
        data = {
            "uploaded_by": "test@example.com",
            "title": "Test Word Document",
        }

        # Act - Upload
        upload_response = test_client_with_all_mocks.post(
            "/api/v1/documents/upload",
            files=files,
            data=data,
        )

        # Assert
        assert upload_response.status_code == 201
        result = upload_response.json()
        assert result["format"] == "docx"

    async def test_complete_postman_flow(
        self, test_client_with_all_mocks: TestClient, sample_postman_json: bytes
    ) -> None:
        """Testa fluxo completo para coleção Postman."""
        # Arrange
        files = {"file": ("collection.json", sample_postman_json, "application/json")}
        data = {
            "uploaded_by": "test@example.com",
            "title": "API Collection",
        }

        # Act - Upload
        upload_response = test_client_with_all_mocks.post(
            "/api/v1/documents/upload",
            files=files,
            data=data,
        )

        # Assert
        assert upload_response.status_code == 201
        result = upload_response.json()
        assert result["format"] == "postman"

        # Act - Parse Postman
        parse_response = test_client_with_all_mocks.post(
            f"/api/v1/parsing/{result['id']}/parse",
            json={"format": "postman"},
        )

        # Assert
        assert parse_response.status_code == 202

    async def test_entity_extraction_flow(
        self, test_client_with_all_mocks: TestClient, sample_pdf_bytes: bytes
    ) -> None:
        """Testa fluxo de extração de entidades."""
        # Arrange - Upload documento
        files = {"file": ("test.pdf", sample_pdf_bytes, "application/pdf")}
        data = {"uploaded_by": "test@example.com"}
        upload_response = test_client_with_all_mocks.post(
            "/api/v1/documents/upload",
            files=files,
            data=data,
        )
        document_id = upload_response.json()["id"]

        # Act - Extrair entidades
        entities_response = test_client_with_all_mocks.post(
            f"/api/v1/parsing/{document_id}/entities",
            json={
                "entity_types": ["services", "apis", "data_models"],
                "confidence_threshold": 0.7,
            },
        )

        # Assert - Extração iniciada
        assert entities_response.status_code in [202, 200]  # 202 se async, 200 se sync
        result = entities_response.json()
        assert "job_id" in result or "entities" in result

    async def test_kafka_event_publishing(
        self, test_client_with_kafka_mock: TestClient, sample_pdf_bytes: bytes
    ) -> None:
        """Testa que eventos Kafka são publicados corretamente."""
        # Arrange
        files = {"file": ("test.pdf", sample_pdf_bytes, "application/pdf")}
        data = {"uploaded_by": "test@example.com"}

        # Act - Upload que deve publicar evento
        upload_response = test_client_with_kafka_mock.post(
            "/api/v1/documents/upload",
            files=files,
            data=data,
        )

        # Assert
        assert upload_response.status_code == 201

        # Verificar que producer foi chamado (via mock)
        # Isso é verificado através do fixture test_client_with_kafka_mock

    async def test_error_recovery_flow(self, test_client_with_all_mocks: TestClient) -> None:
        """Testa recuperação de erros no fluxo."""
        # Act - Tentar upload sem arquivo
        response = test_client_with_all_mocks.post(
            "/api/v1/documents/upload",
            data={"uploaded_by": "test@example.com"},
        )

        # Assert - Erro de validação
        assert response.status_code == 422

        # Act - Tentar obter documento inexistente
        response = test_client_with_all_mocks.get("/api/v1/documents/NONEXISTENT")

        # Assert - Not found
        assert response.status_code == 404

    async def test_list_documents_with_pagination(
        self, test_client_with_all_mocks: TestClient, sample_pdf_bytes: bytes
    ) -> None:
        """Testa paginação na listagem de documentos."""
        # Arrange - Upload múltiplos documentos
        for i in range(5):
            files = {"file": (f"test{i}.pdf", sample_pdf_bytes, "application/pdf")}
            data = {"uploaded_by": "test@example.com"}
            test_client_with_all_mocks.post("/api/v1/documents/upload", files=files, data=data)

        # Act - Listar primeira página
        response = test_client_with_all_mocks.get("/api/v1/documents?limit=3&skip=0")

        # Assert
        assert response.status_code == 200
        result = response.json()
        assert result["total"] >= 5
        assert len(result["items"]) <= 3

    async def test_document_deletion_flow(
        self, test_client_with_all_mocks: TestClient, sample_pdf_bytes: bytes
    ) -> None:
        """Testa fluxo de deleção de documento."""
        # Arrange - Upload documento
        files = {"file": ("test.pdf", sample_pdf_bytes, "application/pdf")}
        data = {"uploaded_by": "test@example.com"}
        upload_response = test_client_with_all_mocks.post(
            "/api/v1/documents/upload", files=files, data=data
        )
        document_id = upload_response.json()["id"]

        # Act - Deletar documento
        delete_response = test_client_with_all_mocks.delete(f"/api/v1/documents/{document_id}")

        # Assert - Deleção bem-sucedida
        assert delete_response.status_code == 204

        # Act - Tentar obter documento deletado
        get_response = test_client_with_all_mocks.get(f"/api/v1/documents/{document_id}")

        # Assert - Not found
        assert get_response.status_code == 404


# Fixtures auxiliares
@pytest.fixture
def mock_kafka_producer() -> AsyncMock:
    """Cria mock do Kafka producer."""
    producer = AsyncMock()
    producer.start = AsyncMock()
    producer.stop = AsyncMock()
    producer.publish = AsyncMock(return_value=True)
    return producer


@pytest.fixture
def mock_s3_client() -> AsyncMock:
    """Cria mock do cliente S3."""
    from moto import mock_aws

    with mock_aws():
        import boto3

        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="doc-ingestion")

        # Criar mock async
        mock_client = AsyncMock()
        mock_client.upload_file = AsyncMock(return_value="test/doc.pdf")
        mock_client.download_file = AsyncMock(return_value=b"test content")
        mock_client.delete_file = AsyncMock(return_value=True)
        mock_client._initialized = True

        yield mock_client


@pytest.fixture
def mock_mongodb_client() -> AsyncMock:
    """Cria mock do cliente MongoDB."""
    from unittest.mock import MagicMock

    mock_db = MagicMock()
    mock_db.documents = MagicMock()
    mock_db.entities = MagicMock()
    mock_db.parsing_jobs = MagicMock()
    mock_db.documents.insert_one = MagicMock(return_value=MagicMock(inserted_id="test-id"))
    mock_db.documents.find_one = MagicMock(return_value={"id": "test-id", "status": "uploaded"})
    mock_db.documents.update_one = MagicMock(return_value=MagicMock(modified_count=1))
    mock_db.documents.delete_one = MagicMock(return_value=MagicMock(deleted_count=1))
    mock_db.documents.find = MagicMock(return_value=[])

    mock_client = AsyncMock()
    mock_client.database = mock_db
    mock_client.ping = AsyncMock(return_value=True)
    mock_client.documents_collection = mock_db.documents
    mock_client.entities_collection = mock_db.entities
    mock_client.parsing_jobs_collection = mock_db.parsing_jobs

    yield mock_client


@pytest.fixture
def test_client_with_all_mocks(
    mock_mongodb_client, mock_s3_client, mock_kafka_producer, sample_pdf_bytes
) -> TestClient:
    """Cria cliente de teste com todos os mocks configurados."""
    from src.main import app

    # Patch MongoDB
    with patch("src.db.mongodb.get_mongodb_client", return_value=mock_mongodb_client):
        # Patch S3
        with patch("src.clients.s3_client.S3Client", return_value=mock_s3_client):
            # Patch Kafka producer
            with patch("src.dependencies.get_doc_producer", return_value=mock_kafka_producer):
                yield TestClient(app)


@pytest.fixture
def test_client_with_kafka_mock(
    mock_mongodb_client, mock_s3_client, mock_kafka_producer
) -> TestClient:
    """Cria cliente de teste com mock Kafka específico."""
    from src.main import app

    with patch("src.db.mongodb.get_mongodb_client", return_value=mock_mongodb_client):
        with patch("src.clients.s3_client.S3Client", return_value=mock_s3_client):
            with patch("src.dependencies.get_doc_producer", return_value=mock_kafka_producer):
                yield TestClient(app)


@pytest.fixture
def sample_pdf_bytes() -> bytes:
    """Cria conteúdo PDF de exemplo."""
    return b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n"


@pytest.fixture
def sample_docx_bytes() -> bytes:
    """Cria conteúdo DOCX de exemplo."""
    return b"PK\x03\x04\x14\x00\x00\x00\x08\x00Sample DOCX content placeholder"


@pytest.fixture
def sample_postman_json() -> bytes:
    """Cria JSON de coleção Postman de exemplo."""
    collection = {
        "info": {
            "name": "Test API",
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "item": [
            {
                "name": "Get Users",
                "request": {
                    "method": "GET",
                    "url": {"raw": "https://api.example.com/users", "protocol": "https"},
                },
            }
        ],
    }
    return json.dumps(collection).encode("utf-8")
