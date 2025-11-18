"""
Testes de integração end-to-end para monitoramento de SLA.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

from src.activities.result_consolidation import consolidate_results, publish_telemetry
from src.sla.sla_monitor import SLAMonitor
from src.sla.alert_manager import AlertManager


@pytest.fixture
def mock_settings():
    """Fixture com settings mock."""
    settings = MagicMock()
    settings.sla_management_enabled = True
    settings.sla_management_host = 'localhost'
    settings.sla_management_port = 8000
    settings.sla_management_timeout_seconds = 5
    settings.sla_management_cache_ttl_seconds = 10
    settings.sla_deadline_warning_threshold = 0.8
    settings.sla_budget_critical_threshold = 0.2
    settings.sla_violations_topic = 'sla.violations'
    settings.sla_alerts_topic = 'sla.alerts'
    settings.sla_alert_deduplication_ttl_seconds = 300
    return settings


@pytest.fixture
def tickets_deadline_approaching():
    """Tickets com deadline próximo."""
    now = datetime.now().timestamp() * 1000
    return [
        {
            'ticket': {
                'ticket_id': 'ticket-1',
                'plan_id': 'plan-1',
                'intent_id': 'intent-1',
                'status': 'PENDING',
                'sla': {'deadline': int(now + 1000), 'timeout_ms': 5000},
                'created_at': int(now - 4000),
                'estimated_duration_ms': 1000
            }
        }
    ]


@pytest.fixture
def tickets_with_violations():
    """Tickets com violações de SLA."""
    now = datetime.now().timestamp() * 1000
    return [
        {
            'ticket': {
                'ticket_id': 'ticket-2',
                'plan_id': 'plan-2',
                'intent_id': 'intent-2',
                'status': 'FAILED',
                'sla': {'deadline': int(now - 5000), 'timeout_ms': 3000},
                'created_at': int(now - 10000),
                'estimated_duration_ms': 8000,  # Excedeu timeout de 3000ms
                'retry_count': 2
            }
        }
    ]


@pytest.fixture
def tickets_healthy():
    """Tickets saudáveis sem problemas de SLA."""
    now = datetime.now().timestamp() * 1000
    return [
        {
            'ticket': {
                'ticket_id': 'ticket-3',
                'plan_id': 'plan-3',
                'intent_id': 'intent-3',
                'status': 'COMPLETED',
                'sla': {'deadline': int(now + 10000), 'timeout_ms': 5000},
                'created_at': int(now - 1000),
                'estimated_duration_ms': 800
            }
        }
    ]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_workflow_with_deadline_approaching(
    tickets_deadline_approaching, mock_settings
):
    """Testa workflow com deadline próximo."""
    with patch('src.activities.result_consolidation.get_settings', return_value=mock_settings):
        with patch('src.activities.result_consolidation.get_metrics') as mock_get_metrics:
            mock_metrics = MagicMock()
            mock_get_metrics.return_value = mock_metrics

            # Mock Redis client
            with patch('src.activities.result_consolidation.get_redis_client') as mock_get_redis:
                mock_get_redis.return_value = None  # Fail-open

                # Mock Kafka producer
                with patch('src.activities.result_consolidation.KafkaProducerClient') as MockKafkaProducer:
                    mock_producer = AsyncMock()
                    mock_producer.initialize = AsyncMock()
                    mock_producer.close = AsyncMock()
                    MockKafkaProducer.return_value = mock_producer

                    # Mock do SLAMonitor
                    with patch('src.activities.result_consolidation.SLAMonitor') as MockSLAMonitor:
                        # Mock do AlertManager
                        with patch('src.activities.result_consolidation.AlertManager') as MockAlertManager:
                            mock_monitor = AsyncMock()
                            mock_monitor.initialize = AsyncMock()
                            mock_monitor.close = AsyncMock()
                            mock_monitor.check_workflow_sla = AsyncMock(return_value={
                                'deadline_approaching': True,
                                'critical_tickets': ['ticket-1'],
                                'remaining_seconds': 1.0,
                                'ticket_deadline_data': {}
                            })
                            mock_monitor.check_budget_threshold = AsyncMock(return_value=(False, None))
                            MockSLAMonitor.return_value = mock_monitor

                            mock_alert_manager = AsyncMock()
                            mock_alert_manager.set_redis = MagicMock()
                            mock_alert_manager.send_deadline_alert = AsyncMock()
                            MockAlertManager.return_value = mock_alert_manager

                            # Executar consolidate_results
                            result = await consolidate_results(tickets_deadline_approaching, 'workflow-1')

                            # Verificar resultado
                            assert result['sla_status']['deadline_approaching'] is True
                            assert result['sla_remaining_seconds'] == 1.0
                            assert result['sla_status']['violations_count'] == 0

                            # Verificar que SLA monitor foi usado
                            mock_monitor.initialize.assert_called_once()
                            mock_monitor.check_workflow_sla.assert_called_once_with('workflow-1', tickets_deadline_approaching)
                            mock_monitor.close.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_workflow_with_budget_critical(
    tickets_healthy, mock_settings
):
    """Testa workflow com budget crítico."""
    budget_data = {
        'error_budget_remaining': 0.15,
        'status': 'CRITICAL',
        'burn_rates': [{'window_hours': 1, 'rate': 8.5}]
    }

    with patch('src.activities.result_consolidation.get_settings', return_value=mock_settings):
        with patch('src.activities.result_consolidation.get_metrics') as mock_get_metrics:
            mock_metrics = MagicMock()
            mock_get_metrics.return_value = mock_metrics

            with patch('src.activities.result_consolidation.SLAMonitor') as MockSLAMonitor:
                mock_monitor = AsyncMock()
                mock_monitor.initialize = AsyncMock()
                mock_monitor.close = AsyncMock()
                mock_monitor.check_workflow_sla = AsyncMock(return_value={
                    'deadline_approaching': False,
                    'critical_tickets': [],
                    'remaining_seconds': 10.0
                })
                mock_monitor.check_budget_threshold = AsyncMock(return_value=(True, budget_data))
                MockSLAMonitor.return_value = mock_monitor

                result = await consolidate_results(tickets_healthy, 'workflow-2')

                assert result['sla_status']['budget_critical'] is True
                assert result['budget_status'] == 'CRITICAL'

                # Verificar métricas atualizadas
                mock_metrics.update_budget_remaining.assert_called()
                mock_metrics.update_budget_status.assert_called()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_workflow_with_sla_violation(
    tickets_with_violations, mock_settings
):
    """Testa workflow com violação real de SLA."""
    with patch('src.activities.result_consolidation.get_settings', return_value=mock_settings):
        with patch('src.activities.result_consolidation.get_metrics') as mock_get_metrics:
            mock_metrics = MagicMock()
            mock_get_metrics.return_value = mock_metrics

            with patch('src.activities.result_consolidation.SLAMonitor') as MockSLAMonitor:
                mock_monitor = AsyncMock()
                mock_monitor.initialize = AsyncMock()
                mock_monitor.close = AsyncMock()
                mock_monitor.check_workflow_sla = AsyncMock(return_value={
                    'deadline_approaching': False,
                    'critical_tickets': [],
                    'remaining_seconds': 0
                })
                mock_monitor.check_budget_threshold = AsyncMock(return_value=(False, None))
                MockSLAMonitor.return_value = mock_monitor

                result = await consolidate_results(tickets_with_violations, 'workflow-3')

                # Verificar violação detectada
                assert result['sla_status']['violations_count'] == 1
                assert result['metrics']['sla_violations'] == 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_consolidate_results_with_sla_checks(
    tickets_healthy, mock_settings
):
    """Testa integração completa em consolidate_results."""
    with patch('src.activities.result_consolidation.get_settings', return_value=mock_settings):
        with patch('src.activities.result_consolidation.get_metrics') as mock_get_metrics:
            mock_metrics = MagicMock()
            mock_get_metrics.return_value = mock_metrics

            with patch('src.activities.result_consolidation.SLAMonitor') as MockSLAMonitor:
                mock_monitor = AsyncMock()
                mock_monitor.initialize = AsyncMock()
                mock_monitor.close = AsyncMock()
                mock_monitor.check_workflow_sla = AsyncMock(return_value={
                    'deadline_approaching': False,
                    'critical_tickets': [],
                    'remaining_seconds': 9.0
                })
                mock_monitor.check_budget_threshold = AsyncMock(return_value=(False, {
                    'error_budget_remaining': 0.75,
                    'status': 'HEALTHY'
                }))
                MockSLAMonitor.return_value = mock_monitor

                result = await consolidate_results(tickets_healthy, 'workflow-4')

                # Verificar campos SLA no resultado
                assert 'sla_status' in result
                assert 'sla_remaining_seconds' in result
                assert 'budget_status' in result

                assert result['sla_status']['deadline_approaching'] is False
                assert result['sla_status']['budget_critical'] is False
                assert result['budget_status'] == 'HEALTHY'


@pytest.mark.asyncio
@pytest.mark.integration
async def test_publish_telemetry_with_sla_metrics(tickets_healthy):
    """Testa inclusão de métricas SLA em telemetria."""
    workflow_result = {
        'workflow_id': 'workflow-5',
        'intent_id': 'intent-5',
        'plan_id': 'plan-5',
        'status': 'SUCCESS',
        'metrics': {
            'total_tickets': 1,
            'successful_tickets': 1
        },
        'tickets_summary': [
            {'ticket_id': 'ticket-3', 'status': 'COMPLETED'}
        ],
        'sla_status': {
            'deadline_approaching': False,
            'budget_critical': False,
            'violations_count': 0
        },
        'sla_remaining_seconds': 9.0,
        'budget_status': 'HEALTHY'
    }

    with patch('src.activities.result_consolidation.get_metrics') as mock_get_metrics:
        mock_metrics = MagicMock()
        mock_get_metrics.return_value = mock_metrics

        await publish_telemetry(workflow_result)

        # Verificar que métricas foram registradas
        # (Como não há Kafka real, verificamos apenas que não houve exceção)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_sla_monitoring_failure_resilience(
    tickets_healthy, mock_settings
):
    """Testa fail-open quando SLA Management System está indisponível."""
    with patch('src.activities.result_consolidation.get_settings', return_value=mock_settings):
        with patch('src.activities.result_consolidation.get_metrics') as mock_get_metrics:
            mock_metrics = MagicMock()
            mock_get_metrics.return_value = mock_metrics

            with patch('src.activities.result_consolidation.SLAMonitor') as MockSLAMonitor:
                # Simular falha no SLA monitoring
                MockSLAMonitor.side_effect = Exception("SLA System unavailable")

                # Deve continuar sem bloquear workflow
                result = await consolidate_results(tickets_healthy, 'workflow-6')

                # Verificar que workflow foi consolidado mesmo com falha
                assert result['status'] == 'SUCCESS'
                assert result['workflow_id'] == 'workflow-6'

                # Campos SLA devem ter valores padrão (fail-open)
                assert result['sla_status']['violations_count'] == 0
                assert result['budget_status'] == 'UNKNOWN'


@pytest.mark.asyncio
@pytest.mark.integration
async def test_sla_monitoring_disabled(tickets_healthy):
    """Testa comportamento quando SLA monitoring está desabilitado."""
    mock_settings = MagicMock()
    mock_settings.sla_management_enabled = False

    with patch('src.activities.result_consolidation.get_settings', return_value=mock_settings):
        with patch('src.activities.result_consolidation.get_metrics') as mock_get_metrics:
            mock_metrics = MagicMock()
            mock_get_metrics.return_value = mock_metrics

            result = await consolidate_results(tickets_healthy, 'workflow-7')

            # Verificar que SLA monitoring não foi executado
            assert result['sla_status']['violations_count'] == 0
            assert result['budget_status'] == 'UNKNOWN'
