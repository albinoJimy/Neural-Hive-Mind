"""
Testes unitários para ArtifactRegistryClient.

Valida registro e recuperação de artefatos no registry.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.clients.artifact_registry_client import ArtifactRegistryClient


@pytest.fixture
def registry_client():
    """Instância do ArtifactRegistryClient."""
    return ArtifactRegistryClient(
        registry_url='https://registry.example.com'
    )


@pytest.fixture
async def started_registry_client(registry_client):
    """Cliente com HTTP inicializado."""
    await registry_client.start()
    yield registry_client
    await registry_client.stop()


class TestArtifactRegistryClientInitialization:
    """Testes de inicialização."""

    def test_init_with_defaults(self):
        """Testa inicialização com URL."""
        client = ArtifactRegistryClient(
            registry_url='https://registry.example.com/'
        )

        assert client.registry_url == 'https://registry.example.com'
        assert client.timeout == 30
        assert client._client is None

    def test_init_with_custom_timeout(self):
        """Testa inicialização com timeout customizado."""
        client = ArtifactRegistryClient(
            registry_url='https://registry.example.com',
            timeout=60
        )

        assert client.timeout == 60


class TestArtifactRegistryLifecycle:
    """Testes de ciclo de vida do cliente."""

    @pytest.mark.asyncio
    async def test_start_creates_http_client(self, registry_client):
        """Testa que start cria cliente HTTP."""
        await registry_client.start()

        assert registry_client._client is not None

        await registry_client.stop()

    @pytest.mark.asyncio
    async def test_stop_closes_http_client(self, registry_client):
        """Testa que stop fecha cliente HTTP."""
        await registry_client.start()

        await registry_client.stop()

        assert registry_client._client is None


class TestRegisterArtifact:
    """Testes de registro de artefatos."""

    @pytest.mark.asyncio
    async def test_register_container_image_success(self, started_registry_client):
        """Testa registro bem-sucedido de imagem de container."""
        with patch.object(started_registry_client._client, 'post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = {
                'artifact_id': 'artifact-123',
                'reference': 'registry.example.com/artifacts/123'
            }
            mock_post.return_value = mock_response

            result = await started_registry_client.register_artifact(
                artifact_uri='ghcr.io/neural-hive/app:latest',
                artifact_type='CONTAINER_IMAGE',
                metadata={'digest': 'sha256:abc123', 'size': 1024000}
            )

            assert result is not None
            assert result['artifact_id'] == 'artifact-123'

    @pytest.mark.asyncio
    async def test_register_artifact_failure(self, started_registry_client):
        """Testa falha no registro de artefato."""
        with patch.object(started_registry_client._client, 'post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.text = 'Internal Server Error'
            mock_post.return_value = mock_response

            result = await started_registry_client.register_artifact(
                artifact_uri='ghcr.io/neural-hive/app:latest',
                artifact_type='CONTAINER_IMAGE',
                metadata={}
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_register_artifact_client_not_started(self, registry_client):
        """Testa registro quando cliente não foi iniciado."""
        result = await registry_client.register_artifact(
            artifact_uri='ghcr.io/neural-hive/app:latest',
            artifact_type='CONTAINER_IMAGE',
            metadata={}
        )

        assert result is None


class TestGetArtifactMetadata:
    """Testes de obtenção de metadados de artefato."""

    @pytest.mark.asyncio
    async def test_get_artifact_metadata_success(self, started_registry_client):
        """Testa obtenção bem-sucedida de metadados."""
        with patch.object(started_registry_client._client, 'get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'artifact_id': 'artifact-123',
                'artifact_uri': 'ghcr.io/neural-hive/app:latest',
                'artifact_type': 'CONTAINER_IMAGE',
                'metadata': {'digest': 'sha256:abc123'}
            }
            mock_get.return_value = mock_response

            result = await started_registry_client.get_artifact_metadata('artifact-123')

            assert result is not None
            assert result['artifact_id'] == 'artifact-123'
            assert result['metadata']['digest'] == 'sha256:abc123'

    @pytest.mark.asyncio
    async def test_get_artifact_metadata_not_found(self, started_registry_client):
        """Testa artefato não encontrado."""
        with patch.object(started_registry_client._client, 'get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_get.return_value = mock_response

            result = await started_registry_client.get_artifact_metadata('artifact-999')

            assert result is None

    @pytest.mark.asyncio
    async def test_get_artifact_metadata_error(self, started_registry_client):
        """Testa erro na obtenção de metadados."""
        with patch.object(started_registry_client._client, 'get') as mock_get:
            mock_get.side_effect = Exception('Network error')

            result = await started_registry_client.get_artifact_metadata('artifact-123')

            assert result is None


class TestRegisterSBOM:
    """Testes de registro de SBOM."""

    @pytest.mark.asyncio
    async def test_register_sbom_success(self, started_registry_client):
        """Testa registro bem-sucedido de SBOM."""
        with patch.object(started_registry_client._client, 'post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'reference': 'registry.example.com/sboms/sbom-456'
            }
            mock_post.return_value = mock_response

            result = await started_registry_client.register_sbom(
                sbom_uri='s3://bucket/sboms/ticket-123/artifact-456/sbom.json',
                artifact_id='artifact-456',
                metadata={'ticket_id': 'ticket-123'}
            )

            assert result == 'registry.example.com/sboms/sbom-456'

    @pytest.mark.asyncio
    async def test_register_sbom_failure(self, started_registry_client):
        """Testa falha no registro de SBOM."""
        with patch.object(started_registry_client._client, 'post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 400
            mock_response.text = 'Invalid SBOM URI'
            mock_post.return_value = mock_response

            result = await started_registry_client.register_sbom(
                sbom_uri='invalid-uri',
                artifact_id='artifact-456',
                metadata={}
            )

            assert result is None


class TestGetSBOMReference:
    """Testes de obtenção de referência de SBOM."""

    @pytest.mark.asyncio
    async def test_get_sbom_reference_success(self, started_registry_client):
        """Testa obtenção bem-sucedida de referência de SBOM."""
        with patch.object(started_registry_client._client, 'get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'sbom_uri': 's3://bucket/sboms/ticket-123/artifact-456/sbom.json',
                'artifact_id': 'artifact-456'
            }
            mock_get.return_value = mock_response

            result = await started_registry_client.get_sbom_reference('artifact-456')

            assert result == 's3://bucket/sboms/ticket-123/artifact-456/sbom.json'

    @pytest.mark.asyncio
    async def test_get_sbom_reference_not_found(self, started_registry_client):
        """Testa SBOM não encontrado."""
        with patch.object(started_registry_client._client, 'get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_get.return_value = mock_response

            result = await started_registry_client.get_sbom_reference('artifact-999')

            assert result is None


class TestListArtifacts:
    """Testes de listagem de artefatos."""

    @pytest.mark.asyncio
    async def test_list_artifacts_success(self, started_registry_client):
        """Testa listagem bem-sucedida de artefatos."""
        with patch.object(started_registry_client._client, 'get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'artifacts': [
                    {'artifact_id': 'artifact-1', 'artifact_uri': 'ghcr.io/app1:latest'},
                    {'artifact_id': 'artifact-2', 'artifact_uri': 'ghcr.io/app2:latest'},
                ]
            }
            mock_get.return_value = mock_response

            result = await started_registry_client.list_artifacts()

            assert len(result) == 2
            assert result[0]['artifact_id'] == 'artifact-1'

    @pytest.mark.asyncio
    async def test_list_artifacts_filtered_by_type(self, started_registry_client):
        """Testa listagem filtrada por tipo."""
        with patch.object(started_registry_client._client, 'get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'artifacts': [
                    {'artifact_id': 'artifact-1', 'artifact_type': 'CONTAINER_IMAGE'},
                ]
            }
            mock_get.return_value = mock_response

            result = await started_registry_client.list_artifacts(
                artifact_type='CONTAINER_IMAGE'
            )

            assert len(result) == 1
            assert result[0]['artifact_type'] == 'CONTAINER_IMAGE'

    @pytest.mark.asyncio
    async def test_list_artifacts_error(self, started_registry_client):
        """Testa erro na listagem."""
        with patch.object(started_registry_client._client, 'get') as mock_get:
            mock_get.side_effect = Exception('Network error')

            result = await started_registry_client.list_artifacts()

            assert result == []

    @pytest.mark.asyncio
    async def test_list_artifacts_with_limit(self, started_registry_client):
        """Testa listagem com limite."""
        with patch.object(started_registry_client._client, 'get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {'artifacts': []}
            mock_get.return_value = mock_response

            await started_registry_client.list_artifacts(limit=50)

            mock_get.assert_called_once()
            assert mock_get.call_args[1]['params']['limit'] == 50


class TestHealthCheck:
    """Testes de verificação de saúde."""

    @pytest.mark.asyncio
    async def test_health_check_success(self, started_registry_client):
        """Testa health_check bem-sucedido."""
        with patch.object(started_registry_client._client, 'get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            result = await started_registry_client.health_check()

            assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, started_registry_client):
        """Testa health_check com falha."""
        with patch.object(started_registry_client._client, 'get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 503
            mock_get.return_value = mock_response

            result = await started_registry_client.health_check()

            assert result is False

    @pytest.mark.asyncio
    async def test_health_check_exception(self, started_registry_client):
        """Testa health_check com exceção."""
        with patch.object(started_registry_client._client, 'get') as mock_get:
            mock_get.side_effect = Exception('Connection error')

            result = await started_registry_client.health_check()

            assert result is False

    @pytest.mark.asyncio
    async def test_health_check_client_not_started(self, registry_client):
        """Testa health_check quando cliente não iniciado."""
        result = await registry_client.health_check()

        assert result is False
