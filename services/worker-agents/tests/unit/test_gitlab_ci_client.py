"""Unit tests for GitLab CI client."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from src.clients.gitlab_ci_client import (
    GitLabCIClient,
    PipelineStatus,
    GitLabCIAPIError,
    GitLabCITimeoutError,
)


@pytest.fixture
def gitlab_client():
    """Create GitLab CI client for testing."""
    return GitLabCIClient(
        base_url='https://gitlab.example.com',
        token='test-token',
        timeout=30,
        tls_verify=True
    )


@pytest.fixture
def mock_response():
    """Create mock response factory."""
    def _mock_response(status_code=200, json_data=None):
        response = MagicMock()
        response.status_code = status_code
        response.json.return_value = json_data or {}
        response.raise_for_status = MagicMock()
        if status_code >= 400:
            response.raise_for_status.side_effect = Exception(f'HTTP {status_code}')
        return response
    return _mock_response


class TestGitLabCIClient:
    """Tests for GitLabCIClient."""

    def test_init(self, gitlab_client):
        """Test client initialization."""
        assert gitlab_client.base_url == 'https://gitlab.example.com'
        assert gitlab_client.timeout == 30

    def test_from_env(self):
        """Test client creation from environment config."""
        config = MagicMock()
        config.gitlab_url = 'https://gitlab.com'
        config.gitlab_token = 'env-token'
        config.gitlab_timeout_seconds = 600
        config.gitlab_tls_verify = True

        client = GitLabCIClient.from_env(config)

        assert client.base_url == 'https://gitlab.com'
        assert client.timeout == 600

    @pytest.mark.asyncio
    async def test_trigger_pipeline_success(self, gitlab_client, mock_response):
        """Test successful pipeline trigger."""
        pipeline_data = {
            'id': 12345,
            'iid': 100,
            'project_id': 999,
            'status': 'pending',
            'ref': 'main',
            'sha': 'abc123',
            'web_url': 'https://gitlab.example.com/project/-/pipelines/12345',
            'created_at': '2024-01-15T10:00:00Z',
            'updated_at': '2024-01-15T10:00:00Z',
        }

        with patch.object(gitlab_client, '_client') as mock_client:
            mock_client.post = AsyncMock(return_value=mock_response(200, pipeline_data))

            result = await gitlab_client.trigger_pipeline(
                project_id=999,
                ref='main',
                variables={'VAR1': 'value1'}
            )

            assert result['id'] == 12345
            assert result['status'] == 'pending'

    @pytest.mark.asyncio
    async def test_trigger_pipeline_api_error(self, gitlab_client, mock_response):
        """Test pipeline trigger with API error."""
        with patch.object(gitlab_client, '_client') as mock_client:
            mock_client.post = AsyncMock(return_value=mock_response(400, {'error': 'Bad request'}))

            with pytest.raises(GitLabCIAPIError):
                await gitlab_client.trigger_pipeline(project_id=999, ref='main')

    @pytest.mark.asyncio
    async def test_get_pipeline_status_success(self, gitlab_client, mock_response):
        """Test getting pipeline status."""
        pipeline_data = {
            'id': 12345,
            'iid': 100,
            'project_id': 999,
            'status': 'success',
            'ref': 'main',
            'sha': 'abc123',
            'web_url': 'https://gitlab.example.com/project/-/pipelines/12345',
            'created_at': '2024-01-15T10:00:00Z',
            'updated_at': '2024-01-15T10:30:00Z',
            'finished_at': '2024-01-15T10:30:00Z',
            'duration': 1800,
        }

        with patch.object(gitlab_client, '_client') as mock_client:
            mock_client.get = AsyncMock(return_value=mock_response(200, pipeline_data))

            result = await gitlab_client.get_pipeline_status(project_id=999, pipeline_id=12345)

            assert isinstance(result, PipelineStatus)
            assert result.pipeline_id == 12345
            assert result.status == 'success'
            assert result.duration == 1800

    @pytest.mark.asyncio
    async def test_wait_for_pipeline_success(self, gitlab_client, mock_response):
        """Test waiting for pipeline completion."""
        running_data = {
            'id': 12345,
            'iid': 100,
            'project_id': 999,
            'status': 'running',
            'ref': 'main',
            'sha': 'abc123',
            'web_url': 'https://gitlab.example.com/project/-/pipelines/12345',
            'created_at': '2024-01-15T10:00:00Z',
            'updated_at': '2024-01-15T10:15:00Z',
        }

        success_data = {
            **running_data,
            'status': 'success',
            'finished_at': '2024-01-15T10:30:00Z',
            'duration': 1800,
        }

        call_count = 0

        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return mock_response(200, running_data)
            return mock_response(200, success_data)

        with patch.object(gitlab_client, '_client') as mock_client:
            mock_client.get = mock_get

            result = await gitlab_client.wait_for_pipeline(
                project_id=999,
                pipeline_id=12345,
                timeout_seconds=60,
                poll_interval=0.1
            )

            assert result.status == 'success'

    @pytest.mark.asyncio
    async def test_wait_for_pipeline_timeout(self, gitlab_client, mock_response):
        """Test pipeline wait timeout."""
        running_data = {
            'id': 12345,
            'iid': 100,
            'project_id': 999,
            'status': 'running',
            'ref': 'main',
            'sha': 'abc123',
            'web_url': 'https://gitlab.example.com/project/-/pipelines/12345',
            'created_at': '2024-01-15T10:00:00Z',
            'updated_at': '2024-01-15T10:15:00Z',
        }

        with patch.object(gitlab_client, '_client') as mock_client:
            mock_client.get = AsyncMock(return_value=mock_response(200, running_data))

            with pytest.raises(GitLabCITimeoutError):
                await gitlab_client.wait_for_pipeline(
                    project_id=999,
                    pipeline_id=12345,
                    timeout_seconds=0.2,
                    poll_interval=0.1
                )

    @pytest.mark.asyncio
    async def test_get_test_report_success(self, gitlab_client, mock_response):
        """Test getting test report."""
        test_report = {
            'total_time': 120.5,
            'total_count': 50,
            'success_count': 48,
            'failed_count': 2,
            'skipped_count': 0,
            'error_count': 0,
            'test_suites': [
                {
                    'name': 'TestSuite1',
                    'total_time': 60.0,
                    'total_count': 25,
                    'success_count': 25,
                    'failed_count': 0,
                    'skipped_count': 0,
                    'error_count': 0,
                }
            ]
        }

        with patch.object(gitlab_client, '_client') as mock_client:
            mock_client.get = AsyncMock(return_value=mock_response(200, test_report))

            result = await gitlab_client.get_test_report(project_id=999, pipeline_id=12345)

            assert result['total_count'] == 50
            assert result['success_count'] == 48
            assert result['failed_count'] == 2

    @pytest.mark.asyncio
    async def test_get_test_report_summary(self, gitlab_client, mock_response):
        """Test getting test report summary."""
        summary = {
            'total': {'count': 100, 'time': 300.0},
            'success': {'count': 95},
            'failed': {'count': 3},
            'skipped': {'count': 2},
        }

        with patch.object(gitlab_client, '_client') as mock_client:
            mock_client.get = AsyncMock(return_value=mock_response(200, summary))

            result = await gitlab_client.get_test_report_summary(project_id=999, pipeline_id=12345)

            assert result['total']['count'] == 100
            assert result['success']['count'] == 95

    @pytest.mark.asyncio
    async def test_get_pipeline_jobs(self, gitlab_client, mock_response):
        """Test getting pipeline jobs."""
        jobs = [
            {'id': 1, 'name': 'build', 'status': 'success'},
            {'id': 2, 'name': 'test', 'status': 'success'},
            {'id': 3, 'name': 'deploy', 'status': 'pending'},
        ]

        with patch.object(gitlab_client, '_client') as mock_client:
            mock_client.get = AsyncMock(return_value=mock_response(200, jobs))

            result = await gitlab_client.get_pipeline_jobs(project_id=999, pipeline_id=12345)

            assert len(result) == 3
            assert result[0]['name'] == 'build'

    @pytest.mark.asyncio
    async def test_cancel_pipeline(self, gitlab_client, mock_response):
        """Test canceling a pipeline."""
        cancelled_data = {
            'id': 12345,
            'status': 'canceled',
        }

        with patch.object(gitlab_client, '_client') as mock_client:
            mock_client.post = AsyncMock(return_value=mock_response(200, cancelled_data))

            result = await gitlab_client.cancel_pipeline(project_id=999, pipeline_id=12345)

            assert result['status'] == 'canceled'

    @pytest.mark.asyncio
    async def test_retry_pipeline(self, gitlab_client, mock_response):
        """Test retrying a pipeline."""
        retried_data = {
            'id': 12346,
            'status': 'pending',
        }

        with patch.object(gitlab_client, '_client') as mock_client:
            mock_client.post = AsyncMock(return_value=mock_response(200, retried_data))

            result = await gitlab_client.retry_pipeline(project_id=999, pipeline_id=12345)

            assert result['id'] == 12346
            assert result['status'] == 'pending'


class TestPipelineStatus:
    """Tests for PipelineStatus dataclass."""

    def test_is_terminal_success(self):
        """Test is_terminal for success status."""
        status = PipelineStatus(
            pipeline_id=1,
            project_id=999,
            status='success',
            ref='main',
            sha='abc123',
            web_url='https://gitlab.com',
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        assert status.is_terminal is True

    def test_is_terminal_running(self):
        """Test is_terminal for running status."""
        status = PipelineStatus(
            pipeline_id=1,
            project_id=999,
            status='running',
            ref='main',
            sha='abc123',
            web_url='https://gitlab.com',
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        assert status.is_terminal is False

    def test_is_success(self):
        """Test is_success property."""
        status = PipelineStatus(
            pipeline_id=1,
            project_id=999,
            status='success',
            ref='main',
            sha='abc123',
            web_url='https://gitlab.com',
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        assert status.is_success is True

    def test_is_failed(self):
        """Test is_failed property."""
        status = PipelineStatus(
            pipeline_id=1,
            project_id=999,
            status='failed',
            ref='main',
            sha='abc123',
            web_url='https://gitlab.com',
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        assert status.is_failed is True
