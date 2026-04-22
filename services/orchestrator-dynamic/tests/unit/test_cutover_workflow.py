"""
Unit tests para Cutover Workflow.

Testa o gerenciador de cutover, modelos e lógica de rollback.
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

# Adicionar src ao path
src_path = str(Path(__file__).parent.parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from src.models.workflow import (
    CutoverConfig,
    CutoverEvent,
    CutoverMetrics,
    CutoverPhase,
    CutoverStatus,
    RollbackReason,
)


@pytest.fixture()
def sample_cutover_config():
    """Configuração de cutover para testes."""
    return CutoverConfig(
        legacy_service_url="http://legacy.example.com",
        target_service_url="http://target.example.com",
        shadow_duration_hours=168,
        canary_stages=[5, 25, 50, 100],
        canary_min_hours=24,
        rollback_threshold_error_rate=0.05,
        rollback_threshold_p95_latency_ms=2000,
    )


@pytest.fixture()
def sample_cutover_status():
    """Status de cutover para testes."""
    return CutoverStatus(
        cutover_id="cutover-123",
        phase=CutoverPhase.CANARY_5,  # Usar canary para testes de promoção
        traffic_percentage=5,
    )


@pytest.fixture()
def sample_cutover_metrics():
    """Métricas de cutover para testes."""
    return CutoverMetrics(
        phase=CutoverPhase.CANARY_5,
        error_rate=0.01,
        p50_latency_ms=100,
        p95_latency_ms=200,
        p99_latency_ms=400,
        requests_per_second=100.0,
        legacy_p95_latency_ms=180,
    )


class TestCutoverConfig:
    """Testes de configuração do cutover."""

    def test_create_default_config(self):
        """Deve criar configuração com valores padrão."""
        config = CutoverConfig(
            legacy_service_url="http://legacy.example.com",
            target_service_url="http://target.example.com",
        )

        assert config.shadow_duration_hours == 168
        assert config.canary_stages == [5, 25, 50, 100]
        assert config.canary_min_hours == 24
        assert config.rollback_threshold_error_rate == 0.05
        assert config.rollback_threshold_p95_latency_ms == 2000
        assert config.enable_auto_rollback is True
        assert config.enable_auto_promote is True

    def test_custom_canary_stages(self):
        """Deve aceitar estágios canary customizados."""
        config = CutoverConfig(
            legacy_service_url="http://legacy.example.com",
            target_service_url="http://target.example.com",
            canary_stages=[10, 50, 100],
        )

        assert config.canary_stages == [10, 50, 100]

    def test_invalid_canary_stages_unordered(self):
        """Deve rejeitar estágios canary fora de ordem."""
        with pytest.raises(ValueError, match="ordem crescente"):
            CutoverConfig(
                legacy_service_url="http://legacy.example.com",
                target_service_url="http://target.example.com",
                canary_stages=[50, 25, 100],
            )

    def test_invalid_canary_stages_no_100(self):
        """Deve rejeitar estágios canary sem 100%."""
        with pytest.raises(ValueError, match="Último estágio deve ser 100"):
            CutoverConfig(
                legacy_service_url="http://legacy.example.com",
                target_service_url="http://target.example.com",
                canary_stages=[5, 25, 50],
            )

    def test_invalid_shadow_duration_too_short(self):
        """Deve rejeitar shadow mode muito curto."""
        from pydantic_core._pydantic_core import ValidationError

        with pytest.raises(ValidationError, match="greater than or equal to 24"):
            CutoverConfig(
                legacy_service_url="http://legacy.example.com",
                target_service_url="http://target.example.com",
                shadow_duration_hours=12,
            )

    def test_invalid_error_rate_negative(self):
        """Deve rejeitar error rate negativo."""
        with pytest.raises(ValueError):
            CutoverConfig(
                legacy_service_url="http://legacy.example.com",
                target_service_url="http://target.example.com",
                rollback_threshold_error_rate=-0.01,
            )


class TestCutoverMetrics:
    """Testes de métricas de cutover."""

    def test_create_metrics(self, sample_cutover_metrics):
        """Deve criar métricas com valores válidos."""
        metrics = sample_cutover_metrics

        assert metrics.phase == CutoverPhase.CANARY_5
        assert metrics.error_rate == 0.01
        assert metrics.p95_latency_ms == 200
        assert metrics.legacy_p95_latency_ms == 180
        assert metrics.anomaly_detected is False

    def test_error_rate_boundary(self):
        """Deve respeitar limites de error rate."""
        # Valor válido
        metrics = CutoverMetrics(
            phase=CutoverPhase.CANARY_5,
            error_rate=0.0,
        )
        assert metrics.error_rate == 0.0

        # Valor válido
        metrics = CutoverMetrics(
            phase=CutoverPhase.CANARY_5,
            error_rate=1.0,
        )
        assert metrics.error_rate == 1.0

    def test_invalid_error_rate(self):
        """Deve rejeitar error rate fora dos limites."""
        with pytest.raises(ValueError):
            CutoverMetrics(
                phase=CutoverPhase.CANARY_5,
                error_rate=1.5,  # > 1.0
            )

        with pytest.raises(ValueError):
            CutoverMetrics(
                phase=CutoverPhase.CANARY_5,
                error_rate=-0.1,  # < 0.0
            )

    def test_latency_must_be_positive(self):
        """Deve rejeitar latência negativa."""
        with pytest.raises(ValueError):
            CutoverMetrics(
                phase=CutoverPhase.CANARY_5,
                p95_latency_ms=-100,
            )


class TestCutoverStatus:
    """Testes de status do cutover."""

    def test_create_status(self, sample_cutover_status):
        """Deve criar status com valores válidos."""
        status = sample_cutover_status

        assert status.cutover_id == "cutover-123"
        assert status.phase == CutoverPhase.CANARY_5
        assert status.traffic_percentage == 5
        assert status.started_at is not None

    def test_shadow_mode_must_have_zero_traffic(self):
        """Deve exigir 0% de tráfego em shadow mode."""
        with pytest.raises(ValueError, match="Shadow mode deve ter 0%"):
            CutoverStatus(
                cutover_id="cutover-123",
                phase=CutoverPhase.SHADOW_MODE,
                traffic_percentage=5,  # Inválido
            )

    def test_full_cutover_must_have_100_traffic(self):
        """Deve exigir 100% de tráfego em full cutover."""
        with pytest.raises(ValueError, match="Full cutover deve ter 100%"):
            CutoverStatus(
                cutover_id="cutover-123",
                phase=CutoverPhase.FULL_CUTOVER,
                traffic_percentage=50,  # Inválido
            )

    def test_rolled_back_must_have_zero_traffic(self):
        """Deve exigir 0% de tráfego após rollback."""
        with pytest.raises(ValueError, match="Rolled back deve ter 0%"):
            CutoverStatus(
                cutover_id="cutover-123",
                phase=CutoverPhase.ROLLED_BACK,
                traffic_percentage=100,  # Inválido
            )

    def test_add_metrics(self, sample_cutover_status, sample_cutover_metrics):
        """Deve adicionar métricas ao histórico."""
        status = sample_cutover_status
        metrics = sample_cutover_metrics

        status.add_metrics(metrics)

        assert len(status.metrics_history) == 1
        assert status.current_metrics == metrics
        assert status.current_metrics.error_rate == 0.01

    def test_metrics_history_limit(self, sample_cutover_status):
        """Deve limitar histórico a 1000 métricas."""
        status = sample_cutover_status

        # Adicionar 1500 métricas
        for i in range(1500):
            metrics = CutoverMetrics(
                phase=CutoverPhase.CANARY_5,
                error_rate=0.01,
            )
            status.add_metrics(metrics)

        # Deve ter apenas as últimas 1000
        assert len(status.metrics_history) == 1000

    def test_get_metrics_summary_empty(self, sample_cutover_status):
        """Deve retornar resumo vazio quando sem métricas."""
        summary = sample_cutover_status.get_metrics_summary()

        assert summary["total_samples"] == 0
        assert summary["avg_error_rate"] == 0.0
        assert summary["max_error_rate"] == 0.0

    def test_get_metrics_summary_with_data(self, sample_cutover_status, sample_cutover_metrics):
        """Deve calcular resumo correto com métricas."""
        status = sample_cutover_status

        # Adicionar métricas com valores conhecidos
        metrics1 = CutoverMetrics(
            phase=CutoverPhase.CANARY_5,
            error_rate=0.01,
            p95_latency_ms=100,
        )
        metrics2 = CutoverMetrics(
            phase=CutoverPhase.CANARY_5,
            error_rate=0.02,
            p95_latency_ms=200,
        )

        status.add_metrics(metrics1)
        status.add_metrics(metrics2)

        summary = status.get_metrics_summary()

        assert summary["total_samples"] == 2
        assert summary["avg_error_rate"] == 0.015
        assert summary["max_error_rate"] == 0.02
        assert summary["avg_p95_latency_ms"] == 150
        assert summary["max_p95_latency_ms"] == 200


class TestRollbackConditions:
    """Testes de condições de rollback."""

    def test_should_trigger_rollback_error_rate_exceeded(
        self, sample_cutover_status, sample_cutover_config
    ):
        """Deve acionar rollback quando error rate excede threshold."""
        status = sample_cutover_status
        config = sample_cutover_config

        # Métricas com error rate alto (6% > 5%)
        metrics = CutoverMetrics(
            phase=CutoverPhase.CANARY_5,
            error_rate=0.06,
            p95_latency_ms=100,
        )
        status.add_metrics(metrics)

        should_rollback, reason = status.should_trigger_rollback(config)

        assert should_rollback is True
        assert "error rate" in reason.lower()
        assert "6.00%" in reason

    def test_should_trigger_rollback_latency_high(
        self, sample_cutover_status, sample_cutover_config
    ):
        """Deve acionar rollback quando latência excede threshold."""
        status = sample_cutover_status
        config = sample_cutover_config

        # Métricas com latência alta (2500ms > 2000ms)
        metrics = CutoverMetrics(
            phase=CutoverPhase.CANARY_5,
            error_rate=0.01,
            p95_latency_ms=2500,
        )
        status.add_metrics(metrics)

        should_rollback, reason = status.should_trigger_rollback(config)

        assert should_rollback is True
        assert "latência" in reason.lower() or "latency" in reason.lower()

    def test_should_trigger_rollback_latency_2x_legacy(
        self, sample_cutover_status, sample_cutover_config
    ):
        """Deve acionar rollback quando latência é 2x legacy."""
        status = sample_cutover_status
        config = sample_cutover_config

        # Métricas com latência 2.5x legacy
        metrics = CutoverMetrics(
            phase=CutoverPhase.CANARY_5,
            error_rate=0.01,
            p95_latency_ms=500,
            legacy_p95_latency_ms=200,  # 2.5x
        )
        status.add_metrics(metrics)

        should_rollback, reason = status.should_trigger_rollback(config)

        assert should_rollback is True
        assert "2.5x" in reason

    def test_should_not_trigger_rollback_healthy(
        self, sample_cutover_status, sample_cutover_config
    ):
        """Não deve acionar rollback com métricas saudáveis."""
        status = sample_cutover_status
        config = sample_cutover_config

        # Métricas saudáveis
        metrics = CutoverMetrics(
            phase=CutoverPhase.CANARY_5,
            error_rate=0.01,  # 1% < 5%
            p95_latency_ms=150,  # < 2000ms
            legacy_p95_latency_ms=140,  # ~1.07x
        )
        status.add_metrics(metrics)

        should_rollback, reason = status.should_trigger_rollback(config)

        assert should_rollback is False
        assert reason is None

    def test_should_trigger_rollback_anomaly_detected(
        self, sample_cutover_status, sample_cutover_config
    ):
        """Deve acionar rollback quando anomalia é detectada."""
        status = sample_cutover_status
        config = sample_cutover_config

        # Métricas com anomalia
        metrics = CutoverMetrics(
            phase=CutoverPhase.CANARY_5,
            error_rate=0.01,
            p95_latency_ms=150,
            anomaly_detected=True,
        )
        status.add_metrics(metrics)

        should_rollback, reason = status.should_trigger_rollback(config)

        assert should_rollback is True
        assert "anomalia" in reason.lower()


class TestPromotionConditions:
    """Testes de condições de promoção de fase."""

    def test_cannot_promote_time_not_elapsed(self, sample_cutover_status, sample_cutover_config):
        """Não deve promover se tempo mínimo não decorreu."""
        status = sample_cutover_status
        config = sample_cutover_config

        # Status criado agora, tempo não decorrido
        can_promote, reason = status.can_promote_to_next_phase(config)

        assert can_promote is False
        assert "Tempo mínimo não atingido" in reason

    def test_can_promote_after_min_time(self, sample_cutover_status, sample_cutover_config):
        """Deve permitir promoção após tempo mínimo."""
        status = sample_cutover_status
        config = sample_cutover_config

        # Simular tempo decorrido - usar um pouco mais que o mínimo para garantir
        # canary_min_hours = 24, então usamos 25 horas
        status.current_phase_start = datetime.now() - timedelta(hours=25, seconds=1)

        can_promote, reason = status.can_promote_to_next_phase(config)

        assert can_promote is True
        assert reason is None

    def test_cannot_promote_high_error_rate(self, sample_cutover_status, sample_cutover_config):
        """Não deve promover com error rate alto."""
        status = sample_cutover_status
        config = sample_cutover_config

        # Tempo decorrido - usar um pouco mais que o mínimo
        status.current_phase_start = datetime.now() - timedelta(hours=25, seconds=1)

        # Adicionar métricas com error rate alto (3% > 2.5%)
        metrics = CutoverMetrics(
            phase=CutoverPhase.CANARY_5,
            error_rate=0.03,
        )
        status.add_metrics(metrics)

        can_promote, reason = status.can_promote_to_next_phase(config)

        assert can_promote is False
        assert "error rate" in reason.lower()


class TestCutoverPhases:
    """Testes de fases do cutover."""

    def test_phase_values(self):
        """Deve ter todas as fases esperadas."""
        expected_phases = [
            "shadow_mode",
            "canary_5",
            "canary_25",
            "canary_50",
            "full_cutover",
            "rolled_back",
            "completed",
            "paused",
        ]

        actual_phases = [phase.value for phase in CutoverPhase]

        for expected in expected_phases:
            assert expected in actual_phases

    def test_rollback_reason_values(self):
        """Deve ter todos os motivos de rollback esperados."""
        expected_reasons = [
            "error_rate_exceeded",
            "latency_high",
            "system_down",
            "data_corruption",
            "manual_request",
            "business_critical_bug",
        ]

        actual_reasons = [reason.value for reason in RollbackReason]

        for expected in expected_reasons:
            assert expected in actual_reasons


class TestCutoverEvent:
    """Testes de eventos de cutover."""

    def test_create_event(self):
        """Deve criar evento com valores válidos."""
        event = CutoverEvent(
            event_id="event-123",
            cutover_id="cutover-123",
            event_type="cutover.started",
            phase=CutoverPhase.SHADOW_MODE,
        )

        assert event.event_id == "event-123"
        assert event.cutover_id == "cutover-123"
        assert event.event_type == "cutover.started"
        assert event.phase == CutoverPhase.SHADOW_MODE
        assert event.success is True
        assert event.timestamp is not None

    def test_create_event_with_previous_phase(self):
        """Deve criar evento com fase anterior."""
        event = CutoverEvent(
            event_id="event-456",
            cutover_id="cutover-123",
            event_type="cutover.phase_changed",
            phase=CutoverPhase.CANARY_5,
            previous_phase=CutoverPhase.SHADOW_MODE,
            message="Transição de shadow_mode para canary_5",
        )

        assert event.phase == CutoverPhase.CANARY_5
        assert event.previous_phase == CutoverPhase.SHADOW_MODE
        assert event.message == "Transição de shadow_mode para canary_5"
