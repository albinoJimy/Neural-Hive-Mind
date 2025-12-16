"""Teste de integração do Scheduler com modelos ML."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock

from src.scheduler.intelligent_scheduler import IntelligentScheduler
from src.config.settings import OrchestratorSettings
from src.observability.metrics import OrchestratorMetrics


@pytest.mark.asyncio
async def test_scheduler_enriches_ticket_with_predictions():
    """Valida que scheduler enriquece ticket com predições ML."""
    
    # Setup
    config = OrchestratorSettings()
    metrics = OrchestratorMetrics()
    
    # Mock predictors
    scheduling_predictor = AsyncMock()
    scheduling_predictor.predict_duration = AsyncMock(return_value={
        'predicted_duration_ms': 5000,
        'confidence': 0.85,
        'model_type': 'xgboost'
    })
    scheduling_predictor.predict_resources = AsyncMock(return_value={
        'cpu_cores': 2.0,
        'memory_mb': 1024,
        'confidence': 0.8
    })
    
    anomaly_detector = AsyncMock()
    anomaly_detector.detect_anomaly = AsyncMock(return_value={
        'is_anomaly': False,
        'anomaly_score': 0.1,
        'anomaly_type': None,
        'confidence': 0.9
    })
    
    # Mock components
    priority_calculator = MagicMock()
    priority_calculator.calculate_priority_score = MagicMock(return_value=0.7)
    
    resource_allocator = AsyncMock()
    resource_allocator.discover_workers = AsyncMock(return_value=[
        {'agent_id': 'worker-1', 'agent_type': 'worker-agent', 'score': 0.8}
    ])
    resource_allocator.select_best_worker = AsyncMock(return_value={
        'agent_id': 'worker-1',
        'agent_type': 'worker-agent',
        'score': 0.8
    })
    
    # Create scheduler
    scheduler = IntelligentScheduler(
        config=config,
        metrics=metrics,
        priority_calculator=priority_calculator,
        resource_allocator=resource_allocator,
        scheduling_predictor=scheduling_predictor,
        anomaly_detector=anomaly_detector
    )
    
    # Test ticket
    ticket = {
        'ticket_id': 'test-123',
        'risk_weight': 50,
        'capabilities': ['database', 'analytics'],
        'estimated_duration_ms': 4000,
        'qos': {'priority': 0.7}
    }
    
    # Execute
    result = await scheduler.schedule_ticket(ticket)
    
    # Assertions
    assert 'predictions' in result
    assert result['predictions']['duration_ms'] == 5000
    assert result['predictions']['confidence'] == 0.85
    assert result['predictions']['cpu_cores'] == 2.0
    assert result['predictions']['anomaly']['is_anomaly'] is False
    
    assert 'allocation_metadata' in result
    assert result['allocation_metadata']['predicted_duration_ms'] == 5000
    assert result['allocation_metadata']['anomaly_detected'] is False
    
    # Verify predictors were called
    scheduling_predictor.predict_duration.assert_called_once()
    scheduling_predictor.predict_resources.assert_called_once()
    anomaly_detector.detect_anomaly.assert_called_once()


@pytest.mark.asyncio
async def test_scheduler_boosts_priority_on_anomaly():
    """Valida que scheduler aumenta prioridade quando anomalia detectada."""
    
    # Setup (similar ao teste anterior)
    config = OrchestratorSettings()
    metrics = OrchestratorMetrics()
    
    scheduling_predictor = AsyncMock()
    scheduling_predictor.predict_duration = AsyncMock(return_value={
        'predicted_duration_ms': 8000,  # 2x estimado
        'confidence': 0.75,
        'model_type': 'xgboost'
    })
    scheduling_predictor.predict_resources = AsyncMock(return_value={
        'cpu_cores': 2.0,
        'memory_mb': 1024,
        'confidence': 0.8
    })
    
    anomaly_detector = AsyncMock()
    anomaly_detector.detect_anomaly = AsyncMock(return_value={
        'is_anomaly': True,
        'anomaly_score': 0.85,
        'anomaly_type': 'capability_anomaly',
        'confidence': 0.95
    })
    
    priority_calculator = MagicMock()
    priority_calculator.calculate_priority_score = MagicMock(return_value=0.5)
    
    resource_allocator = AsyncMock()
    resource_allocator.discover_workers = AsyncMock(return_value=[
        {'agent_id': 'worker-1', 'agent_type': 'worker-agent', 'score': 0.8}
    ])
    resource_allocator.select_best_worker = AsyncMock(return_value={
        'agent_id': 'worker-1',
        'agent_type': 'worker-agent',
        'score': 0.8
    })
    
    scheduler = IntelligentScheduler(
        config=config,
        metrics=metrics,
        priority_calculator=priority_calculator,
        resource_allocator=resource_allocator,
        scheduling_predictor=scheduling_predictor,
        anomaly_detector=anomaly_detector
    )
    
    ticket = {
        'ticket_id': 'test-anomaly',
        'risk_weight': 50,
        'capabilities': ['cap1', 'cap2', 'cap3', 'cap4', 'cap5'],
        'estimated_duration_ms': 4000,
        'qos': {'priority': 0.5}
    }
    
    result = await scheduler.schedule_ticket(ticket)
    
    # Priority deve ter sido boosted (0.5 * 1.2 = 0.6)
    assert result['allocation_metadata']['priority_score'] == 0.6
    assert result['allocation_metadata']['anomaly_detected'] is True
    assert result['allocation_metadata']['anomaly_type'] == 'capability_anomaly'
