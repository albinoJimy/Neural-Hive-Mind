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


# ============================================================================
# Testes de Integração para SLA Timeout
# ============================================================================


from src.activities.ticket_generation import (
    generate_execution_tickets,
    set_activity_dependencies
)


@pytest.fixture
def mock_config_integration():
    """Config mock para testes de integração de timeout."""
    config = MagicMock()
    config.sla_ticket_min_timeout_ms = 60000  # 60s
    config.sla_ticket_timeout_buffer_multiplier = 3.0
    return config


@pytest.fixture
def consolidated_decision():
    """Decisão consolidada mock."""
    return {
        'decision_id': 'decision-integration-001',
        'correlation_id': 'corr-integration-001',
        'trace_id': 'trace-integration-001',
        'span_id': 'span-integration-001'
    }


@pytest.mark.asyncio
@pytest.mark.integration
async def test_multiple_tickets_with_varying_durations(
    mock_config_integration, consolidated_decision
):
    """Plano com múltiplos tickets de durações variadas deve calcular timeouts corretamente."""
    with patch('src.activities.ticket_generation.activity') as mock_activity:
        mock_info = MagicMock()
        mock_info.workflow_id = 'workflow-integration-001'
        mock_activity.info.return_value = mock_info
        mock_activity.logger = MagicMock()

        plan = {
            'plan_id': 'plan-integration-001',
            'intent_id': 'intent-integration-001',
            'tasks': [
                {
                    'task_id': 'task-very-short',
                    'dependencies': [],
                    'estimated_duration_ms': 5000,  # 5s → timeout 60s (mínimo)
                    'task_type': 'VALIDATE'
                },
                {
                    'task_id': 'task-short',
                    'dependencies': ['task-very-short'],
                    'estimated_duration_ms': 15000,  # 15s → timeout 60s (mínimo)
                    'task_type': 'BUILD'
                },
                {
                    'task_id': 'task-medium',
                    'dependencies': ['task-short'],
                    'estimated_duration_ms': 30000,  # 30s → timeout 90s (30*3)
                    'task_type': 'TEST'
                },
                {
                    'task_id': 'task-long',
                    'dependencies': ['task-medium'],
                    'estimated_duration_ms': 120000,  # 2min → timeout 360s (120*3)
                    'task_type': 'DEPLOY'
                },
                {
                    'task_id': 'task-very-long',
                    'dependencies': ['task-long'],
                    'estimated_duration_ms': 600000,  # 10min → timeout 1800s (600*3)
                    'task_type': 'EXECUTE'
                }
            ],
            'execution_order': ['task-very-short', 'task-short', 'task-medium', 'task-long', 'task-very-long'],
            'risk_band': 'high'
        }

        set_activity_dependencies(
            kafka_producer=None,
            mongodb_client=None,
            config=mock_config_integration
        )

        tickets = await generate_execution_tickets(plan, consolidated_decision)

        # Validar que todos os tickets foram gerados
        assert len(tickets) == 5

        # Validar timeouts calculados
        expected_timeouts = {
            'task-very-short': 60000,   # max(60000, 5000*3) = 60000
            'task-short': 60000,         # max(60000, 15000*3) = 60000
            'task-medium': 90000,        # max(60000, 30000*3) = 90000
            'task-long': 360000,         # max(60000, 120000*3) = 360000
            'task-very-long': 1800000    # max(60000, 600000*3) = 1800000
        }

        for ticket in tickets:
            task_id = ticket['task_id']
            expected_timeout = expected_timeouts[task_id]
            actual_timeout = ticket['sla']['timeout_ms']

            assert actual_timeout == expected_timeout, (
                f"Ticket {task_id}: esperado timeout {expected_timeout}ms, "
                f"obtido {actual_timeout}ms"
            )

            # Validar que nenhum timeout está abaixo do mínimo
            assert actual_timeout >= 60000, (
                f"Ticket {task_id} tem timeout {actual_timeout}ms abaixo do mínimo 60000ms"
            )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_timeout_consistency_across_risk_bands(
    mock_config_integration, consolidated_decision
):
    """Timeout deve ser consistente independente do risk_band."""
    with patch('src.activities.ticket_generation.activity') as mock_activity:
        mock_info = MagicMock()
        mock_info.workflow_id = 'workflow-integration-002'
        mock_activity.info.return_value = mock_info
        mock_activity.logger = MagicMock()

        estimated_duration = 45000  # 45s

        risk_bands = ['low', 'medium', 'high', 'critical']

        for risk_band in risk_bands:
            plan = {
                'plan_id': f'plan-{risk_band}',
                'intent_id': f'intent-{risk_band}',
                'tasks': [{
                    'task_id': 'task-1',
                    'dependencies': [],
                    'estimated_duration_ms': estimated_duration
                }],
                'execution_order': ['task-1'],
                'risk_band': risk_band
            }

            set_activity_dependencies(
                kafka_producer=None,
                mongodb_client=None,
                config=mock_config_integration
            )

            tickets = await generate_execution_tickets(plan, consolidated_decision)

            # Timeout deve ser o mesmo para todos os risk_bands
            # (risk_band afeta max_retries e QoS, não timeout)
            expected_timeout = max(60000, int(45000 * 3.0))  # 135000ms
            assert tickets[0]['sla']['timeout_ms'] == expected_timeout, (
                f"Risk band {risk_band}: esperado {expected_timeout}ms, "
                f"obtido {tickets[0]['sla']['timeout_ms']}ms"
            )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_no_ticket_below_minimum_timeout_in_realistic_scenario(
    mock_config_integration, consolidated_decision
):
    """Cenário realista: nenhum ticket deve ter timeout < 60s."""
    with patch('src.activities.ticket_generation.activity') as mock_activity:
        mock_info = MagicMock()
        mock_info.workflow_id = 'workflow-integration-003'
        mock_activity.info.return_value = mock_info
        mock_activity.logger = MagicMock()

        # Simular plano realista com durações variadas
        plan = {
            'plan_id': 'plan-realistic',
            'intent_id': 'intent-realistic',
            'tasks': [
                {'task_id': 'validate', 'dependencies': [], 'estimated_duration_ms': 2000},
                {'task_id': 'analyze', 'dependencies': ['validate'], 'estimated_duration_ms': 8000},
                {'task_id': 'build', 'dependencies': ['analyze'], 'estimated_duration_ms': 45000},
                {'task_id': 'test-unit', 'dependencies': ['build'], 'estimated_duration_ms': 30000},
                {'task_id': 'test-integration', 'dependencies': ['build'], 'estimated_duration_ms': 60000},
                {'task_id': 'security-scan', 'dependencies': ['build'], 'estimated_duration_ms': 90000},
                {'task_id': 'deploy-staging', 'dependencies': ['test-unit', 'test-integration', 'security-scan'], 'estimated_duration_ms': 120000},
                {'task_id': 'smoke-test', 'dependencies': ['deploy-staging'], 'estimated_duration_ms': 15000},
                {'task_id': 'deploy-prod', 'dependencies': ['smoke-test'], 'estimated_duration_ms': 180000},
            ],
            'execution_order': [
                'validate', 'analyze', 'build',
                'test-unit', 'test-integration', 'security-scan',
                'deploy-staging', 'smoke-test', 'deploy-prod'
            ],
            'risk_band': 'high'
        }

        set_activity_dependencies(
            kafka_producer=None,
            mongodb_client=None,
            config=mock_config_integration
        )

        tickets = await generate_execution_tickets(plan, consolidated_decision)

        # Validar que TODOS os tickets têm timeout >= 60s
        for ticket in tickets:
            timeout_ms = ticket['sla']['timeout_ms']
            assert timeout_ms >= 60000, (
                f"Ticket {ticket['task_id']} tem timeout {timeout_ms}ms < 60000ms. "
                f"Estimated duration: {ticket['estimated_duration_ms']}ms"
            )

        # Validar que tickets com duração curta usam mínimo
        short_tasks = ['validate', 'analyze', 'smoke-test']
        for ticket in tickets:
            if ticket['task_id'] in short_tasks:
                assert ticket['sla']['timeout_ms'] == 60000, (
                    f"Ticket {ticket['task_id']} deveria usar timeout mínimo 60000ms, "
                    f"mas tem {ticket['sla']['timeout_ms']}ms"
                )

        # Validar que tickets com duração longa usam multiplicador
        long_tasks = ['build', 'test-integration', 'security-scan', 'deploy-staging', 'deploy-prod']
        for ticket in tickets:
            if ticket['task_id'] in long_tasks:
                estimated = ticket['estimated_duration_ms']
                expected = max(60000, int(estimated * 3.0))
                assert ticket['sla']['timeout_ms'] == expected, (
                    f"Ticket {ticket['task_id']} deveria ter timeout {expected}ms, "
                    f"mas tem {ticket['sla']['timeout_ms']}ms"
                )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_timeout_with_config_defaults_fallback(consolidated_decision):
    """Sem config injetado, deve usar defaults (60s, 3.0x)."""
    with patch('src.activities.ticket_generation.activity') as mock_activity:
        mock_info = MagicMock()
        mock_info.workflow_id = 'workflow-integration-004'
        mock_activity.info.return_value = mock_info
        mock_activity.logger = MagicMock()

        plan = {
            'plan_id': 'plan-defaults',
            'intent_id': 'intent-defaults',
            'tasks': [
                {'task_id': 'task-short', 'dependencies': [], 'estimated_duration_ms': 10000},
                {'task_id': 'task-long', 'dependencies': [], 'estimated_duration_ms': 50000}
            ],
            'execution_order': ['task-short', 'task-long'],
            'risk_band': 'medium'
        }

        # Não injetar config (usar defaults)
        set_activity_dependencies(
            kafka_producer=None,
            mongodb_client=None,
            config=None
        )

        tickets = await generate_execution_tickets(plan, consolidated_decision)

        # Validar que defaults foram usados
        assert tickets[0]['sla']['timeout_ms'] == 60000  # max(60000, 10000*3) = 60000
        assert tickets[1]['sla']['timeout_ms'] == 150000  # max(60000, 50000*3) = 150000
