"""Testes unitários para o cliente S3/MinIO."""

from unittest.mock import Mock, patch

import pytest
from minio.error import S3Error

from src.clients.s3_client import S3Client, get_s3_client


@pytest.fixture
def mock_settings():
    """Fixture para mock das configurações."""
    with patch("src.clients.s3_client.get_settings") as mock:
        settings = Mock()
        settings.s3_endpoint = "http://localhost:9000"
        settings.s3_access_key = "minioadmin"
        settings.s3_secret_key = "minioadmin"
        settings.s3_bucket = "doc-ingestion"
        settings.s3_secure = False
        mock.return_value = settings
        yield mock


@pytest.fixture
def reset_singleton():
    """Reseta o singleton entre testes."""
    S3Client._instance = None
    yield
    S3Client._instance = None


@pytest.fixture
def s3_client(reset_singleton, mock_settings):
    """Fixture para instância do S3Client."""
    return S3Client()


@pytest.mark.asyncio
async def test_s3_client_initialize_creates_bucket(s3_client, mock_settings):
    """Testa inicialização do cliente quando bucket não existe."""
    # Arrange
    with patch("src.clients.s3_client.Minio") as mock_minio:
        mock_client = Mock()
        mock_client.bucket_exists = Mock(return_value=False)
        mock_client.make_bucket = Mock()
        mock_minio.return_value = mock_client

        # Act
        await s3_client.initialize()

        # Assert
        assert s3_client._client is not None
        mock_client.bucket_exists.assert_called_once_with("doc-ingestion")
        mock_client.make_bucket.assert_called_once_with("doc-ingestion")


@pytest.mark.asyncio
async def test_s3_client_initialize_bucket_exists(s3_client, mock_settings):
    """Testa inicialização do cliente quando bucket já existe."""
    # Arrange
    with patch("src.clients.s3_client.Minio") as mock_minio:
        mock_client = Mock()
        mock_client.bucket_exists = Mock(return_value=True)
        mock_client.make_bucket = Mock()
        mock_minio.return_value = mock_client

        # Act
        await s3_client.initialize()

        # Assert
        assert s3_client._client is not None
        mock_client.bucket_exists.assert_called_once_with("doc-ingestion")
        mock_client.make_bucket.assert_not_called()


@pytest.mark.asyncio
async def test_s3_client_initialize_error(s3_client, mock_settings):
    """Testa tratamento de erro na inicialização."""
    # Arrange
    with patch("src.clients.s3_client.Minio") as mock_minio:
        mock_minio.side_effect = Exception("Connection error")

        # Act & Assert
        with pytest.raises(Exception, match="Connection error"):
            await s3_client.initialize()


@pytest.mark.asyncio
async def test_s3_client_upload_file(s3_client, mock_settings):
    """Testa upload de arquivo para S3/MinIO."""
    # Arrange
    with patch("src.clients.s3_client.Minio") as mock_minio:
        mock_client = Mock()
        mock_client.put_object = Mock()
        mock_minio.return_value = mock_client

        await s3_client.initialize()
        content = b"test file content"
        metadata = {"content-type": "application/pdf"}

        # Act
        s3_key = await s3_client.upload_file(
            ingestion_id="ingestion-001",
            filename="test.pdf",
            content=content,
            metadata=metadata,
        )

        # Assert
        assert s3_key == "ingestion-001/raw/test.pdf"
        mock_client.put_object.assert_called_once()
        call_args = mock_client.put_object.call_args
        assert call_args[1]["bucket_name"] == "doc-ingestion"
        assert call_args[1]["object_name"] == "ingestion-001/raw/test.pdf"
        assert call_args[1]["length"] == len(content)
        assert call_args[1]["metadata"] == metadata


@pytest.mark.asyncio
async def test_s3_client_upload_file_without_metadata(s3_client, mock_settings):
    """Testa upload de arquivo sem metadados."""
    # Arrange
    with patch("src.clients.s3_client.Minio") as mock_minio:
        mock_client = Mock()
        mock_client.put_object = Mock()
        mock_minio.return_value = mock_client

        await s3_client.initialize()
        content = b"test file content"

        # Act
        s3_key = await s3_client.upload_file(
            ingestion_id="ingestion-001",
            filename="test.pdf",
            content=content,
        )

        # Assert
        assert s3_key == "ingestion-001/raw/test.pdf"
        call_args = mock_client.put_object.call_args
        assert call_args[1]["metadata"] == {}


@pytest.mark.asyncio
async def test_s3_client_upload_file_not_initialized(s3_client, mock_settings):
    """Testa erro ao fazer upload sem inicializar."""
    # Arrange
    content = b"test content"

    # Act & Assert
    with pytest.raises(RuntimeError, match="S3 client not initialized"):
        await s3_client.upload_file(
            ingestion_id="ingestion-001",
            filename="test.pdf",
            content=content,
        )


@pytest.mark.asyncio
async def test_s3_client_upload_file_s3_error(s3_client, mock_settings):
    """Testa tratamento de S3Error no upload."""
    # Arrange
    with patch("src.clients.s3_client.Minio") as mock_minio:
        mock_client = Mock()
        error = S3Error(
            message="Access denied",
            resource="doc-ingestion",
            request_id="test-id",
            code="AccessDenied",
            host_id="host-id",
            response=Mock(),
        )
        mock_client.put_object = Mock(side_effect=error)
        mock_minio.return_value = mock_client

        await s3_client.initialize()
        content = b"test content"

        # Act & Assert
        with pytest.raises(S3Error):
            await s3_client.upload_file(
                ingestion_id="ingestion-001",
                filename="test.pdf",
                content=content,
            )


@pytest.mark.asyncio
async def test_s3_client_download_file(s3_client, mock_settings):
    """Testa download de arquivo do S3/MinIO."""
    # Arrange
    with patch("src.clients.s3_client.Minio") as mock_minio:
        mock_client = Mock()
        mock_response = Mock()
        mock_response.read = Mock(return_value=b"downloaded content")
        mock_response.close = Mock()
        mock_response.release_conn = Mock()
        mock_client.get_object = Mock(return_value=mock_response)
        mock_minio.return_value = mock_client

        await s3_client.initialize()

        # Act
        content = await s3_client.download_file("ingestion-001/raw/test.pdf")

        # Assert
        assert content == b"downloaded content"
        mock_client.get_object.assert_called_once_with(
            bucket_name="doc-ingestion",
            object_name="ingestion-001/raw/test.pdf",
        )
        mock_response.close.assert_called_once()
        mock_response.release_conn.assert_called_once()


@pytest.mark.asyncio
async def test_s3_client_download_file_not_initialized(s3_client):
    """Testa erro ao fazer download sem inicializar."""
    # Act & Assert
    with pytest.raises(RuntimeError, match="S3 client not initialized"):
        await s3_client.download_file("ingestion-001/raw/test.pdf")


@pytest.mark.asyncio
async def test_s3_client_delete_file(s3_client, mock_settings):
    """Testa deleção de arquivo do S3/MinIO."""
    # Arrange
    with patch("src.clients.s3_client.Minio") as mock_minio:
        mock_client = Mock()
        mock_client.remove_object = Mock()
        mock_minio.return_value = mock_client

        await s3_client.initialize()

        # Act
        await s3_client.delete_file("ingestion-001/raw/test.pdf")

        # Assert
        mock_client.remove_object.assert_called_once_with(
            bucket_name="doc-ingestion",
            object_name="ingestion-001/raw/test.pdf",
        )


@pytest.mark.asyncio
async def test_s3_client_delete_file_not_initialized(s3_client):
    """Testa erro ao deletar sem inicializar."""
    # Act & Assert
    with pytest.raises(RuntimeError, match="S3 client not initialized"):
        await s3_client.delete_file("ingestion-001/raw/test.pdf")


@pytest.mark.asyncio
async def test_s3_client_list_files(s3_client, mock_settings):
    """Testa listagem de arquivos de uma ingestão."""
    # Arrange
    with patch("src.clients.s3_client.Minio") as mock_minio:
        mock_client = Mock()
        mock_obj1 = Mock()
        mock_obj1.object_name = "ingestion-001/raw/file1.pdf"
        mock_obj2 = Mock()
        mock_obj2.object_name = "ingestion-001/raw/file2.docx"
        mock_client.list_objects = Mock(return_value=[mock_obj1, mock_obj2])
        mock_minio.return_value = mock_client

        await s3_client.initialize()

        # Act
        files = await s3_client.list_files("ingestion-001")

        # Assert
        assert len(files) == 2
        assert "ingestion-001/raw/file1.pdf" in files
        assert "ingestion-001/raw/file2.docx" in files
        mock_client.list_objects.assert_called_once_with(
            bucket_name="doc-ingestion",
            prefix="ingestion-001/raw/",
            recursive=True,
        )


@pytest.mark.asyncio
async def test_s3_client_list_files_with_custom_prefix(s3_client, mock_settings):
    """Testa listagem de arquivos com prefixo customizado."""
    # Arrange
    with patch("src.clients.s3_client.Minio") as mock_minio:
        mock_client = Mock()
        mock_obj = Mock()
        mock_obj.object_name = "ingestion-001/parsed/entities.json"
        mock_client.list_objects = Mock(return_value=[mock_obj])
        mock_minio.return_value = mock_client

        await s3_client.initialize()

        # Act
        files = await s3_client.list_files("ingestion-001", prefix="parsed")

        # Assert
        assert len(files) == 1
        assert "ingestion-001/parsed/entities.json" in files
        mock_client.list_objects.assert_called_once_with(
            bucket_name="doc-ingestion",
            prefix="ingestion-001/parsed/",
            recursive=True,
        )


@pytest.mark.asyncio
async def test_s3_client_list_files_not_initialized(s3_client):
    """Testa erro ao listar arquivos sem inicializar."""
    # Act & Assert
    with pytest.raises(RuntimeError, match="S3 client not initialized"):
        await s3_client.list_files("ingestion-001")


@pytest.mark.asyncio
async def test_s3_client_list_files_empty(s3_client, mock_settings):
    """Testa listagem quando não há arquivos."""
    # Arrange
    with patch("src.clients.s3_client.Minio") as mock_minio:
        mock_client = Mock()
        mock_client.list_objects = Mock(return_value=[])
        mock_minio.return_value = mock_client

        await s3_client.initialize()

        # Act
        files = await s3_client.list_files("ingestion-001")

        # Assert
        assert files == []


@pytest.mark.asyncio
async def test_s3_client_build_s3_key(s3_client):
    """Testa construção de chave S3 com prefixo padrão."""
    # Act
    key = s3_client._build_s3_key("ingestion-001", "test.pdf")

    # Assert
    assert key == "ingestion-001/raw/test.pdf"


@pytest.mark.asyncio
async def test_s3_client_build_s3_key_custom_prefix(s3_client):
    """Testa construção de chave S3 com prefixo customizado."""
    # Act
    key = s3_client._build_s3_key("ingestion-001", "entities.json", prefix="parsed")

    # Assert
    assert key == "ingestion-001/parsed/entities.json"


@pytest.mark.asyncio
async def test_s3_client_singleton(reset_singleton, mock_settings):
    """Testa padrão singleton do S3Client."""
    # Arrange & Act
    client1 = S3Client()
    client2 = S3Client()

    # Assert
    assert client1 is client2, "Deve retornar a mesma instância"


@pytest.mark.asyncio
async def test_get_s3_client_singleton(reset_singleton, mock_settings):
    """Testa função get_s3_client como singleton."""
    # Arrange
    with patch("src.clients.s3_client.Minio") as mock_minio:
        mock_client = Mock()
        mock_client.bucket_exists = Mock(return_value=True)
        mock_minio.return_value = mock_client

        # Act
        client1 = await get_s3_client()
        client2 = await get_s3_client()

        # Assert
        assert client1 is client2
