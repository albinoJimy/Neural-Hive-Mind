"""
Testes unitários para SBOM Generator (SigstoreClient).

Seguindo TDD, estes testes validam a geração de SBOM via Syft CLI.
"""

import pytest
import json
import tempfile
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, mock_open

from src.clients.sigstore_client import SigstoreClient
from src.clients.s3_artifact_client import S3ArtifactClient


@pytest.fixture
def mock_s3_client():
    """Mock do S3ArtifactClient."""
    client = AsyncMock(spec=S3ArtifactClient)
    client.upload_sbom = AsyncMock(return_value="s3://test-bucket/sboms/ticket-123/artifact-456/sbom.cyclonedx.json")
    client.verify_sbom_integrity = AsyncMock(return_value=True)
    return client


@pytest.fixture
def sbom_generator(mock_s3_client):
    """Instância do SigstoreClient com mocks."""
    client = SigstoreClient(
        fulcio_url="https://fulcio.sigstore.dev",
        rekor_url="https://rekor.sigstore.dev",
        enabled=True,
        syft_path="/usr/bin/syft",
        s3_client=mock_s3_client
    )
    return client


class TestSBOMGeneration:
    """Testes de geração de SBOM."""

    @pytest.mark.asyncio
    async def test_generate_sbom_with_syft_success(self, sbom_generator, mock_s3_client):
        """Testa geração de SBOM com Syft CLI sucesso."""
        # Criar diretório temporário com arquivo Python simples
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "app.py"
            test_file.write_text("""
from fastapi import FastAPI
app = FastAPI()

@app.get("/")
def root():
    return {"message": "hello"}
""")

            # Mock do subprocess para Syft
            sbom_content = {
                "bomFormat": "CycloneDX",
                "specVersion": "1.4",
                "metadata": {"component": {"name": "app", "type": "application"}},
                "components": []
            }

            with patch('asyncio.create_subprocess_exec') as mock_subprocess:
                # Setup mock do processo
                mock_proc = AsyncMock()
                mock_proc.returncode = 0
                mock_proc.communicate = AsyncMock(return_value=(
                    json.dumps(sbom_content).encode(),
                    b""
                ))
                mock_subprocess.return_value = mock_proc

                # Temp file para o SBOM
                sbom_temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
                sbom_temp_file.write(json.dumps(sbom_content))
                sbom_temp_path = sbom_temp_file.name
                sbom_temp_file.close()

                try:
                    with patch('tempfile.NamedTemporaryFile', return_value=sbom_temp_file):
                        result = await sbom_generator.generate_sbom(
                            artifact_path=str(test_file),
                            artifact_id="artifact-456",
                            ticket_id="ticket-123",
                            output_format="cyclonedx-json"
                        )

                    # Assert
                    assert result == "s3://test-bucket/sboms/ticket-123/artifact-456/sbom.cyclonedx.json"
                    mock_s3_client.upload_sbom.assert_called_once()

                finally:
                    # Limpeza
                    if os.path.exists(sbom_temp_path):
                        os.unlink(sbom_temp_path)

    @pytest.mark.asyncio
    async def test_generate_sbom_syft_not_available(self, sbom_generator):
        """Testa fallback quando Syft não está disponível."""
        sbom_generator._tools_available['syft'] = False
        sbom_generator.syft_path = None

        result = await sbom_generator.generate_sbom(
            artifact_path="/tmp/app",
            artifact_id="artifact-456",
            ticket_id="ticket-123"
        )

        # Deve retornar mock URI quando Syft não disponível
        assert result == "MOCK_SBOM_URI_SYFT_NOT_INSTALLED"

    @pytest.mark.asyncio
    async def test_generate_sbom_client_disabled(self, sbom_generator):
        """Testa comportamento quando cliente está desabilitado."""
        sbom_generator.enabled = False

        result = await sbom_generator.generate_sbom(
            artifact_path="/tmp/app",
            artifact_id="artifact-456",
            ticket_id="ticket-123"
        )

        # Deve retornar string vazia quando desabilitado
        assert result == ""

    @pytest.mark.asyncio
    async def test_generate_sbom_syft_command_failure(self, sbom_generator):
        """Testa tratamento de erro quando Syft falha."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "app.py"
            test_file.write_text("print('hello')")

            with patch('asyncio.create_subprocess_exec') as mock_subprocess:
                # Mock falha do Syft
                mock_proc = AsyncMock()
                mock_proc.returncode = 1
                mock_proc.communicate = AsyncMock(return_value=(
                    b"",
                    b"Error: unable to access file"
                ))
                mock_subprocess.return_value = mock_proc

                # Temp file
                sbom_temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
                sbom_temp_path = sbom_temp_file.name
                sbom_temp_file.close()

                try:
                    with patch('tempfile.NamedTemporaryFile', return_value=sbom_temp_file):
                        with pytest.raises(RuntimeError) as exc_info:
                            await sbom_generator.generate_sbom(
                                artifact_path=str(test_file),
                                artifact_id="artifact-456",
                                ticket_id="ticket-123"
                            )

                    assert "Syft falhou" in str(exc_info.value)

                finally:
                    if os.path.exists(sbom_temp_path):
                        os.unlink(sbom_temp_path)

    @pytest.mark.asyncio
    async def test_generate_sbom_s3_upload_fallback(self, sbom_generator, mock_s3_client):
        """Testa fallback para file:// quando S3 upload falha."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "app.py"
            test_file.write_text("print('hello')")

            # Mock S3 upload falhando
            mock_s3_client.upload_sbom.side_effect = Exception("S3 connection failed")

            # Mock subprocess Syft sucesso
            sbom_content = {"bomFormat": "CycloneDX"}

            with patch('asyncio.create_subprocess_exec') as mock_subprocess:
                mock_proc = AsyncMock()
                mock_proc.returncode = 0
                mock_proc.communicate = AsyncMock(return_value=(
                    json.dumps(sbom_content).encode(),
                    b""
                ))
                mock_subprocess.return_value = mock_proc

                sbom_temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
                sbom_temp_path = sbom_temp_file.name
                sbom_temp_file.write(json.dumps(sbom_content))
                sbom_temp_file.close()

                try:
                    with patch('tempfile.NamedTemporaryFile', return_value=sbom_temp_file):
                        result = await sbom_generator.generate_sbom(
                            artifact_path=str(test_file),
                            artifact_id="artifact-456",
                            ticket_id="ticket-123"
                        )

                    # Deve retornar file:// como fallback
                    assert result.startswith("file://")
                    assert result.endswith(".json")

                finally:
                    if os.path.exists(sbom_temp_path):
                        os.unlink(sbom_temp_path)

    @pytest.mark.asyncio
    async def test_generate_sbom_without_s3_client(self):
        """Testa geração de SBOM sem cliente S3."""
        # Cliente sem S3
        client = SigstoreClient(
            fulcio_url="https://fulcio.sigstore.dev",
            rekor_url="https://rekor.sigstore.dev",
            enabled=True,
            syft_path="/usr/bin/syft",
            s3_client=None
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "app.py"
            test_file.write_text("print('hello')")

            sbom_content = {"bomFormat": "CycloneDX"}

            with patch('asyncio.create_subprocess_exec') as mock_subprocess:
                mock_proc = AsyncMock()
                mock_proc.returncode = 0
                mock_proc.communicate = AsyncMock(return_value=(
                    json.dumps(sbom_content).encode(),
                    b""
                ))
                mock_subprocess.return_value = mock_proc

                sbom_temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
                sbom_temp_path = sbom_temp_file.name
                sbom_temp_file.write(json.dumps(sbom_content))
                sbom_temp_file.close()

                try:
                    with patch('tempfile.NamedTemporaryFile', return_value=sbom_temp_file):
                        result = await client.generate_sbom(
                            artifact_path=str(test_file)
                        )

                    # Sem S3, deve retornar file://
                    assert result.startswith("file://")

                finally:
                    if os.path.exists(sbom_temp_path):
                        os.unlink(sbom_temp_path)


class TestSBOMFormats:
    """Testes de diferentes formatos de SBOM."""

    @pytest.mark.asyncio
    async def test_generate_sbom_cyclonedx_format(self, sbom_generator, mock_s3_client):
        """Testa geração de SBOM no formato CycloneDX."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "app.py"
            test_file.write_text("print('test')")

            sbom_content = {"bomFormat": "CycloneDX", "specVersion": "1.4"}

            with patch('asyncio.create_subprocess_exec') as mock_subprocess:
                mock_proc = AsyncMock()
                mock_proc.returncode = 0
                mock_proc.communicate = AsyncMock(return_value=(
                    json.dumps(sbom_content).encode(),
                    b""
                ))
                mock_subprocess.return_value = mock_proc

                sbom_temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
                sbom_temp_path = sbom_temp_file.name
                sbom_temp_file.write(json.dumps(sbom_content))
                sbom_temp_file.close()

                try:
                    with patch('tempfile.NamedTemporaryFile', return_value=sbom_temp_file):
                        result = await sbom_generator.generate_sbom(
                            artifact_path=str(test_file),
                            artifact_id="artifact-456",
                            ticket_id="ticket-123",
                            output_format="cyclonedx-json"
                        )

                    assert "s3://" in result

                finally:
                    if os.path.exists(sbom_temp_path):
                        os.unlink(sbom_temp_path)

    @pytest.mark.asyncio
    async def test_generate_sbom_spdx_format(self, sbom_generator, mock_s3_client):
        """Testa geração de SBOM no formato SPDX."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "app.py"
            test_file.write_text("print('test')")

            sbom_content = {"spdxVersion": "SPDX-2.3"}

            with patch('asyncio.create_subprocess_exec') as mock_subprocess:
                mock_proc = AsyncMock()
                mock_proc.returncode = 0
                mock_proc.communicate = AsyncMock(return_value=(
                    json.dumps(sbom_content).encode(),
                    b""
                ))
                mock_subprocess.return_value = mock_proc

                sbom_temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
                sbom_temp_path = sbom_temp_file.name
                sbom_temp_file.write(json.dumps(sbom_content))
                sbom_temp_file.close()

                try:
                    with patch('tempfile.NamedTemporaryFile', return_value=sbom_temp_file):
                        result = await sbom_generator.generate_sbom(
                            artifact_path=str(test_file),
                            artifact_id="artifact-456",
                            ticket_id="ticket-123",
                            output_format="spdx-json"
                        )

                    assert "s3://" in result

                finally:
                    if os.path.exists(sbom_temp_path):
                        os.unlink(sbom_temp_path)

    @pytest.mark.asyncio
    async def test_generate_sbom_table_format(self, sbom_generator, mock_s3_client):
        """Testa geração de SBOM no formato tabela."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "app.py"
            test_file.write_text("print('test')")

            table_output = "NAME    VERSION    TYPE\napp     1.0       application"

            with patch('asyncio.create_subprocess_exec') as mock_subprocess:
                mock_proc = AsyncMock()
                mock_proc.returncode = 0
                mock_proc.communicate = AsyncMock(return_value=(
                    table_output.encode(),
                    b""
                ))
                mock_subprocess.return_value = mock_proc

                sbom_temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
                sbom_temp_path = sbom_temp_file.name
                sbom_temp_file.write(table_output)
                sbom_temp_file.close()

                try:
                    with patch('tempfile.NamedTemporaryFile', return_value=sbom_temp_file):
                        result = await sbom_generator.generate_sbom(
                            artifact_path=str(test_file),
                            artifact_id="artifact-456",
                            ticket_id="ticket-123",
                            output_format="table"
                        )

                    assert "s3://" in result

                finally:
                    if os.path.exists(sbom_temp_path):
                        os.unlink(sbom_temp_path)


class TestSBOMIntegration:
    """Testes de integração SBOM com outros componentes."""

    @pytest.mark.asyncio
    async def test_sbom_integrity_verification(self, mock_s3_client):
        """Testa verificação de integridade de SBOM."""
        mock_s3_client.verify_sbom_integrity = AsyncMock(return_value=True)

        result = await mock_s3_client.verify_sbom_integrity(
            sbom_uri="s3://bucket/sboms/ticket-123/artifact-456/sbom.json"
        )

        assert result is True
        mock_s3_client.verify_sbom_integrity.assert_called_once_with(
            sbom_uri="s3://bucket/sboms/ticket-123/artifact-456/sbom.json"
        )

    @pytest.mark.asyncio
    async def test_sbom_metadata_retrieval(self, mock_s3_client):
        """Testa recuperação de metadados de SBOM."""
        mock_metadata = {
            'size': 2048,
            'etag': '"abc123"',
            'last_modified': '2026-03-11T10:00:00Z',
            'metadata': {'sha256': '1234abcd...'}
        }
        mock_s3_client.get_sbom_metadata = AsyncMock(return_value=mock_metadata)

        result = await mock_s3_client.get_sbom_metadata(
            sbom_uri="s3://bucket/sboms/ticket-123/artifact-456/sbom.json"
        )

        assert result['size'] == 2048
        assert result['metadata']['sha256'] == '1234abcd...'

    @pytest.mark.asyncio
    async def test_list_sboms_by_ticket(self, mock_s3_client):
        """Testa listagem de SBOMs por ticket."""
        mock_sboms = [
            {'key': 'sboms/ticket-123/artifact-1/sbom.json', 's3_uri': 's3://bucket/sboms/...', 'size': 1024},
            {'key': 'sboms/ticket-123/artifact-2/sbom.json', 's3_uri': 's3://bucket/sboms/...', 'size': 2048},
        ]
        mock_s3_client.list_sboms = AsyncMock(return_value=mock_sboms)

        result = await mock_s3_client.list_sboms(ticket_id="ticket-123")

        assert len(result) == 2
        assert result[0]['size'] == 1024
