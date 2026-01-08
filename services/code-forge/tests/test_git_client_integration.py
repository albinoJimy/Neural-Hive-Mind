"""Testes de integração para GitClient"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.clients.git_client import GitClient


@pytest.fixture
def client():
    return GitClient(
        templates_repo='https://github.com/example/templates.git',
        templates_branch='main',
        local_path='/tmp/templates',
        gitlab_url='https://gitlab.com',
        gitlab_token='gl-test-token',
        github_token='gh-test-token',
        timeout=30
    )


class TestExtractProjectInfo:
    """Testes para _extract_project_info"""

    def test_extract_gitlab_url(self, client):
        provider, owner, repo = client._extract_project_info('https://gitlab.com/myorg/myrepo.git')

        assert provider == 'gitlab'
        assert owner == 'myorg'
        assert repo == 'myrepo'

    def test_extract_github_url(self, client):
        provider, owner, repo = client._extract_project_info('https://github.com/myuser/myrepo')

        assert provider == 'github'
        assert owner == 'myuser'
        assert repo == 'myrepo'

    def test_extract_nested_gitlab_path(self, client):
        provider, owner, repo = client._extract_project_info('https://gitlab.com/org/subgroup/project.git')

        assert provider == 'gitlab'
        assert owner == 'org/subgroup'
        assert repo == 'project'


class TestGitLabOperations:
    """Testes para operações GitLab"""

    @pytest.mark.asyncio
    async def test_create_branch_gitlab_success(self, client):
        mock_http_client = AsyncMock()

        response = MagicMock()
        response.status_code = 201
        response.raise_for_status = MagicMock()

        mock_http_client.post = AsyncMock(return_value=response)

        with patch.object(client, '_ensure_gitlab_client', return_value=mock_http_client):
            result = await client.create_branch(
                'https://gitlab.com/myorg/myrepo.git',
                'feature-branch'
            )

        assert result == 'feature-branch'
        mock_http_client.post.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_branch_gitlab_already_exists(self, client):
        mock_http_client = AsyncMock()

        response = MagicMock()
        response.status_code = 400
        response.text = 'Branch already exists'
        response.raise_for_status = MagicMock(side_effect=httpx.HTTPStatusError('', request=MagicMock(), response=response))

        mock_http_client.post = AsyncMock(return_value=response)

        with patch.object(client, '_ensure_gitlab_client', return_value=mock_http_client):
            result = await client.create_branch(
                'https://gitlab.com/myorg/myrepo.git',
                'existing-branch'
            )

        assert result == 'existing-branch'

    @pytest.mark.asyncio
    async def test_commit_artifacts_gitlab(self, client):
        mock_http_client = AsyncMock()

        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json.return_value = {'id': 'abc123def456'}

        mock_http_client.post = AsyncMock(return_value=response)

        with patch.object(client, '_ensure_gitlab_client', return_value=mock_http_client):
            sha = await client.commit_artifacts(
                'https://gitlab.com/myorg/myrepo.git',
                'feature-branch',
                [
                    {'path': 'src/main.py', 'content': 'print("hello")'},
                    {'path': 'README.md', 'content': '# Hello'}
                ],
                'Add new files'
            )

        assert sha == 'abc123def456'

    @pytest.mark.asyncio
    async def test_create_merge_request_gitlab(self, client):
        mock_http_client = AsyncMock()

        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json.return_value = {'web_url': 'https://gitlab.com/myorg/myrepo/-/merge_requests/42'}

        mock_http_client.post = AsyncMock(return_value=response)

        with patch.object(client, '_ensure_gitlab_client', return_value=mock_http_client):
            mr_url = await client.create_merge_request(
                'https://gitlab.com/myorg/myrepo.git',
                'feature-branch',
                'Add new feature',
                'This MR adds a new feature'
            )

        assert mr_url == 'https://gitlab.com/myorg/myrepo/-/merge_requests/42'


class TestGitHubOperations:
    """Testes para operações GitHub"""

    @pytest.mark.asyncio
    async def test_create_branch_github_success(self, client):
        mock_http_client = AsyncMock()

        ref_response = MagicMock()
        ref_response.raise_for_status = MagicMock()
        ref_response.json.return_value = {'object': {'sha': 'abc123'}}

        create_response = MagicMock()
        create_response.status_code = 201
        create_response.raise_for_status = MagicMock()

        mock_http_client.get = AsyncMock(return_value=ref_response)
        mock_http_client.post = AsyncMock(return_value=create_response)

        with patch.object(client, '_ensure_github_client', return_value=mock_http_client):
            result = await client.create_branch(
                'https://github.com/myuser/myrepo',
                'feature-branch'
            )

        assert result == 'feature-branch'

    @pytest.mark.asyncio
    async def test_create_branch_github_already_exists(self, client):
        mock_http_client = AsyncMock()

        ref_response = MagicMock()
        ref_response.raise_for_status = MagicMock()
        ref_response.json.return_value = {'object': {'sha': 'abc123'}}

        create_response = MagicMock()
        create_response.status_code = 422
        create_response.text = 'Reference already exists'
        create_response.raise_for_status = MagicMock(side_effect=httpx.HTTPStatusError('', request=MagicMock(), response=create_response))

        mock_http_client.get = AsyncMock(return_value=ref_response)
        mock_http_client.post = AsyncMock(return_value=create_response)

        with patch.object(client, '_ensure_github_client', return_value=mock_http_client):
            result = await client.create_branch(
                'https://github.com/myuser/myrepo',
                'existing-branch'
            )

        assert result == 'existing-branch'

    @pytest.mark.asyncio
    async def test_commit_artifacts_github(self, client):
        mock_http_client = AsyncMock()

        ref_response = MagicMock()
        ref_response.raise_for_status = MagicMock()
        ref_response.json.return_value = {'object': {'sha': 'base-sha'}}

        commit_response = MagicMock()
        commit_response.raise_for_status = MagicMock()
        commit_response.json.return_value = {'tree': {'sha': 'tree-sha'}}

        blob_response = MagicMock()
        blob_response.raise_for_status = MagicMock()
        blob_response.json.return_value = {'sha': 'blob-sha'}

        tree_response = MagicMock()
        tree_response.raise_for_status = MagicMock()
        tree_response.json.return_value = {'sha': 'new-tree-sha'}

        new_commit_response = MagicMock()
        new_commit_response.raise_for_status = MagicMock()
        new_commit_response.json.return_value = {'sha': 'new-commit-sha'}

        patch_response = MagicMock()
        patch_response.raise_for_status = MagicMock()

        mock_http_client.get = AsyncMock(side_effect=[ref_response, commit_response])
        mock_http_client.post = AsyncMock(side_effect=[blob_response, tree_response, new_commit_response])
        mock_http_client.patch = AsyncMock(return_value=patch_response)

        with patch.object(client, '_ensure_github_client', return_value=mock_http_client):
            sha = await client.commit_artifacts(
                'https://github.com/myuser/myrepo',
                'feature-branch',
                [{'path': 'src/main.py', 'content': 'print("hello")'}],
                'Add new file'
            )

        assert sha == 'new-commit-sha'

    @pytest.mark.asyncio
    async def test_create_pull_request_github(self, client):
        mock_http_client = AsyncMock()

        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json.return_value = {'html_url': 'https://github.com/myuser/myrepo/pull/42'}

        mock_http_client.post = AsyncMock(return_value=response)

        with patch.object(client, '_ensure_github_client', return_value=mock_http_client):
            pr_url = await client.create_merge_request(
                'https://github.com/myuser/myrepo',
                'feature-branch',
                'Add new feature',
                'This PR adds a new feature'
            )

        assert pr_url == 'https://github.com/myuser/myrepo/pull/42'


class TestPushBranch:
    """Testes para push_branch"""

    @pytest.mark.asyncio
    async def test_push_branch_gitlab(self, client):
        await client.push_branch('https://gitlab.com/myorg/myrepo.git', 'feature-branch')

    @pytest.mark.asyncio
    async def test_push_branch_github(self, client):
        await client.push_branch('https://github.com/myuser/myrepo', 'feature-branch')


class TestCloseClient:
    """Testes para close"""

    @pytest.mark.asyncio
    async def test_close_clients(self, client):
        mock_gitlab = AsyncMock()
        mock_github = AsyncMock()

        client._gitlab_client = mock_gitlab
        client._github_client = mock_github

        await client.close()

        mock_gitlab.aclose.assert_awaited_once()
        mock_github.aclose.assert_awaited_once()
        assert client._gitlab_client is None
        assert client._github_client is None
