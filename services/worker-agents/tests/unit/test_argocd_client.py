"""
Testes unitarios para ArgoCDClient.

Cobertura:
- Criacao de aplicacao
- Obtencao de status
- Polling de health
- Sync manual
- Delecao de aplicacao
- Tratamento de erros
- Retry logic
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx


@pytest.fixture
def argocd_client():
    """Fixture para ArgoCDClient."""
    from services.worker_agents.src.clients.argocd_client import ArgoCDClient
    return ArgoCDClient(
        base_url='http://argocd.test:8080',
        token='test-token',
        timeout=30
    )


@pytest.fixture
def application_request():
    """Fixture para ApplicationCreateRequest."""
    from services.worker_agents.src.clients.argocd_client import (
        ApplicationCreateRequest,
        ApplicationMetadata,
        ApplicationSpec,
        ApplicationSource,
        ApplicationDestination,
        SyncPolicy
    )
    return ApplicationCreateRequest(
        metadata=ApplicationMetadata(
            name='test-app',
            namespace='argocd'
        ),
        spec=ApplicationSpec(
            project='default',
            source=ApplicationSource(
                repoURL='https://github.com/test/repo',
                path='charts/app',
                targetRevision='HEAD'
            ),
            destination=ApplicationDestination(
                server='https://kubernetes.default.svc',
                namespace='default'
            ),
            syncPolicy=SyncPolicy(
                automated={'prune': True, 'selfHeal': True}
            )
        )
    )


class TestArgoCDClientInit:
    """Testes de inicializacao do cliente."""

    def test_init_with_token(self):
        """Deve inicializar com token."""
        from services.worker_agents.src.clients.argocd_client import ArgoCDClient
        client = ArgoCDClient(
            base_url='http://argocd.test:8080',
            token='my-token',
            timeout=60
        )
        assert client.base_url == 'http://argocd.test:8080'
        assert client.token == 'my-token'
        assert client.timeout == 60

    def test_init_without_token(self):
        """Deve inicializar sem token."""
        from services.worker_agents.src.clients.argocd_client import ArgoCDClient
        client = ArgoCDClient(base_url='http://argocd.test:8080')
        assert client.token is None

    def test_base_url_trailing_slash_removed(self):
        """Deve remover trailing slash da URL."""
        from services.worker_agents.src.clients.argocd_client import ArgoCDClient
        client = ArgoCDClient(base_url='http://argocd.test:8080/')
        assert client.base_url == 'http://argocd.test:8080'

    def test_get_headers_with_token(self, argocd_client):
        """Deve incluir Authorization header quando token presente."""
        headers = argocd_client._get_headers()
        assert headers['Authorization'] == 'Bearer test-token'
        assert headers['Content-Type'] == 'application/json'

    def test_get_headers_without_token(self):
        """Deve nao incluir Authorization quando sem token."""
        from services.worker_agents.src.clients.argocd_client import ArgoCDClient
        client = ArgoCDClient(base_url='http://argocd.test:8080')
        headers = client._get_headers()
        assert 'Authorization' not in headers


class TestCreateApplication:
    """Testes de criacao de aplicacao."""

    @pytest.mark.asyncio
    async def test_create_application_success(self, argocd_client, application_request):
        """Deve criar aplicacao com sucesso."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {'metadata': {'name': 'test-app'}}

        with patch.object(argocd_client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            result = await argocd_client.create_application(application_request)

            assert result == 'test-app'
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert 'api/v1/applications' in call_args[0][0]

    @pytest.mark.asyncio
    async def test_create_application_http_error(self, argocd_client, application_request):
        """Deve tratar erro HTTP na criacao."""
        from services.worker_agents.src.clients.argocd_client import ArgoCDAPIError

        mock_response = MagicMock()
        mock_response.status_code = 409
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            'Conflict',
            request=MagicMock(),
            response=mock_response
        )

        with patch.object(argocd_client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            with pytest.raises(ArgoCDAPIError) as exc_info:
                await argocd_client.create_application(application_request)

            assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_create_application_timeout(self, argocd_client, application_request):
        """Deve tratar timeout na criacao."""
        from services.worker_agents.src.clients.argocd_client import ArgoCDTimeoutError

        with patch.object(argocd_client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.TimeoutException('Timeout')

            with pytest.raises(ArgoCDTimeoutError):
                await argocd_client.create_application(application_request)


class TestGetApplicationStatus:
    """Testes de obtencao de status."""

    @pytest.mark.asyncio
    async def test_get_status_success(self, argocd_client):
        """Deve obter status com sucesso."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            'metadata': {'name': 'test-app'},
            'status': {
                'health': {'status': 'Healthy', 'message': 'OK'},
                'sync': {'status': 'Synced', 'revision': 'abc123'},
                'operationState': {'phase': 'Succeeded'}
            }
        }

        with patch.object(argocd_client.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            status = await argocd_client.get_application_status('test-app')

            assert status.name == 'test-app'
            assert status.health.status == 'Healthy'
            assert status.sync.status == 'Synced'
            assert status.sync.revision == 'abc123'

    @pytest.mark.asyncio
    async def test_get_status_not_found(self, argocd_client):
        """Deve tratar aplicacao nao encontrada."""
        from services.worker_agents.src.clients.argocd_client import ArgoCDAPIError

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            'Not Found',
            request=MagicMock(),
            response=mock_response
        )

        with patch.object(argocd_client.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            with pytest.raises(ArgoCDAPIError) as exc_info:
                await argocd_client.get_application_status('nonexistent')

            assert exc_info.value.status_code == 404


class TestWaitForHealth:
    """Testes de polling de health."""

    @pytest.mark.asyncio
    async def test_wait_for_health_immediate_success(self, argocd_client):
        """Deve retornar imediatamente se ja healthy."""
        from services.worker_agents.src.clients.argocd_client import (
            ApplicationStatus,
            HealthStatus,
            SyncStatus
        )

        mock_status = ApplicationStatus(
            name='test-app',
            health=HealthStatus(status='Healthy'),
            sync=SyncStatus(status='Synced')
        )

        with patch.object(argocd_client, 'get_application_status', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_status

            result = await argocd_client.wait_for_health('test-app', timeout=10)

            assert result.health.status == 'Healthy'
            mock_get.assert_called_once()

    @pytest.mark.asyncio
    async def test_wait_for_health_polling(self, argocd_client):
        """Deve fazer polling ate ficar healthy."""
        from services.worker_agents.src.clients.argocd_client import (
            ApplicationStatus,
            HealthStatus,
            SyncStatus
        )

        statuses = [
            ApplicationStatus(
                name='test-app',
                health=HealthStatus(status='Progressing'),
                sync=SyncStatus(status='Synced')
            ),
            ApplicationStatus(
                name='test-app',
                health=HealthStatus(status='Progressing'),
                sync=SyncStatus(status='Synced')
            ),
            ApplicationStatus(
                name='test-app',
                health=HealthStatus(status='Healthy'),
                sync=SyncStatus(status='Synced')
            ),
        ]

        with patch.object(argocd_client, 'get_application_status', new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = statuses

            with patch('asyncio.sleep', new_callable=AsyncMock):
                result = await argocd_client.wait_for_health(
                    'test-app',
                    poll_interval=1,
                    timeout=30
                )

            assert result.health.status == 'Healthy'
            assert mock_get.call_count == 3

    @pytest.mark.asyncio
    async def test_wait_for_health_timeout(self, argocd_client):
        """Deve levantar timeout se nao ficar healthy."""
        from services.worker_agents.src.clients.argocd_client import (
            ApplicationStatus,
            HealthStatus,
            SyncStatus,
            ArgoCDTimeoutError
        )

        mock_status = ApplicationStatus(
            name='test-app',
            health=HealthStatus(status='Progressing'),
            sync=SyncStatus(status='Synced')
        )

        with patch.object(argocd_client, 'get_application_status', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_status

            with patch('asyncio.sleep', new_callable=AsyncMock):
                with patch('asyncio.get_event_loop') as mock_loop:
                    # Simular tempo passando
                    mock_loop.return_value.time.side_effect = [0, 0.1, 0.2, 100]

                    with pytest.raises(ArgoCDTimeoutError):
                        await argocd_client.wait_for_health(
                            'test-app',
                            poll_interval=1,
                            timeout=1
                        )


class TestSyncApplication:
    """Testes de sync manual."""

    @pytest.mark.asyncio
    async def test_sync_success(self, argocd_client):
        """Deve fazer sync com sucesso."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {'operationState': {'phase': 'Running'}}

        with patch.object(argocd_client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            result = await argocd_client.sync_application('test-app')

            assert 'operationState' in result
            call_args = mock_post.call_args
            assert 'test-app/sync' in call_args[0][0]

    @pytest.mark.asyncio
    async def test_sync_with_prune(self, argocd_client):
        """Deve fazer sync com prune."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {}

        with patch.object(argocd_client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            await argocd_client.sync_application('test-app', prune=True)

            call_args = mock_post.call_args
            assert call_args[1]['json']['prune'] is True

    @pytest.mark.asyncio
    async def test_sync_with_dry_run(self, argocd_client):
        """Deve fazer sync com dry-run."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {}

        with patch.object(argocd_client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            await argocd_client.sync_application('test-app', dry_run=True)

            call_args = mock_post.call_args
            assert call_args[1]['json']['dryRun'] is True


class TestDeleteApplication:
    """Testes de delecao de aplicacao."""

    @pytest.mark.asyncio
    async def test_delete_success(self, argocd_client):
        """Deve deletar aplicacao com sucesso."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with patch.object(argocd_client.client, 'delete', new_callable=AsyncMock) as mock_delete:
            mock_delete.return_value = mock_response

            result = await argocd_client.delete_application('test-app')

            assert result is True
            call_args = mock_delete.call_args
            assert 'cascade=true' in str(call_args)

    @pytest.mark.asyncio
    async def test_delete_not_found_returns_true(self, argocd_client):
        """Deve retornar True se aplicacao nao existe."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            'Not Found',
            request=MagicMock(),
            response=mock_response
        )

        with patch.object(argocd_client.client, 'delete', new_callable=AsyncMock) as mock_delete:
            mock_delete.return_value = mock_response

            result = await argocd_client.delete_application('nonexistent')

            assert result is True

    @pytest.mark.asyncio
    async def test_delete_without_cascade(self, argocd_client):
        """Deve deletar sem cascade."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with patch.object(argocd_client.client, 'delete', new_callable=AsyncMock) as mock_delete:
            mock_delete.return_value = mock_response

            await argocd_client.delete_application('test-app', cascade=False)

            call_args = mock_delete.call_args
            assert 'cascade=false' in str(call_args)


class TestListApplications:
    """Testes de listagem de aplicacoes."""

    @pytest.mark.asyncio
    async def test_list_success(self, argocd_client):
        """Deve listar aplicacoes com sucesso."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            'items': [
                {
                    'metadata': {'name': 'app1', 'namespace': 'argocd'},
                    'spec': {'project': 'default'},
                    'status': {'health': {'status': 'Healthy'}}
                },
                {
                    'metadata': {'name': 'app2', 'namespace': 'argocd'},
                    'spec': {'project': 'default'},
                    'status': {'health': {'status': 'Degraded'}}
                }
            ]
        }

        with patch.object(argocd_client.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            result = await argocd_client.list_applications()

            assert len(result) == 2
            assert result[0].metadata['name'] == 'app1'
            assert result[1].metadata['name'] == 'app2'

    @pytest.mark.asyncio
    async def test_list_with_project_filter(self, argocd_client):
        """Deve filtrar por projeto."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {'items': []}

        with patch.object(argocd_client.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            await argocd_client.list_applications(project='my-project')

            call_args = mock_get.call_args
            assert call_args[1]['params']['project'] == 'my-project'

    @pytest.mark.asyncio
    async def test_list_empty(self, argocd_client):
        """Deve retornar lista vazia."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {'items': []}

        with patch.object(argocd_client.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            result = await argocd_client.list_applications()

            assert result == []


class TestClientClose:
    """Testes de fechamento do cliente."""

    @pytest.mark.asyncio
    async def test_close_client(self, argocd_client):
        """Deve fechar cliente HTTP."""
        with patch.object(argocd_client.client, 'aclose', new_callable=AsyncMock) as mock_close:
            await argocd_client.close()

            mock_close.assert_called_once()
