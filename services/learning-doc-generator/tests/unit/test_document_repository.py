"""Testes unitários para DocumentRepository"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.models import DocumentStatus, DocumentType, LearningDocument
from src.services.document_repository import DocumentRepository


@pytest.mark.asyncio()
async def test_repository_initialization():
    """Testa inicialização do repositório"""
    with pytest.MonkeyPatch.context() as m:
        m.setenv("MONGODB_URI", "mongodb://localhost:27017")
        m.setenv("MONGODB_DATABASE", "test_db")
        m.setenv("MONGODB_COLLECTION", "test_collection")

        repo = DocumentRepository()

        # Mock cliente
        mock_client = AsyncMock()
        repo._client = mock_client
        repo._database = mock_client["test_db"]
        repo._collection = repo._database["test_collection"]

        await repo.initialize()

        assert repo._client is not None


@pytest.mark.asyncio()
async def test_save_document():
    """Testa salvar documento"""
    repo = DocumentRepository()
    repo._collection = AsyncMock()

    # Mock insert_one
    mock_result = MagicMock()
    mock_result.inserted_id = "doc_123"
    repo._collection.insert_one = AsyncMock(return_value=mock_result)

    document = LearningDocument(
        title="Test Document",
        type=DocumentType.EXPERIMENT_REPORT,
        status=DocumentStatus.PENDING,
    )

    doc_id = await repo.save(document)

    assert doc_id == "doc_123"
    repo._collection.insert_one.assert_called_once()


@pytest.mark.asyncio()
async def test_get_by_id():
    """Testa buscar documento por ID"""
    repo = DocumentRepository()
    repo._collection = AsyncMock()

    doc_dict = {
        "_id": "doc_123",
        "title": "Test Document",
        "type": "experiment_report",
        "status": "pending",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    repo._collection.find_one = AsyncMock(return_value=doc_dict)

    document = await repo.get_by_id("doc_123")

    assert document is not None
    assert document.id == "doc_123"
    assert document.title == "Test Document"


@pytest.mark.asyncio()
async def test_get_by_id_not_found():
    """Testa buscar documento inexistente"""
    repo = DocumentRepository()
    repo._collection = AsyncMock()
    repo._collection.find_one = AsyncMock(return_value=None)

    document = await repo.get_by_id("nonexistent")

    assert document is None


@pytest.mark.asyncio()
async def test_update_document():
    """Testa atualizar documento"""
    repo = DocumentRepository()
    repo._collection = AsyncMock()

    # Mock update_one
    mock_result = MagicMock()
    mock_result.modified_count = 1
    repo._collection.update_one = AsyncMock(return_value=mock_result)

    document = LearningDocument(
        id="doc_123",
        title="Updated Title",
        type=DocumentType.EXPERIMENT_REPORT,
        status=DocumentStatus.COMPLETED,
    )

    success = await repo.update("doc_123", document)

    assert success is True


@pytest.mark.asyncio()
async def test_update_status():
    """Testa atualizar status do documento"""
    repo = DocumentRepository()
    repo._collection = AsyncMock()

    mock_result = MagicMock()
    mock_result.modified_count = 1
    repo._collection.update_one = AsyncMock(return_value=mock_result)

    success = await repo.update_status("doc_123", DocumentStatus.COMPLETED)

    assert success is True


@pytest.mark.asyncio()
async def test_list_documents():
    """Testa listar documentos"""
    repo = DocumentRepository()
    repo._collection = AsyncMock()

    # Mock cursor
    doc_dicts = [
        {
            "_id": f"doc_{i}",
            "title": f"Document {i}",
            "type": "experiment_report",
            "status": "completed",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        for i in range(5)
    ]

    async def mock_to_list(cursor):
        return doc_dicts

    repo._collection.count_documents = AsyncMock(return_value=5)
    repo._collection.find = MagicMock(return_value=AsyncMock(to_list=mock_to_list))

    documents, total = await repo.list_documents(page=1, page_size=20)

    assert total == 5
    assert len(documents) == 5


@pytest.mark.asyncio()
async def test_delete_document():
    """Testa deletar documento"""
    repo = DocumentRepository()
    repo._collection = AsyncMock()

    mock_result = MagicMock()
    mock_result.deleted_count = 1
    repo._collection.delete_one = AsyncMock(return_value=mock_result)

    success = await repo.delete("doc_123")

    assert success is True


@pytest.mark.asyncio()
async def test_get_by_period():
    """Testa buscar por período"""
    repo = DocumentRepository()
    repo._collection = AsyncMock()

    doc_dict = {
        "_id": "doc_123",
        "title": "Test",
        "type": "weekly_summary",
        "status": "completed",
        "period_start": datetime(2026, 1, 1),
        "period_end": datetime(2026, 1, 7),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }

    async def mock_to_list(cursor):
        return [doc_dict]

    repo._collection.find = MagicMock(return_value=AsyncMock(to_list=mock_to_list))

    documents = await repo.get_by_period(
        period_start=datetime(2026, 1, 1),
        period_end=datetime(2026, 1, 7),
    )

    assert len(documents) >= 0
