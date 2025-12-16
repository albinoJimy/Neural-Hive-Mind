"""
Testes unitários para integração de predições ML no IntelligentScheduler.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, Mock

from src.scheduler.intelligent_scheduler import IntelligentScheduler
from src.config.settings import OrchestratorSettings
from src.scheduler.priority_calculator import PriorityCalculator
from src.scheduler.resource_allocator import ResourceAllocator
from src.observability.metrics import OrchestratorMetrics


@pytest.fixture
def mock_config():
    config = Mock(spec=OrchestratorSettings)
    config.service_registry_cache_ttl_seconds = 60
    config.optimizer_forecast_horizon_minutes = 15
    return config


@pytest.fixture
def mock_metrics():
    metrics = Mock(spec=OrchestratorMetrics)
    metrics.record_priority_score = Mock()
    metrics.record_workers_discovered = Mock()
    metrics.record_scheduler_allocation = Mock()
    metrics.record_scheduler_rejection = Mock()
    metrics.record_cache_hit = Mock()
    metrics.record_discovery_failure = Mock()
    metrics.record_anomaly_detection = AsyncMock()
    return metrics


@pytest.fixture
def mock_priority_calculator():
    calculator = Mock(spec=PriorityCalculator)
    calculator.calculate_priority_score = Mock(return_value=0.5)
    return calculator


@pytest.fixture
def mock_resource_allocator():
    allocator = AsyncMock(spec=ResourceAllocator)
    allocator.discover_workers = AsyncMock(return_value=[{
        'agent_id': 'agent-1',
        'agent_type': 'worker-agent',
        'score': 0.8,
        'predicted_queue_ms': 1200.0,
        'predicted_load_pct': 0.25,
        'ml_enriched': True
    }])
    allocator.select_best_worker = AsyncMock(return_value={
        'agent_id': 'agent-1',
        'agent_type': 'worker-agent',
        'score': 0.8,
        'predicted_queue_ms': 1200.0,
        'predicted_load_pct': 0.25,
        'ml_enriched': True
    })
    return allocator


@pytest.fixture
def mock_scheduling_predictor():
    predictor = AsyncMock()
    predictor.predict_duration = AsyncMock(return_value={
        'predicted_duration_ms': 90000,
        'confidence': 0.85,
        'model_type': 'duration_rf'
    })
    predictor.predict_resources = AsyncMock(return_value={
        'cpu_cores': 1.5,
        'memory_mb': 256,
        'confidence': 0.7
    })
    return predictor


@pytest.fixture
def mock_anomaly_detector():
    detector = AsyncMock()
    detector.detect_anomaly = AsyncMock(return_value={
        'is_anomaly': True,
        'score': 0.75,
        'type': 'duration_spike',
        'confidence': 0.8
    })
    return detector


@pytest.fixture
def sample_ticket():
    return {
        'ticket_id': 'ticket-ml-1',
        'risk_band': 'high',
        'required_capabilities': ['python'],
        'estimated_duration_ms': 60000
    }


@pytest.mark.asyncio
async def test_enrich_ticket_with_predictions_success(mock_config, mock_metrics, mock_priority_calculator, mock_resource_allocator, mock_scheduling_predictor, mock_anomaly_detector, sample_ticket):
    scheduler = IntelligentScheduler(
        mock_config,
        mock_metrics,
        mock_priority_calculator,
        mock_resource_allocator,
        scheduling_optimizer=None,
        scheduling_predictor=mock_scheduling_predictor,
        anomaly_detector=mock_anomaly_detector
    )

    enriched = await scheduler._enrich_ticket_with_predictions(sample_ticket.copy())

    predictions = enriched.get('predictions')
    assert predictions['duration_ms'] == 90000
    assert predictions['duration_confidence'] == 0.85
    assert predictions['anomaly']['is_anomaly'] is True
    assert predictions['anomaly']['type'] == 'duration_spike'
    assert predictions['anomaly']['score'] == 0.75


@pytest.mark.asyncio
async def test_priority_boost_by_duration_ratio(mock_config, mock_metrics, mock_priority_calculator, mock_resource_allocator, mock_scheduling_predictor, sample_ticket):
    mock_scheduling_predictor.predict_duration = AsyncMock(return_value={
        'predicted_duration_ms': 100000,
        'confidence': 0.9,
        'model_type': 'duration_rf'
    })
    mock_scheduling_predictor.predict_resources = AsyncMock(return_value={
        'cpu_cores': 1.0,
        'memory_mb': 256,
        'confidence': 0.5
    })

    scheduler = IntelligentScheduler(
        mock_config,
        mock_metrics,
        mock_priority_calculator,
        mock_resource_allocator,
        scheduling_optimizer=None,
        scheduling_predictor=mock_scheduling_predictor
    )

    ticket = await scheduler.schedule_ticket(sample_ticket.copy())
    assert ticket['allocation_metadata']['priority_score'] > 0.5
    assert mock_metrics.record_priority_score.call_args.kwargs['boosted'] is True


@pytest.mark.asyncio
async def test_priority_boost_by_anomaly(mock_config, mock_metrics, mock_priority_calculator, mock_resource_allocator, mock_scheduling_predictor, mock_anomaly_detector, sample_ticket):
    scheduler = IntelligentScheduler(
        mock_config,
        mock_metrics,
        mock_priority_calculator,
        mock_resource_allocator,
        scheduling_optimizer=None,
        scheduling_predictor=mock_scheduling_predictor,
        anomaly_detector=mock_anomaly_detector
    )

    ticket = await scheduler.schedule_ticket(sample_ticket.copy())
    assert ticket['allocation_metadata']['priority_score'] > 0.5
    assert mock_metrics.record_priority_score.call_args.kwargs['boosted'] is True
    await asyncio.sleep(0)
    mock_metrics.record_anomaly_detection.assert_awaited()


@pytest.mark.asyncio
async def test_no_boost_when_duration_ratio_low(mock_config, mock_metrics, mock_priority_calculator, mock_resource_allocator, mock_scheduling_predictor, sample_ticket):
    mock_scheduling_predictor.predict_duration = AsyncMock(return_value={
        'predicted_duration_ms': 70000,
        'confidence': 0.6,
        'model_type': 'duration_rf'
    })
    mock_scheduling_predictor.predict_resources = AsyncMock(return_value={
        'cpu_cores': 1.0,
        'memory_mb': 256,
        'confidence': 0.5
    })

    scheduler = IntelligentScheduler(
        mock_config,
        mock_metrics,
        mock_priority_calculator,
        mock_resource_allocator,
        scheduling_optimizer=None,
        scheduling_predictor=mock_scheduling_predictor
    )

    ticket = await scheduler.schedule_ticket(sample_ticket.copy())
    assert ticket['allocation_metadata']['priority_score'] == 0.5
    assert mock_metrics.record_priority_score.call_args.kwargs['boosted'] is False


@pytest.mark.asyncio
async def test_allocation_metadata_includes_predictions(mock_config, mock_metrics, mock_priority_calculator, mock_resource_allocator, mock_scheduling_predictor, mock_anomaly_detector, sample_ticket):
    scheduler = IntelligentScheduler(
        mock_config,
        mock_metrics,
        mock_priority_calculator,
        mock_resource_allocator,
        scheduling_optimizer=None,
        scheduling_predictor=mock_scheduling_predictor,
        anomaly_detector=mock_anomaly_detector
    )

    ticket = await scheduler.schedule_ticket(sample_ticket.copy())
    metadata = ticket.get('allocation_metadata', {})
    assert 'predicted_duration_ms' in metadata
    assert metadata.get('anomaly_detected') is True
    assert metadata.get('predicted_queue_ms') == 1200.0
    assert metadata.get('predicted_load_pct') == 0.25
    assert metadata.get('ml_scheduling_enriched') is True


@pytest.mark.asyncio
async def test_predictions_fail_gracefully(mock_config, mock_metrics, mock_priority_calculator, mock_resource_allocator, mock_scheduling_predictor, sample_ticket):
    mock_scheduling_predictor.predict_duration = AsyncMock(side_effect=RuntimeError('prediction failed'))
    mock_scheduling_predictor.predict_resources = AsyncMock()

    scheduler = IntelligentScheduler(
        mock_config,
        mock_metrics,
        mock_priority_calculator,
        mock_resource_allocator,
        scheduling_optimizer=None,
        scheduling_predictor=mock_scheduling_predictor
    )

    ticket = await scheduler.schedule_ticket(sample_ticket.copy())
    assert 'predictions' not in ticket
    assert ticket['allocation_metadata']['agent_id'] == 'agent-1'
