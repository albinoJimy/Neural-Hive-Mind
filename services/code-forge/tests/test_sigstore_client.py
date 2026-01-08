"""Testes unitários para SigstoreClient"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.clients.sigstore_client import SigstoreClient


@pytest.fixture
def mock_subprocess_success():
    """Mock de subprocess com sucesso"""
    async def mock_create_subprocess(*args, **kwargs):
        proc = AsyncMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(b'MEUCIQDxyz123signature', b''))
        return proc
    return mock_create_subprocess


@pytest.fixture
def mock_subprocess_failure():
    """Mock de subprocess com falha"""
    async def mock_create_subprocess(*args, **kwargs):
        proc = AsyncMock()
        proc.returncode = 1
        proc.communicate = AsyncMock(return_value=(b'', b'Error: signing failed'))
        return proc
    return mock_create_subprocess


@pytest.mark.asyncio
async def test_start_with_tools_available():
    """Testar inicialização com ferramentas disponíveis"""
    with patch('shutil.which') as mock_which:
        mock_which.side_effect = lambda x: f'/usr/bin/{x}'

        client = SigstoreClient(
            fulcio_url='https://fulcio.sigstore.dev',
            rekor_url='https://rekor.sigstore.dev',
            enabled=True
        )
        await client.start()

        assert client._tools_available['cosign'] is True
        assert client._tools_available['syft'] is True
        assert client._tools_available['rekor-cli'] is True


@pytest.mark.asyncio
async def test_start_without_tools():
    """Testar inicialização sem ferramentas instaladas"""
    with patch('shutil.which', return_value=None):
        client = SigstoreClient(
            fulcio_url='https://fulcio.sigstore.dev',
            rekor_url='https://rekor.sigstore.dev',
            enabled=True
        )
        await client.start()

        assert client._tools_available['cosign'] is False
        assert client._tools_available['syft'] is False
        assert client._tools_available['rekor-cli'] is False


@pytest.mark.asyncio
async def test_sign_artifact_disabled():
    """Testar assinatura com cliente desabilitado"""
    client = SigstoreClient(
        fulcio_url='https://fulcio.sigstore.dev',
        rekor_url='https://rekor.sigstore.dev',
        enabled=False
    )

    signature = await client.sign_artifact('/tmp/artifact.tar')

    assert signature == ''


@pytest.mark.asyncio
async def test_sign_artifact_no_cosign():
    """Testar assinatura sem cosign instalado"""
    with patch('shutil.which', return_value=None):
        client = SigstoreClient(
            fulcio_url='https://fulcio.sigstore.dev',
            rekor_url='https://rekor.sigstore.dev',
            enabled=True
        )
        await client.start()

        signature = await client.sign_artifact('/tmp/artifact.tar')

        assert signature == 'MOCK_SIGNATURE_COSIGN_NOT_INSTALLED'


@pytest.mark.asyncio
async def test_sign_artifact_success(mock_subprocess_success):
    """Testar assinatura bem-sucedida"""
    with patch('shutil.which') as mock_which, \
         patch('asyncio.create_subprocess_exec', mock_subprocess_success):
        mock_which.side_effect = lambda x: f'/usr/bin/{x}'

        client = SigstoreClient(
            fulcio_url='https://fulcio.sigstore.dev',
            rekor_url='https://rekor.sigstore.dev',
            enabled=True
        )
        await client.start()

        signature = await client.sign_artifact('/tmp/artifact.tar')

        assert 'MEUCIQDxyz123signature' in signature


@pytest.mark.asyncio
async def test_sign_artifact_failure(mock_subprocess_failure):
    """Testar falha na assinatura"""
    with patch('shutil.which') as mock_which, \
         patch('asyncio.create_subprocess_exec', mock_subprocess_failure):
        mock_which.side_effect = lambda x: f'/usr/bin/{x}'

        client = SigstoreClient(
            fulcio_url='https://fulcio.sigstore.dev',
            rekor_url='https://rekor.sigstore.dev',
            enabled=True
        )
        await client.start()

        with pytest.raises(RuntimeError, match='Cosign falhou'):
            await client.sign_artifact('/tmp/artifact.tar')


@pytest.mark.asyncio
async def test_verify_signature_disabled():
    """Testar verificação com cliente desabilitado"""
    client = SigstoreClient(
        fulcio_url='https://fulcio.sigstore.dev',
        rekor_url='https://rekor.sigstore.dev',
        enabled=False
    )

    valid = await client.verify_signature('/tmp/artifact.tar', 'signature')

    assert valid is True


@pytest.mark.asyncio
async def test_verify_signature_mock():
    """Testar verificação com assinatura mock"""
    with patch('shutil.which', return_value=None):
        client = SigstoreClient(
            fulcio_url='https://fulcio.sigstore.dev',
            rekor_url='https://rekor.sigstore.dev',
            enabled=True
        )
        await client.start()

        valid = await client.verify_signature(
            '/tmp/artifact.tar',
            'MOCK_SIGNATURE_COSIGN_NOT_INSTALLED'
        )

        assert valid is True


@pytest.mark.asyncio
async def test_generate_sbom_disabled():
    """Testar geração de SBOM com cliente desabilitado"""
    client = SigstoreClient(
        fulcio_url='https://fulcio.sigstore.dev',
        rekor_url='https://rekor.sigstore.dev',
        enabled=False
    )

    sbom_uri = await client.generate_sbom('/tmp/artifact.tar')

    assert sbom_uri == ''


@pytest.mark.asyncio
async def test_generate_sbom_no_syft():
    """Testar geração de SBOM sem syft instalado"""
    with patch('shutil.which', return_value=None):
        client = SigstoreClient(
            fulcio_url='https://fulcio.sigstore.dev',
            rekor_url='https://rekor.sigstore.dev',
            enabled=True
        )
        await client.start()

        sbom_uri = await client.generate_sbom('/tmp/artifact.tar')

        assert sbom_uri == 'MOCK_SBOM_URI_SYFT_NOT_INSTALLED'


@pytest.mark.asyncio
async def test_generate_sbom_success():
    """Testar geração de SBOM bem-sucedida"""
    async def mock_subprocess(*args, **kwargs):
        proc = AsyncMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(b'{"sbom": "data"}', b''))
        return proc

    with patch('shutil.which') as mock_which, \
         patch('asyncio.create_subprocess_exec', mock_subprocess):
        mock_which.side_effect = lambda x: f'/usr/bin/{x}'

        client = SigstoreClient(
            fulcio_url='https://fulcio.sigstore.dev',
            rekor_url='https://rekor.sigstore.dev',
            enabled=True
        )
        await client.start()

        sbom_uri = await client.generate_sbom('/tmp/artifact.tar')

        assert 'file://' in sbom_uri


@pytest.mark.asyncio
async def test_upload_to_rekor_disabled():
    """Testar upload para Rekor com cliente desabilitado"""
    client = SigstoreClient(
        fulcio_url='https://fulcio.sigstore.dev',
        rekor_url='https://rekor.sigstore.dev',
        enabled=False
    )

    uuid = await client.upload_to_rekor('hash123', 'signature')

    assert uuid is None


@pytest.mark.asyncio
async def test_upload_to_rekor_no_cli():
    """Testar upload para Rekor sem CLI"""
    with patch('shutil.which', return_value=None):
        client = SigstoreClient(
            fulcio_url='https://fulcio.sigstore.dev',
            rekor_url='https://rekor.sigstore.dev',
            enabled=True
        )
        await client.start()

        uuid = await client.upload_to_rekor('hash123', 'real_signature')

        assert uuid is None


@pytest.mark.asyncio
async def test_upload_to_rekor_mock_signature():
    """Testar upload para Rekor com assinatura mock"""
    with patch('shutil.which', return_value=None):
        client = SigstoreClient(
            fulcio_url='https://fulcio.sigstore.dev',
            rekor_url='https://rekor.sigstore.dev',
            enabled=True
        )
        await client.start()

        uuid = await client.upload_to_rekor('hash123', 'MOCK_SIGNATURE_COSIGN_NOT_INSTALLED')

        assert uuid == 'MOCK_REKOR_UUID'


@pytest.mark.asyncio
async def test_health_check_disabled():
    """Testar health check com cliente desabilitado"""
    client = SigstoreClient(
        fulcio_url='https://fulcio.sigstore.dev',
        rekor_url='https://rekor.sigstore.dev',
        enabled=False
    )

    healthy = await client.health_check()

    assert healthy is True


@pytest.mark.asyncio
async def test_health_check_with_cosign():
    """Testar health check com cosign disponível"""
    async def mock_subprocess(*args, **kwargs):
        proc = AsyncMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(b'cosign v2.0.0', b''))
        return proc

    with patch('shutil.which') as mock_which, \
         patch('asyncio.create_subprocess_exec', mock_subprocess):
        mock_which.side_effect = lambda x: f'/usr/bin/{x}'

        client = SigstoreClient(
            fulcio_url='https://fulcio.sigstore.dev',
            rekor_url='https://rekor.sigstore.dev',
            enabled=True
        )
        await client.start()

        healthy = await client.health_check()

        assert healthy is True


def test_is_available_enabled_with_tools():
    """Testar is_available com cliente habilitado e ferramentas"""
    with patch('shutil.which') as mock_which:
        mock_which.side_effect = lambda x: f'/usr/bin/{x}'

        client = SigstoreClient(
            fulcio_url='https://fulcio.sigstore.dev',
            rekor_url='https://rekor.sigstore.dev',
            enabled=True
        )

        assert client.is_available() is True


def test_is_available_disabled():
    """Testar is_available com cliente desabilitado"""
    client = SigstoreClient(
        fulcio_url='https://fulcio.sigstore.dev',
        rekor_url='https://rekor.sigstore.dev',
        enabled=False
    )

    assert client.is_available() is False


def test_is_available_enabled_without_tools():
    """Testar is_available sem ferramentas instaladas"""
    with patch('shutil.which', return_value=None):
        client = SigstoreClient(
            fulcio_url='https://fulcio.sigstore.dev',
            rekor_url='https://rekor.sigstore.dev',
            enabled=True
        )

        assert client.is_available() is False


# Testes de integração com S3

@pytest.mark.asyncio
async def test_generate_sbom_with_s3_upload():
    """Testar geração de SBOM com upload para S3"""
    mock_s3_client = AsyncMock()
    mock_s3_client.upload_sbom = AsyncMock(
        return_value='s3://test-bucket/sboms/ticket-123/artifact-456/sbom.cyclonedx.json'
    )

    async def mock_subprocess(*args, **kwargs):
        proc = AsyncMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(b'{"sbom": "data"}', b''))
        return proc

    with patch('shutil.which') as mock_which, \
         patch('asyncio.create_subprocess_exec', mock_subprocess), \
         patch('os.unlink'):  # Mock unlink para não deletar arquivo inexistente
        mock_which.side_effect = lambda x: f'/usr/bin/{x}'

        client = SigstoreClient(
            fulcio_url='https://fulcio.sigstore.dev',
            rekor_url='https://rekor.sigstore.dev',
            enabled=True,
            s3_client=mock_s3_client
        )
        await client.start()

        sbom_uri = await client.generate_sbom(
            artifact_path='/tmp/artifact.tar',
            artifact_id='artifact-456',
            ticket_id='ticket-123'
        )

        assert sbom_uri.startswith('s3://')
        mock_s3_client.upload_sbom.assert_called_once()


@pytest.mark.asyncio
async def test_generate_sbom_s3_upload_failure_fallback():
    """Testar fallback para file:// quando upload S3 falha"""
    mock_s3_client = AsyncMock()
    mock_s3_client.upload_sbom = AsyncMock(side_effect=Exception('S3 upload failed'))

    async def mock_subprocess(*args, **kwargs):
        proc = AsyncMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(b'{"sbom": "data"}', b''))
        return proc

    with patch('shutil.which') as mock_which, \
         patch('asyncio.create_subprocess_exec', mock_subprocess):
        mock_which.side_effect = lambda x: f'/usr/bin/{x}'

        client = SigstoreClient(
            fulcio_url='https://fulcio.sigstore.dev',
            rekor_url='https://rekor.sigstore.dev',
            enabled=True,
            s3_client=mock_s3_client
        )
        await client.start()

        sbom_uri = await client.generate_sbom(
            artifact_path='/tmp/artifact.tar',
            artifact_id='artifact-456',
            ticket_id='ticket-123'
        )

        assert sbom_uri.startswith('file://')


@pytest.mark.asyncio
async def test_generate_sbom_without_s3_client():
    """Testar geração de SBOM sem cliente S3"""
    async def mock_subprocess(*args, **kwargs):
        proc = AsyncMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(b'{"sbom": "data"}', b''))
        return proc

    with patch('shutil.which') as mock_which, \
         patch('asyncio.create_subprocess_exec', mock_subprocess):
        mock_which.side_effect = lambda x: f'/usr/bin/{x}'

        client = SigstoreClient(
            fulcio_url='https://fulcio.sigstore.dev',
            rekor_url='https://rekor.sigstore.dev',
            enabled=True,
            s3_client=None
        )
        await client.start()

        sbom_uri = await client.generate_sbom(
            artifact_path='/tmp/artifact.tar',
            artifact_id='artifact-456',
            ticket_id='ticket-123'
        )

        assert sbom_uri.startswith('file://')


@pytest.mark.asyncio
async def test_generate_sbom_without_ids():
    """Testar geração de SBOM sem IDs (não faz upload S3)"""
    mock_s3_client = AsyncMock()

    async def mock_subprocess(*args, **kwargs):
        proc = AsyncMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(b'{"sbom": "data"}', b''))
        return proc

    with patch('shutil.which') as mock_which, \
         patch('asyncio.create_subprocess_exec', mock_subprocess):
        mock_which.side_effect = lambda x: f'/usr/bin/{x}'

        client = SigstoreClient(
            fulcio_url='https://fulcio.sigstore.dev',
            rekor_url='https://rekor.sigstore.dev',
            enabled=True,
            s3_client=mock_s3_client
        )
        await client.start()

        # Sem artifact_id e ticket_id
        sbom_uri = await client.generate_sbom(artifact_path='/tmp/artifact.tar')

        assert sbom_uri.startswith('file://')
        mock_s3_client.upload_sbom.assert_not_called()
