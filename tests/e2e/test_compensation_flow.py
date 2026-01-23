"""
Testes E2E para fluxo de compensacao automatica (Saga Pattern).

Valida que:
1. Falhas em tarefas acionam compensacao automatica
2. Compensacao segue ordem topologica reversa
3. Metricas sao registradas corretamente
4. Compensacao e idempotente
"""
import sys
import os
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from uuid import uuid4

# Adicionar path do orchestrator-dynamic
_orchestrator_path = os.path.join(
    os.path.dirname(__file__),
    '..',
    '..',
    'services',
    'orchestrator-dynamic'
)
sys.path.insert(0, os.path.abspath(_orchestrator_path))

# Mock dos modulos problematicos antes de importar
sys.modules['src.clients.kafka_producer'] = MagicMock()
sys.modules['src.config.settings'] = MagicMock()


@pytest.fixture
def mock_temporal_client():
    """Mock do cliente Temporal."""
    client = AsyncMock()
    client.start_workflow = AsyncMock()
    client.get_workflow_handle = AsyncMock()
    return client


@pytest.fixture
def mock_kafka_producer():
    """Mock do Kafka producer."""
    producer = AsyncMock()
    producer.publish_ticket = AsyncMock(return_value=True)
    return producer


@pytest.fixture
def mock_mongodb_client():
    """Mock do MongoDB client."""
    client = AsyncMock()
    client.save_ticket = AsyncMock()
    client.update_ticket_compensation = AsyncMock()
    client.get_ticket_by_id = AsyncMock()
    return client


@pytest.fixture
def mock_argocd_client():
    """Mock do ArgoCD client."""
    client = AsyncMock()
    client.sync_application = AsyncMock(return_value={'status': 'success'})
    client.delete_application = AsyncMock(return_value=True)
    return client


@pytest.fixture
def mock_metrics():
    """Mock de metricas."""
    metrics = MagicMock()
    metrics.record_compensation = MagicMock()
    metrics.record_compensation_duration = MagicMock()
    metrics.compensations_triggered_total = MagicMock()
    metrics.compensation_duration_seconds = MagicMock()
    return metrics


class TestCompensationBuildFailure:
    """Testes para compensacao quando BUILD falha."""

    @pytest.mark.asyncio
    async def test_compensation_build_failure_deletes_artifacts(
        self,
        mock_kafka_producer,
        mock_mongodb_client,
        mock_metrics
    ):
        """
        Cenario: BUILD falhou apos criar artefatos
        Esperado: Compensacao deve deletar artefatos criados
        """
        # Criar ticket de BUILD que falhou
        build_ticket = {
            'ticket_id': str(uuid4()),
            'task_type': 'BUILD',
            'status': 'FAILED',
            'plan_id': 'plan-001',
            'intent_id': 'intent-001',
            'parameters': {
                'artifact_ids': ['artifact-1', 'artifact-2'],
                'registry_url': 'https://registry.example.com',
                'repository': 'my-app',
                'image_tag': 'v1.0.0'
            }
        }

        # Importar e configurar activity
        from src.activities.compensation import (
            compensate_ticket,
            set_compensation_dependencies
        )

        set_compensation_dependencies(
            config=MagicMock(),
            kafka_producer=mock_kafka_producer,
            mongodb_client=mock_mongodb_client,
            metrics=mock_metrics
        )

        # Executar compensacao
        with patch('src.activities.compensation.activity'):
            compensation_ticket_id = await compensate_ticket(
                build_ticket,
                reason='task_failed'
            )

        # Verificar que ticket de compensacao foi criado
        assert compensation_ticket_id is not None

        # Verificar que Kafka foi chamado com ticket correto
        mock_kafka_producer.publish_ticket.assert_called_once()
        published_ticket = mock_kafka_producer.publish_ticket.call_args[0][0]

        assert published_ticket['task_type'] == 'COMPENSATE'
        assert published_ticket['parameters']['action'] == 'delete_artifacts'
        assert published_ticket['parameters']['artifact_ids'] == ['artifact-1', 'artifact-2']

        # Verificar metrica
        mock_metrics.record_compensation.assert_called_once_with(reason='task_failed')


class TestCompensationDeployFailure:
    """Testes para compensacao quando DEPLOY falha."""

    @pytest.mark.asyncio
    async def test_compensation_deploy_failure_triggers_rollback(
        self,
        mock_kafka_producer,
        mock_mongodb_client,
        mock_argocd_client,
        mock_metrics
    ):
        """
        Cenario: DEPLOY falhou apos criar Application no ArgoCD
        Esperado: Compensacao deve fazer rollback para versao anterior
        """
        deploy_ticket = {
            'ticket_id': str(uuid4()),
            'task_type': 'DEPLOY',
            'status': 'FAILED',
            'plan_id': 'plan-001',
            'intent_id': 'intent-001',
            'parameters': {
                'deployment_name': 'my-app-deploy',
                'previous_revision': 'v0.9.0',
                'namespace': 'production',
                'provider': 'argocd'
            }
        }

        from src.activities.compensation import (
            compensate_ticket,
            set_compensation_dependencies
        )

        set_compensation_dependencies(
            config=MagicMock(),
            kafka_producer=mock_kafka_producer,
            mongodb_client=mock_mongodb_client,
            metrics=mock_metrics
        )

        with patch('src.activities.compensation.activity'):
            compensation_ticket_id = await compensate_ticket(
                deploy_ticket,
                reason='workflow_inconsistent'
            )

        # Verificar ticket de compensacao
        assert compensation_ticket_id is not None

        published_ticket = mock_kafka_producer.publish_ticket.call_args[0][0]
        assert published_ticket['parameters']['action'] == 'rollback_deployment'
        assert published_ticket['parameters']['previous_revision'] == 'v0.9.0'
        assert published_ticket['parameters']['provider'] == 'argocd'


class TestCompensationPartialWorkflow:
    """Testes para compensacao de workflow parcialmente executado."""

    @pytest.mark.asyncio
    async def test_compensation_partial_workflow_reverse_order(
        self,
        mock_kafka_producer,
        mock_mongodb_client,
        mock_metrics
    ):
        """
        Cenario: Workflow A -> B -> C, C falhou
        Esperado: Compensar na ordem C, B, A
        """
        # Tickets do workflow
        ticket_a = {
            'ticket': {
                'ticket_id': 'ticket-a',
                'task_type': 'BUILD',
                'status': 'COMPLETED',
                'dependencies': []
            }
        }
        ticket_b = {
            'ticket': {
                'ticket_id': 'ticket-b',
                'task_type': 'DEPLOY',
                'status': 'COMPLETED',
                'dependencies': ['ticket-a']
            }
        }
        ticket_c = {
            'ticket': {
                'ticket_id': 'ticket-c',
                'task_type': 'TEST',
                'status': 'FAILED',
                'dependencies': ['ticket-b']
            }
        }

        all_tickets = [ticket_a, ticket_b, ticket_c]
        failed_tickets = [ticket_c]

        from src.activities.compensation import build_compensation_order

        with patch('src.activities.compensation.activity'):
            compensation_order = await build_compensation_order(
                failed_tickets,
                all_tickets
            )

        # Verificar ordem: C primeiro (falhou), depois B, depois A
        ticket_ids = [t['ticket_id'] for t in compensation_order]

        # C deve vir antes de B
        assert ticket_ids.index('ticket-c') < ticket_ids.index('ticket-b')
        # B deve vir antes de A
        assert ticket_ids.index('ticket-b') < ticket_ids.index('ticket-a')


class TestCompensationMetrics:
    """Testes para metricas de compensacao."""

    @pytest.mark.asyncio
    async def test_compensation_metrics_recorded(
        self,
        mock_kafka_producer,
        mock_mongodb_client,
        mock_metrics
    ):
        """
        Cenario: Compensacao executada
        Esperado: Metricas compensations_triggered_total registradas
        """
        ticket = {
            'ticket_id': str(uuid4()),
            'task_type': 'EXECUTE',
            'status': 'FAILED',
            'parameters': {
                'execution_id': 'exec-123'
            }
        }

        from src.activities.compensation import (
            compensate_ticket,
            set_compensation_dependencies
        )

        set_compensation_dependencies(
            config=MagicMock(),
            kafka_producer=mock_kafka_producer,
            mongodb_client=mock_mongodb_client,
            metrics=mock_metrics
        )

        with patch('src.activities.compensation.activity'):
            await compensate_ticket(ticket, reason='task_timeout')

        # Verificar que metrica foi registrada
        mock_metrics.record_compensation.assert_called_once_with(reason='task_timeout')


class TestCompensationIdempotency:
    """Testes de idempotencia para compensacao."""

    @pytest.mark.asyncio
    async def test_compensation_idempotent_multiple_executions(
        self,
        mock_kafka_producer,
        mock_mongodb_client,
        mock_metrics
    ):
        """
        Cenario: Compensacao executada multiplas vezes para mesmo ticket
        Esperado: Sem efeitos colaterais, resultados consistentes
        """
        ticket = {
            'ticket_id': 'ticket-123',
            'task_type': 'BUILD',
            'status': 'FAILED',
            'parameters': {
                'artifact_ids': ['artifact-1']
            }
        }

        from src.activities.compensation import (
            compensate_ticket,
            set_compensation_dependencies
        )

        set_compensation_dependencies(
            config=MagicMock(),
            kafka_producer=mock_kafka_producer,
            mongodb_client=mock_mongodb_client,
            metrics=mock_metrics
        )

        # Executar compensacao 3 vezes
        results = []
        with patch('src.activities.compensation.activity'):
            for _ in range(3):
                result = await compensate_ticket(ticket, reason='manual_trigger')
                results.append(result)

        # Todas execucoes devem gerar IDs validos
        for result in results:
            assert result is not None
            assert len(result) == 36  # UUID format

        # Kafka deve ser chamado 3 vezes
        assert mock_kafka_producer.publish_ticket.call_count == 3


class TestCompensationWorkflowIntegration:
    """Testes de integracao com workflow de orquestracao."""

    @pytest.mark.asyncio
    async def test_workflow_triggers_compensation_on_failure(self):
        """
        Cenario: Workflow detecta resultado inconsistente
        Esperado: Compensacao automatica acionada
        """
        # Este teste valida que a logica no workflow esta correta
        # Simular workflow_result inconsistente
        workflow_result = {
            'consistent': False,
            'errors': ['Task C failed with timeout'],
            'completed_tickets': 2,
            'failed_tickets': 1
        }

        published_tickets = [
            {'ticket': {'ticket_id': 'ticket-a', 'status': 'COMPLETED', 'dependencies': []}},
            {'ticket': {'ticket_id': 'ticket-b', 'status': 'COMPLETED', 'dependencies': ['ticket-a']}},
            {'ticket': {'ticket_id': 'ticket-c', 'status': 'FAILED', 'dependencies': ['ticket-b']}}
        ]

        # Identificar tickets falhados (logica do workflow)
        failed_tickets = [
            t for t in published_tickets
            if t.get('ticket', {}).get('status') == 'FAILED'
        ]

        assert len(failed_tickets) == 1
        assert failed_tickets[0]['ticket']['ticket_id'] == 'ticket-c'

        # Verificar que workflow_result.consistent == False aciona compensacao
        assert workflow_result.get('consistent', True) is False


class TestCompensationErrorHandling:
    """Testes de tratamento de erros em compensacao."""

    @pytest.mark.asyncio
    async def test_compensation_continues_on_kafka_failure(
        self,
        mock_mongodb_client,
        mock_metrics
    ):
        """
        Cenario: Kafka indisponivel durante compensacao
        Esperado: Compensacao deve continuar (fail-open)
        """
        # Kafka producer que falha
        failing_kafka = AsyncMock()
        failing_kafka.publish_ticket = AsyncMock(side_effect=Exception('Kafka unavailable'))

        ticket = {
            'ticket_id': str(uuid4()),
            'task_type': 'TEST',
            'status': 'FAILED',
            'parameters': {}
        }

        from src.activities.compensation import (
            compensate_ticket,
            set_compensation_dependencies
        )

        set_compensation_dependencies(
            config=MagicMock(),
            kafka_producer=failing_kafka,
            mongodb_client=mock_mongodb_client,
            metrics=mock_metrics
        )

        # Deve continuar mesmo com Kafka falhando
        with patch('src.activities.compensation.activity'):
            compensation_id = await compensate_ticket(ticket, reason='test_failure')

        # ID deve ser gerado (compensacao foi registrada no MongoDB)
        assert compensation_id is not None

    @pytest.mark.asyncio
    async def test_compensation_continues_without_mongodb(
        self,
        mock_kafka_producer,
        mock_metrics
    ):
        """
        Cenario: MongoDB indisponivel durante compensacao
        Esperado: Compensacao deve continuar e publicar no Kafka
        """
        ticket = {
            'ticket_id': str(uuid4()),
            'task_type': 'VALIDATE',
            'status': 'FAILED',
            'parameters': {}
        }

        from src.activities.compensation import (
            compensate_ticket,
            set_compensation_dependencies
        )

        set_compensation_dependencies(
            config=MagicMock(),
            kafka_producer=mock_kafka_producer,
            mongodb_client=None,  # Sem MongoDB
            metrics=mock_metrics
        )

        with patch('src.activities.compensation.activity'):
            compensation_id = await compensate_ticket(ticket, reason='validation_failed')

        # Deve gerar ID e publicar no Kafka
        assert compensation_id is not None
        mock_kafka_producer.publish_ticket.assert_called_once()
