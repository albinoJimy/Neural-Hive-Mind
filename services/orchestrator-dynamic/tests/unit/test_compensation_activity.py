"""
Testes unitarios para activities de compensacao (Saga Pattern).

Nota: Os testes usam mocks para evitar dependencias circulares de imports.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
import sys


# Mock dos modulos problematicos antes de importar
sys.modules['src.clients.kafka_producer'] = MagicMock()
sys.modules['src.config.settings'] = MagicMock()


class TestGetCompensationAction:
    """Testes para funcao _get_compensation_action."""

    def test_build_action_returns_delete_artifacts(self):
        """BUILD deve retornar acao delete_artifacts."""
        # Import local para usar o mock
        from src.activities.compensation import _get_compensation_action

        params = {
            'artifact_ids': ['art-1', 'art-2'],
            'registry_url': 'https://registry.example.com',
            'repository': 'my-app'
        }

        result = _get_compensation_action('BUILD', params)

        assert result['action'] == 'delete_artifacts'
        assert result['artifact_ids'] == ['art-1', 'art-2']
        assert result['registry_url'] == 'https://registry.example.com'

    def test_deploy_action_returns_rollback_deployment(self):
        """DEPLOY deve retornar acao rollback_deployment."""
        from src.activities.compensation import _get_compensation_action

        params = {
            'deployment_name': 'my-deploy',
            'previous_revision': 'v1.0.0',
            'namespace': 'production',
            'provider': 'argocd'
        }

        result = _get_compensation_action('DEPLOY', params)

        assert result['action'] == 'rollback_deployment'
        assert result['deployment_name'] == 'my-deploy'
        assert result['previous_revision'] == 'v1.0.0'
        assert result['provider'] == 'argocd'

    def test_test_action_returns_cleanup_test_env(self):
        """TEST deve retornar acao cleanup_test_env."""
        from src.activities.compensation import _get_compensation_action

        params = {
            'test_id': 'test-123',
            'namespace': 'test-ns',
            'resources': [{'type': 'Job', 'name': 'test-job'}]
        }

        result = _get_compensation_action('TEST', params)

        assert result['action'] == 'cleanup_test_env'
        assert result['test_id'] == 'test-123'
        assert result['cleanup_jobs'] is True

    def test_validate_action_returns_revert_approval(self):
        """VALIDATE deve retornar acao revert_approval."""
        from src.activities.compensation import _get_compensation_action

        params = {
            'approval_id': 'approval-456',
            'validation_id': 'val-789'
        }

        result = _get_compensation_action('VALIDATE', params)

        assert result['action'] == 'revert_approval'
        assert result['approval_id'] == 'approval-456'

    def test_execute_action_returns_rollback_execution(self):
        """EXECUTE deve retornar acao rollback_execution."""
        from src.activities.compensation import _get_compensation_action

        params = {
            'execution_id': 'exec-101',
            'rollback_script': 'cleanup.sh'
        }

        result = _get_compensation_action('EXECUTE', params)

        assert result['action'] == 'rollback_execution'
        assert result['execution_id'] == 'exec-101'

    def test_unknown_action_returns_generic_cleanup(self):
        """Task type desconhecido deve retornar generic_cleanup."""
        from src.activities.compensation import _get_compensation_action

        params = {'custom_param': 'value'}

        result = _get_compensation_action('UNKNOWN_TYPE', params)

        assert result['action'] == 'generic_cleanup'
        assert result['original_task_type'] == 'UNKNOWN_TYPE'


class TestBuildCompensationOrder:
    """Testes para funcao build_compensation_order."""

    @pytest.mark.asyncio
    async def test_single_failed_ticket_returns_self(self):
        """Ticket falhado unico deve retornar apenas ele mesmo."""
        from src.activities.compensation import build_compensation_order

        failed_tickets = [
            {'ticket': {'ticket_id': 'ticket-1', 'status': 'FAILED', 'dependencies': []}}
        ]
        all_tickets = [
            {'ticket': {'ticket_id': 'ticket-1', 'status': 'FAILED', 'dependencies': []}}
        ]

        with patch('src.activities.compensation.activity'):
            result = await build_compensation_order(failed_tickets, all_tickets)

        assert len(result) == 1
        assert result[0]['ticket_id'] == 'ticket-1'

    @pytest.mark.asyncio
    async def test_chain_dependency_returns_reverse_order(self):
        """Cadeia A -> B -> C deve compensar na ordem C, B, A."""
        from src.activities.compensation import build_compensation_order

        # C falhou, depende de B, que depende de A
        failed_tickets = [
            {'ticket': {'ticket_id': 'ticket-c', 'status': 'FAILED', 'dependencies': ['ticket-b']}}
        ]
        all_tickets = [
            {'ticket': {'ticket_id': 'ticket-a', 'status': 'COMPLETED', 'dependencies': []}},
            {'ticket': {'ticket_id': 'ticket-b', 'status': 'COMPLETED', 'dependencies': ['ticket-a']}},
            {'ticket': {'ticket_id': 'ticket-c', 'status': 'FAILED', 'dependencies': ['ticket-b']}}
        ]

        with patch('src.activities.compensation.activity'):
            result = await build_compensation_order(failed_tickets, all_tickets)

        # Primeiro C (ultimo executado), depois B, depois A
        ticket_ids = [t['ticket_id'] for t in result]
        assert ticket_ids.index('ticket-c') < ticket_ids.index('ticket-b')
        assert ticket_ids.index('ticket-b') < ticket_ids.index('ticket-a')

    @pytest.mark.asyncio
    async def test_pending_tickets_excluded(self):
        """Tickets PENDING nao devem ser compensados."""
        from src.activities.compensation import build_compensation_order

        failed_tickets = [
            {'ticket': {'ticket_id': 'ticket-c', 'status': 'FAILED', 'dependencies': ['ticket-b']}}
        ]
        all_tickets = [
            {'ticket': {'ticket_id': 'ticket-a', 'status': 'COMPLETED', 'dependencies': []}},
            {'ticket': {'ticket_id': 'ticket-b', 'status': 'PENDING', 'dependencies': ['ticket-a']}},
            {'ticket': {'ticket_id': 'ticket-c', 'status': 'FAILED', 'dependencies': ['ticket-b']}}
        ]

        with patch('src.activities.compensation.activity'):
            result = await build_compensation_order(failed_tickets, all_tickets)

        ticket_ids = [t['ticket_id'] for t in result]
        # ticket-b nao deve estar na lista pois esta PENDING
        assert 'ticket-b' not in ticket_ids
        assert 'ticket-c' in ticket_ids
        assert 'ticket-a' in ticket_ids


class TestCompensateTicket:
    """Testes para funcao compensate_ticket."""

    @pytest.mark.asyncio
    async def test_creates_compensation_ticket_with_correct_fields(self):
        """Deve criar ticket de compensacao com campos corretos."""
        from src.activities.compensation import (
            compensate_ticket,
            set_compensation_dependencies
        )

        mock_kafka = AsyncMock()
        mock_kafka.publish_ticket = AsyncMock(return_value=True)
        mock_mongodb = AsyncMock()
        mock_metrics = MagicMock()
        mock_metrics.record_compensation = MagicMock()

        set_compensation_dependencies(
            config=MagicMock(),
            kafka_producer=mock_kafka,
            mongodb_client=mock_mongodb,
            metrics=mock_metrics
        )

        ticket = {
            'ticket_id': 'original-ticket-123',
            'task_type': 'DEPLOY',
            'plan_id': 'plan-1',
            'intent_id': 'intent-1',
            'priority': 'HIGH',
            'status': 'FAILED',
            'parameters': {
                'deployment_name': 'my-deploy',
                'namespace': 'production'
            }
        }

        with patch('src.activities.compensation.activity'):
            compensation_id = await compensate_ticket(ticket, 'workflow_inconsistent')

        assert compensation_id is not None
        assert len(compensation_id) == 36  # UUID format

        # Verificar que Kafka foi chamado
        mock_kafka.publish_ticket.assert_called_once()
        published_ticket = mock_kafka.publish_ticket.call_args[0][0]
        assert published_ticket['task_type'] == 'COMPENSATE'
        assert published_ticket['status'] == 'PENDING'
        assert published_ticket['parameters']['action'] == 'rollback_deployment'

    @pytest.mark.asyncio
    async def test_records_metric_on_compensation(self):
        """Deve registrar metrica quando compensacao e criada."""
        from src.activities.compensation import (
            compensate_ticket,
            set_compensation_dependencies
        )

        mock_metrics = MagicMock()
        mock_metrics.record_compensation = MagicMock()
        mock_kafka = AsyncMock()
        mock_kafka.publish_ticket = AsyncMock(return_value=True)

        set_compensation_dependencies(
            config=MagicMock(),
            kafka_producer=mock_kafka,
            mongodb_client=None,
            metrics=mock_metrics
        )

        ticket = {
            'ticket_id': 'ticket-123',
            'task_type': 'BUILD',
            'parameters': {}
        }

        with patch('src.activities.compensation.activity'):
            await compensate_ticket(ticket, 'task_failed')

        mock_metrics.record_compensation.assert_called_once_with(reason='task_failed')

    @pytest.mark.asyncio
    async def test_continues_without_kafka(self):
        """Deve continuar mesmo sem Kafka (fail-open)."""
        from src.activities.compensation import (
            compensate_ticket,
            set_compensation_dependencies
        )

        set_compensation_dependencies(
            config=MagicMock(),
            kafka_producer=None,
            mongodb_client=None,
            metrics=None
        )

        ticket = {
            'ticket_id': 'ticket-123',
            'task_type': 'TEST',
            'parameters': {}
        }

        with patch('src.activities.compensation.activity'):
            compensation_id = await compensate_ticket(ticket, 'workflow_inconsistent')

        # Deve retornar ID mesmo sem Kafka
        assert compensation_id is not None


class TestUpdateTicketCompensationStatus:
    """Testes para funcao update_ticket_compensation_status."""

    @pytest.mark.asyncio
    async def test_updates_mongodb_with_compensation_reference(self):
        """Deve atualizar MongoDB com referencia ao ticket de compensacao."""
        from src.activities.compensation import (
            update_ticket_compensation_status,
            set_compensation_dependencies
        )

        mock_mongodb = AsyncMock()
        mock_mongodb.update_ticket_compensation = AsyncMock()

        set_compensation_dependencies(
            config=MagicMock(),
            kafka_producer=None,
            mongodb_client=mock_mongodb,
            metrics=None
        )

        with patch('src.activities.compensation.activity'):
            result = await update_ticket_compensation_status(
                ticket_id='original-123',
                compensation_ticket_id='compensation-456'
            )

        assert result is True
        mock_mongodb.update_ticket_compensation.assert_called_once_with(
            ticket_id='original-123',
            compensation_ticket_id='compensation-456',
            status='COMPENSATING'
        )

    @pytest.mark.asyncio
    async def test_returns_false_without_mongodb(self):
        """Deve retornar False sem MongoDB."""
        from src.activities.compensation import (
            update_ticket_compensation_status,
            set_compensation_dependencies
        )

        set_compensation_dependencies(
            config=MagicMock(),
            kafka_producer=None,
            mongodb_client=None,
            metrics=None
        )

        with patch('src.activities.compensation.activity'):
            result = await update_ticket_compensation_status(
                ticket_id='original-123',
                compensation_ticket_id='compensation-456'
            )

        assert result is False
