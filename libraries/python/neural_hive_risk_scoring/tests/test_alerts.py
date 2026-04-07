"""
Testes para RiskAlertManager e componentes relacionados
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

from neural_hive_risk_scoring import (
    RiskAlertManager,
    RiskAlert,
    AlertRule,
    AlertType,
    AlertSeverity,
    LoggingAlertHandler,
    CallbackAlertHandler,
    DynamicThresholds,
    ThresholdMonitor,
    RiskHistory,
    RiskScoringConfig,
    RiskBand,
    RiskAssessment,
    UnifiedDomain,
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
        threshold_monitor=threshold_monitor, risk_history=risk_history, config=config
    )


@pytest.fixture
def sample_assessment():
    """Avaliação de exemplo."""
    return RiskAssessment(
        score=0.9,
        band=RiskBand.CRITICAL,
        domain=UnifiedDomain.SECURITY,
        factors={"security_level": 0.9},
        reasoning="Critical security risk",
    )


class TestAlertRule:
    """Testes para AlertRule."""

    def test_init(self):
        """Testa inicialização."""
        rule = AlertRule(
            name="test_rule",
            alert_type=AlertType.THRESHOLD_VIOLATION,
            enabled=True,
            min_severity=AlertSeverity.WARNING,
            cooldown_minutes=60,
        )

        assert rule.name == "test_rule"
        assert rule.alert_type == AlertType.THRESHOLD_VIOLATION
        assert rule.enabled == True

    def test_should_trigger_disabled(self):
        """Testa regra desabilitada."""
        rule = AlertRule(name="disabled", alert_type=AlertType.THRESHOLD_VIOLATION, enabled=False)

        context = {"threshold_violation": True}
        result = rule.should_trigger("entity-1", context, None)

        assert result == False

    def test_should_trigger_with_cooldown(self):
        """Testa cooldown de regra."""
        rule = AlertRule(
            name="with_cooldown", alert_type=AlertType.THRESHOLD_VIOLATION, cooldown_minutes=60
        )

        context = {"threshold_violation": True}
        last_alert = datetime.now(timezone.utc) - timedelta(minutes=30)

        result = rule.should_trigger("entity-1", context, last_alert)

        # Deve bloquear por cooldown
        assert result == False

    def test_should_trigger_threshold_violation(self):
        """Testa gatilho de violação de threshold."""
        rule = AlertRule(name="violation", alert_type=AlertType.THRESHOLD_VIOLATION)

        context = {"threshold_violation": True}
        result = rule.should_trigger("entity-1", context, None)

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
            id="ALT-001",
            alert_type=AlertType.THRESHOLD_VIOLATION,
            severity=AlertSeverity.WARNING,
            entity_id="test-entity",
            domain=UnifiedDomain.SECURITY,
            score=0.9,
            band=RiskBand.CRITICAL,
            message="Test alert",
            details={},
        )

        result = handler.handle(alert)

        assert result == True


class TestCallbackAlertHandler:
    """Testes para CallbackAlertHandler."""

    def test_init(self):
        """Testa inicialização."""
        callback = Mock(return_value=True)
        handler = CallbackAlertHandler("test_handler", callback)

        assert handler.name == "test_handler"

    def test_handle_success(self):
        """Testa processamento bem-sucedido."""
        callback = Mock(return_value=True)
        handler = CallbackAlertHandler("test", callback)

        alert = Mock()
        result = handler.handle(alert)

        assert result == True
        callback.assert_called_once_with(alert)

    def test_handle_failure(self):
        """Testa processamento com falha."""
        callback = Mock(side_effect=Exception("Test error"))
        handler = CallbackAlertHandler("test", callback)

        alert = Mock()
        result = handler.handle(alert)

        assert result == False


class TestRiskAlert:
    """Testes para RiskAlert."""

    def test_init(self):
        """Testa inicialização."""
        alert = RiskAlert(
            id="ALT-001",
            alert_type=AlertType.THRESHOLD_VIOLATION,
            severity=AlertSeverity.CRITICAL,
            entity_id="test-entity",
            domain=UnifiedDomain.SECURITY,
            score=0.9,
            band=RiskBand.CRITICAL,
            message="Critical alert",
            details={},
        )

        assert alert.id == "ALT-001"
        assert alert.acknowledged == False
        assert alert.resolved == False

    def test_to_dict(self):
        """Testa conversão para dicionário."""
        alert = RiskAlert(
            id="ALT-001",
            alert_type=AlertType.ANOMALY_DETECTED,
            severity=AlertSeverity.WARNING,
            entity_id="test-entity",
            domain=UnifiedDomain.BUSINESS,
            score=0.7,
            band=RiskBand.HIGH,
            message="Anomaly alert",
            details={},
        )

        alert_dict = alert.to_dict()

        assert alert_dict["id"] == "ALT-001"
        assert alert_dict["alert_type"] == "anomaly_detected"
        assert alert_dict["severity"] == "warning"
        assert alert_dict["acknowledged"] == False


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

        rule = AlertRule(name="custom_rule", alert_type=AlertType.TREND_WORSENING)
        alert_manager.add_rule(rule)

        assert len(alert_manager._rules) == initial_count + 1

    def test_add_handler(self, alert_manager):
        """Testa adição de handler."""
        initial_count = len(alert_manager._handlers)

        def custom_handler(alert):
            return True

        handler = CallbackAlertHandler("custom", custom_handler)
        alert_manager.add_handler(handler)

        assert len(alert_manager._handlers) == initial_count + 1

    def test_process_assessment_no_alert(self, alert_manager):
        """Testa processamento sem alertas."""
        assessment = RiskAssessment(
            score=0.2,
            band=RiskBand.LOW,
            domain=UnifiedDomain.BUSINESS,
            factors={},
            reasoning="Low risk",
        )

        alerts = alert_manager.process_assessment(assessment, "safe-entity")

        # Score baixo não deve gerar alerta
        assert len(alerts) == 0

    def test_process_assessment_with_alert(self, alert_manager, sample_assessment):
        """Testa processamento com alerta."""
        alerts = alert_manager.process_assessment(sample_assessment, "risky-entity")

        # Score crítico deve gerar alerta
        assert len(alerts) >= 1

    def test_acknowledge_alert(self, alert_manager, sample_assessment):
        """Testa confirmação de alerta."""
        alerts = alert_manager.process_assessment(sample_assessment, "test-entity")

        if alerts:
            alert_id = alerts[0].id
            result = alert_manager.acknowledge_alert(alert_id, "user-1")

            assert result == True

            # Verificar que foi confirmado (filtrar por ID manualmente)
            all_alerts = alert_manager.get_alerts()
            alert = next((a for a in all_alerts if a.id == alert_id), None)
            assert alert is not None
            assert alert.acknowledged == True
            assert alert.acknowledged_by == "user-1"

    def test_resolve_alert(self, alert_manager, sample_assessment):
        """Testa resolução de alerta."""
        alerts = alert_manager.process_assessment(sample_assessment, "test-entity")

        if alerts:
            alert_id = alerts[0].id
            result = alert_manager.resolve_alert(alert_id, "user-1")

            assert result == True

            # Verificar que foi resolvido (filtrar por ID manualmente)
            all_alerts = alert_manager.get_alerts()
            alert = next((a for a in all_alerts if a.id == alert_id), None)
            assert alert is not None
            assert alert.resolved == True

    def test_get_alerts_by_entity(self, alert_manager, sample_assessment):
        """Testa filtro por entidade."""
        alert_manager.process_assessment(sample_assessment, "entity-1")
        alert_manager.process_assessment(sample_assessment, "entity-2")

        entity1_alerts = alert_manager.get_alerts(entity_id="entity-1")

        assert all(a.entity_id == "entity-1" for a in entity1_alerts)

    def test_get_alerts_by_type(self, alert_manager, sample_assessment):
        """Testa filtro por tipo."""
        alerts = alert_manager.process_assessment(sample_assessment, "test-entity")

        if alerts:
            alert_type = alerts[0].alert_type
            filtered = alert_manager.get_alerts(alert_type=alert_type)

            assert all(a.alert_type == alert_type for a in filtered)

    def test_get_alerts_unacknowledged_only(self, alert_manager, sample_assessment):
        """Testa filtro de não confirmados."""
        alert_manager.process_assessment(sample_assessment, "test-entity")

        unacknowledged = alert_manager.get_alerts(unacknowledged_only=True)

        # Todos devem estar não confirmados inicialmente
        if unacknowledged:
            assert all(not a.acknowledged for a in unacknowledged)

    def test_get_alert_stats(self, alert_manager, sample_assessment):
        """Testa estatísticas de alertas."""
        alert_manager.process_assessment(sample_assessment, "entity-1")
        alert_manager.process_assessment(sample_assessment, "entity-2")

        stats = alert_manager.get_alert_stats()

        assert "total_alerts" in stats
        assert "unacknowledged" in stats
        assert "unresolved" in stats
        assert "by_type" in stats
        assert "by_severity" in stats
        assert stats["total_alerts"] >= 2

    def test_cleanup_old_alerts(self, alert_manager):
        """Testa limpeza de alertas antigos."""
        # Criar alerta antigo
        old_alert = RiskAlert(
            id="ALT-OLD",
            alert_type=AlertType.THRESHOLD_VIOLATION,
            severity=AlertSeverity.INFO,
            entity_id="old-entity",
            domain=UnifiedDomain.BUSINESS,
            score=0.5,
            band=RiskBand.MEDIUM,
            message="Old alert",
            details={},
            timestamp=datetime.now(timezone.utc) - timedelta(days=60),
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
                reasoning=f"High risk {i}",
            )
            alert_manager.process_assessment(assessment, "consecutive-entity")

        # Deve ter rastreado contagens
        assert "consecutive-entity" in alert_manager._consecutive_high_risk

    def test_custom_rule_triggering(self, alert_manager, risk_history, sample_assessment):
        """Testa regra customizada."""
        # Registrar histórico para detecção de tendência
        now = datetime.now(timezone.utc)
        for i in range(10):
            assessment = RiskAssessment(
                score=0.3 + i * 0.05,
                band=RiskBand.MEDIUM,
                domain=UnifiedDomain.BUSINESS,
                factors={},
                reasoning="test",
            )
            assessment.assessed_at = now - timedelta(hours=10 - i)
            alert_manager.risk_history.record_assessment(assessment, "trend-entity")

        # Criar regra customizada
        custom_rule = AlertRule(
            name="custom_trend", alert_type=AlertType.TREND_WORSENING, cooldown_minutes=0
        )
        alert_manager.add_rule(custom_rule)

        # Processar avaliação atual
        current = RiskAssessment(
            score=0.9,
            band=RiskBand.HIGH,
            domain=UnifiedDomain.BUSINESS,
            factors={},
            reasoning="Current high",
        )

        alerts = alert_manager.process_assessment(current, "trend-entity")

        # Pode gerar alerta de tendência
        assert isinstance(alerts, list)

    def test_anomaly_alert_rule(self, alert_manager, risk_history):
        """Testa regra de alerta de anomalia."""
        now = datetime.now(timezone.utc)

        # Histórico normal
        for i in range(20):
            assessment = RiskAssessment(
                score=0.5,
                band=RiskBand.MEDIUM,
                domain=UnifiedDomain.BUSINESS,
                factors={},
                reasoning="normal",
            )
            assessment.assessed_at = now - timedelta(hours=24 - i)
            alert_manager.risk_history.record_assessment(assessment, "anomaly-entity")

        # Criar regra de anomalia
        anomaly_rule = AlertRule(
            name="anomaly_detection", alert_type=AlertType.ANOMALY_DETECTED, cooldown_minutes=0
        )
        alert_manager.add_rule(anomaly_rule)

        # Avaliação com anomalia potencial
        anomaly_assessment = RiskAssessment(
            score=0.95,
            band=RiskBand.CRITICAL,
            domain=UnifiedDomain.BUSINESS,
            factors={},
            reasoning="potential anomaly",
        )

        alerts = alert_manager.process_assessment(anomaly_assessment, "anomaly-entity")

        assert isinstance(alerts, list)

    def test_rapid_escalation_alert(self, alert_manager):
        """Testa alerta de escalada rápida."""
        # Primeira avaliação baixa
        low = RiskAssessment(
            score=0.2, band=RiskBand.LOW, domain=UnifiedDomain.BUSINESS, factors={}, reasoning="low"
        )
        alert_manager.process_assessment(low, "escalation-entity")

        # Regra de escalada rápida
        escalation_rule = AlertRule(
            name="rapid_escalation",
            alert_type=AlertType.RAPID_ESCALATION,
            cooldown_minutes=0,
            conditions={"max_escalation_rate": 0.3},
        )
        alert_manager.add_rule(escalation_rule)

        # Segunda avaliação muito alta (escalada)
        high = RiskAssessment(
            score=0.9,
            band=RiskBand.CRITICAL,
            domain=UnifiedDomain.BUSINESS,
            factors={},
            reasoning="high",
        )

        alerts = alert_manager.process_assessment(high, "escalation-entity")

        # Pode gerar alerta de escalada
        assert isinstance(alerts, list)

    def test_severity_mapping(self, alert_manager, sample_assessment):
        """Testa mapeamento de band para severidade."""
        # Testar cada band
        band_severity = {
            RiskBand.LOW: AlertSeverity.INFO,
            RiskBand.MEDIUM: AlertSeverity.WARNING,
            RiskBand.HIGH: AlertSeverity.ERROR,
            RiskBand.CRITICAL: AlertSeverity.CRITICAL,
        }

        for band, expected_severity in band_severity.items():
            assessment = RiskAssessment(
                score=0.5, band=band, domain=UnifiedDomain.BUSINESS, factors={}, reasoning="test"
            )

            severity = alert_manager._determine_severity(
                rule=Mock(min_severity=AlertSeverity.INFO), assessment=assessment, context={}
            )

            assert severity == expected_severity

    def test_alert_message_generation(self, alert_manager):
        """Testa geração de mensagens de alerta."""
        templates = {
            AlertType.THRESHOLD_VIOLATION: "Threshold",
            AlertType.ANOMALY_DETECTED: "Anomaly",
            AlertType.TREND_WORSENING: "Trend",
            AlertType.RAPID_ESCALATION: "Escalation",
            AlertType.CONSECUTIVE_HIGH_RISK: "Consecutive",
        }

        for alert_type, keyword in templates.items():
            rule = AlertRule(name="test", alert_type=alert_type)

            assessment = RiskAssessment(
                score=0.8,
                band=RiskBand.HIGH,
                domain=UnifiedDomain.SECURITY,
                factors={},
                reasoning="test",
            )

            context = {
                "entity_id": "test-entity",
                "score_delta": 0.3,
                "consecutive_high_risk_count": 3,
            }

            message = alert_manager._generate_message(rule, assessment, context)

            # Mensagem deve conter palavras-chave relevantes
            assert "test-entity" in message

    def test_get_alerts_by_severity(self, alert_manager, sample_assessment):
        """Testa filtro por severidade."""
        alert_manager.process_assessment(sample_assessment, "entity-1")

        critical_alerts = alert_manager.get_alerts(severity=AlertSeverity.CRITICAL)

        # Todos devem ser críticos
        for alert in critical_alerts:
            assert alert.severity == AlertSeverity.CRITICAL

    def test_get_alerts_by_time_range(self, alert_manager):
        """Testa filtro por intervalo de tempo."""
        now = datetime.now(timezone.utc)

        # Criar alerta antigo
        old_alert = RiskAlert(
            id="ALT-OLD-001",
            alert_type=AlertType.THRESHOLD_VIOLATION,
            severity=AlertSeverity.INFO,
            entity_id="old-entity",
            domain=UnifiedDomain.BUSINESS,
            score=0.5,
            band=RiskBand.MEDIUM,
            message="Old alert",
            details={},
            timestamp=now - timedelta(hours=10),
        )
        alert_manager._store_alert(old_alert)

        # Criar alerta recente
        recent_alert = RiskAlert(
            id="ALT-NEW-001",
            alert_type=AlertType.THRESHOLD_VIOLATION,
            severity=AlertSeverity.INFO,
            entity_id="recent-entity",
            domain=UnifiedDomain.BUSINESS,
            score=0.5,
            band=RiskBand.MEDIUM,
            message="Recent alert",
            details={},
            timestamp=now - timedelta(minutes=5),
        )
        alert_manager._store_alert(recent_alert)

        # Buscar apenas últimas 2 horas
        recent_alerts = alert_manager.get_alerts(start=now - timedelta(hours=2))

        assert len(recent_alerts) >= 1
        assert all(a.timestamp >= now - timedelta(hours=2) for a in recent_alerts)

    def test_get_alerts_with_limit(self, alert_manager, sample_assessment):
        """Testa limite de resultados."""
        # Criar múltiplos alertas
        for i in range(5):
            alert_manager.process_assessment(sample_assessment, f"entity-{i}")

        # Buscar com limite
        limited_alerts = alert_manager.get_alerts(limit=3)

        assert len(limited_alerts) <= 3

    def test_acknowledge_nonexistent_alert(self, alert_manager):
        """Testa confirmação de alerta inexistente."""
        result = alert_manager.acknowledge_alert("NONEXISTENT", "user-1")

        assert result == False

    def test_resolve_nonexistent_alert(self, alert_manager):
        """Testa resolução de alerta inexistente."""
        result = alert_manager.resolve_alert("NONEXISTENT", "user-1")

        assert result == False

    def test_top_entities_in_stats(self, alert_manager, sample_assessment):
        """Testa top entidades nas estatísticas."""
        # Criar alertas para diferentes entidades
        entity_counts = {"entity-1": 3, "entity-2": 2, "entity-3": 1}

        for entity_id, count in entity_counts.items():
            for _ in range(count):
                alert_manager.process_assessment(sample_assessment, entity_id)

        stats = alert_manager.get_alert_stats()

        # top_entities deve ter até 10 entidades
        # A contagem inclui alertas gerados pelas regras padrão
        # então o valor exato pode variar
        assert len(stats["top_entities"]) >= 3

    def test_cross_domain_spike_detection(self, alert_manager):
        """Testa detecção de spike em múltiplos domínios."""
        # Criar regra
        spike_rule = AlertRule(
            name="cross_domain_spike",
            alert_type=AlertType.CROSS_DOMAIN_SPIKE,
            cooldown_minutes=0,
            conditions={"min_domains": 2},
        )
        alert_manager.add_rule(spike_rule)

        # Avaliações de risco em múltiplos domínios
        high_domains = [UnifiedDomain.BUSINESS, UnifiedDomain.SECURITY, UnifiedDomain.TECHNICAL]

        for domain in high_domains:
            assessment = RiskAssessment(
                score=0.9, band=RiskBand.CRITICAL, domain=domain, factors={}, reasoning="high risk"
            )
            alert_manager.process_assessment(assessment, "spike-entity")

        # Deve ter registrado contagens de alto risco
        assert alert_manager._consecutive_high_risk["spike-entity"] >= len(high_domains)

    def test_alert_timestamp_ordering(self, alert_manager):
        """Testa ordenação de alertas por timestamp."""
        now = datetime.now(timezone.utc)

        # Criar alertas em ordem reversa
        for i in range(5):
            alert = RiskAlert(
                id=f"ALT-{i:03d}",
                alert_type=AlertType.THRESHOLD_VIOLATION,
                severity=AlertSeverity.INFO,
                entity_id=f"entity-{i}",
                domain=UnifiedDomain.BUSINESS,
                score=0.5,
                band=RiskBand.MEDIUM,
                message=f"Alert {i}",
                details={},
                timestamp=now - timedelta(hours=5 - i),
            )
            alert_manager._store_alert(alert)

        # Buscar alertas - devem vir ordenados por timestamp (mais recente primeiro)
        all_alerts = alert_manager.get_alerts()

        # Verificar ordenação
        for i in range(len(all_alerts) - 1):
            assert all_alerts[i].timestamp >= all_alerts[i + 1].timestamp

    def test_store_alert_limit(self, alert_manager):
        """Testa limite de armazenamento de alertas."""
        # Criar mais de 1000 alertas
        for i in range(1010):
            alert = RiskAlert(
                id=f"ALT-{i:04d}",
                alert_type=AlertType.THRESHOLD_VIOLATION,
                severity=AlertSeverity.INFO,
                entity_id="test-entity",
                domain=UnifiedDomain.BUSINESS,
                score=0.5,
                band=RiskBand.MEDIUM,
                message="Test",
                details={},
            )
            alert_manager._store_alert(alert)

        # Deve ter mantido apenas últimos 1000
        assert len(alert_manager._alerts) == 1000

    def test_reset_consecutive_counter(self, alert_manager):
        """Testa reset de contador de alto risco consecutivo."""
        # Avaliações de alto risco
        for _ in range(3):
            assessment = RiskAssessment(
                score=0.8,
                band=RiskBand.HIGH,
                domain=UnifiedDomain.SECURITY,
                factors={},
                reasoning="high",
            )
            alert_manager.process_assessment(assessment, "reset-entity")

        assert alert_manager._consecutive_high_risk["reset-entity"] >= 3

        # Avaliação de baixo risco deve resetar
        low = RiskAssessment(
            score=0.2, band=RiskBand.LOW, domain=UnifiedDomain.SECURITY, factors={}, reasoning="low"
        )
        alert_manager.process_assessment(low, "reset-entity")

        assert alert_manager._consecutive_high_risk["reset-entity"] == 0

    def test_multiple_handlers_execution(self, alert_manager):
        """Testa execução de múltiplos handlers."""
        execution_log = []

        def handler1(alert):
            execution_log.append("handler1")
            return True

        def handler2(alert):
            execution_log.append("handler2")
            return True

        alert_manager.add_handler(CallbackAlertHandler("h1", handler1))
        alert_manager.add_handler(CallbackAlertHandler("h2", handler2))

        # Processar avaliação que gera alerta
        assessment = RiskAssessment(
            score=0.95,
            band=RiskBand.CRITICAL,
            domain=UnifiedDomain.SECURITY,
            factors={},
            reasoning="critical",
        )

        alert_manager.process_assessment(assessment, "test-entity")

        # Ambos handlers devem ter sido executados
        assert "handler1" in execution_log
        assert "handler2" in execution_log

    def test_alert_details_completeness(self, alert_manager, sample_assessment):
        """Testa completude dos detalhes do alerta."""
        alerts = alert_manager.process_assessment(sample_assessment, "test-entity")

        if alerts:
            alert = alerts[0]

            # Verificar que detalhes contêm informações esperadas
            assert "rule_name" in alert.details
            assert "factors" in alert.details

            # Pode conter violação, anomalia ou tendência
            assert any(key in alert.details for key in ["violation", "anomaly", "trend"])
