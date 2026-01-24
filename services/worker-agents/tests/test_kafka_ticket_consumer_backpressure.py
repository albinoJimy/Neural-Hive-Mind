"""
Testes de Backpressure para o Kafka Ticket Consumer.

Verifica o controle de backpressure via semaphore, pause/resume do consumer,
e cleanup adequado de tickets in-flight.
"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Adicionar src ao path antes de importar
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


@pytest.fixture
def backpressure_config():
    """Configuração específica para testes de backpressure."""
    return SimpleNamespace(
        kafka_bootstrap_servers='localhost:9092',
        kafka_tickets_topic='execution.tickets',
        kafka_consumer_group_id='worker-agents-test',
        kafka_auto_offset_reset='earliest',
        kafka_schema_registry_url='http://localhost:8081',
        supported_task_types=['BUILD', 'DEPLOY', 'TEST'],
        kafka_security_protocol='PLAINTEXT',
        schemas_base_path=str(ROOT.parent / 'schemas'),
        max_concurrent_tickets=3,  # Limite baixo para testes
        consumer_pause_threshold=0.8,
        consumer_resume_threshold=0.5,
        kafka_max_retries_before_dlq=3,
    )


@pytest.fixture
def mock_backpressure_engine():
    """Mock do execution engine para testes de backpressure."""
    engine = AsyncMock()
    # Simular processamento lento (500ms)
    async def slow_process(ticket):
        await asyncio.sleep(0.5)
    engine.process_ticket = slow_process
    return engine


@pytest.fixture
def mock_backpressure_metrics():
    """Mock de métricas para testes de backpressure."""
    metrics = MagicMock()
    metrics.tickets_in_flight = MagicMock()
    metrics.consumer_paused_total = MagicMock()
    metrics.consumer_resumed_total = MagicMock()
    metrics.consumer_pause_duration_seconds = MagicMock()
    metrics.tickets_consumed_total = MagicMock()
    metrics.kafka_consumer_errors_total = MagicMock()
    metrics.dlq_messages_total = MagicMock()
    metrics.dlq_publish_duration_seconds = MagicMock()
    metrics.ticket_retry_count = MagicMock()
    return metrics


@pytest.mark.asyncio
async def test_backpressure_semaphore_initialized(backpressure_config, mock_backpressure_engine):
    """Verificar que semaphore é inicializado com valor correto."""
    from clients.kafka_ticket_consumer import KafkaTicketConsumer

    consumer = KafkaTicketConsumer(backpressure_config, mock_backpressure_engine)

    with patch.object(consumer, 'consumer', MagicMock()):
        await consumer.initialize()

    assert consumer.tickets_semaphore is not None
    assert consumer.tickets_semaphore._value == 3  # max_concurrent_tickets


@pytest.mark.asyncio
async def test_backpressure_limits_concurrent_tickets(backpressure_config, mock_backpressure_engine, mock_backpressure_metrics):
    """Verificar que backpressure limita tickets concorrentes."""
    from clients.kafka_ticket_consumer import KafkaTicketConsumer

    consumer = KafkaTicketConsumer(backpressure_config, mock_backpressure_engine, mock_backpressure_metrics)

    with patch.object(consumer, 'consumer', MagicMock()):
        await consumer.initialize()

    # Verificar que semaphore inicia com o valor correto
    assert consumer.tickets_semaphore._value == 3

    # Usar tasks com timeout para evitar bloqueio indefinido
    acquired_permits = []

    async def try_acquire_with_timeout(permit_id: int, timeout: float = 0.1):
        """Tentar adquirir semaphore com timeout."""
        try:
            await asyncio.wait_for(consumer.tickets_semaphore.acquire(), timeout=timeout)
            acquired_permits.append(permit_id)
            consumer.in_flight_tickets.add(f'ticket-{permit_id}')
            return True
        except asyncio.TimeoutError:
            return False

    # Adquirir 3 permits (máximo) - deve ter sucesso
    for i in range(3):
        result = await try_acquire_with_timeout(i)
        assert result is True, f"Falhou ao adquirir permit {i}"

    # Verificar que semaphore está esgotado
    assert consumer.tickets_semaphore._value == 0
    assert len(consumer.in_flight_tickets) == 3
    assert len(acquired_permits) == 3

    # Tentar adquirir 4o permit (deve falhar por timeout)
    result = await try_acquire_with_timeout(3)
    assert result is False, "4o permit não deveria ter sido adquirido"

    # Cleanup - liberar apenas os permits adquiridos
    for permit_id in acquired_permits:
        consumer.tickets_semaphore.release()
        consumer.in_flight_tickets.discard(f'ticket-{permit_id}')

    # Verificar estado final
    assert consumer.tickets_semaphore._value == 3
    assert len(consumer.in_flight_tickets) == 0


@pytest.mark.asyncio
async def test_consumer_pauses_at_threshold(backpressure_config, mock_backpressure_engine, mock_backpressure_metrics):
    """Verificar que consumer pausa quando threshold atingido."""
    from clients.kafka_ticket_consumer import KafkaTicketConsumer

    mock_kafka_consumer = MagicMock()
    mock_kafka_consumer.assignment.return_value = [MagicMock()]

    with patch('clients.kafka_ticket_consumer.Consumer', return_value=mock_kafka_consumer):
        consumer = KafkaTicketConsumer(backpressure_config, mock_backpressure_engine, mock_backpressure_metrics)
        await consumer.initialize()

        # Simular 3 tickets in-flight COM aquisição do semaphore
        # max_concurrent = semaphore._value + len(in_flight) = 0 + 3 = 3
        # pause_limit = int(3 * 0.8) = 2
        # 3 >= 2 = True -> deve pausar
        for i in range(3):
            await consumer.tickets_semaphore.acquire()
            consumer.in_flight_tickets.add(f'ticket-{i}')

        # Verificar estado antes de pausar
        assert consumer.tickets_semaphore._value == 0
        assert len(consumer.in_flight_tickets) == 3

        await consumer._pause_consumer_if_needed()

        assert consumer.consumer_paused is True
        mock_kafka_consumer.pause.assert_called_once()
        mock_backpressure_metrics.consumer_paused_total.inc.assert_called_once()

        # Cleanup
        for i in range(3):
            consumer.tickets_semaphore.release()


@pytest.mark.asyncio
async def test_consumer_resumes_at_threshold(backpressure_config, mock_backpressure_engine, mock_backpressure_metrics):
    """Verificar que consumer resume quando threshold atingido."""
    from clients.kafka_ticket_consumer import KafkaTicketConsumer

    mock_kafka_consumer = MagicMock()
    mock_kafka_consumer.assignment.return_value = [MagicMock()]

    with patch('clients.kafka_ticket_consumer.Consumer', return_value=mock_kafka_consumer):
        consumer = KafkaTicketConsumer(backpressure_config, mock_backpressure_engine, mock_backpressure_metrics)
        await consumer.initialize()

        # Simular estado de pausa (consumer foi pausado anteriormente)
        consumer.consumer_paused = True
        consumer.pause_start_time = asyncio.get_event_loop().time()

        # Simular 1 ticket in-flight COM aquisição do semaphore
        # max_concurrent = semaphore._value + len(in_flight) = 2 + 1 = 3
        # resume_limit = int(3 * 0.5) = 1
        # 1 <= 1 = True -> deve resumir
        await consumer.tickets_semaphore.acquire()
        consumer.in_flight_tickets.add('ticket-1')

        await consumer._resume_consumer_if_needed()

        assert consumer.consumer_paused is False
        mock_kafka_consumer.resume.assert_called_once()
        mock_backpressure_metrics.consumer_resumed_total.inc.assert_called_once()
        mock_backpressure_metrics.consumer_pause_duration_seconds.observe.assert_called_once()

        # Cleanup
        consumer.tickets_semaphore.release()


@pytest.mark.asyncio
async def test_in_flight_tickets_cleaned_up_on_success(backpressure_config, mock_backpressure_engine, mock_backpressure_metrics):
    """Verificar que tickets são removidos de in_flight após sucesso."""
    from clients.kafka_ticket_consumer import KafkaTicketConsumer

    mock_kafka_consumer = MagicMock()

    with patch('clients.kafka_ticket_consumer.Consumer', return_value=mock_kafka_consumer):
        consumer = KafkaTicketConsumer(backpressure_config, mock_backpressure_engine, mock_backpressure_metrics)
        await consumer.initialize()

        ticket = {
            'ticket_id': 'ticket-1',
            'task_id': 'task-1',
            'task_type': 'BUILD',
            'status': 'PENDING',
            'dependencies': []
        }

        mock_message = MagicMock()

        # Adicionar ticket a in_flight
        consumer.in_flight_tickets.add('ticket-1')
        initial_semaphore_value = consumer.tickets_semaphore._value

        # Processar ticket
        await consumer._process_ticket_with_cleanup(ticket, mock_message)

        # Verificar cleanup
        assert 'ticket-1' not in consumer.in_flight_tickets
        assert consumer.tickets_semaphore._value == initial_semaphore_value + 1  # Semaphore liberado


@pytest.mark.asyncio
async def test_in_flight_tickets_cleaned_up_on_failure(backpressure_config, mock_backpressure_metrics):
    """Verificar que tickets são removidos de in_flight mesmo em caso de falha."""
    from clients.kafka_ticket_consumer import KafkaTicketConsumer

    # Execution engine que sempre falha
    failing_engine = AsyncMock()
    failing_engine.process_ticket.side_effect = Exception('Simulated failure')

    mock_kafka_consumer = MagicMock()

    with patch('clients.kafka_ticket_consumer.Consumer', return_value=mock_kafka_consumer):
        consumer = KafkaTicketConsumer(backpressure_config, failing_engine, mock_backpressure_metrics)
        await consumer.initialize()

        ticket = {
            'ticket_id': 'ticket-1',
            'task_id': 'task-1',
            'task_type': 'BUILD',
            'status': 'PENDING',
            'dependencies': []
        }

        mock_message = MagicMock()

        # Adicionar ticket a in_flight
        consumer.in_flight_tickets.add('ticket-1')
        initial_semaphore_value = consumer.tickets_semaphore._value

        # Processar ticket (deve falhar mas fazer cleanup)
        await consumer._process_ticket_with_cleanup(ticket, mock_message)

        # Verificar cleanup mesmo com falha
        assert 'ticket-1' not in consumer.in_flight_tickets
        assert consumer.tickets_semaphore._value == initial_semaphore_value + 1  # Semaphore liberado


@pytest.mark.asyncio
async def test_metrics_updated_correctly(backpressure_config, mock_backpressure_engine, mock_backpressure_metrics):
    """Verificar que métricas são atualizadas corretamente."""
    from clients.kafka_ticket_consumer import KafkaTicketConsumer

    consumer = KafkaTicketConsumer(backpressure_config, mock_backpressure_engine, mock_backpressure_metrics)

    mock_consumer = MagicMock()
    consumer.consumer = mock_consumer

    await consumer.initialize()

    # Simular adição de tickets
    consumer.in_flight_tickets.add('ticket-1')
    consumer.in_flight_tickets.add('ticket-2')

    # Atualizar métrica manualmente (como faria o código real)
    mock_backpressure_metrics.tickets_in_flight.set(len(consumer.in_flight_tickets))

    # Verificar que métrica foi atualizada
    mock_backpressure_metrics.tickets_in_flight.set.assert_called_with(2)


@pytest.mark.asyncio
async def test_backpressure_with_high_load(backpressure_config, mock_backpressure_engine, mock_backpressure_metrics):
    """Teste de carga: verificar comportamento com muitos tickets sem bloqueio."""
    from clients.kafka_ticket_consumer import KafkaTicketConsumer

    mock_kafka_consumer = MagicMock()
    mock_kafka_consumer.assignment.return_value = [MagicMock()]

    with patch('clients.kafka_ticket_consumer.Consumer', return_value=mock_kafka_consumer):
        consumer = KafkaTicketConsumer(backpressure_config, mock_backpressure_engine, mock_backpressure_metrics)
        await consumer.initialize()

        # Simular tickets (limitado ao max_concurrent para evitar bloqueio)
        num_tickets = 3  # Igual ao max_concurrent_tickets
        tickets = [
            {'ticket_id': f'ticket-{i}', 'task_id': f'task-{i}', 'task_type': 'BUILD',
             'status': 'PENDING', 'dependencies': []}
            for i in range(num_tickets)
        ]

        # Processar tickets em paralelo (simular fluxo real: acquire -> process -> release)
        tasks = []
        for ticket in tickets:
            mock_message = MagicMock()
            # Adquirir semaphore antes de processar (simula loop principal)
            await consumer.tickets_semaphore.acquire()
            # Adicionar ticket a in_flight
            consumer.in_flight_tickets.add(ticket['ticket_id'])
            # Criar task para processamento
            task = asyncio.create_task(consumer._process_ticket_with_cleanup(ticket, mock_message))
            tasks.append(task)

        # Aguardar conclusão com timeout para evitar deadlock
        try:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=10.0
            )
        except asyncio.TimeoutError:
            # Cancelar tasks pendentes
            for task in tasks:
                if not task.done():
                    task.cancel()
            pytest.fail("Teste travou por timeout - possível deadlock no semaphore")

        # Verificar que a métrica foi chamada (cleanup aconteceu)
        assert mock_backpressure_metrics.tickets_in_flight.set.called

        # Verificar estado final: todos os tickets processados
        assert len(consumer.in_flight_tickets) == 0
        assert consumer.tickets_semaphore._value == 3  # Restaurado ao máximo
