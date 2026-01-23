"""
Testes unitarios para CompensateExecutor.
"""
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# Mock do modulo de observability antes de importar
def _create_mock_tracer():
    mock_span = MagicMock()
    mock_span.__enter__ = MagicMock(return_value=mock_span)
    mock_span.__exit__ = MagicMock(return_value=False)
    mock_span.set_attribute = MagicMock()

    tracer = MagicMock()
    tracer.start_as_current_span = MagicMock(return_value=mock_span)
    return tracer


mock_tracer_module = MagicMock()
mock_tracer_module.get_tracer = MagicMock(return_value=_create_mock_tracer())
sys.modules['neural_hive_observability'] = mock_tracer_module


from src.executors.compensate_executor import CompensateExecutor


@pytest.fixture
def mock_config():
    """Configuracao mock para testes."""
    config = MagicMock()
    config.supported_task_types = ['BUILD', 'DEPLOY', 'TEST', 'VALIDATE', 'EXECUTE', 'COMPENSATE']
    return config


@pytest.fixture
def mock_metrics():
    """Metricas mock para testes."""
    metrics = MagicMock()
    metrics.compensation_duration_seconds = MagicMock()
    metrics.compensation_tasks_executed_total = MagicMock()
    return metrics


@pytest.fixture
def compensate_executor(mock_config, mock_metrics):
    """Fixture que cria CompensateExecutor para testes."""
    return CompensateExecutor(
        config=mock_config,
        vault_client=None,
        code_forge_client=None,
        metrics=mock_metrics,
        argocd_client=None,
        flux_client=None,
        k8s_jobs_client=None
    )


class TestCompensateExecutorBasic:
    """Testes basicos do CompensateExecutor."""

    def test_get_task_type_returns_compensate(self, compensate_executor):
        """Deve retornar COMPENSATE como task_type."""
        assert compensate_executor.get_task_type() == 'COMPENSATE'

    @pytest.mark.asyncio
    async def test_execute_with_unknown_action_returns_error(self, compensate_executor):
        """Deve retornar erro para action desconhecida."""
        ticket = {
            'ticket_id': 'comp-ticket-123',
            'task_id': 'task-123',
            'task_type': 'COMPENSATE',
            'parameters': {
                'action': 'unknown_action',
                'original_ticket_id': 'original-123'
            }
        }

        result = await compensate_executor.execute(ticket)

        assert result['success'] is False
        assert 'unknown_action' in result['output']['error'].lower()


class TestCompensateBuild:
    """Testes para compensacao de BUILD."""

    @pytest.mark.asyncio
    async def test_compensate_build_deletes_artifacts_simulation(self, compensate_executor):
        """Deve simular delecao de artefatos quando Code Forge nao disponivel."""
        ticket = {
            'ticket_id': 'comp-ticket-123',
            'task_id': 'task-123',
            'task_type': 'COMPENSATE',
            'parameters': {
                'action': 'delete_artifacts',
                'artifact_ids': ['artifact-1', 'artifact-2'],
                'registry_url': 'https://registry.example.com',
                'original_ticket_id': 'original-123'
            }
        }

        result = await compensate_executor.execute(ticket)

        assert result['success'] is True
        assert 'deleted_artifacts' in result['output']
        assert len(result['output']['deleted_artifacts']) == 2

    @pytest.mark.asyncio
    async def test_compensate_build_with_code_forge_client(self, mock_config, mock_metrics):
        """Deve usar Code Forge client para deletar artefatos se disponivel."""
        mock_code_forge = AsyncMock()
        mock_code_forge.delete_artifact = AsyncMock()

        executor = CompensateExecutor(
            config=mock_config,
            code_forge_client=mock_code_forge,
            metrics=mock_metrics
        )

        ticket = {
            'ticket_id': 'comp-ticket-123',
            'task_id': 'task-123',
            'task_type': 'COMPENSATE',
            'parameters': {
                'action': 'delete_artifacts',
                'artifact_ids': ['artifact-1'],
                'original_ticket_id': 'original-123'
            }
        }

        result = await executor.execute(ticket)

        assert result['success'] is True
        mock_code_forge.delete_artifact.assert_called_once_with('artifact-1')


class TestCompensateDeploy:
    """Testes para compensacao de DEPLOY."""

    @pytest.mark.asyncio
    async def test_compensate_deploy_argocd_rollback(self, mock_config, mock_metrics):
        """Deve usar ArgoCD client para rollback."""
        mock_argocd = AsyncMock()
        mock_argocd.sync_application = AsyncMock(return_value={'status': 'success'})

        executor = CompensateExecutor(
            config=mock_config,
            argocd_client=mock_argocd,
            metrics=mock_metrics
        )

        ticket = {
            'ticket_id': 'comp-ticket-123',
            'task_id': 'task-123',
            'task_type': 'COMPENSATE',
            'parameters': {
                'action': 'rollback_deployment',
                'deployment_name': 'my-app',
                'previous_revision': 'v1.0.0',
                'namespace': 'production',
                'provider': 'argocd',
                'original_ticket_id': 'original-123'
            }
        }

        result = await executor.execute(ticket)

        assert result['success'] is True
        assert result['output']['provider'] == 'argocd'
        mock_argocd.sync_application.assert_called_once_with(
            app_name='my-app',
            revision='v1.0.0',
            prune=True
        )

    @pytest.mark.asyncio
    async def test_compensate_deploy_flux_delete_kustomization(self, mock_config, mock_metrics):
        """Deve usar Flux client para deletar Kustomization."""
        mock_flux = AsyncMock()
        mock_flux.delete_kustomization = AsyncMock()

        executor = CompensateExecutor(
            config=mock_config,
            flux_client=mock_flux,
            metrics=mock_metrics
        )

        ticket = {
            'ticket_id': 'comp-ticket-123',
            'task_id': 'task-123',
            'task_type': 'COMPENSATE',
            'parameters': {
                'action': 'rollback_deployment',
                'deployment_name': 'my-app',
                'previous_revision': 'v1.0.0',
                'namespace': 'production',
                'provider': 'flux',
                'original_ticket_id': 'original-123'
            }
        }

        result = await executor.execute(ticket)

        assert result['success'] is True
        assert result['output']['provider'] == 'flux'

    @pytest.mark.asyncio
    async def test_compensate_deploy_simulation_fallback(self, compensate_executor):
        """Deve simular rollback quando nenhum provider disponivel."""
        ticket = {
            'ticket_id': 'comp-ticket-123',
            'task_id': 'task-123',
            'task_type': 'COMPENSATE',
            'parameters': {
                'action': 'rollback_deployment',
                'deployment_name': 'my-app',
                'previous_revision': 'v1.0.0',
                'namespace': 'production',
                'provider': 'argocd',
                'original_ticket_id': 'original-123'
            }
        }

        result = await compensate_executor.execute(ticket)

        assert result['success'] is True
        assert result['metadata'].get('simulated') is True


class TestCompensateTest:
    """Testes para compensacao de TEST."""

    @pytest.mark.asyncio
    async def test_compensate_test_cleanup_simulation(self, compensate_executor):
        """Deve simular cleanup de ambiente de teste."""
        ticket = {
            'ticket_id': 'comp-ticket-123',
            'task_id': 'task-123',
            'task_type': 'COMPENSATE',
            'parameters': {
                'action': 'cleanup_test_env',
                'test_id': 'test-456',
                'namespace': 'test-ns',
                'resources': [],
                'original_ticket_id': 'original-123'
            }
        }

        result = await compensate_executor.execute(ticket)

        assert result['success'] is True
        assert 'cleaned_resources' in result['output']

    @pytest.mark.asyncio
    async def test_compensate_test_with_k8s_client(self, mock_config, mock_metrics):
        """Deve usar K8s client para cleanup de Jobs."""
        mock_k8s = AsyncMock()
        mock_k8s.delete_job = AsyncMock()

        executor = CompensateExecutor(
            config=mock_config,
            k8s_jobs_client=mock_k8s,
            metrics=mock_metrics
        )

        ticket = {
            'ticket_id': 'comp-ticket-123',
            'task_id': 'task-123',
            'task_type': 'COMPENSATE',
            'parameters': {
                'action': 'cleanup_test_env',
                'test_id': 'test-456',
                'namespace': 'test-ns',
                'cleanup_jobs': True,
                'original_ticket_id': 'original-123'
            }
        }

        result = await executor.execute(ticket)

        assert result['success'] is True
        mock_k8s.delete_job.assert_called_once()


class TestCompensateValidate:
    """Testes para compensacao de VALIDATE."""

    @pytest.mark.asyncio
    async def test_compensate_validate_revert_approval(self, compensate_executor):
        """Deve reverter aprovacao para status anterior."""
        ticket = {
            'ticket_id': 'comp-ticket-123',
            'task_id': 'task-123',
            'task_type': 'COMPENSATE',
            'parameters': {
                'action': 'revert_approval',
                'approval_id': 'approval-789',
                'validation_id': 'val-123',
                'revert_status': 'PENDING',
                'original_ticket_id': 'original-123'
            }
        }

        result = await compensate_executor.execute(ticket)

        assert result['success'] is True
        assert result['output']['reverted_to_status'] == 'PENDING'


class TestCompensateExecute:
    """Testes para compensacao de EXECUTE."""

    @pytest.mark.asyncio
    async def test_compensate_execute_with_rollback_script(self, compensate_executor):
        """Deve executar script de rollback se fornecido."""
        ticket = {
            'ticket_id': 'comp-ticket-123',
            'task_id': 'task-123',
            'task_type': 'COMPENSATE',
            'parameters': {
                'action': 'rollback_execution',
                'execution_id': 'exec-101',
                'rollback_script': 'cleanup.sh',
                'working_dir': '/app',
                'original_ticket_id': 'original-123'
            }
        }

        result = await compensate_executor.execute(ticket)

        assert result['success'] is True
        assert result['output']['rollback_executed'] is True

    @pytest.mark.asyncio
    async def test_compensate_execute_without_rollback_script(self, compensate_executor):
        """Deve completar mesmo sem script de rollback."""
        ticket = {
            'ticket_id': 'comp-ticket-123',
            'task_id': 'task-123',
            'task_type': 'COMPENSATE',
            'parameters': {
                'action': 'rollback_execution',
                'execution_id': 'exec-101',
                'original_ticket_id': 'original-123'
            }
        }

        result = await compensate_executor.execute(ticket)

        assert result['success'] is True
        assert result['output']['rollback_executed'] is False


class TestCompensateMetrics:
    """Testes para metricas de compensacao."""

    @pytest.mark.asyncio
    async def test_records_duration_metric_on_success(self, compensate_executor, mock_metrics):
        """Deve registrar metrica de duracao em caso de sucesso."""
        ticket = {
            'ticket_id': 'comp-ticket-123',
            'task_id': 'task-123',
            'task_type': 'COMPENSATE',
            'parameters': {
                'action': 'generic_cleanup',
                'reason': 'workflow_inconsistent',
                'original_ticket_id': 'original-123'
            }
        }

        await compensate_executor.execute(ticket)

        mock_metrics.compensation_duration_seconds.labels.assert_called()
        mock_metrics.compensation_tasks_executed_total.labels.assert_called()

    @pytest.mark.asyncio
    async def test_records_metric_with_correct_labels(self, compensate_executor, mock_metrics):
        """Deve usar labels corretos nas metricas."""
        ticket = {
            'ticket_id': 'comp-ticket-123',
            'task_id': 'task-123',
            'task_type': 'COMPENSATE',
            'parameters': {
                'action': 'delete_artifacts',
                'reason': 'task_failed',
                'original_ticket_id': 'original-123'
            }
        }

        await compensate_executor.execute(ticket)

        # Verificar labels de duration
        duration_labels = mock_metrics.compensation_duration_seconds.labels.call_args
        assert duration_labels[1]['reason'] == 'task_failed'
        assert duration_labels[1]['status'] == 'success'

        # Verificar labels de tasks_executed
        tasks_labels = mock_metrics.compensation_tasks_executed_total.labels.call_args
        assert tasks_labels[1]['action'] == 'delete_artifacts'
        assert tasks_labels[1]['status'] == 'success'


class TestCompensateIdempotency:
    """Testes de idempotencia para compensacao."""

    @pytest.mark.asyncio
    async def test_compensation_is_idempotent(self, compensate_executor):
        """Compensacao deve ser idempotente - executar multiplas vezes sem efeitos colaterais."""
        ticket = {
            'ticket_id': 'comp-ticket-123',
            'task_id': 'task-123',
            'task_type': 'COMPENSATE',
            'parameters': {
                'action': 'delete_artifacts',
                'artifact_ids': ['artifact-1'],
                'original_ticket_id': 'original-123'
            }
        }

        # Executar multiplas vezes
        result1 = await compensate_executor.execute(ticket)
        result2 = await compensate_executor.execute(ticket)
        result3 = await compensate_executor.execute(ticket)

        # Todas devem ter sucesso
        assert result1['success'] is True
        assert result2['success'] is True
        assert result3['success'] is True

        # Resultados devem ser consistentes
        assert result1['output']['deleted_artifacts'] == result2['output']['deleted_artifacts']
        assert result2['output']['deleted_artifacts'] == result3['output']['deleted_artifacts']
