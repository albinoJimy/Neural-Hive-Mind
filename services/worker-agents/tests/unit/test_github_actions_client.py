"""
Testes unitarios para GitHubActionsClient.

Cobertura:
- Trigger de workflow
- Polling de status
- Obtencao de test results
- Download de artifacts
- Timeout handling
- Retry logic
- Error handling
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestGitHubActionsClientTrigger:
    """Testes de trigger de workflow."""

    @pytest.mark.asyncio
    async def test_trigger_workflow_success(self):
        """Deve disparar workflow com sucesso."""
        from src.clients.github_actions_client import GitHubActionsClient

        client = GitHubActionsClient(token='test-token')

        with patch.object(client, 'client') as mock_http:
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.status_code = 204
            mock_http.post = AsyncMock(return_value=mock_response)

            # Mock _get_latest_run_id
            with patch.object(client, '_get_latest_run_id', return_value='12345'):
                run_id = await client.trigger_workflow(
                    repo='test-org/test-repo',
                    workflow_id='ci.yml',
                    ref='main',
                    inputs={'env': 'test'}
                )

                assert run_id == '12345'
                mock_http.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_trigger_workflow_invalid_repo(self):
        """Deve retornar erro para repo invalido."""
        from src.clients.github_actions_client import GitHubActionsClient

        client = GitHubActionsClient(token='test-token')

        with pytest.raises(ValueError, match='Invalid repo format'):
            await client.trigger_workflow(
                repo='invalid-repo',
                workflow_id='ci.yml'
            )

    @pytest.mark.asyncio
    async def test_trigger_workflow_api_error(self):
        """Deve propagar erro da API."""
        from src.clients.github_actions_client import GitHubActionsClient, GitHubActionsAPIError
        import httpx

        client = GitHubActionsClient(token='test-token')

        with patch.object(client, 'client') as mock_http:
            mock_response = MagicMock()
            mock_response.status_code = 403
            mock_response.text = 'Forbidden'
            mock_response.raise_for_status = MagicMock(
                side_effect=httpx.HTTPStatusError(
                    'Forbidden', request=MagicMock(), response=mock_response
                )
            )
            mock_http.post = AsyncMock(return_value=mock_response)

            with pytest.raises(GitHubActionsAPIError) as exc_info:
                await client.trigger_workflow(
                    repo='test-org/test-repo',
                    workflow_id='ci.yml'
                )

            assert exc_info.value.status_code == 403


class TestGitHubActionsClientStatus:
    """Testes de obtencao de status."""

    @pytest.mark.asyncio
    async def test_get_workflow_run_success(self):
        """Deve obter status do workflow."""
        from src.clients.github_actions_client import GitHubActionsClient

        client = GitHubActionsClient(token='test-token')

        with patch.object(client, 'client') as mock_http:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()
            mock_response.json = MagicMock(return_value={
                'id': 12345,
                'status': 'completed',
                'conclusion': 'success',
                'html_url': 'https://github.com/test/runs/12345',
                'workflow_id': 100,
                'head_branch': 'main',
                'head_sha': 'abc123'
            })
            mock_http.get = AsyncMock(return_value=mock_response)

            status = await client.get_workflow_run('test-org/test-repo', '12345')

            assert status.run_id == '12345'
            assert status.status == 'completed'
            assert status.conclusion == 'success'
            assert status.success is True

    @pytest.mark.asyncio
    async def test_get_workflow_run_not_found(self):
        """Deve retornar status queued quando run nao encontrado."""
        from src.clients.github_actions_client import GitHubActionsClient

        client = GitHubActionsClient(token='test-token')

        with patch.object(client, 'client') as mock_http:
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_http.get = AsyncMock(return_value=mock_response)

            status = await client.get_workflow_run('test-org/test-repo', '12345')

            assert status.status == 'queued'
            assert status.conclusion is None


class TestGitHubActionsClientWait:
    """Testes de wait for run."""

    @pytest.mark.asyncio
    async def test_wait_for_run_completes(self):
        """Deve aguardar run completar."""
        from src.clients.github_actions_client import (
            GitHubActionsClient, WorkflowRunStatus
        )

        client = GitHubActionsClient(token='test-token', default_repo='test/repo')

        # Mock get_workflow_run para retornar completed
        with patch.object(client, 'get_workflow_run') as mock_get:
            mock_get.return_value = WorkflowRunStatus(
                run_id='12345',
                status='completed',
                conclusion='success'
            )

            # Mock list_artifacts e get_test_results
            with patch.object(client, 'list_artifacts', return_value=[]):
                with patch.object(client, 'get_test_results', return_value={'passed': 10}):
                    status = await client.wait_for_run(
                        run_id='12345',
                        poll_interval=0.1,
                        timeout=5
                    )

                    assert status.completed is True
                    assert status.success is True

    @pytest.mark.asyncio
    async def test_wait_for_run_timeout(self):
        """Deve levantar timeout quando excede limite."""
        from src.clients.github_actions_client import (
            GitHubActionsClient, WorkflowRunStatus, GitHubActionsTimeoutError
        )

        client = GitHubActionsClient(token='test-token', default_repo='test/repo')

        # Mock get_workflow_run para sempre retornar in_progress
        with patch.object(client, 'get_workflow_run') as mock_get:
            mock_get.return_value = WorkflowRunStatus(
                run_id='12345',
                status='in_progress',
                conclusion=None
            )

            with pytest.raises(GitHubActionsTimeoutError):
                await client.wait_for_run(
                    run_id='12345',
                    poll_interval=0.1,
                    timeout=0.3
                )


class TestGitHubActionsClientArtifacts:
    """Testes de artifacts."""

    @pytest.mark.asyncio
    async def test_list_artifacts_success(self):
        """Deve listar artifacts do run."""
        from src.clients.github_actions_client import GitHubActionsClient

        client = GitHubActionsClient(token='test-token')

        with patch.object(client, 'client') as mock_http:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()
            mock_response.json = MagicMock(return_value={
                'artifacts': [
                    {'id': 1, 'name': 'test-results', 'size_in_bytes': 1000},
                    {'id': 2, 'name': 'coverage', 'size_in_bytes': 2000}
                ]
            })
            mock_http.get = AsyncMock(return_value=mock_response)

            artifacts = await client.list_artifacts('test/repo', '12345')

            assert len(artifacts) == 2
            assert artifacts[0]['name'] == 'test-results'

    @pytest.mark.asyncio
    async def test_download_artifact_success(self):
        """Deve baixar artifact."""
        from src.clients.github_actions_client import GitHubActionsClient

        client = GitHubActionsClient(token='test-token')

        with patch.object(client, 'client') as mock_http:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()
            mock_response.content = b'PK\x03\x04...'  # ZIP header
            mock_http.get = AsyncMock(return_value=mock_response)

            content = await client.download_artifact('test/repo', 12345)

            assert content.startswith(b'PK')


class TestGitHubActionsClientTestResults:
    """Testes de obtencao de test results."""

    @pytest.mark.asyncio
    async def test_get_test_results_success(self):
        """Deve obter test results de artifacts."""
        from src.clients.github_actions_client import GitHubActionsClient

        client = GitHubActionsClient(token='test-token')

        # Mock list_artifacts
        with patch.object(client, 'list_artifacts') as mock_list:
            mock_list.return_value = [
                {'id': 1, 'name': 'test-results'}
            ]

            # Mock download_artifact com ZIP vazio (nao vai parsear)
            with patch.object(client, 'download_artifact') as mock_download:
                mock_download.return_value = b''

                with patch.object(client, '_parse_artifact_tests') as mock_parse:
                    mock_parse.return_value = {
                        'passed': 50,
                        'failed': 2,
                        'skipped': 5,
                        'errors': 0,
                        'total': 57
                    }

                    results = await client.get_test_results('test/repo', '12345')

                    assert results['passed'] == 50
                    assert results['failed'] == 2


class TestGitHubActionsClientOperations:
    """Testes de operacoes diversas."""

    @pytest.mark.asyncio
    async def test_cancel_workflow_run(self):
        """Deve cancelar workflow run."""
        from src.clients.github_actions_client import GitHubActionsClient

        client = GitHubActionsClient(token='test-token')

        with patch.object(client, 'client') as mock_http:
            mock_response = MagicMock()
            mock_response.status_code = 202
            mock_response.raise_for_status = MagicMock()
            mock_http.post = AsyncMock(return_value=mock_response)

            result = await client.cancel_workflow_run('test/repo', '12345')

            assert result is True

    @pytest.mark.asyncio
    async def test_rerun_workflow(self):
        """Deve re-executar workflow."""
        from src.clients.github_actions_client import (
            GitHubActionsClient, WorkflowRunStatus
        )

        client = GitHubActionsClient(token='test-token')

        with patch.object(client, 'client') as mock_http:
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.raise_for_status = MagicMock()
            mock_http.post = AsyncMock(return_value=mock_response)

            with patch.object(client, 'get_workflow_run') as mock_get:
                mock_get.return_value = WorkflowRunStatus(
                    run_id='67890',
                    status='queued',
                    conclusion=None
                )

                new_run_id = await client.rerun_workflow('test/repo', '12345')

                assert new_run_id == '67890'


class TestGitHubActionsClientFromEnv:
    """Testes de criacao via environment."""

    def test_from_env_success(self):
        """Deve criar cliente via environment."""
        from src.clients.github_actions_client import GitHubActionsClient

        with patch.dict('os.environ', {'GITHUB_TOKEN': 'test-token'}):
            client = GitHubActionsClient.from_env()

            assert client.token == 'test-token'

    def test_from_env_missing_token(self):
        """Deve levantar erro quando token ausente."""
        from src.clients.github_actions_client import GitHubActionsClient

        with patch.dict('os.environ', {}, clear=True):
            with pytest.raises(ValueError, match='not configured'):
                GitHubActionsClient.from_env()
