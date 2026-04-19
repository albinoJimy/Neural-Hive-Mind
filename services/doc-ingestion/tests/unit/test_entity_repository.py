"""Testes unitários para EntityRepository."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.models.entities import EntityType, ExtractedEntity
from src.repositories.entity_repository import EntityRepository


@pytest.fixture
def mock_mongodb_client():
    """Cliente MongoDB mock."""
    client = MagicMock()
    client.entities_collection = MagicMock()
    return client


@pytest.fixture
def entity_repository(mock_mongodb_client):
    """Repositório de entidades para testes."""
    return EntityRepository(mock_mongodb_client)


@pytest.fixture
def sample_entities():
    """Entidades de exemplo."""
    return [
        ExtractedEntity(
            id="ent1",
            type=EntityType.FUNCTIONALITY,
            name="User Login",
            description="Login functionality for users",
            source_text="The system shall provide user login",
            confidence_score=0.9,
            document_id="doc1",
        ),
        ExtractedEntity(
            id="ent2",
            type=EntityType.REQUIREMENT,
            name="Password Requirement",
            description="Password must be 8 characters",
            source_text="Passwords must be at least 8 characters",
            confidence_score=0.85,
            document_id="doc1",
        ),
        ExtractedEntity(
            id="ent3",
            type=EntityType.API,
            name="POST /api/users",
            description="API endpoint to create users",
            source_text="POST /api/users creates a new user",
            confidence_score=0.95,
            document_id="doc1",
        ),
    ]


class TestEntityRepository:
    """Testes para EntityRepository."""

    def test_init(self, mock_mongodb_client):
        """Testa inicialização."""
        repo = EntityRepository(mock_mongodb_client)

        assert repo.mongodb_client == mock_mongodb_client
        assert repo._collection is None

    def test_collection_lazy_init(self, entity_repository, mock_mongodb_client):
        """Testa lazy initialization da coleção."""
        collection = entity_repository.collection

        assert collection == mock_mongodb_client.entities_collection
        # Segunda chamada retorna cache
        assert entity_repository.collection is collection

    @pytest.mark.asyncio
    async def test_create_many_empty_list(self, entity_repository):
        """Testa criar lista vazia de entidades."""
        result = await entity_repository.create_many([], "doc1")

        assert result == []

    @pytest.mark.asyncio
    async def test_create_many_success(
        self, entity_repository, mock_mongodb_client, sample_entities
    ):
        """Testa criar múltiplas entidades."""
        # Mock insert_many
        mock_result = MagicMock()
        mock_result.inserted_ids = ["id1", "id2", "id3"]
        mock_mongodb_client.entities_collection.insert_many = AsyncMock(
            return_value=mock_result
        )

        result = await entity_repository.create_many(sample_entities, "doc1")

        assert len(result) == 3
        assert result == ["id1", "id2", "id3"]
        mock_mongodb_client.entities_collection.insert_many.assert_called_once()

        # Verificar documentos inseridos
        call_args = mock_mongodb_client.entities_collection.insert_many.call_args
        documents = call_args[0][0]
        assert len(documents) == 3
        assert documents[0]["document_id"] == "doc1"
        assert documents[0]["type"] == EntityType.FUNCTIONALITY
        assert documents[0]["name"] == "User Login"
        assert "extracted_at" in documents[0]
        assert documents[0]["extracted_by"] == "entity_extractor"

    @pytest.mark.asyncio
    async def test_list_by_document(
        self, entity_repository, mock_mongodb_client
    ):
        """Testa listar entidades por documento."""
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(
            return_value=[
                {
                    "_id": "id1",
                    "type": EntityType.FUNCTIONALITY,
                    "name": "User Login",
                    "document_id": "doc1",
                }
            ]
        )
        mock_mongodb_client.entities_collection.find = MagicMock(return_value=mock_cursor)

        result = await entity_repository.list_by_document("doc1")

        assert len(result) == 1
        assert result[0]["name"] == "User Login"
        mock_cursor.to_list.assert_called_once_with(length=None)

    @pytest.mark.asyncio
    async def test_list_by_document_with_type_filter(
        self, entity_repository, mock_mongodb_client
    ):
        """Testa listar entidades por documento e tipo."""
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=[])
        mock_mongodb_client.entities_collection.find = MagicMock(return_value=mock_cursor)

        await entity_repository.list_by_document("doc1", EntityType.API)

        # Verificar query com filtro
        call_args = mock_mongodb_client.entities_collection.find.call_args
        query = call_args[0][0]
        assert query["document_id"] == "doc1"
        assert query["type"] == EntityType.API

    @pytest.mark.asyncio
    async def test_delete_by_document(
        self, entity_repository, mock_mongodb_client
    ):
        """Testa deletar entidades por documento."""
        mock_result = MagicMock()
        mock_result.deleted_count = 5
        mock_mongodb_client.entities_collection.delete_many = AsyncMock(
            return_value=mock_result
        )

        result = await entity_repository.delete_by_document("doc1")

        assert result == 5
        mock_mongodb_client.entities_collection.delete_many.assert_called_once_with(
            {"document_id": "doc1"}
        )
