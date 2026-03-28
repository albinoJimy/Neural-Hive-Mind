"""
Testes para RiskAlertManager e componentes relacionados
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock

from neural_hive_risk_scoring import (
    RiskAlertManager,
    RiskAlert,
    AlertRule,
    AlertType,
    AlertSeverity,
    AlertHandler,
    LoggingAlertHandler,
    CallbackAlertHandler,
    DynamicThresholds,
    ThresholdMonitor,
    RiskHistory,
    RiskScoringConfig,
    RiskBand,
    RiskAssessment,
    UnifiedDomain
)


@pytest.fixture
def config():
    """Configuração de teste."""
    return RiskScoringConfig()


@pytest.fixture
def dynamic_thresholds(config):
    """Thresholds dinâmicos de teste."""
    return DynamicThresholds(base_config=config)


@pytest.fixture
def threshold_monitor(dynamic_thresholds):
    """Monitor de thresholds de teste."""
    return ThresholdMonitor(dynamic_thresholds)


@pytest.fixture
def risk_history():
    """Histórico de risco de teste."""
    return RiskHistory()


@pytest.fixture
def alert_manager(threshold_monitor, risk_history, config):
    """Gerenciador de alertas de teste."""
    return RiskAlertManager(
        threshold_monitor=threshold_monitor,
        risk_history=risk_history,
        config=config
    )


@pytest.fixture
def sample_assessment():
    """Avaliação de exemplo."""
    return RiskAssessment(
        score=0.9,
        band=RiskBand.CRITICAL,
        domain=UnifiedDomain.SECURITY,
        factors={'security_level': 0.9},
        reasoning='Critical security risk'
    )


class TestAlertRule:
    """Testes para AlertRule."""

    def test_init(self):
        """Testa inicialização."""
        rule = AlertRule(
            name='test_rule',
            alert_type=AlertType.THRESHOLD_VIOLATION,
            enabled=True,
            min_severity=AlertSeverity.WARNING,
            cooldown_minutes=60
        )

        assert rule.name == 'test_rule'
        assert rule.alert_type == AlertType.THRESHOLD_VIOLATION
        assert rule.enabled == True

    def test_should_trigger_disabled(self):
        """Testa regra desabilitada."""
        rule = AlertRule(
            name='disabled',
            alert_type=AlertType.THRESHOLD_VIOLATION,
            enabled=False
        )

        context = {'threshold_violation': True}
        result = rule.should_trigger('entity-1', context, None)

        assert result == False

    def test_should_trigger_with_cooldown(self):
        """Testa cooldown de regra."""
        rule = AlertRule(
            name='with_cooldown',
            alert_type=AlertType.THRESHOLD_VIOLATION,
            cooldown_minutes=60
        )

        context = {'threshold_violation': True}
        last_alert = datetime.utcnow() - timedelta(minutes=30)

        result = rule.should_trigger('entity-1', context, last_alert)

        # Deve bloquear por cooldown
        assert result == False

    def test_should_trigger_threshold_violation(self):
        """Testa gatilho de violação de threshold."""
        rule = AlertRule(
            name='violation',
            alert_type=AlertType.THRESHOLD_VIOLATION
        )

        context = {'threshold_violation': True}
        result = rule.should_trigger('entity-1', context, None)

        assert result == True


class TestLoggingAlertHandler:
    """Testes para LoggingAlertHandler."""

    def test_init(self):
        """Testa inicialização."""
        handler = LoggingAlertHandler()
        assert handler.name == "logging"

    def test_handle(self, alert_manager):
        """Testa processamento de alerta."""
        handler = LoggingAlertHandler()

        alert = RiskAlert(
            id='ALT-001',
            alert_type=AlertType.THRESHOLD_VIOLATION,
            severity=AlertSeverity.WARNING,
            entity_id='test-entity',
            domain=UnifiedDomain.SECURITY,
            score=0.9,
            band=RiskBand.CRITICAL,
            message='Test alert',
            details={}
        )

        result = handler.handle(alert)

        assert result == True


class TestCallbackAlertHandler:
    """Testes para CallbackAlertHandler."""

    def test_init(self):
        """Testa inicialização."""
        callback = Mock(return_value=True)
        handler = CallbackAlertHandler('test_handler', callback)

        assert handler.name == 'test_handler'

    def test_handle_success(self):
        """Testa processamento bem-sucedido."""
        callback = Mock(return_value=True)
        handler = CallbackAlertHandler('test', callback)

        alert = Mock()
        result = handler.handle(alert)

        assert result == True
        callback.assert_called_once_with(alert)

    def test_handle_failure(self):
        """Testa processamento com falha."""
        callback = Mock(side_effect=Exception("Test error"))
        handler = CallbackAlertHandler('test', callback)

        alert = Mock()
        result = handler.handle(alert)

        assert result == False


class TestRiskAlert:
    """Testes para RiskAlert."""

    def test_init(self):
        """Testa inicialização."""
        alert = RiskAlert(
            id='ALT-001',
            alert_type=AlertType.THRESHOLD_VIOLATION,
            severity=AlertSeverity.CRITICAL,
            entity_id='test-entity',
            domain=UnifiedDomain.SECURITY,
            score=0.9,
            band=RiskBand.CRITICAL,
            message='Critical alert',
            details={}
        )

        assert alert.id == 'ALT-001'
        assert alert.acknowledged == False
        assert alert.resolved == False

    def test_to_dict(self):
        """Testa conversão para dicionário."""
        alert = RiskAlert(
            id='ALT-001',
            alert_type=AlertType.ANOMALY_DETECTED,
            severity=AlertSeverity.WARNING,
            entity_id='test-entity',
            domain=UnifiedDomain.BUSINESS,
            score=0.7,
            band=RiskBand.HIGH,
            message='Anomaly alert',
            details={}
        )

        alert_dict = alert.to_dict()

        assert alert_dict['id'] == 'ALT-001'
        assert alert_dict['alert_type'] == 'anomaly_detected'
        assert alert_dict['severity'] == 'warning'
        assert alert_dict['acknowledged'] == False


class TestRiskAlertManager:
    """Testes para RiskAlertManager."""

    def test_init(self, alert_manager):
        """Testa inicialização."""
        assert alert_manager.threshold_monitor is not None
        assert alert_manager.risk_history is not None
        assert len(alert_manager._rules) > 0
        assert len(alert_manager._handlers) > 0

    def test_add_rule(self, alert_manager):
        """Testa adição de regra."""
        initial_count = len(alert_manager._rules)

        rule = AlertRule(
            name='custom_rule',
            alert_type=AlertType.TREND_WORSENING
        )
        alert_manager.add_rule(rule)

        assert len(alert_manager._rules) == initial_count + 1

    def test_add_handler(self, alert_manager):
        """Testa adição de handler."""
        initial_count = len(alert_manager._handlers)

        def custom_handler(alert):
            return True

        handler = CallbackAlertHandler('custom', custom_handler)
        alert_manager.add_handler(handler)

        assert len(alert_manager._handlers) == initial_count + 1

    def test_process_assessment_no_alert(self, alert_manager):
        """Testa processamento sem alertas."""
        assessment = RiskAssessment(
            score=0.2,
            band=RiskBand.LOW,
            domain=UnifiedDomain.BUSINESS,
            factors={},
            reasoning='Low risk'
        )

        alerts = alert_manager.process_assessment(assessment, 'safe-entity')

        # Score baixo não deve gerar alerta
        assert len(alerts) == 0

    def test_process_assessment_with_alert(self, alert_manager, sample_assessment):
        """Testa processamento com alerta."""
        alerts = alert_manager.process_assessment(sample_assessment, 'risky-entity')

        # Score crítico deve gerar alerta
        assert len(alerts) >= 1

    def test_acknowledge_alert(self, alert_manager, sample_assessment):
        """Testa confirmação de alerta."""
        alerts = alert_manager.process_assessment(sample_assessment, 'test-entity')

        if alerts:
            alert_id = alerts[0].id
            result = alert_manager.acknowledge_alert(alert_id, 'user-1')

            assert result == True

            # Verificar que foi confirmado (filtrar por ID manualmente)
            all_alerts = alert_manager.get_alerts()
            alert = next((a for a in all_alerts if a.id == alert_id), None)
            assert alert is not None
            assert alert.acknowledged == True
            assert alert.acknowledged_by == 'user-1'

    def test_resolve_alert(self, alert_manager, sample_assessment):
        """Testa resolução de alerta."""
        alerts = alert_manager.process_assessment(sample_assessment, 'test-entity')

        if alerts:
            alert_id = alerts[0].id
            result = alert_manager.resolve_alert(alert_id, 'user-1')

            assert result == True

            # Verificar que foi resolvido (filtrar por ID manualmente)
            all_alerts = alert_manager.get_alerts()
            alert = next((a for a in all_alerts if a.id == alert_id), None)
            assert alert is not None
            assert alert.resolved == True

    def test_get_alerts_by_entity(self, alert_manager, sample_assessment):
        """Testa filtro por entidade."""
        alert_manager.process_assessment(sample_assessment, 'entity-1')
        alert_manager.process_assessment(sample_assessment, 'entity-2')

        entity1_alerts = alert_manager.get_alerts(entity_id='entity-1')

        assert all(a.entity_id == 'entity-1' for a in entity1_alerts)

    def test_get_alerts_by_type(self, alert_manager, sample_assessment):
        """Testa filtro por tipo."""
        alerts = alert_manager.process_assessment(sample_assessment, 'test-entity')

        if alerts:
            alert_type = alerts[0].alert_type
            filtered = alert_manager.get_alerts(alert_type=alert_type)

            assert all(a.alert_type == alert_type for a in filtered)

    def test_get_alerts_unacknowledged_only(self, alert_manager, sample_assessment):
        """Testa filtro de não confirmados."""
        alert_manager.process_assessment(sample_assessment, 'test-entity')

        unacknowledged = alert_manager.get_alerts(unacknowledged_only=True)

        # Todos devem estar não confirmados inicialmente
        if unacknowledged:
            assert all(not a.acknowledged for a in unacknowledged)

    def test_get_alert_stats(self, alert_manager, sample_assessment):
        """Testa estatísticas de alertas."""
        alert_manager.process_assessment(sample_assessment, 'entity-1')
        alert_manager.process_assessment(sample_assessment, 'entity-2')

        stats = alert_manager.get_alert_stats()

        assert 'total_alerts' in stats
        assert 'unacknowledged' in stats
        assert 'unresolved' in stats
        assert 'by_type' in stats
        assert 'by_severity' in stats
        assert stats['total_alerts'] >= 2

    def test_cleanup_old_alerts(self, alert_manager):
        """Testa limpeza de alertas antigos."""
        # Criar alerta antigo
        old_alert = RiskAlert(
            id='ALT-OLD',
            alert_type=AlertType.THRESHOLD_VIOLATION,
            severity=AlertSeverity.INFO,
            entity_id='old-entity',
            domain=UnifiedDomain.BUSINESS,
            score=0.5,
            band=RiskBand.MEDIUM,
            message='Old alert',
            details={},
            timestamp=datetime.utcnow() - timedelta(days=60)
        )
        alert_manager._store_alert(old_alert)

        # Limpar alertas com mais de 30 dias
        alert_manager.cleanup_old_alerts(days=30)

        # Alerta antigo deve ter sido removido
        remaining = alert_manager.get_alerts()
        assert old_alert not in remaining

    def test_consecutive_high_risk_tracking(self, alert_manager):
        """Testa rastreamento de risco alto consecutivo."""
        # Múltiplas avaliações de alto risco
        for i in range(5):
            assessment = RiskAssessment(
                score=0.8,
                band=RiskBand.HIGH,
                domain=UnifiedDomain.SECURITY,
                factors={},
                reasoning=f'High risk {i}'
            )
            alert_manager.process_assessment(assessment, 'consecutive-entity')

        # Deve ter rastreado contagens
        assert 'consecutive-entity' in alert_manager._consecutive_high_risk

    def test_custom_rule_triggering(self, alert_manager, risk_history, sample_assessment):
        """Testa regra customizada."""
        # Registrar histórico para detecção de tendência
        now = datetime.utcnow()
        for i in range(10):
            assessment = RiskAssessment(
                score=0.3 + i * 0.05,
                band=RiskBand.MEDIUM,
                domain=UnifiedDomain.BUSINESS,
                factors={},
                reasoning='test'
            )
            assessment.assessed_at = now - timedelta(hours=10 - i)
            alert_manager.risk_history.record_assessment(assessment, 'trend-entity')

        # Criar regra customizada
        custom_rule = AlertRule(
            name='custom_trend',
            alert_type=AlertType.TREND_WORSENING,
            cooldown_minutes=0
        )
        alert_manager.add_rule(custom_rule)

        # Processar avaliação atual
        current = RiskAssessment(
            score=0.9,
            band=RiskBand.HIGH,
            domain=UnifiedDomain.BUSINESS,
            factors={},
            reasoning='Current high'
        )

        alerts = alert_manager.process_assessment(current, 'trend-entity')

        # Pode gerar alerta de tendência
        assert isinstance(alerts, list)
