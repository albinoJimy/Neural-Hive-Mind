"""Testes unitários para S3ArtifactClient"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.clients.s3_artifact_client import S3ArtifactClient


@pytest.fixture
def s3_client():
    """Fixture para S3ArtifactClient com mock boto3"""
    with patch.dict('sys.modules', {'boto3': MagicMock(), 'botocore.config': MagicMock()}):
        client = S3ArtifactClient(
            bucket='test-bucket',
            region='us-east-1',
            endpoint=None,
            metrics=None
        )
        return client


@pytest.fixture
def mock_boto3_client():
    """Mock do cliente boto3"""
    mock_client = MagicMock()
    mock_client.upload_file = MagicMock()
    mock_client.download_file = MagicMock()
    mock_client.head_object = MagicMock(return_value={
        'ContentLength': 1024,
        'ETag': '"abc123"',
        'LastModified': '2024-01-01T00:00:00Z',
        'Metadata': {'sha256': 'abc123def456'}
    })
    mock_client.list_objects_v2 = MagicMock(return_value={
        'Contents': [
            {'Key': 'sboms/ticket1/artifact1/sbom.json', 'Size': 1024, 'LastModified': '2024-01-01', 'ETag': '"abc"'},
            {'Key': 'sboms/ticket1/artifact2/sbom.json', 'Size': 2048, 'LastModified': '2024-01-02', 'ETag': '"def"'}
        ]
    })
    mock_client.delete_object = MagicMock()
    mock_client.head_bucket = MagicMock()
    return mock_client


@pytest.mark.asyncio
async def test_upload_sbom_success(s3_client, mock_boto3_client):
    """Testar upload de SBOM com sucesso"""
    s3_client._s3_client = mock_boto3_client

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write('{"sbom": "test"}')
        temp_path = f.name

    try:
        result = await s3_client.upload_sbom(
            local_path=temp_path,
            artifact_id='artifact-123',
            ticket_id='ticket-456'
        )

        assert result.startswith('s3://test-bucket/sboms/ticket-456/artifact-123/')
        mock_boto3_client.upload_file.assert_called_once()
    finally:
        os.unlink(temp_path)


@pytest.mark.asyncio
async def test_upload_sbom_with_encryption(s3_client, mock_boto3_client):
    """Testar upload de SBOM com encryption AES256"""
    s3_client._s3_client = mock_boto3_client

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write('{"sbom": "test"}')
        temp_path = f.name

    try:
        await s3_client.upload_sbom(
            local_path=temp_path,
            artifact_id='artifact-123',
            ticket_id='ticket-456'
        )

        call_args = mock_boto3_client.upload_file.call_args
        extra_args = call_args[1]['ExtraArgs']
        assert extra_args['ServerSideEncryption'] == 'AES256'
    finally:
        os.unlink(temp_path)


@pytest.mark.asyncio
async def test_upload_artifact_success(s3_client, mock_boto3_client):
    """Testar upload de artefato com sucesso"""
    s3_client._s3_client = mock_boto3_client

    with tempfile.NamedTemporaryFile(mode='w', suffix='.tar', delete=False) as f:
        f.write('artifact content')
        temp_path = f.name

    try:
        result = await s3_client.upload_artifact(
            local_path=temp_path,
            artifact_id='artifact-123',
            ticket_id='ticket-456'
        )

        assert result.startswith('s3://test-bucket/artifacts/ticket-456/artifact-123/')
    finally:
        os.unlink(temp_path)


@pytest.mark.asyncio
async def test_upload_sbom_failure(s3_client, mock_boto3_client):
    """Testar falha de upload de SBOM"""
    mock_boto3_client.upload_file.side_effect = Exception('Upload failed')
    s3_client._s3_client = mock_boto3_client

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write('{"sbom": "test"}')
        temp_path = f.name

    try:
        with pytest.raises(Exception, match='Upload failed'):
            await s3_client.upload_sbom(
                local_path=temp_path,
                artifact_id='artifact-123',
                ticket_id='ticket-456'
            )
    finally:
        os.unlink(temp_path)


@pytest.mark.asyncio
async def test_download_sbom_success(s3_client, mock_boto3_client):
    """Testar download de SBOM com sucesso"""
    s3_client._s3_client = mock_boto3_client

    with tempfile.TemporaryDirectory() as tmpdir:
        local_path = os.path.join(tmpdir, 'sbom.json')

        result = await s3_client.download_sbom(
            sbom_uri='s3://test-bucket/sboms/ticket-456/artifact-123/sbom.json',
            local_path=local_path
        )

        assert result is True
        mock_boto3_client.download_file.assert_called_once()


@pytest.mark.asyncio
async def test_download_sbom_invalid_uri(s3_client):
    """Testar download com URI inválida"""
    result = await s3_client.download_sbom(
        sbom_uri='file:///tmp/sbom.json',
        local_path='/tmp/local.json'
    )

    assert result is False


@pytest.mark.asyncio
async def test_download_sbom_failure(s3_client, mock_boto3_client):
    """Testar falha de download"""
    mock_boto3_client.download_file.side_effect = Exception('Download failed')
    s3_client._s3_client = mock_boto3_client

    result = await s3_client.download_sbom(
        sbom_uri='s3://test-bucket/sboms/test/sbom.json',
        local_path='/tmp/local.json'
    )

    assert result is False


@pytest.mark.asyncio
async def test_get_sbom_metadata_success(s3_client, mock_boto3_client):
    """Testar obtenção de metadados"""
    s3_client._s3_client = mock_boto3_client

    result = await s3_client.get_sbom_metadata(
        sbom_uri='s3://test-bucket/sboms/test/sbom.json'
    )

    assert result['size'] == 1024
    assert result['etag'] == '"abc123"'
    assert 'metadata' in result


@pytest.mark.asyncio
async def test_get_sbom_metadata_invalid_uri(s3_client):
    """Testar metadados com URI inválida"""
    result = await s3_client.get_sbom_metadata(
        sbom_uri='invalid-uri'
    )

    assert result == {}


@pytest.mark.asyncio
async def test_list_sboms_success(s3_client, mock_boto3_client):
    """Testar listagem de SBOMs"""
    s3_client._s3_client = mock_boto3_client

    result = await s3_client.list_sboms(ticket_id='ticket1')

    assert len(result) == 2
    assert result[0]['key'] == 'sboms/ticket1/artifact1/sbom.json'


@pytest.mark.asyncio
async def test_list_sboms_empty(s3_client, mock_boto3_client):
    """Testar listagem vazia"""
    mock_boto3_client.list_objects_v2.return_value = {}
    s3_client._s3_client = mock_boto3_client

    result = await s3_client.list_sboms(ticket_id='ticket-empty')

    assert result == []


@pytest.mark.asyncio
async def test_delete_sbom_success(s3_client, mock_boto3_client):
    """Testar deleção de SBOM"""
    s3_client._s3_client = mock_boto3_client

    result = await s3_client.delete_sbom(
        sbom_uri='s3://test-bucket/sboms/test/sbom.json'
    )

    assert result is True
    mock_boto3_client.delete_object.assert_called_once()


@pytest.mark.asyncio
async def test_delete_sbom_invalid_uri(s3_client):
    """Testar deleção com URI inválida"""
    result = await s3_client.delete_sbom(
        sbom_uri='invalid-uri'
    )

    assert result is False


@pytest.mark.asyncio
async def test_verify_sbom_integrity_success(s3_client, mock_boto3_client):
    """Testar verificação de integridade"""
    s3_client._s3_client = mock_boto3_client

    # Criar arquivo temporário e calcular checksum
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write('{"sbom": "test"}')
        temp_path = f.name

    expected_checksum = s3_client._calculate_file_checksum(temp_path)

    # Mock download para retornar o mesmo arquivo
    def mock_download(bucket, key, path):
        import shutil
        shutil.copy(temp_path, path)

    mock_boto3_client.download_file.side_effect = mock_download

    try:
        result = await s3_client.verify_sbom_integrity(
            sbom_uri='s3://test-bucket/sboms/test/sbom.json',
            expected_checksum=expected_checksum
        )

        assert result is True
    finally:
        os.unlink(temp_path)


@pytest.mark.asyncio
async def test_verify_sbom_integrity_mismatch(s3_client, mock_boto3_client):
    """Testar verificação de integridade com mismatch"""
    s3_client._s3_client = mock_boto3_client

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write('{"sbom": "different"}')
        temp_path = f.name

    def mock_download(bucket, key, path):
        import shutil
        shutil.copy(temp_path, path)

    mock_boto3_client.download_file.side_effect = mock_download

    try:
        result = await s3_client.verify_sbom_integrity(
            sbom_uri='s3://test-bucket/sboms/test/sbom.json',
            expected_checksum='wrong_checksum_value'
        )

        assert result is False
    finally:
        os.unlink(temp_path)


@pytest.mark.asyncio
async def test_health_check_success(s3_client, mock_boto3_client):
    """Testar health check com sucesso"""
    s3_client._s3_client = mock_boto3_client

    result = await s3_client.health_check()

    assert result is True
    mock_boto3_client.head_bucket.assert_called_once_with(Bucket='test-bucket')


@pytest.mark.asyncio
async def test_health_check_failure(s3_client, mock_boto3_client):
    """Testar health check com falha"""
    mock_boto3_client.head_bucket.side_effect = Exception('Bucket not found')
    s3_client._s3_client = mock_boto3_client

    result = await s3_client.health_check()

    assert result is False


def test_calculate_file_checksum(s3_client):
    """Testar cálculo de checksum SHA-256"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write('test content')
        temp_path = f.name

    try:
        checksum = s3_client._calculate_file_checksum(temp_path)

        # SHA-256 tem 64 caracteres hex
        assert len(checksum) == 64
        assert all(c in '0123456789abcdef' for c in checksum)
    finally:
        os.unlink(temp_path)


def test_client_initialization_without_endpoint():
    """Testar inicialização sem endpoint customizado"""
    with patch.dict('sys.modules', {'boto3': MagicMock(), 'botocore.config': MagicMock()}):
        client = S3ArtifactClient(
            bucket='my-bucket',
            region='eu-west-1',
            endpoint=None
        )

        assert client.bucket == 'my-bucket'
        assert client.region == 'eu-west-1'
        assert client.endpoint is None


def test_client_initialization_with_endpoint():
    """Testar inicialização com endpoint customizado (MinIO/LocalStack)"""
    with patch.dict('sys.modules', {'boto3': MagicMock(), 'botocore.config': MagicMock()}):
        client = S3ArtifactClient(
            bucket='test-bucket',
            region='us-east-1',
            endpoint='http://localhost:4566'
        )

        assert client.endpoint == 'http://localhost:4566'
