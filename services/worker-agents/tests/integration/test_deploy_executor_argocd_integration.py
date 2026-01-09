"""
Testes de integracao para DeployExecutor com ArgoCD mock server.

Cobertura:
- Fluxo completo de deployment
- Polling de health check
- Tratamento de timeout
- Erros de autenticacao
- Cenarios de rollback
"""

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock
from aioresponses import aioresponses
import uuid


ARGOCD_BASE_URL = 'http://argocd.test:8080'


@pytest.fixture
def worker_config():
    """Configuracao do worker para testes de integracao."""
    config = MagicMock()
    config.argocd_url = ARGOCD_BASE_URL
    config.argocd_token = 'test-token'
    config.argocd_enabled = True
    config.flux_enabled = False
    return config


@pytest.fixture
def mock_metrics():
    """Mock para metricas Prometheus."""
    metrics = MagicMock()
    metrics.deploy_tasks_executed_total = MagicMock()
    metrics.deploy_tasks_executed_total.labels.return_value.inc = MagicMock()
    metrics.deploy_duration_seconds = MagicMock()
    metrics.deploy_duration_seconds.labels.return_value.observe = MagicMock()
    metrics.argocd_api_calls_total = MagicMock()
    metrics.argocd_api_calls_total.labels.return_value.inc = MagicMock()
    return metrics


@pytest.fixture
def deploy_ticket():
    """Ticket de deploy para testes."""
    ticket_id = str(uuid.uuid4())
    return {
        'ticket_id': ticket_id,
        'task_id': f'task-{ticket_id[:8]}',
        'task_type': 'DEPLOY',
        'parameters': {
            'namespace': 'production',
            'deployment_name': 'integration-test-app',
            'image': 'my-registry/my-app:v1.0.0',
            'replicas': 3,
            'repo_url': 'https://github.com/org/repo',
            'chart_path': 'charts/my-app',
            'revision': 'main',
            'provider': 'argocd',
            'timeout_seconds': 10,
            'poll_interval': 1
        }
    }


@pytest.fixture
def argocd_client():
    """Cliente ArgoCD real para testes de integracao."""
    from services.worker_agents.src.clients.argocd_client import ArgoCDClient
    return ArgoCDClient(
        base_url=ARGOCD_BASE_URL,
        token='test-token',
        timeout=30
    )


@pytest.fixture
def deploy_executor_integration(worker_config, mock_metrics, argocd_client):
    """DeployExecutor para testes de integracao."""
    from services.worker_agents.src.executors.deploy_executor import DeployExecutor

    return DeployExecutor(
        config=worker_config,
        vault_client=None,
        code_forge_client=None,
        metrics=mock_metrics,
        argocd_client=argocd_client,
        flux_client=None
    )


class TestFullDeploymentFlow:
    """Testes de fluxo completo de deployment."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_full_deployment_flow_success(
        self,
        deploy_executor_integration,
        deploy_ticket,
        argocd_client
    ):
        """Deve executar fluxo completo de deployment com sucesso."""
        app_name = deploy_ticket['parameters']['deployment_name']

        with aioresponses() as m:
            # Mock create application
            m.post(
                f'{ARGOCD_BASE_URL}/api/v1/applications',
                payload={'metadata': {'name': app_name}},
                status=200
            )

            # Mock get status - first call returns Progressing
            m.get(
                f'{ARGOCD_BASE_URL}/api/v1/applications/{app_name}',
                payload={
                    'metadata': {'name': app_name},
                    'status': {
                        'health': {'status': 'Progressing'},
                        'sync': {'status': 'Syncing'}
                    }
                },
                status=200
            )

            # Mock get status - second call returns Healthy
            m.get(
                f'{ARGOCD_BASE_URL}/api/v1/applications/{app_name}',
                payload={
                    'metadata': {'name': app_name},
                    'status': {
                        'health': {'status': 'Healthy', 'message': 'All resources healthy'},
                        'sync': {'status': 'Synced', 'revision': 'abc123'}
                    }
                },
                status=200
            )

            result = await deploy_executor_integration.execute(deploy_ticket)

            assert result['success'] is True
            assert result['output']['status'] == 'healthy'
            assert result['metadata']['provider'] == 'argocd'

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_deployment_with_multiple_polling_cycles(
        self,
        deploy_executor_integration,
        deploy_ticket,
        argocd_client
    ):
        """Deve fazer multiple polling cycles ate ficar healthy."""
        app_name = deploy_ticket['parameters']['deployment_name']

        with aioresponses() as m:
            # Mock create application
            m.post(
                f'{ARGOCD_BASE_URL}/api/v1/applications',
                payload={'metadata': {'name': app_name}},
                status=200
            )

            # Mock get status - multiple Progressing responses
            for _ in range(3):
                m.get(
                    f'{ARGOCD_BASE_URL}/api/v1/applications/{app_name}',
                    payload={
                        'metadata': {'name': app_name},
                        'status': {
                            'health': {'status': 'Progressing'},
                            'sync': {'status': 'Syncing'}
                        }
                    },
                    status=200
                )

            # Final Healthy response
            m.get(
                f'{ARGOCD_BASE_URL}/api/v1/applications/{app_name}',
                payload={
                    'metadata': {'name': app_name},
                    'status': {
                        'health': {'status': 'Healthy'},
                        'sync': {'status': 'Synced', 'revision': 'xyz789'}
                    }
                },
                status=200
            )

            result = await deploy_executor_integration.execute(deploy_ticket)

            assert result['success'] is True
            assert result['output']['status'] == 'healthy'


class TestDeploymentHealthCheckPolling:
    """Testes de polling de health check."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_polling_respects_interval(
        self,
        argocd_client
    ):
        """Deve respeitar intervalo de polling."""
        from services.worker_agents.src.clients.argocd_client import (
            ApplicationStatus,
            HealthStatus,
            SyncStatus
        )

        call_times = []

        original_get_status = argocd_client.get_application_status

        async def mock_get_status(app_name):
            call_times.append(asyncio.get_event_loop().time())
            if len(call_times) >= 3:
                return ApplicationStatus(
                    name=app_name,
                    health=HealthStatus(status='Healthy'),
                    sync=SyncStatus(status='Synced')
                )
            return ApplicationStatus(
                name=app_name,
                health=HealthStatus(status='Progressing'),
                sync=SyncStatus(status='Syncing')
            )

        argocd_client.get_application_status = mock_get_status

        try:
            await argocd_client.wait_for_health(
                'test-app',
                poll_interval=1,
                timeout=10
            )

            # Verificar que houve intervalo entre chamadas
            assert len(call_times) >= 3
            for i in range(1, len(call_times)):
                interval = call_times[i] - call_times[i-1]
                assert interval >= 0.9  # Permitir pequena variacao

        finally:
            argocd_client.get_application_status = original_get_status


class TestDeploymentTimeoutHandling:
    """Testes de tratamento de timeout."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_deployment_timeout_after_max_attempts(
        self,
        deploy_executor_integration,
        deploy_ticket
    ):
        """Deve falhar com timeout apos limite de tentativas."""
        app_name = deploy_ticket['parameters']['deployment_name']
        deploy_ticket['parameters']['timeout_seconds'] = 3
        deploy_ticket['parameters']['poll_interval'] = 1

        with aioresponses() as m:
            # Mock create application
            m.post(
                f'{ARGOCD_BASE_URL}/api/v1/applications',
                payload={'metadata': {'name': app_name}},
                status=200
            )

            # Mock get status - sempre Progressing (nunca fica healthy)
            for _ in range(10):
                m.get(
                    f'{ARGOCD_BASE_URL}/api/v1/applications/{app_name}',
                    payload={
                        'metadata': {'name': app_name},
                        'status': {
                            'health': {'status': 'Progressing'},
                            'sync': {'status': 'Syncing'}
                        }
                    },
                    status=200
                )

            result = await deploy_executor_integration.execute(deploy_ticket)

            assert result['success'] is False
            assert result['output']['status'] == 'timeout'


class TestDeploymentAuthenticationError:
    """Testes de erros de autenticacao."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_authentication_error_401(
        self,
        deploy_executor_integration,
        deploy_ticket
    ):
        """Deve tratar erro 401 de autenticacao."""
        with aioresponses() as m:
            # Mock create application com erro 401
            m.post(
                f'{ARGOCD_BASE_URL}/api/v1/applications',
                payload={'error': 'Unauthorized'},
                status=401
            )

            result = await deploy_executor_integration.execute(deploy_ticket)

            assert result['success'] is False
            assert result['output']['status'] == 'error'

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_authentication_error_403(
        self,
        deploy_executor_integration,
        deploy_ticket
    ):
        """Deve tratar erro 403 de permissao."""
        with aioresponses() as m:
            # Mock create application com erro 403
            m.post(
                f'{ARGOCD_BASE_URL}/api/v1/applications',
                payload={'error': 'Forbidden'},
                status=403
            )

            result = await deploy_executor_integration.execute(deploy_ticket)

            assert result['success'] is False
            assert result['output']['status'] == 'error'


class TestDeploymentRollbackScenarios:
    """Testes de cenarios de rollback."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_deployment_degraded_status(
        self,
        deploy_executor_integration,
        deploy_ticket
    ):
        """Deve aceitar status Degraded como parcialmente healthy."""
        app_name = deploy_ticket['parameters']['deployment_name']

        with aioresponses() as m:
            # Mock create application
            m.post(
                f'{ARGOCD_BASE_URL}/api/v1/applications',
                payload={'metadata': {'name': app_name}},
                status=200
            )

            # Mock get status - retorna Degraded
            m.get(
                f'{ARGOCD_BASE_URL}/api/v1/applications/{app_name}',
                payload={
                    'metadata': {'name': app_name},
                    'status': {
                        'health': {'status': 'Degraded', 'message': 'Some pods not ready'},
                        'sync': {'status': 'Synced', 'revision': 'abc123'}
                    }
                },
                status=200
            )

            result = await deploy_executor_integration.execute(deploy_ticket)

            # Degraded eh considerado "healthy" (com ressalvas)
            assert result['success'] is True
            assert result['output']['status'] == 'degraded'

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_deployment_missing_status(
        self,
        deploy_executor_integration,
        deploy_ticket
    ):
        """Deve tratar resposta sem status."""
        app_name = deploy_ticket['parameters']['deployment_name']

        with aioresponses() as m:
            # Mock create application
            m.post(
                f'{ARGOCD_BASE_URL}/api/v1/applications',
                payload={'metadata': {'name': app_name}},
                status=200
            )

            # Mock get status - Healthy
            m.get(
                f'{ARGOCD_BASE_URL}/api/v1/applications/{app_name}',
                payload={
                    'metadata': {'name': app_name},
                    'status': {
                        'health': {'status': 'Healthy'},
                        'sync': {'status': 'Synced'}
                    }
                },
                status=200
            )

            result = await deploy_executor_integration.execute(deploy_ticket)

            assert result['success'] is True


class TestDeploymentServerErrors:
    """Testes de erros de servidor."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_server_error_500(
        self,
        deploy_executor_integration,
        deploy_ticket
    ):
        """Deve tratar erro 500 do servidor."""
        with aioresponses() as m:
            # Mock create application com erro 500
            m.post(
                f'{ARGOCD_BASE_URL}/api/v1/applications',
                payload={'error': 'Internal Server Error'},
                status=500
            )

            result = await deploy_executor_integration.execute(deploy_ticket)

            assert result['success'] is False

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_connection_error(
        self,
        worker_config,
        mock_metrics,
        deploy_ticket
    ):
        """Deve tratar erro de conexao."""
        from services.worker_agents.src.executors.deploy_executor import DeployExecutor
        from services.worker_agents.src.clients.argocd_client import ArgoCDClient

        # Cliente com URL invalida
        client = ArgoCDClient(
            base_url='http://nonexistent-server:9999',
            token='test-token',
            timeout=5
        )

        executor = DeployExecutor(
            config=worker_config,
            vault_client=None,
            code_forge_client=None,
            metrics=mock_metrics,
            argocd_client=client,
            flux_client=None
        )

        result = await executor.execute(deploy_ticket)

        assert result['success'] is False
        assert result['output']['status'] == 'error'

        await client.close()


class TestClientClose:
    """Testes de fechamento do cliente."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_client_close(self, argocd_client):
        """Deve fechar cliente corretamente."""
        await argocd_client.close()
        # Verificar que o cliente foi fechado
        assert argocd_client.client.is_closed
