"""
Testes unitários para activity de monitoramento proativo de SLA.

Testes cobrem:
- check_workflow_sla_proactive com deadline se aproximando
- check_workflow_sla_proactive com deadline OK
- Verificação de budget no checkpoint post_ticket_publishing
- Fail-open quando SLA Management System indisponível
- Cleanup de SLAMonitor no finally block
- Métricas Prometheus de duração de verificação
"""
import pytest
import time
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from src.activities.sla_monitoring import (
    check_workflow_sla_proactive,
    _default_response,
    SLAMonitorUnavailable
)


@pytest.fixture
def mock_activity_info():
    """Mock activity.info() para contexto de workflow."""
    with patch('src.activities.sla_monitoring.activity') as mock_activity:
        mock_info = MagicMock()
        mock_info.workflow_id = 'test-workflow-123'
        mock_activity.info.return_value = mock_info
        mock_activity.logger = MagicMock()
        yield mock_activity


@pytest.fixture
def mock_config():
    """Criar mock de configuração."""
    config = MagicMock()
    config.sla_management_enabled = True
    config.sla_budget_critical_threshold = 0.2
    return config


@pytest.fixture
def mock_metrics():
    """Criar mock de métricas."""
    metrics = MagicMock()
    metrics.record_deadline_approaching = MagicMock()
    metrics.update_sla_remaining = MagicMock()
    metrics.record_sla_check_duration = MagicMock()
    metrics.record_sla_monitor_error = MagicMock()
    return metrics


@pytest.fixture
def mock_sla_monitor():
    """Criar mock de SLAMonitor."""
    monitor = AsyncMock()
    monitor.initialize = AsyncMock()
    monitor.close = AsyncMock()
    monitor.check_workflow_sla = AsyncMock(return_value={
        'deadline_approaching': False,
        'critical_tickets': [],
        'remaining_seconds': 3600.0
    })
    monitor.check_budget_threshold = AsyncMock(return_value=(False, {'status': 'HEALTHY'}))
    return monitor


@pytest.fixture
def sample_tickets():
    """Lista de tickets de exemplo para verificação de SLA."""
    return [
        {
            'ticket_id': 'ticket-1',
            'sla': {'deadline': int((datetime.now().timestamp() + 7200) * 1000), 'timeout_ms': 60000}
        },
        {
            'ticket_id': 'ticket-2',
            'sla': {'deadline': int((datetime.now().timestamp() + 7200) * 1000), 'timeout_ms': 45000}
        }
    ]


class TestCheckWorkflowSlaProactive:
    """Testes para check_workflow_sla_proactive activity."""

    @pytest.mark.asyncio
    async def test_returns_deadline_approaching_true(
        self, mock_activity_info, sample_tickets, mock_config, mock_metrics, mock_sla_monitor
    ):
        """Deve retornar deadline_approaching=True quando deadline próximo."""
        mock_sla_monitor.check_workflow_sla.return_value = {
            'deadline_approaching': True,
            'critical_tickets': ['ticket-1'],
            'remaining_seconds': 120.0
        }

        with patch('src.activities.sla_monitoring.get_settings', return_value=mock_config):
            with patch('src.activities.sla_monitoring.get_metrics', return_value=mock_metrics):
                with patch('src.activities.sla_monitoring.SLAMonitor', return_value=mock_sla_monitor):
                    result = await check_workflow_sla_proactive(
                        'workflow-001',
                        sample_tickets,
                        'post_ticket_generation'
                    )

                    assert result['deadline_approaching'] is True
                    assert result['remaining_seconds'] == 120.0
                    assert 'ticket-1' in result['critical_tickets']
                    mock_metrics.record_deadline_approaching.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_deadline_approaching_false_when_ok(
        self, mock_activity_info, sample_tickets, mock_config, mock_metrics, mock_sla_monitor
    ):
        """Deve retornar deadline_approaching=False quando deadline OK."""
        with patch('src.activities.sla_monitoring.get_settings', return_value=mock_config):
            with patch('src.activities.sla_monitoring.get_metrics', return_value=mock_metrics):
                with patch('src.activities.sla_monitoring.SLAMonitor', return_value=mock_sla_monitor):
                    result = await check_workflow_sla_proactive(
                        'workflow-001',
                        sample_tickets,
                        'post_ticket_generation'
                    )

                    assert result['deadline_approaching'] is False
                    assert len(result['critical_tickets']) == 0
                    mock_metrics.record_deadline_approaching.assert_not_called()

    @pytest.mark.asyncio
    async def test_checks_budget_on_post_ticket_publishing_checkpoint(
        self, mock_activity_info, sample_tickets, mock_config, mock_metrics, mock_sla_monitor
    ):
        """Deve verificar budget apenas no checkpoint post_ticket_publishing."""
        mock_sla_monitor.check_budget_threshold.return_value = (True, {
            'status': 'CRITICAL',
            'error_budget_remaining': 0.05
        })

        with patch('src.activities.sla_monitoring.get_settings', return_value=mock_config):
            with patch('src.activities.sla_monitoring.get_metrics', return_value=mock_metrics):
                with patch('src.activities.sla_monitoring.SLAMonitor', return_value=mock_sla_monitor):
                    result = await check_workflow_sla_proactive(
                        'workflow-001',
                        sample_tickets,
                        'post_ticket_publishing'
                    )

                    assert result['budget_critical'] is True
                    assert result['budget_data']['status'] == 'CRITICAL'
                    mock_sla_monitor.check_budget_threshold.assert_called_once()

    @pytest.mark.asyncio
    async def test_does_not_check_budget_on_generation_checkpoint(
        self, mock_activity_info, sample_tickets, mock_config, mock_metrics, mock_sla_monitor
    ):
        """Não deve verificar budget no checkpoint post_ticket_generation."""
        with patch('src.activities.sla_monitoring.get_settings', return_value=mock_config):
            with patch('src.activities.sla_monitoring.get_metrics', return_value=mock_metrics):
                with patch('src.activities.sla_monitoring.SLAMonitor', return_value=mock_sla_monitor):
                    result = await check_workflow_sla_proactive(
                        'workflow-001',
                        sample_tickets,
                        'post_ticket_generation'
                    )

                    assert 'budget_critical' not in result
                    mock_sla_monitor.check_budget_threshold.assert_not_called()

    @pytest.mark.asyncio
    async def test_fail_open_when_sla_system_unavailable(
        self, mock_activity_info, sample_tickets, mock_config, mock_metrics
    ):
        """Deve retornar resposta default quando SLA System indisponível (fail-open)."""
        mock_sla_monitor = AsyncMock()
        mock_sla_monitor.initialize.side_effect = Exception('Connection refused')

        with patch('src.activities.sla_monitoring.get_settings', return_value=mock_config):
            with patch('src.activities.sla_monitoring.get_metrics', return_value=mock_metrics):
                with patch('src.activities.sla_monitoring.SLAMonitor', return_value=mock_sla_monitor):
                    result = await check_workflow_sla_proactive(
                        'workflow-001',
                        sample_tickets,
                        'post_ticket_generation'
                    )

                    # Deve retornar resposta default (fail-open)
                    assert result['deadline_approaching'] is False
                    assert result['critical_tickets'] == []
                    assert result['checkpoint'] == 'post_ticket_generation'
                    mock_metrics.record_sla_monitor_error.assert_called_once_with('proactive_check')

    @pytest.mark.asyncio
    async def test_closes_sla_monitor_in_finally_block(
        self, mock_activity_info, sample_tickets, mock_config, mock_metrics, mock_sla_monitor
    ):
        """Deve fechar SLAMonitor no finally block."""
        with patch('src.activities.sla_monitoring.get_settings', return_value=mock_config):
            with patch('src.activities.sla_monitoring.get_metrics', return_value=mock_metrics):
                with patch('src.activities.sla_monitoring.SLAMonitor', return_value=mock_sla_monitor):
                    await check_workflow_sla_proactive(
                        'workflow-001',
                        sample_tickets,
                        'post_ticket_generation'
                    )

                    mock_sla_monitor.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_records_sla_check_duration_metric(
        self, mock_activity_info, sample_tickets, mock_config, mock_metrics, mock_sla_monitor
    ):
        """Deve registrar métrica de duração da verificação."""
        with patch('src.activities.sla_monitoring.get_settings', return_value=mock_config):
            with patch('src.activities.sla_monitoring.get_metrics', return_value=mock_metrics):
                with patch('src.activities.sla_monitoring.SLAMonitor', return_value=mock_sla_monitor):
                    await check_workflow_sla_proactive(
                        'workflow-001',
                        sample_tickets,
                        'post_ticket_generation'
                    )

                    mock_metrics.record_sla_check_duration.assert_called_once()
                    call_args = mock_metrics.record_sla_check_duration.call_args
                    assert 'proactive_post_ticket_generation' in call_args[0][0]

    @pytest.mark.asyncio
    async def test_skips_when_sla_management_disabled(
        self, mock_activity_info, sample_tickets, mock_metrics
    ):
        """Deve pular verificação quando SLA management desabilitado."""
        disabled_config = MagicMock()
        disabled_config.sla_management_enabled = False

        with patch('src.activities.sla_monitoring.get_settings', return_value=disabled_config):
            with patch('src.activities.sla_monitoring.get_metrics', return_value=mock_metrics):
                result = await check_workflow_sla_proactive(
                    'workflow-001',
                    sample_tickets,
                    'post_ticket_generation'
                )

                # Deve retornar resposta default
                assert result['deadline_approaching'] is False
                assert result['checkpoint'] == 'post_ticket_generation'


class TestDefaultResponse:
    """Testes para _default_response helper."""

    def test_returns_default_for_generation_checkpoint(self):
        """Deve retornar resposta default sem budget_critical para generation checkpoint."""
        response = _default_response('post_ticket_generation')

        assert response['deadline_approaching'] is False
        assert response['critical_tickets'] == []
        assert response['remaining_seconds'] == 0.0
        assert response['checkpoint'] == 'post_ticket_generation'
        assert 'budget_critical' not in response

    def test_returns_default_with_budget_for_publishing_checkpoint(self):
        """Deve retornar resposta default com budget_critical para publishing checkpoint."""
        response = _default_response('post_ticket_publishing')

        assert response['deadline_approaching'] is False
        assert response['checkpoint'] == 'post_ticket_publishing'
        assert response['budget_critical'] is False
