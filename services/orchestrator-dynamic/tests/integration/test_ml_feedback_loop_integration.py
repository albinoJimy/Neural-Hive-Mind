"""
Testes de integração para feedback loop ML (error tracking + allocation outcomes).
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch

from src.activities import result_consolidation
from src.ml.scheduling_optimizer import SchedulingOptimizer
from src.observability.metrics import OrchestratorMetrics
from src.config.settings import OrchestratorSettings


@pytest.fixture
def mock_config():
    config = Mock(spec=OrchestratorSettings)
    config.sla_management_enabled = True
    config.ml_allocation_outcomes_enabled = True
    config.opa_enabled = False
    return config


@pytest.fixture
def mock_metrics():
    metrics = Mock(spec=OrchestratorMetrics)
    metrics.record_ml_prediction_error_with_logging = Mock()
    metrics.record_ml_prediction_accuracy = Mock()
    metrics.update_sla_remaining = Mock()
    metrics.record_deadline_approaching = Mock()
    metrics.update_budget_remaining = Mock()
    metrics.update_budget_status = Mock()
    return metrics


@pytest.fixture
def mock_scheduling_optimizer():
    optimizer = Mock(spec=SchedulingOptimizer)
    optimizer.record_allocation_outcome = AsyncMock()
    return optimizer


@pytest.fixture
def sample_ticket_completed():
    return {
        'ticket_id': 'ticket-123',
        'status': 'COMPLETED',
        'actual_duration_ms': 45000,
        'allocation_metadata': {
            'agent_id': 'agent-1',
            'agent_type': 'worker-agent',
            'predicted_duration_ms': 50000,
            'predicted_queue_ms': 1500.0,
            'predicted_load_pct': 0.3,
            'ml_enriched': True
        }
    }


@pytest.mark.asyncio
async def test_record_allocation_outcome_for_ticket_success(mock_scheduling_optimizer, sample_ticket_completed):
    await result_consolidation.record_allocation_outcome_for_ticket(
        sample_ticket_completed,
        mock_scheduling_optimizer
    )

    mock_scheduling_optimizer.record_allocation_outcome.assert_awaited_once()
    args, kwargs = mock_scheduling_optimizer.record_allocation_outcome.call_args
    assert kwargs['ticket']['ticket_id'] == 'ticket-123'
    worker = kwargs['worker']
    assert worker['agent_id'] == 'agent-1'
    assert worker['predicted_queue_ms'] == 1500.0
    assert worker['predicted_load_pct'] == 0.3
    assert kwargs['actual_duration_ms'] == 45000


@pytest.mark.asyncio
async def test_record_allocation_outcome_missing_data(mock_scheduling_optimizer):
    ticket_without_metadata = {'ticket_id': 'ticket-456', 'status': 'COMPLETED', 'actual_duration_ms': 1000}

    await result_consolidation.record_allocation_outcome_for_ticket(
        ticket_without_metadata,
        mock_scheduling_optimizer
    )

    mock_scheduling_optimizer.record_allocation_outcome.assert_not_awaited()


@pytest.mark.asyncio
async def test_consolidate_results_calls_feedback_loop(mock_config, mock_metrics, mock_scheduling_optimizer, sample_ticket_completed):
    pending_ticket = {'ticket_id': 'ticket-789', 'status': 'PENDING'}
    tickets = [
        {'ticket': sample_ticket_completed},
        {'ticket': pending_ticket}
    ]

    result_consolidation.set_activity_dependencies(scheduling_optimizer=mock_scheduling_optimizer, config=mock_config)

    sla_monitor_instance = AsyncMock()
    sla_monitor_instance.initialize = AsyncMock()
    sla_monitor_instance.check_workflow_sla = AsyncMock(return_value={
        'deadline_approaching': False,
        'remaining_seconds': 0,
        'critical_tickets': [],
        'ticket_deadline_data': {}
    })
    sla_monitor_instance.check_budget_threshold = AsyncMock(return_value=(False, {'status': 'HEALTHY', 'error_budget_remaining': 0}))
    sla_monitor_instance.close = AsyncMock()

    alert_manager_instance = AsyncMock()
    alert_manager_instance.set_redis = Mock()
    alert_manager_instance.send_deadline_alert = AsyncMock()
    alert_manager_instance.send_budget_alert = AsyncMock()
    alert_manager_instance.publish_sla_violation = AsyncMock()

    kafka_producer_instance = AsyncMock()
    kafka_producer_instance.initialize = AsyncMock()
    kafka_producer_instance.close = AsyncMock()

    with patch('src.activities.result_consolidation.get_metrics', return_value=mock_metrics), \
            patch('src.clients.redis_client.get_redis_client', AsyncMock(return_value=AsyncMock())), \
            patch('src.clients.kafka_producer.KafkaProducerClient', return_value=kafka_producer_instance), \
            patch('src.activities.result_consolidation.SLAMonitor', return_value=sla_monitor_instance), \
            patch('src.activities.result_consolidation.AlertManager', return_value=alert_manager_instance), \
            patch.object(result_consolidation, 'compute_and_record_ml_error') as compute_mock:
        result = await result_consolidation.consolidate_results(tickets, 'workflow-123')

    compute_mock.assert_called_once_with(sample_ticket_completed, mock_metrics)
    mock_scheduling_optimizer.record_allocation_outcome.assert_awaited_once()
    assert result['status'] in ['SUCCESS', 'PARTIAL']


@pytest.mark.asyncio
async def test_feedback_loop_disabled_by_config(mock_config, mock_metrics, mock_scheduling_optimizer, sample_ticket_completed):
    mock_config.ml_allocation_outcomes_enabled = False
    tickets = [{'ticket': sample_ticket_completed}]
    result_consolidation.set_activity_dependencies(scheduling_optimizer=mock_scheduling_optimizer, config=mock_config)

    sla_monitor_instance = AsyncMock()
    sla_monitor_instance.initialize = AsyncMock()
    sla_monitor_instance.check_workflow_sla = AsyncMock(return_value={
        'deadline_approaching': False,
        'remaining_seconds': 0,
        'critical_tickets': [],
        'ticket_deadline_data': {}
    })
    sla_monitor_instance.check_budget_threshold = AsyncMock(return_value=(False, {'status': 'HEALTHY', 'error_budget_remaining': 0}))
    sla_monitor_instance.close = AsyncMock()

    alert_manager_instance = AsyncMock()
    alert_manager_instance.set_redis = Mock()

    kafka_producer_instance = AsyncMock()
    kafka_producer_instance.initialize = AsyncMock()
    kafka_producer_instance.close = AsyncMock()

    with patch('src.activities.result_consolidation.get_metrics', return_value=mock_metrics), \
            patch('src.clients.redis_client.get_redis_client', AsyncMock(return_value=AsyncMock())), \
            patch('src.clients.kafka_producer.KafkaProducerClient', return_value=kafka_producer_instance), \
            patch('src.activities.result_consolidation.SLAMonitor', return_value=sla_monitor_instance), \
            patch('src.activities.result_consolidation.AlertManager', return_value=alert_manager_instance), \
            patch.object(result_consolidation, 'compute_and_record_ml_error'):
        await result_consolidation.consolidate_results(tickets, 'workflow-456')

    mock_scheduling_optimizer.record_allocation_outcome.assert_not_awaited()


@pytest.mark.asyncio
async def test_feedback_loop_fail_open_on_error(mock_config, mock_metrics, mock_scheduling_optimizer, sample_ticket_completed):
    sample_ticket_completed['allocation_metadata']['agent_id'] = 'agent-err'
    mock_scheduling_optimizer.record_allocation_outcome.side_effect = RuntimeError('kafka down')
    tickets = [{'ticket': sample_ticket_completed}]
    result_consolidation.set_activity_dependencies(scheduling_optimizer=mock_scheduling_optimizer, config=mock_config)

    sla_monitor_instance = AsyncMock()
    sla_monitor_instance.initialize = AsyncMock()
    sla_monitor_instance.check_workflow_sla = AsyncMock(return_value={
        'deadline_approaching': False,
        'remaining_seconds': 0,
        'critical_tickets': [],
        'ticket_deadline_data': {}
    })
    sla_monitor_instance.check_budget_threshold = AsyncMock(return_value=(False, {'status': 'HEALTHY', 'error_budget_remaining': 0}))
    sla_monitor_instance.close = AsyncMock()

    alert_manager_instance = AsyncMock()
    alert_manager_instance.set_redis = Mock()

    kafka_producer_instance = AsyncMock()
    kafka_producer_instance.initialize = AsyncMock()
    kafka_producer_instance.close = AsyncMock()

    with patch('src.activities.result_consolidation.get_metrics', return_value=mock_metrics), \
            patch('src.clients.redis_client.get_redis_client', AsyncMock(return_value=AsyncMock())), \
            patch('src.clients.kafka_producer.KafkaProducerClient', return_value=kafka_producer_instance), \
            patch('src.activities.result_consolidation.SLAMonitor', return_value=sla_monitor_instance), \
            patch('src.activities.result_consolidation.AlertManager', return_value=alert_manager_instance), \
            patch.object(result_consolidation, 'compute_and_record_ml_error'):
        result = await result_consolidation.consolidate_results(tickets, 'workflow-789')

    assert result['workflow_id'] == 'workflow-789'
    mock_scheduling_optimizer.record_allocation_outcome.assert_awaited()


@pytest.mark.asyncio
async def test_ml_feedback_runs_without_sla(mock_config, mock_metrics, mock_scheduling_optimizer, sample_ticket_completed):
    mock_config.sla_management_enabled = False
    mock_config.ml_allocation_outcomes_enabled = True
    tickets = [{'ticket': sample_ticket_completed}]
    result_consolidation.set_activity_dependencies(scheduling_optimizer=mock_scheduling_optimizer, config=mock_config)

    with patch('src.activities.result_consolidation.get_metrics', return_value=mock_metrics), \
            patch.object(result_consolidation, 'compute_and_record_ml_error') as compute_mock:
        result = await result_consolidation.consolidate_results(tickets, 'workflow-000')

    compute_mock.assert_called_once_with(sample_ticket_completed, mock_metrics)
    mock_scheduling_optimizer.record_allocation_outcome.assert_awaited_once()
    assert result['workflow_id'] == 'workflow-000'


def test_compute_and_record_ml_error_records_accuracy(mock_metrics):
    ticket = {
        'ticket_id': 'ticket-accuracy',
        'status': 'COMPLETED',
        'actual_duration_ms': 45000,
        'allocation_metadata': {'predicted_duration_ms': 50000}
    }

    result_consolidation.compute_and_record_ml_error(ticket, mock_metrics)

    mock_metrics.record_ml_prediction_error_with_logging.assert_called_once()
    mock_metrics.record_ml_prediction_accuracy.assert_called_once_with(
        model_type='duration',
        predicted_ms=50000,
        actual_ms=45000
    )
