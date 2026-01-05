"""
Testes unitários para ExecutionEngine - validação de incrementos de métricas.

Testa se as métricas são corretamente incrementadas durante o processamento de tickets.
"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))

# Mock neural_hive_observability antes de importar o módulo
mock_tracer_module = MagicMock()
mock_tracer_module.get_tracer = MagicMock()
sys.modules['neural_hive_observability'] = mock_tracer_module

from engine.execution_engine import ExecutionEngine, TaskExecutionError  # noqa: E402


class StubTicketClient:
    """Cliente de ticket stub para testes."""

    def __init__(self):
        self.status_calls = []

    async def update_ticket_status(self, ticket_id, status, error_message=None, actual_duration_ms=None):
        self.status_calls.append({
            'ticket_id': ticket_id,
            'status': status,
            'error_message': error_message,
            'actual_duration_ms': actual_duration_ms,
        })


class StubResultProducer:
    """Producer de resultados stub para testes."""

    def __init__(self):
        self.published = []

    async def publish_result(self, ticket_id, status, result, error_message=None, actual_duration_ms=None):
        self.published.append({
            'ticket_id': ticket_id,
            'status': status,
            'result': result,
            'error_message': error_message,
            'actual_duration_ms': actual_duration_ms,
        })


class StubDependencyCoordinator:
    """Coordenador de dependências stub para testes."""

    async def wait_for_dependencies(self, ticket):
        pass


class StubExecutorSuccess:
    """Executor que sempre retorna sucesso."""

    async def execute(self, ticket):
        return {'success': True, 'output': {'ok': True}, 'metadata': {}, 'logs': []}


class StubExecutorFail:
    """Executor que sempre falha."""

    async def execute(self, ticket):
        raise RuntimeError('Executor failure')


class StubExecutorTimeout:
    """Executor que causa timeout."""

    async def execute(self, ticket):
        await asyncio.sleep(10)


class RegistryWrapper:
    """Wrapper para registro de executores."""

    def __init__(self, executor):
        self.executor = executor

    def get_executor(self, task_type: str):
        return self.executor


@pytest.fixture
def config():
    """Configuração básica para testes."""
    return SimpleNamespace(
        max_concurrent_tasks=5,
        max_retries_per_ticket=0,
        retry_backoff_base_seconds=0,
        retry_backoff_max_seconds=0,
        task_timeout_multiplier=1.0,
    )


@pytest.fixture
def sample_ticket():
    """Ticket de exemplo para testes."""
    return {
        'ticket_id': 'ticket-metrics-test',
        'task_id': 'task-1',
        'task_type': 'BUILD',
        'status': 'PENDING',
        'dependencies': [],
        'plan_id': 'plan-123',
        'intent_id': 'intent-456',
        'sla': {'timeout_ms': 5000, 'max_retries': 0},
    }


@pytest.fixture
def mock_metrics():
    """Métricas mock para validação de chamadas."""
    metrics = MagicMock()

    # tickets_processing_total
    metrics.tickets_processing_total = MagicMock()
    metrics.tickets_processing_total.labels = MagicMock(return_value=MagicMock())

    # active_tasks
    metrics.active_tasks = MagicMock()
    metrics.active_tasks.set = MagicMock()

    # tickets_completed_total
    metrics.tickets_completed_total = MagicMock()
    metrics.tickets_completed_total.labels = MagicMock(return_value=MagicMock())

    # tickets_failed_total
    metrics.tickets_failed_total = MagicMock()
    metrics.tickets_failed_total.labels = MagicMock(return_value=MagicMock())

    # task_duration_seconds
    metrics.task_duration_seconds = MagicMock()
    metrics.task_duration_seconds.labels = MagicMock(return_value=MagicMock())

    # task_retries_total
    metrics.task_retries_total = MagicMock()
    metrics.task_retries_total.labels = MagicMock(return_value=MagicMock())

    return metrics


@pytest.fixture
def mock_tracer():
    """Mock do tracer para evitar dependências externas."""
    mock_span = MagicMock()
    mock_span.__enter__ = MagicMock(return_value=mock_span)
    mock_span.__exit__ = MagicMock(return_value=False)
    mock_span.set_attribute = MagicMock()

    tracer = MagicMock()
    tracer.start_as_current_span = MagicMock(return_value=mock_span)

    # Configura o mock global
    mock_tracer_module.get_tracer.return_value = tracer

    return tracer


@pytest.mark.asyncio
async def test_process_ticket_increments_tickets_processing_total(config, sample_ticket, mock_metrics, mock_tracer):
    """Verifica se tickets_processing_total é incrementado ao iniciar processamento."""
    ticket_client = StubTicketClient()
    result_producer = StubResultProducer()
    dependency_coordinator = StubDependencyCoordinator()
    executor = StubExecutorSuccess()
    registry = RegistryWrapper(executor)

    engine = ExecutionEngine(
        config, ticket_client, result_producer, dependency_coordinator, registry, metrics=mock_metrics
    )

    await engine.process_ticket(sample_ticket)
    await asyncio.wait_for(engine.active_tasks[sample_ticket['ticket_id']], timeout=5)

    # Verifica que tickets_processing_total.labels(task_type='BUILD').inc() foi chamado
    mock_metrics.tickets_processing_total.labels.assert_called_with(task_type='BUILD')
    mock_metrics.tickets_processing_total.labels.return_value.inc.assert_called()


@pytest.mark.asyncio
async def test_process_ticket_sets_active_tasks(config, sample_ticket, mock_metrics, mock_tracer):
    """Verifica se active_tasks.set() é chamado corretamente."""
    ticket_client = StubTicketClient()
    result_producer = StubResultProducer()
    dependency_coordinator = StubDependencyCoordinator()
    executor = StubExecutorSuccess()
    registry = RegistryWrapper(executor)

    engine = ExecutionEngine(
        config, ticket_client, result_producer, dependency_coordinator, registry, metrics=mock_metrics
    )

    await engine.process_ticket(sample_ticket)
    await asyncio.wait_for(engine.active_tasks[sample_ticket['ticket_id']], timeout=5)

    # Verifica que active_tasks.set() foi chamado
    assert mock_metrics.active_tasks.set.called


@pytest.mark.asyncio
async def test_process_ticket_success_increments_completed_total(config, sample_ticket, mock_metrics, mock_tracer):
    """Verifica se tickets_completed_total é incrementado em sucesso."""
    ticket_client = StubTicketClient()
    result_producer = StubResultProducer()
    dependency_coordinator = StubDependencyCoordinator()
    executor = StubExecutorSuccess()
    registry = RegistryWrapper(executor)

    engine = ExecutionEngine(
        config, ticket_client, result_producer, dependency_coordinator, registry, metrics=mock_metrics
    )

    await engine.process_ticket(sample_ticket)
    await asyncio.wait_for(engine.active_tasks[sample_ticket['ticket_id']], timeout=5)

    # Verifica que tickets_completed_total.labels(task_type='BUILD').inc() foi chamado
    mock_metrics.tickets_completed_total.labels.assert_called_with(task_type='BUILD')
    mock_metrics.tickets_completed_total.labels.return_value.inc.assert_called()


@pytest.mark.asyncio
async def test_process_ticket_success_observes_duration(config, sample_ticket, mock_metrics, mock_tracer):
    """Verifica se task_duration_seconds.observe() é chamado em sucesso."""
    ticket_client = StubTicketClient()
    result_producer = StubResultProducer()
    dependency_coordinator = StubDependencyCoordinator()
    executor = StubExecutorSuccess()
    registry = RegistryWrapper(executor)

    engine = ExecutionEngine(
        config, ticket_client, result_producer, dependency_coordinator, registry, metrics=mock_metrics
    )

    await engine.process_ticket(sample_ticket)
    await asyncio.wait_for(engine.active_tasks[sample_ticket['ticket_id']], timeout=5)

    # Verifica que task_duration_seconds.labels(task_type='BUILD').observe() foi chamado
    mock_metrics.task_duration_seconds.labels.assert_called_with(task_type='BUILD')
    mock_metrics.task_duration_seconds.labels.return_value.observe.assert_called()


@pytest.mark.asyncio
async def test_process_ticket_failure_increments_failed_total(config, sample_ticket, mock_metrics, mock_tracer):
    """Verifica se tickets_failed_total é incrementado em falha."""
    ticket_client = StubTicketClient()
    result_producer = StubResultProducer()
    dependency_coordinator = StubDependencyCoordinator()
    executor = StubExecutorFail()
    registry = RegistryWrapper(executor)

    engine = ExecutionEngine(
        config, ticket_client, result_producer, dependency_coordinator, registry, metrics=mock_metrics
    )

    await engine.process_ticket(sample_ticket)
    await asyncio.wait_for(engine.active_tasks[sample_ticket['ticket_id']], timeout=5)

    # Verifica que tickets_failed_total.labels(...).inc() foi chamado
    assert mock_metrics.tickets_failed_total.labels.called
    mock_metrics.tickets_failed_total.labels.return_value.inc.assert_called()


@pytest.mark.asyncio
async def test_process_ticket_timeout_increments_failed_total(config, sample_ticket, mock_metrics, mock_tracer):
    """Verifica se tickets_failed_total é incrementado em timeout (via execution_error após retry)."""
    ticket_client = StubTicketClient()
    result_producer = StubResultProducer()
    dependency_coordinator = StubDependencyCoordinator()
    executor = StubExecutorTimeout()
    registry = RegistryWrapper(executor)

    # Configura timeout curto para o teste
    sample_ticket['sla']['timeout_ms'] = 100

    engine = ExecutionEngine(
        config, ticket_client, result_producer, dependency_coordinator, registry, metrics=mock_metrics
    )

    await engine.process_ticket(sample_ticket)
    await asyncio.wait_for(engine.active_tasks[sample_ticket['ticket_id']], timeout=5)

    # O timeout interno é capturado por _execute_task_with_retry e convertido em TaskExecutionError
    # que é tratado como 'execution_error'. Verificamos que tickets_failed_total foi incrementado.
    assert mock_metrics.tickets_failed_total.labels.called
    mock_metrics.tickets_failed_total.labels.return_value.inc.assert_called()


@pytest.mark.asyncio
async def test_active_tasks_reset_after_completion(config, sample_ticket, mock_metrics, mock_tracer):
    """Verifica se active_tasks é resetado após conclusão."""
    ticket_client = StubTicketClient()
    result_producer = StubResultProducer()
    dependency_coordinator = StubDependencyCoordinator()
    executor = StubExecutorSuccess()
    registry = RegistryWrapper(executor)

    engine = ExecutionEngine(
        config, ticket_client, result_producer, dependency_coordinator, registry, metrics=mock_metrics
    )

    await engine.process_ticket(sample_ticket)
    await asyncio.wait_for(engine.active_tasks[sample_ticket['ticket_id']], timeout=5)

    # Após conclusão, active_tasks deve ter sido chamado com 0
    calls = [call[0][0] for call in mock_metrics.active_tasks.set.call_args_list]
    assert 0 in calls, 'active_tasks.set(0) deve ser chamado após conclusão'
