"""Testes unitários para ArtifactStore."""

import pytest
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch
from bson import Binary

from src.services.artifact_store import (
    ArtifactStore,
    get_artifact_store
)


class TestArtifactStore:
    """Testes para ArtifactStore."""

    @pytest.fixture
    def mock_gridfs(self):
        """Mock para GridFS."""
        gridfs = Mock()
        gridfs.put = Mock(return_value="gridfs-id-123")
        gridfs.get = Mock()
        gridfs.delete = Mock()
        gridfs.list = Mock(return_value={"length": 5})
        return gridfs

    @pytest.fixture
    def mock_collection(self):
        """Mock para coleção MongoDB."""
        collection = Mock()
        collection.create_index = Mock()
        collection.insert_one = Mock(return_value=Mock(inserted_id="id-123"))
        collection.find_one = Mock()
        collection.find = Mock()
        collection.update_one = Mock()
        collection.delete_one = Mock()
        collection.delete_many = AsyncMock(return_value=Mock(deleted_count=5))
        collection.count_documents = AsyncMock(return_value=10)
        collection.aggregate = AsyncMock()
        return collection

    @pytest.fixture
    def artifact_store(self, mock_gridfs, mock_collection):
        """Fixture para ArtifactStore com mocks."""
        # Criar store sem MongoDB client real
        with patch('src.services.artifact_store.GridFS', return_value=mock_gridfs):
            with patch('src.services.artifact_store.MongoClient'):
                store = ArtifactStore()
                store._gridfs = mock_gridfs
                store._collection = mock_collection
                return store

    def test_get_artifact_store_singleton(self):
        """Testa se get_artifact_store retorna instância."""
        # Mock tanto MongoClient como GridFS para evitar erro de database
        with patch('src.services.artifact_store.MongoClient'):
            with patch('src.services.artifact_store.GridFS'):
                store = get_artifact_store()
                assert isinstance(store, ArtifactStore)

    def test_ensure_indexes(self, artifact_store, mock_collection):
        """Testa criação de índices."""
        artifact_store._ensure_indexes()
        assert mock_collection.create_index.call_count == 4

    def test_store_artifact_with_string_content(
        self, artifact_store, mock_gridfs, mock_collection
    ):
        """Testa armazenamento de artefato com conteúdo string."""
        mock_gridfs_file = Mock()
        mock_gridfs_file.read = Mock(return_value=b"test content")
        mock_gridfs.get = Mock(return_value=mock_gridfs_file)

        import asyncio
        result = asyncio.run(artifact_store.store_artifact(
            approval_id="approval-123",
            artifact_type="code",
            content="print('hello world')",
            filename="test.py",
            metadata={"language": "python"}
        ))

        assert result is not None
        assert isinstance(result, str)
        mock_gridfs.put.assert_called_once()
        assert mock_collection.insert_one.call_count >= 1

    def test_store_artifact_with_bytes_content(
        self, artifact_store, mock_gridfs
    ):
        """Testa armazenamento de artefato com conteúdo bytes."""
        import asyncio
        result = asyncio.run(artifact_store.store_artifact(
            approval_id="approval-123",
            artifact_type="binary",
            content=b"\x00\x01\x02\x03",
            filename="test.bin"
        ))

        assert result is not None
        mock_gridfs.put.assert_called_once()

    def test_store_artifact_gridfs_failure_fallback(
        self, artifact_store, mock_gridfs, mock_collection
    ):
        """Testa fallback para BSON Binary quando GridFS falha."""
        mock_gridfs.put = Mock(side_effect=Exception("GridFS error"))

        import asyncio
        result = asyncio.run(artifact_store.store_artifact(
            approval_id="approval-123",
            artifact_type="document",
            content="test content"
        ))

        assert result is not None
        # Verificar que insert_one foi chamado (fallback)
        assert mock_collection.insert_one.call_count >= 1

    def test_get_artifact_found(self, artifact_store, mock_collection):
        """Testa recuperação de artefato existente."""
        mock_collection.find_one = Mock(return_value={
            "artifact_id": "artifact-123",
            "approval_id": "approval-123",
            "artifact_type": "code",
            "storage": "bson_binary",
            "content_bson": Binary(b"test content"),
            "filename": "test.py",
            "size_bytes": 12,
            "version": "1.0.0",
            "created_at": datetime.utcnow(),
            "metadata": {}
        })

        import asyncio
        result = asyncio.run(artifact_store.get_artifact("artifact-123"))

        assert result is not None
        assert result["artifact_id"] == "artifact-123"
        assert result["content"] == "test content"
        mock_collection.find_one.assert_called_once_with({"artifact_id": "artifact-123"})

    def test_get_artifact_not_found(self, artifact_store, mock_collection):
        """Testa recuperação de artefato inexistente."""
        mock_collection.find_one = Mock(return_value=None)

        import asyncio
        result = asyncio.run(artifact_store.get_artifact("artifact-999"))

        assert result is None

    def test_get_artifact_with_gridfs(
        self, artifact_store, mock_collection, mock_gridfs
    ):
        """Testa recuperação de artefato do GridFS."""
        mock_gridfs_file = Mock()
        mock_gridfs_file.read = Mock(return_value=b"content from gridfs")
        mock_gridfs.get = Mock(return_value=mock_gridfs_file)

        mock_collection.find_one = Mock(return_value={
            "artifact_id": "artifact-123",
            "storage": "gridfs",
            "gridfs_id": "gridfs-id-123",
            "filename": "test.py",
            "size_bytes": 18,
            "version": "1.0.0",
            "created_at": datetime.utcnow(),
            "metadata": {}
        })

        import asyncio
        result = asyncio.run(artifact_store.get_artifact("artifact-123"))

        assert result is not None
        assert result["content"] == b"content from gridfs"
        mock_gridfs.get.assert_called_once_with("gridfs-id-123")

    def test_get_artifacts_by_approval(self, artifact_store, mock_collection):
        """Testa listagem de artefatos por aprovação."""
        mock_cursor = Mock()
        mock_cursor.sort = Mock(return_value=mock_cursor)

        # Criar lista assíncrona mock
        artifacts = [
            {
                "artifact_id": "artifact-1",
                "artifact_type": "code",
                "filename": "test.py",
                "content_type": "text/plain",
                "size_bytes": 100,
                "version": "1.0.0",
                "created_at": datetime.utcnow(),
                "metadata": {}
            },
            {
                "artifact_id": "artifact-2",
                "artifact_type": "document",
                "filename": "README.md",
                "content_type": "text/markdown",
                "size_bytes": 250,
                "version": "1.0.0",
                "created_at": datetime.utcnow(),
                "metadata": {}
            }
        ]

        async def async_iteration():
            for item in artifacts:
                yield item

        mock_cursor.__aiter__ = Mock(return_value=async_iteration())
        mock_collection.find = Mock(return_value=mock_cursor)

        # Run async
        import asyncio
        result = asyncio.run(artifact_store.get_artifacts_by_approval("approval-123"))

        assert len(result) == 2
        assert result[0]["artifact_id"] == "artifact-1"
        assert result[1]["artifact_type"] == "document"

    def test_get_artifact_content_string(
        self, artifact_store, mock_collection, mock_gridfs
    ):
        """Testa recuperação de conteúdo string."""
        # Mock get_artifact para retornar artifact com conteúdo string
        import asyncio
        artifact_store.get_artifact = AsyncMock(return_value={
            "artifact_id": "artifact-123",
            "storage": "gridfs",
            "gridfs_id": "gridfs-id-123",
            "content": "decodable content"
        })

        result = asyncio.run(artifact_store.get_artifact_content("artifact-123"))

        assert result == "decodable content"

    def test_get_artifact_content_binary(
        self, artifact_store, mock_collection, mock_gridfs
    ):
        """Testa recuperação de conteúdo binário."""
        binary_content = b"\x00\x01\x02\xff"

        # Mock get_artifact para retornar artifact com conteúdo binário
        import asyncio
        artifact_store.get_artifact = AsyncMock(return_value={
            "artifact_id": "artifact-123",
            "storage": "gridfs",
            "gridfs_id": "gridfs-id-123",
            "content": binary_content
        })

        result = asyncio.run(artifact_store.get_artifact_content("artifact-123"))

        assert result == binary_content

    def test_update_artifact_metadata(self, artifact_store, mock_collection):
        """Testa atualização de metadados."""
        mock_collection.update_one = Mock(return_value=Mock(modified_count=1))

        # Run async
        import asyncio
        result = asyncio.run(artifact_store.update_artifact_metadata(
            "artifact-123",
            {"reviewed": True, "reviewer": "user-456"}
        ))

        assert result is True
        mock_collection.update_one.assert_called_once()

    def test_delete_artifact(self, artifact_store, mock_collection, mock_gridfs):
        """Testa remoção de artefato."""
        # Mock gridfs.get para retornar um arquivo válido (para get_artifact funcionar)
        mock_gridfs_file = Mock()
        mock_gridfs.get = Mock(return_value=mock_gridfs_file)
        mock_collection.delete_one = Mock(return_value=Mock(deleted_count=1))

        # Mock find_one para retornar metadados com gridfs_id
        mock_collection.find_one = Mock(return_value={
            "artifact_id": "artifact-123",
            "storage": "gridfs",
            "gridfs_id": "gridfs-id-123"
        })

        # Run async
        import asyncio
        result = asyncio.run(artifact_store.delete_artifact("artifact-123"))

        assert result is True
        mock_gridfs.delete.assert_called_once_with("gridfs-id-123")
        mock_collection.delete_one.assert_called_once()

    def test_list_artifacts(self, artifact_store, mock_collection):
        """Testa listagem de artefatos paginada."""
        mock_cursor = Mock()
        mock_cursor.sort = Mock(return_value=mock_cursor)
        mock_cursor.skip = Mock(return_value=mock_cursor)
        mock_cursor.limit = Mock(return_value=mock_cursor)

        artifacts = [
            {
                "artifact_id": "artifact-1",
                "artifact_type": "code",
                "filename": "test.py",
                "size_bytes": 100,
                "version": "1.0.0",
                "created_at": datetime.utcnow()
            }
        ]

        async def async_list(length):
            return artifacts

        mock_cursor.to_list = async_list
        mock_collection.find = Mock(return_value=mock_cursor)

        import asyncio
        result = asyncio.run(artifact_store.list_artifacts(limit=10, offset=0))

        assert len(result) == 1
        assert result[0]["artifact_id"] == "artifact-1"

    def test_get_storage_stats(self, artifact_store, mock_collection):
        """Testa obtenção de estatísticas de armazenamento."""
        mock_collection.count_documents = AsyncMock(return_value=42)

        # Criar dois mocks diferentes para cada chamada de aggregate
        # Primeira chamada: $group para soma de size_bytes
        mock_agg_size = Mock()
        mock_agg_size.to_list = AsyncMock(return_value=[{"size_bytes": 1024000}])

        # Segunda chamada: $group por artifact_type
        mock_agg_type = Mock()
        mock_agg_type.to_list = AsyncMock(return_value=[
            {"_id": "code", "count": 20},
            {"_id": "document", "count": 15},
            {"_id": "diagram", "count": 7}
        ])

        # aggregate retorna os cursores em sequência
        mock_collection.aggregate = Mock(side_effect=[mock_agg_size, mock_agg_type])

        import asyncio
        result = asyncio.run(artifact_store.get_storage_stats())

        assert result["total_artifacts"] == 42
        assert result["total_size_bytes"] == 1024000
        assert result["artifacts_by_type"]["code"] == 20

    def test_cleanup_old_artifacts(self, artifact_store, mock_collection):
        """Testa limpeza de artefatos antigos."""
        from unittest.mock import AsyncMock
        mock_collection.delete_many = AsyncMock(return_value=Mock(deleted_count=5))

        import asyncio
        result = asyncio.run(artifact_store.cleanup_old_artifacts(days_to_keep=90))

        assert result == 5
        mock_collection.delete_many.assert_called_once()
