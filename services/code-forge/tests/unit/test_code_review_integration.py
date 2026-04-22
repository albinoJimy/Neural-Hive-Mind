"""
Testes unitários para CodeReviewIntegration.

Cobertura:
- Criação de Pull Requests
- Criação de Merge Requests
- Comentários de validação
- Status de review
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.services.code_review_integration import (
    CodeReviewClient,
    CodeReviewIntegration,
    GitProvider,
    ReviewStatus,
)
from src.types.artifact_types import ValidationResult, ValidationStatus, ValidationType


@pytest.fixture()
def mock_httpx_client():
    """Fixture para cliente HTTPX mockado."""
    with patch("src.services.code_review_integration.httpx.AsyncClient") as mock:
        client = AsyncMock()
        mock.return_value = client
        yield client


class TestCodeReviewClientInit:
    """Testes de inicialização do CodeReviewClient."""

    def test_init_github(self):
        """Testa inicialização para GitHub."""
        client = CodeReviewClient(
            provider=GitProvider.GITHUB, base_url="https://api.github.com", token="test-token"
        )

        assert client.provider == GitProvider.GITHUB
        assert client.base_url == "https://api.github.com"
        assert client.token == "test-token"

    def test_init_gitlab(self):
        """Testa inicialização para GitLab."""
        client = CodeReviewClient(
            provider=GitProvider.GITLAB, base_url="https://gitlab.com/api/v4", token="test-token"
        )

        assert client.provider == GitProvider.GITLAB
        assert client.base_url == "https://gitlab.com/api/v4"

    def test_headers_github(self):
        """Testa headers para GitHub."""
        client = CodeReviewClient(
            provider=GitProvider.GITHUB, base_url="https://api.github.com", token="test-token"
        )

        headers = client._get_headers()

        assert "Authorization" in headers
        assert headers["Authorization"] == "token test-token"
        assert "X-GitHub-Api-Version" in headers

    def test_headers_gitlab(self):
        """Testa headers para GitLab."""
        client = CodeReviewClient(
            provider=GitProvider.GITLAB, base_url="https://gitlab.com", token="test-token"
        )

        headers = client._get_headers()

        assert "PRIVATE-TOKEN" in headers
        assert headers["PRIVATE-TOKEN"] == "test-token"


class TestGitHubPullRequests:
    """Testes de criação de Pull Requests no GitHub."""

    @pytest.mark.asyncio()
    async def test_create_pr_basic(self, mock_httpx_client):
        """Testa criação básica de PR."""
        # Configurar mock
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "number": 123,
            "id": 456,
            "html_url": "https://github.com/owner/repo/pull/123",
            "state": "open",
            "draft": False,
            "created_at": "2024-01-01T00:00:00Z",
        }
        mock_httpx_client.post.return_value = mock_response

        client = CodeReviewClient(
            provider=GitProvider.GITHUB, base_url="https://api.github.com", token="test-token"
        )

        result = await client.create_pull_request(
            repo_owner="owner",
            repo_name="repo",
            title="Test PR",
            description="Test description",
            source_branch="feature-branch",
        )

        assert result["provider"] == "github"
        assert result["pr_number"] == 123
        assert result["url"] == "https://github.com/owner/repo/pull/123"

    @pytest.mark.asyncio()
    async def test_create_pr_with_labels(self, mock_httpx_client):
        """Testa criação de PR com labels."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "number": 124,
            "id": 457,
            "html_url": "https://github.com/owner/repo/pull/124",
            "state": "open",
            "draft": False,
            "created_at": "2024-01-01T00:00:00Z",
        }
        mock_httpx_client.post.return_value = mock_response

        client = CodeReviewClient(
            provider=GitProvider.GITHUB, base_url="https://api.github.com", token="test-token"
        )

        result = await client.create_pull_request(
            repo_owner="owner",
            repo_name="repo",
            title="PR with labels",
            description="Description",
            source_branch="branch",
            labels=["enhancement", "automated"],
        )

        assert result["pr_number"] == 124

    @pytest.mark.asyncio()
    async def test_create_draft_pr(self, mock_httpx_client):
        """Testa criação de draft PR."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "number": 125,
            "id": 458,
            "html_url": "https://github.com/owner/repo/pull/125",
            "state": "open",
            "draft": True,
            "created_at": "2024-01-01T00:00:00Z",
        }
        mock_httpx_client.post.return_value = mock_response

        client = CodeReviewClient(
            provider=GitProvider.GITHUB, base_url="https://api.github.com", token="test-token"
        )

        result = await client.create_pull_request(
            repo_owner="owner",
            repo_name="repo",
            title="Draft PR",
            description="Draft description",
            source_branch="draft-branch",
            draft=True,
        )

        assert result["draft"] is True

    @pytest.mark.asyncio()
    async def test_create_pr_wrong_provider(self):
        """Testa erro ao criar PR com provider errado."""
        client = CodeReviewClient(
            provider=GitProvider.GITLAB, base_url="https://gitlab.com", token="test-token"
        )

        with pytest.raises(ValueError, match="only supports GitHub"):
            await client.create_pull_request(
                repo_owner="owner",
                repo_name="repo",
                title="Test",
                description="Test",
                source_branch="branch",
            )


class TestGitLabMergeRequests:
    """Testes de criação de Merge Requests no GitLab."""

    @pytest.mark.asyncio()
    async def test_create_mr_basic(self, mock_httpx_client):
        """Testa criação básica de MR."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": 789,
            "iid": 42,
            "web_url": "https://gitlab.com/group/project/-/merge_requests/42",
            "state": "opened",
            "draft": False,
            "created_at": "2024-01-01T00:00:00Z",
        }
        mock_httpx_client.post.return_value = mock_response

        client = CodeReviewClient(
            provider=GitProvider.GITLAB, base_url="https://gitlab.com", token="test-token"
        )

        result = await client.create_merge_request(
            project_id=123,
            source_branch="feature-branch",
            target_branch="main",
            title="Test MR",
            description="Test description",
        )

        assert result["provider"] == "gitlab"
        assert result["mr_number"] == 42
        assert result["web_url"] == "https://gitlab.com/group/project/-/merge_requests/42"

    @pytest.mark.asyncio()
    async def test_create_mr_draft(self, mock_httpx_client):
        """Testa criação de draft MR."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": 790,
            "iid": 43,
            "web_url": "https://gitlab.com/group/project/-/merge_requests/43",
            "state": "opened",
            "draft": True,
            "created_at": "2024-01-01T00:00:00Z",
        }
        mock_httpx_client.post.return_value = mock_response

        client = CodeReviewClient(
            provider=GitProvider.GITLAB, base_url="https://gitlab.com", token="test-token"
        )

        result = await client.create_merge_request(
            project_id=123,
            source_branch="draft-branch",
            target_branch="main",
            title="Draft MR",
            draft=True,
        )

        assert result["draft"] is True

    @pytest.mark.asyncio()
    async def test_create_mr_wrong_provider(self):
        """Testa erro ao criar MR com provider errado."""
        client = CodeReviewClient(
            provider=GitProvider.GITHUB, base_url="https://api.github.com", token="test-token"
        )

        with pytest.raises(ValueError, match="only supports GitLab"):
            await client.create_merge_request(project_id=123, source_branch="branch")


class TestValidationComments:
    """Testes de comentários de validação."""

    def test_format_validation_comment_passed(self):
        """Testa formatação de comentário com validações passadas."""
        client = CodeReviewClient(
            provider=GitProvider.GITHUB, base_url="https://api.github.com", token="test-token"
        )

        validation_results = [
            ValidationResult(
                validation_type=ValidationType.SAST,
                tool_name="SonarQube",
                tool_version="1.0",
                status=ValidationStatus.PASSED,
                score=0.95,
                issues_count=0,
                critical_issues=0,
                high_issues=0,
                medium_issues=0,
                low_issues=0,
                executed_at=None,
                duration_ms=1000,
                report_uri="https://sonarqube.com/report/123",
            )
        ]

        comment = client._format_validation_comment(validation_results, "approved")

        assert "## 🔍 Code Review" in comment
        assert "### Validation Results" in comment
        assert "✅ **SonarQube**" in comment
        assert "### ✅ Approved" in comment

    def test_format_validation_comment_failed(self):
        """Testa formatação de comentário com validações falhadas."""
        client = CodeReviewClient(
            provider=GitProvider.GITHUB, base_url="https://api.github.com", token="test-token"
        )

        validation_results = [
            ValidationResult(
                validation_type=ValidationType.SCA,
                tool_name="Snyk",
                tool_version="1.0",
                status=ValidationStatus.FAILED,
                score=0.5,
                issues_count=10,
                critical_issues=2,
                high_issues=5,
                medium_issues=2,
                low_issues=1,
                executed_at=None,
                duration_ms=2000,
                report_uri="https://snyk.com/report/456",
            )
        ]

        comment = client._format_validation_comment(validation_results, "changes_requested")

        assert "❌ **Snyk**" in comment
        assert "- Issues: 10" in comment
        assert "- 🔴 Critical: 2" in comment
        assert "### 🔧 Recommendations" in comment

    def test_format_validation_comment_multiple(self):
        """Testa formatação com múltiplos tipos de validação."""
        client = CodeReviewClient(
            provider=GitProvider.GITHUB, base_url="https://api.github.com", token="test-token"
        )

        validation_results = [
            ValidationResult(
                validation_type=ValidationType.SAST,
                tool_name="SonarQube",
                tool_version="1.0",
                status=ValidationStatus.PASSED,
                score=0.9,
                issues_count=1,
                critical_issues=0,
                high_issues=0,
                medium_issues=1,
                low_issues=0,
                executed_at=None,
                duration_ms=1000,
                report_uri="https://sonarqube.com/report/1",
            ),
            ValidationResult(
                validation_type=ValidationType.LICENSE_CHECK,
                tool_name="LicenseValidator",
                tool_version="1.0",
                status=ValidationStatus.PASSED,
                score=1.0,
                issues_count=0,
                critical_issues=0,
                high_issues=0,
                medium_issues=0,
                low_issues=0,
                executed_at=None,
                duration_ms=500,
                report_uri=None,
            ),
        ]

        comment = client._format_validation_comment(validation_results, "approved")

        assert "#### SAST" in comment
        assert "#### LICENSE_CHECK" in comment

    @pytest.mark.asyncio()
    async def test_add_validation_comment_github(self, mock_httpx_client):
        """Testa adicionar comentário no GitHub."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": 999,
            "html_url": "https://github.com/owner/repo/pull/1#issuecomment-999",
        }
        mock_httpx_client.post.return_value = mock_response

        client = CodeReviewClient(
            provider=GitProvider.GITHUB, base_url="https://api.github.com", token="test-token"
        )

        result = await client.add_validation_comment(
            repo_owner="owner",
            repo_name="repo",
            pr_number=1,
            validation_results=[],
            overall_status="approved",
        )

        assert result["comment_id"] == 999


class TestReviewStatus:
    """Testes de status de review."""

    @pytest.mark.asyncio()
    async def test_approve_pull_request(self, mock_httpx_client):
        """Testa aprovação de PR."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": 111,
            "user": {"login": "code-forge"},
            "state": "APPROVED",
            "submitted_at": "2024-01-01T00:00:00Z",
        }
        mock_httpx_client.post.return_value = mock_response

        client = CodeReviewClient(
            provider=GitProvider.GITHUB, base_url="https://api.github.com", token="test-token"
        )

        result = await client.set_review_status(
            repo_owner="owner",
            repo_name="repo",
            pr_number=1,
            status=ReviewStatus.APPROVED,
            comment="LGTM! Great work.",
        )

        assert result["state"] == "APPROVED"
        assert result["user"] == "code-forge"

    @pytest.mark.asyncio()
    async def test_request_changes(self, mock_httpx_client):
        """Testa solicitação de mudanças."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": 112,
            "user": {"login": "code-forge"},
            "state": "CHANGES_REQUESTED",
            "submitted_at": "2024-01-01T00:00:00Z",
        }
        mock_httpx_client.post.return_value = mock_response

        client = CodeReviewClient(
            provider=GitProvider.GITHUB, base_url="https://api.github.com", token="test-token"
        )

        result = await client.set_review_status(
            repo_owner="owner",
            repo_name="repo",
            pr_number=1,
            status=ReviewStatus.CHANGES_REQUESTED,
            comment="Please address the security issues.",
        )

        assert result["state"] == "CHANGES_REQUESTED"


class TestCodeReviewIntegration:
    """Testes de integração de Code Review."""

    @pytest.mark.asyncio()
    async def test_calculate_overall_status_all_passed(self):
        """Testa cálculo de status quando tudo passou."""
        integration = CodeReviewIntegration()

        validation_results = [
            ValidationResult(
                validation_type=ValidationType.SAST,
                tool_name="Tool1",
                tool_version="1.0",
                status=ValidationStatus.PASSED,
                score=0.9,
                issues_count=0,
                critical_issues=0,
                high_issues=0,
                medium_issues=0,
                low_issues=0,
                executed_at=None,
                duration_ms=100,
                report_uri=None,
            )
        ]

        status = integration._calculate_overall_status(validation_results)

        assert status == "approved"

    @pytest.mark.asyncio()
    async def test_calculate_overall_status_critical_issues(self):
        """Testa cálculo de status com issues críticos."""
        integration = CodeReviewIntegration()

        validation_results = [
            ValidationResult(
                validation_type=ValidationType.SAST,
                tool_name="Tool1",
                tool_version="1.0",
                status=ValidationStatus.FAILED,
                score=0.3,
                issues_count=10,
                critical_issues=3,
                high_issues=2,
                medium_issues=3,
                low_issues=2,
                executed_at=None,
                duration_ms=100,
                report_uri=None,
            )
        ]

        status = integration._calculate_overall_status(validation_results)

        assert status == "changes_requested"

    def test_generate_pr_description(self):
        """Testa geração de descrição de PR."""
        integration = CodeReviewIntegration()

        validation_results = [
            ValidationResult(
                validation_type=ValidationType.SAST,
                tool_name="Tool1",
                tool_version="1.0",
                status=ValidationStatus.PASSED,
                score=0.9,
                issues_count=0,
                critical_issues=0,
                high_issues=0,
                medium_issues=0,
                low_issues=0,
                executed_at=None,
                duration_ms=100,
                report_uri="https://example.com/report",
            )
        ]

        description = integration._generate_pr_description("artifact-123", validation_results)

        assert "## 📦 Generated Artifact" in description
        assert "artifact-123" in description
        assert "## 🔍 Validations" in description
        assert "✅" in description

    def test_all_validations_passed(self):
        """Testa verificação se todas validações passaram."""
        integration = CodeReviewIntegration()

        # Todas passaram
        passed_results = [
            ValidationResult(
                validation_type=ValidationType.SAST,
                tool_name="Tool",
                tool_version="1.0",
                status=ValidationStatus.PASSED,
                score=1.0,
                issues_count=0,
                critical_issues=0,
                high_issues=0,
                medium_issues=0,
                low_issues=0,
                executed_at=None,
                duration_ms=100,
                report_uri=None,
            )
        ]

        assert integration._all_validations_passed(passed_results) is True

        # Algumas falharam
        failed_results = [
            ValidationResult(
                validation_type=ValidationType.SAST,
                tool_name="Tool",
                tool_version="1.0",
                status=ValidationStatus.FAILED,
                score=0.5,
                issues_count=5,
                critical_issues=1,
                high_issues=2,
                medium_issues=1,
                low_issues=1,
                executed_at=None,
                duration_ms=100,
                report_uri=None,
            )
        ]

        assert integration._all_validations_passed(failed_results) is False


class TestEdgeCases:
    """Testes de casos extremos."""

    def test_empty_validation_results(self):
        """Testa com lista vazia de validações."""
        client = CodeReviewClient(
            provider=GitProvider.GITHUB, base_url="https://api.github.com", token="test-token"
        )

        comment = client._format_validation_comment([], "commented")

        assert "No validations performed" in comment

    @pytest.mark.asyncio()
    async def test_close_client(self, mock_httpx_client):
        """Testa fechamento do cliente."""
        client = CodeReviewClient(
            provider=GitProvider.GITHUB, base_url="https://api.github.com", token="test-token"
        )

        # Não deve levantar exceção
        await client.close()
