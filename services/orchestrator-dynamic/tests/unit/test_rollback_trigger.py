"""
Testes unitários para RollbackTrigger.

Cobre:
- Avaliação de condições de rollback
- Trigger automático baseado em métricas
- Trigger manual
- Integração com HealthMonitor e TrafficSwitcher
- Publicação de eventos Kafka
- Histórico e status de rollback
"""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.services.health_monitor import (
    HealthComparison,
    HealthStatus,
    SystemHealth,
)
from src.services.rollback_trigger import (
    RollbackEvent,
    RollbackReason,
    RollbackStatus,
    RollbackThresholds,
    RollbackTrigger,
    RollbackTriggerConfig,
    RollbackTriggerType,
)

UTC = UTC


@pytest.fixture()
def rollback_thresholds():
    """Fixture para thresholds de rollback."""
    return RollbackThresholds(
        error_rate_critical=0.05,
        error_rate_warning=0.01,
        consecutive_minutes_critical=5,
        p95_latency_critical_ms=2000,
        p95_latency_ratio_warning=2.0,
    )


@pytest.fixture()
def rollback_config(rollback_thresholds):
    """Fixture para configuração do RollbackTrigger."""
    return RollbackTriggerConfig(
        evaluation_interval_seconds=10,  # Mínimo permitido: 10
        thresholds=rollback_thresholds,
        enable_automatic_rollback=True,
        enable_manual_rollback=True,
        enable_kafka_events=False,  # Desabilitar para testes
        enable_webhook_notifications=False,
    )


@pytest.fixture()
def mock_health_monitor():
    """Fixture para HealthMonitor mockado."""
    monitor = MagicMock()
    monitor.get_health_status = AsyncMock()
    return monitor


@pytest.fixture()
def mock_traffic_switcher():
    """Fixture para TrafficSwitcher mockado."""
    switcher = MagicMock()
    switcher.emergency_switch_to_legacy = AsyncMock(return_value=True)
    return switcher


@pytest.fixture()
def rollback_trigger(rollback_config, mock_health_monitor, mock_traffic_switcher):
    """Fixture para RollbackTrigger."""
    return RollbackTrigger(
        config=rollback_config,
        cutover_id="test-cutover-123",
        health_monitor=mock_health_monitor,
        traffic_switcher=mock_traffic_switcher,
        kafka_producer=None,
        webhook_client=None,
    )


@pytest.fixture()
def healthy_comparison():
    """Fixture para comparação de saúde saudável."""
    return HealthComparison(
        legacy_health=SystemHealth(
            service_name="legacy",
            status=HealthStatus.HEALTHY,
            error_rate=0.001,
            latency_p95_ms=100,
        ),
        target_health=SystemHealth(
            service_name="target",
            status=HealthStatus.HEALTHY,
            error_rate=0.001,
            latency_p95_ms=120,
        ),
        overall_status=HealthStatus.HEALTHY,
        should_rollback=False,
        latency_p95_ratio=1.2,
    )


@pytest.fixture()
def critical_error_comparison():
    """Fixture para comparação com error rate crítico."""
    return HealthComparison(
        legacy_health=SystemHealth(
            service_name="legacy",
            status=HealthStatus.HEALTHY,
            error_rate=0.001,
            latency_p95_ms=100,
        ),
        target_health=SystemHealth(
            service_name="target",
            status=HealthStatus.CRITICAL,
            error_rate=0.10,  # 10% - acima do threshold de 5%
            latency_p95_ms=150,
        ),
        overall_status=HealthStatus.CRITICAL,
        should_rollback=True,
        rollback_reason="Error rate 10.00% exceeds rollback threshold 5.00%",
        latency_p95_ratio=1.5,
    )


@pytest.fixture()
def system_down_comparison():
    """Fixture para comparação com sistema DOWN."""
    return HealthComparison(
        legacy_health=SystemHealth(
            service_name="legacy",
            status=HealthStatus.HEALTHY,
            error_rate=0.001,
            latency_p95_ms=100,
        ),
        target_health=SystemHealth(
            service_name="target",
            status=HealthStatus.DOWN,
            error_rate=1.0,
            latency_p95_ms=0,
        ),
        overall_status=HealthStatus.CRITICAL,
        should_rollback=True,
        rollback_reason="Target system is DOWN",
        latency_p95_ratio=0.0,
    )


@pytest.fixture()
def high_latency_comparison():
    """Fixture para comparação com latência alta."""
    return HealthComparison(
        legacy_health=SystemHealth(
            service_name="legacy",
            status=HealthStatus.HEALTHY,
            error_rate=0.001,
            latency_p95_ms=100,
        ),
        target_health=SystemHealth(
            service_name="target",
            status=HealthStatus.HEALTHY,
            error_rate=0.001,
            latency_p95_ms=3000,  # 3s - acima do threshold de 2s
        ),
        overall_status=HealthStatus.CRITICAL,
        should_rollback=True,
        rollback_reason="P95 latency 3000ms exceeds rollback threshold 2000ms",
        latency_p95_ratio=30.0,
    )


class TestRollbackTriggerConfig:
    """Testes para RollbackTriggerConfig."""

    def test_default_config(self):
        """Testa configuração padrão."""
        config = RollbackTriggerConfig()

        assert config.evaluation_interval_seconds == 30
        assert config.enable_automatic_rollback is True
        assert config.enable_manual_rollback is True
        assert config.enable_kafka_events is True
        assert config.max_history_size == 1000

    def test_custom_config(self):
        """Testa configuração customizada."""
        thresholds = RollbackThresholds(error_rate_critical=0.10)
        config = RollbackTriggerConfig(
            evaluation_interval_seconds=60,
            thresholds=thresholds,
            enable_automatic_rollback=False,
        )

        assert config.evaluation_interval_seconds == 60
        assert config.thresholds.error_rate_critical == 0.10
        assert config.enable_automatic_rollback is False


class TestRollbackThresholds:
    """Testes para RollbackThresholds."""

    def test_default_thresholds(self):
        """Testa valores padrão dos thresholds."""
        thresholds = RollbackThresholds()

        assert thresholds.error_rate_critical == 0.05  # 5%
        assert thresholds.error_rate_warning == 0.01  # 1%
        assert thresholds.consecutive_minutes_critical == 5
        assert thresholds.p95_latency_critical_ms == 2000
        assert thresholds.p95_latency_ratio_warning == 2.0

    def test_custom_thresholds(self):
        """Testa thresholds customizados."""
        thresholds = RollbackThresholds(
            error_rate_critical=0.10,
            consecutive_minutes_critical=10,
        )

        assert thresholds.error_rate_critical == 0.10
        assert thresholds.consecutive_minutes_critical == 10


class TestRollbackTriggerInit:
    """Testes para inicialização do RollbackTrigger."""

    def test_initialization(self, rollback_config, mock_health_monitor, mock_traffic_switcher):
        """Testa inicialização correta."""
        trigger = RollbackTrigger(
            config=rollback_config,
            cutover_id="test-cutover",
            health_monitor=mock_health_monitor,
            traffic_switcher=mock_traffic_switcher,
        )

        assert trigger.cutover_id == "test-cutover"
        assert trigger.config == rollback_config
        assert trigger.health_monitor == mock_health_monitor
        assert trigger.traffic_switcher == mock_traffic_switcher
        assert trigger._running is False
        assert trigger._rollback_in_progress is False

    def test_initial_status(self, rollback_trigger):
        """Testa status inicial."""
        status = rollback_trigger._status

        assert status.is_active is False
        assert status.last_rollback_timestamp is None
        assert status.last_rollback_reason is None
        assert status.rollback_count == 0
        assert status.rollback_history == []


class TestEvaluateRollbackConditions:
    """Testes para avaliação de condições de rollback."""

    @pytest.mark.asyncio()
    async def test_healthy_system_no_rollback(self, rollback_trigger, healthy_comparison):
        """Testa que sistema saudável não triggera rollback."""
        should_rollback, reason = await rollback_trigger.evaluate_rollback_conditions(
            healthy_comparison
        )

        assert should_rollback is False
        assert reason is None

    @pytest.mark.asyncio()
    async def test_error_rate_critical_first_minute(self, rollback_trigger, rollback_thresholds):
        """Testa que error rate crítico não triggera no primeiro minuto."""
        # Criar comparação com error rate crítico
        comparison = HealthComparison(
            legacy_health=SystemHealth(
                service_name="legacy",
                status=HealthStatus.HEALTHY,
                error_rate=0.001,
                latency_p95_ms=100,
            ),
            target_health=SystemHealth(
                service_name="target",
                status=HealthStatus.CRITICAL,
                error_rate=rollback_thresholds.error_rate_critical,  # Exatamente no threshold
                latency_p95_ms=150,
            ),
            overall_status=HealthStatus.CRITICAL,
            should_rollback=False,
            latency_p95_ratio=1.5,
        )

        # Primeira avaliação - não deve triggerar
        should_rollback, _reason = await rollback_trigger.evaluate_rollback_conditions(comparison)

        assert should_rollback is False
        assert rollback_trigger._consecutive_critical_minutes == 1

    @pytest.mark.asyncio()
    async def test_error_rate_critical_after_threshold(
        self, rollback_trigger, rollback_thresholds, critical_error_comparison
    ):
        """Testa que error rate crítico triggera após minutos consecutivos."""
        # Simular minutos consecutivos
        for _ in range(rollback_thresholds.consecutive_minutes_critical):
            await rollback_trigger.evaluate_rollback_conditions(critical_error_comparison)

        # Próxima avaliação deve triggerar
        should_rollback, reason = await rollback_trigger.evaluate_rollback_conditions(
            critical_error_comparison
        )

        assert should_rollback is True
        assert reason == RollbackReason.ERROR_RATE_CRITICAL

    @pytest.mark.asyncio()
    async def test_system_down_triggers_immediate(self, rollback_trigger, system_down_comparison):
        """Testa que sistema DOWN triggera imediatamente."""
        should_rollback, reason = await rollback_trigger.evaluate_rollback_conditions(
            system_down_comparison
        )

        assert should_rollback is True
        assert reason == RollbackReason.SYSTEM_DOWN

    @pytest.mark.asyncio()
    async def test_high_latency_triggers_rollback(self, rollback_trigger, high_latency_comparison):
        """Testa que latência alta triggera rollback."""
        should_rollback, reason = await rollback_trigger.evaluate_rollback_conditions(
            high_latency_comparison
        )

        assert should_rollback is True
        assert reason == RollbackReason.LATENCY_CRITICAL

    @pytest.mark.asyncio()
    async def test_data_corruption_triggers_rollback(self, rollback_trigger):
        """Testa que data corruption triggera rollback."""
        comparison = HealthComparison(
            legacy_health=SystemHealth(
                service_name="legacy",
                status=HealthStatus.HEALTHY,
                error_rate=0.001,
                latency_p95_ms=100,
            ),
            target_health=SystemHealth(
                service_name="target",
                status=HealthStatus.HEALTHY,
                error_rate=0.001,
                latency_p95_ms=120,
                anomalies=["data_corruption"],
            ),
            overall_status=HealthStatus.CRITICAL,
            should_rollback=True,
            latency_p95_ratio=1.2,
        )

        should_rollback, reason = await rollback_trigger.evaluate_rollback_conditions(comparison)

        assert should_rollback is True
        assert reason == RollbackReason.DATA_CORRUPTION

    @pytest.mark.asyncio()
    async def test_security_breach_triggers_rollback(self, rollback_trigger):
        """Testa que security breach triggera rollback."""
        comparison = HealthComparison(
            legacy_health=SystemHealth(
                service_name="legacy",
                status=HealthStatus.HEALTHY,
                error_rate=0.001,
                latency_p95_ms=100,
            ),
            target_health=SystemHealth(
                service_name="target",
                status=HealthStatus.HEALTHY,
                error_rate=0.001,
                latency_p95_ms=120,
                anomalies=["security_breach"],
            ),
            overall_status=HealthStatus.CRITICAL,
            should_rollback=True,
            latency_p95_ratio=1.2,
        )

        should_rollback, reason = await rollback_trigger.evaluate_rollback_conditions(comparison)

        assert should_rollback is True
        assert reason == RollbackReason.SECURITY_BREACH

    @pytest.mark.asyncio()
    async def test_consecutive_counter_resets_on_recovery(
        self, rollback_trigger, critical_error_comparison, healthy_comparison
    ):
        """Testa que contador consecutivo reseta com recuperação."""
        # 3 minutos críticos
        for _ in range(3):
            await rollback_trigger.evaluate_rollback_conditions(critical_error_comparison)

        assert rollback_trigger._consecutive_critical_minutes == 3

        # Sistema recupera
        await rollback_trigger.evaluate_rollback_conditions(healthy_comparison)

        assert rollback_trigger._consecutive_critical_minutes == 0


class TestManualRollback:
    """Testes para rollback manual."""

    @pytest.mark.asyncio()
    async def test_manual_rollback_success(self, rollback_trigger):
        """Testa rollback manual bem-sucedido."""
        success, message = await rollback_trigger.trigger_manual_rollback(
            reason=RollbackReason.BUSINESS_CRITICAL_BUG,
            triggered_by="operator@example.com",
            message="Critical bug detected in payment flow",
        )

        assert success is True
        assert "executed successfully" in message.lower()
        assert rollback_trigger._status.rollback_count == 1
        assert rollback_trigger._status.last_rollback_reason == RollbackReason.BUSINESS_CRITICAL_BUG

    @pytest.mark.asyncio()
    async def test_manual_rollback_disabled(self, rollback_config):
        """Testa que rollback manual desabilitado não executa."""
        config = rollback_config.model_copy(update={"enable_manual_rollback": False})
        trigger = RollbackTrigger(config=config, cutover_id="test")

        success, message = await trigger.trigger_manual_rollback(
            reason=RollbackReason.BUSINESS_CRITICAL_BUG,
            triggered_by="operator@example.com",
        )

        assert success is False
        assert "disabled" in message.lower()

    @pytest.mark.asyncio()
    async def test_manual_rollback_when_in_progress(self, rollback_trigger):
        """Testa que não executa rollback quando já há um em progresso."""
        rollback_trigger._rollback_in_progress = True

        success, message = await rollback_trigger.trigger_manual_rollback(
            reason=RollbackReason.BUSINESS_CRITICAL_BUG,
            triggered_by="operator@example.com",
        )

        assert success is False
        assert "already in progress" in message.lower()


class TestAutomaticRollback:
    """Testes para rollback automático."""

    @pytest.mark.asyncio()
    async def test_automatic_rollback_disabled(self, rollback_config, mock_health_monitor):
        """Testa que rollback automático desabilitado não executa."""
        config = rollback_config.model_copy(update={"enable_automatic_rollback": False})
        trigger = RollbackTrigger(
            config=config,
            cutover_id="test",
            health_monitor=mock_health_monitor,
        )

        # Setup health monitor para retornar condição crítica
        mock_health_monitor.get_health_status = AsyncMock(
            return_value=HealthComparison(
                legacy_health=SystemHealth(
                    service_name="legacy",
                    status=HealthStatus.HEALTHY,
                    error_rate=0.001,
                    latency_p95_ms=100,
                ),
                target_health=SystemHealth(
                    service_name="target",
                    status=HealthStatus.DOWN,
                    error_rate=1.0,
                    latency_p95_ms=0,
                ),
                overall_status=HealthStatus.CRITICAL,
                should_rollback=True,
                rollback_reason="Target system is DOWN",
            )
        )

        # Iniciar monitoramento
        await trigger.start_monitoring()

        # Aguardar uma avaliação
        await asyncio.sleep(0.1)

        # Parar monitoramento
        await trigger.stop_monitoring()

        # Verificar que rollback não foi executado
        assert trigger._status.rollback_count == 0

    @pytest.mark.asyncio()
    async def test_automatic_rollback_on_system_down(self, rollback_trigger, mock_health_monitor):
        """Testa rollback automático quando sistema target está DOWN."""
        # Setup health monitor para retornar sistema DOWN
        mock_health_monitor.get_health_status = AsyncMock(
            return_value=HealthComparison(
                legacy_health=SystemHealth(
                    service_name="legacy",
                    status=HealthStatus.HEALTHY,
                    error_rate=0.001,
                    latency_p95_ms=100,
                ),
                target_health=SystemHealth(
                    service_name="target",
                    status=HealthStatus.DOWN,
                    error_rate=1.0,
                    latency_p95_ms=0,
                ),
                overall_status=HealthStatus.CRITICAL,
                should_rollback=True,
                rollback_reason="Target system is DOWN",
            )
        )

        # Iniciar monitoramento
        await rollback_trigger.start_monitoring()

        # Aguardar uma avaliação
        await asyncio.sleep(0.1)

        # Parar monitoramento
        await rollback_trigger.stop_monitoring()

        # Verificar que rollback foi executado
        assert rollback_trigger._status.rollback_count == 1
        assert rollback_trigger._status.last_rollback_reason == RollbackReason.SYSTEM_DOWN
        assert rollback_trigger._status.is_active is True


class TestRollbackStatus:
    """Testes para status de rollback."""

    @pytest.mark.asyncio()
    async def test_get_rollback_status(self, rollback_trigger):
        """Testa obter status de rollback."""
        status = await rollback_trigger.get_rollback_status()

        assert isinstance(status, RollbackStatus)
        assert status.is_active is False
        assert status.rollback_count == 0

    @pytest.mark.asyncio()
    async def test_status_after_rollback(self, rollback_trigger):
        """Testa status após rollback executado."""
        await rollback_trigger.trigger_manual_rollback(
            reason=RollbackReason.OPERATOR_DECISION,
            triggered_by="admin@example.com",
        )

        status = await rollback_trigger.get_rollback_status()

        assert status.is_active is True
        assert status.rollback_count == 1
        assert status.last_rollback_reason == RollbackReason.OPERATOR_DECISION
        assert status.last_rollback_timestamp is not None

    @pytest.mark.asyncio()
    async def test_rollback_history(self, rollback_trigger):
        """Testa histórico de rollbacks."""
        # Executar 3 rollbacks
        for i, reason in enumerate(
            [
                RollbackReason.ERROR_RATE_CRITICAL,
                RollbackReason.SYSTEM_DOWN,
                RollbackReason.LATENCY_CRITICAL,
            ]
        ):
            await rollback_trigger.trigger_manual_rollback(
                reason=reason,
                triggered_by=f"operator{i}@example.com",
            )
            # Resetar status ativo para permitir novo rollback
            await rollback_trigger.reset_rollback_status()

        status = await rollback_trigger.get_rollback_status()

        assert status.rollback_count == 3
        assert len(status.rollback_history) == 3


class TestConfigureThresholds:
    """Testes para configuração de thresholds."""

    def test_configure_thresholds(self, rollback_trigger):
        """Testa configuração de thresholds."""
        new_thresholds = RollbackThresholds(
            error_rate_critical=0.10,  # 10%
            consecutive_minutes_critical=10,
        )

        rollback_trigger.configure_thresholds(new_thresholds)

        assert rollback_trigger.config.thresholds.error_rate_critical == 0.10
        assert rollback_trigger.config.thresholds.consecutive_minutes_critical == 10


class TestGetRollbackEvents:
    """Testes para obter eventos de rollback."""

    @pytest.mark.asyncio()
    async def test_get_rollback_events_empty(self, rollback_trigger):
        """Testa obter eventos quando não há rollbacks."""
        events = rollback_trigger.get_rollback_events()

        assert events == []

    @pytest.mark.asyncio()
    async def test_get_rollback_events_with_data(self, rollback_trigger):
        """Testa obter eventos com rollbacks registrados."""
        await rollback_trigger.trigger_manual_rollback(
            reason=RollbackReason.OPERATOR_DECISION,
            triggered_by="admin@example.com",
        )

        events = rollback_trigger.get_rollback_events()

        assert len(events) == 1
        assert events[0]["trigger_type"] == RollbackTriggerType.MANUAL.value
        assert events[0]["reason"] == RollbackReason.OPERATOR_DECISION.value
        assert events[0]["triggered_by"] == "admin@example.com"

    @pytest.mark.asyncio()
    async def test_get_rollback_events_limit(self, rollback_trigger):
        """Testa limite de eventos retornados."""
        # Executar 5 rollbacks
        for i in range(5):
            await rollback_trigger.trigger_manual_rollback(
                reason=RollbackReason.OPERATOR_DECISION,
                triggered_by=f"operator{i}@example.com",
            )
            await rollback_trigger.reset_rollback_status()

        # Pedir apenas 3
        events = rollback_trigger.get_rollback_events(limit=3)

        assert len(events) == 3


class TestGetEvaluationMetrics:
    """Testes para métricas de avaliação."""

    @pytest.mark.asyncio()
    async def test_get_evaluation_metrics_empty(self, rollback_trigger):
        """Testa métricas quando não há avaliações."""
        metrics = rollback_trigger.get_evaluation_metrics()

        assert metrics["total_evaluations"] == 0
        assert metrics["consecutive_critical_minutes"] == 0

    @pytest.mark.asyncio()
    async def test_get_evaluation_metrics_with_data(self, rollback_trigger, mock_health_monitor):
        """Testa métricas com avaliações registradas."""
        # Setup health monitor para retornar status misto
        responses = [
            HealthComparison(
                legacy_health=SystemHealth(
                    service_name="legacy",
                    status=HealthStatus.HEALTHY,
                    error_rate=0.001,
                    latency_p95_ms=100,
                ),
                target_health=SystemHealth(
                    service_name="target",
                    status=HealthStatus.HEALTHY,
                    error_rate=0.001,
                    latency_p95_ms=120,
                ),
                overall_status=HealthStatus.HEALTHY,
                should_rollback=False,
                latency_p95_ratio=1.2,
            ),
            HealthComparison(
                legacy_health=SystemHealth(
                    service_name="legacy",
                    status=HealthStatus.HEALTHY,
                    error_rate=0.001,
                    latency_p95_ms=100,
                ),
                target_health=SystemHealth(
                    service_name="target",
                    status=HealthStatus.CRITICAL,
                    error_rate=0.10,
                    latency_p95_ms=150,
                ),
                overall_status=HealthStatus.CRITICAL,
                should_rollback=True,
                latency_p95_ratio=1.5,
            ),
        ]

        mock_health_monitor.get_health_status = AsyncMock(side_effect=responses)

        # Adicionar avaliações ao histórico
        for _ in range(2):
            comparison = await mock_health_monitor.get_health_status()
            rollback_trigger._evaluation_history.append(comparison)

        metrics = rollback_trigger.get_evaluation_metrics()

        assert metrics["total_evaluations"] == 2
        assert metrics["critical_evaluations"] == 1
        assert metrics["critical_percentage"] == 0.5


class TestResetRollbackStatus:
    """Testes para reset de status de rollback."""

    @pytest.mark.asyncio()
    async def test_reset_rollback_status(self, rollback_trigger):
        """Testa reset de status ativo."""
        # Executar rollback
        await rollback_trigger.trigger_manual_rollback(
            reason=RollbackReason.OPERATOR_DECISION,
            triggered_by="admin@example.com",
        )

        assert rollback_trigger._status.is_active is True

        # Resetar
        await rollback_trigger.reset_rollback_status()

        assert rollback_trigger._status.is_active is False
        assert rollback_trigger._consecutive_critical_minutes == 0


class TestStartStopMonitoring:
    """Testes para iniciar/parar monitoramento."""

    @pytest.mark.asyncio()
    async def test_start_monitoring(self, rollback_trigger):
        """Testa iniciar monitoramento."""
        await rollback_trigger.start_monitoring()

        assert rollback_trigger._running is True
        assert rollback_trigger._monitor_task is not None

        await rollback_trigger.stop_monitoring()

    @pytest.mark.asyncio()
    async def test_stop_monitoring(self, rollback_trigger):
        """Testa parar monitoramento."""
        await rollback_trigger.start_monitoring()
        await rollback_trigger.stop_monitoring()

        assert rollback_trigger._running is False

    @pytest.mark.asyncio()
    async def test_start_when_already_running(self, rollback_trigger):
        """Testa iniciar quando já está rodando."""
        await rollback_trigger.start_monitoring()

        # Tentar iniciar novamente
        await rollback_trigger.start_monitoring()

        # Apenas um task deve existir
        assert rollback_trigger._monitor_task is not None

        await rollback_trigger.stop_monitoring()


class TestRollbackEvent:
    """Testes para RollbackEvent dataclass."""

    def test_rollback_event_creation(self):
        """Testa criação de evento de rollback."""
        event = RollbackEvent(
            cutover_id="test-cutover",
            timestamp=datetime.now(UTC),
            trigger_type=RollbackTriggerType.AUTOMATIC,
            reason=RollbackReason.ERROR_RATE_CRITICAL,
            metrics={"error_rate": 0.10},
        )

        assert event.cutover_id == "test-cutover"
        assert event.trigger_type == RollbackTriggerType.AUTOMATIC
        assert event.reason == RollbackReason.ERROR_RATE_CRITICAL
        assert event.executed is False
        assert event.execution_result is None

    def test_rollback_event_manual(self):
        """Testa evento de rollback manual."""
        event = RollbackEvent(
            cutover_id="test-cutover",
            timestamp=datetime.now(UTC),
            trigger_type=RollbackTriggerType.MANUAL,
            reason=RollbackReason.OPERATOR_DECISION,
            metrics={},
            triggered_by="admin@example.com",
        )

        assert event.trigger_type == RollbackTriggerType.MANUAL
        assert event.triggered_by == "admin@example.com"


class TestClose:
    """Testes para método close."""

    @pytest.mark.asyncio()
    async def test_close_stops_monitoring(self, rollback_trigger):
        """Testa que close para monitoramento."""
        await rollback_trigger.start_monitoring()

        await rollback_trigger.close()

        assert rollback_trigger._running is False

    @pytest.mark.asyncio()
    async def test_close_without_monitoring(self, rollback_trigger):
        """Testa close sem monitoramento ativo."""
        # Não deve lançar exceção
        await rollback_trigger.close()

        assert rollback_trigger._running is False


class TestIntegrationWithTrafficSwitcher:
    """Testes de integração com TrafficSwitcher."""

    @pytest.mark.asyncio()
    async def test_rollback_calls_traffic_switcher(self, rollback_trigger, mock_traffic_switcher):
        """Testa que rollback chama TrafficSwitcher."""
        await rollback_trigger.trigger_manual_rollback(
            reason=RollbackReason.OPERATOR_DECISION,
            triggered_by="admin@example.com",
        )

        mock_traffic_switcher.emergency_switch_to_legacy.assert_called_once()

    @pytest.mark.asyncio()
    async def test_rollback_with_traffic_switcher_failure(
        self, rollback_trigger, mock_traffic_switcher
    ):
        """Testa rollback quando TrafficSwitcher falha."""
        mock_traffic_switcher.emergency_switch_to_legacy = AsyncMock(return_value=False)

        success, message = await rollback_trigger.trigger_manual_rollback(
            reason=RollbackReason.OPERATOR_DECISION,
            triggered_by="admin@example.com",
        )

        assert success is False
        assert "failed" in message.lower()


class TestLatencyRatioWarning:
    """Testes para warning de ratio de latência."""

    @pytest.mark.asyncio()
    async def test_latency_ratio_warning_logged(self, rollback_trigger):
        """Testa que warning de ratio de latência é logado."""
        comparison = HealthComparison(
            legacy_health=SystemHealth(
                service_name="legacy",
                status=HealthStatus.HEALTHY,
                error_rate=0.001,
                latency_p95_ms=100,
            ),
            target_health=SystemHealth(
                service_name="target",
                status=HealthStatus.HEALTHY,
                error_rate=0.001,
                latency_p95_ms=250,  # 2.5x legacy
            ),
            overall_status=HealthStatus.HEALTHY,
            should_rollback=False,
            latency_p95_ratio=2.5,
        )

        await rollback_trigger.evaluate_rollback_conditions(comparison)

        # Não deve triggerar rollback
        assert rollback_trigger._consecutive_critical_minutes == 0
