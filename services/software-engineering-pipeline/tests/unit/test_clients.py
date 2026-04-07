"""Testes unitários para clientes de integração externa."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.clients.github_client import (
    GitHubClient,
    WorkflowDispatchRequest,
)
from src.clients.gitlab_client import (
    GitLabClient,
    PipelineTriggerRequest,
)
from src.clients.argocd_client import (
    ArgoCDClient,
    ApplicationSyncRequest,
    ApplicationRollbackRequest,
)


@pytest.mark.asyncio
async def test_github_trigger_workflow_success():
    """Teste de disparo bem-sucedido de workflow GitHub."""
    client = GitHubClient(token="test-token")

    mock_response = MagicMock()
    mock_response.status_code = 204

    mock_run_response = MagicMock()
    mock_run_response.status_code = 200
    mock_run_response.json.return_value = {
        "workflow_runs": [
            {
                "id": 12345,
                "html_url": "https://github.com/org/repo/actions/runs/12345",
            }
        ]
    }

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.get = AsyncMock(return_value=mock_run_response)

    client._client = mock_client

    request = WorkflowDispatchRequest(
        owner="org",
        repo="repo",
        workflow_id="test.yml",
        branch="main",
        inputs={"param1": "value1"},
    )

    result = await client.trigger_workflow(request)

    assert result.success is True
    assert result.workflow_run_id == 12345
    assert result.status_url == "https://github.com/org/repo/actions/runs/12345"


@pytest.mark.asyncio
async def test_github_trigger_workflow_failure():
    """Teste de falha ao disparar workflow GitHub."""
    client = GitHubClient(token="test-token")

    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.text = "Workflow not found"
    mock_response.json.return_value = {"message": "Workflow not found"}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    client._client = mock_client

    request = WorkflowDispatchRequest(
        owner="org",
        repo="repo",
        workflow_id="missing.yml",
    )

    result = await client.trigger_workflow(request)

    assert result.success is False
    assert "not found" in result.message.lower()


@pytest.mark.asyncio
async def test_github_get_file_success():
    """Teste de obtenção bem-sucedida de arquivo."""
    client = GitHubClient(token="test-token")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "content": "SGVsbG8gV29ybGQ=",  # "Hello World" base64
        "sha": "abc123",
    }

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    client._client = mock_client

    result = await client.get_file("org", "repo", "README.md")

    assert result is not None
    assert result.path == "README.md"
    assert result.content == "Hello World"
    assert result.sha == "abc123"


@pytest.mark.asyncio
async def test_github_get_file_not_found():
    """Teste de arquivo não encontrado."""
    client = GitHubClient(token="test-token")

    mock_response = MagicMock()
    mock_response.status_code = 404

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    client._client = mock_client

    result = await client.get_file("org", "repo", "missing.txt")

    assert result is None


@pytest.mark.asyncio
async def test_github_create_file():
    """Teste de criação de arquivo."""
    client = GitHubClient(token="test-token")

    mock_response = MagicMock()
    mock_response.status_code = 201

    mock_client = AsyncMock()
    mock_client.put = AsyncMock(return_value=mock_response)

    client._client = mock_client

    result = await client.create_or_update_file(
        owner="org",
        repo="repo",
        path="new-file.txt",
        content="New content",
        message="Create file",
    )

    assert result is True


@pytest.mark.asyncio
async def test_github_get_workflow_run_status():
    """Teste de obtenção de status de workflow run."""
    client = GitHubClient(token="test-token")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": "completed",
        "conclusion": "success",
        "html_url": "https://github.com/org/repo/actions/runs/12345",
        "created_at": "2026-03-27T10:00:00Z",
        "updated_at": "2026-03-27T10:05:00Z",
    }

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    client._client = mock_client

    result = await client.get_workflow_run_status("org", "repo", 12345)

    assert result is not None
    assert result["status"] == "completed"
    assert result["conclusion"] == "success"


@pytest.mark.asyncio
async def test_github_list_workflows():
    """Teste de listagem de workflows."""
    client = GitHubClient(token="test-token")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "workflows": [
            {
                "id": 1,
                "name": "CI",
                "path": ".github/workflows/ci.yml",
                "state": "active",
            },
            {
                "id": 2,
                "name": "CD",
                "path": ".github/workflows/cd.yml",
                "state": "active",
            },
        ]
    }

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    client._client = mock_client

    result = await client.list_workflows("org", "repo")

    assert len(result) == 2
    assert result[0]["name"] == "CI"
    assert result[1]["name"] == "CD"


@pytest.mark.asyncio
async def test_gitlab_trigger_pipeline_success():
    """Teste de disparo bem-sucedido de pipeline GitLab."""
    client = GitLabClient(token="test-token")

    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {
        "id": 42,
        "web_url": "https://gitlab.com/org/repo/-/pipelines/42",
        "status": "pending",
    }

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    client._client = mock_client

    request = PipelineTriggerRequest(
        project_id=123,
        ref="main",
        variables={"VAR1": "value1"},
    )

    result = await client.trigger_pipeline(request)

    assert result.success is True
    assert result.pipeline_id == 42
    assert result.status == "pending"


@pytest.mark.asyncio
async def test_gitlab_get_pipeline_status():
    """Teste de obtenção de status de pipeline."""
    client = GitLabClient(token="test-token")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "id": 42,
        "status": "success",
        "stage": "deploy",
        "web_url": "https://gitlab.com/org/repo/-/pipelines/42",
        "created_at": "2026-03-27T10:00:00Z",
        "updated_at": "2026-03-27T10:05:00Z",
        "finished_at": "2026-03-27T10:05:00Z",
    }

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    client._client = mock_client

    result = await client.get_pipeline_status(123, 42)

    assert result is not None
    assert result["status"] == "success"
    assert result["stage"] == "deploy"


@pytest.mark.asyncio
async def test_gitlab_list_pipelines():
    """Teste de listagem de pipelines."""
    client = GitLabClient(token="test-token")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {"id": 1, "status": "success", "ref": "main"},
        {"id": 2, "status": "running", "ref": "main"},
    ]

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    client._client = mock_client

    result = await client.list_pipelines(123)

    assert len(result) == 2
    assert result[0]["id"] == 1


@pytest.mark.asyncio
async def test_gitlab_get_file():
    """Teste de obtenção de arquivo GitLab."""
    client = GitLabClient(token="test-token")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "file_name": "README.md",
        "file_path": "README.md",
        "content": "SGVsbG8=",  # "Hello" base64
        "size": 5,
        "ref": "main",
        "commit_id": "abc123",
    }

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    client._client = mock_client

    result = await client.get_file(123, "README.md")

    assert result is not None
    assert result["file_name"] == "README.md"
    assert result["content"] == "Hello"


@pytest.mark.asyncio
async def test_gitlab_create_file():
    """Teste de criação de arquivo GitLab."""
    client = GitLabClient(token="test-token")

    mock_response = MagicMock()
    mock_response.status_code = 201

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    client._client = mock_client

    result = await client.create_file(
        project_id=123,
        file_path="new-file.txt",
        content="Content",
        commit_message="Create file",
    )

    assert result is True


@pytest.mark.asyncio
async def test_gitlab_list_branches():
    """Teste de listagem de branches GitLab."""
    client = GitLabClient(token="test-token")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {"name": "main", "protected": True, "default": True},
        {"name": "develop", "protected": False, "default": False},
    ]

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    client._client = mock_client

    result = await client.list_branches(123)

    assert len(result) == 2
    assert result[0]["name"] == "main"
    assert result[0]["protected"] is True


@pytest.mark.asyncio
async def test_argocd_sync_application():
    """Teste de sync de aplicação ArgoCD."""
    client = ArgoCDClient(token="test-token")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"uid": "op-123"}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    client._client = mock_client

    request = ApplicationSyncRequest(
        name="test-app",
        revision="v1.0.0",
    )

    result = await client.sync_application(request)

    assert result.success is True
    assert result.operation_id == "op-123"


@pytest.mark.asyncio
async def test_argocd_rollback_application():
    """Teste de rollback de aplicação ArgoCD."""
    client = ArgoCDClient(token="test-token")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"uid": "rollback-123"}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    client._client = mock_client

    request = ApplicationRollbackRequest(
        name="test-app",
        revision="v0.9.0",
    )

    result = await client.rollback_application(request)

    assert result.success is True
    assert result.operation_id == "rollback-123"


@pytest.mark.asyncio
async def test_argocd_get_application():
    """Teste de obtenção de aplicação ArgoCD."""
    client = ArgoCDClient(token="test-token")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "name": "test-app",
        "spec": {
            "project": "default",
            "destination": {"namespace": "production"},
            "source": {
                "repoURL": "https://github.com/org/manifests",
                "path": "apps",
            },
        },
        "status": {
            "sync": {"status": "Synced", "revision": "v1.0.0"},
            "health": {"status": "Healthy"},
            "operation": None,
        },
    }

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    client._client = mock_client

    result = await client.get_application("test-app")

    assert result is not None
    assert result["name"] == "test-app"
    assert result["sync_status"] == "Synced"
    assert result["health_status"] == "Healthy"


@pytest.mark.asyncio
async def test_argocd_list_applications():
    """Teste de listagem de aplicações ArgoCD."""
    client = ArgoCDClient(token="test-token")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "items": [
            {
                "name": "app1",
                "spec": {
                    "project": "default",
                    "destination": {"namespace": "prod"},
                },
                "status": {
                    "sync": {"status": "Synced", "startedAt": "2026-03-27T10:00:00Z"},
                    "health": {"status": "Healthy"},
                },
            },
            {
                "name": "app2",
                "spec": {
                    "project": "default",
                    "destination": {"namespace": "staging"},
                },
                "status": {
                    "sync": {
                        "status": "OutOfSync",
                        "startedAt": "2026-03-27T09:00:00Z",
                    },
                    "health": {"status": "Progressing"},
                },
            },
        ]
    }

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    client._client = mock_client

    result = await client.list_applications()

    assert len(result) == 2
    assert result[0]["name"] == "app1"
    assert result[1]["sync_status"] == "OutOfSync"


@pytest.mark.asyncio
async def test_argocd_get_application_health():
    """Teste de obtenção de saúde de aplicação."""
    client = ArgoCDClient(token="test-token")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": {
            "health": {"status": "Healthy", "message": "Application is healthy"},
        }
    }

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    client._client = mock_client

    result = await client.get_application_health("test-app")

    assert result is not None
    assert result["healthy"] is True
    assert result["status"] == "Healthy"


@pytest.mark.asyncio
async def test_argocd_get_application_sync_status():
    """Teste de obtenção de status de sync."""
    client = ArgoCDClient(token="test-token")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": {
            "sync": {
                "status": "Synced",
                "revision": "v1.0.0",
                "comparedTo": {"revision": "v1.0.0"},
            }
        }
    }

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    client._client = mock_client

    result = await client.get_application_sync_status("test-app")

    assert result is not None
    assert result["synced"] is True
    assert result["revision"] == "v1.0.0"


@pytest.mark.asyncio
async def test_argocd_delete_application():
    """Teste de deleção de aplicação."""
    client = ArgoCDClient(token="test-token")

    mock_response = MagicMock()
    mock_response.status_code = 200

    mock_client = AsyncMock()
    mock_client.delete = AsyncMock(return_value=mock_response)

    client._client = mock_client

    result = await client.delete_application("test-app")

    assert result is True


@pytest.mark.asyncio
async def test_argocd_create_application():
    """Teste de criação de aplicação."""
    client = ArgoCDClient(token="test-token")

    mock_response = MagicMock()
    mock_response.status_code = 201

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    client._client = mock_client

    result = await client.create_application(
        name="new-app",
        project="default",
        repo_url="https://github.com/org/manifests",
        path="apps",
        destination_namespace="prod",
    )

    assert result is True


@pytest.mark.asyncio
async def test_argocd_get_repository_list():
    """Teste de listagem de repositórios."""
    client = ArgoCDClient(token="test-token")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {
            "repoURL": "https://github.com/org/manifests",
            "connectionState": {"status": "Successful"},
            "insecure": False,
        },
        {
            "repoURL": "https://gitlab.com/org/manifests",
            "connectionState": {"status": "Successful"},
            "insecure": True,
        },
    ]

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    client._client = mock_client

    result = await client.get_repository_list()

    assert len(result) == 2
    assert result[0]["url"] == "https://github.com/org/manifests"
    assert result[1]["insecure"] is True


@pytest.mark.asyncio
async def test_client_close():
    """Teste de fechamento de clientes HTTP."""
    github_client = GitHubClient(token="test-token")
    gitlab_client = GitLabClient(token="test-token")
    argocd_client = ArgoCDClient(token="test-token")

    # Criar clientes mockados
    mock_client = AsyncMock()
    mock_client.aclose = AsyncMock()

    github_client._client = mock_client
    gitlab_client._client = mock_client
    argocd_client._client = mock_client

    await github_client.close()
    await gitlab_client.close()
    await argocd_client.close()

    assert mock_client.aclose.call_count == 3
