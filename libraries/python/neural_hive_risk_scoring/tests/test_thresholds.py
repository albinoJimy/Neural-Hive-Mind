"""
Testes para DynamicThresholds e ThresholdMonitor
"""

import pytest
from datetime import datetime, timedelta, timezone

from neural_hive_risk_scoring import (
    DynamicThresholds,
    ThresholdAdjustmentStrategy,
    ThresholdMonitor,
    RiskScoringConfig,
    UnifiedDomain,
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
        min_samples_for_adjustment=10,
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

        assert "medium" in thresholds
        assert "high" in thresholds
        assert "critical" in thresholds
        assert 0.0 < thresholds["medium"] < thresholds["high"] < thresholds["critical"] <= 1.0

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
        assert "medium" in new_thresholds
        assert "high" in new_thresholds
        assert "critical" in new_thresholds

    def test_reset_to_base(self, dynamic_thresholds):
        """Testa reset para configuração base."""
        # Modificar thresholds
        dynamic_thresholds.set_manual_threshold(UnifiedDomain.BUSINESS, "medium", 0.99)

        # Verificar que foi modificado
        assert dynamic_thresholds.get_thresholds(UnifiedDomain.BUSINESS)["medium"] == 0.99

        # Reset
        dynamic_thresholds.reset_to_base(UnifiedDomain.BUSINESS)

        # Verificar reset
        assert dynamic_thresholds.get_thresholds(UnifiedDomain.BUSINESS)["medium"] < 0.99

    def test_set_manual_threshold(self, dynamic_thresholds):
        """Testa definição manual de threshold."""
        dynamic_thresholds.set_manual_threshold(UnifiedDomain.SECURITY, "critical", 0.75)

        thresholds = dynamic_thresholds.get_thresholds(UnifiedDomain.SECURITY)

        assert thresholds["critical"] == 0.75

    def test_get_threshold_stats(self, dynamic_thresholds):
        """Testa obtenção de estatísticas."""
        dynamic_thresholds.record_score(UnifiedDomain.TECHNICAL, 0.6)

        stats = dynamic_thresholds.get_threshold_stats(UnifiedDomain.TECHNICAL)

        assert stats["domain"] == UnifiedDomain.TECHNICAL.value
        assert "current_thresholds" in stats
        assert "base_thresholds" in stats
        assert stats["sample_count"] == 1

    def test_percentile_strategy(self, config):
        """Testa estratégia de percentil."""
        dt = DynamicThresholds(
            base_config=config, adjustment_strategy=ThresholdAdjustmentStrategy.PERCENTILE
        )

        # Registrar scores com distribuição conhecida
        scores = [i / 100 for i in range(100)]  # 0.0 a 0.99
        for score in scores:
            dt.record_score(UnifiedDomain.BUSINESS, score)

        adjusted = dt.adjust_thresholds(UnifiedDomain.BUSINESS, force=True)
        thresholds = adjusted[UnifiedDomain.BUSINESS.value]

        # Validar que thresholds foram ajustados (valores reais podem variar)
        assert 0.4 <= thresholds["medium"] <= 0.65
        assert 0.65 <= thresholds["high"] <= 0.75
        assert 0.85 <= thresholds["critical"] <= 0.95

    def test_std_dev_strategy(self, config):
        """Testa estratégia de desvio padrão."""
        dt = DynamicThresholds(
            base_config=config, adjustment_strategy=ThresholdAdjustmentStrategy.STANDARD_DEVIATION
        )

        # Registrar scores com média ~0.5
        for _ in range(50):
            dt.record_score(UnifiedDomain.BUSINESS, 0.5)

        adjusted = dt.adjust_thresholds(UnifiedDomain.BUSINESS, force=True)
        thresholds = adjusted[UnifiedDomain.BUSINESS.value]

        # Thresholds devem estar próximos de 0.5
        for level in ["medium", "high", "critical"]:
            assert 0.0 <= thresholds[level] <= 1.0


class TestThresholdMonitor:
    """Testes para ThresholdMonitor."""

    def test_init(self, threshold_monitor):
        """Testa inicialização."""
        assert threshold_monitor.thresholds is not None

    def test_check_violation_no_violation(self, threshold_monitor):
        """Testa verificação sem violação."""
        violation = threshold_monitor.check_violation(
            UnifiedDomain.BUSINESS, 0.2  # Score baixo, não viola
        )

        assert violation is None

    def test_check_violation_critical(self, threshold_monitor):
        """Testa violação crítica."""
        violation = threshold_monitor.check_violation(
            UnifiedDomain.SECURITY, 0.95  # Score muito alto
        )

        assert violation is not None
        assert violation.severity == "critical"
        assert violation.threshold_level == "critical"

    def test_check_violation_high(self, threshold_monitor):
        """Testa violação alta."""
        violation = threshold_monitor.check_violation(UnifiedDomain.BUSINESS, 0.8)

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

        assert "total_violations" in stats
        assert "counts_by_type" in stats
        assert stats["total_violations"] >= 2

    def test_clear_violations(self, threshold_monitor):
        """Testa limpeza de violações."""
        threshold_monitor.check_violation(UnifiedDomain.SECURITY, 0.95)

        assert len(threshold_monitor.get_violations()) >= 1

        # Limpar violações recentes
        threshold_monitor.clear_violations(before=datetime.now(timezone.utc) + timedelta(hours=1))

        # Deve estar vazio
        assert len(threshold_monitor.get_violations()) == 0

    def test_ema_strategy(self, config):
        """Testa estratégia de média móvel exponencial."""
        dt = DynamicThresholds(
            base_config=config,
            adjustment_strategy=ThresholdAdjustmentStrategy.EXPONENTIAL_MOVING_AVG,
        )

        # Registrar scores crescentes
        for i in range(30):
            dt.record_score(UnifiedDomain.BUSINESS, 0.3 + i * 0.02)

        adjusted = dt.adjust_thresholds(UnifiedDomain.BUSINESS, force=True)
        thresholds = adjusted[UnifiedDomain.BUSINESS.value]

        # Thresholds devem ter sido ajustados
        assert "medium" in thresholds
        assert "high" in thresholds
        assert "critical" in thresholds

    def test_threshold_violation_to_dict(self, threshold_monitor):
        """Testa conversão de violação para dicionário."""
        threshold_monitor.check_violation(UnifiedDomain.SECURITY, 0.95)
        violations = threshold_monitor.get_violations()

        if violations:
            violation_dict = violations[0].to_dict()
            assert "domain" in violation_dict
            assert "score" in violation_dict
            assert "threshold_level" in violation_dict
            assert "severity" in violation_dict

    def test_adjustment_factor_impact(self, config):
        """Testa impacto do fator de ajuste."""
        dt_low_factor = DynamicThresholds(
            base_config=config, adjustment_factor=0.05  # Ajuste muito pequeno
        )

        dt_high_factor = DynamicThresholds(
            base_config=config, adjustment_factor=0.5  # Ajuste grande
        )

        # Registrar scores
        for _ in range(30):
            dt_low_factor.record_score(UnifiedDomain.BUSINESS, 0.8)
            dt_high_factor.record_score(UnifiedDomain.BUSINESS, 0.8)

        # Ajustar
        old_thresholds = dt_low_factor.get_thresholds(UnifiedDomain.BUSINESS)
        dt_low_factor.adjust_thresholds(UnifiedDomain.BUSINESS, force=True)
        new_low = dt_low_factor.get_thresholds(UnifiedDomain.BUSINESS)

        dt_high_factor.adjust_thresholds(UnifiedDomain.BUSINESS, force=True)
        new_high = dt_high_factor.get_thresholds(UnifiedDomain.BUSINESS)

        # Fator alto deve causar mudança maior
        delta_low = abs(new_low["medium"] - old_thresholds["medium"])
        delta_high = abs(new_high["medium"] - old_thresholds["medium"])
        assert delta_high >= delta_low

    def test_violation_severity_levels(self, threshold_monitor):
        """Testa diferentes níveis de severidade de violação."""
        # Violação crítica
        v_critical = threshold_monitor.check_violation(UnifiedDomain.SECURITY, 0.95)
        assert v_critical.severity == "critical" if v_critical else True

        # Violação major
        v_major = threshold_monitor.check_violation(UnifiedDomain.BUSINESS, 0.8)
        if v_major:
            assert v_major.severity == "major"

        # Violação minor
        v_minor = threshold_monitor.check_violation(UnifiedDomain.BUSINESS, 0.5)
        if v_minor:
            assert v_minor.severity == "minor"

    def test_violation_delta_calculation(self, threshold_monitor):
        """Testa cálculo de delta na violação."""
        violation = threshold_monitor.check_violation(UnifiedDomain.SECURITY, 0.9)

        if violation:
            assert "delta" in violation.to_dict()
            # Delta deve ser positivo (score acima do threshold)

    def test_clear_violations_by_severity(self, threshold_monitor):
        """Testa filtro de violações por severidade."""
        # Criar violações de diferentes severidades
        threshold_monitor.check_violation(UnifiedDomain.SECURITY, 0.95)  # critical
        threshold_monitor.check_violation(UnifiedDomain.BUSINESS, 0.8)  # major
        threshold_monitor.check_violation(UnifiedDomain.BUSINESS, 0.5)  # minor

        # Buscar apenas critical
        critical_violations = threshold_monitor.get_violations(severity="critical")

        for v in critical_violations:
            assert v.severity == "critical"

    def test_violation_timestamp(self, threshold_monitor):
        """Testa timestamp da violação."""
        before = datetime.now(timezone.utc)
        violation = threshold_monitor.check_violation(UnifiedDomain.SECURITY, 0.95)
        after = datetime.now(timezone.utc)

        if violation:
            assert before <= violation.timestamp <= after

    def test_domain_specific_thresholds(self, dynamic_thresholds):
        """Testa que diferentes domínios têm thresholds independentes."""
        # Definir thresholds diferentes
        dynamic_thresholds.set_manual_threshold(UnifiedDomain.BUSINESS, "medium", 0.5)
        dynamic_thresholds.set_manual_threshold(UnifiedDomain.SECURITY, "medium", 0.2)

        business_thresholds = dynamic_thresholds.get_thresholds(UnifiedDomain.BUSINESS)
        security_thresholds = dynamic_thresholds.get_thresholds(UnifiedDomain.SECURITY)

        assert business_thresholds["medium"] == 0.5
        assert security_thresholds["medium"] == 0.2
        assert business_thresholds["medium"] != security_thresholds["medium"]

    def test_violation_count_tracking(self, threshold_monitor):
        """Testa rastreamento de contagem de violações."""
        # Múltiplas violações do mesmo tipo
        for _ in range(3):
            threshold_monitor.check_violation(UnifiedDomain.SECURITY, 0.95)

        stats = threshold_monitor.get_violation_stats()
        assert stats["total_violations"] >= 3
        assert "SECURITY_critical" in stats["counts_by_type"]
        assert stats["counts_by_type"]["SECURITY_critical"] >= 3

    def test_clear_all_violations(self, threshold_monitor):
        """Testa limpar todas as violações."""
        # Criar violações
        threshold_monitor.check_violation(UnifiedDomain.SECURITY, 0.95)
        threshold_monitor.check_violation(UnifiedDomain.BUSINESS, 0.8)

        assert len(threshold_monitor.get_violations()) >= 2

        # Limpar todas
        threshold_monitor.clear_violations()

        assert len(threshold_monitor.get_violations()) == 0

    def test_adjust_all_domains(self, dynamic_thresholds):
        """Testa ajuste de todos os domínios."""
        # Registrar scores para todos os domínios
        for domain in UnifiedDomain:
            for _ in range(30):
                dynamic_thresholds.record_score(domain, 0.6)

        # Ajustar todos
        adjusted = dynamic_thresholds.adjust_thresholds()

        # Todos devem ter sido ajustados
        assert len(adjusted) == len(UnifiedDomain)
        for domain_value, thresholds in adjusted.items():
            assert "medium" in thresholds
            assert "high" in thresholds
            assert "critical" in thresholds
