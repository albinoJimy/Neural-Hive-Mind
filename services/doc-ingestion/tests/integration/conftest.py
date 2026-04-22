"""Configuração de fixtures para testes de integração."""

import asyncio
from collections.abc import Generator
from io import BytesIO
from typing import Any

import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pymongo import MongoClient

from src.main import app
from src.models.document import DocumentFormat, DocumentStatus


@pytest.fixture
def event_loop() -> asyncio.AbstractEventLoop:
    """Cria event loop para testes assíncronos."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_s3() -> Generator:
    """Cria mock do S3/MinIO."""
    with mock_aws():
        import boto3

        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="doc-ingestion")
        yield s3


@pytest.fixture
def mock_mongodb() -> Generator:
    """Cria mock do MongoDB."""
    client = MongoClient("mongodb://localhost:27017/test_db")

    # Criar banco de dados de teste
    db = client["test_doc_ingestion"]

    # Criar coleções
    db.create_collection("documents")
    db.create_collection("entities")
    db.create_collection("parsing_jobs")

    # Criar índices
    db.documents.create_index("id", unique=True)
    db.documents.create_index("status")
    db.documents.create_index("format")
    db.entities.create_index("document_id")

    yield db

    # Limpeza
    client.drop_database("test_doc_ingestion")
    client.close()


@pytest.fixture
def sample_pdf_bytes() -> bytes:
    """Cria conteúdo PDF de exemplo."""
    try:
        # Usar pypdf para criar um PDF simples
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas

        buffer = BytesIO()
        p = canvas.Canvas(buffer, pagesize=letter)
        p.drawString(100, 750, "Sample Document")
        p.drawString(100, 730, "This is a test document for parsing.")
        p.drawString(100, 710, "It contains multiple lines of text.")
        p.drawString(100, 690, "End of document.")
        p.save()

        return buffer.getvalue()
    except ImportError:
        # Se reportlab não estiver disponível, retornar bytes dummy
        return b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n"


@pytest.fixture
def sample_docx_bytes() -> bytes:
    """Cria conteúdo DOCX de exemplo."""
    # Retorna bytes dummy representando um DOCX
    return b"PK\x03\x04\x14\x00\x00\x00\x08\x00" b"Sample DOCX content placeholder"


@pytest.fixture
def sample_postman_json() -> bytes:
    """Cria JSON de coleção Postman de exemplo."""
    import json

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
            },
            {
                "name": "Create User",
                "request": {
                    "method": "POST",
                    "url": {"raw": "https://api.example.com/users", "protocol": "https"},
                },
            },
        ],
    }

    return json.dumps(collection).encode("utf-8")


@pytest.fixture
def test_client(mock_mongodb, mock_s3) -> TestClient:
    """Cria cliente de teste FastAPI."""
    from unittest.mock import AsyncMock, patch

    # Mock do MongoDB client
    with patch("src.db.mongodb.get_mongodb_client", new_callable=AsyncMock) as mock_mongo_client:
        # Criar mock async client
        mock_async_client = AsyncMock()
        mock_async_client.database = mock_mongodb
        mock_async_client.client = mock_mongodb.client
        mock_async_client.ping = AsyncMock(return_value=True)
        mock_async_client.documents_collection = mock_mongodb.documents
        mock_async_client.entities_collection = mock_mongodb.entities
        mock_async_client.parsing_jobs_collection = mock_mongodb.parsing_jobs

        mock_mongo_client.return_value = mock_async_client

        # Mock do S3 client
        with patch("src.clients.s3_client.S3Client") as mock_s3_class:
            mock_s3_instance = AsyncMock()
            mock_s3_instance.upload_file = AsyncMock(return_value="test/doc.pdf")
            mock_s3_instance.download_file = AsyncMock(return_value=b"test content")
            mock_s3_instance._initialized = True

            mock_s3_class.return_value = mock_s3_instance
            mock_s3_class._instance = mock_s3_instance

            # Mock do producer
            with patch("src.dependencies.get_doc_producer", return_value=None):
                yield TestClient(app)


@pytest.fixture
def sample_document_data() -> dict[str, Any]:
    """Dados de documento de exemplo."""
    return {
        "id": "DOC-TEST001",
        "filename": "test.pdf",
        "format": DocumentFormat.PDF,
        "status": DocumentStatus.UPLOADED,
        "file_size_bytes": 1024,
        "s3_key": "test/test.pdf",
        "uploaded_by": "test@example.com",
        "title": "Test Document",
        "description": "A test document",
        "project_id": "PROJ-001",
        "tags": ["test", "sample"],
    }
