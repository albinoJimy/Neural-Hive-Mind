"""
Unit tests for ParallelExecutor.

Testa execução paralela de tickets, filas de prioridade, batch processing
e coordenação de dependências.
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))

from engine.parallel_executor import (
    ParallelExecutor,
    ParallelExecutionConfig,
    TaskPriority,
    TicketWrapper,
    execute_parallel_tickets
)


@pytest.fixture
def mock_execution_engine():
    """Mock ExecutionEngine."""
    engine = AsyncMock()
    engine.process_ticket = AsyncMock()
    return engine


@pytest.fixture
def mock_metrics():
    """Mock metrics."""
    metrics = MagicMock()
    metrics.parallel_tickets_submitted_total = MagicMock()
    metrics.parallel_tickets_submitted_total.labels = MagicMock(return_value=MagicMock(inc=MagicMock()))
    metrics.parallel_ticket_duration_seconds = MagicMock()
    metrics.parallel_ticket_duration_seconds.labels = MagicMock(return_value=MagicMock(observe=MagicMock()))
    metrics.parallel_tickets_failed_total = MagicMock()
    metrics.parallel_tickets_failed_total.labels = MagicMock(return_value=MagicMock(inc=MagicMock()))
    metrics.parallel_batch_duration_seconds = MagicMock()
    metrics.parallel_batch_duration_seconds.observe = MagicMock()
    return metrics


@pytest.fixture
def parallel_config():
    """Configuração padrão para testes."""
    return ParallelExecutionConfig(
        max_parallel_tasks=5,
        enable_batching=True,
        batch_size=3,
        batch_timeout_seconds=0.5,
        enable_priority_queue=True
    )


class TestParallelExecutorInit:
    """Testes de inicialização do ParallelExecutor."""

    def test_init_default_config(self, mock_execution_engine):
        """Testa inicialização com configuração padrão."""
        config = ParallelExecutionConfig()
        executor = ParallelExecutor(config, mock_execution_engine)

        assert executor.config == config
        assert executor.execution_engine == mock_execution_engine
        assert len(executor.queues) == len(TaskPriority)
        assert executor.active_by_type == {}
        assert executor.active_tasks == {}
        assert not executor._running

    def test_init_with_custom_config(self, mock_execution_engine):
        """Testa inicialização com configuração customizada."""
        config = ParallelExecutionConfig(
            max_parallel_tasks=20,
            max_parallel_by_type={'BUILD': 5, 'DEPLOY': 3},
            enable_batching=False
        )
        executor = ParallelExecutor(config, mock_execution_engine)

        assert executor.config.max_parallel_tasks == 20
        assert 'BUILD' in executor.config.max_parallel_by_type
        assert not executor.config.enable_batching

    def test_type_semaphore_creation(self, parallel_config, mock_execution_engine):
        """Testa criação de semaphores por task_type."""
        executor = ParallelExecutor(parallel_config, mock_execution_engine, None)

        semaphore = executor.get_type_semaphore('BUILD')
        assert semaphore is not None
        assert semaphore._value == parallel_config.max_parallel_tasks

        # Deve retornar o mesmo semaphore em chamadas subsequentes
        same_semaphore = executor.get_type_semaphore('BUILD')
        assert semaphore is same_semaphore

    def test_type_semaphore_custom_limit(self, mock_execution_engine):
        """Testa semaphore com limite customizado por tipo."""
        config = ParallelExecutionConfig(
            max_parallel_tasks=10,
            max_parallel_by_type={'BUILD': 2, 'DEPLOY': 1}
        )
        executor = ParallelExecutor(config, mock_execution_engine, None)

        build_semaphore = executor.get_type_semaphore('BUILD')
        assert build_semaphore._value == 2

        deploy_semaphore = executor.get_type_semaphore('DEPLOY')
        assert deploy_semaphore._value == 1

        # Outros tipos usam o padrão
        test_semaphore = executor.get_type_semaphore('TEST')
        assert test_semaphore._value == 10


class TestSubmitTicket:
    """Testes de submissão de tickets."""

    @pytest.mark.asyncio
    async def test_submit_ticket_default_priority(self, parallel_config, mock_execution_engine):
        """Testa submissão com prioridade padrão."""
        executor = ParallelExecutor(parallel_config, mock_execution_engine)

        ticket = {
            'ticket_id': 'test-1',
            'task_id': 'task-1',
            'task_type': 'BUILD',
            'parameters': {}
        }

        correlation_id = await executor.submit_ticket(ticket)

        assert correlation_id is not None
        assert len(correlation_id) > 0

        # Verificar que foi adicionado à fila correta
        queue = executor.queues[TaskPriority.MEDIUM]
        assert not queue.empty()

    @pytest.mark.asyncio
    async def test_submit_ticket_with_priority(self, parallel_config, mock_execution_engine):
        """Testa submissão com prioridade específica."""
        executor = ParallelExecutor(parallel_config, mock_execution_engine)

        ticket = {
            'ticket_id': 'test-1',
            'task_id': 'task-1',
            'task_type': 'BUILD',
            'parameters': {}
        }

        await executor.submit_ticket(ticket, priority=TaskPriority.CRITICAL)

        # Verificar que foi adicionado à fila CRITICAL
        queue = executor.queues[TaskPriority.CRITICAL]
        assert not queue.empty()

    @pytest.mark.asyncio
    async def test_submit_ticket_with_dependencies(self, parallel_config, mock_execution_engine):
        """Testa submissão com dependências."""
        executor = ParallelExecutor(parallel_config, mock_execution_engine)

        ticket = {
            'ticket_id': 'test-1',
            'task_id': 'task-1',
            'task_type': 'BUILD',
            'parameters': {}
        }

        dependencies = {'dep-1', 'dep-2'}
        correlation_id = await executor.submit_ticket(
            ticket,
            dependencies=dependencies
        )

        # Recuperar da fila para verificar
        queue = executor.queues[TaskPriority.MEDIUM]
        wrapper = await queue.get()

        assert wrapper.dependencies == dependencies

    @pytest.mark.asyncio
    async def test_submit_ticket_disabled_priority(self, mock_execution_engine):
        """Testa submissão com fila de prioridade desabilitada."""
        config = ParallelExecutionConfig(enable_priority_queue=False)
        executor = ParallelExecutor(config, mock_execution_engine)

        ticket = {
            'ticket_id': 'test-1',
            'task_id': 'task-1',
            'task_type': 'BUILD',
            'parameters': {}
        }

        await executor.submit_ticket(ticket, priority=TaskPriority.CRITICAL)

        # Deve ir para fila MEDIUM quando priority queue desabilitada
        queue = executor.queues[TaskPriority.MEDIUM]
        assert not queue.empty()

        queue_critical = executor.queues[TaskPriority.CRITICAL]
        assert queue_critical.empty()


class TestSubmitBatch:
    """Testes de submissão em lote."""

    @pytest.mark.asyncio
    async def test_submit_batch_tickets(self, parallel_config, mock_execution_engine):
        """Testa submissão de múltiplos tickets."""
        executor = ParallelExecutor(parallel_config, mock_execution_engine)

        tickets = [
            {
                'ticket_id': f'test-{i}',
                'task_id': f'task-{i}',
                'task_type': 'BUILD',
                'parameters': {}
            }
            for i in range(5)
        ]

        correlation_ids = await executor.submit_batch(tickets)

        assert len(correlation_ids) == 5
        assert all(cid is not None for cid in correlation_ids)

    @pytest.mark.asyncio
    async def test_submit_batch_grouped_by_type(self, parallel_config, mock_execution_engine):
        """Testa que tickets são agrupados por tipo quando batching habilitado."""
        executor = ParallelExecutor(parallel_config, mock_execution_engine)

        tickets = [
            {'ticket_id': 'b1', 'task_type': 'BUILD', 'parameters': {}},
            {'ticket_id': 'b2', 'task_type': 'BUILD', 'parameters': {}},
            {'ticket_id': 'd1', 'task_type': 'DEPLOY', 'parameters': {}},
        ]

        correlation_ids = await executor.submit_batch(tickets)

        assert len(correlation_ids) == 3

        # Verificar contador das filas
        medium_queue = executor.queues[TaskPriority.MEDIUM]
        size = medium_queue.qsize()
        assert size == 3

    @pytest.mark.asyncio
    async def test_submit_batch_no_batching(self, mock_execution_engine):
        """Testa submissão em lote com batching desabilitado."""
        config = ParallelExecutionConfig(enable_batching=False)
        executor = ParallelExecutor(config, mock_execution_engine)

        tickets = [
            {'ticket_id': f'test-{i}', 'task_type': 'BUILD', 'parameters': {}}
            for i in range(3)
        ]

        correlation_ids = await executor.submit_batch(tickets)

        assert len(correlation_ids) == 3


class TestExecuteParallelIndependent:
    """Testes de execução paralela de tickets independentes."""

    @pytest.mark.asyncio
    async def test_execute_empty_list(self, parallel_config, mock_execution_engine):
        """Testa execução de lista vazia."""
        executor = ParallelExecutor(parallel_config, mock_execution_engine)

        results = await executor.execute_parallel_independent([])

        assert results == []

    @pytest.mark.asyncio
    async def test_execute_single_ticket(self, parallel_config, mock_execution_engine):
        """Testa execução de único ticket."""
        executor = ParallelExecutor(parallel_config, mock_execution_engine)

        ticket = {
            'ticket_id': 'test-1',
            'task_type': 'BUILD',
            'parameters': {}
        }

        results = await executor.execute_parallel_independent([ticket])

        assert len(results) == 1
        assert results[0]['ticket_id'] == 'test-1'
        assert results[0]['success'] is True
        mock_execution_engine.process_ticket.assert_called_once_with(ticket)

    @pytest.mark.asyncio
    async def test_execute_multiple_tickets(self, parallel_config, mock_execution_engine):
        """Testa execução de múltiplos tickets em paralelo."""
        executor = ParallelExecutor(parallel_config, mock_execution_engine)

        tickets = [
            {'ticket_id': f'test-{i}', 'task_type': 'BUILD', 'parameters': {}}
            for i in range(5)
        ]

        results = await executor.execute_parallel_independent(tickets)

        assert len(results) == 5
        assert all(r['success'] for r in results)

        # Verificar que todos foram processados
        assert mock_execution_engine.process_ticket.call_count == 5

    @pytest.mark.asyncio
    async def test_execute_with_failure(self, parallel_config, mock_execution_engine):
        """Testa execução com falha em um ticket."""
        executor = ParallelExecutor(parallel_config, mock_execution_engine)

        # Configurar mock para falhar em um ticket específico
        async def failing_process(ticket):
            if ticket['ticket_id'] == 'test-fail':
                raise ValueError('Simulated failure')
            return None

        mock_execution_engine.process_ticket = AsyncMock(side_effect=failing_process)

        tickets = [
            {'ticket_id': 'test-1', 'task_type': 'BUILD', 'parameters': {}},
            {'ticket_id': 'test-fail', 'task_type': 'BUILD', 'parameters': {}},
            {'ticket_id': 'test-2', 'task_type': 'BUILD', 'parameters': {}},
        ]

        results = await executor.execute_parallel_independent(tickets)

        assert len(results) == 3
        assert results[0]['success'] is True
        assert results[1]['success'] is False
        assert results[1]['error'] == 'Simulated failure'
        assert results[2]['success'] is True

    @pytest.mark.asyncio
    async def test_execute_with_timeout(self, parallel_config, mock_execution_engine):
        """Testa execução com timeout."""
        executor = ParallelExecutor(parallel_config, mock_execution_engine)

        # Configurar mock para ser lento
        async def slow_process(ticket):
            await asyncio.sleep(10)
            return None

        mock_execution_engine.process_ticket = AsyncMock(side_effect=slow_process)

        tickets = [
            {'ticket_id': 'test-1', 'task_type': 'BUILD', 'parameters': {}}
        ]

        results = await executor.execute_parallel_independent(
            tickets,
            timeout_seconds=0.1
        )

        assert len(results) == 1
        assert results[0]['success'] is False
        assert results[0]['error'] == 'Timeout'


class TestExecuteWithDependencies:
    """Testes de execução com dependências."""

    @pytest.mark.asyncio
    async def test_execute_empty_dependencies(self, parallel_config, mock_execution_engine):
        """Testa execução sem dependências."""
        executor = ParallelExecutor(parallel_config, mock_execution_engine)

        tickets = [
            {'ticket_id': f'test-{i}', 'task_type': 'BUILD', 'parameters': {}}
            for i in range(3)
        ]
        dependency_graph = {}

        results = await executor.execute_with_dependencies(tickets, dependency_graph)

        assert len(results) == 3
        assert all(r['success'] for r in results)

    @pytest.mark.asyncio
    async def test_execute_with_simple_dependencies(self, parallel_config, mock_execution_engine):
        """Testa execução com dependências simples (sequencial)."""
        executor = ParallelExecutor(parallel_config, mock_execution_engine)

        tickets = [
            {'ticket_id': 'test-1', 'task_type': 'BUILD', 'parameters': {}},
            {'ticket_id': 'test-2', 'task_type': 'BUILD', 'parameters': {}},
            {'ticket_id': 'test-3', 'task_type': 'BUILD', 'parameters': {}},
        ]
        dependency_graph = {
            'test-1': [],
            'test-2': ['test-1'],  # depende de test-1
            'test-3': ['test-2'],  # depende de test-2
        }

        results = await executor.execute_with_dependencies(tickets, dependency_graph)

        assert len(results) == 3

        # Verificar ordem de execução
        call_order = [
            call[0][0]['ticket_id']
            for call in mock_execution_engine.process_ticket.call_args_list
        ]

        # test-1 deve vir antes de test-2
        assert call_order.index('test-1') < call_order.index('test-2')
        # test-2 deve vir antes de test-3
        assert call_order.index('test-2') < call_order.index('test-3')

    @pytest.mark.asyncio
    async def test_execute_with_parallel_dependencies(self, parallel_config, mock_execution_engine):
        """Testa execução com dependências paralelas."""
        executor = ParallelExecutor(parallel_config, mock_execution_engine)

        tickets = [
            {'ticket_id': 'base', 'task_type': 'BUILD', 'parameters': {}},
            {'ticket_id': 'dep-1', 'task_type': 'BUILD', 'parameters': {}},
            {'ticket_id': 'dep-2', 'task_type': 'BUILD', 'parameters': {}},
            {'ticket_id': 'final', 'task_type': 'BUILD', 'parameters': {}},
        ]
        dependency_graph = {
            'base': [],
            'dep-1': ['base'],
            'dep-2': ['base'],
            'final': ['dep-1', 'dep-2'],
        }

        results = await executor.execute_with_dependencies(tickets, dependency_graph)

        assert len(results) == 4
        assert all(r['success'] for r in results)

    @pytest.mark.asyncio
    async def test_execute_with_failed_dependency(self, parallel_config, mock_execution_engine):
        """Testa execução quando dependência falha."""
        executor = ParallelExecutor(parallel_config, mock_execution_engine)

        async def failing_process(ticket):
            if ticket['ticket_id'] == 'base':
                raise ValueError('Base failed')
            return None

        mock_execution_engine.process_ticket = AsyncMock(side_effect=failing_process)

        tickets = [
            {'ticket_id': 'base', 'task_type': 'BUILD', 'parameters': {}},
            {'ticket_id': 'dep', 'task_type': 'BUILD', 'parameters': {}},
        ]
        dependency_graph = {
            'base': [],
            'dep': ['base'],
        }

        results = await executor.execute_with_dependencies(tickets, dependency_graph)

        assert len(results) == 2
        # Base falha, dep nunca executa
        assert results[0]['success'] is False


class TestGetStatus:
    """Testes de status do executor."""

    def test_get_status_initial(self, parallel_config, mock_execution_engine):
        """Testa status inicial."""
        executor = ParallelExecutor(parallel_config, mock_execution_engine)

        status = executor.get_status()

        assert status['running'] is False
        assert status['active_tasks'] == 0
        assert status['active_by_type'] == {}
        assert 'queue_sizes' in status
        assert status['processor_tasks'] == 0

    @pytest.mark.asyncio
    async def test_get_status_with_tickets(self, parallel_config, mock_execution_engine):
        """Testa status com tickets nas filas."""
        executor = ParallelExecutor(parallel_config, mock_execution_engine)

        # Adicionar tickets às filas
        ticket = {'ticket_id': 'test-1', 'task_type': 'BUILD', 'parameters': {}}
        await executor.submit_ticket(ticket, TaskPriority.HIGH)

        status = executor.get_status()

        assert 'queue_sizes' in status
        assert 'HIGH' in status['queue_sizes']


class TestConvenienceFunction:
    """Testes da função de conveniência execute_parallel_tickets."""

    @pytest.mark.asyncio
    async def test_convenience_function(self, mock_execution_engine):
        """Testa função de conveniência."""
        tickets = [
            {'ticket_id': f'test-{i}', 'task_type': 'BUILD', 'parameters': {}}
            for i in range(3)
        ]

        results = await execute_parallel_tickets(
            tickets,
            mock_execution_engine,
            max_parallel=5
        )

        assert len(results) == 3
        assert all(r['success'] for r in results)


class TestTicketWrapper:
    """Testes do TicketWrapper."""

    def test_ticket_wrapper_properties(self):
        """Testa propriedades do wrapper."""
        ticket = {
            'ticket_id': 'test-123',
            'task_type': 'BUILD',
            'parameters': {}
        }

        wrapper = TicketWrapper(ticket=ticket)

        assert wrapper.ticket_id == 'test-123'
        assert wrapper.task_type == 'BUILD'
        assert wrapper.priority == TaskPriority.MEDIUM
        assert wrapper.submitted_at > 0
        assert len(wrapper.correlation_id) > 0

    def test_ticket_wrapper_with_custom_fields(self):
        """Testa wrapper com campos customizados."""
        ticket = {
            'ticket_id': 'test-456',
            'task_type': 'DEPLOY',
            'parameters': {}
        }

        wrapper = TicketWrapper(
            ticket=ticket,
            priority=TaskPriority.CRITICAL,
            dependencies={'dep-1'}
        )

        assert wrapper.priority == TaskPriority.CRITICAL
        assert wrapper.dependencies == {'dep-1'}


@pytest.mark.asyncio
class TestParallelExecutorLifecycle:
    """Testes de ciclo de vida do executor."""

    async def test_start_and_stop(self, parallel_config, mock_execution_engine):
        """Testa iniciar e parar executor."""
        executor = ParallelExecutor(parallel_config, mock_execution_engine)

        assert not executor._running

        await executor.start(num_workers=2)

        assert executor._running
        assert len(executor._processor_tasks) == 2

        await executor.stop()

        assert not executor._running

    async def test_stop_timeout(self, parallel_config, mock_execution_engine):
        """Testa parar com timeout."""
        executor = ParallelExecutor(parallel_config, mock_execution_engine)

        await executor.start(num_workers=1)

        # Definir um timeout curto
        await executor.stop(timeout_seconds=0.1)

        assert not executor._running
