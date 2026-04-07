"""
Testes para Alert Engine do SLA Management System.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta

from src.models.alert_rule import (
    AlertSeverity,
    AlertChannel,
    AlertConditionType,
    AlertCondition,
    AlertRule,
    Alert,
)
from src.models.error_budget import (
    ErrorBudget,
    BudgetStatus,
    BurnRate,
    BurnRateLevel,
)
from src.services.alert_engine import AlertEngine
from src.services.alert_dispatcher import AlertDispatcher


@pytest.fixture
def mock_postgresql_client():
    """Mock do PostgreSQL client."""
    client = MagicMock()
    client.list_slos = AsyncMock(return_value=[])
    client.save_alert = AsyncMock(return_value="alert-123")
    client.list_alerts = AsyncMock(return_value=[])
    client.get_alert_statistics = AsyncMock(
        return_value={
            "total_alerts": 0,
            "alerts_by_severity": {},
            "alerts_by_channel": {},
            "recent_alerts_count": 0,
        }
    )
    client.acknowledge_alert = AsyncMock(return_value=True)
    client.resolve_alert = AsyncMock(return_value=True)
    return client


@pytest.fixture
def mock_redis_client():
    """Mock do Redis client."""
    client = MagicMock()
    client.get_cached_budget = AsyncMock(return_value=None)
    client.setex = AsyncMock()
    return client


@pytest.fixture
def mock_alert_dispatcher():
    """Mock do AlertDispatcher."""
    dispatcher = MagicMock(spec=AlertDispatcher)
    dispatcher.connect = AsyncMock()
    dispatcher.disconnect = AsyncMock()
    dispatcher.dispatch = AsyncMock(return_value=[])
    return dispatcher


@pytest.fixture
def sample_budget():
    """Budget de exemplo."""
    return ErrorBudget(
        budget_id="budget-123",
        slo_id="slo-123",
        service_name="test-service",
        calculated_at=datetime.now(timezone.utc),
        window_start=datetime.now(timezone.utc) - timedelta(days=1),
        window_end=datetime.now(timezone.utc),
        sli_value=0.95,
        slo_target=0.99,
        error_budget_total=1.0,
        error_budget_consumed=40.0,
        error_budget_remaining=60.0,
        status=BudgetStatus.HEALTHY,
        burn_rates=[
            BurnRate(
                window_hours=1,
                rate=1.5,
                level=BurnRateLevel.NORMAL,
                estimated_exhaustion_hours=66.7,
            ),
        ],
        violations_count=2,
    )


@pytest.fixture
def alert_engine(mock_postgresql_client, mock_redis_client, mock_alert_dispatcher):
    """Instância do AlertEngine para testes."""
    engine = AlertEngine(
        postgresql_client=mock_postgresql_client,
        redis_client=mock_redis_client,
        alert_dispatcher=mock_alert_dispatcher,
        check_interval_seconds=60,
    )
    return engine


class TestAlertEngineInit:
    """Testes para inicialização do AlertEngine."""

    def test_init(self, alert_engine):
        """Testa inicialização do AlertEngine."""
        assert alert_engine._running is False
        assert alert_engine._monitoring_task is None
        assert alert_engine.check_interval_seconds == 60


class TestDefaultRules:
    """Testes para regras padrão."""

    def test_create_default_rules(self, alert_engine):
        """Testa criação de regras padrão."""
        alert_engine._create_default_rules()

        # Verificar que regras foram criadas
        assert len(alert_engine._rules) > 0

        # Verificar regras específicas
        assert "budget-critical" in alert_engine._rules
        assert "budget-exhausted" in alert_engine._rules
        assert "burn-rate-critical" in alert_engine._rules

    def test_budget_critical_rule(self, alert_engine):
        """Testa configuração da regra de budget crítico."""
        alert_engine._create_default_rules()

        rule = alert_engine._rules["budget-critical"]
        assert rule.name == "Error Budget Crítico"
        assert rule.severity == AlertSeverity.CRITICAL
        assert rule.condition.condition_type == AlertConditionType.BUDGET_BELOW_THRESHOLD
        assert rule.condition.threshold == 20.0
        assert AlertChannel.SLACK in rule.channels
        assert AlertChannel.ALERTMANAGER in rule.channels

    def test_budget_exhausted_rule(self, alert_engine):
        """Testa configuração da regra de budget esgotado."""
        alert_engine._create_default_rules()

        rule = alert_engine._rules["budget-exhausted"]
        assert rule.name == "Error Budget Esgotado"
        assert rule.severity == AlertSeverity.EMERGENCY
        assert rule.condition.threshold == 5.0
        assert AlertChannel.PAGERDUTY in rule.channels


class TestConditionEvaluation:
    """Testes para avaliação de condições."""

    @pytest.mark.asyncio
    async def test_budget_below_threshold(self, alert_engine, sample_budget):
        """Testa condição de budget abaixo do threshold."""
        condition = AlertCondition(
            condition_type=AlertConditionType.BUDGET_BELOW_THRESHOLD,
            threshold=70.0,
        )

        result = await alert_engine._evaluate_condition(condition, sample_budget)
        assert result is True  # 60% < 70%

    @pytest.mark.asyncio
    async def test_budget_above_threshold(self, alert_engine, sample_budget):
        """Testa condição de budget acima do threshold."""
        condition = AlertCondition(
            condition_type=AlertConditionType.BUDGET_BELOW_THRESHOLD,
            threshold=50.0,
        )

        result = await alert_engine._evaluate_condition(condition, sample_budget)
        assert result is False  # 60% > 50%

    @pytest.mark.asyncio
    async def test_burn_rate_exceeds(self, alert_engine, sample_budget):
        """Testa condição de burn rate alto."""
        condition = AlertCondition(
            condition_type=AlertConditionType.BURN_RATE_EXCEEDS,
            threshold=1.0,
            window_hours=1,
        )

        result = await alert_engine._evaluate_condition(condition, sample_budget)
        assert result is True  # 1.5 > 1.0

    @pytest.mark.asyncio
    async def test_slo_violation_count(self, alert_engine, sample_budget):
        """Testa condição de contagem de violações."""
        condition = AlertCondition(
            condition_type=AlertConditionType.SLO_VIOLATION_COUNT,
            threshold=1,
        )

        result = await alert_engine._evaluate_condition(condition, sample_budget)
        assert result is True  # 2 > 1

    @pytest.mark.asyncio
    async def test_status_change_critical(self, alert_engine, sample_budget):
        """Testa condição de mudança de status."""
        # Alterar status para CRITICAL
        sample_budget.status = BudgetStatus.CRITICAL
        sample_budget.error_budget_remaining = 15.0

        condition = AlertCondition(
            condition_type=AlertConditionType.STATUS_CHANGE,
            threshold=0,
        )

        result = await alert_engine._evaluate_condition(condition, sample_budget)
        assert result is True

    @pytest.mark.asyncio
    async def test_predictive_exhaustion(self, alert_engine):
        """Testa condição de exaustão preditiva."""
        # Budget com burn rate alto que vai esgotar em breve
        budget = ErrorBudget(
            budget_id="budget-456",
            slo_id="slo-456",
            service_name="test-service",
            calculated_at=datetime.now(timezone.utc),
            window_start=datetime.now(timezone.utc) - timedelta(days=1),
            window_end=datetime.now(timezone.utc),
            sli_value=0.90,
            slo_target=0.99,
            error_budget_total=1.0,
            error_budget_consumed=80.0,
            error_budget_remaining=20.0,
            status=BudgetStatus.CRITICAL,
            burn_rates=[
                BurnRate(
                    window_hours=1,
                    rate=10.0,  # Vai esgotar em 10 horas
                    level=BurnRateLevel.CRITICAL,
                    estimated_exhaustion_hours=10.0,
                ),
            ],
            violations_count=5,
        )

        condition = AlertCondition(
            condition_type=AlertConditionType.PREDICTIVE_EXHAUSTION,
            threshold=24.0,  # 24 horas
        )

        result = await alert_engine._evaluate_condition(condition, budget)
        assert result is True  # 10h < 24h


class TestCooldown:
    """Testes para cooldown de alertas."""

    @pytest.mark.asyncio
    async def test_cooldown_active(self, alert_engine):
        """Testa que cooldown evita spam de alertas."""
        alert_engine._rules["test-rule"] = AlertRule(
            rule_id="test-rule",
            name="Test Rule",
            condition=AlertCondition(
                condition_type=AlertConditionType.BUDGET_BELOW_THRESHOLD,
                threshold=50.0,
            ),
            severity=AlertSeverity.WARNING,
            channels=[AlertChannel.SLACK],
            cooldown_minutes=30,
            created_at=datetime.now(timezone.utc),
        )

        # Simular último alerta há 5 minutos
        alert_engine._last_alert_times["test-rule"] = datetime.now(timezone.utc) - timedelta(
            minutes=5
        )

        # Verificar que está em cooldown
        in_cooldown = await alert_engine._is_in_cooldown("test-rule")
        assert in_cooldown is True

    @pytest.mark.asyncio
    async def test_cooldown_expired(self, alert_engine):
        """Testa que cooldown expira após o tempo."""
        alert_engine._rules["test-rule"] = AlertRule(
            rule_id="test-rule",
            name="Test Rule",
            condition=AlertCondition(
                condition_type=AlertConditionType.BUDGET_BELOW_THRESHOLD,
                threshold=50.0,
            ),
            severity=AlertSeverity.WARNING,
            channels=[AlertChannel.SLACK],
            cooldown_minutes=30,
            created_at=datetime.now(timezone.utc),
        )

        # Simular último alerta há 31 minutos
        alert_engine._last_alert_times["test-rule"] = datetime.now(timezone.utc) - timedelta(
            minutes=31
        )

        # Verificar que não está mais em cooldown
        in_cooldown = await alert_engine._is_in_cooldown("test-rule")
        assert in_cooldown is False


class TestAlertMessageCreation:
    """Testes para criação de mensagens de alerta."""

    def test_budget_below_message(self, alert_engine, sample_budget):
        """Testa criação de mensagem para budget baixo."""
        rule = AlertRule(
            rule_id="test-rule",
            name="Test Rule",
            condition=AlertCondition(
                condition_type=AlertConditionType.BUDGET_BELOW_THRESHOLD,
                threshold=70.0,
            ),
            severity=AlertSeverity.CRITICAL,
            channels=[AlertChannel.SLACK],
            cooldown_minutes=30,
            created_at=datetime.now(timezone.utc),
        )

        title, message, details = alert_engine._create_alert_message(rule, sample_budget)

        assert "Crítico" in title
        assert "abaixo do threshold" in message.lower()
        assert details["budget_remaining"] == "60.00%"

    def test_burn_rate_message(self, alert_engine, sample_budget):
        """Testa criação de mensagem para burn rate alto."""
        rule = AlertRule(
            rule_id="test-rule",
            name="Test Rule",
            condition=AlertCondition(
                condition_type=AlertConditionType.BURN_RATE_EXCEEDS,
                threshold=1.0,
                window_hours=1,
            ),
            severity=AlertSeverity.CRITICAL,
            channels=[AlertChannel.SLACK],
            cooldown_minutes=30,
            created_at=datetime.now(timezone.utc),
        )

        title, message, details = alert_engine._create_alert_message(rule, sample_budget)

        assert "Burn Rate" in title
        assert "excede" in message.lower()
        assert "burn_rate" in details


class TestAlertCRUD:
    """Testes para CRUD de regras de alerta."""

    @pytest.mark.asyncio
    async def test_create_rule(self, alert_engine):
        """Testa criação de nova regra."""
        rule = AlertRule(
            rule_id="",  # Deve ser gerado
            name="Nova Regra",
            condition=AlertCondition(
                condition_type=AlertConditionType.BUDGET_BELOW_THRESHOLD,
                threshold=50.0,
            ),
            severity=AlertSeverity.WARNING,
            channels=[AlertChannel.SLACK],
            created_at=datetime.now(timezone.utc),
        )

        created = await alert_engine.create_rule(rule)

        assert created.rule_id.startswith("rule-")
        assert created.name == "Nova Regra"
        assert created.rule_id in alert_engine._rules

    @pytest.mark.asyncio
    async def test_list_rules(self, alert_engine):
        """Testa listagem de regras."""
        alert_engine._create_default_rules()

        rules = await alert_engine.list_rules()

        assert len(rules) > 0
        assert any(r.rule_id == "budget-critical" for r in rules)

    @pytest.mark.asyncio
    async def test_get_rule(self, alert_engine):
        """Testa busca de regra por ID."""
        alert_engine._create_default_rules()

        rule = await alert_engine.get_rule("budget-critical")

        assert rule is not None
        assert rule.name == "Error Budget Crítico"

    @pytest.mark.asyncio
    async def test_update_rule(self, alert_engine):
        """Testa atualização de regra."""
        alert_engine._create_default_rules()

        updated = await alert_engine.update_rule(
            "budget-critical", {"severity": AlertSeverity.EMERGENCY}
        )

        assert updated is not None
        assert updated.severity == AlertSeverity.EMERGENCY

    @pytest.mark.asyncio
    async def test_delete_rule(self, alert_engine):
        """Testa deleção de regra."""
        alert_engine._create_default_rules()

        success = await alert_engine.delete_rule("budget-critical")

        assert success is True
        assert "budget-critical" not in alert_engine._rules

    @pytest.mark.asyncio
    async def test_delete_nonexistent_rule(self, alert_engine):
        """Testa deleção de regra inexistente."""
        success = await alert_engine.delete_rule("nonexistent")

        assert success is False
