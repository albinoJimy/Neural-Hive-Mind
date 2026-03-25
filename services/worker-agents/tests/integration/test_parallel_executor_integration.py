"""
Integration tests for ParallelExecutor with real ExecutionEngine.

Testa execução paralela usando executores reais do Worker Agents.
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))

from engine.parallel_executor import (
    ParallelExecutor,
    ParallelExecutionConfig,
    TaskPriority
)
from engine.execution_engine import ExecutionEngine
from engine.dependency_coordinator import DependencyCoordinator
from executors.registry import TaskExecutorRegistry
from executors.base_executor import BaseTaskExecutor


class MockExecutor(BaseTaskExecutor):
    """Executor mock para testes."""

    def __init__(self, config, **kwargs):
        super().__init__(config, **kwargs)
        self.executed_tickets = []

    async def execute(self, ticket):
        # Simular processamento
        await asyncio.sleep(0.01)
        self.executed_tickets.append(ticket)
        return {
            'success': True,
            'output': {'ticket_id': ticket.get('ticket_id')},
            'metadata': {},
            'logs': ['Executed successfully']
        }

    def get_task_type(self):
        return 'MOCK'


@pytest.fixture
async def execution_engine():
    """Cria ExecutionEngine com mock executor."""
    config = MagicMock()
    config.max_retries_per_ticket = 3
    config.task_timeout_multiplier = 1.5
    config.max_concurrent_tasks = 10

    # Criar registry
    registry = TaskExecutorRegistry(config)

    # Adicionar mock executor
    mock_exec = MockExecutor(config)
    registry.register_executor(mock_exec)

    # Mock clients
    ticket_client = AsyncMock()
    ticket_client.update_ticket_status = AsyncMock()
    ticket_client.get_ticket = AsyncMock(return_value={'status': 'PENDING'})

    result_producer = AsyncMock()
    result_producer.publish_result = AsyncMock()

    dependency_coordinator = DependencyCoordinator(config, ticket_client)

    engine = ExecutionEngine(
        config,
        ticket_client,
        result_producer,
        dependency_coordinator,
        registry
    )

    yield engine

    # Cleanup
    await engine.shutdown()


@pytest.fixture
def parallel_config():
    """Configuração para testes de integração."""
    return ParallelExecutionConfig(
        max_parallel_tasks=3,
        enable_batching=True,
        batch_size=2,
        batch_timeout_seconds=0.1,
        enable_priority_queue=True
    )


class TestParallelExecutorIntegration:
    """Testes de integração do ParallelExecutor."""

    @pytest.mark.asyncio
    async def test_execute_parallel_with_real_engine(self, parallel_config, execution_engine):
        """Testa execução paralela com ExecutionEngine real."""
        executor = ParallelExecutor(parallel_config, execution_engine)

        tickets = [
            {
                'ticket_id': f'parallel-{i}',
                'task_id': f'task-{i}',
                'task_type': 'MOCK',
                'parameters': {}
            }
            for i in range(5)
        ]

        results = await executor.execute_parallel_independent(tickets)

        assert len(results) == 5
        assert all(r['success'] for r in results)

    @pytest.mark.asyncio
    async def test_execute_with_dependencies_complex(self, parallel_config, execution_engine):
        """Testa execução com grafo de dependências complexo."""
        executor = ParallelExecutor(parallel_config, execution_engine)

        tickets = [
            {'ticket_id': 'base', 'task_type': 'MOCK', 'parameters': {}},
            {'ticket_id': 'a1', 'task_type': 'MOCK', 'parameters': {}},
            {'ticket_id': 'a2', 'task_type': 'MOCK', 'parameters': {}},
            {'ticket_id': 'b1', 'task_type': 'MOCK', 'parameters': {}},
            {'ticket_id': 'final', 'task_type': 'MOCK', 'parameters': {}},
        ]

        dependency_graph = {
            'base': [],
            'a1': ['base'],
            'a2': ['base'],
            'b1': ['a1', 'a2'],
            'final': ['b1'],
        }

        results = await executor.execute_with_dependencies(tickets, dependency_graph)

        assert len(results) == 5
        successful = sum(1 for r in results if r['success'])
        assert successful >= 3  # Pelo menos os independentes

    @pytest.mark.asyncio
    async def test_start_stop_processors(self, parallel_config, execution_engine):
        """Testa ciclo de vida dos processor workers."""
        executor = ParallelExecutor(parallel_config, execution_engine)

        # Submeter tickets
        for i in range(3):
            ticket = {
                'ticket_id': f'proc-{i}',
                'task_type': 'MOCK',
                'parameters': {}
            }
            await executor.submit_ticket(ticket, TaskPriority.HIGH)

        # Iniciar processadores
        await executor.start(num_workers=2)

        # Aguardar processamento
        await asyncio.sleep(0.5)

        # Verificar status
        status = executor.get_status()
        assert status['running'] is True
        assert status['processor_tasks'] == 2

        # Parar
        await executor.stop(timeout_seconds=2)

        status = executor.get_status()
        assert status['running'] is False

    @pytest.mark.asyncio
    async def test_priority_ordering(self, parallel_config, execution_engine):
        """Testa que tickets de maior prioridade são processados primeiro."""
        executor = ParallelExecutor(parallel_config, execution_engine)

        # Submeter tickets em ordem inversa de prioridade
        tickets = [
            ('low-1', TaskPriority.LOW),
            ('critical-1', TaskPriority.CRITICAL),
            ('medium-1', TaskPriority.MEDIUM),
            ('high-1', TaskPriority.HIGH),
            ('low-2', TaskPriority.LOW),
        ]

        for ticket_id, priority in tickets:
            ticket = {
                'ticket_id': ticket_id,
                'task_type': 'MOCK',
                'parameters': {}
            }
            await executor.submit_ticket(ticket, priority)

        # Iniciar e aguardar processamento
        await executor.start(num_workers=1)

        # Aguardar um pouco
        await asyncio.sleep(0.3)

        await executor.stop(timeout_seconds=1)

    @pytest.mark.asyncio
    async def test_concurrent_limit_by_type(self, execution_engine):
        """Testa limite de concorrência por tipo."""
        config = ParallelExecutionConfig(
            max_parallel_tasks=10,
            max_parallel_by_type={'MOCK': 2},
            enable_priority_queue=False
        )
        executor = ParallelExecutor(config, execution_engine)

        tickets = [
            {
                'ticket_id': f'limit-{i}',
                'task_type': 'MOCK',
                'parameters': {}
            }
            for i in range(5)
        ]

        start_time = asyncio.get_event_loop().time()
        results = await executor.execute_parallel_independent(tickets)
        duration = asyncio.get_event_loop().time() - start_time

        assert len(results) == 5
        # Com limite de 2, deve levar pelo menos 2 "ciclos"
        assert duration >= 0.02


class TestParallelExecutorMetrics:
    """Testes de métricas do ParallelExecutor."""

    @pytest.mark.asyncio
    async def test_metrics_recorded(self, parallel_config, execution_engine):
        """Testa que métricas são registradas."""
        mock_metrics = MagicMock()
        mock_metrics.parallel_tickets_submitted_total = MagicMock()
        mock_metrics.parallel_tickets_submitted_total.labels = MagicMock(
            return_value=MagicMock(inc=MagicMock())
        )
        mock_metrics.parallel_ticket_duration_seconds = MagicMock()
        mock_metrics.parallel_ticket_duration_seconds.labels = MagicMock(
            return_value=MagicMock(observe=MagicMock())
        )

        executor = ParallelExecutor(parallel_config, execution_engine, mock_metrics)

        tickets = [
            {
                'ticket_id': f'metric-{i}',
                'task_type': 'MOCK',
                'parameters': {}
            }
            for i in range(3)
        ]

        await executor.execute_parallel_independent(tickets)

        # Verificar que métricas foram chamadas
        assert mock_metrics.parallel_tickets_submitted_total.labels.call_count > 0


class TestParallelExecutorErrors:
    """Testes de tratamento de erros."""

    @pytest.mark.asyncio
    async def test_handles_executor_exception(self, parallel_config):
        """Testa tratamento de exceções no executor."""
        # Criar engine que lança exceção
        engine = MagicMock()
        engine.process_ticket = AsyncMock(side_effect=RuntimeError('Test error'))

        executor = ParallelExecutor(parallel_config, engine)

        tickets = [
            {
                'ticket_id': f'error-{i}',
                'task_type': 'BUILD',
                'parameters': {}
            }
            for i in range(2)
        ]

        results = await executor.execute_parallel_independent(tickets)

        assert len(results) == 2
        assert all(r['success'] is False for r in results)

    @pytest.mark.asyncio
    async def test_handles_timeout_during_execution(self, parallel_config, execution_engine):
        """Testa timeout durante execução."""
        executor = ParallelExecutor(parallel_config, execution_engine)

        # Criar ticket com processamento lento
        tickets = [
            {
                'ticket_id': 'slow-ticket',
                'task_type': 'MOCK',
                'parameters': {'sleep': 100}
            }
        ]

        results = await executor.execute_parallel_independent(
            tickets,
            timeout_seconds=0.05
        )

        assert len(results) == 1
        assert results[0]['success'] is False
        assert 'Timeout' in results[0]['error']


class TestParallelExecutorBatching:
    """Testes de batch processing."""

    @pytest.mark.asyncio
    async def test_batch_processing_enabled(self, execution_engine):
        """Testa processamento em batch habilitado."""
        config = ParallelExecutionConfig(
            max_parallel_tasks=5,
            enable_batching=True,
            batch_size=3
        )
        executor = ParallelExecutor(config, execution_engine)

        tickets = [
            {
                'ticket_id': f'batch-{i}',
                'task_type': 'MOCK',
                'parameters': {}
            }
            for i in range(6)
        ]

        correlation_ids = await executor.submit_batch(tickets, TaskPriority.MEDIUM)

        assert len(correlation_ids) == 6

    @pytest.mark.asyncio
    async def test_batch_processing_disabled(self, execution_engine):
        """Testa processamento em batch desabilitado."""
        config = ParallelExecutionConfig(
            max_parallel_tasks=5,
            enable_batching=False
        )
        executor = ParallelExecutor(config, execution_engine)

        tickets = [
            {
                'ticket_id': f'no-batch-{i}',
                'task_type': 'MOCK',
                'parameters': {}
            }
            for i in range(4)
        ]

        correlation_ids = await executor.submit_batch(tickets)

        assert len(correlation_ids) == 4


class TestParallelExecutorRecovery:
    """Testes de recuperação de falhas."""

    @pytest.mark.asyncio
    async def test_continues_after_individual_failure(self, parallel_config, execution_engine):
        """Testa que executor continua após falha individual."""
        executor = ParallelExecutor(parallel_config, execution_engine)

        tickets = [
            {'ticket_id': 'ok-1', 'task_type': 'MOCK', 'parameters': {}},
            {'ticket_id': 'bad', 'task_type': 'MOCK', 'parameters': {'fail': True}},
            {'ticket_id': 'ok-2', 'task_type': 'MOCK', 'parameters': {}},
        ]

        # Configurar um ticket para falhar
        original_execute = execution_engine.executor_registry.get_executor('MOCK').execute

        async def conditional_execute(ticket):
            if ticket['ticket_id'] == 'bad':
                raise ValueError('Simulated failure')
            return await original_execute(ticket)

        execution_engine.executor_registry.get_executor('MOCK').execute = conditional_execute

        results = await executor.execute_parallel_independent(tickets)

        assert len(results) == 3
        assert results[0]['success'] is True
        assert results[1]['success'] is False
        assert results[2]['success'] is True
