"""
Integration tests for DeployExecutor.

Tests the DeployExecutor with mocked and real ArgoCD integration,
including timeout handling, error scenarios, and fallback to simulation.
"""

import asyncio
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from tests.fixtures.client_fixtures import MockArgoCDServer
from tests.helpers.integration_helpers import (
    ExecutorTestHelper,
    ResultValidator,
)


pytestmark = [pytest.mark.integration]


class TestDeployExecutorWithMockArgoCD:
    """Tests for DeployExecutor with mocked ArgoCD API."""

    @pytest.mark.asyncio
    async def test_deploy_executor_with_mock_argocd_success(
        self, worker_config, mock_vault_client, mock_metrics
    ):
        """Test successful deployment with mocked ArgoCD."""
        from services.worker_agents.src.executors.deploy_executor import DeployExecutor

        # Create mock ArgoCD server
        mock_server = MockArgoCDServer(base_health_status='Healthy')

        # Enable ArgoCD in config
        worker_config.argocd_enabled = True
        worker_config.argocd_url = 'http://argocd-mock:8080'
        worker_config.argocd_token = 'test-token'

        executor = DeployExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )

        # Patch httpx.AsyncClient to use mock transport
        with patch.object(httpx, 'AsyncClient') as mock_client_class:
            mock_client = mock_server.get_client()
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

            ticket = ExecutorTestHelper.create_deploy_ticket(
                namespace='test-ns',
                deployment_name='test-app',
                image='myapp:v1.0',
                replicas=2,
                repo_url='https://github.com/test/repo',
                chart_path='charts/app',
            )

            result = await executor.execute(ticket)

        # Validate result
        ResultValidator.assert_success(result)
        ResultValidator.assert_simulated(result, expected=False)
        ResultValidator.assert_has_output(result, 'deployment_id', 'status', 'namespace')
        ResultValidator.assert_output_value(result, 'deployment_id', 'test-app')
        ResultValidator.assert_output_value(result, 'namespace', 'test-ns')
        ResultValidator.assert_has_logs(result, min_count=2)

    @pytest.mark.asyncio
    async def test_deploy_executor_argocd_timeout(
        self, worker_config, mock_vault_client, mock_metrics
    ):
        """Test timeout when ArgoCD application never becomes healthy."""
        from services.worker_agents.src.executors.deploy_executor import DeployExecutor

        # Create mock ArgoCD server that never becomes healthy
        mock_server = MockArgoCDServer(base_health_status='Progressing')

        worker_config.argocd_enabled = True
        worker_config.argocd_url = 'http://argocd-mock:8080'
        worker_config.argocd_token = 'test-token'

        executor = DeployExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )

        with patch.object(httpx, 'AsyncClient') as mock_client_class:
            mock_client = mock_server.get_client()
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

            ticket = ExecutorTestHelper.create_deploy_ticket(
                deployment_name='timeout-app',
                timeout_seconds=2,  # Short timeout
                poll_interval=0.5,
            )

            result = await executor.execute(ticket)

        # Should timeout and return failure
        ResultValidator.assert_failure(result)
        ResultValidator.assert_simulated(result, expected=False)
        ResultValidator.assert_output_value(result, 'status', 'timeout')

    @pytest.mark.asyncio
    async def test_deploy_executor_argocd_auth_error(
        self, worker_config, mock_vault_client, mock_metrics
    ):
        """Test handling of ArgoCD authentication error."""
        from services.worker_agents.src.executors.deploy_executor import DeployExecutor

        worker_config.argocd_enabled = True
        worker_config.argocd_url = 'http://argocd-mock:8080'
        worker_config.argocd_token = 'invalid-token'

        executor = DeployExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )

        # Create a mock that returns 401
        async def mock_post(*args, **kwargs):
            response = httpx.Response(
                status_code=401,
                content=b'{"error": "Unauthorized"}',
            )
            response.raise_for_status()

        with patch.object(httpx.AsyncClient, 'post', side_effect=httpx.HTTPStatusError(
            'Unauthorized',
            request=MagicMock(),
            response=httpx.Response(status_code=401),
        )):
            ticket = ExecutorTestHelper.create_deploy_ticket()

            result = await executor.execute(ticket)

        # Should fail with error status
        ResultValidator.assert_failure(result)
        ResultValidator.assert_output_value(result, 'status', 'error')

    @pytest.mark.asyncio
    async def test_deploy_executor_argocd_connection_error(
        self, worker_config, mock_vault_client, mock_metrics
    ):
        """Test handling of connection error to ArgoCD."""
        from services.worker_agents.src.executors.deploy_executor import DeployExecutor

        worker_config.argocd_enabled = True
        worker_config.argocd_url = 'http://argocd-unreachable:8080'
        worker_config.argocd_token = 'test-token'

        executor = DeployExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )

        # Mock connection error
        with patch.object(httpx.AsyncClient, 'post', side_effect=httpx.ConnectError('Connection refused')):
            ticket = ExecutorTestHelper.create_deploy_ticket()

            result = await executor.execute(ticket)

        # Should fail
        ResultValidator.assert_failure(result)
        ResultValidator.assert_simulated(result, expected=False)


class TestDeployExecutorSimulation:
    """Tests for DeployExecutor simulation mode (ArgoCD disabled)."""

    @pytest.mark.asyncio
    async def test_deploy_executor_simulation_mode(
        self, worker_config_minimal, mock_vault_client, mock_metrics
    ):
        """Test deployment in pure simulation mode."""
        from services.worker_agents.src.executors.deploy_executor import DeployExecutor

        executor = DeployExecutor(
            config=worker_config_minimal,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )

        ticket = ExecutorTestHelper.create_deploy_ticket(
            namespace='test-ns',
            deployment_name='simulated-app',
        )

        result = await executor.execute(ticket)

        # Simulation should succeed
        ResultValidator.assert_success(result)
        ResultValidator.assert_simulated(result, expected=True)
        ResultValidator.assert_has_output(result, 'deployment_id', 'status', 'namespace')
        ResultValidator.assert_output_value(result, 'status', 'deployed')
        ResultValidator.assert_log_contains(result, 'simulated')

    @pytest.mark.asyncio
    async def test_deploy_executor_fallback_simulation(
        self, worker_config, mock_vault_client, mock_metrics
    ):
        """Test fallback to simulation when ArgoCD is disabled."""
        from services.worker_agents.src.executors.deploy_executor import DeployExecutor

        # ArgoCD disabled by default in worker_config
        worker_config.argocd_enabled = False

        executor = DeployExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )

        ticket = ExecutorTestHelper.create_deploy_ticket()

        result = await executor.execute(ticket)

        # Should use simulation
        ResultValidator.assert_success(result)
        ResultValidator.assert_simulated(result, expected=True)

    @pytest.mark.asyncio
    async def test_deploy_executor_simulation_metrics(
        self, worker_config_minimal, mock_vault_client, mock_metrics
    ):
        """Test that metrics are recorded in simulation mode."""
        from services.worker_agents.src.executors.deploy_executor import DeployExecutor

        executor = DeployExecutor(
            config=worker_config_minimal,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )

        ticket = ExecutorTestHelper.create_deploy_ticket()

        result = await executor.execute(ticket)

        # Verify metrics were recorded
        mock_metrics.deploy_tasks_executed_total.labels.assert_called_with(status='success')
        mock_metrics.deploy_duration_seconds.labels.assert_called_with(stage='simulated')


class TestDeployExecutorValidation:
    """Tests for DeployExecutor input validation."""

    @pytest.mark.asyncio
    async def test_deploy_executor_missing_ticket_id(self, deploy_executor):
        """Test that missing ticket_id raises ValidationError."""
        from services.worker_agents.src.executors.base_executor import ValidationError

        ticket = {
            'task_id': 'task-123',
            'task_type': 'DEPLOY',
            'parameters': {},
        }

        with pytest.raises(ValidationError) as exc_info:
            await deploy_executor.execute(ticket)

        assert 'ticket_id' in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_deploy_executor_wrong_task_type(self, deploy_executor):
        """Test that wrong task_type raises ValidationError."""
        from services.worker_agents.src.executors.base_executor import ValidationError

        ticket = {
            'ticket_id': 'ticket-123',
            'task_id': 'task-123',
            'task_type': 'BUILD',  # Wrong type
            'parameters': {},
        }

        with pytest.raises(ValidationError) as exc_info:
            await deploy_executor.execute(ticket)

        assert 'task type mismatch' in str(exc_info.value).lower()


class TestDeployExecutorWithMockHTTPTransport:
    """Tests using httpx.MockTransport for HTTP mocking."""

    @pytest.mark.asyncio
    async def test_deploy_executor_mock_transport_success(
        self, worker_config, mock_vault_client, mock_metrics
    ):
        """Test with httpx MockTransport for clean HTTP mocking."""
        from services.worker_agents.src.executors.deploy_executor import DeployExecutor

        # Track requests for verification
        requests_made = []

        def handle_request(request: httpx.Request) -> httpx.Response:
            requests_made.append(request)
            path = request.url.path

            # POST /api/v1/applications - create
            if request.method == 'POST' and path == '/api/v1/applications':
                return httpx.Response(
                    status_code=201,
                    json={'metadata': {'name': 'mock-app'}},
                )

            # GET /api/v1/applications/{name} - status
            if request.method == 'GET' and path.startswith('/api/v1/applications/'):
                return httpx.Response(
                    status_code=200,
                    json={
                        'metadata': {'name': 'mock-app'},
                        'status': {
                            'health': {'status': 'Healthy'},
                            'sync': {'status': 'Synced'},
                        },
                    },
                )

            return httpx.Response(status_code=404, json={'error': 'Not found'})

        transport = httpx.MockTransport(handle_request)

        worker_config.argocd_enabled = True
        worker_config.argocd_url = 'http://mock-argocd:8080'
        worker_config.argocd_token = 'test-token'

        executor = DeployExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )

        # Patch AsyncClient to use our transport
        original_init = httpx.AsyncClient.__init__

        def patched_init(self, *args, **kwargs):
            kwargs['transport'] = transport
            kwargs.pop('timeout', None)
            return original_init(self, *args, **kwargs)

        with patch.object(httpx.AsyncClient, '__init__', patched_init):
            ticket = ExecutorTestHelper.create_deploy_ticket(
                deployment_name='mock-app',
            )

            result = await executor.execute(ticket)

        # Validate result
        ResultValidator.assert_success(result)
        ResultValidator.assert_simulated(result, expected=False)

        # Verify requests were made
        assert len(requests_made) >= 2, 'Expected at least POST and GET requests'


@pytest.mark.real_integration
@pytest.mark.argocd
class TestDeployExecutorRealArgoCD:
    """Tests that require a real ArgoCD instance."""

    @pytest.mark.asyncio
    async def test_deploy_executor_with_real_argocd(
        self, worker_config, mock_vault_client, mock_metrics
    ):
        """Test with real ArgoCD (requires ARGOCD_URL and ARGOCD_TOKEN env vars)."""
        from services.worker_agents.src.executors.deploy_executor import DeployExecutor

        argocd_url = os.getenv('ARGOCD_URL')
        argocd_token = os.getenv('ARGOCD_TOKEN')

        if not argocd_url or not argocd_token:
            pytest.skip('ARGOCD_URL and ARGOCD_TOKEN not configured')

        worker_config.argocd_enabled = True
        worker_config.argocd_url = argocd_url
        worker_config.argocd_token = argocd_token

        executor = DeployExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )

        # Create a test application with unique name
        import uuid
        test_app_name = f'test-integration-{uuid.uuid4().hex[:8]}'

        try:
            ticket = ExecutorTestHelper.create_deploy_ticket(
                deployment_name=test_app_name,
                namespace='default',
                repo_url='https://github.com/argoproj/argocd-example-apps',
                chart_path='guestbook',
                timeout_seconds=120,
            )

            result = await executor.execute(ticket)

            # With real service, expect either success or graceful failure
            assert 'success' in result
            assert 'output' in result
            assert 'metadata' in result

        finally:
            # Cleanup: delete test application
            try:
                async with httpx.AsyncClient() as client:
                    await client.delete(
                        f'{argocd_url}/api/v1/applications/{test_app_name}',
                        headers={'Authorization': f'Bearer {argocd_token}'},
                    )
            except Exception:
                pass  # Cleanup failure is not critical
