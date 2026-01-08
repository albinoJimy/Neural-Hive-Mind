# -*- coding: utf-8 -*-
"""
Testes unitarios para o modulo de analise estatistica.
"""

import pytest
import numpy as np

from src.experimentation.statistical_analysis import (
    StatisticalAnalyzer,
    ContinuousMetricResult,
    BinaryMetricResult,
    BayesianResult,
)


@pytest.fixture
def analyzer():
    """Fixture para StatisticalAnalyzer."""
    return StatisticalAnalyzer(alpha=0.05)


class TestContinuousMetricAnalysis:
    """Testes para analise de metricas continuas."""

    def test_ttest_normal_data(self, analyzer):
        """Testar t-test com dados normalmente distribuidos."""
        np.random.seed(42)
        control = list(np.random.normal(100, 10, 200))
        treatment = list(np.random.normal(95, 10, 200))  # 5% melhor

        result = analyzer.analyze_continuous_metric(
            control_data=control,
            treatment_data=treatment,
            metric_name="latency",
        )

        assert isinstance(result, ContinuousMetricResult)
        assert result.metric_name == "latency"
        assert result.p_value < 0.05  # Significativo
        assert result.effect_size < 0  # Treatment menor (melhor para latency)
        assert result.sample_size_control == 200
        assert result.sample_size_treatment == 200

    def test_mannwhitney_nonnormal_data(self, analyzer):
        """Testar Mann-Whitney U com dados nao-normais."""
        np.random.seed(42)
        # Distribuicao exponencial (assimetrica)
        control = list(np.random.exponential(100, 200))
        treatment = list(np.random.exponential(80, 200))  # Melhor

        result = analyzer.analyze_continuous_metric(
            control_data=control,
            treatment_data=treatment,
            metric_name="response_time",
        )

        assert isinstance(result, ContinuousMetricResult)
        # Deve usar Mann-Whitney para dados nao-normais
        assert result.test_used in ["mann_whitney_u", "welch_t_test", "welch_t_test_fallback"]

    def test_effect_size_interpretation(self, analyzer):
        """Testar interpretacao de effect size."""
        np.random.seed(42)

        # Efeito pequeno
        control = list(np.random.normal(100, 10, 200))
        treatment = list(np.random.normal(98, 10, 200))  # 2% diferenca

        result = analyzer.analyze_continuous_metric(control, treatment, "small_effect")
        assert result.effect_size_interpretation in ["negligible", "small"]

        # Efeito grande
        control = list(np.random.normal(100, 10, 200))
        treatment = list(np.random.normal(70, 10, 200))  # 30% diferenca

        result = analyzer.analyze_continuous_metric(control, treatment, "large_effect")
        assert result.effect_size_interpretation in ["large", "medium"]

    def test_confidence_interval(self, analyzer):
        """Testar intervalo de confianca."""
        np.random.seed(42)
        control = list(np.random.normal(100, 10, 200))
        treatment = list(np.random.normal(90, 10, 200))

        result = analyzer.analyze_continuous_metric(control, treatment, "ci_test")

        ci_lower, ci_upper = result.confidence_interval_95
        assert ci_lower < ci_upper
        # A diferenca de medias deve estar dentro do CI
        mean_diff = result.treatment_mean - result.control_mean
        assert ci_lower <= mean_diff <= ci_upper


class TestBinaryMetricAnalysis:
    """Testes para analise de metricas binarias."""

    def test_chi_square_binary_metric(self, analyzer):
        """Testar chi-square para metricas binarias."""
        # Controle: 10% conversao
        # Treatment: 12% conversao
        result = analyzer.analyze_binary_metric(
            control_successes=100,
            control_total=1000,
            treatment_successes=120,
            treatment_total=1000,
            metric_name="conversion_rate",
        )

        assert isinstance(result, BinaryMetricResult)
        assert result.metric_name == "conversion_rate"
        assert result.control_rate == 0.1
        assert result.treatment_rate == 0.12
        assert result.relative_risk > 1  # Treatment melhor
        assert result.odds_ratio > 1

    def test_chi_square_significant_difference(self, analyzer):
        """Testar chi-square com diferenca significativa."""
        # Grande diferenca
        result = analyzer.analyze_binary_metric(
            control_successes=100,
            control_total=1000,
            treatment_successes=200,
            treatment_total=1000,
            metric_name="large_diff",
        )

        assert result.p_value < 0.05
        assert result.statistically_significant is True

    def test_chi_square_no_difference(self, analyzer):
        """Testar chi-square sem diferenca significativa."""
        # Mesma taxa
        result = analyzer.analyze_binary_metric(
            control_successes=100,
            control_total=1000,
            treatment_successes=102,
            treatment_total=1000,
            metric_name="no_diff",
        )

        # Diferenca muito pequena nao deve ser significativa
        assert result.statistically_significant is False or result.p_value > 0.01


class TestBayesianAnalysis:
    """Testes para analise Bayesiana."""

    def test_bayesian_analysis(self, analyzer):
        """Testar analise Bayesiana basica."""
        np.random.seed(42)
        control = list(np.random.normal(100, 10, 200))
        treatment = list(np.random.normal(90, 10, 200))  # Melhor

        result = analyzer.bayesian_analysis(
            control_data=control,
            treatment_data=treatment,
            metric_name="bayesian_test",
        )

        assert isinstance(result, BayesianResult)
        assert result.metric_name == "bayesian_test"
        assert 0 <= result.probability_of_superiority <= 1
        # Treatment deve ter alta probabilidade de ser superior
        assert result.probability_of_superiority > 0.9

    def test_bayesian_with_priors(self, analyzer):
        """Testar analise Bayesiana com priors informativos."""
        np.random.seed(42)
        control = list(np.random.normal(100, 10, 50))
        treatment = list(np.random.normal(95, 10, 50))

        result = analyzer.bayesian_analysis(
            control_data=control,
            treatment_data=treatment,
            metric_name="prior_test",
            prior_mean=100,
            prior_std=20,
        )

        assert result is not None
        assert result.credible_interval_95_control[0] < result.credible_interval_95_control[1]
        assert result.credible_interval_95_treatment[0] < result.credible_interval_95_treatment[1]

    def test_expected_lift(self, analyzer):
        """Testar calculo de expected lift."""
        np.random.seed(42)
        control = list(np.random.normal(100, 10, 200))
        treatment = list(np.random.normal(80, 10, 200))  # 20% melhor

        result = analyzer.bayesian_analysis(control, treatment, "lift_test")

        # Expected lift deve ser aproximadamente -0.2 (20% reducao)
        assert result.expected_lift < 0
        assert -0.3 < result.expected_lift < -0.1


class TestConfidenceIntervals:
    """Testes para intervalos de confianca."""

    def test_bootstrap_confidence_intervals(self, analyzer):
        """Testar intervalos de confianca via bootstrap."""
        np.random.seed(42)
        data = list(np.random.normal(100, 10, 200))

        ci_lower, ci_upper = analyzer.calculate_confidence_intervals(
            data=data,
            confidence_level=0.95,
            n_bootstrap=1000,
        )

        assert ci_lower < ci_upper
        # Media deve estar dentro do CI
        mean = np.mean(data)
        assert ci_lower <= mean <= ci_upper

    def test_ci_with_small_sample(self, analyzer):
        """Testar CI com amostra pequena."""
        data = [100, 105, 95, 102, 98]

        ci_lower, ci_upper = analyzer.calculate_confidence_intervals(data)

        assert ci_lower < ci_upper


class TestMultipleTesting:
    """Testes para correcao de testes multiplos."""

    def test_bonferroni_correction(self, analyzer):
        """Testar correcao de Bonferroni."""
        p_values = [0.01, 0.03, 0.04, 0.06]

        corrected = analyzer.multiple_testing_correction(
            p_values=p_values,
            method="bonferroni",
        )

        assert len(corrected) == len(p_values)
        # Bonferroni: p * n
        assert corrected[0] == 0.04  # 0.01 * 4
        assert all(c >= p for c, p in zip(corrected, p_values))

    def test_benjamini_hochberg_correction(self, analyzer):
        """Testar correcao de Benjamini-Hochberg."""
        p_values = [0.001, 0.01, 0.02, 0.05, 0.1]

        corrected = analyzer.multiple_testing_correction(
            p_values=p_values,
            method="benjamini_hochberg",
        )

        assert len(corrected) == len(p_values)
        # FDR correction deve ser menos conservadora que Bonferroni

    def test_empty_pvalues(self, analyzer):
        """Testar com lista vazia de p-values."""
        corrected = analyzer.multiple_testing_correction([])
        assert corrected == []


class TestEdgeCases:
    """Testes para casos extremos."""

    def test_identical_data(self, analyzer):
        """Testar com dados identicos."""
        control = [100.0] * 100
        treatment = [100.0] * 100

        result = analyzer.analyze_continuous_metric(control, treatment, "identical")

        # Sem diferenca significativa
        assert result.p_value >= 0.05 or result.effect_size == 0

    def test_single_value_data(self, analyzer):
        """Testar com valor unico."""
        control = [100.0]
        treatment = [90.0]

        result = analyzer.analyze_continuous_metric(control, treatment, "single")

        # Deve processar sem erro
        assert result is not None

    def test_very_different_sample_sizes(self, analyzer):
        """Testar com tamanhos de amostra muito diferentes."""
        np.random.seed(42)
        control = list(np.random.normal(100, 10, 1000))
        treatment = list(np.random.normal(95, 10, 50))

        result = analyzer.analyze_continuous_metric(control, treatment, "unbalanced")

        assert result.sample_size_control == 1000
        assert result.sample_size_treatment == 50
