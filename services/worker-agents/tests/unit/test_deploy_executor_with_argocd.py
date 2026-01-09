"""
Testes unitarios para DeployExecutor com clientes ArgoCD e Flux.

Cobertura:
- Execucao com ArgoCD client
- Execucao com Flux client
- Fallback para simulacao
- Tratamento de erros e timeouts
- Metricas Prometheus
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import uuid


@pytest.fixture
def worker_config():
    """Configuracao do worker para testes."""
    config = MagicMock()
    config.argocd_url = 'http://argocd.test:8080'
    config.argocd_token = 'test-token'
    config.argocd_enabled = True
    config.flux_enabled = False
    config.flux_namespace = 'flux-system'
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
    metrics.flux_api_calls_total = MagicMock()
    metrics.flux_api_calls_total.labels.return_value.inc = MagicMock()
    return metrics


@pytest.fixture
def mock_argocd_client():
    """Mock para ArgoCDClient."""
    from services.worker_agents.src.clients.argocd_client import (
        ApplicationStatus,
        HealthStatus,
        SyncStatus
    )

    client = AsyncMock()
    client.create_application = AsyncMock(return_value='test-app')
    client.wait_for_health = AsyncMock(return_value=ApplicationStatus(
        name='test-app',
        health=HealthStatus(status='Healthy', message='All resources healthy'),
        sync=SyncStatus(status='Synced', revision='abc123')
    ))
    client.close = AsyncMock()
    return client


@pytest.fixture
def mock_flux_client():
    """Mock para FluxClient."""
    from services.worker_agents.src.clients.flux_client import (
        KustomizationStatus,
        Condition
    )

    client = AsyncMock()
    client.initialize = AsyncMock()
    client.create_kustomization = AsyncMock(return_value='test-kustomization')
    client.wait_for_ready = AsyncMock(return_value=KustomizationStatus(
        name='test-kustomization',
        namespace='flux-system',
        ready=True,
        conditions=[Condition(type='Ready', status='True')],
        lastAppliedRevision='main/abc123'
    ))
    client.close = AsyncMock()
    return client


@pytest.fixture
def deploy_executor_with_argocd(worker_config, mock_metrics, mock_argocd_client):
    """DeployExecutor com ArgoCD client."""
    from services.worker_agents.src.executors.deploy_executor import DeployExecutor

    return DeployExecutor(
        config=worker_config,
        vault_client=None,
        code_forge_client=None,
        metrics=mock_metrics,
        argocd_client=mock_argocd_client,
        flux_client=None
    )


@pytest.fixture
def deploy_executor_with_flux(worker_config, mock_metrics, mock_flux_client):
    """DeployExecutor com Flux client."""
    from services.worker_agents.src.executors.deploy_executor import DeployExecutor

    worker_config.flux_enabled = True
    return DeployExecutor(
        config=worker_config,
        vault_client=None,
        code_forge_client=None,
        metrics=mock_metrics,
        argocd_client=None,
        flux_client=mock_flux_client
    )


@pytest.fixture
def deploy_executor_simulation(worker_config, mock_metrics):
    """DeployExecutor sem clients (modo simulacao)."""
    from services.worker_agents.src.executors.deploy_executor import DeployExecutor

    worker_config.argocd_enabled = False
    worker_config.argocd_url = None
    return DeployExecutor(
        config=worker_config,
        vault_client=None,
        code_forge_client=None,
        metrics=mock_metrics,
        argocd_client=None,
        flux_client=None
    )


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
            'deployment_name': 'my-app',
            'image': 'my-registry/my-app:v1.0.0',
            'replicas': 3,
            'repo_url': 'https://github.com/org/repo',
            'chart_path': 'charts/my-app',
            'revision': 'main',
            'provider': 'argocd'
        }
    }


@pytest.fixture
def flux_deploy_ticket():
    """Ticket de deploy Flux para testes."""
    ticket_id = str(uuid.uuid4())
    return {
        'ticket_id': ticket_id,
        'task_id': f'task-{ticket_id[:8]}',
        'task_type': 'DEPLOY',
        'parameters': {
            'namespace': 'production',
            'deployment_name': 'my-app',
            'provider': 'flux',
            'source_name': 'my-git-repo',
            'path': './deploy/production',
            'interval': '5m'
        }
    }


class TestDeployExecutorWithArgoCD:
    """Testes do DeployExecutor com cliente ArgoCD."""

    @pytest.mark.asyncio
    async def test_execute_argocd_success(
        self,
        deploy_executor_with_argocd,
        deploy_ticket,
        mock_argocd_client
    ):
        """Deve executar deploy via ArgoCD com sucesso."""
        result = await deploy_executor_with_argocd.execute(deploy_ticket)

        assert result['success'] is True
        assert result['output']['deployment_id'] == 'test-app'
        assert result['output']['status'] == 'healthy'
        assert result['metadata']['provider'] == 'argocd'
        assert result['metadata']['simulated'] is False

        mock_argocd_client.create_application.assert_called_once()
        mock_argocd_client.wait_for_health.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_argocd_timeout(
        self,
        deploy_executor_with_argocd,
        deploy_ticket,
        mock_argocd_client
    ):
        """Deve tratar timeout do ArgoCD."""
        from services.worker_agents.src.clients.argocd_client import ArgoCDTimeoutError

        mock_argocd_client.wait_for_health.side_effect = ArgoCDTimeoutError('Timeout')

        result = await deploy_executor_with_argocd.execute(deploy_ticket)

        assert result['success'] is False
        assert result['output']['status'] == 'timeout'
        assert result['metadata']['provider'] == 'argocd'

    @pytest.mark.asyncio
    async def test_execute_argocd_api_error(
        self,
        deploy_executor_with_argocd,
        deploy_ticket,
        mock_argocd_client
    ):
        """Deve tratar erro de API do ArgoCD."""
        from services.worker_agents.src.clients.argocd_client import ArgoCDAPIError

        mock_argocd_client.create_application.side_effect = ArgoCDAPIError(
            'Conflict: application already exists',
            status_code=409
        )

        result = await deploy_executor_with_argocd.execute(deploy_ticket)

        assert result['success'] is False
        assert result['output']['status'] == 'error'
        assert result['metadata']['error_code'] == 409

    @pytest.mark.asyncio
    async def test_execute_argocd_metrics_recorded(
        self,
        deploy_executor_with_argocd,
        deploy_ticket,
        mock_metrics
    ):
        """Deve registrar metricas Prometheus."""
        await deploy_executor_with_argocd.execute(deploy_ticket)

        mock_metrics.deploy_tasks_executed_total.labels.assert_called_with(status='success')
        mock_metrics.deploy_duration_seconds.labels.assert_called()
        mock_metrics.argocd_api_calls_total.labels.assert_called()


class TestDeployExecutorWithFlux:
    """Testes do DeployExecutor com cliente Flux."""

    @pytest.mark.asyncio
    async def test_execute_flux_success(
        self,
        deploy_executor_with_flux,
        flux_deploy_ticket,
        mock_flux_client
    ):
        """Deve executar deploy via Flux com sucesso."""
        result = await deploy_executor_with_flux.execute(flux_deploy_ticket)

        assert result['success'] is True
        assert result['output']['deployment_id'] == 'test-kustomization'
        assert result['output']['status'] == 'ready'
        assert result['metadata']['provider'] == 'flux'
        assert result['metadata']['simulated'] is False

        mock_flux_client.create_kustomization.assert_called_once()
        mock_flux_client.wait_for_ready.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_flux_timeout(
        self,
        deploy_executor_with_flux,
        flux_deploy_ticket,
        mock_flux_client
    ):
        """Deve tratar timeout do Flux."""
        from services.worker_agents.src.clients.flux_client import FluxTimeoutError

        mock_flux_client.wait_for_ready.side_effect = FluxTimeoutError('Timeout')

        result = await deploy_executor_with_flux.execute(flux_deploy_ticket)

        assert result['success'] is False
        assert result['output']['status'] == 'timeout'
        assert result['metadata']['provider'] == 'flux'

    @pytest.mark.asyncio
    async def test_execute_flux_api_error(
        self,
        deploy_executor_with_flux,
        flux_deploy_ticket,
        mock_flux_client
    ):
        """Deve tratar erro de API do Flux."""
        from services.worker_agents.src.clients.flux_client import FluxAPIError

        mock_flux_client.create_kustomization.side_effect = FluxAPIError(
            'Kustomization validation failed',
            status_code=422
        )

        result = await deploy_executor_with_flux.execute(flux_deploy_ticket)

        assert result['success'] is False
        assert result['output']['status'] == 'error'
        assert result['metadata']['error_code'] == 422


class TestDeployExecutorSimulation:
    """Testes do DeployExecutor em modo simulacao."""

    @pytest.mark.asyncio
    async def test_execute_simulation_no_clients(
        self,
        deploy_executor_simulation,
        deploy_ticket
    ):
        """Deve executar simulacao quando sem clients."""
        with patch('asyncio.sleep', new_callable=AsyncMock):
            result = await deploy_executor_simulation.execute(deploy_ticket)

        assert result['success'] is True
        assert result['metadata']['simulated'] is True
        assert result['metadata']['provider'] == 'simulation'
        assert 'stub-deploy' in result['output']['deployment_id']

    @pytest.mark.asyncio
    async def test_execute_simulation_metrics(
        self,
        deploy_executor_simulation,
        deploy_ticket,
        mock_metrics
    ):
        """Deve registrar metricas na simulacao."""
        deploy_executor_simulation.metrics = mock_metrics

        with patch('asyncio.sleep', new_callable=AsyncMock):
            await deploy_executor_simulation.execute(deploy_ticket)

        mock_metrics.deploy_tasks_executed_total.labels.assert_called_with(status='success')
        mock_metrics.deploy_duration_seconds.labels.assert_called_with(stage='simulated')


class TestDeployExecutorProviderSelection:
    """Testes de selecao de provider."""

    @pytest.mark.asyncio
    async def test_provider_argocd_selected(
        self,
        deploy_executor_with_argocd,
        deploy_ticket
    ):
        """Deve usar ArgoCD quando provider=argocd."""
        deploy_ticket['parameters']['provider'] = 'argocd'

        result = await deploy_executor_with_argocd.execute(deploy_ticket)

        assert result['metadata']['provider'] == 'argocd'

    @pytest.mark.asyncio
    async def test_provider_flux_selected(
        self,
        deploy_executor_with_flux,
        flux_deploy_ticket
    ):
        """Deve usar Flux quando provider=flux."""
        result = await deploy_executor_with_flux.execute(flux_deploy_ticket)

        assert result['metadata']['provider'] == 'flux'

    @pytest.mark.asyncio
    async def test_fallback_to_legacy_argocd(
        self,
        worker_config,
        mock_metrics,
        deploy_ticket
    ):
        """Deve usar ArgoCD legado quando sem client mas URL configurada."""
        from services.worker_agents.src.executors.deploy_executor import DeployExecutor

        executor = DeployExecutor(
            config=worker_config,
            vault_client=None,
            code_forge_client=None,
            metrics=mock_metrics,
            argocd_client=None,  # Sem client dedicado
            flux_client=None
        )

        # Provider argocd mas sem client, deve cair no legado
        deploy_ticket['parameters']['provider'] = 'argocd'

        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {
                'status': {'health': {'status': 'Healthy'}}
            }
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await executor.execute(deploy_ticket)

            assert result['metadata']['provider'] == 'argocd_legacy'


class TestDeployExecutorValidation:
    """Testes de validacao de tickets."""

    @pytest.mark.asyncio
    async def test_validate_ticket_missing_ticket_id(
        self,
        deploy_executor_with_argocd
    ):
        """Deve validar ticket sem ticket_id."""
        invalid_ticket = {
            'parameters': {}
        }

        with pytest.raises(ValueError):
            await deploy_executor_with_argocd.execute(invalid_ticket)


class TestDeployExecutorTaskType:
    """Testes de tipo de tarefa."""

    def test_get_task_type(self, deploy_executor_with_argocd):
        """Deve retornar DEPLOY como task_type."""
        assert deploy_executor_with_argocd.get_task_type() == 'DEPLOY'
