"""Testes de integração para entity persistence."""

import pytest
from httpx import AsyncClient
from src.main import app
from src.db.mongodb import get_mongodb_client


@pytest.mark.asyncio
async def test_extract_entities_persists_to_mongodb():
    """Testa que entidades extraídas são persistidas na coleção entities."""
    # Setup
    mongodb_client = await get_mongodb_client()
    await mongodb_client.connect()

    # Limpar coleção entities
    entities_collection = mongodb_client.db.get("entities")
    await entities_collection.delete_many({})

    # Criar documento de teste
    from src.models.document import DocumentCreate, DocumentFormat
    from src.repositories.document_repository import DocumentRepository

    repository = DocumentRepository()
    doc_create = DocumentCreate(
        filename="test.pdf",
        format=DocumentFormat.PDF,
        file_size_bytes=1024,
        s3_key="test/test.pdf",
        uploaded_by="test_user",
    )
    document = await repository.create(doc_create)

    # Extrair entidades
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/documents/{document.id}/parse",
        )
        assert response.status_code == 202

        response = await client.post(
            f"/api/v1/documents/{document.id}/extract", params={"min_confidence": 0.5}
        )
        assert response.status_code == 202

    # Verificar que entidades foram persistidas
    entities = await entities_collection.find({"document_id": document.id}).to_list(None)
    assert len(entities) > 0, "Entities should be persisted"
    assert entities[0].get("document_id") == document.id

    # Cleanup
    await entities_collection.delete_many({"document_id": document.id})
    await repository.delete(document.id)
    await mongodb_client.disconnect()
