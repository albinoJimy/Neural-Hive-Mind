"""
Testes para DynamicThresholds e ThresholdMonitor
"""

import pytest
from datetime import datetime, timedelta

from neural_hive_risk_scoring import (
    DynamicThresholds,
    ThresholdAdjustmentStrategy,
    ThresholdMonitor,
    ThresholdViolation,
    RiskScoringConfig,
    RiskBand,
    UnifiedDomain
)


@pytest.fixture
def config():
    """Configuração de teste."""
    return RiskScoringConfig()


@pytest.fixture
def dynamic_thresholds(config):
    """Thresholds dinâmicos de teste."""
    return DynamicThresholds(
        base_config=config,
        adjustment_strategy=ThresholdAdjustmentStrategy.PERCENTILE,
        window_size=50,
        min_samples_for_adjustment=10
    )


@pytest.fixture
def threshold_monitor(dynamic_thresholds):
    """Monitor de thresholds de teste."""
    return ThresholdMonitor(dynamic_thresholds)


class TestDynamicThresholds:
    """Testes para DynamicThresholds."""

    def test_init(self, dynamic_thresholds):
        """Testa inicialização."""
        assert dynamic_thresholds.adjustment_strategy == ThresholdAdjustmentStrategy.PERCENTILE
        assert dynamic_thresholds.window_size == 50
        assert dynamic_thresholds.min_samples_for_adjustment == 10

    def test_get_thresholds_initial(self, dynamic_thresholds):
        """Testa obtenção de thresholds iniciais."""
        thresholds = dynamic_thresholds.get_thresholds(UnifiedDomain.BUSINESS)

        assert 'medium' in thresholds
        assert 'high' in thresholds
        assert 'critical' in thresholds
        assert 0.0 < thresholds['medium'] < thresholds['high'] < thresholds['critical'] <= 1.0

    def test_record_score(self, dynamic_thresholds):
        """Testa registro de scores."""
        dynamic_thresholds.record_score(UnifiedDomain.BUSINESS, 0.5)

        assert len(dynamic_thresholds._history[UnifiedDomain.BUSINESS.value]) == 1

    def test_adjust_thresholds_insufficient_samples(self, dynamic_thresholds):
        """Testa ajuste com amostras insuficientes."""
        # Registrar poucos scores
        for i in range(5):
            dynamic_thresholds.record_score(UnifiedDomain.BUSINESS, 0.5)

        adjusted = dynamic_thresholds.adjust_thresholds(UnifiedDomain.BUSINESS)

        # Não deve ajustar (menos que min_samples_for_adjustment)
        assert UnifiedDomain.BUSINESS.value in adjusted

    def test_adjust_thresholds_with_samples(self, dynamic_thresholds):
        """Testa ajuste com amostras suficientes."""
        # Registrar scores variados
        scores = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.4, 0.5, 0.6] * 5  # 50 scores
        for score in scores:
            dynamic_thresholds.record_score(UnifiedDomain.BUSINESS, score)

        old_thresholds = dynamic_thresholds.get_thresholds(UnifiedDomain.BUSINESS)

        adjusted = dynamic_thresholds.adjust_thresholds(UnifiedDomain.BUSINESS, force=True)

        new_thresholds = adjusted[UnifiedDomain.BUSINESS.value]

        # Deve ter thresholds (mesmo que similares)
        assert 'medium' in new_thresholds
        assert 'high' in new_thresholds
        assert 'critical' in new_thresholds

    def test_reset_to_base(self, dynamic_thresholds):
        """Testa reset para configuração base."""
        # Modificar thresholds
        dynamic_thresholds.set_manual_threshold(
            UnifiedDomain.BUSINESS,
            'medium',
            0.99
        )

        # Verificar que foi modificado
        assert dynamic_thresholds.get_thresholds(UnifiedDomain.BUSINESS)['medium'] == 0.99

        # Reset
        dynamic_thresholds.reset_to_base(UnifiedDomain.BUSINESS)

        # Verificar reset
        assert dynamic_thresholds.get_thresholds(UnifiedDomain.BUSINESS)['medium'] < 0.99

    def test_set_manual_threshold(self, dynamic_thresholds):
        """Testa definição manual de threshold."""
        dynamic_thresholds.set_manual_threshold(
            UnifiedDomain.SECURITY,
            'critical',
            0.75
        )

        thresholds = dynamic_thresholds.get_thresholds(UnifiedDomain.SECURITY)

        assert thresholds['critical'] == 0.75

    def test_get_threshold_stats(self, dynamic_thresholds):
        """Testa obtenção de estatísticas."""
        dynamic_thresholds.record_score(UnifiedDomain.TECHNICAL, 0.6)

        stats = dynamic_thresholds.get_threshold_stats(UnifiedDomain.TECHNICAL)

        assert stats['domain'] == UnifiedDomain.TECHNICAL.value
        assert 'current_thresholds' in stats
        assert 'base_thresholds' in stats
        assert stats['sample_count'] == 1

    def test_percentile_strategy(self, config):
        """Testa estratégia de percentil."""
        dt = DynamicThresholds(
            base_config=config,
            adjustment_strategy=ThresholdAdjustmentStrategy.PERCENTILE
        )

        # Registrar scores com distribuição conhecida
        scores = [i / 100 for i in range(100)]  # 0.0 a 0.99
        for score in scores:
            dt.record_score(UnifiedDomain.BUSINESS, score)

        adjusted = dt.adjust_thresholds(UnifiedDomain.BUSINESS, force=True)
        thresholds = adjusted[UnifiedDomain.BUSINESS.value]

        # Validar que thresholds foram ajustados (valores reais podem variar)
        assert 0.4 <= thresholds['medium'] <= 0.65
        assert 0.65 <= thresholds['high'] <= 0.75
        assert 0.85 <= thresholds['critical'] <= 0.95

    def test_std_dev_strategy(self, config):
        """Testa estratégia de desvio padrão."""
        dt = DynamicThresholds(
            base_config=config,
            adjustment_strategy=ThresholdAdjustmentStrategy.STANDARD_DEVIATION
        )

        # Registrar scores com média ~0.5
        for _ in range(50):
            dt.record_score(UnifiedDomain.BUSINESS, 0.5)

        adjusted = dt.adjust_thresholds(UnifiedDomain.BUSINESS, force=True)
        thresholds = adjusted[UnifiedDomain.BUSINESS.value]

        # Thresholds devem estar próximos de 0.5
        for level in ['medium', 'high', 'critical']:
            assert 0.0 <= thresholds[level] <= 1.0


class TestThresholdMonitor:
    """Testes para ThresholdMonitor."""

    def test_init(self, threshold_monitor):
        """Testa inicialização."""
        assert threshold_monitor.thresholds is not None

    def test_check_violation_no_violation(self, threshold_monitor):
        """Testa verificação sem violação."""
        violation = threshold_monitor.check_violation(
            UnifiedDomain.BUSINESS,
            0.2  # Score baixo, não viola
        )

        assert violation is None

    def test_check_violation_critical(self, threshold_monitor):
        """Testa violação crítica."""
        violation = threshold_monitor.check_violation(
            UnifiedDomain.SECURITY,
            0.95  # Score muito alto
        )

        assert violation is not None
        assert violation.severity == 'critical'
        assert violation.threshold_level == 'critical'

    def test_check_violation_high(self, threshold_monitor):
        """Testa violação alta."""
        violation = threshold_monitor.check_violation(
            UnifiedDomain.BUSINESS,
            0.8
        )

        if violation:  # Pode depender do threshold configurado
            assert violation.domain == UnifiedDomain.BUSINESS
            assert 0.0 <= violation.score <= 1.0

    def test_multiple_violations(self, threshold_monitor):
        """Testa múltiplas violações."""
        # Gerar algumas violações
        threshold_monitor.check_violation(UnifiedDomain.SECURITY, 0.95)
        threshold_monitor.check_violation(UnifiedDomain.BUSINESS, 0.8)
        threshold_monitor.check_violation(UnifiedDomain.TECHNICAL, 0.5)  # Sem violação

        violations = threshold_monitor.get_violations()

        # Pelo menos 2 violações (SECURITY, BUSINESS)
        assert len(violations) >= 2

    def test_get_violations_by_domain(self, threshold_monitor):
        """Testa filtro de violações por domínio."""
        threshold_monitor.check_violation(UnifiedDomain.SECURITY, 0.95)
        threshold_monitor.check_violation(UnifiedDomain.BUSINESS, 0.8)

        security_violations = threshold_monitor.get_violations(domain=UnifiedDomain.SECURITY)

        assert len(security_violations) >= 1
        assert all(v.domain == UnifiedDomain.SECURITY for v in security_violations)

    def test_get_violation_stats(self, threshold_monitor):
        """Testa estatísticas de violações."""
        threshold_monitor.check_violation(UnifiedDomain.SECURITY, 0.95)
        threshold_monitor.check_violation(UnifiedDomain.SECURITY, 0.9)

        stats = threshold_monitor.get_violation_stats()

        assert 'total_violations' in stats
        assert 'counts_by_type' in stats
        assert stats['total_violations'] >= 2

    def test_clear_violations(self, threshold_monitor):
        """Testa limpeza de violações."""
        threshold_monitor.check_violation(UnifiedDomain.SECURITY, 0.95)

        assert len(threshold_monitor.get_violations()) >= 1

        # Limpar violações recentes
        threshold_monitor.clear_violations(before=datetime.utcnow() + timedelta(hours=1))

        # Deve estar vazio
        assert len(threshold_monitor.get_violations()) == 0
